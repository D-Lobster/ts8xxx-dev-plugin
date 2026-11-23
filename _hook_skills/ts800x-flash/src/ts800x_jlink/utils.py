"""TS800X JLink utility functions."""

from pathlib import Path
import time
from typing import Any, Dict, List, Tuple


def human_readable_size(size: int) -> str:
    """将字节数转换为人类可读格式."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def format_hex(value: int, width: int = 8) -> str:
    """格式化十六进制值."""
    return f"0x{value:0{width}X}"


def timed_operation(name: str) -> Dict[str, Any]:
    """创建计时操作上下文，返回耗时信息."""
    return {"name": name, "start": time.time()}


def elapsed_ms(ctx: Dict[str, Any]) -> float:
    """计算操作耗时（毫秒）."""
    return (time.time() - ctx["start"]) * 1000


def parse_intel_hex(path: str) -> List[Tuple[int, bytes]]:
    """Parse Intel HEX with checksum, overlap, and EOF validation."""
    records: List[Tuple[int, bytes]] = []
    base_address = 0
    saw_eof = False
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="ascii").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ValueError(f"line {line_number}: missing ':'")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise ValueError(f"line {line_number}: invalid hexadecimal record") from exc
        if len(record) < 5 or len(record) != record[0] + 5:
            raise ValueError(f"line {line_number}: invalid record length")
        if sum(record) & 0xFF:
            raise ValueError(f"line {line_number}: checksum mismatch")

        count = record[0]
        offset = int.from_bytes(record[1:3], "big")
        record_type = record[3]
        data = record[4:4 + count]
        if record_type == 0x00:
            records.append((base_address + offset, data))
        elif record_type == 0x01:
            saw_eof = True
            break
        elif record_type == 0x02:
            if count != 2:
                raise ValueError(f"line {line_number}: invalid segment-address record")
            base_address = int.from_bytes(data, "big") << 4
        elif record_type == 0x04:
            if count != 2:
                raise ValueError(f"line {line_number}: invalid linear-address record")
            base_address = int.from_bytes(data, "big") << 16
        elif record_type not in (0x03, 0x05):
            raise ValueError(f"line {line_number}: unsupported record type 0x{record_type:02X}")

    if not records:
        raise ValueError("HEX contains no data records")
    if not saw_eof:
        raise ValueError("HEX is missing EOF record")
    records.sort(key=lambda item: item[0])
    previous_end = -1
    for address, data in records:
        if address < previous_end:
            raise ValueError(f"HEX data overlaps at 0x{address:08X}")
        previous_end = address + len(data)

    merged: List[Tuple[int, bytes]] = []
    for address, data in records:
        if merged and merged[-1][0] + len(merged[-1][1]) == address:
            merged[-1] = (merged[-1][0], merged[-1][1] + data)
        else:
            merged.append((address, data))
    return merged


def load_firmware_segments(path: str, binary_address: int) -> List[Tuple[int, bytes]]:
    """Load BIN or HEX firmware as absolute address/data segments."""
    firmware_path = Path(path).expanduser().resolve()
    if not firmware_path.is_file():
        raise ValueError(f"firmware file not found: {firmware_path}")
    suffix = firmware_path.suffix.lower()
    if suffix == ".bin":
        data = firmware_path.read_bytes()
        if not data:
            raise ValueError("BIN firmware is empty")
        return [(binary_address, data)]
    if suffix == ".hex":
        segments = parse_intel_hex(str(firmware_path))
        # Some Keil HEX files use image-relative addresses near zero. Relocate
        # only that unambiguous form; never reinterpret another absolute map.
        if all(address < 0x01000000 for address, _data in segments):
            return [(binary_address + address, data) for address, data in segments]
        return segments
    raise ValueError("only .bin and .hex firmware files are supported")
