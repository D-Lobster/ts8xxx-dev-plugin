#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPK2 (PCA63100 Power Profiler Kit II) 功耗自动测量工具
=======================================================
协议依据: Nordic pc-nrfconnect-ppk 上位机源码 (src/device/serialDevice.ts,
src/constants.ts, worker/serialDevice.js) 与 PPK2 固件 1.2.4 提取的元数据格式。

物理层 : USB CDC 虚拟串口, 115200 baud, 8N1
命令层 : 单字节命令码 + 定长参数(小端, RegulatorSet 例外为大端 2 字节)
数据层 : 连续 4 字节小端样本流 (见 parse_sample)

用法:
  ppk2.py scan                       # 枚举并识别 PPK2 串口
  ppk2.py info  --port COMx          # 连接 + 读元数据(校准系数/VDD), 验证连接
  ppk2.py measure --port COMx [选项] # 配置并采集, 输出 .bin + .json
  ppk2.py analyze --input file.bin   # 统计分析(整体/分位/区间/电量/丢包)
"""
import argparse
import json
import os
import statistics
import struct
import sys
import time
from datetime import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.stderr.write("缺少 pyserial, 请执行: pip install pyserial\n")
    sys.exit(2)

# ---------------------------------------------------------------- 协议常量
BAUD = 115200
# 采样时间 10us -> 100kHz 连续采样
ADC_SAMPLING_TIME_US = 10

# 命令码 (来自 pc-nrfconnect-ppk/src/constants.ts)
CMD = {
    "TriggerSet": 0x01,
    "TriggerWindowSet": 0x03,
    "TriggerSingleSet": 0x05,
    "AverageStart": 0x06,
    "AverageStop": 0x07,
    "DeviceRunningSet": 0x0C,
    "RegulatorSet": 0x0D,
    "SwitchPointDown": 0x0E,
    "SwitchPointUp": 0x0F,
    "SetPowerMode": 0x11,
    "ResUserSet": 0x12,
    "SpikeFilteringOn": 0x15,
    "SpikeFilteringOff": 0x16,
    "GetMetadata": 0x19,
    "Reset": 0x20,
    "SetUserGains": 0x25,
}

POWER_MODE_SMU = 2   # SMU: PPK2 给 DUT 供电并测量
POWER_MODE_AM = 1    # Ampere meter: 外部供电只测电流

VDD_RANGE = (800, 5000)  # mV

# 元数据键: 量程电阻 R, 增益 GS/GI, 偏移 O, 温度/电源系数 S/I, 用户增益 UG
META_KEYS = (
    [f"R{i}" for i in range(5)]
    + [f"GS{i}" for i in range(5)]
    + [f"GI{i}" for i in range(5)]
    + [f"O{i}" for i in range(5)]
    + [f"S{i}" for i in range(5)]
    + [f"I{i}" for i in range(5)]
    + [f"UG{i}" for i in range(5)]
    + ["VDD", "MODE"]
)

# 元数据缺省值 (与上位机 serialDevice.ts 默认一致)
DEFAULT_META = {f"R{i}": r for i, r in enumerate([1031.64, 101.65, 10.15, 0.94, 0.043])}
DEFAULT_META.update({f"GS{i}": 1.0 for i in range(5)})
DEFAULT_META.update({f"GI{i}": 1.0 for i in range(5)})
DEFAULT_META.update({f"O{i}": 0.0 for i in range(5)})
DEFAULT_META.update({f"S{i}": 0.0 for i in range(5)})
DEFAULT_META.update({f"I{i}": 0.0 for i in range(5)})
DEFAULT_META.update({f"UG{i}": 1.0 for i in range(5)})
DEFAULT_META["VDD"] = 5000
DEFAULT_META["MODE"] = 2  # 2=SMU(供电+测量), 1=Ampere(外部供电只测电流)

# ADC 满量程系数: 1.8V 满量程 / 163840 (14bit 左移 2 位后 16bit)
ADC_MULT = 1.8 / 163840
DATALOSS_THRESHOLD = 500  # 与上位机一致: 500*10us = 5ms 允许丢失


# ---------------------------------------------------------------- 串口识别
# 电源控制: 供 ts800x-flash 等流程调用 —— 芯片深度睡眠时 JLink 连不上,
# 用 PPK2 重新上电(cycle) 唤醒后 JLink 才能重新连接烧录
def cmd_power(args):
    vdd = args.vdd
    if not (VDD_RANGE[0] <= vdd <= VDD_RANGE[1]):
        sys.stderr.write(f"VDD 超出范围 {VDD_RANGE} mV\n")
        return 2
    if args.hold_open < 0:
        sys.stderr.write("--hold-open 不能为负数\n")
        return 2
    ser = open_port(args.port)
    try:
        # 连接验证: 元数据 (失败=PPK2 不可用, 禁止继续)
        text = read_metadata(ser)
        if text is None:
            return 1
        meta, _ = parse_metadata(text)
        if args.state == "off":
            send(ser, CMD["DeviceRunningSet"], 0)  # DUT 电源 OFF
            print("DUT 电源 OFF")
        else:  # on / cycle
            if args.state == "cycle":
                # 先断电 -> 保持 hold 秒(电容放电/芯片彻底掉电) -> 重新上电
                send(ser, CMD["DeviceRunningSet"], 0)
                time.sleep(args.hold)
            mode_matches = int(round(meta["MODE"])) == POWER_MODE_SMU
            vdd_matches = int(round(meta["VDD"])) == vdd
            if not mode_matches:
                send(ser, CMD["SetPowerMode"], POWER_MODE_SMU)  # SMU: PPK2 供电
                time.sleep(0.1)
            if not vdd_matches:
                send(ser, CMD["RegulatorSet"], (vdd >> 8) & 0xFF, vdd & 0xFF)
                time.sleep(0.2)
            send(ser, CMD["DeviceRunningSet"], 1)  # DUT 电源 ON (VDD 输出)
            if mode_matches and vdd_matches:
                print(f"复用当前 PPK2 配置: SMU, VDD={vdd}mV")
            if args.state == "cycle":
                print(f"DUT 已重新上电 (断电保持 {args.hold}s 后恢复, VDD={vdd}mV)")
            else:
                print(f"DUT 电源 ON: VDD={vdd}mV (SMU)")
            if args.hold_open > 0:
                print(f"保持 PPK2 控制会话 {args.hold_open}s，供外部 JLink 操作")
                deadline = time.monotonic() + args.hold_open
                while time.monotonic() < deadline:
                    time.sleep(min(0.1, deadline - time.monotonic()))
        return 0
    finally:
        ser.close()


def is_ppk2_port(p):
    """PPK2 枚举特征: Nordic VID 0x1915 或描述含 nRF/JLink CDC/PPK。
    不匹配的端口仍可通过 --port 显式指定使用。"""
    vid = p.vid or 0
    desc = (p.description or "").lower()
    hwid = (p.hwid or "").lower()
    if vid == 0x1915:
        return True
    if any(k in desc for k in ("jlink cdc", "nrf", "ppk", "nordic")):
        return True
    if any(k in hwid for k in ("1915", "nordic")):
        return True
    return False


def cmd_scan(args):
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("未发现任何串口。检查 PPK2 USB 连接。")
        return 1
    found = []
    for p in ports:
        tag = " <-- 疑似 PPK2" if is_ppk2_port(p) else ""
        vp = "unknown" if p.vid is None else f"{p.vid:04X}:{p.pid:04X}"
        print(f"{p.device:8s} {p.description:45s} VID:PID={vp}{tag}")
        if is_ppk2_port(p):
            found.append(p.device)
    if not found:
        print("\n未识别出 PPK2。若 PPK2 已插入, 请检查驱动/其他程序占用, 或用 --port 显式指定。")
        return 1
    return 0


def open_port(port, timeout=2.0):
    try:
        return serial.Serial(port, BAUD, timeout=timeout, write_timeout=2.0)
    except serial.SerialException as e:
        sys.stderr.write(f"打开 {port} 失败: {e}\n(可能被其他程序占用, 或不是 PPK2)\n")
        sys.exit(2)


# ---------------------------------------------------------------- 协议实现
def send(ser, *data):
    ser.write(bytes(data))
    ser.flush()


def parse_metadata(text):
    """解析固件元数据文本 (直到 END):
    'R0: 1.8\nR1: ... VDD: 5000\n... END'
    返回 (meta_dict, 缺失键列表)。"""
    text = text.split("END", 1)[0]
    meta = {}
    for m in text.replace("\r", "\n").split("\n"):
        m = m.strip()
        if not m:
            continue
        for kv in m.split(","):
            kv = kv.strip()
            if ":" not in kv:
                continue
            k, v = kv.split(":", 1)
            k, v = k.strip().upper(), v.strip()
            if k in META_KEYS:
                try:
                    meta[k] = float(v)
                except ValueError:
                    sys.stderr.write(f"元数据键 {k} 值非法: {v!r}\n")
    missing = [k for k in META_KEYS if k not in meta]
    # 缺省值回填, 供电流换算使用
    for k in META_KEYS:
        meta.setdefault(k, DEFAULT_META[k])
    return meta, missing


def read_metadata(ser):
    """发送 0x19 GetMetadata, 累积文本直到 'END' 出现。"""
    ser.reset_input_buffer()
    send(ser, CMD["GetMetadata"])
    buf = b""
    deadline = time.time() + 3.0
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            if b"END" in buf:
                return buf.decode("ascii", errors="replace")
        else:
            time.sleep(0.02)
    sys.stderr.write("元数据读取超时(3s), 连接不可用\n")
    return None


def parse_sample(b):
    """4 字节小端样本 -> (adc_raw, range, counter, bits)
    bit0-13: ADC (值 x4), bit14-16: 量程, bit18-23: 计数器, bit24-31: 数字逻辑
    (bit17 为保留位; 真机位翻转验证: bit18 每样本翻转 ~1/1, bit19 ~1/2, bit20 ~1/4)"""
    v = struct.unpack("<I", b)[0]
    return (v & 0x3FFF), ((v >> 14) & 0x7), ((v >> 18) & 0x3F), ((v >> 24) & 0xFF)


def sample_current_ua(adc_raw, rng, meta, vdd_mv):
    """电流换算 (与 serialDevice.ts getAdcResult 一致), 返回 µA。"""
    rng = min(rng, 4)
    adc_val = adc_raw * 4
    x = (adc_val - meta[f"O{rng}"]) * (ADC_MULT / meta[f"R{rng}"])
    cur = meta[f"UG{rng}"] * (
        x * (meta[f"GS{rng}"] * x + meta[f"GI{rng}"])
        + (meta[f"S{rng}"] * (vdd_mv / 1000.0) + meta[f"I{rng}"])
    )
    return cur * 1e6


# ---------------------------------------------------------------- 测量
def cmd_info(args):
    ser = open_port(args.port)
    try:
        text = read_metadata(ser)
        if text is None:
            return 1
        meta, missing = parse_metadata(text)
        if missing:
            sys.stderr.write(f"警告: 元数据缺失键(用缺省值): {missing}\n")
        print(f"端口      : {args.port}")
        print(f"元数据    : 解析成功, END 结尾, {len(meta)} 键")
        print(f"量程电阻  : " + " ".join(f"R{i}={meta[f'R{i}']:.4f}" for i in range(5)))
        print(f"用户增益  : " + " ".join(f"UG{i}={meta[f'UG{i}']:.4f}" for i in range(5)))
        print(f"VDD(元数据): {meta['VDD']:.0f} mV")
        print("连接验证: 通过")
        return 0
    finally:
        ser.close()


def cmd_measure(args):
    vdd = args.vdd
    if not (VDD_RANGE[0] <= vdd <= VDD_RANGE[1]):
        sys.stderr.write(f"VDD 超出范围 {VDD_RANGE} mV\n")
        return 2

    ser = open_port(args.port)
    try:
        # 1. 连接验证: 元数据
        text = read_metadata(ser)
        if text is None:
            return 1
        meta, missing = parse_metadata(text)
        if missing:
            sys.stderr.write(f"警告: 元数据缺失键(用缺省值): {missing}\n")

        # 2. 配置: 模式 -> VDD -> 打开 DUT 电源 (官方序列:
        #    SetPowerMode -> RegulatorSet -> DeviceRunningSet(ON) -> AverageStart)
        mode = POWER_MODE_SMU if args.mode == "smu" else POWER_MODE_AM
        send(ser, CMD["SetPowerMode"], mode)
        time.sleep(0.1)
        send(ser, CMD["RegulatorSet"], (vdd >> 8) & 0xFF, vdd & 0xFF)
        time.sleep(0.2)
        if getattr(args, "no_power", False):
            # --no-power: 电源由外部保持, 本采集不触碰 DeviceRunningSet
            time.sleep(min(args.settle, 0.5))
        else:
            send(ser, CMD["DeviceRunningSet"], 1)  # DUT 电源 ON (VDD 输出)
            # 上电稳定时间: 刚上电有启动瞬态, 等 settle 秒后再采集才准
            time.sleep(args.settle)
        send(ser, CMD["AverageStop"])
        time.sleep(0.1)

        # 3. 启动采集
        send(ser, CMD["AverageStart"])
        t0 = time.time()
        samples = 0
        dropped = 0
        expected = None
        remainder = b""
        out_bin = open(args.output + ".bin", "wb")

        print(f"开始采集: {args.port} VDD={vdd}mV 模式={args.mode} 时长={args.duration}s ...")
        print("按 Ctrl+C 提前停止")
        deadline = t0 + args.duration
        try:
            while time.time() < deadline:
                chunk = ser.read(4096)
                if not chunk:
                    time.sleep(0.01)
                    continue
                buf = remainder + chunk
                n_full = len(buf) // 4
                out_bin.write(buf[: n_full * 4])
                remainder = buf[n_full * 4 :]
                for i in range(n_full):
                    adc, rng, counter, bits = parse_sample(buf[i * 4 : i * 4 + 4])
                    samples += 1
                    if expected is None:
                        expected = counter
                    else:
                        exp = (expected + 1) & 0x3F  # 期望的当前样本值
                        if counter != exp:
                            diff = (counter - exp + 64) & 0x3F
                            dropped += diff
                        expected = counter
        except KeyboardInterrupt:
            print("\n用户中断, 停止采集")
        finally:
            out_bin.close()
            send(ser, CMD["AverageStop"])
            if not getattr(args, "keep_power", False) and not getattr(args, "no_power", False):
                send(ser, CMD["DeviceRunningSet"], 0)  # 关 DUT 电源, 恢复默认
            time.sleep(0.1)

        dur = time.time() - t0
        loss_pct = 100.0 * dropped / (samples + dropped) if (samples + dropped) else 0.0
        summary = {
            "port": args.port,
            "vdd_mv": vdd,
            "mode": args.mode,
            "duration_s": round(dur, 3),
            "samples": samples,
            "sample_rate_hz": round(samples / dur, 1) if dur else 0,
            "dropped_samples": dropped,
            "data_loss_pct": round(loss_pct, 4),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "metadata": {k: meta[k] for k in META_KEYS if k in meta},
        }
        with open(args.output + ".json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"采集完成: {samples} 样本, {dur:.2f}s, 丢包 {dropped} ({loss_pct:.4f}%)")
        print(f"输出: {args.output}.bin (原始4字节样本) + {args.output}.json (摘要)")
        if loss_pct > 1.0:
            sys.stderr.write(f"警告: 丢包率 {loss_pct:.2f}% 超过 1%, 结论需标注数据不完整\n")
        return 0
    finally:
        ser.close()


# ---------------------------------------------------------------- 分析
def cmd_analyze(args):
    bin_path = args.input
    if not os.path.exists(bin_path):
        sys.stderr.write(f"文件不存在: {bin_path}\n")
        return 2
    meta_path = bin_path[:-4] + ".json"
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            summary = json.load(f)
        meta = summary.get("metadata", {})
        vdd = summary.get("vdd_mv", DEFAULT_META["VDD"])
    else:
        vdd = args.vdd
    for k in META_KEYS:
        meta.setdefault(k, DEFAULT_META[k])

    with open(bin_path, "rb") as f:
        raw = f.read()
    n = len(raw) // 4
    if n == 0:
        sys.stderr.write("无样本数据\n")
        return 2

    times = []   # us
    currents = []  # uA
    powers = []  # mW (逐样本: uA * V / 1000)
    ranges = []
    bits_list = []
    prev_counter = None
    dropped = 0
    for i in range(n):
        adc, rng, counter, bits = parse_sample(raw[i * 4 : i * 4 + 4])
        if prev_counter is not None:
            diff = (counter - prev_counter - 1) % 64
            # 允许计数器正常递增; diff>0 表示丢包
            if diff:
                dropped += diff
        prev_counter = counter
        times.append(i * ADC_SAMPLING_TIME_US)
        cur = sample_current_ua(adc, rng, meta, vdd)
        currents.append(cur)
        powers.append(cur * vdd / 1e6)  # uA * mV / 1e6 = mW
        ranges.append(rng)
        bits_list.append(bits)
    dur_s = n * ADC_SAMPLING_TIME_US / 1e6
    loss_pct = 100.0 * dropped / (n + dropped) if (n + dropped) else 0.0

    def pct(p):
        return statistics.quantiles(currents, n=100, method="inclusive")[int(p) - 1]

    def pct_p(p):
        return statistics.quantiles(powers, n=100, method="inclusive")[int(p) - 1]

    mean_ua = statistics.fmean(currents)
    min_ua = min(currents)
    max_ua = max(currents)
    mean_mw = statistics.fmean(powers)
    min_mw = min(powers)
    max_mw = max(powers)
    mah = mean_ua * dur_s / 3600.0 / 1000.0
    mwh = mean_mw * dur_s / 3600.0  # 平均功耗 x 时长

    # 睡眠/活跃双态: 以 --phase-threshold µA 切分
    phases = None
    if args.phase_threshold is not None:
        low_i = [(c, p) for c, p in zip(currents, powers) if c < args.phase_threshold]
        high_i = [(c, p) for c, p in zip(currents, powers) if c >= args.phase_threshold]
        phases = {
            "threshold_ua": args.phase_threshold,
            "low": {
                "samples": len(low_i),
                "time_s": round(len(low_i) * ADC_SAMPLING_TIME_US / 1e6, 4),
                "mean_ua": round(statistics.fmean([c for c, _ in low_i]), 3) if low_i else None,
                "p90_ua": round(statistics.quantiles([c for c, _ in low_i], n=100, method="inclusive")[89], 3) if low_i else None,
                "mean_mw": round(statistics.fmean([p for _, p in low_i]), 4) if low_i else None,
            },
            "high": {
                "samples": len(high_i),
                "time_s": round(len(high_i) * ADC_SAMPLING_TIME_US / 1e6, 4),
                "mean_ua": round(statistics.fmean([c for c, _ in high_i]), 3) if high_i else None,
                "p90_ua": round(statistics.quantiles([c for c, _ in high_i], n=100, method="inclusive")[89], 3) if high_i else None,
                "mean_mw": round(statistics.fmean([p for _, p in high_i]), 4) if high_i else None,
            },
        }

    # 按量程统计 (量程切换伪影会在 R 高量程出现负值)
    range_stats = {}
    for r in sorted(set(ranges)):
        rs = [c for c, rr in zip(currents, ranges) if rr == r]
        range_stats[f"range{r}"] = {
            "samples": len(rs),
            "mean_ua": round(statistics.fmean(rs), 3),
            "min_ua": round(min(rs), 3),
            "max_ua": round(max(rs), 3),
        }

    result = {
        "file": bin_path,
        "samples": n,
        "duration_s": round(dur_s, 4),
        "dropped_samples": dropped,
        "data_loss_pct": round(loss_pct, 4),
        "vdd_mv": vdd,
        # 电流
        "mean_ua": round(mean_ua, 3),
        "min_ua": round(min_ua, 3),
        "max_ua": round(max_ua, 3),
        "p50_ua": round(pct(50), 3),
        "p90_ua": round(pct(90), 3),
        "p99_ua": round(pct(99), 3),
        "p99_9_ua": round(pct(99.9), 3),
        # 功耗 (mW)
        "mean_mw": round(mean_mw, 4),
        "min_mw": round(min_mw, 4),
        "max_mw": round(max_mw, 4),
        "p50_mw": round(pct_p(50), 4),
        "p90_mw": round(pct_p(90), 4),
        "p99_mw": round(pct_p(99), 4),
        # 能量
        "charge_mah": round(mah, 6),
        "energy_mwh": round(mwh, 6),
        "phases": phases,
        "range_stats": range_stats,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    out_json = args.output or (bin_path[:-4] + "_analysis.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n分析结果已写入: {out_json}")
    if loss_pct > 1.0:
        sys.stderr.write(f"警告: 丢包率 {loss_pct:.2f}% 超过 1%, 结论需标注数据不完整\n")
    return 0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="PPK2 功耗分析仪自动测量工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="枚举串口并识别 PPK2")

    p = sub.add_parser("info", help="连接并读取元数据(校准系数), 验证连接")
    p.add_argument("--port", required=True, help="PPK2 串口, 如 COM4")

    p = sub.add_parser("power", help="直接控制 DUT 电源: on/off/cycle (唤醒休眠芯片供 JLink 烧录)")
    p.add_argument("--port", required=True, help="PPK2 串口, 如 COM4")
    p.add_argument("--state", choices=["on", "off", "cycle"], required=True,
                   help="on=上电, off=断电, cycle=断电->保持->重新上电")
    p.add_argument("--vdd", type=int, default=3000, help="上电电压 mV (800-5000), cycle 恢复时使用")
    p.add_argument("--hold", type=float, default=1.5,
                   help="cycle 断电保持秒数(默认 1.5, 让电容放电芯片彻底掉电)")
    p.add_argument("--hold-open", type=float, default=0.0,
                   help="on/cycle 后保持串口会话秒数，供 JLink 在此窗口内连接/烧录")

    p = sub.add_parser("measure", help="配置并采集功耗数据")
    p.add_argument("--port", required=True, help="PPK2 串口, 如 COM4")
    p.add_argument("--vdd", type=int, default=3000, help="DUT 供电电压 mV (800-5000)")
    p.add_argument("--mode", choices=["smu", "am"], default="smu",
                   help="smu=PPK2供电+测量, am=外部供电只测电流")
    p.add_argument("--duration", type=float, required=True, help="采集时长 秒")
    p.add_argument("--settle", type=float, default=2.0,
                   help="上电后稳定等待秒数(默认 2.0, 避开启动瞬态)")
    p.add_argument("--keep-power", action="store_true",
                   help="采集结束后不关 DUT 电源 (测休眠/连续状态时保持供电)")
    p.add_argument("--no-power", action="store_true",
                   help="完全不触碰 DUT 电源开关 (电源由外部保持, 只采集)")
    p.add_argument("--output", required=True, help="输出文件前缀, 生成 .bin+.json")

    p = sub.add_parser("analyze", help="分析采集的 .bin 数据")
    p.add_argument("--input", required=True, help=".bin 文件 (同目录 .json 摘要会被自动读取)")
    p.add_argument("--vdd", type=int, default=None, help="无 .json 时手工指定 VDD mV")
    p.add_argument("--phase-threshold", type=float, default=None,
                   help="双态切分阈值 µA (低于=低功耗态, 高于=活跃态)")
    p.add_argument("--output", default=None, help="分析结果 JSON 输出路径")

    args = ap.parse_args()
    rc = {"scan": cmd_scan, "info": cmd_info, "power": cmd_power,
          "measure": cmd_measure, "analyze": cmd_analyze}[args.cmd](args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
