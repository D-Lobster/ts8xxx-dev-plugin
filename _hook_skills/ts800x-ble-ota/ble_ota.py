#!/usr/bin/env python3
"""
TS800X BLE OTA Firmware Upgrade Tool

通过 BLE 无线烧录 TS800X 固件。
使用 bleak 库通过蓝牙与 TS800X 设备通信，实现无线固件升级。

与 ts800x-flash (JLink) 和 ts800x-uart-download (UART) 互补：
  - JLink: 需要调试器，速度最快，支持深度调试
  - UART: 只需要串口线，适合产线
  - BLE OTA: 无线烧录，无需物理连接，适合现场升级

用法:
  python ble_ota.py scan                         # 扫描 BLE 设备
  python ble_ota.py info <device>                # 查看设备信息
  python ble_ota.py flash <device> --bin firmware.bin [options]
"""

import asyncio
import argparse
import hashlib
import re
import struct
import sys
import time

# ============================================================
# 依赖检查
# ============================================================
try:
    from bleak import BleakScanner, BleakClient
    from bleak.exc import BleakError
except ImportError:
    print("错误: 需要安装 bleak: pip install bleak")
    sys.exit(99)


# ============================================================
# 常量定义
# ============================================================

# BLE Service & Characteristic UUIDs
OTA_SRV_UUID = "00005453-0000-1000-8000-00805F9B34FB"
OTA_CTRL_CHR_UUID = "00005400-0000-1000-8000-00805F9B34FB"
OTA_DATA_CHR_UUID = "00005401-0000-1000-8000-00805F9B34FB"
CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"

# Flash Layout (TS800X)
FLASH_BASE = 0x10000000
FLASH_SIZE_DEFAULT = 0x40000
BACKUP_ADDR_DEFAULT = 0x10020000
OTA_ADDR_DEFAULT = 0x10002000
BOOT_ADDR_DEFAULT = 0x10000000

# OTA Protocol - 控制类型枚举
SIGNATURE = 0
DIGEST = 1
START_REQ = 2
START_RSP = 3
NEW_SECTOR = 4
INTEGRITY_CHECK_REQ = 5
INTEGRITY_CHECK_RSP = 6
FINISH = 7

# OTA 协议常量
SECTOR_SIZE = 4096                       # 扇区大小
SIGNATURE_PACKET_COUNT = 4               # 签名包数
SIGNATURE_PACKET_DATA_LEN = 16           # 每包签名数据长度
DIGEST_PACKET_COUNT = 2                  # 摘要包数
DIGEST_PACKET_DATA_LEN = 16              # 每包摘要数据长度

# 超时 (秒)
SCAN_TIMEOUT = 10
CONNECT_TIMEOUT = 15
SEND_TIMEOUT = 10
INDICATION_TIMEOUT = 10
SECTOR_TIMEOUT = 30

# 重试
SECTOR_RETRY_MAX = 3
BLE_ADDRESS_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


# ============================================================
# 协议工具函数
# ============================================================

def hex_dump(data: bytes, max_len: int = 32) -> str:
    """返回十六进制显示字符串（截断长数据）"""
    if not data:
        return "(empty)"
    s = ' '.join(f'{b:02X}' for b in data)
    if len(data) <= max_len:
        return s
    return s[:max_len * 3 - 1] + f'... ({len(data)}B)'


def check_sector_ack(data: bytes, segment_count: int) -> bool:
    """检查扇区 ACK 位图 — 所有片段是否都被设备确认收到。

    设备在 fota_profile.c 中按位设置 ACK 缓冲:
      fota_params.ack[segment_id/8] |= 1 << (segment_id % 8)

    读取时按相同规则检查每个位是否为 1。
    """
    for seg_id in range(segment_count):
        byte_idx = seg_id // 8
        bit_idx = seg_id % 8
        if byte_idx >= len(data):
            return False
        if not (data[byte_idx] & (1 << bit_idx)):
            return False
    return True


def build_finish_packed(file_size: int,
                        auto_reboot: bool = False,
                        erase_settings: bool = False) -> int:
    """构建 FINISH 命令的 packed 字段。

    位域(小端):
      bits  0-7 : status (bit0=OTA有效, bit1=重启, bit2=擦除设置)
      bits 8-31 : fw_copy_size (固件大小)
    """
    if file_size <= 0 or file_size > 0xFFFFFF:
        raise ValueError("FINISH file_size 必须在 1..0xFFFFFF")
    status = 0x01  # OTA valid
    if auto_reboot:
        status |= 0x02
    if erase_settings:
        status |= 0x04
    return (file_size << 8) | status


def validate_flash_layout(file_size: int, ota_addr: int, backup_addr: int,
                          boot_addr: int, flash_size: int) -> None:
    """Validate OTA ranges before connecting to a device."""
    if file_size <= 0 or file_size > 0xFFFFFF:
        raise ValueError("固件大小必须在 1..0xFFFFFF")
    if flash_size <= 0:
        raise ValueError("Flash 容量必须大于 0")
    flash_end = FLASH_BASE + flash_size
    for label, address, alignment in (
        ("ota_addr", ota_addr, SECTOR_SIZE),
        ("backup_addr", backup_addr, SECTOR_SIZE),
        ("boot_addr", boot_addr, 4),
    ):
        if address < FLASH_BASE or address >= flash_end or address % alignment:
            raise ValueError(f"{label}=0x{address:08X} 越界或未按 {alignment} 字节对齐")
    ota_range = (ota_addr, ota_addr + file_size)
    backup_range = (backup_addr, backup_addr + file_size)
    if ota_range[1] > flash_end or backup_range[1] > flash_end:
        raise ValueError("OTA/备份固件范围超出 Flash 容量")
    if max(ota_range[0], backup_range[0]) < min(ota_range[1], backup_range[1]):
        raise ValueError("OTA 目标区与备份区重叠")


# ============================================================
# BLE OTA 客户端
# ============================================================

class BLEOTA:
    """TS800X BLE OTA 固件升级客户端

    实现完整的 BLE OTA 协议流程:
    签名(可选) → 摘要 → 开始请求 → 扇区数据传输 → 完整性校验 → 完成
    """

    def __init__(self, verbose: bool = False, write_delay_ms: float = 10.0,
                 write_with_response: bool = False):
        self.client: BleakClient | None = None
        self.device_address: str = ""
        self.device_name: str = ""
        self.ctrl_char = None       # 控制特征 (indicate)
        self.data_char = None       # 数据特征 (write-without-response + read)
        self._ctrl_cccd_handle = None  # CCCD handle for control characteristic
        self.verbose = verbose
        # 数据包流控: TS800X 协议栈在无应答写(WW)洪泛下会大量丢包,
        # 默认每包之间插入 write_delay_ms 毫秒间隔; 也可强制 write-with-response
        self.write_delay_ms = float(write_delay_ms)
        self.write_with_response = bool(write_with_response)

        # 异步事件 — 用于等待设备指示(indicate)
        self._indication_event = asyncio.Event()
        self._indication_data = bytearray()

    # ---- 日志 ----

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def _vlog(self, msg: str):
        if self.verbose:
            self._log(msg)

    # ---- 扫描 ----

    async def scan(self, timeout: float = SCAN_TIMEOUT,
                   name_filter: str = "") -> list:
        """扫描 BLE 设备，标记 OTA 服务兼容设备。"""
        if timeout <= 0 or timeout > 120:
            raise ValueError("扫描超时必须在 0..120 秒")
        self._log(f"扫描 BLE 设备 (timeout={timeout}s, filter='{name_filter}')...")

        devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

        results = []
        for addr, (dev, adv) in devices.items():
            name = adv.local_name or dev.name or ""

            if name_filter and name_filter.lower() not in name.lower():
                continue

            has_ota = False
            if adv.service_uuids:
                has_ota = any(
                    OTA_SRV_UUID.lower() == u.lower()
                    for u in adv.service_uuids
                )

            results.append({
                'name': name,
                'address': addr,
                'rssi': adv.rssi,
                'has_ota': has_ota,
            })

        # 按信号强度排序
        results.sort(key=lambda d: -d['rssi'])
        return results

    # ---- 连接/断开 ----

    async def connect(self, address_or_name: str) -> bool:
        """连接 BLE 设备；重名设备必须改用地址。"""
        self.device_address = address_or_name

        self._log(f"连接设备 '{address_or_name}' ...")

        try:
            target = address_or_name
            if not BLE_ADDRESS_PATTERN.fullmatch(address_or_name):
                discovered = await BleakScanner.discover(
                    timeout=SCAN_TIMEOUT, return_adv=True
                )
                matches = []
                for _address, (device, advertisement) in discovered.items():
                    name = advertisement.local_name or device.name or ""
                    if name.casefold() == address_or_name.casefold():
                        matches.append(device)
                if not matches:
                    raise BleakError(f"未找到设备: {address_or_name}")
                if len(matches) > 1:
                    raise BleakError("发现多个同名设备，请使用 scan 输出的 BLE 地址")
                target = matches[0]
            self.client = BleakClient(target, timeout=CONNECT_TIMEOUT)
            await self.client.connect()

            if not self.client.is_connected:
                raise BleakError("连接失败")

            mtu = self.client.mtu_size
            self._log(f"已连接: {self.client.address}  MTU: {mtu}")

            await self._discover_services()
            return True

        except Exception as e:
            self._log(f"连接失败: {e}")
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            return False

    async def _discover_services(self):
        """发现 OTA 服务和特征值。"""
        if not self.client or not self.client.services:
            raise RuntimeError("服务未发现")

        for svc in self.client.services:
            if svc.uuid.lower() == OTA_SRV_UUID.lower():
                self._log(f"发现 OTA 服务: {svc.uuid}")
                for char in svc.characteristics:
                    cu = char.uuid.lower()
                    is_ctrl = (cu == OTA_CTRL_CHR_UUID.lower())
                    is_data = (cu == OTA_DATA_CHR_UUID.lower())
                    for d in char.descriptors:
                        if is_ctrl and d.uuid.lower() == CCCD_UUID.lower():
                            self._ctrl_cccd_handle = d.handle
                    label = "控制特征" if is_ctrl else "数据特征" if is_data else str(char.uuid)
                    self._log(f"  {label}: {char.uuid}  [{','.join(char.properties)}]")
                    if is_ctrl and self._ctrl_cccd_handle:
                        self._log(f"    CCCD = 0x{self._ctrl_cccd_handle:04X}")
                    if is_data:
                        self.data_char = char
                    elif is_ctrl:
                        self.ctrl_char = char
                break

        if not self.ctrl_char:
            raise RuntimeError(f"未找到控制特征 ({OTA_CTRL_CHR_UUID})")
        if not self.data_char:
            raise RuntimeError(f"未找到数据特征 ({OTA_DATA_CHR_UUID})")
        if "indicate" not in self.ctrl_char.properties:
            raise RuntimeError("控制特征不支持 Indicate，拒绝降级为 Notification")
        if "write" not in self.ctrl_char.properties:
            raise RuntimeError("控制特征不支持 write-with-response")
        if not any(prop in self.data_char.properties for prop in ("write", "write-without-response")):
            raise RuntimeError("数据特征不可写")
        if "read" not in self.data_char.properties:
            raise RuntimeError("数据特征不可读，无法校验扇区 ACK")

    async def disconnect(self):
        """断开 BLE 连接。"""
        if self.client and self.client.is_connected:
            try:
                if self.ctrl_char:
                    try:
                        await self.client.stop_notify(self.ctrl_char)
                    except Exception:
                        pass
                await self.client.disconnect()
                self._log("已断开连接")
            except Exception as e:
                self._log(f"断开异常: {e}")

    # ---- CCCD / 通知 ----

    async def _enable_ctrl_indications(self):
        """使能控制特征的 Indicate (CCCD=0x0200)。

        bleak 0.20+ 的 start_notify 支持 force_indicate=True 参数，
        会调用 WinRT 的 WriteClientCharacteristicConfigurationDescriptorWithResultAsync(INDICATE)。
        """
        if self._ctrl_cccd_handle is None:
            raise RuntimeError("CCCD handle 未知（服务发现阶段未解析）")

        try:
            await self.client.start_notify(
                self.ctrl_char,
                self._ctrl_indication_handler,
                force_indicate=True,
            )
            self._log("控制特征 Indication 已启用")
            return True
        except Exception as e:
            raise RuntimeError(f"无法启用控制特征 Indication: {e}") from e

    def _ctrl_indication_handler(self, characteristic, data: bytearray):
        """控制特征 Indication 回调。"""
        self._indication_data = bytearray(data)
        self._indication_event.set()
        self._vlog(f"IND CTRL: {hex_dump(bytes(data))}")

    # ---- 特征值读写 ----

    async def send_ctrl_cmd(self, data: bytes) -> bytes:
        """写入控制特征并等待 Indication 响应。

        必须先清除事件再发送，否则 indication 可能在 write 返回前到达
        导致事件被 _wait_for_indication 误清除而永远等不到。
        """
        self._indication_event.clear()
        self._indication_data = bytearray()
        self._vlog(f"CTRL > {hex_dump(data)}")
        await self.client.write_gatt_char(self.ctrl_char, data, response=True)
        try:
            await asyncio.wait_for(
                self._indication_event.wait(), timeout=INDICATION_TIMEOUT
            )
            return bytes(self._indication_data)
        except asyncio.TimeoutError:
            raise TimeoutError(f"等待设备指示超时 ({INDICATION_TIMEOUT}s)")

    async def send_ctrl_no_wait(self, data: bytes):
        """写入控制特征，不等待响应。

        用于不需要应答的命令(SIGNATURE, DIGEST, NEW_SECTOR, FINISH)。
        """
        self._vlog(f"CTRL > {hex_dump(data)} (no-wait)")
        await self.client.write_gatt_char(self.ctrl_char, data, response=True)

    async def write_data(self, data: bytes):
        """写入数据特征 (write-without-response)。"""
        self._vlog(f"DATA > {hex_dump(data)}")
        response = self.write_with_response or ("write-without-response" not in self.data_char.properties)
        await self.client.write_gatt_char(self.data_char, data, response=response)
        if (not response) and (self.write_delay_ms > 0):
            await asyncio.sleep(self.write_delay_ms / 1000.0)

    async def read_data(self) -> bytes:
        """读取数据特征 (获取扇区 ACK 位图)。"""
        data = await self.client.read_gatt_char(self.data_char)
        self._vlog(f"DATA < {hex_dump(bytes(data))}")
        return bytes(data)

    # ---- OTA 协议步骤 ----

    async def send_signature(self, sig_data: bytes):
        """发送签名 (4 包 × 16 字节 = 64 字节，可选步骤)。"""
        expected_length = SIGNATURE_PACKET_COUNT * SIGNATURE_PACKET_DATA_LEN
        if len(sig_data) != expected_length:
            raise ValueError(f"签名长度必须为 {expected_length} 字节")
        self._log(f"OTA: 发送签名 ({len(sig_data)} bytes)...")
        for i in range(SIGNATURE_PACKET_COUNT):
            cmd = bytearray(18)
            cmd[0] = SIGNATURE
            cmd[1] = i
            start = SIGNATURE_PACKET_DATA_LEN * i
            chunk = sig_data[start:start + SIGNATURE_PACKET_DATA_LEN]
            cmd[2:2 + len(chunk)] = chunk
            await self.send_ctrl_no_wait(bytes(cmd))
        self._log("OTA: 签名完成")

    async def send_digest(self, image_data: bytes):
        """发送 SHA-256 摘要 (2 包 × 16 字节 = 32 字节)。"""
        digest = hashlib.sha256(image_data).digest()
        self._log(f"OTA: SHA-256 = {digest.hex()}")

        self._log("OTA: 发送摘要...")
        for i in range(DIGEST_PACKET_COUNT):
            cmd = bytearray(18)
            cmd[0] = DIGEST
            cmd[1] = i
            start = DIGEST_PACKET_DATA_LEN * i
            chunk = digest[start:start + DIGEST_PACKET_DATA_LEN]
            cmd[2:2 + len(chunk)] = chunk
            await self.send_ctrl_no_wait(bytes(cmd))
        self._log("OTA: 摘要完成")

    async def send_start_req(self, backup_addr: int,
                              file_size: int, mtu: int) -> int:
        """发送开始请求，返回实际使用的 segment_max_size。"""
        # segment_max = 每个数据片段的 DATA 最大字节数
        # BLE ATT write-without-response: max = MTU-3
        # 数据包格式: [segment_id(1B)][data...], 所以 data = MTU-3-1 = MTU-4
        segment_max = max(16, mtu - 4)
        # 包总长 = 1(段号) + segment_max 必须 <= MTU-3, 否则主机侧写操作会抛异常
        if segment_max > (mtu - 4):
            segment_max = mtu - 4

        cmd = bytearray(13)
        cmd[0] = START_REQ
        struct.pack_into('<I', cmd, 1, backup_addr)
        struct.pack_into('<I', cmd, 5, file_size)
        struct.pack_into('<H', cmd, 9, segment_max)

        self._log(f"OTA: 开始请求 (backup=0x{backup_addr:08X}, "
                  f"size={file_size}, seg_max={segment_max})")

        ind_data = await self.send_ctrl_cmd(bytes(cmd))

        if len(ind_data) >= 2:
            rsp_type = ind_data[0]
            rsp_status = ind_data[1]
            if rsp_type == START_RSP:
                if rsp_status == 0:
                    self._log("OTA: 开始请求被接受")
                    # 设备在 START 处理里同步整片擦除目标区(GATT回调内阻塞)，
                    # 立即发扇区数据会撞进擦除窗口导致丢段/NAK，等待擦除完成
                    await asyncio.sleep(2.0)
                    return segment_max
                else:
                    raise RuntimeError(f"开始请求被拒绝: status={rsp_status}")

        raise RuntimeError(f"开始响应格式错误: {hex_dump(ind_data)}")

    async def send_new_sector(self, sector_idx: int):
        """发送新扇区命令 (NEW_SECTOR + sector_idx)。"""
        cmd = bytearray(3)
        cmd[0] = NEW_SECTOR
        struct.pack_into('<H', cmd, 1, sector_idx)
        await self.send_ctrl_no_wait(bytes(cmd))

    async def send_sector(self, image_data: bytes, sector_idx: int,
                          sector_size: int, segment_max: int) -> bool:
        """发送一个扇区的所有数据片段，并读取 ACK 确认。

        流程:
          1. NEW_SECTOR(sector_idx)
          2. 逐个发送 SEGMENT_ID + data (write-without-response)
          3. 读取 DATA 特征获取 ACK 位图
          4. 检查所有片段都被确认
        """
        # 计算本扇区的实际数据范围
        start = sector_size * sector_idx
        end = min(len(image_data), sector_size * (sector_idx + 1))
        sector_data = image_data[start:end]

        if not sector_data:
            return True  # 空扇区视为成功

        segment_count = (len(sector_data) + segment_max - 1) // segment_max

        self._vlog(f"  SECTOR {sector_idx}: {len(sector_data)}B, "
                   f"{segment_count} segments")

        # 1. 通知设备新扇区开始
        await self.send_new_sector(sector_idx)

        # 2. 发送所有数据片段
        for seg_idx in range(segment_count):
            seg_start = segment_max * seg_idx
            seg_end = min(len(sector_data), segment_max * (seg_idx + 1))
            seg_data = sector_data[seg_start:seg_end]

            cmd = bytearray(1 + len(seg_data))
            cmd[0] = seg_idx & 0xFF
            cmd[1:] = seg_data

            await self.write_data(bytes(cmd))

        # 3. 读 ACK 位图
        # WW 写是异步的: 最后几个包可能还在空中, 先等待落盘再读位图
        if (not self.write_with_response) and (self.write_delay_ms > 0):
            await asyncio.sleep(0.15)
        ack_data = await self.read_data()

        # 4. 验证
        if check_sector_ack(ack_data, segment_count):
            self._vlog(f"  SECTOR {sector_idx}: ACK OK")
            return True
        else:
            self._log(f"  SECTOR {sector_idx}: NAK")
            return False

    async def send_integrity_check(self) -> bool:
        """发送完整性校验请求，等待设备响应。"""
        cmd = bytearray(1)
        cmd[0] = INTEGRITY_CHECK_REQ

        self._log("OTA: 完整性校验...")
        ind_data = await self.send_ctrl_cmd(bytes(cmd))

        if len(ind_data) >= 2:
            rsp_type = ind_data[0]
            rsp_status = ind_data[1]
            if rsp_type == INTEGRITY_CHECK_RSP:
                if rsp_status == 0:
                    self._log("OTA: [OK] 完整性校验通过")
                    return True
                else:
                    self._log(f"OTA: [FAIL] 完整性校验失败 (status={rsp_status})")
                    return False

        raise RuntimeError(f"完整性校验响应格式错误: {hex_dump(ind_data)}")

    async def send_finish(self, file_size: int,
                           backup_addr: int, ota_addr: int,
                           boot_addr: int,
                           auto_reboot: bool = False,
                           erase_settings: bool = False):
        """发送完成指令。

        FINISH 指令包含:
          packed   = status(8bit) + fw_copy_size(24bit)
          src_addr = 备份区地址 (固件数据源)
          dst_addr = OTA 目标地址
          boot_addr = 启动地址

        当 auto_reboot=True 时，设备收到指令后立即复位，
        BLE 连接将断开，使用无响应写入避免等待超时。
        """
        packed = build_finish_packed(file_size, auto_reboot, erase_settings)

        cmd = bytearray(17)
        cmd[0] = FINISH
        struct.pack_into('<I', cmd, 1, packed)
        struct.pack_into('<I', cmd, 5, backup_addr)
        struct.pack_into('<I', cmd, 9, ota_addr)
        struct.pack_into('<I', cmd, 13, boot_addr)

        self._log(f"OTA: 发送完成指令 (reboot={auto_reboot})")
        use_response = "write-without-response" not in self.ctrl_char.properties
        self._vlog(f"CTRL > FINISH (response={use_response})")
        await self.client.write_gatt_char(
            self.ctrl_char, bytes(cmd), response=use_response
        )

        if auto_reboot:
            self._log("OTA: 设备将自动重启")
        else:
            self._log("OTA: 完成指令已发送，设备需要手动重启")

    # ---- 全流程编排 ----

    async def flash(self, image_data: bytes, *,
                     ota_addr: int = OTA_ADDR_DEFAULT,
                     backup_addr: int = BACKUP_ADDR_DEFAULT,
                     boot_addr: int = BOOT_ADDR_DEFAULT,
                     signature_data: bytes | None = None,
                     auto_reboot: bool = False,
                     erase_settings: bool = False,
                     flash_size: int = FLASH_SIZE_DEFAULT,
                     ) -> bool:
        """执行完整 BLE OTA 固件升级。"""
        file_size = len(image_data)
        validate_flash_layout(
            file_size, ota_addr, backup_addr, boot_addr, flash_size
        )
        sector_count = (file_size + SECTOR_SIZE - 1) // SECTOR_SIZE

        self._log(f"{'=' * 50}")
        self._log("BLE OTA 固件升级")
        self._log(f"{'=' * 50}")
        self._log(f"固件大小: {file_size} bytes ({file_size / 1024:.1f} KB)")
        self._log(f"扇区数量: {sector_count} (每个 {SECTOR_SIZE}B)")
        self._log(f"OTA 地址: 0x{ota_addr:08X}")
        self._log(f"备份地址: 0x{backup_addr:08X}")
        self._log(f"启动地址: 0x{boot_addr:08X}")
        self._log(f"自动重启: {auto_reboot}")
        self._log(f"{'=' * 50}")

        try:
            # 使能 Indication
            await self._enable_ctrl_indications()

            # [可选] 签名
            if signature_data:
                await self.send_signature(signature_data)

            # 摘要
            await self.send_digest(image_data)

            # 开始请求
            segment_max = await self.send_start_req(
                backup_addr, file_size, self.client.mtu_size
            )

            # 扇区数据传输
            for sector_idx in range(sector_count):
                for retry in range(SECTOR_RETRY_MAX + 1):
                    ok = await self.send_sector(
                        image_data, sector_idx, SECTOR_SIZE, segment_max
                    )
                    if ok:
                        break
                    if retry < SECTOR_RETRY_MAX:
                        self._log(f"  扇区 {sector_idx} 重试 {retry + 1}/{SECTOR_RETRY_MAX}...")
                    else:
                        raise RuntimeError(f"扇区 {sector_idx} 传输失败 (重试耗尽)")

                pct = (sector_idx + 1) * 100 // sector_count
                self._log(f"进度: [{sector_idx + 1}/{sector_count}] {pct}%")

            # 完整性校验
            integrity_ok = await self.send_integrity_check()
            if not integrity_ok:
                raise RuntimeError("完整性校验失败")

            # 完成
            await self.send_finish(file_size, backup_addr, ota_addr,
                                    boot_addr, auto_reboot, erase_settings)

            self._log(f"{'=' * 50}")
            self._log("[OK] BLE OTA 成功")
            self._log(f"{'=' * 50}")
            return True

        except Exception as e:
            self._log(f"[FAIL] OTA 失败: {e}")
            return False


# ============================================================
# CLI 命令
# ============================================================

async def cmd_scan(args):
    """扫描 BLE 设备。"""
    ota = BLEOTA(verbose=args.verbose,
                 write_delay_ms=getattr(args, 'write_delay_ms', 10.0),
                 write_with_response=getattr(args, 'write_with_response', False))
    try:
        devices = await ota.scan(timeout=args.timeout, name_filter=args.filter)
    except Exception as exc:
        print(f"扫描失败: {exc}")
        return 1

    if not devices:
        print("未发现 BLE 设备")
        return 2

    print(f"\n发现 {len(devices)} 个设备:")
    print(f"{'名称':<25} {'地址':<20} {'RSSI':<6} {'OTA'}")
    print("-" * 60)
    for d in devices:
        name = d['name'] or '(未命名)'
        ota_mark = "[OTA]" if d['has_ota'] else "     "
        print(f"{name:<25} {d['address']:<20} {d['rssi']:<6} {ota_mark}")
    return 0


async def cmd_info(args):
    """连接并查看设备信息 (服务 / 特征值)。"""
    ota = BLEOTA(verbose=args.verbose)

    ok = await ota.connect(args.device)
    if not ok:
        return 1

    try:
        print(f"\n设备: {ota.client.address}")
        print(f"MTU: {ota.client.mtu_size}")
        print()

        for svc in ota.client.services:
            is_ota = svc.uuid.lower() == OTA_SRV_UUID.lower()
            prefix = "[OTA]" if is_ota else "     "
            print(f"{prefix} 服务: {svc.uuid} ({svc.description})")

            for char in svc.characteristics:
                props = ', '.join(char.properties)
                print(f"       特征: {char.uuid}")
                print(f"             属性: [{props}]")
                if char.descriptors:
                    for desc in char.descriptors:
                        print(f"             描述符: {desc.uuid}")
            print()
    finally:
        await ota.disconnect()
    return 0


async def cmd_flash(args):
    """执行 BLE OTA 固件升级。"""
    # 验证固件文件
    try:
        with open(args.bin, 'rb') as f:
            image_data = f.read()
    except FileNotFoundError:
        print(f"错误: 固件文件不存在: {args.bin}")
        return 1
    except Exception as e:
        print(f"错误: 读取固件文件失败: {e}")
        return 1

    if not image_data:
        print(f"错误: 固件文件为空")
        return 1

    # 可选签名文件
    sig_data = None
    if not args.sign and not args.allow_unsigned:
        print("错误: 生产 OTA 必须提供 --sign；仅开发调试可显式使用 --allow-unsigned")
        return 1
    if args.sign:
        try:
            with open(args.sign, 'rb') as f:
                sig_data = f.read()
            if len(sig_data) != 64:
                print(f"错误: 签名文件必须为 64 字节 ({len(sig_data)}B)")
                return 1
        except Exception as e:
            print(f"错误: 读取签名文件失败: {e}")
            return 1

    # 地址解析
    def parse_address(value: str) -> int:
        return int(value, 0)

    try:
        ota_addr = parse_address(args.ota_addr)
        backup_addr = parse_address(args.backup_addr)
        boot_addr = parse_address(args.boot_addr)
        flash_size = parse_address(args.flash_size)
        validate_flash_layout(
            len(image_data), ota_addr, backup_addr, boot_addr, flash_size
        )
    except ValueError as exc:
        print(f"错误: OTA 地址布局无效: {exc}")
        return 1

    # 连接
    ota = BLEOTA(verbose=args.verbose)
    ok = await ota.connect(args.device)

    if not ok:
        return 1

    try:
        success = await ota.flash(
            image_data,
            ota_addr=ota_addr,
            backup_addr=backup_addr,
            boot_addr=boot_addr,
            signature_data=sig_data,
            auto_reboot=args.reboot,
            erase_settings=args.erase_settings,
            flash_size=flash_size,
        )
        return 0 if success else 1
    finally:
        try:
            await ota.disconnect()
        except Exception:
            pass  # 设备可能已重启断开，忽略


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='TS800X BLE OTA Firmware Upgrade Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 扫描 BLE 设备
  python ble_ota.py scan

  # 查看设备 OTA 服务信息
  python ble_ota.py info "YQ-TIRE-V04"

  # OTA 固件升级
  python ble_ota.py flash "YQ-TIRE-V04" --bin firmware.bin

  # OTA 升级 + 自动重启
  python ble_ota.py flash "YQ-TIRE-V04" --bin firmware.bin --reboot

  # 指定地址 + 签名文件
  python ble_ota.py flash "YQ-TIRE-V04" --bin firmware.bin --sign signature.bin
  --ota-addr 0x10002000 --backup-addr 0x10020000 --reboot -v
        ''',
    )

    sub = parser.add_subparsers(dest='cmd', help='子命令')

    # --- scan ---
    p_scan = sub.add_parser('scan', help='扫描 BLE 设备')
    p_scan.add_argument('--timeout', type=float, default=SCAN_TIMEOUT,
                        help=f'扫描时长 (默认: {SCAN_TIMEOUT}s)')
    p_scan.add_argument('--filter', type=str, default='',
                        help='按设备名关键字过滤')
    p_scan.add_argument('-v', '--verbose', action='store_true',
                        help='详细输出')

    # --- info ---
    p_info = sub.add_parser('info', help='查看设备 BLE 服务信息')
    p_info.add_argument('device', help='设备名或 BLE 地址')
    p_info.add_argument('-v', '--verbose', action='store_true',
                        help='详细输出')

    # --- flash ---
    p_flash = sub.add_parser('flash', help='执行 BLE OTA 固件升级')
    p_flash.add_argument('device', help='设备名或 BLE 地址')
    p_flash.add_argument('--bin', required=True, help='固件 .bin 文件路径')
    p_flash.add_argument('--sign', help='签名 .bin 文件路径 (生产必需, 64 字节)')
    p_flash.add_argument('--allow-unsigned', action='store_true',
                         help='显式允许无签名 OTA（仅开发调试）')
    p_flash.add_argument('--ota-addr', default='0x10002000',
                         help='OTA 目标地址 (默认: 0x10002000)')
    p_flash.add_argument('--backup-addr', default='0x10020000',
                         help='OTA 备份地址 (默认: 0x10020000)')
    p_flash.add_argument('--boot-addr', default='0x10000000',
                         help='启动地址 (默认: 0x10000000)')
    p_flash.add_argument('--flash-size', default='0x40000',
                         help='Flash 容量 (默认: 0x40000)')
    p_flash.add_argument('--reboot', action='store_true',
                         help='烧录完成后自动重启设备')
    p_flash.add_argument('--erase-settings', action='store_true',
                         help='擦除设置参数')
    p_flash.add_argument('--write-delay-ms', type=float, default=10.0,
                         help='每包之间的间隔毫秒(默认 10ms, 用于避免设备丢包)')
    p_flash.add_argument('--write-with-response', action='store_true',
                         help='数据包使用写应答(更稳但更慢)')
    p_flash.add_argument('-v', '--verbose', action='store_true',
                         help='详细输出')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return 1

    # 路由
    try:
        if args.cmd == 'scan':
            return asyncio.run(cmd_scan(args))
        if args.cmd == 'info':
            return asyncio.run(cmd_info(args))
        return asyncio.run(cmd_flash(args))
    except KeyboardInterrupt:
        print("操作已取消")
        return 130
    except Exception as exc:
        print(f"操作失败: {exc}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
