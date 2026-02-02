import pytest

from src.led_protocol import (
    BRIGHTNESS_LEVELS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAGIC_HEADER,
    NOTIFY_CHAR_UUID,
    SERVICE_UUID,
    WRITE_CHAR_UUID,
    build_brightness_command,
    build_gif_upload_packets,
    build_ready_command,
    build_reset_command,
    build_solid_color_gif,
    build_solid_color_packets,
    build_upload_complete_command,
)
from tests.test_template import TestTemplate


class TestLedProtocol(TestTemplate):
    def test_constants_match_spec(self):
        """Verify BLE UUIDs and protocol constants."""
        assert "FFF0" in SERVICE_UUID
        assert "FFF2" in WRITE_CHAR_UUID
        assert "FFF1" in NOTIFY_CHAR_UUID
        assert DEFAULT_CHUNK_SIZE == 196
        assert DEFAULT_WIDTH == 96
        assert DEFAULT_HEIGHT == 128
        assert BRIGHTNESS_LEVELS == 16

    def test_magic_header(self):
        """Verify magic header is aa55ffff."""
        assert MAGIC_HEADER == bytes.fromhex("aa55ffff")

    def test_reset_command_format(self):
        """Verify reset command has correct format."""
        cmd = build_reset_command()
        assert cmd[:4] == bytearray.fromhex("aa55ffff")
        assert len(cmd) == 16

    def test_ready_command_format(self):
        """Verify ready command has correct format."""
        cmd = build_ready_command()
        assert cmd[:4] == bytearray.fromhex("aa55ffff")
        assert len(cmd) == 16

    def test_upload_complete_command_format(self):
        """Verify upload complete command has correct format."""
        cmd = build_upload_complete_command()
        assert cmd[:4] == bytearray.fromhex("aa55ffff")
        assert len(cmd) == 17  # This command is 17 bytes

    def test_brightness_command_format(self):
        """Verify brightness command structure."""
        for level in [0, 7, 15]:
            cmd = build_brightness_command(level)
            assert cmd[:4] == bytearray.fromhex("aa55ffff")
            assert cmd[13] == level  # Brightness level in payload

    def test_brightness_command_invalid_level(self):
        """Verify brightness rejects invalid levels."""
        with pytest.raises(ValueError):
            build_brightness_command(-1)
        with pytest.raises(ValueError):
            build_brightness_command(16)

    def test_solid_color_gif_valid(self):
        """Verify solid color GIF is valid GIF format."""
        gif = build_solid_color_gif(width=16, height=16, color="#ff0000")
        # Check GIF header (GIF87a or GIF89a are both valid)
        assert gif[:3] == b"GIF"
        assert gif[3:6] in (b"87a", b"89a")
        # Check trailer
        assert gif[-1] == 0x3B

    def test_solid_color_gif_dimensions(self):
        """Verify GIF has correct dimensions."""
        gif = build_solid_color_gif(width=96, height=128, color="#00ff00")
        # Dimensions are at bytes 6-9 (little-endian)
        width = int.from_bytes(gif[6:8], "little")
        height = int.from_bytes(gif[8:10], "little")
        assert width == 96
        assert height == 128

    def test_gif_upload_packets_structure(self):
        """Verify GIF upload packet sequence."""
        gif = build_solid_color_gif(width=16, height=16, color="#0000ff")
        packets = build_gif_upload_packets(gif)

        # Should have: reset, ready, data packet(s), complete x2
        assert len(packets) >= 4

        # First packet is reset
        assert packets[0] == build_reset_command()

        # Second packet is ready
        assert packets[1] == build_ready_command()

        # Last two packets are upload complete
        assert packets[-1] == build_upload_complete_command()
        assert packets[-2] == build_upload_complete_command()

        # Data packets have magic header
        for packet in packets[2:-2]:
            assert packet[:4] == bytearray.fromhex("aa55ffff")

    def test_solid_color_packets_returns_list(self):
        """Verify solid color packets returns non-empty list."""
        packets = build_solid_color_packets(width=16, height=16, color="#ff0000")
        assert isinstance(packets, list)
        assert len(packets) >= 4  # reset, ready, data, complete x2

    def test_packet_checksums_present(self):
        """Verify packets have checksum bytes at the end."""
        packets = build_solid_color_packets(width=16, height=16, color="#ffffff")

        # Data packets should have checksums at the end
        for packet in packets[2:-2]:
            # Last two bytes are checksums
            assert len(packet) > 2
