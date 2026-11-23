#!/usr/bin/env python3
"""Capture TS800X UART logs with deterministic exit codes."""

import argparse
import os
import re
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[FAIL] pyserial is required: python -m pip install pyserial", file=sys.stderr)
    sys.exit(99)


def available_ports() -> dict[str, str]:
    """Return available serial ports keyed case-insensitively."""
    return {port.device.upper(): port.device for port in serial.tools.list_ports.comports()}


def capture(args, expect_pattern) -> int:
    """Capture log lines and return a process exit code."""
    ports = available_ports()
    resolved_port = ports.get(args.port.upper())
    if resolved_port is None:
        print(f"[FAIL] Port not found: {args.port}; available={list(ports.values())}", file=sys.stderr)
        return 1

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    matched = False
    bytes_written = 0
    started_at = time.monotonic()
    deadline = started_at + args.duration
    minimum_match_time = started_at + args.min_duration
    port = None
    try:
        port = serial.Serial(resolved_port, args.baudrate, timeout=0.1)
        print(
            f"[INFO] Capturing {resolved_port} @ {args.baudrate} for {args.duration}s "
            f"-> {args.output}"
        )
        with open(args.output, "w", encoding="utf-8", newline="\n") as output:
            while time.monotonic() < deadline:
                data = port.readline()
                if not data:
                    continue
                line = data.decode("utf-8", errors="replace").rstrip("\r\n")
                output.write(line + "\n")
                output.flush()
                bytes_written += len(data)
                if expect_pattern and time.monotonic() >= minimum_match_time and expect_pattern.search(line):
                    matched = True
                    print(f"[PASS] Expected pattern found: {line}")
                    break
    except (OSError, serial.SerialException) as exc:
        print(f"[FAIL] UART capture failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if port is not None and port.is_open:
            port.close()

    elapsed = time.monotonic() - started_at
    if expect_pattern and not matched:
        print(f"[FAIL] Expected pattern not found in {elapsed:.1f}s ({bytes_written} bytes)")
        return 2
    if bytes_written == 0:
        print(f"[FAIL] No UART data captured in {elapsed:.1f}s")
        return 3
    print(f"[PASS] Captured {bytes_written} bytes in {elapsed:.1f}s")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="TS800X UART capture")
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--expect")
    parser.add_argument("--min-duration", type=float, default=3.0)
    args = parser.parse_args()

    if (
        args.duration <= 0
        or args.duration > 3600
        or args.min_duration < 0
        or args.min_duration > args.duration
        or args.baudrate <= 0
    ):
        parser.error(
            "duration must be 0..3600, min-duration within capture, and baudrate positive"
        )
    try:
        expect_pattern = re.compile(args.expect, re.IGNORECASE) if args.expect else None
    except re.error as exc:
        print(f"[FAIL] Invalid --expect regex: {exc}", file=sys.stderr)
        return 1
    return capture(args, expect_pattern)


if __name__ == "__main__":
    sys.exit(main())
