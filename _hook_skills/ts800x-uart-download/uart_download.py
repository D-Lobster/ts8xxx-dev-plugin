#!/usr/bin/env python3
"""
TS800X UART Bootloader Download Tool

通过串口使用 TS800X 芯片内 bootloader 协议下载固件。
与 ts800x-flash (JLink) 互补：JLink 需要调试器，UART 只需要串口线。

用法:
  python uart_download.py --list
  python uart_download.py --firmware firmware.hex --port COM3
  python uart_download.py --firmware firmware.hex --port COM3 --reset
  python uart_download.py --firmware firmware.hex --ports COM3,COM4 --reset --erase
"""

import argparse
import struct
import sys
import time
import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要安装 pyserial: pip install pyserial")
    sys.exit(99)

# ============================================================
# 常量定义
# ============================================================

# 协议常量
SERIAL_CMD_PATTERN  = 0xA1B2C3D4
SERIAL_CMD_DTYPE_REQ = 0xEE      # 请求帧 dtype
SERIAL_CMD_DTYPE_RSP = 0xEF      # 响应帧 dtype
SERIAL_HDR_SIZE      = 12
SERIAL_DEFAULT_BAUD  = 115200

# 命令类型 (flag 字段)
BLDR_SYNC     = 0
BLDR_DOWNLOAD = 1
BLDR_ERASE    = 3
BLDR_BOOT     = 4
BLDR_READ     = 5
BLDR_WRITE    = 6

# 下载标志
BLDR_COMMAND_MASK     = 0x3F
BLDR_COMMAND_EXT_MASK = 0xC0
BLDR_DOWNLOAD_FIRST   = 0x40
BLDR_DOWNLOAD_LAST    = 0x80
BLDR_READ_BATCH       = 0x40

# 响应状态
BLDR_COMMAND_SUCCESS      = 0
BLDR_COMMAND_BAD_CHECKSUM = 4

# App Target
FLASH_APP = 1
RAM_APP   = 0
OTP_APP   = 2

# 地址
BLDR_FLASH_BASE      = 0x10000000
BLDR_UART_BAUD_BASE  = 0x41001111
BLDR_BLE_MAC_BASE    = 0x10001C00

# 下载参数
MAX_DOWNLOAD_SIZE    = 1024
MAX_SYNC_INTERVAL_MS = 30
SERIAL_READ_TIMEOUT_S = 0.005
SYNC_RECV_BUFFER_MAX = 4096

# 波特率映射 (值 -> 分频器)
# XTAL(0x01000000) + divider
BAUD_TABLE = {
    115200:  0x0D,
    128000:  0x0C000B,
    230400:  0x080006,
    256000:  0x0D0005,
    512000:  0x0F0002,
    1000000: 0x080001,
}

# 唤醒/复位协议
WAKEUP_SOF = 0x55
WAKEUP_EOF = 0xAA
WAKEUP_VER = 0x01
WAKEUP_CMD_A0       = 0xA0   # 唤醒命令
WAKEUP_CMD_A1       = 0xA1   # 复位命令
WAKEUP_FLAG_NO_ACK  = 0x00
WAKEUP_FLAG_ACK_REQ = 0x01

# Magic Key: 防止串口噪声误触发软件复位
# 开发阶段 MCU 固件必须包含此校验，交付时删除
# 4 字节字面值 "TS80" (0x54, 0x53, 0x38, 0x30)
# MCU 端 (ARM LE): *(uint32_t*)payload == 0x30385354
MAGIC_KEY_BYTES = b'TS80'

# 时序常量 (ms)
WAKEUP_ACK_TIMEOUT_MS     = 1000
A0_ACK_RETRY_MAX          = 1
PRE_WAKEUP_DELAY_MS       = 8
BREAK_WAKE_HOLD_MS        = 100
RESET_SYNC_RETRY_DELAY_MS = 300
RESET_SYNC_MAX_RETRY      = 5
RESET_SYNC_DELAY_DEFAULT  = 100

# 擦除默认值
DEFAULT_ERASE_BLOCKS = 64   # TS8001: 64块 × 4096 = 256KB


# ============================================================
# 协议工具函数
# ============================================================

def crc8_dallas(data: bytes) -> int:
    """CRC-8-Dallas: 多项式 0x07, 初值 0x00"""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def parse_hex(hex_path: str, max_span: int = 0x40000) -> tuple[bytes, int]:
    """解析 Intel HEX (.hex) 文件，提取连续二进制数据。

    支持 32 位线性地址拓展 (Record Type 0x04)，
    自动合并地址连续的段，返回从最低地址开始的连续 .bin 数据。
    """
    segments = []  # [(addr, data), ...]
    base_addr = 0
    line_no = 0

    saw_eof = False
    with open(hex_path, 'r', encoding='ascii') as f:
        for line in f:
            line_no += 1
            line = line.strip()
            if not line:
                continue
            if line[0] != ':':
                raise ValueError(f"{hex_path}:{line_no}: Intel HEX 记录缺少 ':'")

            try:
                record = bytes.fromhex(line[1:])
            except ValueError as exc:
                raise ValueError(f"{hex_path}:{line_no}: 非法十六进制记录") from exc
            if len(record) < 5 or len(record) != record[0] + 5:
                raise ValueError(f"{hex_path}:{line_no}: 记录长度错误")
            if sum(record) & 0xFF:
                raise ValueError(f"{hex_path}:{line_no}: checksum 错误")

            byte_count = record[0]
            address = struct.unpack('>H', record[1:3])[0]
            record_type = record[3]
            data = record[4:4 + byte_count]

            if record_type == 0x04:  # Extended Linear Address
                if byte_count != 2:
                    raise ValueError(f"{hex_path}:{line_no}: 线性地址记录长度错误")
                base_addr = struct.unpack('>H', data)[0] << 16
            elif record_type == 0x02:  # Extended Segment Address
                if byte_count != 2:
                    raise ValueError(f"{hex_path}:{line_no}: 段地址记录长度错误")
                base_addr = struct.unpack('>H', data)[0] << 4
            elif record_type == 0x00:  # Data Record
                addr = base_addr + address
                segments.append((addr, data))
            elif record_type == 0x01:  # EOF
                saw_eof = True
                break
            elif record_type not in (0x03, 0x05):
                raise ValueError(f"{hex_path}:{line_no}: 不支持的记录类型 0x{record_type:02X}")

    if not segments:
        raise ValueError(f"{hex_path}: 无有效数据记录")
    if not saw_eof:
        raise ValueError(f"{hex_path}: 缺少 EOF 记录")

    # 排序，找起止地址
    segments.sort(key=lambda x: x[0])
    start_addr = segments[0][0]
    end_addr = max(seg[0] + len(seg[1]) for seg in segments)
    if end_addr - start_addr > max_span:
        raise ValueError(
            f"{hex_path}: HEX 地址跨度 {end_addr - start_addr} 超过限制 {max_span}"
        )

    # 合并成连续块
    result = bytearray(b'\xFF' * (end_addr - start_addr))
    occupied = bytearray(end_addr - start_addr)
    for addr, data in segments:
        offset = addr - start_addr
        if any(occupied[offset:offset + len(data)]):
            raise ValueError(f"{hex_path}: 数据记录地址重叠 0x{addr:08X}")
        result[offset:offset + len(data)] = data
        occupied[offset:offset + len(data)] = b'\x01' * len(data)

    return bytes(result), start_addr


def is_hex_file(path: str) -> bool:
    """判断文件是否为 .hex 格式（扩展名校验 + 内容首字符校验）"""
    if not path.lower().endswith('.hex'):
        return False
    try:
        with open(path, 'r') as f:
            first_char = f.read(1)
            return first_char == ':'
    except Exception:
        return False


def checksum32(data: bytes) -> int:
    """uint32 累加校验和 (低 32 位)"""
    return sum(data) & 0xFFFFFFFF


def checksum16(data: bytes) -> int:
    """uint16 累加校验和 (低 16 位)"""
    return sum(data) & 0xFFFF


def get_command_var(cmd_type: int, target: int = FLASH_APP) -> int:
    """计算命令帧 var 字段，与参考下载工具保持一致。"""
    var = 0
    base = cmd_type & BLDR_COMMAND_MASK
    if base == BLDR_DOWNLOAD:
        var |= target << 8
        if (cmd_type & BLDR_COMMAND_EXT_MASK) & BLDR_DOWNLOAD_FIRST:
            var |= 1 << 10
    elif base == BLDR_READ:
        if (cmd_type & BLDR_COMMAND_EXT_MASK) & BLDR_READ_BATCH:
            var = (1 << 4)
    return var


def build_command(flag: int, payload: bytes = b'', var: int = 0) -> bytes:
    """构建标准命令帧：12B header + 4B csum + payload"""
    pkt_len = 4 + len(payload) if payload else 0

    # 构建 header 前 10 字节（不含 var1）
    header = struct.pack('<IBBH', SERIAL_CMD_PATTERN, SERIAL_CMD_DTYPE_REQ, flag, var)
    header += struct.pack('<H', pkt_len)
    # header 目前 10 字节

    # var1 = 前 10 字节累加校验和的低 16 位
    var1 = checksum16(header)
    header += struct.pack('<H', var1)
    # header 共 12 字节

    # payload 校验和 (4B) + payload
    if payload:
        psum = checksum32(payload)
        return header + struct.pack('<I', psum) + payload
    return header


def build_wakeup_frame(cmd: int, flags: int, msg_id: int,
                       payload: bytes = b'') -> bytes:
    """构建唤醒/复位帧 (A0/A1)

    Frame: SOF(1) + body(7B) + payload + CRC8(1) + EOF(1)
    body = VER(1) + MSG_ID(2 LE) + CMD(1) + FLAGS(1) + LEN(2 LE)
    """
    body = struct.pack('<BHBB', WAKEUP_VER, msg_id, cmd, flags)
    body += struct.pack('<H', len(payload))
    body += payload
    frame = bytes([WAKEUP_SOF]) + body
    frame += bytes([crc8_dallas(body)])  # CRC8 覆盖 body + payload
    frame += bytes([WAKEUP_EOF])
    return frame


def build_download_packets(bin_data: bytes, flash_addr: int = BLDR_FLASH_BASE
                           ) -> list:
    """将固件拆分为下载命令包列表。

    首包: type = BLDR_DOWNLOAD | BLDR_DOWNLOAD_FIRST, payload = addr(4B) + data
    后续包: type = BLDR_DOWNLOAD, payload = data
    每包固件数据最大 1024 字节；首包地址不计入该上限。
    """
    if not bin_data:
        raise ValueError("固件数据不能为空")
    if flash_addr < BLDR_FLASH_BASE or flash_addr % 4:
        raise ValueError("Flash 地址必须位于应用区且按 4 字节对齐")

    packets = []
    remaining = len(bin_data)
    offset = 0
    is_first = True

    while remaining > 0:
        chunk_size = min(remaining, MAX_DOWNLOAD_SIZE)
        cmd_type = BLDR_DOWNLOAD

        if is_first:
            cmd_type |= BLDR_DOWNLOAD_FIRST
            var = get_command_var(cmd_type, FLASH_APP)
            payload = struct.pack('<I', flash_addr) + bin_data[offset:offset + chunk_size]
            is_first = False
        else:
            var = get_command_var(cmd_type, FLASH_APP)
            payload = bin_data[offset:offset + chunk_size]

        flag = cmd_type & BLDR_COMMAND_MASK
        cmd = build_command(flag, payload, var)
        packets.append(cmd)

        remaining -= chunk_size
        offset += chunk_size

    return packets


def parse_response(data: bytes) -> tuple:
    """解析标准响应帧。返回 (flag, payload) 或 (None, None)"""
    if len(data) < SERIAL_HDR_SIZE:
        return None, None

    # 扫描 pattern
    for i in range(len(data) - SERIAL_HDR_SIZE + 1):
        pattern = struct.unpack_from('<I', data, i)[0]
        if pattern != SERIAL_CMD_PATTERN:
            continue

        if i + SERIAL_HDR_SIZE > len(data):
            return None, None

        dtype = data[i + 4]
        if dtype != SERIAL_CMD_DTYPE_RSP:
            continue

        flag = data[i + 5]
        pkt_len = struct.unpack_from('<H', data, i + 8)[0]
        total_len = SERIAL_HDR_SIZE + pkt_len

        if len(data) - i < total_len:
            continue

        header = data[i:i + SERIAL_HDR_SIZE]
        expected_header_sum = struct.unpack_from('<H', header, 10)[0]
        if checksum16(header[:10]) != expected_header_sum:
            continue

        # SYNC 等无 payload 响应只有 12 字节 header，len 字段为 0。
        if pkt_len == 0:
            return flag, b''
        if pkt_len < 4:
            continue

        expected_payload_sum = struct.unpack_from('<I', data, i + SERIAL_HDR_SIZE)[0]
        payload_start = i + SERIAL_HDR_SIZE + 4
        payload = data[payload_start:i + total_len]
        if checksum32(payload) != expected_payload_sum:
            continue
        return flag, bytes(payload)

    return None, None


def parse_wakeup_ack(data: bytes) -> tuple:
    """解析唤醒 ACK 帧。返回 (cmd, msg_id) 或 (None, None)"""
    if len(data) < 10:  # 最小帧: SOF(1)+body(7)+CRC8(1)+EOF(1) = 10
        return None, None

    for i in range(len(data)):
        if data[i] != WAKEUP_SOF:
            continue

        if len(data) - i < 10:
            return None, None

        # body: 7 字节
        body = data[i + 1:i + 8]
        ver = body[0]
        msg_id = struct.unpack_from('<H', body, 1)[0]
        cmd = body[3]
        flags = body[4]
        payload_len = struct.unpack_from('<H', body, 5)[0]

        # 总帧长 = SOF(1) + body(7) + payload + CRC8(1) + EOF(1)
        frame_len = 1 + 7 + payload_len + 1 + 1
        if len(data) - i < frame_len:
            return None, None

        # 读取 payload
        payload = data[i + 8:i + 8 + payload_len]

        # 验证 CRC8 (覆盖 body + payload)
        body_plus_payload = body + payload
        expected_crc = crc8_dallas(body_plus_payload)
        actual_crc = data[i + 8 + payload_len]

        if actual_crc != expected_crc:
            continue

        # 验证 EOF
        if data[i + 8 + payload_len + 1] != WAKEUP_EOF:
            continue

        return cmd, msg_id

    return None, None


# ============================================================
# UARTBootloader 类
# ============================================================

class UARTBootloader:
    """TS800X UART Bootloader 协议实现"""

    def __init__(self, port: str, baud: int = SERIAL_DEFAULT_BAUD,
                 timeout_ms: int = 5000, verbose: bool = False):
        self.port_name = port
        self.target_baud = baud
        self.timeout_ms = timeout_ms
        self.verbose = verbose
        self.serial: serial.Serial | None = None
        self._recv_buf = bytearray()

    # ---- 连接管理 ----

    def connect(self, retries: int = 0) -> bool:
        """打开串口"""
        for attempt in range(retries + 1):
            try:
                self.serial = serial.Serial(
                    port=self.port_name,
                    baudrate=SERIAL_DEFAULT_BAUD,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=SERIAL_READ_TIMEOUT_S,
                    write_timeout=0.5,
                )
                self._log(f"串口 {self.port_name} 已打开 (115200 8N1)")
                return True
            except serial.SerialException as exc:
                self._log(f"ERROR: 打开串口失败 ({attempt + 1}/{retries + 1}): {exc}")
                if attempt < retries:
                    time.sleep(0.2)
        return False

    def disconnect(self):
        """关闭串口"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self._log(f"串口 {self.port_name} 已关闭")

    def _set_baud(self, baud: int):
        """本地切换波特率"""
        if self.serial and self.serial.is_open:
            self.serial.baudrate = baud
            self._log(f"本地波特率切换为 {baud}")

    # ---- 基础收发 ----

    def _log(self, msg: str):
        """输出日志"""
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [{self.port_name}] {msg}")

    def _vlog(self, msg: str):
        """详细日志（仅 verbose 模式）"""
        if self.verbose:
            self._log(msg)

    def flush_input(self):
        """清空输入缓冲区"""
        if self.serial and self.serial.is_open:
            self.serial.reset_input_buffer()

    def send_raw(self, data: bytes):
        """发送原始字节（用于 A0/A1/预字节等）"""
        if not self.serial or not self.serial.is_open:
            self._log("ERROR: 串口未打开，无法发送")
            return
        self._vlog(f"RAW TX: {data.hex().upper()} ({len(data)} bytes)")
        self.serial.write(data)
        self.serial.flush()

    def send_break(self, hold_ms: int = BREAK_WAKE_HOLD_MS):
        """发送 BREAK 低电平脉冲（用于深睡唤醒）"""
        if not self.serial or not self.serial.is_open:
            self._log("ERROR: 串口未打开，无法发送 BREAK")
            return

        actual_ms = hold_ms if hold_ms > 0 else 5
        self._vlog(f"BREAK 开始 (hold={actual_ms}ms)")
        try:
            self.serial.send_break(duration=(actual_ms / 1000.0))
        except (TypeError, ValueError):
            # 部分 pyserial 版本 send_break 不接受 duration 参数
            self.serial.send_break()
            time.sleep(actual_ms / 1000.0)
        self._vlog(f"BREAK 结束")

    def send_command(self, cmd: bytes, timeout_ms: int | None = None
                     ) -> bytes | None:
        """发送命令并等待响应。

        返回完整响应帧，超时返回 None。
        """
        if timeout_ms is None:
            timeout_ms = self.timeout_ms
        if not self.serial or not self.serial.is_open:
            self._log("ERROR: 串口未打开")
            return None

        self.flush_input()
        self.serial.write(cmd)
        self.serial.flush()

        # 计算传输时间（参考 C++ timeout 计算逻辑）
        transfer_time = 0
        flag = cmd[5] if len(cmd) > 5 else 0
        if flag == BLDR_READ and len(cmd) > 6 and cmd[6] == 0x10:
            # Read blocks: +200ms
            transfer_time = 200
        elif flag == BLDR_DOWNLOAD:
            transfer_time = 1000
        elif flag == BLDR_ERASE:
            transfer_time = 1000

        baud = self.serial.baudrate if self.serial.baudrate else SERIAL_DEFAULT_BAUD
        if baud <= 9600:
            transfer_time += len(cmd)
        else:
            transfer_time += int(len(cmd) / (baud / 8 / 1000))

        total_timeout = (timeout_ms + transfer_time) / 1000.0
        deadline = time.monotonic() + total_timeout

        recv_buf = bytearray()
        while time.monotonic() < deadline:
            try:
                chunk = self.serial.read(256)
                if chunk:
                    recv_buf.extend(chunk)
                    flag, payload = parse_response(bytes(recv_buf))
                    if flag is not None:
                        return bytes(recv_buf)
                    # 检查是否有 LOAD BOOT 等特殊响应
                    if b'LOAD' in recv_buf or b'BOOT' in recv_buf:
                        return bytes(recv_buf)
            except serial.SerialException:
                break
            time.sleep(0.005)

        return None

    def wait_for_wakeup_ack(self, timeout_ms: int = WAKEUP_ACK_TIMEOUT_MS
                            ) -> tuple:
        """等待 A0 ACK 帧。返回 (cmd, msg_id) 或 (None, None)"""
        deadline = time.monotonic() + timeout_ms / 1000.0
        recv_buf = bytearray()

        while time.monotonic() < deadline:
            try:
                chunk = self.serial.read(64)
                if chunk:
                    recv_buf.extend(chunk)
                    cmd, msg_id = parse_wakeup_ack(bytes(recv_buf))
                    if cmd is not None:
                        return cmd, msg_id
            except serial.SerialException:
                break
            time.sleep(0.005)

        return None, None

    # ---- 协议步骤 ----

    def step_sync(self) -> bool:
        """Step 1: SYNC — 与 bootloader 建立连接"""
        self._log("SYNC: 发送同步命令...")
        self.flush_input()

        sync_cmd = build_command(BLDR_SYNC)
        deadline = time.monotonic() + self.timeout_ms / 1000.0

        recv_buf = bytearray()
        while time.monotonic() < deadline:
            try:
                self.serial.write(sync_cmd)
                self.serial.flush()
            except serial.SerialException as exc:
                self._log(f"SYNC: 串口写入失败: {exc}")
                return False

            # 短轮询（30ms 内等响应）
            poll_deadline = time.monotonic() + MAX_SYNC_INTERVAL_MS / 1000.0
            while time.monotonic() < poll_deadline:
                try:
                    chunk = self.serial.read(64)
                    if chunk:
                        self._vlog(f"SYNC RX: {chunk.hex().upper()}")
                        recv_buf.extend(chunk)
                        flag, _ = parse_response(bytes(recv_buf))
                        if flag is not None:
                            if flag == BLDR_COMMAND_SUCCESS:
                                self._log("SYNC: OK")
                                return True
                            else:
                                self._log(f"SYNC: 收到错误响应 flag={flag:#04x}")
                                recv_buf.clear()
                except serial.SerialException as exc:
                    self._log(f"SYNC: 串口读取失败: {exc}")
                    return False
                time.sleep(0.002)

            if len(recv_buf) > SYNC_RECV_BUFFER_MAX:
                del recv_buf[:-(SERIAL_HDR_SIZE + 4)]

        self._log("SYNC: 超时")
        return False

    def step_wait_sync(self, total_timeout_ms: int = 30000) -> bool:
        """连续 SYNC 重试循环（--wait-reset 模式专用）。

        以 30ms 间隔反复发送 SYNC，等待用户按 RESET 使芯片进入 bootloader。
        每 5 秒输出一次进度。返回 True 表示 SYNC 成功。
        """
        if not self.serial or not self.serial.is_open:
            self._log("ERROR: 串口未打开，无法执行 SYNC")
            return False

        self._log("SYNC: 等待芯片进入 bootloader (请按 RESET 按键)...")
        self.flush_input()

        sync_cmd = build_command(BLDR_SYNC)
        deadline = time.monotonic() + total_timeout_ms / 1000.0
        last_progress = 0

        recv_buf = bytearray()
        while time.monotonic() < deadline:
            try:
                self.serial.write(sync_cmd)
                self.serial.flush()
            except serial.SerialException as exc:
                self._log(f"SYNC: 串口写入失败: {exc}")
                return False

            # 短轮询等待响应 (30ms)
            poll_deadline = time.monotonic() + MAX_SYNC_INTERVAL_MS / 1000.0
            while time.monotonic() < poll_deadline:
                try:
                    chunk = self.serial.read(64)
                    if chunk:
                        self._vlog(f"SYNC RX: {chunk.hex().upper()}")
                        recv_buf.extend(chunk)
                        flag, _ = parse_response(bytes(recv_buf))
                        if flag is not None:
                            if flag == BLDR_COMMAND_SUCCESS:
                                self._log("SYNC: OK - 检测到 bootloader")
                                return True
                            else:
                                self._log(f"SYNC: 收到错误响应 flag={flag:#04x}")
                                recv_buf.clear()
                except serial.SerialException as exc:
                    self._log(f"SYNC: 串口读取失败: {exc}")
                    return False
                time.sleep(0.002)

            if len(recv_buf) > SYNC_RECV_BUFFER_MAX:
                del recv_buf[:-(SERIAL_HDR_SIZE + 4)]

            # 进度报告(每 5 秒)
            elapsed_s = total_timeout_ms / 1000.0 - (deadline - time.monotonic())
            progress = int(elapsed_s) // 5
            if progress > last_progress:
                last_progress = progress
                remaining = int(deadline - time.monotonic())
                self._log(f"SYNC: 等待中... (剩余 {remaining}s) 请按 RESET 按键")

        self._log("SYNC: 超时 - 未检测到 bootloader, 请检查接线和 RESET 按键")
        return False

    def step_change_baud(self, new_baud: int) -> bool:
        """Step 2: 切换波特率"""
        if new_baud not in BAUD_TABLE:
            self._log(f"BAUD: 不支持的波特率 {new_baud}")
            return False

        self._log(f"BAUD: 切换波特率 {SERIAL_DEFAULT_BAUD} -> {new_baud}")

        divs = 0x01000000 + BAUD_TABLE[new_baud]  # XTAL clock source
        payload = struct.pack('<II', BLDR_UART_BAUD_BASE, divs)
        payload += b'\x00\x00'  # 补齐 10 字节

        cmd = build_command(BLDR_WRITE, payload, var=0)
        rsp = self.send_command(cmd)

        if rsp is None:
            self._log("BAUD: 无响应")
            return False

        flag, _ = parse_response(rsp)
        if flag == BLDR_COMMAND_SUCCESS:
            self._set_baud(new_baud)
            self._log(f"BAUD: 切换成功 ({new_baud})")
            return True

        self._log(f"BAUD: 失败 flag={flag}")
        return False

    def step_erase(self, blocks: int = DEFAULT_ERASE_BLOCKS) -> bool:
        """Step 3: 擦除 Flash"""
        self._log(f"ERASE: 擦除 {blocks} 块 ({blocks * 4}KB)...")

        payload = struct.pack('<II', BLDR_FLASH_BASE, blocks)
        cmd = build_command(BLDR_ERASE, payload, var=0)
        rsp = self.send_command(cmd)

        if rsp is None:
            self._log("ERASE: 无响应")
            return False

        flag, _ = parse_response(rsp)
        if flag == BLDR_COMMAND_SUCCESS:
            self._log("ERASE: 完成")
            return True

        self._log(f"ERASE: 失败 flag={flag}")
        return False

    def step_download(self, packets: list) -> tuple:
        """Step 4: 下载固件。返回 (success, failed_index)"""
        total = len(packets)
        self._log(f"DOWNLOAD: 开始 ({total} 包, {total * MAX_DOWNLOAD_SIZE // 1024}KB)")

        for idx, packet in enumerate(packets):
            rsp = self.send_command(packet)
            if rsp is None:
                self._log(f"DOWNLOAD: 包 {idx + 1}/{total} 无响应")
                return False, idx

            flag, _ = parse_response(rsp)
            if flag != BLDR_COMMAND_SUCCESS:
                self._log(f"DOWNLOAD: 包 {idx + 1}/{total} 失败 flag={flag}")
                return False, idx

            # 每 10 包或最后一包输出进度
            if self.verbose or (idx + 1) % 10 == 0 or (idx + 1) == total:
                pct = (idx + 1) * 100 // total
                self._log(f"DOWNLOAD: {idx + 1}/{total} ({pct}%)")

        self._log("DOWNLOAD: 完成")
        return True, -1

    def step_boot(self, flash_addr: int, allow_no_response: bool = False) -> bool:
        """Step 5: BOOT — 启动固件"""
        self._log(f"BOOT: 跳转到 0x{flash_addr:08X}...")

        payload = struct.pack('<I', flash_addr)
        cmd = build_command(BLDR_BOOT, payload, var=0)
        rsp = self.send_command(cmd)

        if rsp is None:
            if allow_no_response:
                self._log("BOOT: 无响应，按显式兼容选项接受（结果未确认）")
                return True
            self._log("BOOT: 无响应，无法确认跳转结果")
            return False

        flag, _ = parse_response(rsp)
        if flag == BLDR_COMMAND_SUCCESS:
            self._log("BOOT: OK")
            return True

        self._log(f"BOOT: 失败 flag={flag}")
        return False

    # ---- 编排方法 ----

    def download(self, bin_data: bytes, *,
                 flash_addr: int = BLDR_FLASH_BASE,
                 target_baud: int | None = None,
                 do_erase: bool = False,
                 erase_blocks: int = DEFAULT_ERASE_BLOCKS,
                 allow_boot_no_response: bool = False,
                 ) -> bool:
        """正常下载流程：SYNC → [BAUD] → [ERASE] → DOWNLOAD → BOOT"""
        # 1. SYNC
        if not self.step_sync():
            return False

        # 2. BAUD (可选)
        if target_baud and target_baud != SERIAL_DEFAULT_BAUD:
            if not self.step_change_baud(target_baud):
                return False

        # 3. ERASE (可选)
        if do_erase:
            if not self.step_erase(erase_blocks):
                return False

        # 4. DOWNLOAD
        packets = build_download_packets(bin_data, flash_addr)
        ok, _ = self.step_download(packets)
        if not ok:
            return False

        # 5. BOOT
        return self.step_boot(flash_addr, allow_boot_no_response)

    def _do_reset_sync(self, *,
                       reset_delay_ms: int = RESET_SYNC_DELAY_DEFAULT,
                       break_wake: bool = False) -> bool:
        """Phase 1: A0→A1→SYNC（带重试）。

        返回 True 表示 SYNC 成功(芯片已进入 bootloader)。
        返回 False 表示软复位无法进入 bootloader（可降级手动复位）。

        关键设计：一旦 A0 拿到 ACK（芯片 APP 确认响应），说明复位路径有效。
        后续重试不再发 A0/A1（芯片已在 bootloader），而是直接尝试 SYNC
        直到超时，避免错误降级到手动弹窗。
        """
        a0_ever_acked = False  # 标记：本轮是否曾收到过 A0 ACK

        for retry in range(RESET_SYNC_MAX_RETRY + 1):
            if retry > 0:
                self._log(f"复位重试 {retry}/{RESET_SYNC_MAX_RETRY}...")
                time.sleep(RESET_SYNC_RETRY_DELAY_MS / 1000.0)

            # ─── 如果之前 A0 已拿到 ACK，芯片应当已在 bootloader ───
            # 跳过 A0/A1，直接重试 SYNC
            if a0_ever_acked:
                self._log("A0 已确认，芯片应在 bootloader，直接重试 SYNC...")
                self._set_baud(SERIAL_DEFAULT_BAUD)
                if self.step_sync():
                    self._log("复位同步成功：芯片已进入 bootloader")
                    return True
                continue

            # 0a. BREAK 唤醒 (可选，仅深睡设备需要)
            if break_wake:
                self._log("发送 BREAK 低电平唤醒...")
                self.send_break(BREAK_WAKE_HOLD_MS)
                time.sleep(0.002)
                self._log("发送预唤醒字节...")
                self.send_raw(b'\x00')
                time.sleep(PRE_WAKEUP_DELAY_MS / 1000.0)

            # 0b. A0 + Magic Key（带 ACK）
            self._log("发送唤醒指令 (A0 + Magic Key)...")
            magic_payload = MAGIC_KEY_BYTES
            a0_frame = build_wakeup_frame(WAKEUP_CMD_A0, WAKEUP_FLAG_ACK_REQ,
                                          1, magic_payload)
            self.flush_input()
            self.send_raw(a0_frame)

            cmd, msg_id = self.wait_for_wakeup_ack(WAKEUP_ACK_TIMEOUT_MS)
            a0_got_ack = (cmd == WAKEUP_CMD_A0)

            if a0_got_ack:
                self._log(f"A0 ACK 收到 (msg={msg_id})")
                a0_ever_acked = True
            else:
                # 重试 A0 (最多 A0_ACK_RETRY_MAX 次)
                for a0_retry in range(A0_ACK_RETRY_MAX):
                    self._log(f"A0 超时，重试 ({a0_retry + 1}/{A0_ACK_RETRY_MAX})...")
                    self.send_raw(a0_frame)
                    cmd, msg_id = self.wait_for_wakeup_ack(WAKEUP_ACK_TIMEOUT_MS)
                    if cmd == WAKEUP_CMD_A0:
                        self._log(f"A0 ACK 收到 (msg={msg_id})")
                        a0_got_ack = True
                        a0_ever_acked = True
                        break

                if not a0_got_ack:
                    # 首次 A0 就无反馈 → 芯片没有 soft reset 固件 → 快速降级
                    self._log("A0 无回执，芯片不支持软复位，切换到手动复位模式")
                    return False

            # 0c. A1 + Magic Key（无 ACK，触发复位）
            time.sleep(0.005)
            self._log("发送复位指令 (A1 + Magic Key)...")
            a1_frame = build_wakeup_frame(WAKEUP_CMD_A1, WAKEUP_FLAG_NO_ACK,
                                          2, magic_payload)
            self.send_raw(a1_frame)

            # 0d. 等待 MCU 复位完成
            self._log(f"等待 {reset_delay_ms}ms (MCU 复位)...")
            time.sleep(reset_delay_ms / 1000.0)

            self._set_baud(SERIAL_DEFAULT_BAUD)  # 回到默认波特率

            if self.step_sync():
                self._log("复位同步成功：芯片已进入 bootloader")
                return True

            self._log(f"SYNC 超时 (重试 {retry}/{RESET_SYNC_MAX_RETRY})")

        self._log("复位下载失败：A0/A1/SYNC 已达最大重试次数")
        return False

    def reset_download(self, bin_data: bytes, *,
                       flash_addr: int = BLDR_FLASH_BASE,
                       target_baud: int | None = None,
                       do_erase: bool = False,
                       erase_blocks: int = DEFAULT_ERASE_BLOCKS,
                       reset_delay_ms: int = RESET_SYNC_DELAY_DEFAULT,
                       break_wake: bool = False,
                       allow_boot_no_response: bool = False,
                       ) -> tuple:
        """复位下载流程：A0→A1→[延时]→SYNC→[BAUD]→[ERASE]→DOWNLOAD→BOOT

        返回 (success, fail_phase) 元组:
          (True, '')  → 全部成功
          (False, 'sync')  → SYNC 失败（可降级手动复位）
          (False, 'step')  → 后继步骤失败（不应降级）
        """
        # Phase 1: A0/A1/SYNC（带重试）
        if not self._do_reset_sync(reset_delay_ms=reset_delay_ms,
                                    break_wake=break_wake):
            return False, 'sync'

        # Phase 2: BAUD→ERASE→DOWNLOAD→BOOT（无重试）
        packets = build_download_packets(bin_data, flash_addr)

        if target_baud and target_baud != SERIAL_DEFAULT_BAUD:
            if not self.step_change_baud(target_baud):
                return False, 'step'

        if do_erase:
            if not self.step_erase(erase_blocks):
                return False, 'step'

        ok, _ = self.step_download(packets)
        if not ok:
            return False, 'step'

        if not self.step_boot(flash_addr, allow_boot_no_response):
            return False, 'step'
        return True, ''


# ============================================================
# CLI 工具函数
# ============================================================

def show_reset_popup(port_name: str, timeout_s: int = 30, sync_ok: list = None) -> None:
    """非阻塞弹窗提示用户按 RESET 按键。

    后台持续 SYNC，检测到 bootloader 后自动关闭弹窗。
    不可用时降级为控制台提示。
    """
    message = (
        f"请在 [{port_name}] 开发板上按一下 RESET 按键\n"
        f"检测到 bootloader 后弹窗将自动消失\n\n"
        f"同步超时: {timeout_s} 秒"
    )
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title("等待复位 - TS800X UART Download")
        root.attributes('-topmost', True)
        root.geometry("380x160+500+300")

        label = tk.Label(root, text=message, font=("", 11), justify="left")
        label.pack(pady=10, padx=20)

        status = tk.Label(root, text="等待 RESET...", font=("", 10), fg="gray")
        status.pack()

        def check_sync():
            if sync_ok and sync_ok[0]:
                root.destroy()
                return
            elapsed = (time.monotonic() - start_time)
            if elapsed > timeout_s:
                status.config(text="超时，请重试", fg="red")
                root.after(1000, root.destroy)
                return
            status.config(text=f"等待 RESET... ({int(timeout_s - elapsed)}s)")
            root.after(200, check_sync)

        start_time = time.monotonic()
        root.after(200, check_sync)
        root.mainloop()
    except Exception:
        # 降级: 控制台提示
        print(f"\n{'=' * 60}")
        print(f"  ⚠️  请在 [{port_name}] 开发板上按一下 RESET 按键  ⚠️")
        print(f"      检测到 bootloader 后将自动继续...")
        print(f"      同步超时: {timeout_s} 秒")
        print(f"{'=' * 60}")
        # 控制台降级: 轮询等待 SYNC
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if sync_ok and sync_ok[0]:
                print(f"  ✓ 检测到 bootloader!")
                break
            time.sleep(0.3)
        else:
            print(f"  [TIMEOUT] 超时")


def _do_wait_reset_download(bl: UARTBootloader, bin_data: bytes,
                            flash_addr: int, port_name: str, args) -> bool:
    """手动复位下载: 先连串口 → 后台连续 SYNC → 弹窗 → 下载。

    关键设计: 串口在弹窗之前就已打开，SYNC 在后台线程中持续发送。
    用户看到弹窗后按 RESET，芯片立即进入 bootloader，正在运行的 SYNC 即刻捕获。
    解决了"弹窗→开串口→SYNC"之间 bootloader 窗口丢失的问题。

    自行管理 connect/disconnect 生命周期。
    """
    import threading

    # 使用 --timeout 参数，但至少给 10 秒让用户有时间按 RESET
    WAIT_SYNC_MS = max(args.timeout, 10000) if args.timeout else 30000

    if not bl.connect(args.retries):
        return False

    try:
        # 后台线程: 弹窗之前就开始连续发送 SYNC
        sync_ok = [False]

        def _sync_worker():
            sync_ok[0] = bl.step_wait_sync(total_timeout_ms=WAIT_SYNC_MS)

        if args.no_popup:
            print(f"  请在 [{port_name}] 开发板上按一下 RESET，等待 ROM SYNC...")

        t = threading.Thread(target=_sync_worker, daemon=True)
        t.start()

        # 确保 SYNC 线程已经开始发送（不等的话弹窗可能先于首次 SYNC 出现）
        time.sleep(0.15)

        if not args.no_popup:
            # 弹窗期间后台 SYNC 持续发送，检测成功后自动关闭。
            # 弹窗超时与 SYNC 超时保持一致，避免用户按了 RESET 但弹窗不消失
            popup_timeout_s = WAIT_SYNC_MS // 1000
            show_reset_popup(port_name, timeout_s=popup_timeout_s, sync_ok=sync_ok)

        # 等待 SYNC 线程结束（成功则立即返回，否则等自然超时）
        t.join(timeout=35)

        if not sync_ok[0]:
            print(f"  [TIMEOUT]  超时未检测到 RESET, 可重试")
            return False

        if args.sync_only:
            bl._log("SYNC-ONLY: 已确认 ROM bootloader 响应，未执行擦除或下载")
            return True

        # SYNC 成功 → 继续下载流程
        ok = True
        if args.baud != SERIAL_DEFAULT_BAUD:
            if not bl.step_change_baud(args.baud):
                ok = False
        # --wait-reset: 遵循 --erase 参数语义
        if ok and args.erase:
            if not bl.step_erase(args.erase_blocks):
                ok = False
        if ok:
            packets = build_download_packets(bin_data, flash_addr)
            ok, _ = bl.step_download(packets)
        if ok:
            ok = bl.step_boot(flash_addr, args.allow_boot_no_response)

        return ok
    finally:
        bl.disconnect()


def scan_ports() -> list:
    """扫描可用串口"""
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append({
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid,
        })
    return ports


def sort_ports(port_names: list) -> list:
    """按 COM 号从小到大排序"""
    def com_key(name: str) -> int:
        name_upper = name.strip().upper()
        if name_upper.startswith('COM'):
            try:
                return int(name_upper[3:])
            except ValueError:
                pass
        return 0x7FFFFFFF

    return sorted(port_names, key=com_key)


def select_port(port_arg: str | None) -> str:
    """选择目标串口：指定或自动选第一个可用"""
    available = scan_ports()
    if not available:
        print("错误: 未检测到可用串口")
        sys.exit(2)

    if port_arg:
        # 验证指定串口是否存在
        avail_names = [p['device'] for p in available]
        if port_arg not in avail_names:
            print(f"错误: 串口 {port_arg} 不存在")
            print(f"可用串口: {', '.join(avail_names)}")
            sys.exit(2)
        return port_arg

    # 自动选第一个
    return available[0]['device']


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='TS800X UART Bootloader 固件下载工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python uart_download.py --list
  python uart_download.py --firmware firmware.hex --port COM3
  python uart_download.py --firmware firmware.hex --port COM3 --reset
  python uart_download.py --port COM3 --wait-reset --sync-only -V
  python uart_download.py --port COM3 --wait-reset --sync-only --no-popup -V
  python uart_download.py --firmware firmware.hex --ports COM3,COM4 --reset --erase -V
        ''',
    )

    # 主要参数
    parser.add_argument('--firmware', '-f', metavar='PATH', dest='bin',
                        help='固件文件路径（支持 .bin / .hex）')
    parser.add_argument('--bin', metavar='PATH', dest='bin',
                        help='[已弃用] 请使用 --firmware，为兼容保留此别名')
    parser.add_argument('--port', metavar='PORT',
                        help='目标串口 (如 COM3)，不指定时自动选第一个可用')
    parser.add_argument('--ports', metavar='PORTS',
                        help='批量烧录: 逗号分隔的串口号 (如 COM3,COM4,COM5)')

    # 下载选项
    parser.add_argument('--baud', type=int, default=SERIAL_DEFAULT_BAUD,
                        choices=list(BAUD_TABLE.keys()),
                        help=f'下载波特率 (默认: {SERIAL_DEFAULT_BAUD})')
    parser.add_argument('--reset', action='store_true',
                        help='复位下载模式 (A0 唤醒 + A1 复位 + Magic Key 鉴权)')
    parser.add_argument('--wait-reset', action='store_true',
                        help='等待用户按 RESET 键进入 bootloader (30 秒超时)')
    parser.add_argument('--sync-only', action='store_true',
                        help='仅配合 --wait-reset 探测 ROM bootloader，不擦除或下载')
    parser.add_argument('--no-popup', action='store_true',
                        help='等待 RESET 时只输出控制台提示，不显示 tkinter 弹窗')
    parser.add_argument('--break-wake', action='store_true',
                        help='复位前发送 BREAK 低电平脉冲 (深睡设备唤醒)')
    parser.add_argument('--reset-delay', type=int,
                        default=RESET_SYNC_DELAY_DEFAULT,
                        metavar='MS',
                        help=f'A1→SYNC 延时 ms (默认: {RESET_SYNC_DELAY_DEFAULT}, 范围: 10-5000)')
    parser.add_argument('--erase', action='store_true',
                        help='下载前擦除芯片')
    parser.add_argument('--erase-blocks', type=int,
                        default=DEFAULT_ERASE_BLOCKS,
                        metavar='N',
                        help=f'擦除块数 (默认: {DEFAULT_ERASE_BLOCKS}, 每块 4KB)')
    parser.add_argument('--address', type=lambda value: int(value, 0),
                        default=BLDR_FLASH_BASE, metavar='ADDR',
                        help='BIN 烧录地址（默认: 0x10000000；HEX 使用文件内地址）')
    parser.add_argument('--flash-size', type=lambda value: int(value, 0),
                        default=0x40000, metavar='BYTES',
                        help='Flash 容量，用于地址范围校验（默认: 0x40000）')
    parser.add_argument('--allow-boot-no-response', action='store_true',
                        help='兼容旧 Bootloader：BOOT 无响应时仍继续，但结果未确认')

    # 行为选项
    parser.add_argument('--timeout', type=int, default=5000,
                        metavar='MS',
                        help='每步命令超时 ms (默认: 5000)')
    parser.add_argument('--retries', type=int, default=1,
                        metavar='N',
                        help='打开串口的额外重试次数（默认: 1；不会重复发送固件包）')
    parser.add_argument('--verbose', '-V', action='store_true',
                        help='详细日志输出')
    parser.add_argument('--list', '-l', action='store_true',
                        help='列出可用串口并退出')

    args = parser.parse_args()

    # --list 模式
    if args.list:
        ports = scan_ports()
        if not ports:
            print("未检测到可用串口")
            return 2
        else:
            print(f"检测到 {len(ports)} 个串口:")
            print(f"{'设备':<10} {'描述':<30} {'硬件ID'}")
            print("-" * 70)
            for p in ports:
                print(f"{p['device']:<10} {p['description']:<30} {p['hwid']}")
        return 0

    # 验证参数
    if args.port and args.ports:
        parser.error("--port 和 --ports 不能同时使用")

    if args.wait_reset and args.reset:
        parser.error("--wait-reset 和 --reset 不能同时使用")
    if args.sync_only and not args.wait_reset:
        parser.error("--sync-only 必须与 --wait-reset 一起使用")
    if args.no_popup and not args.wait_reset:
        parser.error("--no-popup 必须与 --wait-reset 一起使用")
    if args.sync_only and args.erase:
        parser.error("--sync-only 不允许使用 --erase")
    if not args.sync_only and not args.bin:
        parser.error("需要 --firmware 参数指定固件文件，或使用 --sync-only/--list")

    if args.reset_delay < 10 or args.reset_delay > 5000:
        parser.error("--reset-delay 范围: 10-5000 ms")
    if args.retries < 0 or args.retries > 10:
        parser.error("--retries 范围: 0-10")
    if args.flash_size <= 0:
        parser.error("--flash-size 必须大于 0")
    if args.erase_blocks <= 0 or args.erase_blocks * 4096 > args.flash_size:
        parser.error("--erase-blocks 必须在 Flash 容量范围内")

    bin_data = b''
    flash_addr = args.address
    if not args.sync_only:
        # 验证固件文件 — 支持 .bin 和 .hex 两种格式
        try:
            if is_hex_file(args.bin):
                print(f"检测到 Intel HEX 格式，自动解析: {args.bin}")
                bin_data, flash_addr = parse_hex(args.bin, args.flash_size)
                if flash_addr < BLDR_FLASH_BASE and flash_addr + len(bin_data) <= args.flash_size:
                    flash_addr += BLDR_FLASH_BASE
                print(f"解析完成: 地址 0x{flash_addr:08X} - 0x{flash_addr + len(bin_data):08X}")
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
        allowed_end = BLDR_FLASH_BASE + args.flash_size
        if flash_addr < BLDR_FLASH_BASE or flash_addr % 4 != 0 or flash_end > allowed_end:
            print(
                f"错误: 固件地址范围 0x{flash_addr:08X}-0x{flash_end:08X} "
                f"超出/不对齐，允许范围 0x{BLDR_FLASH_BASE:08X}-0x{allowed_end:08X}"
            )
            return 3

        print(f"固件大小: {len(bin_data)} bytes ({len(bin_data) / 1024:.1f} KB)")

    # 确定目标串口列表
    if args.ports:
        target_ports = sort_ports([p.strip() for p in args.ports.split(',')])
    else:
        target_ports = [select_port(args.port)]

    print(f"目标串口: {', '.join(target_ports)}")

    # 执行下载
    results = {}
    for port in target_ports:
        print(f"\n{'=' * 60}")
        operation_name = "SYNC 探测" if args.sync_only else "烧录"
        print(f"开始{operation_name} {port}")
        print(f"{'=' * 60}")

        # --wait-reset: 独立路径（先连串口 → 后台 SYNC → 弹窗 → 下载）
        if args.wait_reset:
            bl = UARTBootloader(port, baud=args.baud,
                               timeout_ms=args.timeout,
                               verbose=args.verbose)
            ok = _do_wait_reset_download(bl, bin_data, flash_addr, port, args)
            results[port] = ok
            result_text = "SYNC 探测成功" if args.sync_only else "烧录成功"
            if not ok:
                result_text = "SYNC 探测失败" if args.sync_only else "烧录失败"
            print(f"[{port}] ====== {result_text} ======")
            continue

        # 正常路径 (--reset 或普通下载)
        bl = UARTBootloader(port, baud=args.baud,
                           timeout_ms=args.timeout,
                           verbose=args.verbose)

        if not bl.connect(args.retries):
            results[port] = False
            continue

        try:
            if args.reset:
                # TS800X 限制：软件复位无法进入 ROM bootloader
                # 详见 SKILL.md ⚠️ 重要说明
                # 流程：A0→A1 软复位芯片 → 弹窗让用户按 RESET 进 bootloader
                print(f"\n  发送软复位 (A0→A1)，请稍候...")
                ok, fail_phase = bl.reset_download(
                    bin_data,
                    flash_addr=flash_addr,
                    target_baud=args.baud,
                    do_erase=args.erase,
                    erase_blocks=args.erase_blocks,
                    reset_delay_ms=args.reset_delay,
                    break_wake=args.break_wake,
                    allow_boot_no_response=args.allow_boot_no_response,
                )
                if ok:
                    print(f"[OK] 软复位 + 下载完成")
                elif fail_phase == 'sync':
                    # 仅 SYNC 阶段可安全转入人工 RESET；写入阶段失败不得重烧。
                    print(f"\n  ⚠️  TS800X 软件复位后无法自动进入 bootloader")
                    print(f"  ⚠️  请在开发板上按一下 RESET 按键")
                    bl.disconnect()
                    ok = _do_wait_reset_download(bl, bin_data, flash_addr, port, args)
                else:
                    print("  下载阶段失败，停止；不会自动重复发送固件包")
            else:
                ok = bl.download(
                    bin_data,
                    flash_addr=flash_addr,
                    target_baud=args.baud,
                    do_erase=args.erase,
                    erase_blocks=args.erase_blocks,
                    allow_boot_no_response=args.allow_boot_no_response,
                )
        finally:
            bl.disconnect()

        results[port] = ok
        if ok:
            print(f"[{port}] ====== 烧录成功 ======")
        else:
            print(f"[{port}] ====== 烧录失败 ======")

    # 汇总
    print(f"\n{'=' * 60}")
    ok_count = sum(1 for v in results.values() if v)
    ng_count = len(results) - ok_count
    summary_name = "SYNC 探测结果" if args.sync_only else "烧录结果"
    print(f"{summary_name}: {ok_count} 成功, {ng_count} 失败")
    for port, ok in results.items():
        status = "OK" if ok else "NG"
        print(f"  [{status}] {port}")
    print(f"{'=' * 60}")

    if ng_count == 0:
        return 0
    elif ok_count == 0:
        return 4
    else:
        return 1  # 部分失败


if __name__ == '__main__':
    sys.exit(main())
