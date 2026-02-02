"""
CLI to select and upload media files to a LOY SPACE LED backpack.

Converts media files to properly sized GIFs using ffmpeg before upload.
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import click

from src.led_client import LedBackpackClient, discover_backpack
from src.led_protocol import DEFAULT_HEIGHT, DEFAULT_WIDTH
from src.utils.logging_config import setup_logging

MEDIA_DIR = Path(__file__).parent.parent / "backpack_media"
SUPPORTED_EXTENSIONS = {
    ".gif",
    ".mp4",
    ".mov",
    ".webm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

# Conservative limit for stability (device can be unstable near 50KB)
MAX_GIF_SIZE = 40_000


def _get_media_files() -> list[Path]:
    """List all supported media files in the backpack_media folder."""
    if not MEDIA_DIR.exists():
        return []
    files = []
    for f in MEDIA_DIR.iterdir():
        if f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return sorted(files, key=lambda x: x.name.lower())


def _convert_to_gif(
    input_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = 10,
    loop: int = 0,
    max_colors: int = 256,
    duration: float | None = None,
    contrast: float = 1.0,
    saturation: float = 1.0,
    gamma: float = 1.0,
) -> bytes:
    """
    Convert a media file to a properly sized GIF using ffmpeg.

    Args:
        input_path: Path to input media file.
        width: Target width in pixels.
        height: Target height in pixels.
        fps: Frames per second for the output GIF.
        loop: Loop count (0 = infinite).
        max_colors: Maximum colors in palette (lower = smaller file).
        duration: Max duration in seconds (None = full length).
        contrast: Contrast adjustment (1.0 = normal, >1 = more contrast).
        saturation: Saturation adjustment (1.0 = normal, >1 = more vivid).
        gamma: Gamma/brightness (1.0 = normal, <1 = brighter, >1 = darker).

    Returns:
        Raw GIF bytes.
    """
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Build ffmpeg command
        # Apply contrast/saturation/gamma, scale, pad, and generate palette
        eq_filter = ""
        if contrast != 1.0 or saturation != 1.0 or gamma != 1.0:
            eq_filter = f"eq=contrast={contrast}:saturation={saturation}:gamma={gamma},"
        filter_complex = (
            f"{eq_filter}"
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"split[s0][s1];[s0]palettegen=max_colors={max_colors}[p];[s1][p]paletteuse"
        )

        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i",
            str(input_path),
        ]

        # Add duration limit if specified
        if duration is not None:
            cmd.extend(["-t", str(duration)])

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-loop",
                str(loop),
                tmp_path,
            ]
        )

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            click.echo(f"ffmpeg error: {result.stderr}", err=True)
            raise click.ClickException("ffmpeg conversion failed")

        # Read the generated GIF
        gif_data = Path(tmp_path).read_bytes()
        return gif_data

    finally:
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)


def _convert_with_size_limit(
    input_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = 10,
    contrast: float = 1.0,
    saturation: float = 1.0,
    gamma: float = 1.0,
) -> bytes:
    """
    Convert media to GIF, automatically reducing quality to fit size limit.

    Tries progressively smaller settings until under MAX_GIF_SIZE.
    """
    # Try different settings: (fps, max_colors, duration_limit)
    # Prioritize keeping full animation by reducing fps/colors before truncating
    attempts = [
        (fps, 256, None),  # Full quality
        (fps, 128, None),  # Reduced colors
        (fps, 64, None),  # Further reduced colors
        (max(fps // 2, 4), 64, None),  # Half fps
        (4, 64, None),  # 4 fps
        (3, 64, None),  # 3 fps
        (2, 64, None),  # 2 fps (keeps all frames, just slower)
        (2, 32, None),  # 2 fps, fewer colors
        (1, 32, None),  # 1 fps slideshow
    ]

    for attempt_fps, colors, duration in attempts:
        click.echo(
            f"Trying: {attempt_fps}fps, {colors} colors"
            + (f", {duration}s" if duration else "")
            + "..."
        )
        gif_data = _convert_to_gif(
            input_path,
            width=width,
            height=height,
            fps=attempt_fps,
            max_colors=colors,
            duration=duration,
            contrast=contrast,
            saturation=saturation,
            gamma=gamma,
        )

        if len(gif_data) <= MAX_GIF_SIZE:
            click.echo(
                f"Success: {len(gif_data)} bytes "
                f"({len(gif_data) * 100 // MAX_GIF_SIZE}% of limit)"
            )
            return gif_data

        click.echo(f"Too large: {len(gif_data)} bytes (limit: {MAX_GIF_SIZE})")

    raise click.ClickException(
        f"Could not reduce GIF below {MAX_GIF_SIZE} bytes. "
        "Try a shorter/simpler source file."
    )


async def _upload_gif(
    gif_data: bytes,
    device_name: str | None,
    device_address: str | None,
    brightness: int | None,
    timeout: float,
) -> None:
    """Connect to device and upload GIF."""
    address = device_address

    if not address:
        click.echo("Scanning for device...")
        address, _, _ = await discover_backpack(
            name=device_name,
            address=device_address,
            timeout=timeout,
        )
        if address is None:
            raise click.ClickException("Device not found. Use --name or --address.")

    click.echo(f"Connecting to {address}...")
    async with LedBackpackClient(address) as client:
        if brightness is not None:
            click.echo(f"Setting brightness to {brightness}...")
            await client.set_brightness(brightness)
        await client.upload_gif(gif_data)
    click.echo("Done!")


@click.command()
@click.option(
    "--file",
    "-f",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to media file (skips interactive selection)",
)
@click.option(
    "--name",
    "-n",
    "device_name",
    default=None,
    help="Device name substring (e.g., YS6249)",
)
@click.option(
    "--address",
    "-a",
    "device_address",
    default=None,
    help="Device BLE address/UUID",
)
@click.option(
    "--width",
    "-w",
    default=DEFAULT_WIDTH,
    show_default=True,
    help="Target width in pixels",
)
@click.option(
    "--height",
    "-h",
    "height",
    default=DEFAULT_HEIGHT,
    show_default=True,
    help="Target height in pixels",
)
@click.option(
    "--fps",
    default=10,
    show_default=True,
    help="Frames per second for GIF",
)
@click.option(
    "--brightness",
    "-b",
    type=int,
    default=None,
    help="Brightness level (0-255)",
)
@click.option(
    "--timeout",
    "-t",
    default=10.0,
    show_default=True,
    help="BLE scan timeout in seconds",
)
@click.option(
    "--contrast",
    "-c",
    default=1.0,
    show_default=True,
    help="Contrast adjustment (1.0 = normal, 1.5 = more contrast)",
)
@click.option(
    "--saturation",
    "-s",
    default=1.0,
    show_default=True,
    help="Saturation adjustment (1.0 = normal, 1.5 = more vivid)",
)
@click.option(
    "--gamma",
    "-g",
    default=1.0,
    show_default=True,
    help="Gamma/brightness (1.0 = normal, 0.5 = brighter, 2.0 = darker)",
)
@click.option(
    "--list",
    "-l",
    "list_files",
    is_flag=True,
    help="List available media files and exit",
)
def main(
    file_path: Path | None,
    device_name: str | None,
    device_address: str | None,
    width: int,
    height: int,
    fps: int,
    brightness: int | None,
    timeout: float,
    contrast: float,
    saturation: float,
    gamma: float,
    list_files: bool,
) -> None:
    """Upload media files to a LOY SPACE LED backpack.

    Converts images/videos to properly sized GIFs using ffmpeg.
    Files are selected from the backpack_media/ folder.
    """
    setup_logging()

    # Get available media files
    media_files = _get_media_files()

    if list_files:
        if not media_files:
            click.echo("No media files found in backpack_media/")
        else:
            click.echo(f"Media files in {MEDIA_DIR}:")
            for f in media_files:
                click.echo(f"  - {f.name}")
        return

    # Select file
    if file_path is None:
        if not media_files:
            raise click.ClickException(
                f"No media files found in {MEDIA_DIR}. "
                "Add images/videos or use --file to specify a path."
            )

        click.echo(f"\nAvailable media files in {MEDIA_DIR.name}/:")
        for i, f in enumerate(media_files, start=1):
            click.echo(f"  [{i}] {f.name}")

        choice = click.prompt(
            "\nSelect file number",
            type=click.IntRange(1, len(media_files)),
        )
        file_path = media_files[choice - 1]

    click.echo(f"\nSelected: {file_path.name}")
    click.echo(f"Target size: {width}x{height} @ {fps}fps")
    if contrast != 1.0 or saturation != 1.0 or gamma != 1.0:
        click.echo(
            f"Effects: contrast={contrast}, saturation={saturation}, gamma={gamma}"
        )
    click.echo(f"Max GIF size: {MAX_GIF_SIZE} bytes (~{MAX_GIF_SIZE // 1024}KB)")

    # Convert to GIF (auto-reduces quality to fit size limit)
    gif_data = _convert_with_size_limit(
        file_path,
        width=width,
        height=height,
        fps=fps,
        contrast=contrast,
        saturation=saturation,
        gamma=gamma,
    )

    # Upload
    asyncio.run(
        _upload_gif(
            gif_data,
            device_name=device_name,
            device_address=device_address,
            brightness=brightness,
            timeout=timeout,
        )
    )


if __name__ == "__main__":
    main()
