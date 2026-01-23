# Progress

## Context
- Device: LOY SPACE LED backpack (name shown in nRF Connect: YS6249181011L)
- App: LOY SPACE (Android)
- Platform: macOS host using BLE via `bleak`

## Research Summary
- No public protocol writeups found for LOY SPACE.
- Found strong indications that devices use CoolLED/CoolLEDX-style services.
- Confirmed BLE services on device include: `0xFF00`, `0xFF10`, `0xEEE0`, `0xEEE2`, `0xFEE7`, `0xFF80`, `0xFFF0`, plus a 128-bit ISSC UART service.

## Verified Device Services (macOS BLE scan)
- `0000fee7-0000-1000-8000-00805f9b34fb` with write characteristic `0000fec7-0000-1000-8000-00805f9b34fb`
- Other write characteristics:
  - `0000ff02-0000-1000-8000-00805f9b34fb`
  - `0000ff11-0000-1000-8000-00805f9b34fb`
  - `0000ff12-0000-1000-8000-00805f9b34fb`
  - `0000eee1-0000-1000-8000-00805f9b34fb`
  - `0000eee3-0000-1000-8000-00805f9b34fb`
  - `0000ff82-0000-1000-8000-00805f9b34fb`
  - `0000fff2-0000-1000-8000-00805f9b34fb`
  - `49535343-6daa-4d02-abf6-19569aca69fe`
  - `49535343-8841-43f4-a8d4-ecbe34729bb3`
  - `49535343-aca3-481c-91ec-d85e28a60318`

## Code Added
- `src/verify_backpack.py`:
  - Scans for devices, connects, and prints services/characteristics.
  - Confirms connection to `YS6249181011L` and enumerates GATT services.
- `src/send_solid_color.py`:
  - Implements CoolLEDX basic framing and sends a solid-color image payload.
  - Supports flags for init, brightness, mode, clear, and custom characteristic UUID.
- `tests/test_verify_backpack.py`:
  - Unit tests for target matching logic.
- `tests/test_send_solid_color.py`:
  - Unit tests for packet construction and framing.
- Added dependency: `bleak`.

## Attempts and Results
- Connected successfully to device and verified services.
- Sent solid-color frames (purple) using:
  - `0000fec7-0000-1000-8000-00805f9b34fb`
  - `0000fff2-0000-1000-8000-00805f9b34fb`
- Also tried init, switch on, picture mode, clear, brightness.
- Result: device continued playing existing animation; no visible change.

## Current Status
- BLE connection and discovery are working.
- Packet format used in `send_solid_color.py` did not affect device.
- Next step requires capturing the actual packets from LOY SPACE.
