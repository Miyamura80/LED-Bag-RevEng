"""
LED Status - Display system status on the LED backpack.

Shows CPU, memory, load, network, and other system metrics.

Usage:
    uv run python -m src.led_status
    uv run python -m src.led_status --interval 2
"""

import asyncio
import argparse
import os
import platform
import subprocess
from datetime import datetime

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

# Import psutil if available
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# Compact 4x6 font
FONT_4X6: dict[str, list[int]] = {
    " ": [0x0, 0x0, 0x0, 0x0, 0x0, 0x0],
    "!": [0x4, 0x4, 0x4, 0x0, 0x4, 0x0],
    "%": [0x9, 0x2, 0x4, 0x9, 0x0, 0x0],
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
    "A": [0x6, 0x9, 0xF, 0x9, 0x9, 0x0],
    "B": [0xE, 0x9, 0xE, 0x9, 0xE, 0x0],
    "C": [0x6, 0x9, 0x8, 0x9, 0x6, 0x0],
    "D": [0xE, 0x9, 0x9, 0x9, 0xE, 0x0],
    "E": [0xF, 0x8, 0xE, 0x8, 0xF, 0x0],
    "F": [0xF, 0x8, 0xE, 0x8, 0x8, 0x0],
    "G": [0x6, 0x8, 0xB, 0x9, 0x6, 0x0],
    "H": [0x9, 0x9, 0xF, 0x9, 0x9, 0x0],
    "I": [0xE, 0x4, 0x4, 0x4, 0xE, 0x0],
    "K": [0x9, 0xA, 0xC, 0xA, 0x9, 0x0],
    "L": [0x8, 0x8, 0x8, 0x8, 0xF, 0x0],
    "M": [0x9, 0xF, 0x9, 0x9, 0x9, 0x0],
    "N": [0x9, 0xD, 0xB, 0x9, 0x9, 0x0],
    "O": [0x6, 0x9, 0x9, 0x9, 0x6, 0x0],
    "P": [0xE, 0x9, 0xE, 0x8, 0x8, 0x0],
    "R": [0xE, 0x9, 0xE, 0xA, 0x9, 0x0],
    "S": [0x7, 0x8, 0x6, 0x1, 0xE, 0x0],
    "T": [0xE, 0x4, 0x4, 0x4, 0x4, 0x0],
    "U": [0x9, 0x9, 0x9, 0x9, 0x6, 0x0],
    "W": [0x9, 0x9, 0x9, 0xF, 0x9, 0x0],
    "X": [0x9, 0x9, 0x6, 0x9, 0x9, 0x0],
    "a": [0x0, 0x6, 0xA, 0xA, 0x5, 0x0],
    "b": [0x8, 0xE, 0x9, 0x9, 0xE, 0x0],
    "c": [0x0, 0x6, 0x8, 0x8, 0x6, 0x0],
    "d": [0x1, 0x7, 0x9, 0x9, 0x7, 0x0],
    "e": [0x0, 0x6, 0xF, 0x8, 0x6, 0x0],
    "g": [0x0, 0x7, 0x9, 0x7, 0x1, 0x6],
    "h": [0x8, 0xE, 0x9, 0x9, 0x9, 0x0],
    "i": [0x4, 0x0, 0x4, 0x4, 0x4, 0x0],
    "k": [0x8, 0xA, 0xC, 0xA, 0x9, 0x0],
    "l": [0xC, 0x4, 0x4, 0x4, 0xE, 0x0],
    "m": [0x0, 0xA, 0xF, 0x9, 0x9, 0x0],
    "n": [0x0, 0xE, 0x9, 0x9, 0x9, 0x0],
    "o": [0x0, 0x6, 0x9, 0x9, 0x6, 0x0],
    "p": [0x0, 0xE, 0x9, 0xE, 0x8, 0x8],
    "r": [0x0, 0x6, 0x8, 0x8, 0x8, 0x0],
    "s": [0x0, 0x6, 0xC, 0x2, 0xC, 0x0],
    "t": [0x4, 0xE, 0x4, 0x4, 0x2, 0x0],
    "u": [0x0, 0x9, 0x9, 0x9, 0x6, 0x0],
    "v": [0x0, 0x9, 0x9, 0x6, 0x6, 0x0],
    "w": [0x0, 0x9, 0x9, 0xF, 0x6, 0x0],
    "x": [0x0, 0x9, 0x6, 0x6, 0x9, 0x0],
    "y": [0x0, 0x9, 0x9, 0x7, 0x1, 0x6],
}

CHAR_WIDTH = 5
CHAR_HEIGHT = 7
FONT_PIXEL_WIDTH = 4
FONT_PIXEL_HEIGHT = 6

# Colors
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
CYAN = (0, 255, 255)
WHITE = (200, 200, 200)
BLUE = (100, 100, 255)


def render_line_bitmap(
    chars: list[tuple[str, tuple[int, int, int]]],
    cols: int,
) -> tuple[list[list[int]], list[list[tuple[int, int, int]]]]:
    """Render a line of colored text as bitmaps."""
    width = cols * CHAR_WIDTH
    height = FONT_PIXEL_HEIGHT

    bitmap = [[0] * width for _ in range(height)]
    colors = [[(0, 0, 0)] * width for _ in range(height)]

    for col, (char, color) in enumerate(chars[:cols]):
        if char not in FONT_4X6:
            char = " "
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


def get_cpu_percent() -> float:
    """Get CPU usage percentage."""
    if HAS_PSUTIL:
        return psutil.cpu_percent(interval=0.1)
    # Fallback for macOS
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", "%cpu"], capture_output=True, text=True, timeout=2
        )
        total = sum(
            float(x) for x in result.stdout.strip().split("\n")[1:] if x.strip()
        )
        return min(total, 100.0)
    except Exception:
        return 0.0


def get_memory_percent() -> float:
    """Get memory usage percentage."""
    if HAS_PSUTIL:
        return psutil.virtual_memory().percent
    # Fallback for macOS
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=2)
        lines = result.stdout.split("\n")
        stats = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":")
                val = val.strip().rstrip(".")
                if val.isdigit():
                    stats[key.strip()] = int(val)

        page_size = 4096  # macOS default
        free = stats.get("Pages free", 0) * page_size
        active = stats.get("Pages active", 0) * page_size
        inactive = stats.get("Pages inactive", 0) * page_size
        wired = stats.get("Pages wired down", 0) * page_size

        total = free + active + inactive + wired
        used = active + wired
        if total > 0:
            return (used / total) * 100
    except Exception:
        pass
    return 0.0


def get_load_average() -> tuple[float, float, float]:
    """Get system load average."""
    try:
        load = os.getloadavg()
        return load
    except (OSError, AttributeError):
        return (0.0, 0.0, 0.0)


def get_disk_percent() -> float:
    """Get disk usage percentage."""
    if HAS_PSUTIL:
        return psutil.disk_usage("/").percent
    try:
        result = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=2
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                return float(parts[4].rstrip("%"))
    except Exception:
        pass
    return 0.0


def get_network_bytes() -> tuple[int, int]:
    """Get total network bytes (sent, received)."""
    if HAS_PSUTIL:
        counters = psutil.net_io_counters()
        return (counters.bytes_sent, counters.bytes_recv)
    # Fallback - return zeros
    return (0, 0)


def get_uptime() -> str:
    """Get system uptime as a string."""
    try:
        if HAS_PSUTIL:
            boot_time = psutil.boot_time()
            uptime_seconds = datetime.now().timestamp() - boot_time
        else:
            # No psutil, just return generic "up"
            return "up"

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        mins = int((uptime_seconds % 3600) // 60)

        if days > 0:
            return f"{days}d{hours}h"
        elif hours > 0:
            return f"{hours}h{mins}m"
        else:
            return f"{mins}m"
    except Exception:
        return "?"


class LedStatus:
    """System status display for LED backpack."""

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self.cols = DEFAULT_WIDTH // CHAR_WIDTH
        self.rows = DEFAULT_HEIGHT // CHAR_HEIGHT

        # Graph dimensions
        self.graph_width = DEFAULT_WIDTH  # Full width
        self.graph_height = 20  # Pixels per graph (three graphs stacked)

        # History for graphs
        self.cpu_history: list[float] = []
        self.mem_history: list[float] = []
        self.net_up_history: list[float] = []  # KB/s
        self.net_down_history: list[float] = []  # KB/s
        self.sample_count = 0  # For time labels

        # Network tracking
        self.last_net_bytes: tuple[int, int] | None = None
        self.last_net_time: float | None = None

    async def init_display(self) -> None:
        """Initialize the display."""
        log.info(f"Initializing display ({self.cols}x{self.rows} chars)...")

        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_reset_command())
        await asyncio.sleep(0.5)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_ready_command())
        await asyncio.sleep(0.5)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, build_game_mode(16))
        await asyncio.sleep(0.5)

        # Clear screen
        packet = build_rt_draw_fill_rect(
            0, 0, DEFAULT_WIDTH - 1, DEFAULT_HEIGHT - 1, 0, 0, 0
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
            0, base_y, DEFAULT_WIDTH - 1, base_y + CHAR_HEIGHT - 1, 0, 0, 0
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        bitmap, colors = render_line_bitmap(chars, self.cols)

        # Find unique colors
        unique_colors: set[tuple[int, int, int]] = set()
        for row_colors in colors:
            for color in row_colors:
                if color != (0, 0, 0):
                    unique_colors.add(color)

        for color in unique_colors:
            color_bitmap = [
                [
                    1 if bitmap[y][x] and colors[y][x] == color else 0
                    for x in range(len(bitmap[0]))
                ]
                for y in range(len(bitmap))
            ]

            has_pixels = any(any(r) for r in color_bitmap)
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

    def make_colored_line(
        self, text: str, color: tuple[int, int, int]
    ) -> list[tuple[str, tuple[int, int, int]]]:
        """Create a colored line from text."""
        return [(c, color) for c in text.ljust(self.cols)[: self.cols]]

    def make_bar(
        self, value: float, width: int, label: str = ""
    ) -> list[tuple[str, tuple[int, int, int]]]:
        """Create a progress bar with color based on value."""
        if value < 50:
            color = GREEN
        elif value < 80:
            color = YELLOW
        else:
            color = RED

        filled = int((value / 100) * width)
        bar = "#" * filled + "-" * (width - filled)

        percent_str = f"{int(value):2d}%"

        result = []
        # Label
        for c in label:
            result.append((c, CYAN))
        # Bar
        for i, c in enumerate(bar):
            if i < filled:
                result.append((c, color))
            else:
                result.append((c, WHITE))
        # Percent
        for c in percent_str:
            result.append((c, color))

        # Pad to cols
        while len(result) < self.cols:
            result.append((" ", WHITE))

        return result[: self.cols]

    async def draw_graph(
        self,
        y_start: int,
        history: list[float],
        label: str,
        base_color: tuple[int, int, int],
    ) -> None:
        """Draw a usage graph with label using greedy rectangle merging."""
        graph_width = self.graph_width
        graph_height = self.graph_height

        # Clear graph area
        packet = build_rt_draw_fill_rect(
            0, y_start, DEFAULT_WIDTH - 1, y_start + graph_height - 1, r=0, g=0, b=0
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.01)

        # Draw bottom border line
        packet = build_rt_draw_fill_rect(
            0,
            y_start + graph_height - 1,
            graph_width - 1,
            y_start + graph_height - 1,
            r=50,
            g=50,
            b=50,
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        # Build list of bars with their properties
        if len(history) > 0:
            samples = history[-graph_width:]
            start_x = graph_width - len(samples)
            bar_bottom = y_start + graph_height - 2

            # Compute all bars: (x, bar_top, color)
            bars: list[tuple[int, int, tuple[int, int, int]]] = []
            for i, val in enumerate(samples):
                bar_height = int((val / 100.0) * (graph_height - 2))
                if bar_height < 1:
                    bars.append((start_x + i, -1, (0, 0, 0)))  # No bar
                    continue
                bar_top = bar_bottom - bar_height + 1
                if val < 50:
                    color = base_color
                elif val < 80:
                    color = YELLOW
                else:
                    color = RED
                bars.append((start_x + i, bar_top, color))

            # Greedy merge: group consecutive bars with same top and color
            merged: list[tuple[int, int, int, tuple[int, int, int]]] = []
            i = 0
            while i < len(bars):
                x, bar_top, color = bars[i]
                if bar_top == -1:
                    i += 1
                    continue
                # Find run of same bar_top and color
                run_end = i + 1
                while run_end < len(bars):
                    nx, ntop, ncolor = bars[run_end]
                    if ntop == bar_top and ncolor == color:
                        run_end += 1
                    else:
                        break
                # Merge into single rectangle
                x_end = bars[run_end - 1][0]
                merged.append((x, x_end, bar_top, color))
                i = run_end

            # Draw merged rectangles
            for x0, x1, bar_top, color in merged:
                packet = build_rt_draw_fill_rect(
                    x0, bar_top, x1, bar_bottom, r=color[0], g=color[1], b=color[2]
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.002)

        # Draw label at top-left of graph
        label_chars = [(c, base_color) for c in label]
        while len(label_chars) < 4:
            label_chars.append((" ", base_color))

        # Render label bitmap
        bitmap, colors = render_line_bitmap(label_chars[:4], 4)

        for color in [base_color]:
            color_bitmap = [
                [
                    1 if bitmap[y][x] and colors[y][x] == color else 0
                    for x in range(len(bitmap[0]))
                ]
                for y in range(len(bitmap))
            ]
            has_pixels = any(any(r) for r in color_bitmap)
            if has_pixels:
                packet = build_rt_draw_bitmap(
                    1,
                    y_start + 1,
                    4 * CHAR_WIDTH,
                    FONT_PIXEL_HEIGHT,
                    color_bitmap,
                    r=color[0],
                    g=color[1],
                    b=color[2],
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.005)

    async def draw_net_graph(self, y_start: int) -> None:
        """Draw network graph with upload (red) and download (blue) using greedy merging."""
        graph_width = self.graph_width
        graph_height = self.graph_height

        # Clear graph area
        packet = build_rt_draw_fill_rect(
            0, y_start, DEFAULT_WIDTH - 1, y_start + graph_height - 1, r=0, g=0, b=0
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.01)

        # Draw bottom border
        packet = build_rt_draw_fill_rect(
            0,
            y_start + graph_height - 1,
            graph_width - 1,
            y_start + graph_height - 1,
            r=50,
            g=50,
            b=50,
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.005)

        # Find max value for scaling
        all_vals = self.net_up_history + self.net_down_history
        max_val = max(all_vals) if all_vals else 100
        if max_val < 10:
            max_val = 10  # Minimum scale

        bar_bottom = y_start + graph_height - 2
        down_color = (0, 100, 255)
        up_color = (255, 50, 50)

        # Build bar lists for download and upload
        if len(self.net_down_history) > 0:
            down_samples = self.net_down_history[-graph_width:]
            up_samples = self.net_up_history[-graph_width:]
            start_x = graph_width - len(down_samples)

            # Compute bar tops for each type
            down_bars: list[tuple[int, int]] = []  # (x, bar_top) or (x, -1)
            up_bars: list[tuple[int, int]] = []
            for i in range(len(down_samples)):
                x = start_x + i
                down_val = down_samples[i] if i < len(down_samples) else 0
                down_height = int((down_val / max_val) * (graph_height - 2))
                if down_height >= 1:
                    down_bars.append((x, bar_bottom - down_height + 1))
                else:
                    down_bars.append((x, -1))

                up_val = up_samples[i] if i < len(up_samples) else 0
                up_height = int((up_val / max_val) * (graph_height - 2))
                if up_height >= 1:
                    up_bars.append((x, bar_bottom - up_height + 1))
                else:
                    up_bars.append((x, -1))

            # Greedy merge for download bars
            merged_down: list[tuple[int, int, int]] = []
            i = 0
            while i < len(down_bars):
                x, bar_top = down_bars[i]
                if bar_top == -1:
                    i += 1
                    continue
                run_end = i + 1
                while run_end < len(down_bars) and down_bars[run_end][1] == bar_top:
                    run_end += 1
                x_end = down_bars[run_end - 1][0]
                merged_down.append((x, x_end, bar_top))
                i = run_end

            # Greedy merge for upload bars
            merged_up: list[tuple[int, int, int]] = []
            i = 0
            while i < len(up_bars):
                x, bar_top = up_bars[i]
                if bar_top == -1:
                    i += 1
                    continue
                run_end = i + 1
                while run_end < len(up_bars) and up_bars[run_end][1] == bar_top:
                    run_end += 1
                x_end = up_bars[run_end - 1][0]
                merged_up.append((x, x_end, bar_top))
                i = run_end

            # Draw download rectangles first (blue)
            for x0, x1, bar_top in merged_down:
                packet = build_rt_draw_fill_rect(
                    x0,
                    bar_top,
                    x1,
                    bar_bottom,
                    r=down_color[0],
                    g=down_color[1],
                    b=down_color[2],
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.002)

            # Draw upload rectangles on top (red)
            for x0, x1, bar_top in merged_up:
                packet = build_rt_draw_fill_rect(
                    x0,
                    bar_top,
                    x1,
                    bar_bottom,
                    r=up_color[0],
                    g=up_color[1],
                    b=up_color[2],
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.002)

        # Draw "NET" label
        label_chars = [(c, CYAN) for c in "NET"]
        while len(label_chars) < 4:
            label_chars.append((" ", CYAN))

        bitmap, colors = render_line_bitmap(label_chars[:4], 4)
        for color in [CYAN]:
            color_bitmap = [
                [
                    1 if bitmap[y][x] and colors[y][x] == color else 0
                    for x in range(len(bitmap[0]))
                ]
                for y in range(len(bitmap))
            ]
            has_pixels = any(any(r) for r in color_bitmap)
            if has_pixels:
                packet = build_rt_draw_bitmap(
                    1,
                    y_start + 1,
                    4 * CHAR_WIDTH,
                    FONT_PIXEL_HEIGHT,
                    color_bitmap,
                    r=color[0],
                    g=color[1],
                    b=color[2],
                )
                await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
                await asyncio.sleep(0.005)

    async def draw_time_labels(self, y_pos: int) -> None:
        """Draw time axis labels."""
        # Show "now" on right, and time going back on left
        now_label = "now"
        ago_label = f"-{self.graph_width}s"

        # Create line with labels at ends
        line_chars: list[tuple[str, tuple[int, int, int]]] = []

        # Left side: -Xs ago
        for c in ago_label:
            line_chars.append((c, WHITE))

        # Padding in middle
        mid_space = self.cols - len(ago_label) - len(now_label)
        for _ in range(mid_space):
            line_chars.append((" ", WHITE))

        # Right side: now
        for c in now_label:
            line_chars.append((c, CYAN))

        # Draw at specified row
        row = y_pos // CHAR_HEIGHT
        await self.draw_line(row, line_chars)

    async def draw_branding(self, y_pixel: int) -> None:
        """Draw branding text at specified pixel y position."""
        brand = "EDISON.WATCH"
        # Center the text
        padding = (self.cols - len(brand)) // 2
        
        line_chars: list[tuple[str, tuple[int, int, int]]] = []
        for _ in range(padding):
            line_chars.append((" ", WHITE))
        
        # All white, bold effect by drawing twice offset
        for c in brand:
            line_chars.append((c, WHITE))
        
        while len(line_chars) < self.cols:
            line_chars.append((" ", WHITE))
        
        # Render bitmap for this line
        bitmap, colors = render_line_bitmap(line_chars[: self.cols], self.cols)
        
        # Draw at pixel position (not row)
        packet = build_rt_draw_bitmap(
            0,
            y_pixel,
            self.cols * CHAR_WIDTH,
            FONT_PIXEL_HEIGHT,
            bitmap,
            r=255,
            g=255,
            b=255,
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.01)
        
        # Bold effect: draw again offset by 1 pixel right
        packet = build_rt_draw_bitmap(
            1,
            y_pixel,
            self.cols * CHAR_WIDTH,
            FONT_PIXEL_HEIGHT,
            bitmap,
            r=255,
            g=255,
            b=255,
        )
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
        await asyncio.sleep(0.01)

    async def update_status(self) -> None:
        """Update the status display."""
        import time

        now = datetime.now()
        hostname = platform.node().split(".")[0][:8]

        cpu = get_cpu_percent()
        mem = get_memory_percent()

        # Get network rates
        net_bytes = get_network_bytes()
        current_time = time.time()
        net_up_kbps = 0.0
        net_down_kbps = 0.0

        if self.last_net_bytes is not None and self.last_net_time is not None:
            dt = current_time - self.last_net_time
            if dt > 0:
                bytes_sent = net_bytes[0] - self.last_net_bytes[0]
                bytes_recv = net_bytes[1] - self.last_net_bytes[1]
                net_up_kbps = (bytes_sent / 1024) / dt  # KB/s
                net_down_kbps = (bytes_recv / 1024) / dt  # KB/s

        self.last_net_bytes = net_bytes
        self.last_net_time = current_time

        self.sample_count += 1

        # Add to history
        self.cpu_history.append(cpu)
        self.mem_history.append(mem)
        self.net_up_history.append(net_up_kbps)
        self.net_down_history.append(net_down_kbps)

        if len(self.cpu_history) > self.graph_width:
            self.cpu_history = self.cpu_history[-self.graph_width :]
        if len(self.mem_history) > self.graph_width:
            self.mem_history = self.mem_history[-self.graph_width :]
        if len(self.net_up_history) > self.graph_width:
            self.net_up_history = self.net_up_history[-self.graph_width :]
        if len(self.net_down_history) > self.graph_width:
            self.net_down_history = self.net_down_history[-self.graph_width :]

        # Line 0: Hostname and time
        time_str = now.strftime("%H:%M:%S")
        line0_text = f"{hostname:<8} {time_str}"
        line0 = []
        for i, c in enumerate(line0_text[: self.cols]):
            if i < 8:
                line0.append((c, CYAN))
            else:
                line0.append((c, WHITE))
        while len(line0) < self.cols:
            line0.append((" ", WHITE))

        # Line 1: CPU and MEM percentages
        cpu_color = GREEN if cpu < 50 else YELLOW if cpu < 80 else RED
        mem_color = BLUE if mem < 50 else YELLOW if mem < 80 else RED
        line1_chars = []
        cpu_str = f"CPU:{int(cpu):3d}%"
        mem_str = f"MEM:{int(mem):2d}%"
        for c in cpu_str:
            line1_chars.append((c, cpu_color))
        line1_chars.append((" ", WHITE))
        for c in mem_str:
            line1_chars.append((c, mem_color))
        while len(line1_chars) < self.cols:
            line1_chars.append((" ", WHITE))

        # Line 2: Network speed
        net_str = f"D:{int(net_down_kbps):4d}K U:{int(net_up_kbps):3d}K"
        line2_chars = []
        for i, c in enumerate(net_str):
            if i < 7:  # Download part
                line2_chars.append((c, BLUE))
            else:  # Upload part
                line2_chars.append((c, RED))
        while len(line2_chars) < self.cols:
            line2_chars.append((" ", WHITE))

        # Draw header lines (3 lines = 21 pixels)
        await self.draw_line(0, line0)
        await self.draw_line(1, line1_chars[: self.cols])
        await self.draw_line(2, line2_chars[: self.cols])

        # CPU graph: y=22 (height 20)
        await self.draw_graph(22, self.cpu_history, "CPU", GREEN)

        # MEM graph: y=44 (height 20)
        await self.draw_graph(44, self.mem_history, "MEM", BLUE)

        # NET graph: y=66 (height 20)
        await self.draw_net_graph(66)

        # Time labels (row 13)
        await self.draw_time_labels(91)

        # Branding at very bottom
        await self.draw_branding(108)

    async def run(self, interval: float = 1.0) -> None:
        """Run the status display loop."""
        log.info(f"Starting status display (interval: {interval}s)")
        print("\nPress Ctrl+C to stop.\n")

        try:
            while True:
                await self.update_status()
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            log.info("Stopping...")


async def main() -> None:
    """Main entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(description="LED Status - System monitor")
    parser.add_argument("--address", type=str, help="BLE device address")
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Update interval in seconds"
    )
    args = parser.parse_args()

    if not HAS_PSUTIL:
        log.warning("psutil not installed, using fallback methods")

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

        status = LedStatus(client)
        await status.init_display()
        await status.run(interval=args.interval)

        await client.stop_notify(NOTIFY_CHAR_UUID)


if __name__ == "__main__":
    asyncio.run(main())
