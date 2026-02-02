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

- **Tested working**: 196 bytes per chunk (fixed, larger sizes rejected)
- **Tested NOT working**: 256, 384, 462 byte chunks all fail
- Despite firmware v24, this device does not accept larger chunk sizes

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

## Graffiti Mode (Direct Pixel Control) - NOT SUPPORTED

**TESTED: This device does NOT support Merkury-style graffiti mode.**

BC-prefix commands were tested on all 11 writable characteristics and none produced responses or visible effects. The device only responds to YS-protocol (`aa55ffff`) commands.

### What Was Tested

Commands tested with `probe_characteristics.py`:
- `BC 00 01 01 55` (start graffiti) - No response
- `BC 00 0D 0D 55` (enable draw) - No response  
- `BC 01 01 00 00 FF 00 00 FF 55` (red pixel) - No response
- `BC FF 01 00 55` (power on) - No response

### Reference: Merkury-style Protocol (for other devices)

Some YS-family devices DO support graffiti mode. If your device has service `0xFFD0`:

| Role | UUID |
|------|------|
| Service | `0000FFD0-0000-1000-8000-00805F9B34FB` |
| Write char | `0000FFD1-0000-1000-8000-00805F9B34FB` |

### Graffiti Commands (BC-prefix)

| Command | Hex | Description |
|---------|-----|-------------|
| Power off | `BC FF 00 FF 55` | Turn display off (black) |
| Power on | `BC FF 01 00 55` | Turn display on |
| Start graffiti | `BC 00 01 01 55` | Enter graffiti mode |
| Enable draw | `BC 00 0D 0D 55` | Enable pixel drawing |
| Slideshow mode | `BC 00 12 12 55` | Exit graffiti, enter slideshow |

### Pixel Command Format

```
BC 01 01 00 PP RR GG BB QQ 55
```

| Byte | Value | Description |
|------|-------|-------------|
| 0 | `BC` | Command prefix |
| 1-3 | `01 01 00` | Fixed parameters |
| 4 | `PP` | Pixel index (0-255) |
| 5 | `RR` | Red (0-255) |
| 6 | `GG` | Green (0-255) |
| 7 | `BB` | Blue (0-255) |
| 8 | `QQ` | End index: `(PP + 1) % 256`, or `0xFF` if PP=0 |
| 9 | `55` | Terminator |

### Example: Red pixel at position 0

```
BC 01 01 00 00 FF 00 00 FF 55
```

### Performance Limits

Based on Merkury device testing:
- ~360 pixels/second over BLE (individual updates)
- For 96×128 (12,288 pixels): ~34 seconds for full frame
- Practical for: snake, pong, tetris, partial updates
- Not suitable for: video streaming, full-frame animations

### Probing for Graffiti Support

```bash
# Enumerate all services and find graffiti candidates
uv run python -m src.verify_backpack --name YS6249

# Test graffiti commands on all writable characteristics
uv run python -m src.probe_characteristics --name YS6249

# Test specific command
uv run python -m src.probe_characteristics --name YS6249 --command graffiti_init_1

# Send custom hex command
uv run python -m src.probe_characteristics --name YS6249 --custom-hex "bc00010155"
```

## Discovered GATT Services

Full enumeration from `verify_backpack.py`:

| Service | Characteristics | Status |
|---------|-----------------|--------|
| `0000FF00` | `0000FF02` (write), `0000FF01` (notify), `0000FF03` (notify) | Responds to YS commands |
| `0000FF10` | `0000FF11` (write/notify), `0000FF12` (write/notify) | Unknown |
| `0000EEE0` | `0000EEE1` (write/notify) | Responds to YS commands |
| `0000EEE2` | `0000EEE3` (write/notify) | Responds to YS commands |
| `0000FEE7` | `0000FEC7` (write), `0000FEC8` (indicate), `0000FEC9` (read) | CoolLED alternate |
| `0000FF80` | `0000FF82` (write), `0000FF81` (notify) | Nordic UART-like |
| `0000FFF0` | `0000FFF2` (write), `0000FFF1` (indicate) | **Main control** |
| `49535343` | Multiple (write/notify) | ISSC transparent UART |

**Note**: Service `0xFFD0` (Merkury graffiti) is NOT present on this device.

### Services That Respond to YS Commands

These accept `aa55ffff` commands and return ACKs:
- `0000FF02` (service `0000FF00`)
- `0000EEE1` (service `0000EEE0`)
- `0000EEE3` (service `0000EEE2`)

### ISSC UART Service (49535343)

**TESTED**: The ISSC UART is a transparent pass-through to the main command processor.

| Handle | Properties | Purpose |
|--------|------------|---------|
| 47 | write | UART RX (no response) |
| 49 | write, write-without-response | UART RX (passes to main processor) |
| 51 | notify | UART TX (receives ACKs) |
| 54 | write, notify | UART RX/TX |

Commands sent to handle 49 are processed by the same YS-protocol engine as 0xFFF2.
No alternative freedraw/streaming mode discovered via UART.

### CoolLED Service (0xFEE7)

On connection, the device sends an indication on 0xFEC8:
```
fe01001a271100010a0018848004200128023a06d023811a5a48
```

This appears to be a protobuf-encoded status message. Tested protobuf-style commands
to 0xFEC7 but received no responses. Purpose unknown - may be for device pairing/status only.

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

## Research Findings

### Device Identification

Based on specifications, this device is likely a **LOY T3-HD or T4** backpack:

| Model | Resolution | Size | Weight |
|-------|------------|------|--------|
| LOY T3-HD | 96×128 | 34×10.5×17cm | 1.3kg |
| LOY T4 | 96×128 | 50×32×14cm | 1.55kg |

**Manufacturer**: Shenzhen Biosled Technology Co., Ltd (also operates as Shenzhen Yanse Technology)
- Website: https://loy2014.com, https://biosled.com
- Address: 5th Floor, Building D, Skyworth Innovation Valley, Shenzhen
- Contact: biosled@163.com

### Related Apps

| App | Package | Purpose |
|-----|---------|---------|
| LOY SPACE | `com.yskd.loywf` | BLE control for LOY backpacks |
| LED Space | `com.yj.led` | WiFi control for LED bags (YSP-001) |

Both apps are developed by Shenzhen Yanse Technology and support:
- Text, pictures, GIF animations
- Graffiti/freedraw mode (in app)
- QR code display

### What We Know About Freedraw

The LOY SPACE app advertises a "graffiti/drawing function" in the App Store description. However:

1. **BC-style commands don't work** - Tested all Merkury-style graffiti commands
2. **No 0xFFD0 service** - Device lacks the Merkury graffiti GATT service
3. **UART is pass-through** - ISSC UART just forwards to YS processor

**Likely explanation**: The app's freedraw feature probably works by:
- Encoding each stroke as a new GIF frame
- Uploading the modified GIF after each stroke
- Or using a completely different command set we haven't discovered

### Hardware Insights

The device likely uses:
- **HUB75-compatible LED panel** (96×128 pixels)
- **BLE+WiFi combo module** (possibly HLK-series or similar)
- **Custom firmware** with YS-protocol stack

Similar devices (WifiLEDBag project) use:
- UDP over WiFi (16-bit action code + bytestream)
- Serial data embedded in 802.11 or BLE frames

### Next Steps for Freedraw Discovery

1. **HCI Snoop of App Freedraw** - Capture what the app sends during drawing
2. **APK Decompilation** - Use JADX/APKTool on `com.yskd.loywf`
3. **WiFi Capture** - If device supports WiFi, capture UDP traffic
4. **Look for Different Commands** - Freedraw might use a different command prefix

### Similar Projects with Working Freedraw

| Project | Device | Freedraw Method |
|---------|--------|-----------------|
| [mi-led-display](https://github.com/offe/mi-led-display) | Merkury 16×16 | BC-prefix pixel commands |
| [pixelart-16x16](https://github.com/dmachard/pixelart-16x16) | Custom ESP32 | Web Bluetooth + custom firmware |
| [ESP32_BLE_Matrixpanel](https://github.com/meganukebmp/ESP32_BLE_Matrixpanel) | Custom ESP32 | Direct pixel writes |

### Hardware Replacement Option

If software freedraw is not possible, the display panel could potentially be driven by:
- **ESP32 + HUB75** using [ESP32-HUB75-MatrixPanel-I2S-DMA](https://github.com/mrcodetastic/ESP32-HUB75-MatrixPanel-DMA)
- This would give full control over the display at hardware level
- Requires opening the backpack and replacing the controller board
