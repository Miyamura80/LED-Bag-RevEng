#!/usr/bin/env node
/**
 * Beautify LOY SPACE app-service.js for protocol inspection.
 *
 * Prereq: Extract app-service.js from the APK first:
 *   unzip -j apk/loy_space_base.apk "assets/apps/__UNI__F2139F6/www/app-service.js" -d apk/extracted_assets
 *
 * Then run (from repo root):
 *   node scripts/beautify_app_js.js
 *
 * Uses npx js-beautify if available; otherwise prints the manual command.
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.join(__dirname, "..");
const inputPath = path.join(repoRoot, "apk", "extracted_assets", "app-service.js");
const outputPath = path.join(
  repoRoot,
  "apk",
  "extracted_assets",
  "app-service.beautified.js"
);

if (!fs.existsSync(inputPath)) {
  console.error("Missing apk/extracted_assets/app-service.js. Extract from APK first:");
  console.error(
    '  unzip -j apk/loy_space_base.apk "assets/apps/__UNI__F2139F6/www/app-service.js" -d apk/extracted_assets'
  );
  process.exit(1);
}

const result = spawnSync(
  "npx",
  ["js-beautify", inputPath, "-o", outputPath],
  { cwd: repoRoot, stdio: "inherit", shell: true }
);

if (result.status !== 0) {
  console.error("npx js-beautify failed. Run manually:");
  console.error("  npx js-beautify", inputPath, "-o", outputPath);
  process.exit(1);
}

console.log("Wrote", outputPath);
