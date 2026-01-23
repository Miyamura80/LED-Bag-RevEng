import argparse
import asyncio
import re
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bleak import BleakClient, BleakScanner
from loguru import logger as log

from src.utils.logging_config import setup_logging


WRITE_CHARACTERISTIC_UUID = "0000fec7-0000-1000-8000-00805f9b34fb"
DEFAULT_WIDTH = 96
DEFAULT_HEIGHT = 16
CHUNK_SIZE = 128

MODE_MAP = {
    "static": 0x01,
    "left": 0x02,
    "right": 0x03,
    "up": 0x04,
    "down": 0x05,
    "snowflake": 0x06,
    "picture": 0x07,
    "laser": 0x08,
}

SWITCH_MAP = {
    "off": 0x00,
    "on": 0x01,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a solid color frame to a CoolLED-style device",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Device name (substring match)",
    )
    parser.add_argument(
        "--address",
        type=str,
        default=None,
        help="Device address/UUID from BLE scan",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="#ff0000",
        help="Hex color, e.g. #ff0000",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Matrix width (pixels)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Matrix height (pixels)",
    )
    parser.add_argument(
        "--char-uuid",
        type=str,
        default=WRITE_CHARACTERISTIC_UUID,
        help="Write characteristic UUID",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Scan timeout in seconds",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.02,
        help="Delay between BLE writes (seconds)",
    )
    parser.add_argument(
        "--no-response",
        action="store_true",
        help="Write without waiting for response",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Send initialize command before frame",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=None,
        help="Optional brightness (0-255)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=sorted(MODE_MAP.keys()),
        default=None,
        help="Set display mode before sending the frame",
    )
    parser.add_argument(
        "--switch",
        type=str,
        choices=sorted(SWITCH_MAP.keys()),
        default=None,
        help="Switch display on/off before sending the frame",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Send the clear command (0x0D) before the frame",
    )
    return parser.parse_args()


def _parse_color(color: str) -> tuple[int, int, int]:
    raw = color.strip().lower()
    if raw.startswith("#"):
        raw = raw[1:]
    if raw.startswith("0x"):
        raw = raw[2:]

    if len(raw) == 3:
        raw = "".join([char * 2 for char in raw])

    if len(raw) != 6 or not re.fullmatch(r"[0-9a-f]{6}", raw):
        raise ValueError(f"Invalid color '{color}'. Use hex like #ff0000.")

    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    return red, green, blue


def _build_color_plane(width: int, height: int, is_on: bool) -> bytearray:
    if height % 8 != 0:
        raise ValueError("Height must be divisible by 8")

    bytes_per_column = height // 8
    value = 0xFF if is_on else 0x00

    plane = bytearray()
    for _ in range(width):
        for _ in range(bytes_per_column):
            plane.append(value)
    return plane


def build_solid_color_payload(width: int, height: int, color: str) -> bytearray:
    red, green, blue = _parse_color(color)

    red_plane = _build_color_plane(width, height, red >= 128)
    green_plane = _build_color_plane(width, height, green >= 128)
    blue_plane = _build_color_plane(width, height, blue >= 128)

    pixel_bits = red_plane + green_plane + blue_plane

    payload = bytearray(24)
    payload += len(pixel_bits).to_bytes(2, byteorder="big")
    payload += pixel_bits
    return payload


def _xor_checksum(data: bytearray) -> int:
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def _split_chunks(data: bytearray, chunk_size: int) -> list[bytearray]:
    chunks = [data]
    while True:
        last_index = len(chunks) - 1
        if len(chunks[last_index]) > chunk_size:
            chunks.append(chunks[last_index][chunk_size:])
            chunks[last_index] = chunks[last_index][:chunk_size]
        else:
            return chunks


def _build_payload_chunks(payload: bytearray, command_byte: int) -> list[bytearray]:
    raw_chunks = _split_chunks(payload, CHUNK_SIZE)
    formatted_chunks: list[bytearray] = []

    for chunk_id, raw_chunk in enumerate(raw_chunks):
        formatted_chunk = bytearray()
        formatted_chunk += b"\x00"
        formatted_chunk += len(payload).to_bytes(2, byteorder="big")
        formatted_chunk += chunk_id.to_bytes(2, byteorder="big")
        formatted_chunk += len(raw_chunk).to_bytes(1, byteorder="big")
        formatted_chunk += raw_chunk
        formatted_chunk.append(_xor_checksum(formatted_chunk))

        formatted_chunks.append(
            bytearray([command_byte]) + formatted_chunk,
        )

    return formatted_chunks


def _escape_bytes(data: bytearray) -> bytearray:
    escaped = bytes(data)
    escaped = escaped.replace(b"\x02", b"\x02\x06")
    escaped = escaped.replace(b"\x01", b"\x02\x05")
    escaped = escaped.replace(b"\x03", b"\x02\x07")
    return bytearray(escaped)


def encode_command(raw_chunk: bytearray) -> bytearray:
    extended = bytearray()
    extended += len(raw_chunk).to_bytes(2, byteorder="big")
    extended += raw_chunk
    escaped = _escape_bytes(extended)
    return bytearray().join([b"\x01", escaped, b"\x03"])


def build_image_command_chunks(
    *,
    width: int,
    height: int,
    color: str,
) -> list[bytearray]:
    payload = build_solid_color_payload(width, height, color)
    raw_chunks = _build_payload_chunks(payload, command_byte=0x03)
    return [encode_command(chunk) for chunk in raw_chunks]


def build_simple_command(
    command_byte: int,
    payload: bytes | bytearray | None = None,
) -> bytearray:
    raw = bytearray([command_byte])
    if payload:
        raw += payload
    return encode_command(raw)


async def _discover_target(
    *,
    name: str | None,
    address: str | None,
    timeout: float,
) -> tuple[str | None, int | None, int | None]:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

    for device, adv in devices.values():
        device_name = device.name or ""
        if address and device.address.lower() != address.lower():
            continue
        if name and name.lower() not in device_name.lower():
            continue
        height = None
        width = None
        if adv.manufacturer_data:
            value = next(iter(adv.manufacturer_data.values()))
            if len(value) >= 11:
                height = value[6]
                width = value[7] << 8 | value[8]
        return device.address, width, height

    return None, None, None


async def _send_frame(
    *,
    address: str,
    command_chunks: list[bytearray],
    char_uuid: str,
    delay: float,
    no_response: bool,
) -> None:
    async with BleakClient(address) as client:
        log.info("Connected: {}", client.is_connected)
        for index, chunk in enumerate(command_chunks, start=1):
            log.info("Sending chunk {}/{} ({} bytes)", index, len(command_chunks), len(chunk))
            await client.write_gatt_char(
                char_uuid,
                chunk,
                response=not no_response,
            )
            if delay > 0:
                await asyncio.sleep(delay)


async def main() -> None:
    setup_logging()
    args = _parse_args()

    address = args.address
    width = args.width
    height = args.height

    if not address:
        log.info("Scanning for device...")
        address, detected_width, detected_height = await _discover_target(
            name=args.name,
            address=args.address,
            timeout=args.timeout,
        )
        if address is None:
            log.error("Device not found. Provide --name or --address.")
            sys.exit(1)
        if width is None and detected_width:
            width = detected_width
        if height is None and detected_height:
            height = detected_height

    if width is None:
        width = DEFAULT_WIDTH
    if height is None:
        height = DEFAULT_HEIGHT

    log.info("Using matrix size: {}x{}", width, height)
    log.info("Using color: {}", args.color)

    command_chunks: list[bytearray] = []

    if args.init:
        command_chunks.append(build_simple_command(0x23, bytearray([0x01])))

    if args.switch:
        command_chunks.append(
            build_simple_command(0x09, bytearray([SWITCH_MAP[args.switch]])),
        )

    if args.mode:
        command_chunks.append(
            build_simple_command(0x06, bytearray([MODE_MAP[args.mode]])),
        )

    if args.clear:
        command_chunks.append(build_simple_command(0x0D))

    if args.brightness is not None:
        if args.brightness < 0 or args.brightness > 255:
            raise ValueError("Brightness must be 0-255")
        command_chunks.append(
            build_simple_command(0x08, bytearray([args.brightness])),
        )

    command_chunks.extend(
        build_image_command_chunks(
            width=width,
            height=height,
            color=args.color,
        ),
    )

    await _send_frame(
        address=address,
        command_chunks=command_chunks,
        char_uuid=args.char_uuid,
        delay=args.delay,
        no_response=args.no_response,
    )


if __name__ == "__main__":
    asyncio.run(main())
