import pytest

from src.led_protocol import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAGIC_HEADER,
    _parse_color,
    build_brightness_command,
    build_reset_command,
    build_solid_color_gif,
    build_solid_color_packets,
)
from tests.test_template import TestTemplate


class TestSendSolidColor(TestTemplate):
    def test_parse_color_accepts_hex(self):
        """Verify color parsing for various hex formats."""
        assert _parse_color("#ff0000") == (255, 0, 0)
        assert _parse_color("00ff00") == (0, 255, 0)
        assert _parse_color("#0f0") == (0, 255, 0)
        assert _parse_color("0x00ff00") == (0, 255, 0)

    def test_parse_color_rejects_invalid(self):
        """Verify invalid colors are rejected."""
        with pytest.raises(ValueError):
            _parse_color("invalid")
        with pytest.raises(ValueError):
            _parse_color("#gg0000")

    def test_default_dimensions(self):
        """Verify default display dimensions."""
        assert DEFAULT_WIDTH == 96
        assert DEFAULT_HEIGHT == 128
        assert DEFAULT_CHUNK_SIZE == 196

    def test_solid_color_gif_creates_valid_gif(self):
        """Verify GIF creation for solid colors."""
        gif = build_solid_color_gif(width=16, height=16, color="#ff0000")
        # Check GIF header (GIF87a or GIF89a are both valid)
        assert gif[:3] == b"GIF"
        assert gif[3:6] in (b"87a", b"89a")
        assert gif[-1] == 0x3B

    def test_solid_color_packets_have_magic_header(self):
        """Verify all packets have the YS-protocol magic header."""
        packets = build_solid_color_packets(width=16, height=16, color="#00ff00")
        for packet in packets:
            assert packet[:4] == bytearray(MAGIC_HEADER)

    def test_reset_command_has_correct_format(self):
        """Verify reset command format."""
        cmd = build_reset_command()
        assert cmd[:4] == bytearray(MAGIC_HEADER)
        assert len(cmd) == 16

    def test_brightness_command_range(self):
        """Verify brightness commands for valid range."""
        for level in range(16):
            cmd = build_brightness_command(level)
            assert cmd[:4] == bytearray(MAGIC_HEADER)
            assert cmd[13] == level

    def test_brightness_command_invalid_range(self):
        """Verify brightness rejects out-of-range values."""
        with pytest.raises(ValueError):
            build_brightness_command(-1)
        with pytest.raises(ValueError):
            build_brightness_command(16)

    def test_solid_color_packets_count(self):
        """Verify packet count for a small GIF."""
        packets = build_solid_color_packets(width=16, height=16, color="#0000ff")
        # At minimum: reset, ready, 1 data packet, 2x complete
        assert len(packets) >= 5
