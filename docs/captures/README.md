# HCI capture payloads

Place exported ATT write payloads (hex) from Wireshark here after capturing LOY SPACE app traffic. See [../hci_snoop.md](../hci_snoop.md).

**Suggested files:**

- `solid_red_hex.txt` – hex dump(s) of Write Request/Command to 0xFFF2 when app sets solid red (one line per packet or one blob, in order).
- `media_transfer_hex.txt` – hex dump(s) when app sends an image/media to the display.

Then compare with `uv run python scripts/simulate_protocol.py --clear --color "#ff0000" --json` and update `src/led_protocol.py` to match the real framing.
