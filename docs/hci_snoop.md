# Capturing HCI snoop logs for LOY SPACE protocol

Capture Bluetooth HCI traffic from the LOY SPACE app on your Android phone (e.g. S25) so we can see the exact bytes sent for solid colors and media transfer, then update our protocol to match.

## 1. Enable HCI snoop on the phone

1. **Developer options** (if not already): Settings → About phone → Software information → tap **Build number** 7 times.
2. **HCI snoop**: Settings → Developer options → enable **Bluetooth HCI snoop log**.
3. **Bluetooth**: Turn Bluetooth off and back on so logging starts clean.

## 2. Record the scenarios

Do **one** of the following, then stop the snoop (see step 3). You can do multiple runs (e.g. one for solid color, one for media) and label the bugreports.

### Scenario A: Solid color

1. Open the **LOY SPACE** app and connect to your backpack (YS6249181011L).
2. In the app, set the display to a **solid color** (e.g. red). Confirm the backpack actually shows that color.
3. Optionally repeat with **clear** or **off** if the app has those.
4. Leave the app connected; go to step 3 to stop the snoop.

### Scenario B: Media transfer (image)

1. Open the **LOY SPACE** app and connect to the backpack.
2. Send an **image** (or other media) to the display from the app.
3. Wait until the transfer finishes and the display updates.
4. Go to step 3 to stop the snoop.

## 3. Stop snoop and retrieve the log

1. **Stop logging**: Settings → Developer options → turn **Bluetooth HCI snoop log** off (or leave on and pull after each scenario; the file gets overwritten when you toggle off/on, so pull before toggling again if you want multiple captures).

2. **Get the log** (choose one):

   **Option A – Bug report (recommended, no root)**

   ```bash
   adb bugreport bugreport_$(date +%Y%m%d_%H%M).zip
   ```

   Unzip the archive. The HCI log is often under:

   - `FS/data/misc/bluetooth/logs/btsnoop_hci.log`
   - or `bugreport-*.zip` → open and search for `btsnoop` or `bt/` in the path.

   Copy `btsnoop_hci.log` out of the zip to your machine (e.g. `apk/btsnoop_hci.log`).

   **Option B – Direct path (Samsung, if accessible)**

   On some Samsung devices the log is under `/data/log/bt/` or similar. If `adb pull` works:

   ```bash
   adb pull /data/log/bt/btsnoop_hci.log apk/btsnoop_hci.log
   ```

   If you get "permission denied", use Option A (bug report).

## 4. Open in Wireshark

1. Install [Wireshark](https://www.wireshark.org/) if needed.
2. Open the captured file: **File → Open** → select `btsnoop_hci.log`.
3. **Filter for ATT writes** (app traffic to the backpack):

   ```
   btatt.opcode == 0x52 || btatt.opcode == 0x53
   ```

   - `0x52` = ATT Write Request  
   - `0x53` = ATT Write Command  

   Or broader: `btatt` then look for "Write Request" / "Write Command" in the packet list.

4. **Find packets to the backpack**  
   Look at the destination address or connection handle and match it to your backpack (same MAC/UUID as in `verify_backpack`). The payload is in the **Attribute Value** (e.g. `btatt.value`).

5. **Identify 0xFFF2 traffic**  
   Our app uses **service 0xFFF0, write characteristic 0xFFF2**. In Wireshark you may see:
   - **Handle** (e.g. `btatt.handle`) – the handle that corresponds to 0xFFF2 is assigned at connection; it might be listed in an "ATT Find Information Response" or similar discovery packet, or you can match by payload size (e.g. ~509-byte chunks).
   - **Value** – `btatt.value` shows the raw bytes the app sent.

6. **Export payload bytes**  
   For each relevant Write Request/Command:
   - Select the packet.
   - In the tree, expand **Bluetooth ATT** → **Attribute Value** (or similar).
   - Right‑click the value → **Copy** → **…as Hex Stream** (or "Bytes → Hex Dump") and paste into a text file.

   Save one file per scenario (e.g. `docs/captures/solid_red_hex.txt`, `docs/captures/media_transfer_hex.txt`) with one line per packet or one blob per write, and note the order.

## 5. Document and implement

1. **Add captures to the repo** (optional):  
   e.g. `docs/captures/solid_red_hex.txt` with the hex dumps and a short note (e.g. "LOY SPACE app, solid red, 0xFFF2").

2. **Compare with our encoder**  
   Run the Python simulator and compare bytes:

   ```bash
   uv run python scripts/simulate_protocol.py --clear --color "#ff0000" --json
   ```

   Diff the hex from the capture vs the simulator. Note differences: framing (STX/ETX, length, escape), opcodes, checksum, chunk layout.

3. **Update the protocol**  
   In `src/led_protocol.py` (and docs/protocol.md), change the encoder to match the captured format: header, opcodes, chunk structure, checksum. Then re-run the sender and the simulator to confirm.

## Quick reference

| Step              | Action |
|-------------------|--------|
| Enable snoop      | Developer options → Bluetooth HCI snoop log ON, BT cycle |
| Record            | LOY SPACE app: connect → solid color and/or media transfer |
| Stop              | Developer options → HCI snoop log OFF (or leave on and pull once) |
| Get log           | `adb bugreport bugreport.zip`, unzip, find `btsnoop_hci.log` |
| Open              | Wireshark → Open `btsnoop_hci.log` |
| Filter            | `btatt.opcode == 0x52 \|\| btatt.opcode == 0x53` |
| Export            | Copy Attribute Value as hex; save in `docs/captures/` |
| Update protocol   | Match framing in `src/led_protocol.py`, document in `docs/protocol.md` |
