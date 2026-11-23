"""Safe TS800X JLink connection, flash, debug, and RTT operations."""

import os
from typing import Any, Dict, List, Optional

import pylink

from .exceptions import ErrorCode, TS800XError
from .utils import format_hex, load_firmware_segments


TS800X_FLASH_BASE = 0x10000000
TS800X_FLASH_SIZE = int(os.getenv("TS800X_FLASH_SIZE", "0x40000"), 0)
TS800X_DEFAULT_SERIAL = os.getenv("TS800X_JLINK_SERIAL") or None
TS800X_DEFAULT_INTERFACE = "SWD"
TS800X_DEFAULT_SPEED = 1000
TS800X_UNLOCK_ADDR = 0x40020100
TS800X_UNLOCK_VALUE = 0x00000202
TS800X_RTT_CB_ADDR = 0x20005F00
TS800X_RTT_UP_BUFFER = 0x20002988
TS800X_CHIP_NAME = "TS800X"


class JLinkManager:
    """Manage one JLink session and enforce the TS800X flash sequence."""

    _instance: Optional["JLinkManager"] = None
    _initialized = False

    def __new__(cls) -> "JLinkManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if JLinkManager._initialized:
            return

        self._jlink: Optional[pylink.JLink] = None
        self._connected = False
        self._unlocked = False
        self._flash_erased = False
        self._serial: Optional[str] = None
        JLinkManager._initialized = True

    def _require_connected(self) -> pylink.JLink:
        if not self.is_connected or self._jlink is None:
            raise TS800XError(ErrorCode.CONNECTION_FAILED)
        return self._jlink

    def _require_unlocked(self) -> pylink.JLink:
        jlink = self._require_connected()
        if not self._unlocked:
            raise TS800XError(
                ErrorCode.FLASH_LOCKED,
                "Flash operation requires ts800x_unlock first",
            )
        return jlink

    def _require_flash_ready(self) -> pylink.JLink:
        jlink = self._require_unlocked()
        if not self._flash_erased:
            raise TS800XError(ErrorCode.FLASH_NOT_ERASED)
        return jlink

    @staticmethod
    def _validate_width(address: int, size: int, width: int) -> None:
        if width not in (8, 16, 32):
            raise ValueError("width must be 8, 16, or 32")
        unit = width // 8
        if address < 0 or size <= 0 or address % unit or size % unit:
            raise ValueError(
                f"address and size must be positive and {unit}-byte aligned"
            )

    @staticmethod
    def _validate_flash_range(address: int, size: int) -> None:
        flash_end = TS800X_FLASH_BASE + TS800X_FLASH_SIZE
        end = address + size
        if size <= 0 or address < TS800X_FLASH_BASE or end > flash_end:
            raise ValueError(
                f"flash range {format_hex(address)}..{format_hex(end)} is outside "
                f"{format_hex(TS800X_FLASH_BASE)}..{format_hex(flash_end)}"
            )

    @staticmethod
    def _as_bytes(values: Any) -> bytes:
        if isinstance(values, bytes):
            return values
        if isinstance(values, bytearray):
            return bytes(values)
        return bytes(int(value) & 0xFF for value in values)

    @property
    def is_connected(self) -> bool:
        if not self._connected or self._jlink is None:
            return False
        try:
            connected = getattr(self._jlink, "connected", None)
            return bool(connected()) if callable(connected) else True
        except Exception:
            return False

    def enumerate_devices(self) -> List[Dict[str, Any]]:
        """Return connected JLink probes without opening a target session."""
        try:
            devices = pylink.JLink().connected_emulators()
            return [
                {
                    "index": index,
                    "serial_number": str(device.SerialNumber),
                    "product_name": str(device.acProduct or "J-Link"),
                    "connection": "USB" if device.Connection == 1 else "IP",
                }
                for index, device in enumerate(devices)
            ]
        except Exception as exc:
            raise TS800XError(ErrorCode.DEVICE_NOT_FOUND, str(exc)) from exc

    def connect(
        self,
        serial_number: Optional[str] = None,
        interface: str = TS800X_DEFAULT_INTERFACE,
        speed: int = TS800X_DEFAULT_SPEED,
    ) -> Dict[str, Any]:
        """Open a probe and attach to the TS800X target."""
        interface_name = interface.upper().strip()
        if interface_name not in ("SWD", "JTAG"):
            raise ValueError("interface must be SWD or JTAG")
        if speed < 1 or speed > 50000:
            raise ValueError("speed must be between 1 and 50000 kHz")

        selected_serial = serial_number or TS800X_DEFAULT_SERIAL
        if selected_serial is not None:
            selected_serial = str(selected_serial).strip()
            if not selected_serial.isdigit():
                raise ValueError("serial_number must contain digits only")

        if self._jlink is not None:
            self.disconnect()

        jlink = pylink.JLink()
        try:
            if selected_serial is None:
                jlink.open()
            else:
                jlink.open(serial_no=int(selected_serial))

            interface_value = getattr(pylink.enums.JLinkInterfaces, interface_name)
            jlink.set_tif(interface_value)
            jlink.set_speed(speed)
            jlink.connect(TS800X_CHIP_NAME)
            actual_serial = getattr(jlink, "serial_number", selected_serial)

            self._jlink = jlink
            self._connected = True
            self._unlocked = False
            self._flash_erased = False
            self._serial = str(actual_serial) if actual_serial is not None else None
            return {
                "success": True,
                "serial_number": self._serial,
                "interface": interface_name,
                "speed_khz": speed,
                "chip": TS800X_CHIP_NAME,
                "message": "TS800X connected",
            }
        except Exception as exc:
            try:
                jlink.close()
            except Exception:
                pass
            self._jlink = None
            self._connected = False
            self._unlocked = False
            self._flash_erased = False
            self._serial = None
            raise TS800XError(ErrorCode.CONNECTION_FAILED, str(exc)) from exc

    def disconnect(self) -> Dict[str, Any]:
        """Close the active probe and clear all volatile flash state."""
        close_error = None
        try:
            if self._jlink is not None:
                self._jlink.close()
        except Exception as exc:
            close_error = str(exc)
        finally:
            self._jlink = None
            self._connected = False
            self._unlocked = False
            self._flash_erased = False
            self._serial = None

        if close_error:
            return {"success": False, "error": close_error}
        return {"success": True, "message": "JLink disconnected"}

    def unlock(self) -> Dict[str, Any]:
        """Run the TS800X flash-unlock register write."""
        jlink = self._require_connected()
        try:
            jlink.memory_write32(TS800X_UNLOCK_ADDR, [TS800X_UNLOCK_VALUE])
            self._unlocked = True
            self._flash_erased = False
            return {
                "success": True,
                "address": format_hex(TS800X_UNLOCK_ADDR),
                "value": format_hex(TS800X_UNLOCK_VALUE),
                "message": "TS800X unlocked",
            }
        except Exception as exc:
            self._unlocked = False
            self._flash_erased = False
            raise TS800XError(ErrorCode.UNLOCK_FAILED, str(exc)) from exc

    def get_status(self) -> Dict[str, Any]:
        """Return connection and flash-sequence state."""
        connected = self.is_connected
        if not connected:
            self._connected = False
            self._unlocked = False
            self._flash_erased = False
        return {
            "success": True,
            "connected": connected,
            "unlocked": self._unlocked if connected else False,
            "flash_erased": self._flash_erased if connected else False,
            "serial": self._serial if connected else None,
            "chip": TS800X_CHIP_NAME if connected else None,
        }

    def reset(self, reset_type: str = "normal") -> Dict[str, Any]:
        """Reset the target and optionally halt it."""
        reset_name = reset_type.lower().strip()
        if reset_name not in ("normal", "halt"):
            raise ValueError("reset_type must be normal or halt")
        jlink = self._require_connected()
        jlink.reset(halt=reset_name == "halt")
        return {"success": True, "reset_type": reset_name, "message": "Target reset"}

    def halt(self) -> Dict[str, Any]:
        """Halt the target CPU."""
        self._require_connected().halt()
        return {"success": True, "message": "CPU halted"}

    def run(self) -> Dict[str, Any]:
        """Resume the target CPU."""
        self._require_connected().restart()
        return {"success": True, "message": "CPU running"}

    def read_memory(self, address: int, size: int, width: int = 32) -> Dict[str, Any]:
        """Read memory using an explicitly validated access width."""
        self._validate_width(address, size, width)
        jlink = self._require_connected()
        unit_count = size // (width // 8)
        try:
            read_method = getattr(jlink, f"memory_read{width}")
            values = read_method(address, unit_count)
            digits = width // 4
            return {
                "success": True,
                "address": format_hex(address),
                "size": size,
                "width": width,
                "data": [int(value) for value in values],
                "data_hex": " ".join(f"{int(value):0{digits}X}" for value in values),
            }
        except Exception as exc:
            raise TS800XError(ErrorCode.UNKNOWN_ERROR, str(exc)) from exc

    def write_memory(self, address: int, data: int, width: int = 32) -> Dict[str, Any]:
        """Write one validated scalar value to memory."""
        self._validate_width(address, width // 8, width)
        if data < 0 or data >= 1 << width:
            raise ValueError(f"data must fit in {width} bits")
        jlink = self._require_connected()
        try:
            write_method = getattr(jlink, f"memory_write{width}")
            write_method(address, [data])
            return {
                "success": True,
                "address": format_hex(address),
                "value": format_hex(data, width // 4),
                "width": width,
                "message": "Memory written",
            }
        except Exception as exc:
            raise TS800XError(ErrorCode.UNKNOWN_ERROR, str(exc)) from exc

    def flash_erase(
        self,
        start: int = TS800X_FLASH_BASE,
        size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Erase all or a validated range of TS800X flash."""
        jlink = self._require_unlocked()
        try:
            if size is None:
                if start != TS800X_FLASH_BASE:
                    raise ValueError("start must equal flash base for a chip erase")
                jlink.erase()
                result = {"success": True, "erase_type": "chip"}
            else:
                self._validate_flash_range(start, size)
                jlink.erase_range(start, size)
                result = {
                    "success": True,
                    "erase_type": "range",
                    "start": format_hex(start),
                    "size": size,
                }
            self._flash_erased = True
            result["message"] = "Flash erased"
            return result
        except ValueError:
            raise
        except Exception as exc:
            self._flash_erased = False
            raise TS800XError(ErrorCode.ERASE_FAILED, str(exc)) from exc

    def flash_program(self, address: int, data: bytes, verify: bool = True) -> Dict[str, Any]:
        """Program one absolute-address segment and optionally verify it."""
        firmware = self._as_bytes(data)
        self._validate_flash_range(address, len(firmware))
        jlink = self._require_flash_ready()
        try:
            jlink.flash_write(address, firmware)
        except Exception as exc:
            raise TS800XError(ErrorCode.PROGRAM_FAILED, str(exc)) from exc

        result: Dict[str, Any] = {
            "success": True,
            "address": format_hex(address),
            "size": len(firmware),
            "verify": "SKIPPED",
            "message": "Flash programmed",
        }
        if verify:
            verification = self.flash_verify(address, firmware)
            result["verify"] = "PASS" if verification["matched"] else "FAIL"
            result["success"] = verification["matched"]
            if not verification["matched"]:
                result["mismatch_count"] = verification["mismatch_count"]
                result["mismatches"] = verification["mismatches"]
        return result

    def flash_file(
        self,
        path: str,
        address: int = TS800X_FLASH_BASE,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """Program every validated segment in a BIN or Intel HEX file."""
        segments = load_firmware_segments(path, address)
        for segment_address, data in segments:
            self._validate_flash_range(segment_address, len(data))
        self._require_flash_ready()

        segment_results = []
        for segment_address, data in segments:
            segment_result = self.flash_program(segment_address, data, verify)
            segment_results.append(segment_result)
            if not segment_result["success"]:
                break

        success = len(segment_results) == len(segments) and all(
            result["success"] for result in segment_results
        )
        return {
            "success": success,
            "path": path,
            "base_address": format_hex(address),
            "size": sum(len(data) for _segment_address, data in segments),
            "segment_count": len(segments),
            "segments": segment_results,
            "verify": "PASS" if verify and success else ("SKIPPED" if not verify else "FAIL"),
            "message": "Firmware programmed" if success else "Firmware verification failed",
        }

    def flash_verify(self, address: int, data: bytes) -> Dict[str, Any]:
        """Compare one absolute flash range with expected bytes."""
        expected = self._as_bytes(data)
        self._validate_flash_range(address, len(expected))
        jlink = self._require_connected()
        try:
            actual = self._as_bytes(jlink.memory_read8(address, len(expected)))
        except Exception as exc:
            raise TS800XError(ErrorCode.VERIFY_FAILED, str(exc)) from exc

        mismatches = []
        mismatch_count = 0
        for index, (expected_byte, actual_byte) in enumerate(zip(expected, actual)):
            if expected_byte != actual_byte:
                mismatch_count += 1
                if len(mismatches) < 32:
                    mismatches.append(
                        {
                            "address": format_hex(address + index),
                            "expected": expected_byte,
                            "actual": actual_byte,
                        }
                    )
        mismatch_count += abs(len(expected) - len(actual))
        matched = mismatch_count == 0
        return {
            "success": matched,
            "matched": matched,
            "mismatch_count": mismatch_count,
            "mismatches": mismatches,
            "message": "Flash verify passed" if matched else "Flash verify failed",
        }

    def flash_verify_file(
        self,
        path: str,
        address: int = TS800X_FLASH_BASE,
    ) -> Dict[str, Any]:
        """Verify every segment in a BIN or Intel HEX file."""
        segments = load_firmware_segments(path, address)
        results = [
            self.flash_verify(segment_address, data)
            for segment_address, data in segments
        ]
        matched = all(result["matched"] for result in results)
        return {
            "success": matched,
            "matched": matched,
            "path": path,
            "segment_count": len(segments),
            "segments": results,
            "message": "Firmware verify passed" if matched else "Firmware verify failed",
        }

    def rtt_start(self, buffer_index: int = 0) -> Dict[str, Any]:
        """Start RTT at the TS800X control block."""
        if buffer_index < 0:
            raise ValueError("buffer_index must be non-negative")
        jlink = self._require_connected()
        try:
            jlink.rtt_start(TS800X_RTT_CB_ADDR)
            return {
                "success": True,
                "cb_addr": format_hex(TS800X_RTT_CB_ADDR),
                "up_buffer": format_hex(TS800X_RTT_UP_BUFFER),
                "message": "RTT started",
            }
        except Exception as exc:
            raise TS800XError(ErrorCode.RTT_NOT_STARTED, str(exc)) from exc

    def rtt_read(self, buffer_index: int = 0, size: int = 1024) -> Dict[str, Any]:
        """Read and UTF-8 decode one RTT up-buffer."""
        if buffer_index < 0 or size <= 0 or size > 1024 * 1024:
            raise ValueError("invalid RTT buffer_index or size")
        jlink = self._require_connected()
        try:
            raw_data = self._as_bytes(jlink.rtt_read(buffer_index, size))
            return {
                "success": True,
                "data": raw_data.decode("utf-8", errors="replace"),
                "bytes": len(raw_data),
            }
        except Exception as exc:
            raise TS800XError(ErrorCode.RTT_NOT_STARTED, str(exc)) from exc

    def rtt_stop(self) -> Dict[str, Any]:
        """Stop RTT."""
        jlink = self._require_connected()
        try:
            jlink.rtt_stop()
            return {"success": True, "message": "RTT stopped"}
        except Exception as exc:
            raise TS800XError(ErrorCode.RTT_NOT_STARTED, str(exc)) from exc

    def read_registers(self, names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Read selected CPU registers; report unavailable names explicitly."""
        jlink = self._require_connected()
        default_registers = [
            "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7",
            "R8", "R9", "R10", "R11", "R12", "SP", "LR", "PC",
            "xPSR", "MSP", "PSP",
        ]
        target = names or default_registers
        if not target or any(not isinstance(name, str) or not name.strip() for name in target):
            raise ValueError("register_names must contain non-empty strings")

        registers: Dict[str, str] = {}
        for register in target:
            try:
                registers[register] = format_hex(jlink.register_read(register))
            except Exception:
                registers[register] = "N/A"
        return {"success": True, "registers": registers}


jlink_manager = JLinkManager()
