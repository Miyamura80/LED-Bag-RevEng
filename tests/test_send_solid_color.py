from src.send_solid_color import (
    _build_payload_chunks,
    _parse_color,
    build_solid_color_payload,
    build_simple_command,
    encode_command,
)
from tests.test_template import TestTemplate


class TestSendSolidColor(TestTemplate):
    def test_parse_color_accepts_hex(self):
        assert _parse_color("#ff0000") == (255, 0, 0)
        assert _parse_color("00ff00") == (0, 255, 0)
        assert _parse_color("#0f0") == (0, 255, 0)

    def test_build_solid_color_payload_length(self):
        payload = build_solid_color_payload(2, 8, "#ff0000")
        assert payload[:24] == bytearray(24)
        assert payload[24:26] == b"\x00\x06"
        assert len(payload) == 24 + 2 + 6

    def test_build_payload_chunks_checksum(self):
        payload = bytearray([0xAA, 0xBB])
        chunks = _build_payload_chunks(payload, command_byte=0x03)
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk[0] == 0x03
        assert chunk[-1] == 0x11

    def test_encode_command_wraps_and_escapes(self):
        raw = bytearray([0x01, 0x02, 0x03])
        encoded = encode_command(raw)
        assert encoded[0] == 0x01
        assert encoded[-1] == 0x03
        assert b"\x02\x05" in encoded
        assert b"\x02\x06" in encoded
        assert b"\x02\x07" in encoded

    def test_build_simple_command_accepts_empty_payload(self):
        encoded = build_simple_command(0x0D)
        assert encoded[0] == 0x01
        assert encoded[-1] == 0x03
