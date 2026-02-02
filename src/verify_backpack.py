"""
Scan and verify LOY SPACE LED backpack BLE connection.

Enumerates all GATT services and characteristics with detailed info about
writable characteristics that may support graffiti/direct pixel control.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic
from loguru import logger as log

from src.led_protocol import SERVICE_UUID as LOY_SPACE_SERVICE_UUID
from src.utils.logging_config import setup_logging

# Service UUIDs we consider a match when no --name/--address given
COOLLED_SERVICE_UUID = "0000fee7-0000-1000-8000-00805f9b34fb"

# Known service UUIDs and their purposes
KNOWN_SERVICES: dict[str, str] = {
    "0000fff0": "LOY SPACE main control (GIF upload)",
    "0000fee7": "CoolLED / alternate control",
    "0000ffd0": "Merkury graffiti mode (direct pixel)",
    "0000ffe0": "ISSC transparent UART",
    "0000ff00": "Generic LED control",
    "0000ff10": "LED status/config",
    "0000eee0": "Unknown LED service",
    "0000ff80": "Nordic UART-like",
}

# Known characteristic UUIDs and their purposes
KNOWN_CHARS: dict[str, str] = {
    "0000fff1": "Notify (ack/responses)",
    "0000fff2": "Write (GIF upload commands)",
    "0000ffd1": "Merkury graffiti write",
    "0000ffe1": "ISSC UART TX/RX",
}


@dataclass
class CharacteristicInfo:
    """Information about a discovered characteristic."""

    uuid: str
    handle: int
    properties: list[str]
    service_uuid: str
    is_writable: bool
    is_notifiable: bool
    description: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan for LED backpack and enumerate all GATT services/characteristics",
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
        "--include-unknown",
        action="store_true",
        help="Include unnamed devices in the candidate list",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for programmatic use",
    )
    return parser.parse_args()


def _matches_target(
    *,
    device_name: str,
    device_address: str,
    target_name: str | None,
    target_address: str | None,
) -> bool:
    if target_address:
        if device_address.lower() == target_address.lower():
            return True

    if target_name:
        if target_name.lower() in device_name.lower():
            return True

    return False


async def _discover_target(
    *,
    target_name: str | None,
    target_address: str | None,
    timeout: float,
    include_unknown: bool,
) -> tuple[BLEDevice | None, dict[str, list[str]]]:
    log.info("Scanning for BLE devices (disconnect other apps, power the bag on)")
    devices_dict = await BleakScanner.discover(timeout=timeout, return_adv=True)

    target_device = None
    candidates: dict[str, list[str]] = {}

    for _key, (device, adv) in devices_dict.items():
        device_name = device.name or "<Unknown>"
        service_uuids = adv.service_uuids or []

        if _matches_target(
            device_name=device_name,
            device_address=device.address,
            target_name=target_name,
            target_address=target_address,
        ):
            log.info(
                "Matched target {} ({})",
                device_name,
                device.address,
            )
            target_device = device
            break

        if not target_name and not target_address:
            # LOY SPACE app uses 0xFFF0; some devices also advertise 0xFEE7
            if (
                LOY_SPACE_SERVICE_UUID.lower() in [u.lower() for u in service_uuids]
                or COOLLED_SERVICE_UUID in service_uuids
            ):
                log.info(
                    "Matched service UUID on {} ({})",
                    device_name,
                    device.address,
                )
                target_device = device
                break

        if device.name or service_uuids or include_unknown:
            candidates[f"{device_name} [{device.address}]"] = service_uuids

    return target_device, candidates


def _get_service_description(uuid: str) -> str:
    """Get human-readable description for a service UUID."""
    short = uuid[:8].lower()
    if short in KNOWN_SERVICES:
        return KNOWN_SERVICES[short]
    return ""


def _get_char_description(uuid: str) -> str:
    """Get human-readable description for a characteristic UUID."""
    short = uuid[:8].lower()
    if short in KNOWN_CHARS:
        return KNOWN_CHARS[short]
    return ""


def _analyze_characteristic(
    char: BleakGATTCharacteristic, service_uuid: str
) -> CharacteristicInfo:
    """Extract detailed info from a characteristic."""
    props = [str(p) for p in char.properties]
    is_writable = "write" in props or "write-without-response" in props
    is_notifiable = "notify" in props or "indicate" in props

    known_desc = _get_char_description(char.uuid)
    if known_desc:
        desc = known_desc
    elif is_writable and is_notifiable:
        desc = "Read/Write/Notify (potential control)"
    elif is_writable:
        desc = "Write-only (potential command target)"
    elif is_notifiable:
        desc = "Notify-only (responses/status)"
    else:
        desc = ""

    return CharacteristicInfo(
        uuid=char.uuid,
        handle=char.handle,
        properties=props,
        service_uuid=service_uuid,
        is_writable=is_writable,
        is_notifiable=is_notifiable,
        description=desc,
    )


async def _describe_device(
    device_address: str, as_json: bool = False
) -> dict[str, object]:
    """
    Connect to device and enumerate all GATT services/characteristics.

    Returns a dict with service and characteristic details.
    """
    log.info("Connecting to {}", device_address)
    result: dict[str, object] = {
        "address": device_address,
        "services": [],
        "writable_chars": [],
        "notifiable_chars": [],
        "graffiti_candidates": [],
    }

    async with BleakClient(device_address) as client:
        log.info("Connected: {}", client.is_connected)

        for service in client.services:
            service_desc = _get_service_description(service.uuid)
            service_info = {
                "uuid": service.uuid,
                "short": service.uuid[:8],
                "description": service_desc or service.description,
                "characteristics": [],
            }

            # Check if this is a potential graffiti service
            is_graffiti_service = service.uuid[:8].lower() in ("0000ffd0", "0000ffe0")

            if service_desc:
                log.info("[Service] {} - {}", service.uuid[:8], service_desc)
            else:
                log.info("[Service] {} ({})", service.uuid[:8], service.description)

            for char in service.characteristics:
                char_info = _analyze_characteristic(char, service.uuid)
                service_info["characteristics"].append(
                    {
                        "uuid": char_info.uuid,
                        "short": char_info.uuid[:8],
                        "handle": char_info.handle,
                        "properties": char_info.properties,
                        "is_writable": char_info.is_writable,
                        "is_notifiable": char_info.is_notifiable,
                        "description": char_info.description,
                    }
                )

                props_str = ", ".join(char_info.properties)
                if char_info.description:
                    log.info(
                        "  -> {} [{}] - {}",
                        char_info.uuid[:8],
                        props_str,
                        char_info.description,
                    )
                else:
                    log.info("  -> {} [{}]", char_info.uuid[:8], props_str)

                if char_info.is_writable:
                    result["writable_chars"].append(
                        {
                            "service": service.uuid[:8],
                            "char": char_info.uuid,
                            "handle": char_info.handle,
                            "description": char_info.description,
                        }
                    )

                    # Check if this could be a graffiti mode characteristic
                    if is_graffiti_service or char_info.uuid[:8].lower() in (
                        "0000ffd1",
                        "0000ffe1",
                    ):
                        result["graffiti_candidates"].append(
                            {
                                "service": service.uuid,
                                "char": char_info.uuid,
                                "handle": char_info.handle,
                            }
                        )
                        log.info("     *** GRAFFITI MODE CANDIDATE ***")

                if char_info.is_notifiable:
                    result["notifiable_chars"].append(
                        {
                            "service": service.uuid[:8],
                            "char": char_info.uuid,
                            "handle": char_info.handle,
                        }
                    )

            result["services"].append(service_info)

        # Summary
        log.info("")
        log.info("=== SUMMARY ===")
        log.info("Total services: {}", len(result["services"]))
        log.info("Writable characteristics: {}", len(result["writable_chars"]))
        log.info("Notifiable characteristics: {}", len(result["notifiable_chars"]))

        if result["writable_chars"]:
            log.info("")
            log.info("All writable characteristics (potential command targets):")
            for wc in result["writable_chars"]:
                desc = f" - {wc['description']}" if wc["description"] else ""
                log.info(
                    "  {} -> {} (handle {}){}",
                    wc["service"],
                    wc["char"][:8],
                    wc["handle"],
                    desc,
                )

        if result["graffiti_candidates"]:
            log.info("")
            log.info("GRAFFITI MODE CANDIDATES (try BC-style commands):")
            for gc in result["graffiti_candidates"]:
                log.info("  {} -> {}", gc["service"][:8], gc["char"][:8])

        if as_json:
            import json

            print(json.dumps(result, indent=2))

    return result


async def main() -> None:
    setup_logging()
    args = _parse_args()

    if not args.name and not args.address:
        log.info("No name/address provided. Will match by service UUID if advertised.")

    target_device, candidates = await _discover_target(
        target_name=args.name,
        target_address=args.address,
        timeout=args.timeout,
        include_unknown=args.include_unknown,
    )

    if not target_device:
        log.warning("No matching device found.")
        if candidates:
            log.info("Candidates seen during scan:")
            for label, uuids in candidates.items():
                if uuids:
                    log.info("  - {} (UUIDs: {})", label, uuids)
                else:
                    log.info("  - {}", label)
        log.info("Try again with --name or --address.")
        sys.exit(1)

    await _describe_device(target_device.address, as_json=args.json)


async def get_device_info(
    *,
    name: str | None = None,
    address: str | None = None,
    timeout: float = 10.0,
) -> dict[str, object] | None:
    """
    Programmatic API to get device info.

    Returns dict with services, writable_chars, graffiti_candidates, or None.
    """
    target_device, _ = await _discover_target(
        target_name=name,
        target_address=address,
        timeout=timeout,
        include_unknown=False,
    )

    if not target_device:
        return None

    return await _describe_device(target_device.address, as_json=False)


if __name__ == "__main__":
    asyncio.run(main())
