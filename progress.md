# Progress

## Context
- Device: LOY SPACE LED backpack (name shown in nRF Connect: YS6249181011L)
- App: LOY SPACE (Android, package: `com.yskd.loywf`)
- Manufacturer: Shenzhen Yanse Technology (深圳市研色科技有限公司)
- Platform: macOS host using BLE via `bleak`

## Device Specifications (from LOY SPACE app)
- **Screen resolution**: 96×128 pixels
- **Device ID**: 6249181011
- **Firmware**: v2.8.77#v24
- **Control model**: EXYB-A#DPMJBGRRI12BT

## Research Summary
- Found similar YS-prefixed devices with fully reverse-engineered protocols:
  - [ble-led-matrix-controller](https://github.com/mtpiercey/ble-led-matrix-controller) - 96×20 YS device
  - [mi-led-display](https://github.com/offe/mi-led-display) - Merkury Innovations
- These devices use **YS-protocol** with `aa55ffff` magic header (NOT CoolLEDX-style)
- Protocol uploads GIF data in 196-byte chunks with mod256 + high-byte checksums

## Verified Device Services (macOS BLE scan)
- Service `0xFFF0` with write characteristic `0xFFF2`, notify `0xFFF1`
- Other services: `0xFEE7`, `0xFF00`, `0xFF10`, `0xEEE0`, `0xEEE2`, `0xFF80`, ISSC UART

## Code Updated
- `src/led_protocol.py`:
  - Implements YS-protocol with `aa55ffff` magic header
  - Builds GIF data packets with proper checksums
  - Generates minimal solid-color GIFs for upload
- `src/led_client.py`:
  - Uses notification-based acknowledgment
  - Default dimensions now 96×128
- `src/send_solid_color.py`:
  - Simplified CLI using new protocol
- `tests/test_led_protocol.py`, `tests/test_send_solid_color.py`:
  - Updated tests for YS-protocol format

## Protocol Summary
| Item | Value |
|------|-------|
| Magic header | `aa55ffff` |
| Service UUID | 0xFFF0 |
| Write char | 0xFFF2 |
| Notify char | 0xFFF1 |
| Chunk payload | 196 bytes |
| Checksum | mod256 + high byte of sum |

## Current Status
- BLE connection and discovery working
- Protocol updated to YS-style `aa55ffff` format based on similar device research
- **Next step**: Test new protocol on device. If no response, capture HCI snoop log to verify exact packet format. See [docs/protocol.md](docs/protocol.md) and [docs/hci_snoop.md](docs/hci_snoop.md).
