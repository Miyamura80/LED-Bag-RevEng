"""
Draw a maze on the LED backpack one line at a time using rt_draw commands.

This demonstrates real-time drawing capabilities discovered from APK decompilation.

Usage:
    uv run python -m src.draw_maze
    uv run python -m src.draw_maze --speed 0.1  # Faster
    uv run python -m src.draw_maze --color "#00ff00"  # Green maze
"""

import asyncio
import argparse
import colorsys
import random

from bleak import BleakClient, BleakScanner
from loguru import logger as log

from src.led_protocol import (
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    build_rt_draw_fill_rect,
    build_rt_draw_clear_screen,
    build_reset_command,
    build_ready_command,
    build_game_mode,
)
from src.utils.logging_config import setup_logging


# Simple maze stored as list of walls (x0, y0, x1, y1)
# This is a hand-crafted maze for a 96x128 display
def generate_maze_walls(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    cell_size: int = 8,
) -> list[tuple[int, int, int, int]]:
    """
    Generate maze walls using recursive backtracking.

    Returns list of (x0, y0, x1, y1) wall rectangles.
    """
    cols = width // cell_size
    rows = height // cell_size

    # Initialize maze grid (True = wall exists)
    # We'll track which cells have been visited
    visited = [[False] * cols for _ in range(rows)]
    walls_h = [[True] * cols for _ in range(rows + 1)]  # Horizontal walls
    walls_v = [[True] * (cols + 1) for _ in range(rows)]  # Vertical walls

    def carve(row: int, col: int) -> None:
        visited[row][col] = True
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        random.shuffle(directions)

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if 0 <= new_row < rows and 0 <= new_col < cols:
                if not visited[new_row][new_col]:
                    # Remove wall between current and new cell
                    if dr == 0:  # Horizontal movement
                        walls_v[row][max(col, new_col)] = False
                    else:  # Vertical movement
                        walls_h[max(row, new_row)][col] = False
                    carve(new_row, new_col)

    # Start from top-left
    carve(0, 0)

    # Convert to wall rectangles
    walls = []
    wall_thickness = 2

    # Add horizontal walls
    for row in range(rows + 1):
        y = row * cell_size
        if y + wall_thickness > height:
            y = height - wall_thickness
        for col in range(cols):
            if walls_h[row][col]:
                x0 = col * cell_size
                x1 = min((col + 1) * cell_size - 1, width - 1)
                walls.append((x0, y, x1, min(y + wall_thickness - 1, height - 1)))

    # Add vertical walls
    for row in range(rows):
        for col in range(cols + 1):
            if walls_v[row][col]:
                x = col * cell_size
                if x + wall_thickness > width:
                    x = width - wall_thickness
                y0 = row * cell_size
                y1 = min((row + 1) * cell_size - 1, height - 1)
                walls.append((x, y0, min(x + wall_thickness - 1, width - 1), y1))

    return walls


async def find_device(name_prefix: str = "YS") -> str | None:
    """Scan for LED backpack device."""
    log.info(f"Scanning for devices starting with '{name_prefix}'...")
    devices = await BleakScanner.discover(timeout=20.0)
    for device in devices:
        if device.name and device.name.startswith(name_prefix):
            log.info(f"Found device: {device.name} ({device.address})")
            return device.address
    return None


async def draw_maze(
    address: str,
    speed: float = 0.01,
    color: tuple[int, int, int] | None = None,
    rainbow: bool = True,
    loops: int = 1,
) -> None:
    """Draw maze on the LED backpack with optional color rotation."""
    log.info(f"Connecting to {address}...")

    async with BleakClient(address) as client:
        log.info("Connected!")

        # Enable notifications
        def notification_handler(sender: int, data: bytearray) -> None:
            log.debug(f"Notification: {data.hex()}")

        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)
        await asyncio.sleep(0.5)

        # Step 0: Reset device (stops any running playback)
        log.info("Sending RESET...")
        await client.write_gatt_char(WRITE_CHAR_UUID, build_reset_command())
        await asyncio.sleep(0.5)

        log.info("Sending READY...")
        await client.write_gatt_char(WRITE_CHAR_UUID, build_ready_command())
        await asyncio.sleep(0.5)

        # Enter graffiti mode (game id=16) - stops idle animation
        log.info("Entering graffiti mode...")
        await client.write_gatt_char(WRITE_CHAR_UUID, build_game_mode(16))
        await asyncio.sleep(1.0)

        # Generate maze once
        log.info("Generating maze...")
        walls = generate_maze_walls(cell_size=8)
        log.info(f"Generated {len(walls)} wall segments")

        # Draw maze multiple times with rotating hue
        for loop_num in range(loops):
            hue_offset = loop_num / loops if loops > 1 else 0.0
            log.info(
                f"Drawing maze {loop_num + 1}/{loops} (hue offset: {hue_offset:.2f})"
            )

            # Clear screen before each redraw
            packet = build_rt_draw_clear_screen(sno=0)
            await client.write_gatt_char(WRITE_CHAR_UUID, packet)
            await asyncio.sleep(0.1)

            # Draw each wall
            for i, (x0, y0, x1, y1) in enumerate(walls):
                # Clamp coordinates to valid range
                x0 = max(0, min(x0, DEFAULT_WIDTH - 1))
                y0 = max(0, min(y0, DEFAULT_HEIGHT - 1))
                x1 = max(0, min(x1, DEFAULT_WIDTH - 1))
                y1 = max(0, min(y1, DEFAULT_HEIGHT - 1))

                if x0 > x1 or y0 > y1:
                    continue

                # Get color - rainbow based on position or fixed
                if rainbow:
                    r, g, b = rainbow_color(
                        x0, y0, DEFAULT_WIDTH, DEFAULT_HEIGHT, hue_offset
                    )
                elif color:
                    r, g, b = color
                else:
                    r, g, b = (0, 255, 0)  # Default green

                # Use sno=0 as confirmed working
                packet = build_rt_draw_fill_rect(x0, y0, x1, y1, r=r, g=g, b=b, sno=0)
                await client.write_gatt_char(WRITE_CHAR_UUID, packet)

                if i % 50 == 0:
                    log.info(f"  Wall {i + 1}/{len(walls)}")

                # Small delay between commands
                await asyncio.sleep(speed)

        await client.stop_notify(NOTIFY_CHAR_UUID)
        log.info("Maze complete!")


def parse_color(color_str: str) -> tuple[int, int, int]:
    """Parse hex color string to RGB tuple."""
    color_str = color_str.strip().lstrip("#")
    if len(color_str) == 3:
        color_str = "".join(c * 2 for c in color_str)
    r = int(color_str[0:2], 16)
    g = int(color_str[2:4], 16)
    b = int(color_str[4:6], 16)
    return (r, g, b)


def rainbow_color(
    x: int, y: int, width: int, height: int, hue_offset: float = 0.0
) -> tuple[int, int, int]:
    """Get rainbow color based on XY position with optional hue rotation."""
    # Create a diagonal gradient for nice rainbow effect
    # Hue ranges from 0.0 to 1.0 based on position
    hue = ((x / width) + (y / height)) / 2.0 + hue_offset
    hue = hue % 1.0  # Wrap around
    # Full saturation and brightness
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


async def main() -> None:
    """Main entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(description="Draw a maze on the LED backpack")
    parser.add_argument(
        "--address",
        type=str,
        help="BLE device address (will scan if not provided)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.01,
        help="Delay between drawing each wall segment (seconds)",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=5,
        help="Number of times to redraw with rotating colors",
    )
    parser.add_argument(
        "--color",
        type=str,
        default=None,
        help="Maze wall color (hex). If not set, uses rainbow.",
    )
    parser.add_argument(
        "--no-rainbow",
        action="store_true",
        help="Disable rainbow mode (use --color or default green)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible mazes",
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    address = args.address
    if not address:
        address = await find_device()
        if not address:
            log.error("No device found!")
            return

    rainbow = not args.no_rainbow and args.color is None
    color = parse_color(args.color) if args.color else None
    await draw_maze(
        address, speed=args.speed, color=color, rainbow=rainbow, loops=args.loops
    )


if __name__ == "__main__":
    asyncio.run(main())
