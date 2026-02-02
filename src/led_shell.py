"""
LED Shell - Real terminal emulator on the LED backpack.

Uses pyte for proper terminal emulation with ANSI colors.

Usage:
    uv run python -m src.led_shell
    uv run python -m src.led_shell --demo
"""

import asyncio
import argparse
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import tty

import pyte
from bleak import BleakClient, BleakScanner
from loguru import logger as log

from src.led_protocol import (
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    build_rt_draw_fill_rect,
    build_rt_draw_bitmap,
    build_reset_command,
    build_ready_command,
    build_game_mode,
)
from src.utils.logging_config import setup_logging

# Compact 4x6 font for more text on screen
# Each character is 4 pixels wide, 6 pixels tall
# Stored as 6 bytes per character (one byte per row, LSB = leftmost pixel)
FONT_4X6: dict[str, list[int]] = {
    " ": [0x0, 0x0, 0x0, 0x0, 0x0, 0x0],
    "!": [0x4, 0x4, 0x4, 0x0, 0x4, 0x0],
    '"': [0xA, 0xA, 0x0, 0x0, 0x0, 0x0],
    "#": [0xA, 0xF, 0xA, 0xF, 0xA, 0x0],
    "$": [0x4, 0xE, 0xC, 0x2, 0xE, 0x4],
    "%": [0x9, 0x2, 0x4, 0x9, 0x0, 0x0],
    "&": [0x4, 0xA, 0x4, 0xA, 0x5, 0x0],
    "'": [0x4, 0x4, 0x0, 0x0, 0x0, 0x0],
    "(": [0x2, 0x4, 0x4, 0x4, 0x2, 0x0],
    ")": [0x4, 0x2, 0x2, 0x2, 0x4, 0x0],
    "*": [0x0, 0xA, 0x4, 0xA, 0x0, 0x0],
    "+": [0x0, 0x4, 0xE, 0x4, 0x0, 0x0],
    ",": [0x0, 0x0, 0x0, 0x4, 0x4, 0x8],
    "-": [0x0, 0x0, 0xE, 0x0, 0x0, 0x0],
    ".": [0x0, 0x0, 0x0, 0x0, 0x4, 0x0],
    "/": [0x1, 0x2, 0x4, 0x8, 0x0, 0x0],
    "0": [0x6, 0x9, 0x9, 0x9, 0x6, 0x0],
    "1": [0x4, 0xC, 0x4, 0x4, 0xE, 0x0],
    "2": [0xE, 0x1, 0x6, 0x8, 0xF, 0x0],
    "3": [0xE, 0x1, 0x6, 0x1, 0xE, 0x0],
    "4": [0x2, 0x6, 0xA, 0xF, 0x2, 0x0],
    "5": [0xF, 0x8, 0xE, 0x1, 0xE, 0x0],
    "6": [0x6, 0x8, 0xE, 0x9, 0x6, 0x0],
    "7": [0xF, 0x1, 0x2, 0x4, 0x4, 0x0],
    "8": [0x6, 0x9, 0x6, 0x9, 0x6, 0x0],
    "9": [0x6, 0x9, 0x7, 0x1, 0x6, 0x0],
    ":": [0x0, 0x4, 0x0, 0x4, 0x0, 0x0],
    ";": [0x0, 0x4, 0x0, 0x4, 0x8, 0x0],
    "<": [0x2, 0x4, 0x8, 0x4, 0x2, 0x0],
    "=": [0x0, 0xE, 0x0, 0xE, 0x0, 0x0],
    ">": [0x8, 0x4, 0x2, 0x4, 0x8, 0x0],
    "?": [0x6, 0x1, 0x2, 0x0, 0x2, 0x0],
    "@": [0x6, 0x9, 0xB, 0x8, 0x6, 0x0],
    "A": [0x6, 0x9, 0xF, 0x9, 0x9, 0x0],
    "B": [0xE, 0x9, 0xE, 0x9, 0xE, 0x0],
    "C": [0x6, 0x9, 0x8, 0x9, 0x6, 0x0],
    "D": [0xE, 0x9, 0x9, 0x9, 0xE, 0x0],
    "E": [0xF, 0x8, 0xE, 0x8, 0xF, 0x0],
    "F": [0xF, 0x8, 0xE, 0x8, 0x8, 0x0],
    "G": [0x6, 0x8, 0xB, 0x9, 0x6, 0x0],
    "H": [0x9, 0x9, 0xF, 0x9, 0x9, 0x0],
    "I": [0xE, 0x4, 0x4, 0x4, 0xE, 0x0],
    "J": [0x7, 0x2, 0x2, 0xA, 0x4, 0x0],
    "K": [0x9, 0xA, 0xC, 0xA, 0x9, 0x0],
    "L": [0x8, 0x8, 0x8, 0x8, 0xF, 0x0],
    "M": [0x9, 0xF, 0x9, 0x9, 0x9, 0x0],
    "N": [0x9, 0xD, 0xB, 0x9, 0x9, 0x0],
    "O": [0x6, 0x9, 0x9, 0x9, 0x6, 0x0],
    "P": [0xE, 0x9, 0xE, 0x8, 0x8, 0x0],
    "Q": [0x6, 0x9, 0x9, 0xA, 0x5, 0x0],
    "R": [0xE, 0x9, 0xE, 0xA, 0x9, 0x0],
    "S": [0x7, 0x8, 0x6, 0x1, 0xE, 0x0],
    "T": [0xE, 0x4, 0x4, 0x4, 0x4, 0x0],
    "U": [0x9, 0x9, 0x9, 0x9, 0x6, 0x0],
    "V": [0x9, 0x9, 0x9, 0x6, 0x6, 0x0],
    "W": [0x9, 0x9, 0x9, 0xF, 0x9, 0x0],
    "X": [0x9, 0x9, 0x6, 0x9, 0x9, 0x0],
    "Y": [0x9, 0x9, 0x7, 0x1, 0x6, 0x0],
    "Z": [0xF, 0x2, 0x4, 0x8, 0xF, 0x0],
    "[": [0x6, 0x4, 0x4, 0x4, 0x6, 0x0],
    "\\": [0x8, 0x4, 0x2, 0x1, 0x0, 0x0],
    "]": [0x6, 0x2, 0x2, 0x2, 0x6, 0x0],
    "^": [0x4, 0xA, 0x0, 0x0, 0x0, 0x0],
    "_": [0x0, 0x0, 0x0, 0x0, 0xF, 0x0],
    "`": [0x4, 0x2, 0x0, 0x0, 0x0, 0x0],
    "a": [0x0, 0x6, 0xA, 0xA, 0x5, 0x0],
    "b": [0x8, 0xE, 0x9, 0x9, 0xE, 0x0],
    "c": [0x0, 0x6, 0x8, 0x8, 0x6, 0x0],
    "d": [0x1, 0x7, 0x9, 0x9, 0x7, 0x0],
    "e": [0x0, 0x6, 0xF, 0x8, 0x6, 0x0],
    "f": [0x2, 0x4, 0xE, 0x4, 0x4, 0x0],
    "g": [0x0, 0x7, 0x9, 0x7, 0x1, 0x6],
    "h": [0x8, 0xE, 0x9, 0x9, 0x9, 0x0],
    "i": [0x4, 0x0, 0x4, 0x4, 0x4, 0x0],
    "j": [0x2, 0x0, 0x2, 0x2, 0xA, 0x4],
    "k": [0x8, 0xA, 0xC, 0xA, 0x9, 0x0],
    "l": [0xC, 0x4, 0x4, 0x4, 0xE, 0x0],
    "m": [0x0, 0xA, 0xF, 0x9, 0x9, 0x0],
    "n": [0x0, 0xE, 0x9, 0x9, 0x9, 0x0],
    "o": [0x0, 0x6, 0x9, 0x9, 0x6, 0x0],
    "p": [0x0, 0xE, 0x9, 0xE, 0x8, 0x8],
    "q": [0x0, 0x7, 0x9, 0x7, 0x1, 0x1],
    "r": [0x0, 0x6, 0x8, 0x8, 0x8, 0x0],
    "s": [0x0, 0x6, 0xC, 0x2, 0xC, 0x0],
    "t": [0x4, 0xE, 0x4, 0x4, 0x2, 0x0],
    "u": [0x0, 0x9, 0x9, 0x9, 0x6, 0x0],
    "v": [0x0, 0x9, 0x9, 0x6, 0x6, 0x0],
    "w": [0x0, 0x9, 0x9, 0xF, 0x6, 0x0],
    "x": [0x0, 0x9, 0x6, 0x6, 0x9, 0x0],
    "y": [0x0, 0x9, 0x9, 0x7, 0x1, 0x6],
    "z": [0x0, 0xF, 0x2, 0x4, 0xF, 0x0],
    "{": [0x2, 0x4, 0x8, 0x4, 0x2, 0x0],
    "|": [0x4, 0x4, 0x4, 0x4, 0x4, 0x0],
    "}": [0x8, 0x4, 0x2, 0x4, 0x8, 0x0],
    "~": [0x0, 0x5, 0xA, 0x0, 0x0, 0x0],
}

CHAR_WIDTH = 5  # 4 pixels + 1 spacing
CHAR_HEIGHT = 7  # 6 pixels + 1 spacing
FONT_PIXEL_WIDTH = 4
FONT_PIXEL_HEIGHT = 6

# ANSI color palette (basic 8 colors)
ANSI_COLORS = {
    "black": (0, 0, 0),
    "red": (205, 0, 0),
    "green": (0, 205, 0),
    "yellow": (205, 205, 0),
    "blue": (0, 0, 238),
    "magenta": (205, 0, 205),
    "cyan": (0, 205, 205),
    "white": (229, 229, 229),
    # Bright variants
    "brightblack": (127, 127, 127),
    "brightred": (255, 0, 0),
    "brightgreen": (0, 255, 0),
    "brightyellow": (255, 255, 0),
    "brightblue": (92, 92, 255),
    "brightmagenta": (255, 0, 255),
    "brightcyan": (0, 255, 255),
    "brightwhite": (255, 255, 255),
    "default": (0, 255, 0),  # Default green terminal color
}


def get_color(name: str, bold: bool = False) -> tuple[int, int, int]:
    """Get RGB color from ANSI color name."""
    if bold and name in ANSI_COLORS:
        bright_name = f"bright{name}"
        if bright_name in ANSI_COLORS:
            return ANSI_COLORS[bright_name]
    return ANSI_COLORS.get(name, ANSI_COLORS["default"])


def render_line_bitmap(
    chars: list[tuple[str, tuple[int, int, int]]],
    cols: int,
) -> tuple[list[list[int]], list[list[tuple[int, int, int]]]]:
    """
    Render a line of colored text as bitmaps.

    Returns:
        Tuple of (pixel_bitmap, color_map) where color_map has the color for each pixel.
    """
    width = cols * CHAR_WIDTH
    height = FONT_PIXEL_HEIGHT

    # Bitmap (0/1 for each pixel)
    bitmap = [[0] * width for _ in range(height)]
    # Color for each pixel
    colors = [[(0, 0, 0)] * width for _ in range(height)]

    for col, (char, color) in enumerate(chars[:cols]):
        if char not in FONT_4X6:
            char = " " if ord(char) < 32 or ord(char) > 126 else "?"
        font_data = FONT_4X6.get(char, FONT_4X6[" "])

        base_x = col * CHAR_WIDTH

        for row_idx, row_byte in enumerate(font_data):
            if row_idx >= height:
                break
            for bit_idx in range(FONT_PIXEL_WIDTH):
                pixel = 1 if row_byte & (1 << (3 - bit_idx)) else 0
                x = base_x + bit_idx
                if x < width:
                    bitmap[row_idx][x] = pixel
                    if pixel:
                        colors[row_idx][x] = color

    return bitmap, colors


async def find_device(name_prefix: str = "YS") -> str | None:
    """Scan for LED backpack device."""
    log.info(f"Scanning for devices starting with '{name_prefix}'...")
    devices = await BleakScanner.discover(timeout=20.0)
    for device in devices:
        if device.name and device.name.startswith(name_prefix):
            log.info(f"Found device: {device.name} ({device.address})")
            return device.address
    return None


class LedShell:
    """Real terminal emulator for LED backpack using pyte."""

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.cols = DEFAULT_WIDTH // CHAR_WIDTH  # ~19 columns with 4px font
        self.rows = DEFAULT_HEIGHT // CHAR_HEIGHT  # ~18 rows with 6px font

        # Create pyte screen and stream
        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.Stream(self.screen)

        self.default_fg = ANSI_COLORS["default"]
        self.default_bg = (0, 0, 0)
        self.last_screen_hash = None

    async def init_display(self) -> None:
        """Initialize the display for drawing."""
        log.info(f"Initializing display ({self.cols}x{self.rows} chars)...")

        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_reset_command())
        await asyncio.sleep(0.5)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_ready_command())
        await asyncio.sleep(0.5)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_game_mode(16))
        await asyncio.sleep(0.5)

        # Clear screen
        await self.clear_display()

    async def clear_display(self) -> None:
        """Clear the entire display."""
        packet = build_rt_draw_fill_rect(
            0, 0, DEFAULT_WIDTH - 1, DEFAULT_HEIGHT - 1, r=0, g=0, b=0
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.02)

    async def draw_line(
        self, row: int, chars: list[tuple[str, tuple[int, int, int]]]
    ) -> None:
        """Draw a line with colored characters."""
        if row < 0 or row >= self.rows:
            return

        base_y = row * CHAR_HEIGHT

        # Clear line
        packet = build_rt_draw_fill_rect(
            0, base_y, DEFAULT_WIDTH - 1, base_y + CHAR_HEIGHT - 1, r=0, g=0, b=0
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        # Group consecutive chars by color for efficiency
        bitmap, colors = render_line_bitmap(chars, self.cols)

        # Find unique colors in this line
        unique_colors: set[tuple[int, int, int]] = set()
        for row_colors in colors:
            for color in row_colors:
                if color != (0, 0, 0):
                    unique_colors.add(color)

        # Draw each color layer
        for color in unique_colors:
            # Create bitmap for just this color
            color_bitmap = [
                [
                    1 if bitmap[y][x] and colors[y][x] == color else 0
                    for x in range(len(bitmap[0]))
                ]
                for y in range(len(bitmap))
            ]

            # Check if any pixels in this color
            has_pixels = any(any(row) for row in color_bitmap)
            if has_pixels:
                packet = build_rt_draw_bitmap(
                    0,
                    base_y,
                    self.cols * CHAR_WIDTH,
                    FONT_PIXEL_HEIGHT,
                    color_bitmap,
                    r=color[0],
                    g=color[1],
                    b=color[2],
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.005)

    async def refresh_display(self) -> None:
        """Refresh the display from pyte screen state."""
        for row in range(self.rows):
            line_chars = []
            for col in range(self.cols):
                char = self.screen.buffer[row][col]

                # Get character
                char_str = char.data if char.data else " "

                # Get foreground color
                fg = char.fg
                bold = char.bold

                if fg == "default" or fg is None:
                    color = self.default_fg
                else:
                    color = get_color(fg, bold)

                line_chars.append((char_str, color))

            await self.draw_line(row, line_chars)

    async def run_demo(self) -> None:
        """Run demo with colored text."""
        log.info("Running demo mode...")

        # Feed some colored text through pyte
        demo_text = (
            "\x1b[32mHello \x1b[31mLED \x1b[33mWorld!\x1b[0m\r\n"
            "\x1b[1;34mBold Blue\x1b[0m \x1b[35mMagenta\x1b[0m\r\n"
            "\x1b[36mCyan\x1b[0m \x1b[37mWhite\x1b[0m\r\n"
            "\r\n"
            "\x1b[32m$ \x1b[0mls -la\r\n"
            "\x1b[34mdrwxr-xr-x\x1b[0m  5 user\r\n"
            "\x1b[32m-rw-r--r--\x1b[0m  1 file\r\n"
        )

        self.stream.feed(demo_text)
        await self.refresh_display()
        await asyncio.sleep(5)

    async def run_shell(self) -> None:
        """Run interactive shell."""
        log.info("Starting shell...")
        print("\n=== LED Shell ===")
        print("Press Ctrl+D to exit.\n")

        # Create pseudo-terminal
        master_fd, slave_fd = pty.openpty()

        pid = os.fork()
        if pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            os.close(slave_fd)

            # Set terminal size
            winsize = struct.pack("HHHH", self.rows, self.cols, 0, 0)
            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)

            # Set TERM for proper escape sequence support
            os.environ["TERM"] = "xterm-256color"
            os.environ["PS1"] = "\\$ "  # Simple prompt

            shell = os.environ.get("SHELL", "/bin/sh")
            os.execv(shell, [shell, "-i"])

        # Parent process
        os.close(slave_fd)
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setraw(sys.stdin.fileno())

            while True:
                rlist, _, _ = select.select([sys.stdin, master_fd], [], [], 0.05)

                if sys.stdin in rlist:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if not data:
                        break
                    os.write(master_fd, data)

                if master_fd in rlist:
                    try:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        # Feed to pyte
                        self.stream.feed(data.decode("utf-8", errors="replace"))
                        # Refresh display
                        await self.refresh_display()
                    except OSError:
                        break

        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            os.close(master_fd)
            os.waitpid(pid, 0)
            print("\nExiting LED Shell.")


async def main() -> None:
    """Main entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(description="LED Shell - Terminal on LED backpack")
    parser.add_argument("--address", type=str, help="BLE device address")
    parser.add_argument("--demo", action="store_true", help="Run demo mode")
    args = parser.parse_args()

    address = args.address
    if not address:
        address = await find_device()
        if not address:
            log.error("No device found!")
            return

    log.info(f"Connecting to {address}...")
    async with BleakClient(address) as client:
        log.info("Connected!")

        def notification_handler(sender: int, data: bytearray) -> None:
            pass

        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)

        shell = LedShell(client)
        await shell.init_display()

        if args.demo:
            await shell.run_demo()
        else:
            await shell.run_shell()

        await client.stop_notify(NOTIFY_CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())
