"""
Probe all writable characteristics with various command patterns.

Tests for graffiti mode, direct pixel control, and other undocumented features
by sending known command patterns from related devices (Merkury, etc.).
"""

import argparse
import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from loguru import logger as log

from src.utils.logging_config import setup_logging
from src.led_protocol import SERVICE_UUID as LOY_SPACE_SERVICE_UUID

# Service UUIDs we consider a match
COOLLED_SERVICE_UUID = "0000fee7-0000-1000-8000-00805f9b34fb"

# Test command sets from related devices
# Format: (name, hex_command, description)
TEST_COMMANDS: list[tuple[str, str, str]] = [
    # Merkury-style graffiti mode commands
    ("graffiti_init_1", "bc00010155", "Start graffiti mode (Merkury)"),
    ("graffiti_init_2", "bc000d0d55", "Enable draw mode (Merkury)"),
    ("power_on", "bcff010055", "Power on (Merkury)"),
    ("power_off", "bcff00ff55", "Power off (Merkury)"),
    ("slideshow", "bc00121255", "Start slideshow (Merkury)"),
    # Single pixel test (red at position 0)
    ("pixel_0_red", "bc01010000ff0000ff55", "Red pixel at 0 (Merkury)"),
    # YS-protocol style commands (from LOY SPACE)
    ("ys_reset", "aa55ffff0a000900c102080200ffdc04", "Reset (YS)"),
    ("ys_ready", "aa55ffff0a000900c10208020000dd03", "Ready (YS)"),
    ("ys_blank", "aa55ffff0a000500c10204020001d603", "Blank screen (YS)"),
    # Simple ping/status commands
    ("ping_00", "00", "Null byte"),
    ("ping_ff", "ff", "0xFF byte"),
    ("ping_55", "55", "0x55 byte (common terminator)"),
]

# Specific characteristics to try for each command type
GRAFFITI_CHAR_PREFIXES = ["0000ffd1", "0000ffe1", "0000fff2"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe writable characteristics with test commands",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Device name (supports substring match)",
    )
    parser.add_argument(
        "--address",
        type=str,
        default=None,
        help="Device address/UUID from BLE scan",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds",
    )
    parser.add_argument(
        "--char",
        type=str,
        default=None,
        help="Specific characteristic UUID to test (test all writable if not set)",
    )
    parser.add_argument(
        "--command",
        type=str,
        default=None,
        help="Specific command name to test (test all if not set)",
    )
    parser.add_argument(
        "--custom-hex",
        type=str,
        default=None,
        help="Custom hex command to send (e.g., 'bc01010000ff0000ff55')",
    )
    parser.add_argument(
        "--wait-response",
        type=float,
        default=0.5,
        help="Seconds to wait for notification response after each command",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List commands without sending",
    )
    return parser.parse_args()


async def _discover_device(
    *,
    target_name: str | None,
    target_address: str | None,
    timeout: float,
) -> BLEDevice | None:
    """Scan for and return the target device."""
    log.info("Scanning for BLE devices...")
    devices_dict = await BleakScanner.discover(timeout=timeout, return_adv=True)

    for _key, (device, adv) in devices_dict.items():
        device_name = device.name or ""
        service_uuids = adv.service_uuids or []

        if target_address and device.address.lower() == target_address.lower():
            return device

        if target_name and target_name.lower() in device_name.lower():
            return device

        if not target_name and not target_address:
            if (
                LOY_SPACE_SERVICE_UUID.lower() in [u.lower() for u in service_uuids]
                or COOLLED_SERVICE_UUID in service_uuids
            ):
                log.info(
                    "Found device by service UUID: {} ({})", device_name, device.address
                )
                return device

    return None


class CharacteristicProber:
    """Probes characteristics with test commands and monitors responses."""

    def __init__(self, client: BleakClient, wait_time: float = 0.5) -> None:
        self.client = client
        self.wait_time = wait_time
        self.responses: list[tuple[str, bytes]] = []
        self._response_event = asyncio.Event()

    def _notification_handler(self, sender: object, data: bytearray) -> None:
        """Handle notifications from any characteristic."""
        log.info("  RESPONSE from {}: {}", sender, data.hex())
        self.responses.append((str(sender), bytes(data)))
        self._response_event.set()

    async def enable_all_notifications(self) -> list[str]:
        """Enable notifications on all notifiable characteristics."""
        enabled = []
        for service in self.client.services:
            for char in service.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    try:
                        await self.client.start_notify(
                            char.uuid, self._notification_handler
                        )
                        enabled.append(char.uuid[:8])
                        log.debug("Enabled notifications on {}", char.uuid[:8])
                    except Exception as e:
                        log.debug(
                            "Could not enable notifications on {}: {}", char.uuid[:8], e
                        )
        return enabled

    async def get_writable_characteristics(self) -> list[tuple[str, str, int]]:
        """Get list of (service_uuid, char_uuid, handle) for writable chars."""
        writable: list[tuple[str, str, int]] = []
        for service in self.client.services:
            for char in service.characteristics:
                if (
                    "write" in char.properties
                    or "write-without-response" in char.properties
                ):
                    writable.append((service.uuid, char.uuid, char.handle))
        return writable

    async def probe_command(
        self,
        char_uuid: str,
        command_hex: str,
        command_name: str,
    ) -> dict[str, object]:
        """Send a command and wait for response."""
        result: dict[str, object] = {
            "characteristic": char_uuid[:8],
            "command": command_name,
            "hex": command_hex,
            "success": False,
            "error": None,
            "response": None,
        }

        try:
            data = bytes.fromhex(command_hex)
        except ValueError as e:
            result["error"] = f"Invalid hex: {e}"
            return result

        self._response_event.clear()
        self.responses.clear()

        try:
            # Try write with response first, fall back to without
            try:
                await self.client.write_gatt_char(char_uuid, data, response=True)
            except Exception:
                await self.client.write_gatt_char(char_uuid, data, response=False)

            result["success"] = True
            log.info("  Sent {} to {} - OK", command_name, char_uuid[:8])

            # Wait for notification response
            try:
                await asyncio.wait_for(
                    self._response_event.wait(), timeout=self.wait_time
                )
                if self.responses:
                    result["response"] = [r[1].hex() for r in self.responses]
            except asyncio.TimeoutError:
                pass  # No response is fine

        except Exception as e:
            result["error"] = str(e)
            log.warning("  FAILED {} to {}: {}", command_name, char_uuid[:8], e)

        return result


async def main() -> None:
    setup_logging()
    args = _parse_args()

    if args.dry_run:
        log.info("DRY RUN - Commands that would be sent:")
        for name, cmd_hex, desc in TEST_COMMANDS:
            if args.command and args.command != name:
                continue
            log.info("  {} ({}): {}", name, desc, cmd_hex)
        return

    device = await _discover_device(
        target_name=args.name,
        target_address=args.address,
        timeout=args.timeout,
    )

    if not device:
        log.error("No device found. Use --name or --address.")
        return

    log.info("Connecting to {} ({})...", device.name, device.address)

    async with BleakClient(device) as client:
        log.info("Connected: {}", client.is_connected)

        prober = CharacteristicProber(client, wait_time=args.wait_response)

        # Enable all notifications first
        enabled = await prober.enable_all_notifications()
        log.info("Enabled notifications on {} characteristics", len(enabled))

        # Get writable characteristics
        writable = await prober.get_writable_characteristics()
        log.info("Found {} writable characteristics", len(writable))

        # Filter characteristics if specified
        if args.char:
            writable = [
                (s, c, h) for s, c, h in writable if args.char.lower() in c.lower()
            ]
            if not writable:
                log.error("No matching writable characteristic found for {}", args.char)
                return

        # Build command list
        if args.custom_hex:
            commands = [("custom", args.custom_hex, "Custom command")]
        else:
            commands = [
                (name, cmd_hex, desc)
                for name, cmd_hex, desc in TEST_COMMANDS
                if not args.command or args.command == name
            ]

        if not commands:
            log.error("No commands to test")
            return

        # Test each command on each writable characteristic
        results: list[dict] = []
        log.info("")
        log.info(
            "=== PROBING {} COMMANDS ON {} CHARACTERISTICS ===",
            len(commands),
            len(writable),
        )

        for service_uuid, char_uuid, handle in writable:
            log.info("")
            log.info(
                "Characteristic: {} (service {}, handle {})",
                char_uuid[:8],
                service_uuid[:8],
                handle,
            )

            for cmd_name, cmd_hex, cmd_desc in commands:
                result = await prober.probe_command(char_uuid, cmd_hex, cmd_name)
                result["service"] = service_uuid[:8]
                result["command_desc"] = cmd_desc
                results.append(result)

                # Small delay between commands
                await asyncio.sleep(0.1)

        # Summary
        log.info("")
        log.info("=== PROBE SUMMARY ===")
        successful = [r for r in results if r["success"]]
        with_response = [r for r in results if r.get("response")]

        log.info("Commands sent successfully: {}/{}", len(successful), len(results))
        log.info("Commands with responses: {}", len(with_response))

        if with_response:
            log.info("")
            log.info("COMMANDS THAT GOT RESPONSES (potential working commands):")
            for r in with_response:
                log.info(
                    "  {} -> {} ({}): response = {}",
                    r["service"],
                    r["characteristic"],
                    r["command"],
                    r["response"],
                )

        # Check for any errors that might indicate wrong characteristic
        errors = [r for r in results if r.get("error")]
        if errors:
            log.info("")
            log.info("Failed commands:")
            for r in errors:
                log.info(
                    "  {} -> {}: {}", r["characteristic"], r["command"], r["error"]
                )


if __name__ == "__main__":
    asyncio.run(main())
