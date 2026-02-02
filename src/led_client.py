"""
Async client for LOY SPACE LED backpack control.

Use as a context manager to discover/connect and send commands.
"""

import asyncio

from bleak import BleakClient, BleakScanner
from loguru import logger as log

from src.led_protocol import (
    BRIGHTNESS_LEVELS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    NOTIFY_CHAR_UUID,
    WRITE_CHAR_UUID,
    build_brightness_command,
    build_grid_pattern_packets,
    build_ready_command,
    build_reset_command,
    build_solid_color_packets,
)

# Standard BLE Service Changed characteristic (for indications)
SERVICE_CHANGED_UUID = "00002a05-0000-1000-8000-00805f9b34fb"


class LedBackpackClient:
    """
    Async client for LOY SPACE LED backpack over BLE.

    Connect by address or discover by name, then call set_solid_color,
    clear, set_brightness. Uses YS-protocol from src.led_protocol.
    """

    def __init__(
        self,
        address: str,
        *,
        write_char_uuid: str = WRITE_CHAR_UUID,
        notify_char_uuid: str = NOTIFY_CHAR_UUID,
        delay: float = 0.05,
        use_response: bool = False,
    ) -> None:
        self.address = address
        self.write_char_uuid = write_char_uuid
        self.notify_char_uuid = notify_char_uuid
        self.delay = delay
        self.use_response = use_response
        self._client: BleakClient | None = None
        self._notification_event: asyncio.Event = asyncio.Event()

    def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle notifications/indications from the device."""
        log.info("Response from device: {}", data.hex())
        self._notification_event.set()

    async def _write_packet(
        self, packet: bytearray, wait_ack: bool = True, timeout: float = 0.75
    ) -> bool:
        """Write a single packet and optionally wait for acknowledgment."""
        if self._client is None or not self._client.is_connected:
            raise RuntimeError("Not connected")

        self._notification_event.clear()
        log.debug("Sending: {}", packet.hex())

        await self._client.write_gatt_char(
            self.write_char_uuid,
            packet,
            response=self.use_response,
        )

        if wait_ack:
            try:
                await asyncio.wait_for(self._notification_event.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                log.warning("No acknowledgment received (timeout {}s)", timeout)
                return False

        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return True

    async def connect(self) -> None:
        """Connect to the device and enable notifications/indications."""
        log.info("Connecting to {}", self.address)
        self._client = BleakClient(self.address)
        await self._client.connect()
        log.info("Connected: {}", self._client.is_connected)

        # Try to enable indications on Service Changed characteristic
        try:
            await self._client.start_notify(
                SERVICE_CHANGED_UUID, self._notification_handler
            )
            log.info("Indications enabled on Service Changed (2A05)")
        except Exception as e:
            log.debug("Could not enable Service Changed indications: {}", e)

        # Enable notifications/indications on FFF1
        try:
            await self._client.start_notify(
                self.notify_char_uuid, self._notification_handler
            )
            log.info("Notifications enabled on {}", self.notify_char_uuid[:12])
        except Exception as e:
            log.warning("Could not enable notifications on FFF1: {}", e)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(self.notify_char_uuid)
            except Exception:
                pass
            try:
                await self._client.stop_notify(SERVICE_CHANGED_UUID)
            except Exception:
                pass
            log.debug("Disconnecting from {}", self.address)
            await self._client.disconnect()
        self._client = None

    async def __aenter__(self) -> "LedBackpackClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def reset(self) -> None:
        """Send reset and ready commands with proper delays."""
        log.info("Sending reset command...")
        await self._write_packet(build_reset_command(), wait_ack=False)
        await asyncio.sleep(0.5)

        log.info("Sending ready command...")
        await self._write_packet(build_ready_command(), wait_ack=False)
        await asyncio.sleep(0.5)

    async def set_solid_color(
        self,
        color: str,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        """Send a solid-color image using GIF upload protocol."""
        log.info("Sending solid color {} ({}x{})", color, width, height)

        # Get all packets (includes reset, ready, data, complete)
        packets = build_solid_color_packets(width, height, color)
        log.info("Built {} packet(s) for upload", len(packets))

        # Send reset and ready with delays
        log.info("Step 1: Reset")
        await self._write_packet(packets[0], wait_ack=False)
        await asyncio.sleep(0.5)

        log.info("Step 2: Ready")
        await self._write_packet(packets[1], wait_ack=False)
        await asyncio.sleep(0.5)

        # Send data packets with ack waiting
        data_packets = packets[2:-2]
        log.info("Step 3: Upload {} data packet(s)", len(data_packets))
        for i, packet in enumerate(data_packets, start=1):
            log.info("Data packet {}/{} ({} bytes)", i, len(data_packets), len(packet))
            await self._write_packet(packet, wait_ack=True, timeout=0.75)

        # Send upload complete (twice)
        log.info("Step 4: Upload complete")
        await self._write_packet(packets[-2], wait_ack=False)
        await self._write_packet(packets[-1], wait_ack=False)

        log.info("Upload sequence complete")

    async def clear(self) -> None:
        """Send reset/clear command (calls reset())."""
        await self.reset()

    async def set_grid_pattern(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        grid_size: int = 8,
        color1: str = "#ffffff",
        color2: str = "#000000",
    ) -> None:
        """Send a grid/checkerboard pattern using GIF upload protocol."""
        log.info(
            "Sending grid pattern {}x{} (cell size {})",
            width,
            height,
            grid_size,
        )

        packets = build_grid_pattern_packets(width, height, grid_size, color1, color2)
        log.info("Built {} packet(s) for upload", len(packets))

        # Send reset and ready with delays
        log.info("Step 1: Reset")
        await self._write_packet(packets[0], wait_ack=False)
        await asyncio.sleep(0.5)

        log.info("Step 2: Ready")
        await self._write_packet(packets[1], wait_ack=False)
        await asyncio.sleep(0.5)

        # Send data packets with ack waiting
        data_packets = packets[2:-2]
        log.info("Step 3: Upload {} data packet(s)", len(data_packets))
        for i, packet in enumerate(data_packets, start=1):
            log.info("Data packet {}/{} ({} bytes)", i, len(data_packets), len(packet))
            await self._write_packet(packet, wait_ack=True, timeout=0.75)

        # Send upload complete (twice)
        log.info("Step 4: Upload complete")
        await self._write_packet(packets[-2], wait_ack=False)
        await self._write_packet(packets[-1], wait_ack=False)

        log.info("Grid pattern upload complete")

    async def set_brightness(self, level: int) -> None:
        """Set brightness 0-255 (mapped to 0-15 internally)."""
        if level < 0 or level > 255:
            raise ValueError("Brightness must be 0-255")
        # Map 0-255 to 0-15
        mapped_level = level * BRIGHTNESS_LEVELS // 256
        log.info("Sending brightness {} (level {})", level, mapped_level)
        await self._write_packet(build_brightness_command(mapped_level), wait_ack=False)


async def discover_backpack(
    *,
    name: str | None = None,
    address: str | None = None,
    timeout: float = 10.0,
) -> tuple[str | None, int | None, int | None]:
    """
    Scan for a LOY SPACE backpack.

    Returns (address, width, height) or (None, None, None).
    Default dimensions are 96x128 if not detected from advertisement.
    """
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for device, adv in devices.values():
        device_name = device.name or ""
        if address and device.address.lower() != address.lower():
            continue
        if name and name.lower() not in device_name.lower():
            continue
        # Try to get dimensions from manufacturer data
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        if adv.manufacturer_data:
            value = next(iter(adv.manufacturer_data.values()))
            if len(value) >= 11:
                height = value[6]
                width = value[7] << 8 | value[8]
        return device.address, width, height
    return None, None, None
