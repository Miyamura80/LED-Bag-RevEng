import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from loguru import logger as log

from src.led_protocol import SERVICE_UUID as LOY_SPACE_SERVICE_UUID
from src.utils.logging_config import setup_logging

# Service UUIDs we consider a match when no --name/--address given
COOLLED_SERVICE_UUID = "0000fee7-0000-1000-8000-00805f9b34fb"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan for LED backpack and list GATT services",
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


async def _describe_device(device_address: str) -> None:
    log.info("Connecting to {}", device_address)
    async with BleakClient(device_address) as client:
        log.info("Connected: {}", client.is_connected)

        write_candidates: list[str] = []

        for service in client.services:
            log.info("[Service] {} ({})", service.uuid, service.description)
            for char in service.characteristics:
                props = ", ".join(char.properties)
                log.info("  -> [Char] {} ({})", char.uuid, props)

                if (
                    "write" in char.properties
                    or "write-without-response" in char.properties
                ):
                    write_candidates.append(f"{service.uuid} -> {char.uuid}")
                    if service.uuid.lower() in (
                        COOLLED_SERVICE_UUID.lower(),
                        LOY_SPACE_SERVICE_UUID.lower(),
                    ):
                        log.info("     *** Candidate write characteristic ***")

        if write_candidates:
            log.info("Write characteristics found:")
            for entry in write_candidates:
                log.info("  - {}", entry)


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

    await _describe_device(target_device.address)


if __name__ == "__main__":
    asyncio.run(main())
