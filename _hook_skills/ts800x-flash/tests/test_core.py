"""Hardware-free tests for the TS800X JLink CLI backend."""

from types import SimpleNamespace

import pytest

from ts800x_jlink.cli import build_parser, run_flash, run_rtt
from ts800x_jlink.exceptions import TS800XError, ErrorCode
from ts800x_jlink.jlink_manager import JLinkManager, TS800X_FLASH_BASE
from ts800x_jlink.utils import (
    format_hex,
    human_readable_size,
    load_firmware_segments,
    parse_intel_hex,
)


def make_hex_record(address, record_type, data=b""):
    """Build one checksum-correct Intel HEX record."""
    body = bytes([len(data)]) + address.to_bytes(2, "big") + bytes([record_type]) + data
    checksum = (-sum(body)) & 0xFF
    return ":" + (body + bytes([checksum])).hex().upper()


class FakeJLink:
    """Minimal in-memory pylink substitute for flash-state tests."""

    def __init__(self):
        self.memory = {}
        self.unlock_writes = []
        self.erased = False

    def connected(self):
        return True

    def memory_write32(self, address, values):
        self.unlock_writes.append((address, values))

    def erase(self):
        self.erased = True

    def flash_write(self, address, data):
        for index, value in enumerate(data):
            self.memory[address + index] = value

    def memory_read8(self, address, size):
        return [self.memory.get(address + index, 0xFF) for index in range(size)]


def make_manager():
    """Create an isolated manager without changing the module singleton."""
    manager = object.__new__(JLinkManager)
    manager._jlink = FakeJLink()
    manager._connected = True
    manager._unlocked = False
    manager._flash_erased = False
    manager._serial = "test"
    return manager


class TestUtils:
    def test_human_readable_size(self):
        assert human_readable_size(0) == "0 B"
        assert human_readable_size(512) == "512 B"
        assert human_readable_size(1024) == "1.0 KB"
        assert human_readable_size(1536) == "1.5 KB"
        assert human_readable_size(1048576) == "1.0 MB"

    def test_format_hex(self):
        assert format_hex(0) == "0x00000000"
        assert format_hex(0x10000000) == "0x10000000"
        assert format_hex(0xFF, 2) == "0xFF"
        assert format_hex(0x202, 8) == "0x00000202"


class TestExceptions:
    def test_error_code_creation(self):
        err = TS800XError(ErrorCode.UNLOCK_FAILED, "test detail")
        assert err.error_code == ErrorCode.UNLOCK_FAILED
        assert "UNLOCK_FAILED" in str(err)

    def test_error_to_dict(self):
        err = TS800XError(ErrorCode.FLASH_NOT_ERASED)
        d = err.to_dict()
        assert d["code"] == "FLASH_NOT_ERASED"
        assert "suggestion" in d


class TestFirmwareParsing:
    def test_relative_hex_is_relocated_and_contiguous_records_merge(self, tmp_path):
        firmware = tmp_path / "firmware.hex"
        firmware.write_text(
            "\n".join(
                [
                    make_hex_record(0, 0, b"\x01\x02"),
                    make_hex_record(2, 0, b"\x03\x04"),
                    make_hex_record(0, 1),
                ]
            ),
            encoding="ascii",
        )

        segments = load_firmware_segments(str(firmware), TS800X_FLASH_BASE)

        assert segments == [(TS800X_FLASH_BASE, b"\x01\x02\x03\x04")]

    def test_hex_checksum_failure_is_rejected(self, tmp_path):
        firmware = tmp_path / "bad.hex"
        firmware.write_text(":0100000001FF\n:00000001FF\n", encoding="ascii")

        with pytest.raises(ValueError, match="checksum"):
            parse_intel_hex(str(firmware))

    def test_absolute_non_ts800x_hex_is_not_relocated(self, tmp_path):
        firmware = tmp_path / "absolute.hex"
        firmware.write_text(
            "\n".join(
                [
                    make_hex_record(0, 4, b"\x08\x00"),
                    make_hex_record(0, 0, b"\x01"),
                    make_hex_record(0, 1),
                ]
            ),
            encoding="ascii",
        )

        assert load_firmware_segments(str(firmware), TS800X_FLASH_BASE)[0][0] == 0x08000000


class TestFlashStateMachine:
    def test_program_requires_unlock_and_erase(self):
        manager = make_manager()

        with pytest.raises(TS800XError) as error:
            manager.flash_program(TS800X_FLASH_BASE, b"\x01")
        assert error.value.error_code == ErrorCode.FLASH_LOCKED

        manager.unlock()
        with pytest.raises(TS800XError) as error:
            manager.flash_program(TS800X_FLASH_BASE, b"\x01")
        assert error.value.error_code == ErrorCode.FLASH_NOT_ERASED

    def test_bin_program_and_verify(self, tmp_path):
        manager = make_manager()
        firmware = tmp_path / "firmware.bin"
        firmware.write_bytes(b"\x10\x20\x30\x40")

        manager.unlock()
        manager.flash_erase()
        result = manager.flash_file(str(firmware))

        assert result["success"] is True
        assert result["verify"] == "PASS"
        assert result["segment_count"] == 1

    def test_verify_mismatch_is_failure(self):
        manager = make_manager()
        result = manager.flash_verify(TS800X_FLASH_BASE, b"\x01")

        assert result["success"] is False
        assert result["matched"] is False
        assert result["mismatch_count"] == 1

    def test_out_of_range_program_is_rejected(self):
        manager = make_manager()
        manager.unlock()
        manager.flash_erase()

        with pytest.raises(ValueError, match="outside"):
            manager.flash_program(TS800X_FLASH_BASE - 1, b"\x01")


class TestHardwareConstants:
    """验证 TS800X 硬件常量不被意外修改."""

    def test_unlock_sequence(self):
        from ts800x_jlink.jlink_manager import (
            TS800X_UNLOCK_ADDR, TS800X_UNLOCK_VALUE, TS800X_FLASH_BASE
        )
        assert TS800X_UNLOCK_ADDR == 0x40020100
        assert TS800X_UNLOCK_VALUE == 0x00000202
        assert TS800X_FLASH_BASE == 0x10000000

    def test_rtt_addresses(self):
        from ts800x_jlink.jlink_manager import (
            TS800X_RTT_CB_ADDR, TS800X_RTT_UP_BUFFER
        )
        assert TS800X_RTT_CB_ADDR == 0x20005F00
        assert TS800X_RTT_UP_BUFFER == 0x20002988


class FakeAtomicManager:
    """Record one composite CLI operation without opening hardware."""

    def __init__(self, verify="PASS"):
        self.calls = []
        self.verify = verify

    def connect(self, serial_number, interface, speed):
        self.calls.append(("connect", serial_number, interface, speed))
        return {"success": True}

    def unlock(self):
        self.calls.append(("unlock",))
        return {"success": True}

    def flash_erase(self):
        self.calls.append(("erase",))
        return {"success": True}

    def flash_file(self, firmware, address, verify):
        self.calls.append(("program", firmware, address, verify))
        return {"success": self.verify == "PASS", "verify": self.verify}

    def reset(self, reset_type):
        self.calls.append(("reset", reset_type))
        return {"success": True}

    def disconnect(self):
        self.calls.append(("disconnect",))
        return {"success": True}

    def rtt_start(self, buffer_index):
        self.calls.append(("rtt_start", buffer_index))
        return {"success": True}

    def rtt_read(self, buffer_index, size):
        self.calls.append(("rtt_read", buffer_index, size))
        return {"success": True, "data": "OK\n", "bytes": 3}

    def rtt_stop(self):
        self.calls.append(("rtt_stop",))
        return {"success": True}


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


class TestHostCli:
    @staticmethod
    def flash_args():
        return SimpleNamespace(
            firmware="firmware.hex",
            address=TS800X_FLASH_BASE,
            serial_number=None,
            interface="SWD",
            speed=1000,
        )

    def test_atomic_flash_requires_verify_pass_before_reset(self):
        manager = FakeAtomicManager()

        result = run_flash(self.flash_args(), manager)

        assert result["success"] is True
        assert result["verify"] == "PASS"
        assert [call[0] for call in manager.calls] == [
            "connect",
            "unlock",
            "erase",
            "program",
            "reset",
            "disconnect",
        ]

    def test_atomic_flash_stops_after_verify_failure(self):
        manager = FakeAtomicManager(verify="FAIL")

        result = run_flash(self.flash_args(), manager)

        assert result["success"] is False
        assert result["verify"] == "FAIL"
        assert "reset" not in [call[0] for call in manager.calls]
        assert manager.calls[-1][0] == "disconnect"

    def test_cli_parser_does_not_touch_hardware(self):
        args = build_parser().parse_args(["flash", "--firmware", "firmware.hex"])

        assert args.operation == "flash"
        assert args.address == TS800X_FLASH_BASE

    def test_rtt_capture_is_bounded_and_cleans_up(self):
        manager = FakeAtomicManager()
        clock = FakeClock()
        args = SimpleNamespace(
            duration=0.2,
            poll_interval=0.1,
            buffer_index=0,
            size=64,
            serial_number=None,
            interface="SWD",
            speed=1000,
        )

        result = run_rtt(args, manager, clock=clock, sleeper=clock.sleep)

        assert result["success"] is True
        assert result["data"] == "OK\nOK\n"
        assert result["bytes"] == 6
        assert manager.calls[-2:] == [("rtt_stop",), ("disconnect",)]
