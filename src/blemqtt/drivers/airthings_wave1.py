import asyncio
import struct

from bleak import BleakClient
from bleak.exc import BleakError

from blemqtt.drivers.base import Driver, ParseError, ReadError
from blemqtt.models import ReadingSpec, Readings

# Read in this order; parse() takes their raw bytes concatenated in the same order.
CHAR_UUIDS = (
    "00002a6e-0000-1000-8000-00805f9b34fb",  # temperature, int16 LE, 0.01 °C
    "00002a6f-0000-1000-8000-00805f9b34fb",  # humidity, uint16 LE, 0.01 %
    "b42e01aa-ade7-11e4-89d3-123b93f75cba",  # radon, current (24 h), uint16 LE, Bq/m³ on the wire
    "b42e0a4c-ade7-11e4-89d3-123b93f75cba",  # radon, long-term average, uint16 LE, Bq/m³ on the wire
)
_FORMAT = struct.Struct("<hHHH")
_INVALID_RADON = 0xFFFF
ATTEMPTS = 3
RETRY_DELAY = 2.0
_BQ_PER_M3_PER_PCI_L = 37  # 1 pCi/L = 37 Bq/m³


class AirthingsWave1(Driver):
    type_name = "airthings_wave1"
    manufacturer = "Airthings"
    model = "Wave (Gen 1)"
    readings = (
        ReadingSpec("radon_sta", "Radon (24 h average)", "pCi/L", "radon", "mdi:radioactive"),
        ReadingSpec("radon_lta", "Radon (long-term average)", "pCi/L", "radon", "mdi:radioactive"),
        ReadingSpec("temperature", "Temperature", "°C", "temperature"),
        ReadingSpec("humidity", "Humidity", "%", "humidity"),
    )

    def parse(self, payload: bytes) -> Readings:
        if len(payload) != _FORMAT.size:
            raise ParseError(f"expected {_FORMAT.size} bytes, got {len(payload)}")
        temperature, humidity, radon_sta, radon_lta = _FORMAT.unpack(payload)
        return {
            "radon_sta": _radon(radon_sta),
            "radon_lta": _radon(radon_lta),
            "temperature": temperature / 100,
            "humidity": humidity / 100,
        }

    async def read(self, address: str, timeout: float) -> Readings:
        """Read all characteristics, retrying a flaky connection within the `timeout` budget."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        last_error: Exception | None = None
        for attempt in range(ATTEMPTS):
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            if attempt:
                await asyncio.sleep(RETRY_DELAY)
            try:
                return self.parse(await self._read_once(address, remaining))
            except (BleakError, asyncio.TimeoutError, OSError) as e:
                last_error = e
        detail = str(last_error) or type(last_error).__name__ if last_error else "timed out"
        raise ReadError(f"{address}: {detail}") from last_error

    async def _read_once(self, address: str, timeout: float) -> bytes:
        async with BleakClient(address, timeout=timeout) as client:
            async with asyncio.timeout(timeout):
                return b"".join([bytes(await client.read_gatt_char(uuid)) for uuid in CHAR_UUIDS])


def _radon(raw: int) -> float | None:
    """Device reports Bq/m³; Home Assistant here shows pCi/L."""
    return None if raw == _INVALID_RADON else round(raw / _BQ_PER_M3_PER_PCI_L, 2)
