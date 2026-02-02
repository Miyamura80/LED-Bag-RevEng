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

## Real-Time Draw Command (rt_draw) - DISCOVERED FROM APK

**This is a major discovery from APK decompilation!** The LOY SPACE app has a built-in `rt_draw` command for real-time pixel drawing, which is used by the "涂鸦" (graffiti/doodle) feature.

### Status: NEEDS HCI SNOOP VERIFICATION

**Current attempts to send rt_draw commands have NOT worked.** The device continues playing GIFs and ignores our packets. This suggests:

1. The packet format we're building may be incorrect
2. There may be a mode switch or initialization required first
3. The command byte values may be different than what we extracted

**Next step**: Capture an HCI snoop log while using the app's graffiti/doodle feature to see the exact bytes being transmitted.

### Command Index

The `rt_draw` command is index **32** in the command table. The packet header for rt_draw is `0x2A 0xBE` (bytes 42, 190).

### rt_draw Types

| Type | Description | Parameters |
|------|-------------|------------|
| 0 | Raw pixel data in rectangle | `data[]`, `x0`, `y0`, `x1`, `y1`, `color` |
| 1 | Fill rectangle | `color`, `type_rect`, `x0`, `y0`, `x1`, `y1` |
| 16 | Draw pixels at coordinates | `color`, `data[[x1,y1], [x2,y2], ...]` |

### Type 1 - Fill Rectangle (Clear Screen)

Used to fill a rectangular area with a solid color. For clearing the screen:

```javascript
{
  cmd: {
    rt_draw: {
      color: 0,          // RGB as 24-bit integer (R + G<<8 + B<<16)
      type: 1,
      type_rect: 0,      // 0 = fill
      x0: 0, y0: 0,      // Top-left corner
      x1: 95, y1: 127    // Bottom-right corner (96×128 screen)
    }
  }
}
```

**Byte encoding** (15 bytes):
```
[50, 13, 1, R, G, B, type_rect, x0_lo, x0_hi, y0_lo, y0_hi, x1_lo, x1_hi, y1_lo, y1_hi]
```

### Type 16 - Draw Pixels at Coordinates

Used to draw individual pixels at specified coordinates:

```javascript
{
  cmd: {
    rt_draw: {
      color: 0xFF0000,   // Red (R + G<<8 + B<<16)
      type: 16,
      data: [[10, 20], [11, 20], [12, 20]]  // Array of [x, y] pairs
    }
  }
}
```

The encoder calculates the bounding box of all pixels and creates a bitmap.

### Color Format

Colors are encoded as 24-bit integers in **RGB** order:
```
color = R + (G << 8) + (B << 16)
```

Example:
- Red: `0x0000FF` or `255` (R=255, G=0, B=0)
- Green: `0x00FF00` or `65280` (R=0, G=255, B=0)
- Blue: `0xFF0000` or `16711680` (R=0, G=0, B=255)
- White: `0xFFFFFF` or `16777215`

### Wrapping in YS-protocol

The rt_draw payload is wrapped in the standard YS-protocol packet:
1. Length prefix (2 bytes, little-endian)
2. Magic header: `0x55 0xAA 0xFF 0xFF` (21930, 65535 as 16-bit LE)
3. Payload length + 4 (2 bytes)
4. Sequence number (2 bytes)
5. Command flags (1 byte): 193 for rt_draw
6. Command index: 32
7. rt_draw payload
8. Checksum (2 bytes, sum of all bytes)

### Usage in the App

The app uses `rt_draw` in the DIY/graffiti feature:
- `data_parse[12]` - Type 16 pixel drawing
- `data_parse[17]` - Type 1 rectangle (clear screen)

Example from app code:
```javascript
// Clear screen to black
e["cmd"]["rt_draw"]["color"] = rbg_to_color(0, 0, 0);
e["cmd"]["rt_draw"]["x0"] = 0;
e["cmd"]["rt_draw"]["y0"] = 0;
e["cmd"]["rt_draw"]["x1"] = this.c_w - 1;  // 95
e["cmd"]["rt_draw"]["y1"] = this.c_h - 1;  // 127
sendbuffer([e]);

// Draw pixels
i["cmd"]["rt_draw"]["color"] = rbg_to_color(r, g, b);
i["cmd"]["rt_draw"]["data"] = [[x1, y1], [x2, y2], ...];
sendbuffer([i]);
```

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

### Real-Time Drawing (rt_draw) - DISCOVERED!

The LOY SPACE app's "graffiti/drawing function" uses the `rt_draw` command discovered via APK decompilation.

**Key Discovery**: To use rt_draw, you must first enter "graffiti mode" using the game command:

```python
# 1. Send RESET and READY
build_reset_command()
build_ready_command()

# 2. Enter graffiti mode (game id=16) - REQUIRED!
build_game_mode(16)  # Stops idle animation, enables rt_draw

# 3. Now rt_draw commands will work
build_rt_draw_fill_rect(x0, y0, x1, y1, r, g, b)
```

**Commands**:
| Function | Command Index | Description |
|----------|---------------|-------------|
| `build_game_mode(16)` | 31 | Enter graffiti mode (stops idle animation) |
| `build_rt_draw_fill_rect()` | 32 (subtype 2) | Fill rectangle with color |
| `build_rt_draw_clear_screen()` | 32 (subtype 2) | Clear screen (fill black) |
| `build_rt_draw_pixels()` | 32 (subtype 2) | Draw individual pixels |

**rt_draw Packet Format** (CMD_RESET style):
```
[AA 55 FF FF] [len] [sno_lo sno_hi 00] [C1] [02] [payload...] [chk1 chk2]
```

**rt_draw Payload for Fill Rect** (type=1):
```
[32 0D 01] [R G B] [type_rect=0] [x0_lo x0_hi] [y0_lo y0_hi] [x1_lo x1_hi] [y1_lo y1_hi]
```

See `src/draw_maze.py` for a working example that draws animated rainbow mazes!

### Hardware Insights

The device likely uses:
- **HUB75-compatible LED panel** (96×128 pixels)
- **BLE+WiFi combo module** (possibly HLK-series or similar)
- **Custom firmware** with YS-protocol stack

Similar devices (WifiLEDBag project) use:
- UDP over WiFi (16-bit action code + bytestream)
- Serial data embedded in 802.11 or BLE frames

### Freedraw Discovery - COMPLETE

We successfully reverse-engineered the freedraw protocol through APK decompilation:

1. **APK Decompilation** - Used JADX on `com.yskd.loywf` to extract `app-service.js`
2. **Found `ye()` function** - Command encoding function with all command indices
3. **Discovered game mode** - `game: {id: 16}` enters graffiti mode
4. **Discovered rt_draw** - Real-time drawing command for rectangles and pixels

**Key insight**: The device's idle animation interferes with rt_draw. Sending `build_game_mode(16)` stops the animation and enables a clean canvas for drawing.

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
