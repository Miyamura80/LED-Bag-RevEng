# TODO

## Integrations

- [ ] Integrate [Strix](https://github.com/usestrix/strix) - **Requires human supervision**
- [ ] Re-init Postgres API key due to potential leak

## LED Backpack Protocol

- [ ] Capture BLE traffic from LOY SPACE app (Android HCI snoop log)
- [ ] Decode write packets from capture (identify command framing, payload, checksum)
- [ ] Update sender to match captured protocol
- [ ] Validate by sending solid color and stopping animation
- [ ] Add optional CLI helpers (text/image upload) once protocol confirmed
