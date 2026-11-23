"""Host-neutral CLI adapter over the canonical TS800X JLink manager."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Callable

from .exceptions import TS800XError
from .jlink_manager import TS800X_FLASH_BASE, JLinkManager, jlink_manager


Result = dict[str, Any]


def _error_result(operation: str, exc: Exception) -> Result:
    if isinstance(exc, TS800XError):
        error: Any = exc.to_dict()
    elif isinstance(exc, ValueError):
        error = {"code": "INVALID_PARAMETER", "detail": str(exc)}
    else:
        error = {"code": "UNKNOWN", "detail": str(exc)}
    return {"success": False, "operation": operation, "error": error}


def _append_step(steps: list[Result], name: str, result: Result) -> Result:
    step = {"name": name, **result}
    steps.append(step)
    return result


def _connect(args: argparse.Namespace, manager: JLinkManager, steps: list[Result]) -> None:
    _append_step(
        steps,
        "connect",
        manager.connect(args.serial_number, args.interface, args.speed),
    )


def _disconnect(manager: JLinkManager, steps: list[Result]) -> None:
    try:
        _append_step(steps, "disconnect", manager.disconnect())
    except Exception as exc:  # Cleanup must not hide the primary result.
        steps.append({"name": "disconnect", **_error_result("disconnect", exc)})


def run_flash(args: argparse.Namespace, manager: JLinkManager = jlink_manager) -> Result:
    """Connect, unlock, erase, program with verify, reset, and disconnect."""
    steps: list[Result] = []
    report: Result = {"success": False, "operation": "flash", "steps": steps}
    try:
        _connect(args, manager, steps)
        _append_step(steps, "unlock", manager.unlock())
        _append_step(steps, "erase", manager.flash_erase())
        program = _append_step(
            steps,
            "program",
            manager.flash_file(args.firmware, args.address, verify=True),
        )
        report["verify"] = program.get("verify", "FAIL")
        if program.get("success") is not True or program.get("verify") != "PASS":
            report["error"] = {
                "code": "VERIFY_FAILED",
                "detail": "Programming or read-back verification failed",
            }
            return report
        _append_step(steps, "reset", manager.reset("normal"))
        report["success"] = True
        report["firmware_path"] = args.firmware
        return report
    except Exception as exc:
        report.update(_error_result("flash", exc))
        return report
    finally:
        _disconnect(manager, steps)


def run_reset(args: argparse.Namespace, manager: JLinkManager = jlink_manager) -> Result:
    """Connect, reset, and disconnect in one process."""
    steps: list[Result] = []
    report: Result = {"success": False, "operation": "reset", "steps": steps}
    try:
        _connect(args, manager, steps)
        _append_step(steps, "reset", manager.reset(args.reset_type))
        report["success"] = True
        return report
    except Exception as exc:
        report.update(_error_result("reset", exc))
        return report
    finally:
        _disconnect(manager, steps)


def run_rtt(
    args: argparse.Namespace,
    manager: JLinkManager = jlink_manager,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Result:
    """Capture RTT for a bounded duration in one connected session."""
    steps: list[Result] = []
    report: Result = {"success": False, "operation": "rtt", "steps": steps}
    chunks: list[str] = []
    byte_count = 0
    started = False
    try:
        _connect(args, manager, steps)
        _append_step(steps, "rtt_start", manager.rtt_start(args.buffer_index))
        started = True
        deadline = clock() + args.duration
        while clock() < deadline:
            read_result = manager.rtt_read(args.buffer_index, args.size)
            if read_result.get("success") is not True:
                raise RuntimeError("RTT read returned success=false")
            chunks.append(str(read_result.get("data", "")))
            byte_count += int(read_result.get("bytes", 0))
            sleeper(args.poll_interval)
        report.update(
            {
                "success": True,
                "data": "".join(chunks),
                "bytes": byte_count,
                "duration_seconds": args.duration,
            }
        )
        return report
    except Exception as exc:
        report.update(_error_result("rtt", exc))
        return report
    finally:
        if started:
            try:
                _append_step(steps, "rtt_stop", manager.rtt_stop())
            except Exception as exc:
                steps.append({"name": "rtt_stop", **_error_result("rtt_stop", exc)})
        _disconnect(manager, steps)


def run_list(manager: JLinkManager = jlink_manager) -> Result:
    """List probes without opening a target session."""
    try:
        return {
            "success": True,
            "operation": "list",
            "devices": manager.enumerate_devices(),
        }
    except Exception as exc:
        return _error_result("list", exc)


def _positive_int(value: str) -> int:
    number = int(value, 0)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--serial-number")
    parser.add_argument("--interface", choices=("SWD", "JTAG"), default="SWD")
    parser.add_argument("--speed", type=_positive_int, default=1000)


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser without touching hardware."""
    parser = argparse.ArgumentParser(prog="ts800x-jlink")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("list", help="List visible JLink probes")

    flash = subparsers.add_parser("flash", help="Atomic unlock/erase/program/verify/reset")
    _connection_arguments(flash)
    flash.add_argument("--firmware", required=True)
    flash.add_argument("--address", type=lambda value: int(value, 0), default=TS800X_FLASH_BASE)

    reset = subparsers.add_parser("reset", help="Connect and reset the target")
    _connection_arguments(reset)
    reset.add_argument("--reset-type", choices=("normal", "halt"), default="normal")

    rtt = subparsers.add_parser("rtt", help="Capture RTT for a bounded duration")
    _connection_arguments(rtt)
    rtt.add_argument("--duration", type=float, default=10.0)
    rtt.add_argument("--poll-interval", type=float, default=0.1)
    rtt.add_argument("--buffer-index", type=int, default=0)
    rtt.add_argument("--size", type=_positive_int, default=1024)
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if getattr(args, "duration", 1.0) <= 0 or getattr(args, "duration", 1.0) > 60:
        raise ValueError("duration must be greater than 0 and at most 60 seconds")
    if getattr(args, "poll_interval", 0.1) < 0.02:
        raise ValueError("poll_interval must be at least 0.02 seconds")
    if getattr(args, "size", 1) > 1024 * 1024:
        raise ValueError("RTT size must be at most 1048576 bytes")
    if getattr(args, "buffer_index", 0) < 0:
        raise ValueError("buffer_index must be non-negative")


def main() -> None:
    """Run one atomic operation and print one JSON object."""
    args = build_parser().parse_args()
    try:
        _validate_args(args)
        if args.operation == "flash":
            result = run_flash(args)
        elif args.operation == "reset":
            result = run_reset(args)
        elif args.operation == "rtt":
            result = run_rtt(args)
        else:
            result = run_list()
    except Exception as exc:
        result = _error_result(args.operation, exc)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(0 if result.get("success") is True else 1)


if __name__ == "__main__":
    main()
