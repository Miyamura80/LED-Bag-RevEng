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
# Tested: Larger chunks (256, 384, 462) do NOT work on this device
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


# =============================================================================
# GRAFFITI MODE COMMANDS (Merkury-style, BC-prefix)
# These are experimental - may work on some YS devices that share firmware
# =============================================================================

# Merkury graffiti mode uses service 0xFFD0, characteristic 0xFFD1
# Some devices may also support these on 0xFFF2 or 0xFFE1
GRAFFITI_SERVICE_UUID = "0000FFD0-0000-1000-8000-00805F9B34FB"
GRAFFITI_CHAR_UUID = "0000FFD1-0000-1000-8000-00805F9B34FB"

# Graffiti mode command packets (BC-style)
GRAFFITI_POWER_ON = bytes.fromhex("bcff010055")
GRAFFITI_POWER_OFF = bytes.fromhex("bcff00ff55")
GRAFFITI_MODE_START = bytes.fromhex("bc00010155")
GRAFFITI_MODE_ENABLE = bytes.fromhex("bc000d0d55")
GRAFFITI_SLIDESHOW = bytes.fromhex("bc00121255")


def build_graffiti_init_sequence() -> list[bytearray]:
    """
    Build the initialization sequence for graffiti mode.

    Send these commands to enter direct pixel control mode.
    Returns list of packets to send in order.
    """
    return [
        bytearray(GRAFFITI_MODE_START),
        bytearray(GRAFFITI_MODE_ENABLE),
    ]


def build_graffiti_pixel_command(
    pixel_index: int,
    r: int,
    g: int,
    b: int,
) -> bytearray:
    """
    Build command to set a single pixel in graffiti mode.

    Args:
        pixel_index: Pixel position (0-255 for 16x16, 0-12287 for 96x128).
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).

    Returns:
        10-byte command packet.

    Note:
        For displays larger than 16x16, pixel addressing may differ.
        The Merkury protocol uses: BC 01 01 00 PP RR GG BB QQ 55
        where PP is pixel index and QQ is (pixel_index + 1) % 256.
    """
    # Clamp values
    pixel_index = pixel_index % 256
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    # End index calculation (Merkury style)
    end_index = (pixel_index + 1) % 256
    if pixel_index == 0:
        end_index = 0xFF

    return bytearray(
        [
            0xBC,
            0x01,
            0x01,
            0x00,
            pixel_index,
            r,
            g,
            b,
            end_index,
            0x55,
        ]
    )


def build_graffiti_pixel_batch(
    pixels: list[tuple[int, int, int, int]],
) -> list[bytearray]:
    """
    Build commands for multiple pixels.

    Args:
        pixels: List of (pixel_index, r, g, b) tuples.

    Returns:
        List of command packets.
    """
    return [build_graffiti_pixel_command(idx, r, g, b) for idx, r, g, b in pixels]


def build_graffiti_fill_command(
    r: int, g: int, b: int, count: int = 256
) -> list[bytearray]:
    """
    Build commands to fill all pixels with one color.

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).
        count: Number of pixels (default 256 for 16x16).

    Returns:
        List of command packets (one per pixel).
    """
    return [build_graffiti_pixel_command(i, r, g, b) for i in range(count)]


# =============================================================================
# Program Playback Control Commands - DISCOVERED FROM APK DECOMPILATION
# =============================================================================
#
# The pgm_play command controls program playback (stop, play, etc.)
# This is needed before rt_draw commands will be visible.
#
# Command index: 12 (pgm_play in command table)
#

PGM_PLAY_CMD_INDEX = 12


def build_pgm_play_stop(sno: int = 0) -> bytearray:
    """
    Build command to stop program playback.

    This should be called before rt_draw commands to make them visible.
    The device plays stored GIFs by default; this stops that playback.

    Args:
        sno: Sequence number (optional).

    Returns:
        Complete packet ready to send via BLE.
    """
    # pgm_play payload: [54, len, model, index]
    # model=0 seems to be stop/pause, index=255 is default
    payload = bytearray([54, 2, 0, 255])

    return _build_ys_command_packet(payload, PGM_PLAY_CMD_INDEX, sno)


def _build_ys_command_packet(payload: bytes, cmd_index: int, sno: int = 0) -> bytearray:
    """
    Build a generic YS-protocol command packet.

    Args:
        payload: Command-specific payload bytes.
        cmd_index: Command index in the YS command table.
        sno: Sequence number.

    Returns:
        Complete packet ready to send via BLE.
    """
    # Calculate lengths
    inner_len = len(payload) + 4  # +4 for sno(2) + flags(1) + cmd_idx(1)
    c = 10 + len(payload) + 2  # header(10) + payload + checksums(2)

    packet = bytearray()

    # Length prefix (2 bytes, little-endian)
    packet.extend([c & 0xFF, (c >> 8) & 0xFF])

    # Magic header: 0xAA55 0xFFFF
    packet.extend([0xAA, 0x55, 0xFF, 0xFF])

    # Payload length + 4 (2 bytes, little-endian)
    packet.extend([inner_len & 0xFF, (inner_len >> 8) & 0xFF])

    # Sequence number (2 bytes, little-endian)
    packet.extend([sno & 0xFF, (sno >> 8) & 0xFF])

    # Command flags: 193 (0xC1) with checksum
    packet.append(0xC1)

    # Command index
    packet.append(cmd_index)

    # Payload
    packet.extend(payload)

    # Checksum: 16-bit sum of bytes from offset 2 (after length prefix)
    checksum = sum(packet[2:]) & 0xFFFF
    packet.extend([checksum & 0xFF, (checksum >> 8) & 0xFF])

    return packet


# =============================================================================
# Game Mode Command - Required before rt_draw
# =============================================================================
#
# The game command (index 31) with id=16 enters "graffiti mode" which stops
# the default idle animation and allows rt_draw commands to appear on a
# clean black background.
#
# Command payload: [0x30, 0x01, id+128] where id=16 for graffiti mode
#

GAME_CMD_BYTE = 0x02  # Command byte for game (w=2 in ye function)


def build_game_mode(game_id: int = 16) -> bytearray:
    """
    Build game command to enter drawing/graffiti mode.

    Args:
        game_id: Game mode ID. 16 = graffiti/drawing mode.

    Returns:
        Complete packet ready to send via BLE.
    """
    # Payload from case 31 in ye(): [48, 1, id+128]
    payload = bytes([0x30, 0x01, game_id + 128])

    length = len(payload) + 6
    packet = bytearray()
    packet.extend([0xAA, 0x55, 0xFF, 0xFF])
    packet.append(length)
    packet.extend([0x00, 0x00, 0x00])
    packet.append(0xC1)
    packet.append(GAME_CMD_BYTE)
    packet.extend(payload)

    checksum1 = sum(packet) % 256
    checksum2 = sum(packet) // 256 % 256
    packet.extend([checksum1, checksum2])

    return packet


# =============================================================================
# Real-Time Draw (rt_draw) Commands - DISCOVERED FROM APK DECOMPILATION
# =============================================================================
#
# The rt_draw command allows real-time pixel drawing without uploading a full GIF.
# This is used by the "涂鸦" (graffiti/doodle) feature in the LOY SPACE app.
#
# IMPORTANT: Send build_game_mode(16) first to enter graffiti mode and stop
# the default idle animation.
#
# Command index: 32
# Packet header: 0x2A 0xBE (bytes 42, 190)
#

# rt_draw command constants
# Note: The internal case number is 32, but the actual command byte sent is 2
# This matches how ye() function works: w=2 is default and unchanged for rt_draw
RT_DRAW_CMD_BYTE = 2  # The actual byte sent in packet (w value from ye function)
RT_DRAW_TYPE_RAW = 0  # Raw pixel data in rectangle
RT_DRAW_TYPE_RECT = 1  # Fill rectangle with color
RT_DRAW_TYPE_PIXELS = 16  # Draw pixels at coordinates


def _rgb_to_color_int(r: int, g: int, b: int) -> int:
    """Convert RGB to 24-bit color integer (R + G<<8 + B<<16)."""
    return r + (g << 8) + (b << 16)


def _color_int_to_bytes(color: int) -> bytes:
    """Convert 24-bit color int to 3 bytes (R, G, B)."""
    return bytes([color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF])


def _build_rt_draw_packet(payload: bytes, sno: int = 0) -> bytearray:
    """
    Wrap rt_draw payload in YS-protocol packet.

    Packet structure (CMD_RESET style - verified working):
    - 4 bytes: magic 0xAA55FFFF
    - 1 byte: length (payload + 6)
    - 2 bytes: index (little-endian), can be 0
    - 1 byte: padding (0x00)
    - 1 byte: command flags (0xC1)
    - 1 byte: command index (0x02 for rt_draw)
    - N bytes: payload
    - 2 bytes: checksum (mod256 + highbyte of sum)
    """
    # Length byte = payload_len + 6 (matching CMD_RESET pattern)
    length = len(payload) + 6

    packet = bytearray()

    # Magic header
    packet.extend([0xAA, 0x55, 0xFF, 0xFF])

    # 1-byte length
    packet.append(length & 0xFF)

    # 2-byte index (LE) + 1-byte padding
    packet.extend([sno & 0xFF, (sno >> 8) & 0xFF, 0x00])

    # Command flags and index
    packet.append(0xC1)
    packet.append(RT_DRAW_CMD_BYTE)

    # Payload
    packet.extend(payload)

    # Checksum: mod256 + highbyte
    checksum1 = sum(packet) % 256
    checksum2 = sum(packet) // 256 % 256
    packet.extend([checksum1, checksum2])

    return packet


def build_rt_draw_fill_rect(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    r: int = 0,
    g: int = 0,
    b: int = 0,
    sno: int = 0,
) -> bytearray:
    """
    Build rt_draw command to fill a rectangle with a solid color.

    This can be used to clear the screen (fill with black) or draw solid rectangles.

    Args:
        x0, y0: Top-left corner coordinates.
        x1, y1: Bottom-right corner coordinates.
        r, g, b: RGB color values (0-255). Default is black (0, 0, 0).
        sno: Sequence number (optional).

    Returns:
        Complete packet ready to send via BLE.

    Example:
        # Clear screen to black (96x128 display)
        packet = build_rt_draw_fill_rect(0, 0, 95, 127)

        # Draw red rectangle
        packet = build_rt_draw_fill_rect(10, 10, 50, 50, r=255)
    """
    color = _rgb_to_color_int(r, g, b)

    # Type 1 payload: [50, 13, 1, R, G, B, type_rect, x0_lo, x0_hi, ...]
    payload = bytearray(15)
    payload[0] = 50  # TLV tag
    payload[1] = 13  # Length
    payload[2] = RT_DRAW_TYPE_RECT  # Type 1 = fill rect
    payload[3:6] = _color_int_to_bytes(color)
    payload[6] = 0  # type_rect = 0 (fill)
    payload[7] = x0 & 0xFF
    payload[8] = (x0 >> 8) & 0xFF
    payload[9] = y0 & 0xFF
    payload[10] = (y0 >> 8) & 0xFF
    payload[11] = x1 & 0xFF
    payload[12] = (x1 >> 8) & 0xFF
    payload[13] = y1 & 0xFF
    payload[14] = (y1 >> 8) & 0xFF

    return _build_rt_draw_packet(bytes(payload), sno)


def build_rt_draw_clear_screen(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    sno: int = 0,
) -> bytearray:
    """
    Build rt_draw command to clear the screen (fill with black).

    Args:
        width: Screen width (default 96).
        height: Screen height (default 128).
        sno: Sequence number (optional).

    Returns:
        Complete packet ready to send via BLE.
    """
    return build_rt_draw_fill_rect(0, 0, width - 1, height - 1, sno=sno)


def _encode_length(length: int) -> bytes:
    """Encode length using variable-length encoding (protobuf-style)."""
    if length < 128:
        return bytes([length])
    elif length < 16384:
        return bytes([0x80 | (length & 0x7F), (length >> 7) & 0x7F])
    else:
        return bytes(
            [
                0x80 | (length & 0x7F),
                0x80 | ((length >> 7) & 0x7F),
                (length >> 14) & 0x7F,
            ]
        )


def build_rt_draw_bitmap(
    x0: int,
    y0: int,
    width: int,
    height: int,
    bitmap: list[list[int]],
    r: int = 255,
    g: int = 255,
    b: int = 255,
    sno: int = 0,
) -> bytearray:
    """
    Build rt_draw command with bitmap data (type 0).

    This sends a rectangular region with 1-bit-per-pixel data, which is much
    faster than sending individual pixels or rectangles.

    Args:
        x0, y0: Top-left corner coordinates.
        width: Width of the bitmap region.
        height: Height of the bitmap region.
        bitmap: 2D list of pixel values (0 = off, 1 = on). [row][col] format.
        r, g, b: RGB color for "on" pixels.
        sno: Sequence number.

    Returns:
        Complete packet ready to send via BLE.

    Example:
        # Draw a simple 8x8 pattern
        bitmap = [[1 if (x + y) % 2 == 0 else 0 for x in range(8)] for y in range(8)]
        packet = build_rt_draw_bitmap(10, 10, 8, 8, bitmap, r=255, g=0, b=0)
    """
    color = _rgb_to_color_int(r, g, b)

    # Calculate bytes per row (ceil(width / 8))
    bytes_per_row = (width + 7) // 8

    # Total payload size: 12 (header) + height * bytes_per_row (bitmap data)
    bitmap_size = height * bytes_per_row
    inner_len = 12 + bitmap_size

    # Encode inner length
    len_bytes = _encode_length(inner_len)
    len_size = len(len_bytes)

    # Build payload
    payload = bytearray(1 + len_size + inner_len)
    payload[0] = 50  # TLV tag

    # Copy length bytes
    for i, b in enumerate(len_bytes):
        payload[1 + i] = b

    offset = 1 + len_size

    # Type = 0 (bitmap)
    payload[offset] = RT_DRAW_TYPE_RAW
    offset += 1

    # Color (3 bytes)
    payload[offset : offset + 3] = _color_int_to_bytes(color)
    offset += 3

    # Coordinates (x0, y0, x1, y1 as 16-bit LE)
    x1 = x0 + width - 1
    y1 = y0 + height - 1
    payload[offset] = x0 & 0xFF
    payload[offset + 1] = (x0 >> 8) & 0xFF
    payload[offset + 2] = y0 & 0xFF
    payload[offset + 3] = (y0 >> 8) & 0xFF
    payload[offset + 4] = x1 & 0xFF
    payload[offset + 5] = (x1 >> 8) & 0xFF
    payload[offset + 6] = y1 & 0xFF
    payload[offset + 7] = (y1 >> 8) & 0xFF
    offset += 8

    # Pack bitmap data (1 bit per pixel, MSB first)
    for row_idx in range(height):
        row = bitmap[row_idx] if row_idx < len(bitmap) else [0] * width
        byte_val = 0
        bit_pos = 7
        for col_idx in range(width):
            pixel = row[col_idx] if col_idx < len(row) else 0
            if pixel:
                byte_val |= 1 << bit_pos
            bit_pos -= 1
            if bit_pos < 0:
                payload[offset] = byte_val
                offset += 1
                byte_val = 0
                bit_pos = 7
        # Write remaining bits if width is not a multiple of 8
        if bit_pos < 7:
            payload[offset] = byte_val
            offset += 1

    return _build_rt_draw_packet(bytes(payload), sno)


def build_rt_draw_pixels(
    pixels: list[tuple[int, int]],
    r: int = 255,
    g: int = 255,
    b: int = 255,
    sno: int = 0,
) -> bytearray:
    """
    Build rt_draw command to draw pixels at specific coordinates.

    Args:
        pixels: List of (x, y) coordinate tuples.
        r, g, b: RGB color values (0-255). Default is white.
        sno: Sequence number (optional).

    Returns:
        Complete packet ready to send via BLE.

    Example:
        # Draw 3 red pixels
        packet = build_rt_draw_pixels([(10, 20), (11, 20), (12, 20)], r=255, g=0, b=0)
    """
    if not pixels:
        raise ValueError("pixels list cannot be empty")

    color = _rgb_to_color_int(r, g, b)

    # Calculate bounding box
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    width = x1 - x0 + 1
    height = y1 - y0 + 1

    # Create bitmap (1 bit per pixel, packed into bytes)
    bitmap = [0] * (width * height)
    for x, y in pixels:
        idx = (x - x0) + (y - y0) * width
        bitmap[idx] = 1

    # Pack bitmap into bytes (8 pixels per byte, MSB first)
    bitmap_bytes = bytearray()
    for row in range(height):
        row_offset = row * width
        byte_val = 0
        bit_pos = 7
        for col in range(width):
            byte_val += bitmap[row_offset + col] << bit_pos
            if bit_pos == 0:
                bitmap_bytes.append(byte_val)
                byte_val = 0
                bit_pos = 7
            else:
                bit_pos -= 1
        if bit_pos < 7:
            bitmap_bytes.append(byte_val)

    # Build payload
    # Type 0 format: [50, len, type=0, R, G, B, x0, y0, x1, y1, bitmap...]
    payload_len = 12 + len(bitmap_bytes)

    # Use variable-length encoding for payload length
    if payload_len < 128:
        len_bytes = bytes([payload_len])
    else:
        len_bytes = bytes([0x81, payload_len & 0xFF])

    payload = bytearray()
    payload.append(50)  # TLV tag
    payload.extend(len_bytes)
    payload.append(RT_DRAW_TYPE_RAW)  # Type 0 = raw bitmap
    payload.extend(_color_int_to_bytes(color))
    payload.extend([x0 & 0xFF, (x0 >> 8) & 0xFF])
    payload.extend([y0 & 0xFF, (y0 >> 8) & 0xFF])
    payload.extend([x1 & 0xFF, (x1 >> 8) & 0xFF])
    payload.extend([y1 & 0xFF, (y1 >> 8) & 0xFF])
    payload.extend(bitmap_bytes)

    return _build_rt_draw_packet(bytes(payload), sno)


# =============================================================================
# Legacy exports for backwards compatibility
# =============================================================================

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
