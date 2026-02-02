"""
Interactive LED Terminal - Display text and terminal output on the LED backpack.

This creates a TUI where you can type text that appears on the LED display in real-time.

Usage:
    uv run python -m src.led_terminal
    uv run python -m src.led_terminal --shell  # Terminal emulator mode
"""

import asyncio
import argparse
import os
import pty
import select
import struct
import sys
import termios
import tty
from dataclasses import dataclass

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

# Simple 5x7 bitmap font for ASCII characters 32-126
# Each character is 5 pixels wide, 7 pixels tall
# Stored as 7 bytes per character (one byte per row, LSB = leftmost pixel)
FONT_5X7: dict[str, list[int]] = {
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    "!": [0x04, 0x04, 0x04, 0x04, 0x00, 0x04, 0x00],
    '"': [0x0A, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00],
    "#": [0x0A, 0x1F, 0x0A, 0x1F, 0x0A, 0x00, 0x00],
    "$": [0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04],
    "%": [0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03],
    "&": [0x08, 0x14, 0x14, 0x08, 0x15, 0x12, 0x0D],
    "'": [0x04, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    "*": [0x04, 0x15, 0x0E, 0x1F, 0x0E, 0x15, 0x04],
    "+": [0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00],
    ",": [0x00, 0x00, 0x00, 0x00, 0x04, 0x04, 0x08],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00],
    "/": [0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x0E, 0x11, 0x01, 0x06, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    ":": [0x00, 0x04, 0x00, 0x00, 0x04, 0x00, 0x00],
    ";": [0x00, 0x04, 0x00, 0x00, 0x04, 0x04, 0x08],
    "<": [0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02],
    "=": [0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00],
    ">": [0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08],
    "?": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    "@": [0x0E, 0x11, 0x17, 0x15, 0x17, 0x10, 0x0E],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "[": [0x0E, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0E],
    "\\": [0x10, 0x10, 0x08, 0x04, 0x02, 0x01, 0x01],
    "]": [0x0E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0E],
    "^": [0x04, 0x0A, 0x11, 0x00, 0x00, 0x00, 0x00],
    "_": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F],
    "`": [0x08, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00],
    "a": [0x00, 0x00, 0x0E, 0x01, 0x0F, 0x11, 0x0F],
    "b": [0x10, 0x10, 0x1E, 0x11, 0x11, 0x11, 0x1E],
    "c": [0x00, 0x00, 0x0E, 0x11, 0x10, 0x11, 0x0E],
    "d": [0x01, 0x01, 0x0F, 0x11, 0x11, 0x11, 0x0F],
    "e": [0x00, 0x00, 0x0E, 0x11, 0x1F, 0x10, 0x0E],
    "f": [0x06, 0x08, 0x1E, 0x08, 0x08, 0x08, 0x08],
    "g": [0x00, 0x00, 0x0F, 0x11, 0x0F, 0x01, 0x0E],
    "h": [0x10, 0x10, 0x1E, 0x11, 0x11, 0x11, 0x11],
    "i": [0x04, 0x00, 0x0C, 0x04, 0x04, 0x04, 0x0E],
    "j": [0x02, 0x00, 0x06, 0x02, 0x02, 0x12, 0x0C],
    "k": [0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12],
    "l": [0x0C, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "m": [0x00, 0x00, 0x1A, 0x15, 0x15, 0x15, 0x15],
    "n": [0x00, 0x00, 0x1E, 0x11, 0x11, 0x11, 0x11],
    "o": [0x00, 0x00, 0x0E, 0x11, 0x11, 0x11, 0x0E],
    "p": [0x00, 0x00, 0x1E, 0x11, 0x1E, 0x10, 0x10],
    "q": [0x00, 0x00, 0x0F, 0x11, 0x0F, 0x01, 0x01],
    "r": [0x00, 0x00, 0x16, 0x19, 0x10, 0x10, 0x10],
    "s": [0x00, 0x00, 0x0F, 0x10, 0x0E, 0x01, 0x1E],
    "t": [0x08, 0x08, 0x1E, 0x08, 0x08, 0x09, 0x06],
    "u": [0x00, 0x00, 0x11, 0x11, 0x11, 0x11, 0x0F],
    "v": [0x00, 0x00, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "w": [0x00, 0x00, 0x11, 0x11, 0x15, 0x15, 0x0A],
    "x": [0x00, 0x00, 0x11, 0x0A, 0x04, 0x0A, 0x11],
    "y": [0x00, 0x00, 0x11, 0x11, 0x0F, 0x01, 0x0E],
    "z": [0x00, 0x00, 0x1F, 0x02, 0x04, 0x08, 0x1F],
    "{": [0x02, 0x04, 0x04, 0x08, 0x04, 0x04, 0x02],
    "|": [0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "}": [0x08, 0x04, 0x04, 0x02, 0x04, 0x04, 0x08],
    "~": [0x00, 0x00, 0x08, 0x15, 0x02, 0x00, 0x00],
}

CHAR_WIDTH = 6  # 5 pixels + 1 spacing
CHAR_HEIGHT = 8  # 7 pixels + 1 spacing


@dataclass
class TerminalState:
    """State for the terminal display."""

    cursor_x: int = 0
    cursor_y: int = 0
    text_color: tuple[int, int, int] = (0, 255, 0)  # Green
    bg_color: tuple[int, int, int] = (0, 0, 0)  # Black
    cols: int = DEFAULT_WIDTH // CHAR_WIDTH  # ~16 columns
    rows: int = DEFAULT_HEIGHT // CHAR_HEIGHT  # ~16 rows
    buffer: list[list[str]] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.buffer is None:
            self.buffer = [[" " for _ in range(self.cols)] for _ in range(self.rows)]


def get_char_pixels(char: str) -> list[tuple[int, int]]:
    """Get list of (x, y) pixel offsets for a character (relative to top-left)."""
    if char not in FONT_5X7:
        char = "?"
    bitmap = FONT_5X7.get(char, FONT_5X7[" "])
    pixels = []
    for y, row in enumerate(bitmap):
        for x in range(5):
            if row & (1 << x):
                pixels.append((x, y))
    return pixels


def get_char_bitmap(char: str) -> list[list[int]]:
    """Get 2D bitmap for a character (for use with build_rt_draw_bitmap)."""
    if char not in FONT_5X7:
        char = "?"
    font_data = FONT_5X7.get(char, FONT_5X7[" "])
    bitmap = []
    for row_byte in font_data:
        row = []
        # Reverse bit order: font stores LSB=left, but we need MSB=left for display
        for x in range(4, -1, -1):
            row.append(1 if row_byte & (1 << x) else 0)
        bitmap.append(row)
    return bitmap


def render_line_bitmap(
    text: str, cols: int, char_width: int = CHAR_WIDTH, char_height: int = CHAR_HEIGHT
) -> list[list[int]]:
    """Render a line of text as a 2D bitmap."""
    # Limit to available columns
    text = text[:cols]

    # Create bitmap for entire line
    width = cols * char_width
    height = char_height
    bitmap = [[0] * width for _ in range(height)]

    for col, char in enumerate(text):
        if char not in FONT_5X7:
            char = " " if char < " " or char > "~" else "?"
        font_data = FONT_5X7.get(char, FONT_5X7[" "])

        base_x = col * char_width

        for row_idx, row_byte in enumerate(font_data):
            if row_idx >= height:
                break
            # Reverse bit order for correct display
            for bit_idx in range(5):
                pixel = 1 if row_byte & (1 << bit_idx) else 0
                x = base_x + (4 - bit_idx)  # Reverse: bit 0 -> x+4, bit 4 -> x+0
                if x < width:
                    bitmap[row_idx][x] = pixel

    return bitmap


async def find_device(name_prefix: str = "YS") -> str | None:
    """Scan for LED backpack device."""
    log.info(f"Scanning for devices starting with '{name_prefix}'...")
    devices = await BleakScanner.discover(timeout=20.0)
    for device in devices:
        if device.name and device.name.startswith(name_prefix):
            log.info(f"Found device: {device.name} ({device.address})")
            return device.address
    return None


class LedTerminal:
    """Interactive terminal for LED backpack."""

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.state = TerminalState()
        self.running = False

    async def init_display(self) -> None:
        """Initialize the display for drawing."""
        log.info("Initializing display...")

        # Reset and ready
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_reset_command())
        await asyncio.sleep(0.5)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_ready_command())
        await asyncio.sleep(0.5)

        # Enter graffiti mode
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_game_mode(16))
        await asyncio.sleep(0.5)

        # Clear screen
        await self.clear_screen()

    async def clear_screen(self) -> None:
        """Clear the entire screen."""
        packet = build_rt_draw_fill_rect(
            0,
            0,
            DEFAULT_WIDTH - 1,
            DEFAULT_HEIGHT - 1,
            r=self.state.bg_color[0],
            g=self.state.bg_color[1],
            b=self.state.bg_color[2],
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.02)

        # Reset buffer
        self.state.buffer = [
            [" " for _ in range(self.state.cols)] for _ in range(self.state.rows)
        ]
        self.state.cursor_x = 0
        self.state.cursor_y = 0

    async def draw_char(self, char: str, col: int, row: int) -> None:
        """Draw a single character at the given column and row using bitmap."""
        if col < 0 or col >= self.state.cols or row < 0 or row >= self.state.rows:
            return

        base_x = col * CHAR_WIDTH
        base_y = row * CHAR_HEIGHT

        # Clear the character cell first (black background)
        packet = build_rt_draw_fill_rect(
            base_x,
            base_y,
            base_x + CHAR_WIDTH - 1,
            base_y + CHAR_HEIGHT - 1,
            r=self.state.bg_color[0],
            g=self.state.bg_color[1],
            b=self.state.bg_color[2],
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        # Draw character as bitmap (single packet!)
        if char != " ":
            bitmap = get_char_bitmap(char)
            packet = build_rt_draw_bitmap(
                base_x,
                base_y,
                5,  # char width
                7,  # char height
                bitmap,
                r=self.state.text_color[0],
                g=self.state.text_color[1],
                b=self.state.text_color[2],
            )
            await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
            await asyncio.sleep(0.005)

    async def draw_line(self, row: int) -> None:
        """Draw an entire line from the buffer as a single bitmap."""
        if row < 0 or row >= self.state.rows:
            return

        base_y = row * CHAR_HEIGHT
        line_text = "".join(self.state.buffer[row])

        # Clear the entire line first
        packet = build_rt_draw_fill_rect(
            0,
            base_y,
            DEFAULT_WIDTH - 1,
            base_y + CHAR_HEIGHT - 1,
            r=self.state.bg_color[0],
            g=self.state.bg_color[1],
            b=self.state.bg_color[2],
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        # Render entire line as bitmap
        bitmap = render_line_bitmap(line_text, self.state.cols)
        packet = build_rt_draw_bitmap(
            0,
            base_y,
            self.state.cols * CHAR_WIDTH,
            CHAR_HEIGHT - 1,  # 7 pixels for font
            bitmap[:7],  # Only the font rows
            r=self.state.text_color[0],
            g=self.state.text_color[1],
            b=self.state.text_color[2],
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.01)

    async def write_char(self, char: str, immediate: bool = True) -> None:
        """Write a character at the current cursor position."""
        if char == "\n" or char == "\r":
            # Redraw current line before moving
            if immediate:
                await self.draw_line(self.state.cursor_y)
            self.state.cursor_x = 0
            self.state.cursor_y += 1
        elif char == "\b" or ord(char) == 127:  # Backspace
            if self.state.cursor_x > 0:
                self.state.cursor_x -= 1
                self.state.buffer[self.state.cursor_y][self.state.cursor_x] = " "
                if immediate:
                    await self.draw_line(self.state.cursor_y)
        elif char >= " " and char <= "~":
            # Store in buffer
            self.state.buffer[self.state.cursor_y][self.state.cursor_x] = char
            self.state.cursor_x += 1

        # Handle line wrap
        if self.state.cursor_x >= self.state.cols:
            if immediate:
                await self.draw_line(self.state.cursor_y)
            self.state.cursor_x = 0
            self.state.cursor_y += 1

        # Handle scroll (simple: just wrap to top)
        if self.state.cursor_y >= self.state.rows:
            self.state.cursor_y = 0
            # Clear the new line
            for col in range(self.state.cols):
                self.state.buffer[self.state.cursor_y][col] = " "

    async def write_text(self, text: str) -> None:
        """Write a string of text (line-buffered for speed)."""
        for char in text:
            # Buffer chars, only draw on newline or when line is full
            needs_draw = (
                char in ("\n", "\r") or self.state.cursor_x >= self.state.cols - 1
            )
            await self.write_char(char, immediate=needs_draw)

        # Draw current line at end
        await self.draw_line(self.state.cursor_y)

    async def write_line(self, text: str) -> None:
        """Write a complete line of text efficiently."""
        # Pad or truncate to line width
        line = text[: self.state.cols].ljust(self.state.cols)

        # Store in buffer
        for i, char in enumerate(line):
            self.state.buffer[self.state.cursor_y][i] = char

        # Draw entire line at once
        await self.draw_line(self.state.cursor_y)

        # Move to next line
        self.state.cursor_x = 0
        self.state.cursor_y += 1
        if self.state.cursor_y >= self.state.rows:
            self.state.cursor_y = 0

    async def run_interactive(self) -> None:
        """Run interactive text input mode."""
        print("\n=== LED Terminal ===")
        print("Type text to display on the LED backpack.")
        print("Press Ctrl+C to exit.\n")

        self.running = True

        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            # Set terminal to raw mode
            tty.setraw(sys.stdin.fileno())

            while self.running:
                # Check for input
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1)
                    if char == "\x03":  # Ctrl+C
                        break
                    elif char == "\x0c":  # Ctrl+L - clear screen
                        await self.clear_screen()
                    else:
                        await self.write_char(char)

        finally:
            # Restore terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            print("\nExiting LED Terminal.")

    async def run_shell(self) -> None:
        """Run a shell and display output on LED."""
        print("\n=== LED Shell ===")
        print("Running shell on LED display. Press Ctrl+D to exit.\n")

        self.running = True

        # Create pseudo-terminal
        master_fd, slave_fd = pty.openpty()

        # Fork shell process
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
            winsize = struct.pack("HHHH", self.state.rows, self.state.cols, 0, 0)
            import fcntl

            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)

            # Execute shell
            shell = os.environ.get("SHELL", "/bin/sh")
            os.execv(shell, [shell])

        # Parent process
        os.close(slave_fd)

        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setraw(sys.stdin.fileno())

            while self.running:
                rlist, _, _ = select.select([sys.stdin, master_fd], [], [], 0.05)

                # Handle user input
                if sys.stdin in rlist:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if not data:
                        break
                    os.write(master_fd, data)

                # Handle shell output
                if master_fd in rlist:
                    try:
                        data = os.read(master_fd, 1024)
                        if not data:
                            break
                        # Display on LED
                        text = data.decode("utf-8", errors="replace")
                        # Filter out escape sequences (simple approach)
                        filtered = ""
                        i = 0
                        while i < len(text):
                            if text[i] == "\x1b":
                                # Skip escape sequence
                                i += 1
                                if i < len(text) and text[i] == "[":
                                    i += 1
                                    while i < len(text) and not text[i].isalpha():
                                        i += 1
                                    i += 1  # Skip the letter
                            else:
                                filtered += text[i]
                                i += 1
                        await self.write_text(filtered)
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

    parser = argparse.ArgumentParser(description="Interactive LED Terminal")
    parser.add_argument(
        "--address",
        type=str,
        help="BLE device address (will scan if not provided)",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Run shell mode (terminal emulator)",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="#00ff00",
        help="Text color (hex, default green)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode (displays sample text)",
    )
    parser.add_argument(
        "--text",
        type=str,
        help="Text to display (non-interactive)",
    )
    args = parser.parse_args()

    # Parse color
    color_str = args.color.strip().lstrip("#")
    r = int(color_str[0:2], 16)
    g = int(color_str[2:4], 16)
    b = int(color_str[4:6], 16)

    address = args.address
    if not address:
        address = await find_device()
        if not address:
            log.error("No device found!")
            return

    log.info(f"Connecting to {address}...")
    async with BleakClient(address) as client:
        log.info("Connected!")

        # Enable notifications
        def notification_handler(sender: int, data: bytearray) -> None:
            pass  # Silently handle notifications

        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)

        terminal = LedTerminal(client)
        terminal.state.text_color = (r, g, b)
        await terminal.init_display()

        if args.demo:
            # Demo mode - display sample text using fast line rendering
            log.info("Running demo mode...")
            await terminal.write_line("Hello LED!")
            await terminal.write_line("Terminal")
            await terminal.write_line("Works! :)")
            await terminal.write_line("")
            await terminal.write_line("ABCDEFGHIJKLMNO")
            await terminal.write_line("0123456789!@#$%")
            await asyncio.sleep(5)
        elif args.text:
            # Non-interactive text display
            log.info(f"Displaying: {args.text}")
            await terminal.write_text(args.text)
            await asyncio.sleep(5)
        elif args.shell:
            await terminal.run_shell()
        else:
            await terminal.run_interactive()

        await client.stop_notify(NOTIFY_CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())
