import struct

import pytest
from bleak.exc import BleakError

from blemqtt.drivers import get_driver
from blemqtt.drivers.airthings_wave1 import CHAR_UUIDS, AirthingsWave1
from blemqtt.drivers.base import ParseError, ReadError

# Bytes read from a real Wave on 2026-10-24, in parse() order:
# temperature (2a6e), humidity (2a6f), radon current (b42e01aa), radon long-term (b42e0a4c).
REAL_PAYLOAD = bytes.fromhex("a807" "0019" "1a00" "2200")
PAYLOAD = struct.pack("<hHHH", 2150, 4500, 45, 50)


def test_parse_real_device_bytes():
    assert AirthingsWave1().parse(REAL_PAYLOAD) == {
        "radon_sta": 0.7,
        "radon_lta": 0.92,
        "temperature": 19.6,
        "humidity": 64.0,
    }


def test_parse_valid_payload():
    assert AirthingsWave1().parse(PAYLOAD) == {
        "radon_sta": 1.22,
        "radon_lta": 1.35,
        "temperature": 21.5,
        "humidity": 45.0,
    }


def test_radon_is_converted_from_bq_per_m3_to_pci_per_l():
    r = AirthingsWave1().parse(struct.pack("<hHHH", 2150, 4500, 148, 37))
    assert r["radon_sta"] == 4.0  # the US action level, 148 Bq/m³
    assert r["radon_lta"] == 1.0


def test_negative_temperature():
    r = AirthingsWave1().parse(struct.pack("<hHHH", -550, 4500, 45, 50))
    assert r["temperature"] == -5.5


def test_invalid_radon_becomes_none():
    r = AirthingsWave1().parse(struct.pack("<hHHH", 2150, 4500, 0xFFFF, 0xFFFF))
    assert r["radon_sta"] is None and r["radon_lta"] is None
    assert r["temperature"] == 21.5


@pytest.mark.parametrize("bad", [b"", b"\x01\x02", PAYLOAD[:-1], PAYLOAD + b"\x00"])
def test_wrong_length_raises(bad):
    with pytest.raises(ParseError):
        AirthingsWave1().parse(bad)


def test_registered_under_type_name():
    assert isinstance(get_driver("airthings_wave1"), AirthingsWave1)


def test_reading_keys_match_parse_output():
    d = AirthingsWave1()
    assert {s.key for s in d.readings} == set(d.parse(PAYLOAD))


class FakeBleakClient:
    """Fails the first `failures` connection attempts, then serves REAL_PAYLOAD."""

    failures = 0
    attempts = 0
    error = BleakError("")

    def __init__(self, address, timeout):
        type(self).attempts += 1
        self._fail = type(self).attempts <= type(self).failures

    async def __aenter__(self):
        if self._fail:
            raise type(self).error
        return self

    async def __aexit__(self, *exc):
        return False

    async def read_gatt_char(self, uuid):
        index = CHAR_UUIDS.index(uuid)
        return REAL_PAYLOAD[index * 2 : index * 2 + 2]


@pytest.fixture
def fake_bleak(monkeypatch):
    FakeBleakClient.failures = 0
    FakeBleakClient.attempts = 0
    FakeBleakClient.error = BleakError("")
    monkeypatch.setattr("blemqtt.drivers.airthings_wave1.BleakClient", FakeBleakClient)
    monkeypatch.setattr("blemqtt.drivers.airthings_wave1.RETRY_DELAY", 0)
    return FakeBleakClient


async def test_read_retries_transient_failures(fake_bleak):
    fake_bleak.failures = 2
    r = await AirthingsWave1().read("AA:BB", timeout=5)
    assert r["temperature"] == 19.6
    assert fake_bleak.attempts == 3


async def test_read_gives_up_after_three_attempts_with_a_useful_message(fake_bleak):
    fake_bleak.failures = 99
    with pytest.raises(ReadError) as e:
        await AirthingsWave1().read("AA:BB", timeout=5)
    assert fake_bleak.attempts == 3
    assert str(e.value).strip() != "AA:BB:"
    assert "BleakError" in str(e.value)


async def test_read_does_not_retry_unparseable_data(fake_bleak, monkeypatch):
    monkeypatch.setattr(AirthingsWave1, "parse", lambda self, payload: (_ for _ in ()).throw(ParseError("bad")))
    with pytest.raises(ParseError):
        await AirthingsWave1().read("AA:BB", timeout=5)
    assert fake_bleak.attempts == 1
