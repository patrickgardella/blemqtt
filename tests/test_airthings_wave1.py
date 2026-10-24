import struct

import pytest

from blemqtt.drivers import get_driver
from blemqtt.drivers.airthings_wave1 import AirthingsWave1
from blemqtt.drivers.base import ParseError

# Bytes read from a real Wave on 2026-10-24, in parse() order:
# temperature (2a6e), humidity (2a6f), radon current (b42e01aa), radon long-term (b42e0a4c).
REAL_PAYLOAD = bytes.fromhex("a807" "0019" "1a00" "2200")
PAYLOAD = struct.pack("<hHHH", 2150, 4500, 45, 50)


def test_parse_real_device_bytes():
    assert AirthingsWave1().parse(REAL_PAYLOAD) == {
        "radon_sta": 26.0,
        "radon_lta": 34.0,
        "temperature": 19.6,
        "humidity": 64.0,
    }


def test_parse_valid_payload():
    assert AirthingsWave1().parse(PAYLOAD) == {
        "radon_sta": 45.0,
        "radon_lta": 50.0,
        "temperature": 21.5,
        "humidity": 45.0,
    }


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
