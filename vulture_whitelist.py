"""
Vulture whitelist for intentionally unused code.

These are public API elements that are meant to be used by consumers of the module,
or experimental features that are not yet integrated into the main codebase.
"""

# Graffiti mode constants and functions - experimental, for future use
from src.led_protocol import (
    GRAFFITI_SERVICE_UUID,
    GRAFFITI_CHAR_UUID,
    GRAFFITI_POWER_ON,
    GRAFFITI_POWER_OFF,
    GRAFFITI_SLIDESHOW,
    build_graffiti_init_sequence,
    build_graffiti_pixel_batch,
    build_graffiti_fill_command,
    # rt_draw commands - discovered from APK, public API for real-time drawing
    RT_DRAW_CMD_BYTE,
    RT_DRAW_TYPE_PIXELS,
    build_rt_draw_clear_screen,
    build_rt_draw_pixels,
    build_pgm_play_stop,
    GAME_CMD_BYTE,
)

# Probe characteristics - intentionally unused constant for reference
from src.probe_characteristics import GRAFFITI_CHAR_PREFIXES

# Programmatic API for verify_backpack
from src.verify_backpack import get_device_info

# Suppress vulture warnings
_ = (
    GRAFFITI_SERVICE_UUID,
    GRAFFITI_CHAR_UUID,
    GRAFFITI_POWER_ON,
    GRAFFITI_POWER_OFF,
    GRAFFITI_SLIDESHOW,
    build_graffiti_init_sequence,
    build_graffiti_pixel_batch,
    build_graffiti_fill_command,
    GRAFFITI_CHAR_PREFIXES,
    get_device_info,
    # rt_draw commands
    RT_DRAW_CMD_BYTE,
    RT_DRAW_TYPE_PIXELS,
    build_rt_draw_clear_screen,
    build_rt_draw_pixels,
    build_pgm_play_stop,
    GAME_CMD_BYTE,
)
