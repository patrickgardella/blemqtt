import asyncio
import struct

from bleak import BleakClient
from bleak.exc import BleakError

from blemqtt.drivers.base import Driver, ParseError, ReadError
from blemqtt.models import ReadingSpec, Readings

CHAR_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
_FORMAT = struct.Struct("<4B8H")
_INVALID_RADON = 0xFFFF


class AirthingsWave1(Driver):
    type_name = "airthings_wave1"
    manufacturer = "Airthings"
    model = "Wave (Gen 1)"
    readings = (
        ReadingSpec("radon_sta", "Radon short-term average", "Bq/m³", None, "mdi:radioactive"),
        ReadingSpec("radon_lta", "Radon long-term average", "Bq/m³", None, "mdi:radioactive"),
        ReadingSpec("temperature", "Temperature", "°C", "temperature"),
        ReadingSpec("humidity", "Humidity", "%", "humidity"),
    )

    def parse(self, payload: bytes) -> Readings:
        if len(payload) != _FORMAT.size:
            raise ParseError(f"expected {_FORMAT.size} bytes, got {len(payload)}")
        version, humidity, _light, _unused, radon_sta, radon_lta, temperature, *_ = _FORMAT.unpack(payload)
        if version != 1:
            raise ParseError(f"unsupported payload version {version}")
        return {
            "radon_sta": _radon(radon_sta),
            "radon_lta": _radon(radon_lta),
            "temperature": temperature / 100,
            "humidity": humidity / 2,
        }

    async def read(self, address: str, timeout: float) -> Readings:
        try:
            async with BleakClient(address, timeout=timeout) as client:
                payload = await asyncio.wait_for(client.read_gatt_char(CHAR_UUID), timeout)
        except (BleakError, asyncio.TimeoutError, OSError) as e:
            raise ReadError(f"{address}: {e or type(e).__name__}") from e
        return self.parse(bytes(payload))


def _radon(raw: int) -> float | None:
    return None if raw == _INVALID_RADON else float(raw)
