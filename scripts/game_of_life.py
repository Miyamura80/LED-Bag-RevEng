"""
Conway's Game of Life on a 96x128 torus grid for the LED backpack.

Generates animated GIFs with various interesting starting patterns.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# Grid dimensions matching LED backpack
WIDTH = 96
HEIGHT = 128

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "backpack_media"


def step(grid: np.ndarray) -> np.ndarray:
    """
    Compute one step of Game of Life on a torus (wrapping edges).

    Args:
        grid: 2D numpy array where 1=alive, 0=dead.

    Returns:
        New grid state after one generation.
    """
    # Count neighbors using roll for torus wrapping
    neighbors = (
        np.roll(np.roll(grid, 1, 0), 1, 1)
        + np.roll(np.roll(grid, 1, 0), -1, 1)
        + np.roll(np.roll(grid, 1, 0), 0, 1)
        + np.roll(np.roll(grid, -1, 0), 1, 1)
        + np.roll(np.roll(grid, -1, 0), -1, 1)
        + np.roll(np.roll(grid, -1, 0), 0, 1)
        + np.roll(np.roll(grid, 0, 0), 1, 1)
        + np.roll(np.roll(grid, 0, 0), -1, 1)
    )

    # Apply rules: birth (3 neighbors) or survival (2-3 neighbors)
    new_grid = np.zeros_like(grid)
    new_grid[(grid == 1) & ((neighbors == 2) | (neighbors == 3))] = 1
    new_grid[(grid == 0) & (neighbors == 3)] = 1

    return new_grid


def place_pattern(grid: np.ndarray, pattern: np.ndarray, x: int, y: int) -> None:
    """Place a pattern on the grid at position (x, y), with torus wrapping."""
    h, w = pattern.shape
    for dy in range(h):
        for dx in range(w):
            grid[(y + dy) % HEIGHT, (x + dx) % WIDTH] = pattern[dy, dx]


# Classic patterns
def glider() -> np.ndarray:
    """Classic glider that moves diagonally."""
    return np.array(
        [
            [0, 1, 0],
            [0, 0, 1],
            [1, 1, 1],
        ]
    )


def lwss() -> np.ndarray:
    """Lightweight spaceship - moves horizontally."""
    return np.array(
        [
            [0, 1, 0, 0, 1],
            [1, 0, 0, 0, 0],
            [1, 0, 0, 0, 1],
            [1, 1, 1, 1, 0],
        ]
    )


def mwss() -> np.ndarray:
    """Middleweight spaceship."""
    return np.array(
        [
            [0, 0, 1, 0, 0, 0],
            [0, 1, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 0],
        ]
    )


def hwss() -> np.ndarray:
    """Heavyweight spaceship."""
    return np.array(
        [
            [0, 0, 1, 1, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 0],
        ]
    )


def gosper_glider_gun() -> np.ndarray:
    """Gosper glider gun - produces gliders forever."""
    gun = np.zeros((11, 38), dtype=np.uint8)
    # Left block
    gun[5, 1] = gun[5, 2] = gun[6, 1] = gun[6, 2] = 1
    # Left structure
    gun[3, 13] = gun[3, 14] = 1
    gun[4, 12] = gun[4, 16] = 1
    gun[5, 11] = gun[5, 17] = 1
    gun[6, 11] = gun[6, 15] = gun[6, 17] = gun[6, 18] = 1
    gun[7, 11] = gun[7, 17] = 1
    gun[8, 12] = gun[8, 16] = 1
    gun[9, 13] = gun[9, 14] = 1
    # Right structure
    gun[1, 25] = 1
    gun[2, 23] = gun[2, 25] = 1
    gun[3, 21] = gun[3, 22] = 1
    gun[4, 21] = gun[4, 22] = 1
    gun[5, 21] = gun[5, 22] = 1
    gun[6, 23] = gun[6, 25] = 1
    gun[7, 25] = 1
    # Right block
    gun[3, 35] = gun[3, 36] = gun[4, 35] = gun[4, 36] = 1
    return gun


def r_pentomino() -> np.ndarray:
    """R-pentomino - chaotic methuselah that stabilizes after 1103 generations."""
    return np.array(
        [
            [0, 1, 1],
            [1, 1, 0],
            [0, 1, 0],
        ]
    )


def acorn() -> np.ndarray:
    """Acorn - methuselah that takes 5206 generations to stabilize."""
    return np.array(
        [
            [0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0],
            [1, 1, 0, 0, 1, 1, 1],
        ]
    )


def diehard() -> np.ndarray:
    """Diehard - dies after exactly 130 generations."""
    return np.array(
        [
            [0, 0, 0, 0, 0, 0, 1, 0],
            [1, 1, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 1, 1, 1],
        ]
    )


def pulsar() -> np.ndarray:
    """Pulsar - period 3 oscillator."""
    p = np.zeros((15, 15), dtype=np.uint8)
    # Define one quadrant and reflect
    cells = [
        (1, 4),
        (1, 5),
        (1, 6),
        (2, 4),
        (2, 6),
        (3, 4),
        (3, 5),
        (3, 6),
        (4, 1),
        (4, 2),
        (4, 3),
        (4, 6),
        (5, 1),
        (5, 3),
        (6, 1),
        (6, 2),
        (6, 3),
        (6, 4),
        (6, 5),
        (6, 6),
    ]
    for r, c in cells:
        p[r, c] = 1
        p[r, 14 - c] = 1
        p[14 - r, c] = 1
        p[14 - r, 14 - c] = 1
    return p


def pentadecathlon() -> np.ndarray:
    """Pentadecathlon - period 15 oscillator."""
    return np.array(
        [
            [0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
            [1, 1, 0, 1, 1, 1, 1, 0, 1, 1],
            [0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
        ]
    )


def create_scenario_glider_armada(grid: np.ndarray) -> None:
    """Multiple gliders flying across the torus in formation."""
    g = glider()
    # Create a diagonal armada
    for i in range(8):
        place_pattern(grid, g, 10 + i * 12, 10 + i * 12)
    # Counter-armada
    g_flipped = np.fliplr(g)
    for i in range(6):
        place_pattern(grid, g_flipped, 80 - i * 10, 20 + i * 15)


def create_scenario_spaceship_fleet(grid: np.ndarray) -> None:
    """Fleet of various spaceships."""
    # LWSS fleet
    for i in range(4):
        place_pattern(grid, lwss(), 5, 10 + i * 20)
    # MWSS
    for i in range(3):
        place_pattern(grid, mwss(), 40, 15 + i * 25)
    # HWSS
    for i in range(2):
        place_pattern(grid, hwss(), 70, 25 + i * 40)


def create_scenario_guns_and_chaos(grid: np.ndarray) -> None:
    """Gosper guns facing each other with chaos in the middle."""
    gun = gosper_glider_gun()
    # Gun at top-left
    place_pattern(grid, gun, 5, 10)
    # Gun at bottom (flipped)
    gun_flipped = np.flipud(gun)
    place_pattern(grid, gun_flipped, 5, 85)
    # Chaos in middle
    place_pattern(grid, r_pentomino(), 45, 55)
    place_pattern(grid, acorn(), 30, 60)


def create_scenario_oscillator_garden(grid: np.ndarray) -> None:
    """A garden of oscillators."""
    # Pulsars
    for i in range(3):
        for j in range(2):
            place_pattern(grid, pulsar(), 10 + i * 30, 20 + j * 50)
    # Pentadecathlons
    for i in range(4):
        place_pattern(grid, pentadecathlon(), 5 + i * 24, 100)


def create_scenario_methuselah_explosion(grid: np.ndarray) -> None:
    """Multiple methuselahs creating long-lived chaos."""
    place_pattern(grid, r_pentomino(), 20, 30)
    place_pattern(grid, acorn(), 60, 50)
    place_pattern(grid, diehard(), 40, 80)
    place_pattern(grid, r_pentomino(), 70, 100)


def create_scenario_random_soup(grid: np.ndarray, density: float = 0.3) -> None:
    """Random initial configuration (primordial soup)."""
    np.random.seed(42)  # Reproducible
    grid[:] = (np.random.random((HEIGHT, WIDTH)) < density).astype(np.uint8)


def create_scenario_collision_course(grid: np.ndarray) -> None:
    """Spaceships on collision courses."""
    # Horizontal LWSSs from left
    for i in range(5):
        place_pattern(grid, lwss(), 5, 20 + i * 22)
    # Gliders from various angles
    g = glider()
    for i in range(10):
        place_pattern(grid, g, 30 + i * 6, 5 + i * 10)
    # Some from the right (flipped)
    g_flip = np.fliplr(g)
    for i in range(8):
        place_pattern(grid, g_flip, 85, 10 + i * 15)


SCENARIOS = {
    "glider_armada": create_scenario_glider_armada,
    "spaceship_fleet": create_scenario_spaceship_fleet,
    "guns_and_chaos": create_scenario_guns_and_chaos,
    "oscillator_garden": create_scenario_oscillator_garden,
    "methuselah_explosion": create_scenario_methuselah_explosion,
    "random_soup": create_scenario_random_soup,
    "collision_course": create_scenario_collision_course,
}


def generate_frames(
    scenario_name: str,
    num_frames: int = 200,
    alive_color: tuple[int, int, int] = (0, 255, 0),
    dead_color: tuple[int, int, int] = (0, 0, 0),
) -> list[Image.Image]:
    """
    Generate animation frames for a scenario.

    Args:
        scenario_name: Name of the starting scenario.
        num_frames: Number of frames to generate.
        alive_color: RGB color for living cells.
        dead_color: RGB color for dead cells.

    Returns:
        List of PIL Image frames.
    """
    grid = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

    if scenario_name not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario: {scenario_name}. Choose from: {list(SCENARIOS.keys())}"
        )

    SCENARIOS[scenario_name](grid)

    frames: list[Image.Image] = []
    for _ in range(num_frames):
        # Create image from grid
        img = Image.new("RGB", (WIDTH, HEIGHT))
        pixels = img.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                pixels[x, y] = alive_color if grid[y, x] else dead_color
        frames.append(img)

        # Advance simulation
        grid = step(grid)

    return frames


def save_gif(
    frames: list[Image.Image],
    output_path: Path,
    duration: int = 100,
    loop: int = 0,
) -> None:
    """
    Save frames as an animated GIF.

    Args:
        frames: List of PIL Image frames.
        output_path: Path to save the GIF.
        duration: Duration of each frame in milliseconds.
        loop: Loop count (0 = infinite).
    """
    if not frames:
        raise ValueError("No frames to save")

    # Convert to palette mode for smaller file size
    palette_frames = [
        frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=8) for frame in frames
    ]

    palette_frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration,
        loop=loop,
        optimize=True,
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Game of Life GIFs for LED backpack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available scenarios: {', '.join(SCENARIOS.keys())}",
    )
    parser.add_argument(
        "--scenario",
        "-s",
        choices=list(SCENARIOS.keys()),
        default="methuselah_explosion",
        help="Starting scenario (default: methuselah_explosion)",
    )
    parser.add_argument(
        "--frames",
        "-f",
        type=int,
        default=200,
        help="Number of frames to generate (default: 200)",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=100,
        help="Duration per frame in ms (default: 100)",
    )
    parser.add_argument(
        "--color",
        "-c",
        default="00ff00",
        help="Alive cell color as hex (default: 00ff00 / green)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path (default: backpack_media/game_of_life_{scenario}.gif)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Generate GIFs for all scenarios",
    )

    args = parser.parse_args()

    # Parse color
    color_hex = args.color.lstrip("#")
    alive_color = (
        int(color_hex[0:2], 16),
        int(color_hex[2:4], 16),
        int(color_hex[4:6], 16),
    )
    dead_color = (0, 0, 0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scenarios_to_generate = list(SCENARIOS.keys()) if args.all else [args.scenario]

    for scenario in scenarios_to_generate:
        output_path = (
            args.output
            if args.output and not args.all
            else OUTPUT_DIR / f"game_of_life_{scenario}.gif"
        )

        print(f"Generating {scenario} ({args.frames} frames)...")
        frames = generate_frames(
            scenario,
            num_frames=args.frames,
            alive_color=alive_color,
            dead_color=dead_color,
        )

        print(f"Saving to {output_path}...")
        save_gif(frames, output_path, duration=args.duration)
        print(f"Done! File size: {output_path.stat().st_size / 1024:.1f} KB")
        print()


if __name__ == "__main__":
    main()
