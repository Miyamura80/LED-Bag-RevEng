#!/usr/bin/env node
/**
 * Placeholder for transcribed LOY SPACE packet-building logic from app-service.js.
 *
 * After beautifying app-service.js (node scripts/beautify_app_js.js), locate the
 * code that builds the hex string passed to uni.writeBLECharacteristicValue.
 * Transcribe that logic here so you can run it in Node to simulate the protocol
 * without the device.
 *
 * Usage (once implemented):
 *   node scripts/loy_space_packet_builder.js solid_color "#ff0000" 96 16
 *   node scripts/loy_space_packet_builder.js clear
 *
 * Output: hex string(s), one per line (one per BLE write chunk).
 */

const args = process.argv.slice(2);

if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
  console.log(`
Usage (after transcribing from app-service.beautified.js):
  node scripts/loy_space_packet_builder.js solid_color <hex_color> [width] [height]
  node scripts/loy_space_packet_builder.js clear
  node scripts/loy_space_packet_builder.js init
  node scripts/loy_space_packet_builder.js brightness <0-255>

Output: hex string(s) for each BLE write chunk (one per line).

To transcribe:
  1. Run: node scripts/beautify_app_js.js
  2. Open apk/extracted_assets/app-service.beautified.js
  3. Search for writeBLECharacteristicValue and the code that builds "value"
  4. Copy that logic into buildPacket() below.
`);
  process.exit(0);
}

/**
 * Build the hex string(s) the app would send for the given command.
 * Replace this with logic transcribed from app-service.beautified.js.
 *
 * @param {string} command - "solid_color" | "clear" | "init" | "brightness" | ...
 * @param {string[]} rest - e.g. ["#ff0000", "96", "16"] for solid_color
 * @returns {string[]} - Array of hex strings (one per BLE write chunk)
 */
function buildPacket(command, rest) {
  // TODO: Transcribe from app-service.beautified.js
  throw new Error(
    "Not implemented. Beautify app-service.js and transcribe the packet-building logic here."
  );
}

const command = args[0];
const rest = args.slice(1);
try {
  const hexChunks = buildPacket(command, rest);
  hexChunks.forEach((hex) => console.log(hex));
} catch (e) {
  console.error(e.message);
  process.exit(1);
}
