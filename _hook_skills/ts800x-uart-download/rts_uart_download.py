#!/usr/bin/env python3
"""
TS800X UART RTS 自动烧录工具

通过 CH340 的 RTS 管脚控制芯片硬件 RESET，实现完全无人值守烧录：

    RTS 拉低 100ms（复位）→ 释放（芯片进入 ROM bootloader）
    → 连续 SYNC → [BAUD] → [ERASE] → DOWNLOAD → BOOT

协议实现复用兄弟技能 ts800x-uart-download 的 uart_download.py，避免重复维护。
本脚本只增加 RTS 复位时序和对应的 CLI。

用法:
  python rts_uart_download.py --list
  python rts_uart_download.py --firmware firmware.hex --port COM15 --erase
  python rts_uart_download.py --port COM15 --sync-only -V
"""

import argparse
import os
import sys
import time
from pathlib import Path

# ------------------------------------------------------------
# 复用协议实现 uart_download.py：优先兄弟技能目录（本机安装场景），
# 找不到则回退到本目录内置副本（单包自包含场景，便于分发）。
# ------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_SIBLING_DIR = _THIS_DIR.parent / "ts800x-uart-download"
_UD_SOURCE = None
for _dir in (_SIBLING_DIR, _THIS_DIR):
    # 先确认文件存在再尝试导入，避免 sys.path 中其他同名模块被误加载
    if not (_dir / "uart_download.py").is_file():
        continue
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
    try:
        import uart_download as ud
        _UD_SOURCE = _dir
        break
    except ImportError:
        if str(_dir) in sys.path:
            sys.path.remove(str(_dir))
        continue
else:
    print("错误: 无法导入 uart_download.py（协议实现依赖）")
    print(f"已尝试: {_SIBLING_DIR}（兄弟技能）和 {_THIS_DIR}（内置副本）")
    sys.exit(99)

# ------------------------------------------------------------
# 常量
# ------------------------------------------------------------
RTS_HOLD_MS_DEFAULT = 100      # 已验证值：RTS 拉低 100ms
SYNC_TIMEOUT_MS_DEFAULT = 30000


def rts_reset_pulse(bl, hold_ms: int, active_high: bool = False):
    """RTS 复位脉冲：拉低(默认) hold_ms 后释放。

    CH340 极性: setRTS(True)->管脚低电平; setRTS(False)->管脚高电平。
    默认低有效复位（RTS 拉低 = 复位），目标板反极性时用 --rts-active-high。
    返回 True 表示脉冲完成。
    """
    ser = bl.serial
    if ser is None or not ser.is_open:
        bl._log("ERROR: 串口未打开，无法执行 RTS 复位")
        return False

    # 打开后先归一化 RTS/DTR 为高电平，避免上电瞬间误触发
    try:
        ser.setRTS(False)
        ser.setDTR(False)
    except Exception as exc:
        bl._log(f"ERROR: 归一化 RTS/DTR 失败: {exc}")
        return False

    time.sleep(0.05)  # 稳定

    # 复位脉冲
    if active_high:
        # RTS 高 = 复位
        bl._log(f"RTS 复位: 置高 {hold_ms}ms (active-high)...")
        ser.setRTS(True)
        time.sleep(hold_ms / 1000.0)
        ser.setRTS(False)
    else:
        # RTS 低 = 复位（已验证默认）
        bl._log(f"RTS 复位: 拉低 {hold_ms}ms ...")
        ser.setRTS(True)
        time.sleep(hold_ms / 1000.0)
        ser.setRTS(False)

    bl._log("RTS 已释放，芯片应进入 ROM bootloader")
    return True


def step_wait_sync_rts(bl, total_timeout_ms: int = SYNC_TIMEOUT_MS_DEFAULT) -> bool:
    """RTS 释放后连续 SYNC 重试，直到 bootloader 响应或超时。

    与 uart_download.py 的 step_wait_sync 逻辑一致，但日志面向 RTS 自动复位。
    """
    if not bl.serial or not bl.serial.is_open:
        bl._log("ERROR: 串口未打开，无法执行 SYNC")
        return False

    bl._log("SYNC: 等待 ROM bootloader 响应 (RTS 已自动复位)...")
    bl.flush_input()

    sync_cmd = ud.build_command(ud.BLDR_SYNC)
    deadline = time.monotonic() + total_timeout_ms / 1000.0
    recv_buf = bytearray()

    while time.monotonic() < deadline:
        try:
            bl.serial.write(sync_cmd)
            bl.serial.flush()
        except Exception as exc:
            bl._log(f"SYNC: 串口写入失败: {exc}")
            return False

        poll_deadline = time.monotonic() + ud.MAX_SYNC_INTERVAL_MS / 1000.0
        while time.monotonic() < poll_deadline:
            try:
                chunk = bl.serial.read(64)
                if chunk:
                    bl._vlog(f"SYNC RX: {chunk.hex().upper()}")
                    recv_buf.extend(chunk)
                    flag, _ = ud.parse_response(bytes(recv_buf))
                    if flag is not None:
                        if flag == ud.BLDR_COMMAND_SUCCESS:
                            bl._log("SYNC: OK - 检测到 ROM bootloader")
                            return True
                        else:
                            bl._log(f"SYNC: 收到错误响应 flag={flag:#04x}")
                            recv_buf.clear()
            except Exception as exc:
                bl._log(f"SYNC: 串口读取失败: {exc}")
                return False
            time.sleep(0.002)

        if len(recv_buf) > ud.SYNC_RECV_BUFFER_MAX:
            del recv_buf[:-(ud.SERIAL_HDR_SIZE + 4)]

    bl._log("SYNC: 超时 - 未检测到 bootloader（检查 RTS 接线/极性/供电）")
    return False


def run_rts_download(bl, bin_data, flash_addr, args) -> tuple:
    """RTS 复位下载流程。返回 (success, fail_phase)。"""
    # 1. RTS 复位脉冲
    if not rts_reset_pulse(bl, args.rts_hold_ms, args.rts_active_high):
        return False, 'rts'

    # 2. 连续 SYNC
    if not step_wait_sync_rts(bl, args.sync_timeout):
        return False, 'sync'

    if args.sync_only:
        bl._log("SYNC-ONLY: 已确认 ROM bootloader 响应，未执行擦除或下载")
        return True, ''

    # 3. BAUD (可选)
    if args.baud != ud.SERIAL_DEFAULT_BAUD:
        if not bl.step_change_baud(args.baud):
            return False, 'baud'

    # 4. ERASE (可选)
    if args.erase:
        if not bl.step_erase(args.erase_blocks):
            return False, 'erase'

    # 5. DOWNLOAD
    packets = ud.build_download_packets(bin_data, flash_addr)
    ok, _ = bl.step_download(packets)
    if not ok:
        return False, 'download'

    # 6. BOOT
    if not bl.step_boot(flash_addr, args.allow_boot_no_response):
        return False, 'boot'

    return True, ''


CH340_VID_PID_HINTS = ("1A86:7523", "1A86:5523", "VID:PID=1A86")


def select_rts_port(port_arg):
    """选择目标串口：优先 CH340（RTS 控制必需）。

    规则：
      1. 显式 --port：校验存在后直接使用。
      2. 未指定：优先自动选择 CH340（VID:PID 1A86:7523 常见型号），
         因为 RTS 复位依赖 CH340 的 RTS 管脚。
      3. 多个 CH340 时明确报错，要求用 --port 指定，避免烧错设备。
    """
    available = ud.scan_ports()
    if not available:
        print("错误: 未检测到可用串口")
        sys.exit(2)

    if port_arg:
        avail_names = [p['device'] for p in available]
        if port_arg not in avail_names:
            print(f"错误: 串口 {port_arg} 不存在")
            print(f"可用串口: {', '.join(avail_names)}")
            sys.exit(2)
        return port_arg

    # 未指定端口：筛选 CH340 设备（hwid 含 1A86:7523 等）
    ch340_ports = [
        p['device'] for p in available
        if any(hint.lower() in (p.get('hwid') or '').lower()
               for hint in CH340_VID_PID_HINTS)
    ]
    if len(ch340_ports) == 1:
        print(f"自动选择 CH340 串口: {ch340_ports[0]}")
        return ch340_ports[0]
    if len(ch340_ports) > 1:
        print(f"错误: 检测到多个 CH340 串口: {', '.join(ch340_ports)}")
        print("请使用 --port 明确指定目标串口，避免烧录到错误设备")
        sys.exit(2)

    # 无 CH340：退回第一个可用串口（可能是其他 USB 转串口）
    print(f"警告: 未检测到 CH340，自动选择第一个可用串口 {available[0]['device']}")
    print("提示: RTS 复位需要 CH340 (或支持 RTS 控制的 USB 转串口)")
    return available[0]['device']


def main():
    parser = argparse.ArgumentParser(
        description='TS800X UART RTS 自动烧录（RTS 硬件复位，无需人工按键）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python rts_uart_download.py --list
  python rts_uart_download.py --firmware firmware.hex --port COM15 --erase
  python rts_uart_download.py --port COM15 --sync-only -V
        ''',
    )

    parser.add_argument('--firmware', '-f', metavar='PATH', dest='bin',
                        help='固件文件路径（支持 .bin / .hex）')
    parser.add_argument('--port', metavar='PORT',
                        help='目标串口 (如 COM15)；不指定时自动选择 CH340')

    # RTS 复位参数
    parser.add_argument('--rts-hold-ms', type=int, default=RTS_HOLD_MS_DEFAULT,
                        metavar='MS',
                        help=f'RTS 拉低保持时间 (默认: {RTS_HOLD_MS_DEFAULT}, 范围: 10-5000)')
    parser.add_argument('--rts-active-high', action='store_true',
                        help='目标板 RTS 高电平有效复位（默认低有效，已验证）')
    parser.add_argument('--sync-timeout', type=int, default=SYNC_TIMEOUT_MS_DEFAULT,
                        metavar='MS',
                        help=f'RTS 释放后等待 SYNC 总超时 (默认: {SYNC_TIMEOUT_MS_DEFAULT})')

    # 下载选项
    parser.add_argument('--baud', type=int, default=ud.SERIAL_DEFAULT_BAUD,
                        choices=list(ud.BAUD_TABLE.keys()),
                        help=f'下载波特率 (默认: {ud.SERIAL_DEFAULT_BAUD})')
    parser.add_argument('--sync-only', action='store_true',
                        help='只验证 ROM SYNC，不擦除、不下载')
    parser.add_argument('--erase', action='store_true',
                        help='下载前擦除芯片')
    parser.add_argument('--erase-blocks', type=int,
                        default=ud.DEFAULT_ERASE_BLOCKS, metavar='N',
                        help=f'擦除块数 (默认: {ud.DEFAULT_ERASE_BLOCKS}, 每块 4KB)')
    parser.add_argument('--address', type=lambda value: int(value, 0),
                        default=ud.BLDR_FLASH_BASE, metavar='ADDR',
                        help='BIN 烧录地址（默认: 0x10000000；HEX 使用文件内地址）')
    parser.add_argument('--flash-size', type=lambda value: int(value, 0),
                        default=0x40000, metavar='BYTES',
                        help='Flash 容量，用于地址范围校验（默认: 0x40000）')
    parser.add_argument('--allow-boot-no-response', action='store_true',
                        help='兼容旧 Bootloader：BOOT 无响应时仍继续，但结果未确认')

    # 行为选项
    parser.add_argument('--timeout', type=int, default=5000, metavar='MS',
                        help='每步命令超时 ms (默认: 5000)')
    parser.add_argument('--retries', type=int, default=1, metavar='N',
                        help='打开串口的额外重试次数（默认: 1）')
    parser.add_argument('--verbose', '-V', action='store_true',
                        help='详细日志输出')
    parser.add_argument('--list', '-l', action='store_true',
                        help='列出可用串口并退出')

    args = parser.parse_args()

    if args.list:
        ports = ud.scan_ports()
        if not ports:
            print("未检测到可用串口")
            return 2
        print(f"检测到 {len(ports)} 个串口:")
        print(f"{'设备':<10} {'描述':<30} {'硬件ID'}")
        print("-" * 70)
        for p in ports:
            print(f"{p['device']:<10} {p['description']:<30} {p['hwid']}")
        return 0

    if args.sync_only and args.erase:
        parser.error("--sync-only 不允许使用 --erase")
    if not args.sync_only and not args.bin:
        parser.error("需要 --firmware 参数指定固件文件，或使用 --sync-only/--list")
    if args.rts_hold_ms < 10 or args.rts_hold_ms > 5000:
        parser.error("--rts-hold-ms 范围: 10-5000 ms")
    if args.sync_timeout < 1000:
        parser.error("--sync-timeout 至少 1000 ms")
    if args.retries < 0 or args.retries > 10:
        parser.error("--retries 范围: 0-10")
    if args.flash_size <= 0:
        parser.error("--flash-size 必须大于 0")
    if args.erase_blocks <= 0 or args.erase_blocks * 4096 > args.flash_size:
        parser.error("--erase-blocks 必须在 Flash 容量范围内")

    # 加载固件
    bin_data = b''
    flash_addr = args.address
    if not args.sync_only:
        try:
            if ud.is_hex_file(args.bin):
                print(f"检测到 Intel HEX 格式，自动解析: {args.bin}")
                bin_data, flash_addr = ud.parse_hex(args.bin, args.flash_size)
                if flash_addr < ud.BLDR_FLASH_BASE and \
                        flash_addr + len(bin_data) <= args.flash_size:
                    flash_addr += ud.BLDR_FLASH_BASE
                print(f"解析完成: 地址 0x{flash_addr:08X} - "
                      f"0x{flash_addr + len(bin_data):08X}")
            else:
                with open(args.bin, 'rb') as f:
                    bin_data = f.read()
                flash_addr = args.address
        except FileNotFoundError:
            print(f"错误: 固件文件不存在: {args.bin}")
            return 3
        except Exception as e:
            print(f"错误: 读取固件文件失败: {e}")
            return 3

        if not bin_data:
            print(f"错误: 固件文件为空: {args.bin}")
            return 3

        flash_end = flash_addr + len(bin_data)
        allowed_end = ud.BLDR_FLASH_BASE + args.flash_size
        if flash_addr < ud.BLDR_FLASH_BASE or flash_addr % 4 != 0 or flash_end > allowed_end:
            print(
                f"错误: 固件地址范围 0x{flash_addr:08X}-0x{flash_end:08X} "
                f"超出/不对齐，允许范围 0x{ud.BLDR_FLASH_BASE:08X}-0x{allowed_end:08X}"
            )
            return 3

        print(f"固件大小: {len(bin_data)} bytes ({len(bin_data) / 1024:.1f} KB)")

    # 目标串口（优先 CH340）
    port = select_rts_port(args.port)
    print(f"目标串口: {port}")

    bl = ud.UARTBootloader(port, baud=args.baud,
                           timeout_ms=args.timeout,
                           verbose=args.verbose)

    if not bl.connect(args.retries):
        print(f"[{port}] ====== 烧录失败 (串口打开失败) ======")
        return 4

    try:
        ok, fail_phase = run_rts_download(bl, bin_data, flash_addr, args)
    finally:
        bl.disconnect()

    if ok:
        result = "SYNC 探测成功" if args.sync_only else "烧录成功"
        print(f"[{port}] ====== {result} ======")
        return 0

    phase_text = {
        'rts': 'RTS 复位失败',
        'sync': 'SYNC 同步失败',
        'baud': '波特率切换失败',
        'erase': '擦除失败',
        'download': '下载失败',
        'boot': 'BOOT 失败',
    }.get(fail_phase, fail_phase)
    print(f"[{port}] ====== 烧录失败 ({phase_text}) ======")
    return 4


if __name__ == '__main__':
    sys.exit(main())
