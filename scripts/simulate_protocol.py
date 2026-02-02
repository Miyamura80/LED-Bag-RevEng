#!/usr/bin/env python3
"""
Simulate LOY SPACE BLE protocol without a device.

Builds the same packets as the sender and prints hex dumps (and optional JSON)
so you can compare with HCI snoop captures or transcribe to another runtime.
"""

import argparse
import json
import sys

# Allow running from repo root
sys.path.insert(0, "")

from src.led_protocol import (
    CMD_BRIGHTNESS,
    CMD_CLEAR,
    CMD_INIT,
    CMD_MODE,
    CMD_SWITCH,
    DEFAULT_CHUNK_SIZE,
    MODE_MAP,
    SWITCH_MAP,
    WRITE_CHAR_UUID,
    build_image_command_chunks,
    build_simple_command,
)


def chunk_to_hex(chunk: bytearray) -> str:
    return chunk.hex().upper()


def run_simulate(
    *,
    init: bool = False,
    clear: bool = False,
    brightness: int | None = None,
    mode: str | None = None,
    switch: str | None = None,
    color: str | None = None,
    width: int = 96,
    height: int = 16,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    output_json: bool = False,
    char_uuid: str = WRITE_CHAR_UUID,
) -> None:
    chunks: list[bytearray] = []
    if init:
        chunks.append(build_simple_command(CMD_INIT, bytearray([0x01])))
    if switch is not None:
        chunks.append(
            build_simple_command(CMD_SWITCH, bytearray([SWITCH_MAP[switch]])),
        )
    if mode is not None:
        chunks.append(
            build_simple_command(CMD_MODE, bytearray([MODE_MAP[mode]])),
        )
    if clear:
        chunks.append(build_simple_command(CMD_CLEAR))
    if brightness is not None:
        if brightness < 0 or brightness > 255:
            raise ValueError("Brightness must be 0-255")
        chunks.append(
            build_simple_command(CMD_BRIGHTNESS, bytearray([brightness])),
        )
    if color is not None:
        chunks.extend(
            build_image_command_chunks(
                width=width,
                height=height,
                color=color,
                chunk_size=chunk_size,
            ),
        )

    if output_json:
        out = {
            "characteristic_uuid": char_uuid,
            "chunk_size_bytes": chunk_size,
            "num_chunks": len(chunks),
            "chunks": [
                {"index": i + 1, "hex": chunk_to_hex(c), "length": len(c)}
                for i, c in enumerate(chunks)
            ],
        }
        print(json.dumps(out, indent=2))
        return

    print(f"Characteristic: {char_uuid}")
    print(f"Chunk size: {chunk_size} bytes")
    print(f"Total chunks: {len(chunks)}\n")
    for i, c in enumerate(chunks, start=1):
        print(f"--- Chunk {i} ({len(c)} bytes) ---")
        print(chunk_to_hex(c))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate LOY SPACE BLE protocol (no device). Print hex packets.",
    )
    parser.add_argument("--init", action="store_true", help="Add init command")
    parser.add_argument("--clear", action="store_true", help="Add clear command")
    parser.add_argument(
        "--brightness",
        type=int,
        default=None,
        metavar="0-255",
        help="Add brightness command",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=sorted(MODE_MAP.keys()),
        default=None,
        help="Add mode command",
    )
    parser.add_argument(
        "--switch",
        type=str,
        choices=sorted(SWITCH_MAP.keys()),
        default=None,
        help="Add switch on/off command",
    )
    parser.add_argument(
        "--color",
        type=str,
        default=None,
        help="Add solid color image (hex e.g. #ff0000)",
    )
    parser.add_argument("--width", type=int, default=96, help="Matrix width")
    parser.add_argument("--height", type=int, default=16, help="Matrix height")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Max bytes per BLE write",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output JSON instead of plain hex",
    )
    args = parser.parse_args()

    if not any(
        [
            args.init,
            args.clear,
            args.brightness is not None,
            args.mode is not None,
            args.switch is not None,
            args.color is not None,
        ]
    ):
        parser.error(
            "At least one of --init, --clear, --brightness, --mode, --switch, --color required"
        )

    run_simulate(
        init=args.init,
        clear=args.clear,
        brightness=args.brightness,
        mode=args.mode,
        switch=args.switch,
        color=args.color,
        width=args.width,
        height=args.height,
        chunk_size=args.chunk_size,
        output_json=args.output_json,
    )


if __name__ == "__main__":
    main()
