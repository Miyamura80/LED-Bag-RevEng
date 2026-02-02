# Protocol simulation and JS transcription

Ways to run or emulate the LOY SPACE BLE protocol without the device, and how to extract/transcribe the app’s JavaScript so you can simulate the real packet format.

## 1. Python protocol simulator (no device)

The repo’s protocol encoder is in `src/led_protocol.py`. You can “simulate” a run by building the same packets and printing hex dumps (no BLE, no device).

**Run from repo root:**

```bash
# Simulate: clear + solid red (96x16), print hex for each chunk
uv run python scripts/simulate_protocol.py --clear --color "#ff0000"

# Same, output as JSON (for diffing with HCI or other tools)
uv run python scripts/simulate_protocol.py --clear --color "#ff0000" --json

# Init, brightness, then solid green
uv run python scripts/simulate_protocol.py --init --brightness 200 --color "#00ff00" --chunk-size 509
```

Use this to:

- See exactly what bytes would be sent over BLE.
- Compare with an HCI snoop (paste our hex vs captured hex).
- Feed another runtime (e.g. Node) by copying the hex from `--json`.

The simulator uses the **current** encoder (CoolLEDX-style framing). Once the real framing is known (e.g. from HCI or from the app JS), update `src/led_protocol.py` and re-run the simulator to get the new packets.

## 2. Beautify the app JavaScript

The app’s packet-building logic lives in the minified `app-service.js` inside the APK. To read or transcribe it:

1. **Extract the bundle** (if not already done):

   ```bash
   unzip -j apk/loy_space_base.apk "assets/apps/__UNI__F2139F6/www/app-service.js" -d apk/extracted_assets
   ```

2. **Beautify** (Node, one-time):

   ```bash
   npx js-beautify apk/extracted_assets/app-service.js -o apk/extracted_assets/app-service.beautified.js
   ```

   Or with [prettier](https://prettier.io/):  
   `npx prettier --write apk/extracted_assets/app-service.js`

3. **Search the beautified file** for:
   - `writeBLECharacteristicValue` – where the hex `value` is passed.
   - `value:` or `value =` just before that call – that’s the hex string being sent.
   - Backtrack to where that string is built (buffer → hex, chunking, framing).

The beautified file is large; focus on the BLE write path and any helpers that build the send buffer (e.g. names containing “send”, “write”, “buffer”, “hex”).

## 3. Capture writes from the app JS (Node)

To **run** the app’s JS and log the hex values it would pass to `uni.writeBLECharacteristicValue`, you can mock `uni` and load the bundle. The app is a uni-app (Vue) bundle, so it may expect a browser-like environment; the minimal approach is to mock only what’s needed for the BLE write path.

**Option A – Mock and load (capture on first write):**

1. Create a small Node script that:
   - Defines a global `uni` with `writeBLECharacteristicValue({ deviceId, serviceId, characteristicId, value })` that logs `value` (and optionally appends to a file).
   - Loads `apk/extracted_assets/app-service.js` (e.g. with `require` or `fs.readFile` + `vm.runInNewContext`).
   - The bundle runs on load; it usually won’t call `writeBLECharacteristicValue` until some user action is simulated. So you may only get a log when the code path that builds and sends a packet is executed (e.g. from a timer or from calling an exported function if the bundle exposes one).

2. If the bundle doesn’t call `writeBLECharacteristicValue` on load, you have two paths:
   - **Transcribe**: From the beautified file, copy the function(s) that build the hex string for a given command (e.g. “solid color”) into a standalone JS file. Call that with test inputs and log the result. No BLE, no device.
   - **Browser**: Run the actual app in a browser (if the project builds for web) with a patched `uni.writeBLECharacteristicValue` that logs `value`, then trigger “send solid color” in the UI and capture the logged hex.

**Option B – Transcribed standalone (recommended once you found the builder):**

1. From the beautified `app-service.js`, locate the logic that:
   - Takes something like “command” or “image data” or “buffer”.
   - Chunks it, adds headers/checksum, converts to hex.
   - Returns or passes that hex string to `writeBLECharacteristicValue`.
2. Copy that logic into a new file, e.g. `scripts/loy_space_packet_builder.js`, and export a function like `buildSendBuffer(command, payload) -> hexString`.
3. Run it in Node: `node scripts/loy_space_packet_builder.js` with hardcoded or CLI args, and print the hex. Then you can compare with the Python simulator or HCI.

## 4. Suggested workflow

1. **Python simulator**: Run `scripts/simulate_protocol.py` for the commands you care about; save hex (or JSON) as “our current encoder”.
2. **Beautify app JS**: Generate `app-service.beautified.js` and search for the BLE write path and buffer-building code.
3. **HCI capture** (if you have the device): Capture a log while using the official app for the same action (e.g. solid red). Extract the ATT write payloads to 0xFFF2.
4. **Compare**: HCI bytes vs Python simulator hex vs (if you transcribed) Node-built hex. Adjust `src/led_protocol.py` until our simulator output matches HCI or the transcribed JS.
5. **Transcribe (optional)**: Once you understand the app’s format, implement it in `scripts/loy_space_packet_builder.js` (or keep it only in Python) so you can run the “real” protocol in Node for testing without the device.
