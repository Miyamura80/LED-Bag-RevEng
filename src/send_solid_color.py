"""
CLI script to send colors and patterns to a LOY SPACE LED backpack.

Uses the YS-protocol (aa55ffff) to upload GIF images.
"""

import argparse
import asyncio
import sys

from loguru import logger as log

from src.led_client import LedBackpackClient, discover_backpack
from src.led_protocol import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    WRITE_CHAR_UUID,
)
from src.utils.logging_config import setup_logging


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send colors and patterns to a LOY SPACE LED backpack",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Device name (substring match, e.g., YS6249)",
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
        "--pattern",
        type=str,
        choices=["solid", "grid"],
        default="solid",
        help="Pattern type: solid color or checkerboard grid",
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=16,
        help="Grid cell size in pixels (for grid pattern)",
    )
    parser.add_argument(
        "--color2",
        type=str,
        default="#000000",
        help="Second color for grid pattern",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help=f"Matrix width (pixels, default: {DEFAULT_WIDTH})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help=f"Matrix height (pixels, default: {DEFAULT_HEIGHT})",
    )
    parser.add_argument(
        "--char-uuid",
        type=str,
        default=WRITE_CHAR_UUID,
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
        default=0.05,
        help="Delay between BLE writes (seconds)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Send reset/clear command before the pattern",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=None,
        help="Optional brightness (0-255)",
    )
    return parser.parse_args()


async def main() -> None:
    setup_logging()
    args = _parse_args()

    address = args.address
    width = args.width
    height = args.height

    if not address:
        log.info("Scanning for device...")
        address, detected_width, detected_height = await discover_backpack(
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
    log.info("Pattern: {}", args.pattern)
    log.info("Color: {}", args.color)
    if args.pattern == "grid":
        log.info("Color2: {}, Grid size: {}", args.color2, args.grid_size)
    log.info("Write characteristic: {}", args.char_uuid)
    if address:
        log.info("Target address: {}", address)

    log.info("Connecting and sending...")
    async with LedBackpackClient(
        address,
        write_char_uuid=args.char_uuid,
        delay=args.delay,
    ) as client:
        if args.clear:
            await client.clear()
        if args.brightness is not None:
            if args.brightness < 0 or args.brightness > 255:
                raise ValueError("Brightness must be 0-255")
            await client.set_brightness(args.brightness)

        if args.pattern == "grid":
            await client.set_grid_pattern(
                width=width,
                height=height,
                grid_size=args.grid_size,
                color1=args.color,
                color2=args.color2,
            )
        else:
            await client.set_solid_color(args.color, width=width, height=height)
    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
