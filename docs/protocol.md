# LOY SPACE LED Backpack BLE Protocol

Reverse-engineered from the LOY SPACE Android app (package `com.yskd.loywf`) and research on similar YS-prefixed LED matrix devices.

## Device Specifications

| Spec | Value |
|------|-------|
| **Screen resolution** | 96×128 pixels |
| **Device ID** | 6249181011 (BLE name: `YS6249181011L`) |
| **Firmware** | v2.8.77#v24 |
| **Control model** | EXYB-A#DPMJBGRRI12BT |
| **Manufacturer** | Shenzhen Yanse Technology (深圳市研色科技有限公司) |

## BLE Service and Characteristics

| Role            | UUID (full)                              | Short   |
|-----------------|------------------------------------------|---------|
| Service         | `0000FFF0-0000-1000-8000-00805F9B34FB`   | 0xFFF0  |
| Write           | `0000FFF2-0000-1000-8000-00805F9B34FB`   | 0xFFF2  |
| Notify          | `0000FFF1-0000-1000-8000-00805F9B34FB`   | 0xFFF1  |

- **Write**: All commands and image data are sent to the **write** characteristic (0xFFF2).
- **Notify**: The app subscribes to the notify characteristic (0xFFF1) for responses/acks.

### Chunk size

- **High speed**: Up to 509 bytes per BLE write (protocol v24+).
- **Older / fallback**: 248 bytes.
- GIF payload chunks are typically 196 bytes each.

## Packet Format (YS-protocol)

Based on reverse engineering of similar YS-prefixed devices (ATOTOZONE, Merkury), these devices use the **aa55ffff** protocol format.

### Packet Structure

```
aa55ffff        - Magic header (4 bytes)
LL              - Payload length byte (from first index field to checksum, inclusive)
IIII00          - Packet index (little-endian 16-bit + 0x00): 000000, 000100, 000200...
c102...         - Constant header (command-specific)
NN              - Total number of packets
IIII00          - Packet index again
c4000013        - Constant
PPPP            - Payload length indicator (81c4 for full 196-byte payload)
[payload]       - GIF or image data (up to 196 bytes per packet)
CC              - CheckSum8 Mod 256 of all preceding bytes
HH              - High byte of total sum of all preceding bytes
```

### Checksum Calculation

```python
def checksum_mod256(data: bytes) -> int:
    """CheckSum8 Mod 256 of all bytes."""
    return sum(data) % 256

def high_byte_sum(data: bytes) -> int:
    """High byte of total sum (total_sum // 256)."""
    return sum(data) // 256
```

### Known Command Packets

| Command | Hex Payload |
|---------|-------------|
| Reset/clear storage | `aa55ffff0a000900c102080200ffdc04` |
| Ready for upload | `aa55ffff0a000900c10208020000dd03` |
| Upload complete | `aa55ffff0b000f00c10236030100001404` |
| Brightness (0-15) | `aa55ffff0a0004 00c102060200NN CC03` (NN=level, CC=checksum) |
| Screen blank | `aa55ffff0a000500c10204020001 d603` |

### GIF Upload Protocol

1. Send reset command: `aa55ffff0a000900c102080200ffdc04`
2. Send ready command: `aa55ffff0a000900c10208020000dd03`
3. For each 196-byte chunk of GIF data:
   - Build packet with header + chunk + checksums
   - Wait for notification acknowledgment
4. Send upload complete (twice): `aa55ffff0b000f00c10236030100001404`

### Simple Command Format (Merkury-style, untested)

Some similar devices use simpler commands:

```
BC FF 00 FF 55  - Power off
BC FF 01 00 55  - Power on
BC 00 01 01 55  - Start graffiti mode
BC 00 12 12 55  - Start slideshow mode
```

## Other GATT Services (from scan)

The device advertises additional services; the official app uses **0xFFF0** (write 0xFFF2):

- `0000FEE7` / `0000FEC7`
- `0000FF02`, `0000FF11`, `0000FF12`, `0000FF82`
- `0000EEE1`, `0000EEE3`
- ISSC UART 128-bit UUIDs

## Related Projects

- [ble-led-matrix-controller](https://github.com/mtpiercey/ble-led-matrix-controller) - 96×20 YS device, full GIF upload working
- [mi-led-display](https://github.com/offe/mi-led-display) - Merkury Innovations, BC-style commands
- [Blog: Reverse Engineering a BLE LED Matrix](https://overscore.media/posts/series/matthews-machinations/reverse-engineering-a-ble-led-matrix)

## Summary for Implementation

| Item              | Value |
|-------------------|--------|
| Service UUID      | `0000FFF0-0000-1000-8000-00805F9B34FB` |
| Write char UUID   | `0000FFF2-0000-1000-8000-00805F9B34FB` |
| Notify char UUID  | `0000FFF1-0000-1000-8000-00805F9B34FB` |
| Magic header      | `aa55ffff` |
| Max chunk payload | 196 bytes (GIF data per packet) |
| Checksum          | Mod256 + high byte of sum |
| Display size      | 96×128 pixels |

## Connect to the backpack first

Before sending commands, confirm your host can see and connect to the backpack:

1. **Power on** the LOY SPACE backpack and put it in BLE range.
2. **Disconnect other apps** (e.g. close or background the LOY SPACE app on your phone) so only one client connects.
3. **Scan and connect** (from repo root):

   ```bash
   # By device name (e.g. YS6249181011L → use substring YS6249)
   uv run python -m src.verify_backpack --name YS6249

   # By address if you know it
   uv run python -m src.verify_backpack --address XX:XX:XX:XX:XX:XX

   # No args: match by advertised service UUID (0xFFF0 or 0xFEE7) if only one such device
   uv run python -m src.verify_backpack
   ```

4. You should see "Connected: True" and a list of GATT services/characteristics. If you see "No matching device found", increase `--timeout`, ensure the bag is on and nearby, and that no other app is connected.

Once this works, use the sender (below) or the Python API from [README](README.md#led-backpack-control).

## Validating on device

1. Power on the LOY SPACE backpack and ensure it is in BLE range.
2. Run the sender (defaults to write characteristic 0xFFF2):

   ```bash
   uv run python -m src.send_solid_color --color "#ff0000" --clear
   ```

   Or with explicit device name:

   ```bash
   uv run python -m src.send_solid_color --name YS6249 --color "#00ff00"
   ```

3. If the display does not change, capture an HCI snoop log (Developer options → Bluetooth HCI snoop log) while using the official LOY SPACE app, then compare payloads and update the protocol encoder.

## Simulating the protocol (no device)

To run or emulate the protocol without the device (e.g. to get hex dumps for comparison with HCI or to transcribe the app's JS), see [protocol_simulation.md](protocol_simulation.md). It covers:

- **Python simulator**: `uv run python scripts/simulate_protocol.py --clear --color "#ff0000"` to print the exact hex packets our encoder would send.
- **Beautifying the app JS**: How to beautify `app-service.js` and where to look for the packet-building logic.
- **Transcribing to Node**: Optional standalone `scripts/loy_space_packet_builder.js` to run the app's packet format in Node once transcribed.
