#!/usr/bin/env python3
"""TS800X BLE scan, connection, and passthrough test tool."""

import argparse
import asyncio
import re
import sys
import time

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("[FAIL] bleak is required: python -m pip install bleak", file=sys.stderr)
    sys.exit(99)


ADDRESS_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def build_protocol_frame(command: int, payload: bytes) -> bytes:
    """Build [A5][Len][Cmd][Payload][Sum] frame."""
    if not 0 <= command <= 0xFF:
        raise ValueError("command must be one byte")
    if len(payload) > 251:
        raise ValueError("payload is too large for the one-byte frame length")
    frame_without_sum = bytes([0xA5, len(payload) + 4, command]) + payload
    return frame_without_sum + bytes([sum(frame_without_sum) & 0xFF])


def parse_hex_bytes(text: str) -> bytes:
    """Parse whitespace-separated hex bytes."""
    values = [int(value, 16) for value in text.split()]
    if any(value < 0 or value > 0xFF for value in values):
        raise ValueError("hex byte out of range")
    return bytes(values)


async def resolve_target(target: str, timeout: float = 5.0):
    """Resolve an address or one unique exact local name."""
    if ADDRESS_PATTERN.fullmatch(target):
        return target
    print(f"[INFO] Searching for '{target}' ...")
    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches = []
    for _address, (device, advertisement) in discovered.items():
        name = advertisement.local_name or device.name or ""
        if name.casefold() == target.casefold():
            matches.append(device)
    if not matches:
        print(f"[FAIL] Device not found: {target}")
        return None
    if len(matches) > 1:
        print("[FAIL] Multiple devices have this name; use a BLE address.")
        return None
    device = matches[0]
    print(f"[INFO] Found: {device.name or '(unnamed)'} ({device.address})")
    return device


async def connect_with_retry(target, timeout: float, retries: int):
    """Connect and return a client, or None after all attempts."""
    for attempt in range(retries + 1):
        client = BleakClient(target, timeout=timeout)
        try:
            await client.connect()
            if client.is_connected:
                return client
        except Exception as exc:
            print(f"[WARN] Connect attempt {attempt + 1}/{retries + 1} failed: {exc}")
        if client.is_connected:
            await client.disconnect()
        if attempt < retries:
            await asyncio.sleep(1)
    return None


async def cmd_scan(args) -> int:
    """Scan and print matching BLE devices."""
    print(f"[INFO] Scanning {args.timeout}s ...")
    devices = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
    found = []
    for address, (device, advertisement) in devices.items():
        name = advertisement.local_name or device.name or ""
        if args.name and args.name.lower() not in name.lower() and args.name.lower() not in address.lower():
            continue
        found.append((device, advertisement, name))
    if not found:
        print("[FAIL] No matching BLE devices found.")
        return 2

    print(f"\n{'Name':<25} {'Address':<20} {'RSSI':<6} Services")
    print("-" * 80)
    for device, advertisement, name in sorted(found, key=lambda item: -item[1].rssi):
        services = ", ".join((advertisement.service_uuids or [])[:3])
        print(f"{name:<25} {device.address:<20} {advertisement.rssi:<6} {services}")
    return 0


async def cmd_connect(args) -> int:
    """Connect, list GATT services, and disconnect."""
    target = await resolve_target(args.target, args.scan_timeout)
    if target is None:
        return 2
    client = await connect_with_retry(target, args.timeout, args.retries)
    if client is None:
        print("[FAIL] Connection failed after retries.")
        return 3
    try:
        print(f"[PASS] Connected: {client.address} MTU={client.mtu_size}")
        for service in client.services:
            print(f"Service: {service.uuid} ({service.description})")
            for characteristic in service.characteristics:
                print(f"  Char: {characteristic.uuid} [{', '.join(characteristic.properties)}]")
        return 0
    finally:
        if client.is_connected:
            await client.disconnect()


def choose_characteristics(client, write_uuid, notify_uuid):
    """Return write UUID, notify UUID, and write response mode."""
    write_characteristic = None
    notify_characteristic = None
    for service in client.services:
        for characteristic in service.characteristics:
            is_writable = any(
                prop in characteristic.properties for prop in ("write", "write-without-response")
            )
            is_notifiable = any(
                prop in characteristic.properties for prop in ("notify", "indicate")
            )
            if write_uuid and characteristic.uuid.lower() == write_uuid.lower() and is_writable:
                write_characteristic = characteristic
            elif write_characteristic is None and not write_uuid and is_writable:
                write_characteristic = characteristic
            if notify_uuid and characteristic.uuid.lower() == notify_uuid.lower() and is_notifiable:
                notify_characteristic = characteristic
            elif notify_characteristic is None and not notify_uuid and is_notifiable:
                notify_characteristic = characteristic
    write_response = bool(write_characteristic and "write" in write_characteristic.properties)
    return write_characteristic, notify_characteristic, write_response


async def interactive_loop(client, write_uuid: str, write_response: bool, protocol_mode: bool) -> None:
    """Read commands from stdin and perform GATT reads/writes."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = (await loop.run_in_executor(None, input, "\n> ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() in ("quit", "q", "exit"):
            break
        if line.lower().startswith("read"):
            parts = line.split()
            read_uuid = parts[1] if len(parts) > 1 else write_uuid
            data = await client.read_gatt_char(read_uuid)
            print(f"[{read_uuid}]: {' '.join(f'{byte:02X}' for byte in data)}")
            continue

        frame_mode = protocol_mode or line.lower().startswith("frame ")
        raw_text = line[6:].strip() if line.lower().startswith("frame ") else line
        data = parse_hex_bytes(raw_text)
        if frame_mode:
            if not data:
                raise ValueError("protocol mode requires a command byte")
            data = build_protocol_frame(data[0], data[1:])
        print(f"[TX]: {' '.join(f'{byte:02X}' for byte in data)}")
        await client.write_gatt_char(write_uuid, data, response=write_response)
        print(f"[PASS] Written (response={write_response}).")


async def cmd_passthrough(args) -> int:
    """Connect and run interactive GATT passthrough."""
    target = await resolve_target(args.target, args.scan_timeout)
    if target is None:
        return 2
    client = await connect_with_retry(target, args.timeout, args.retries)
    if client is None:
        print("[FAIL] Connection failed after retries.")
        return 3

    notify_started = False
    try:
        write_char, notify_char, write_response = choose_characteristics(client, args.write, args.notify)
        if write_char is None:
            print("[FAIL] No writable characteristic found.")
            return 4
        if args.notify and notify_char is None:
            print("[FAIL] Requested notify characteristic is missing or not notifiable.")
            return 4

        def on_notify(_characteristic, data):
            timestamp = time.strftime("%H:%M:%S")
            print(f"\n[{timestamp}] RX: {' '.join(f'{byte:02X}' for byte in data)}")

        if notify_char is not None:
            await client.start_notify(notify_char.uuid, on_notify)
            notify_started = True
            print(f"[PASS] Notify enabled: {notify_char.uuid}")
        print(f"[PASS] Write characteristic: {write_char.uuid} response={write_response}")
        print("Enter hex bytes, 'frame <cmd payload>', 'read [uuid]', or 'quit'.")
        await interactive_loop(client, write_char.uuid, write_response, args.protocol)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"[FAIL] {exc}")
        return 5
    finally:
        if notify_started and client.is_connected:
            try:
                await client.stop_notify(notify_char.uuid)
            except Exception:
                pass
        if client.is_connected:
            await client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description="TS800X BLE test tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--timeout", type=float, default=5.0)
    scan.add_argument("--name", default="")

    for command in ("connect", "passthrough"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("target")
        subparser.add_argument("--timeout", type=float, default=15.0)
        subparser.add_argument("--scan-timeout", type=float, default=5.0)
        subparser.add_argument("--retries", type=int, default=1)
    passthrough = subparsers.choices["passthrough"]
    passthrough.add_argument("--write")
    passthrough.add_argument("--notify")
    passthrough.add_argument("--protocol", action="store_true")
    return parser


async def run(args) -> int:
    """Dispatch the selected command."""
    if getattr(args, "retries", 0) < 0 or getattr(args, "retries", 0) > 10:
        print("[FAIL] --retries must be between 0 and 10")
        return 1
    if getattr(args, "timeout", 1) <= 0 or getattr(args, "timeout", 1) > 120:
        print("[FAIL] timeout must be between 0 and 120 seconds")
        return 1
    if getattr(args, "scan_timeout", 1) <= 0 or getattr(args, "scan_timeout", 1) > 120:
        print("[FAIL] scan timeout must be between 0 and 120 seconds")
        return 1
    if args.command == "scan":
        return await cmd_scan(args)
    if args.command == "connect":
        return await cmd_connect(args)
    return await cmd_passthrough(args)


def main() -> int:
    """CLI entry point."""
    args = build_parser().parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(f"[FAIL] BLE operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
