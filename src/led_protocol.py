"""
LOY SPACE LED backpack BLE protocol.

Uses the YS-protocol (aa55ffff magic header) based on reverse engineering of
similar YS-prefixed LED matrix devices. See docs/protocol.md for details.

Reference: https://github.com/mtpiercey/ble-led-matrix-controller
"""

import io
import re

from PIL import Image

# BLE service and characteristics (from APK)
SERVICE_UUID = "0000FFF0-0000-1000-8000-00805F9B34FB"
WRITE_CHAR_UUID = "0000FFF2-0000-1000-8000-00805F9B34FB"
NOTIFY_CHAR_UUID = "0000FFF1-0000-1000-8000-00805F9B34FB"

# Default display size (96x128 from device specs)
DEFAULT_WIDTH = 96
DEFAULT_HEIGHT = 128

# YS-protocol uses 196-byte payload chunks for GIF data (392 hex chars)
DEFAULT_CHUNK_SIZE = 196

# Magic header for YS-protocol
MAGIC_HEADER = bytes.fromhex("aa55ffff")

# Known command packets (from similar YS devices)
CMD_RESET = bytes.fromhex("aa55ffff0a000900c102080200ffdc04")
CMD_READY = bytes.fromhex("aa55ffff0a000900c10208020000dd03")
CMD_UPLOAD_COMPLETE = bytes.fromhex("aa55ffff0b000f00c10236030100001404")

# Brightness levels (0-15)
BRIGHTNESS_LEVELS = 16


def _checksum_mod256(hex_string: str) -> str:
    """Calculate CheckSum8 Mod 256 of hex string, return as 2-char hex."""
    total = sum(int(hex_string[i : i + 2], 16) for i in range(0, len(hex_string), 2))
    return f"{total % 256:02X}"


def _high_byte_sum(hex_string: str) -> str:
    """Calculate high byte of total sum, return as 2-char hex."""
    # Sum all bytes except the last one (which is the first checksum)
    data_bytes = [
        int(hex_string[i : i + 2], 16) for i in range(0, len(hex_string) - 2, 2)
    ]
    total_sum = sum(data_bytes)
    return f"{total_sum // 256:02X}"


def _parse_color(color: str) -> tuple[int, int, int]:
    """Parse hex color string to (R, G, B) tuple."""
    raw = color.strip().lower()
    if raw.startswith("#"):
        raw = raw[1:]
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) == 3:
        raw = "".join([c * 2 for c in raw])
    if len(raw) != 6 or not re.fullmatch(r"[0-9a-f]{6}", raw):
        raise ValueError(f"Invalid color '{color}'. Use hex like #ff0000.")
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    return r, g, b


def build_brightness_command(level: int) -> bytearray:
    """
    Build brightness command packet.

    Args:
        level: Brightness level 0-15.

    Returns:
        Complete packet with checksums.
    """
    if level < 0 or level >= BRIGHTNESS_LEVELS:
        raise ValueError(f"Brightness must be 0-{BRIGHTNESS_LEVELS - 1}")

    # Base packet without checksum bytes
    base = bytearray(
        [
            0xAA,
            0x55,
            0xFF,
            0xFF,  # Magic header
            0x0A,
            0x00,
            0x04,
            0x00,  # Length and index
            0xC1,
            0x02,
            0x06,
            0x02,  # Command header
            0x00,  # Padding
            level,  # Brightness level
        ]
    )

    # Calculate checksums
    checksum = (sum(base) + 0xD6 - sum(base[:14]) + sum(base)) % 256
    # Simplified: the reference shows checksum = 0xD6 + brightness
    checksum = (0xD6 + level) % 256
    base.append(checksum)
    base.append(0x03)  # Trailer

    return base


def build_reset_command() -> bytearray:
    """Build reset/clear storage command."""
    return bytearray(CMD_RESET)


def build_ready_command() -> bytearray:
    """Build ready for upload command."""
    return bytearray(CMD_READY)


def build_upload_complete_command() -> bytearray:
    """Build upload complete command."""
    return bytearray(CMD_UPLOAD_COMPLETE)


def _generate_header(payload_hex: str, index: int, total_packets: int) -> str:
    """
    Generate packet header as hex string.

    Based on reference implementation from ble-led-matrix-controller.
    """
    # Magic header
    header = "aa55ffff"

    # Length byte: payload_bytes + 41
    # payload_hex is hex string, so len/2 gives bytes
    length = len(payload_hex) // 2 + 41
    header += f"{length:02x}"

    # Packet index: 000000, 000100, 000200, etc.
    header += f"{index:04x}00"

    # Constant command header (27 bytes = 54 hex chars)
    header += "c1020901010c01000d01000e0100140301090a11040001000a1207"

    # Total number of packets (1 byte, max 255)
    header += f"{min(total_packets, 255):02x}"

    # Packet index again
    header += f"{index:04x}00"

    # Constant
    header += "c4000013"

    # Payload length indicator (81c4 for full 196-byte payload)
    header += "81c4"

    return header


def _build_gif_packet_hex(
    payload_hex: str,
    packet_index: int,
    total_packets: int,
) -> str:
    """
    Build a single GIF data packet as hex string.

    Args:
        payload_hex: GIF data chunk as hex string (up to 392 chars = 196 bytes).
        packet_index: 0-based index of this packet.
        total_packets: Total number of packets being sent.

    Returns:
        Complete packet as hex string.
    """
    # Pad payload to 392 hex chars (196 bytes) if needed
    padded_payload = payload_hex.ljust(392, "0")

    # Build header
    header = _generate_header(padded_payload, packet_index, total_packets)

    # Combine header and payload
    full_value = header + padded_payload

    # First checksum: mod 256
    checksum1 = _checksum_mod256(full_value)
    full_value = full_value + checksum1

    # Second checksum: high byte of sum
    checksum2 = _high_byte_sum(full_value)
    full_value = full_value + checksum2

    return full_value


def build_gif_upload_packets(gif_data: bytes | bytearray) -> list[bytearray]:
    """
    Build all packets needed to upload a GIF.

    Args:
        gif_data: Raw GIF file data.

    Returns:
        List of packets: [reset, ready, data_packets..., complete, complete].
    """
    packets: list[bytearray] = []

    # Reset and ready commands
    packets.append(build_reset_command())
    packets.append(build_ready_command())

    # Convert GIF to hex string
    gif_hex = gif_data.hex()

    # Split into 392-char chunks (196 bytes each)
    chunk_size = 392  # hex chars
    chunks: list[str] = []
    for i in range(0, len(gif_hex), chunk_size):
        chunks.append(gif_hex[i : i + chunk_size])

    # Build data packets
    total_packets = len(chunks)
    for i, chunk in enumerate(chunks):
        packet_hex = _build_gif_packet_hex(chunk, i, total_packets)
        packets.append(bytearray.fromhex(packet_hex))

    # Upload complete (sent twice per protocol)
    packets.append(build_upload_complete_command())
    packets.append(build_upload_complete_command())

    return packets


def build_solid_color_gif(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    color: str = "#ff0000",
) -> bytes:
    """
    Build a GIF with a solid color using Pillow for proper encoding.

    Args:
        width: Display width in pixels.
        height: Display height in pixels.
        color: Hex color string (e.g., "#ff0000").

    Returns:
        Raw GIF bytes.
    """
    r, g, b = _parse_color(color)

    # Create paletted image
    img = Image.new("P", (width, height))

    # Set palette with our color as index 0
    palette = [r, g, b, 0, 0, 0]  # Color 0: our color, Color 1: black
    palette.extend([0] * (256 * 3 - len(palette)))
    img.putpalette(palette)

    # Fill with color index 0
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = 0

    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


def build_solid_color_packets(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    color: str = "#ff0000",
) -> list[bytearray]:
    """
    Build all packets to display a solid color.

    Args:
        width: Display width in pixels.
        height: Display height in pixels.
        color: Hex color string.

    Returns:
        List of packets ready to send.
    """
    gif_data = build_solid_color_gif(width, height, color)
    return build_gif_upload_packets(gif_data)


def build_grid_pattern_gif(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    grid_size: int = 8,
    color1: str = "#ffffff",
    color2: str = "#000000",
) -> bytes:
    """
    Build a GIF with a checkerboard/grid pattern using Pillow.

    Args:
        width: Display width in pixels.
        height: Display height in pixels.
        grid_size: Size of each grid cell in pixels.
        color1: First color (hex string).
        color2: Second color (hex string).

    Returns:
        Raw GIF bytes.
    """
    r1, g1, b1 = _parse_color(color1)
    r2, g2, b2 = _parse_color(color2)

    # Create paletted image
    img = Image.new("P", (width, height))

    # Set palette
    palette = [r1, g1, b1, r2, g2, b2]
    palette.extend([0] * (256 * 3 - len(palette)))
    img.putpalette(palette)

    # Draw checkerboard pattern
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            cell_x = x // grid_size
            cell_y = y // grid_size
            color_idx = (cell_x + cell_y) % 2
            pixels[x, y] = color_idx

    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    return buf.getvalue()


def build_grid_pattern_packets(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    grid_size: int = 8,
    color1: str = "#ffffff",
    color2: str = "#000000",
) -> list[bytearray]:
    """
    Build all packets to display a grid/checkerboard pattern.

    Args:
        width: Display width in pixels.
        height: Display height in pixels.
        grid_size: Size of each grid cell in pixels.
        color1: First color (hex string).
        color2: Second color (hex string).

    Returns:
        List of packets ready to send.
    """
    gif_data = build_grid_pattern_gif(width, height, grid_size, color1, color2)
    return build_gif_upload_packets(gif_data)


# Legacy exports for backwards compatibility
CMD_INIT = 0x23
CMD_SWITCH = 0x09
CMD_MODE = 0x06
CMD_CLEAR = 0x0D
CMD_BRIGHTNESS = 0x08

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


# Legacy function stubs for backwards compatibility
def encode_command(raw: bytearray) -> bytearray:
    """Legacy: wrap in YS-protocol packet (simplified)."""
    packet_hex = MAGIC_HEADER.hex() + raw.hex()
    checksum1 = _checksum_mod256(packet_hex)
    packet_hex += checksum1
    checksum2 = _high_byte_sum(packet_hex)
    packet_hex += checksum2
    return bytearray.fromhex(packet_hex)


def build_simple_command(
    command_byte: int,
    payload: bytes | bytearray | None = None,
) -> bytearray:
    """Legacy: build a simple command packet."""
    if command_byte == CMD_CLEAR:
        return build_reset_command()
    if command_byte == CMD_BRIGHTNESS and payload:
        level = payload[0] * BRIGHTNESS_LEVELS // 256
        return build_brightness_command(level)
    # Default: wrap in basic packet
    raw = bytearray([command_byte])
    if payload:
        raw.extend(payload)
    return encode_command(raw)


def build_image_command_chunks(
    *,
    width: int,
    height: int,
    color: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[bytearray]:
    """Legacy: build image upload chunks using new protocol."""
    return build_solid_color_packets(width, height, color)
