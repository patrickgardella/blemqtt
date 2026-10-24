import struct

import pytest

from blemqtt.drivers import get_driver
from blemqtt.drivers.airthings_wave1 import AirthingsWave1
from blemqtt.drivers.base import ParseError

PAYLOAD = struct.pack("<4B8H", 1, 90, 0, 0, 45, 50, 2150, 0, 0, 0, 0, 0)


def test_parse_valid_payload():
    assert AirthingsWave1().parse(PAYLOAD) == {
        "radon_sta": 45.0,
        "radon_lta": 50.0,
        "temperature": 21.5,
        "humidity": 45.0,
    }


def test_invalid_radon_becomes_none():
    p = struct.pack("<4B8H", 1, 90, 0, 0, 0xFFFF, 0xFFFF, 2150, 0, 0, 0, 0, 0)
    r = AirthingsWave1().parse(p)
    assert r["radon_sta"] is None and r["radon_lta"] is None
    assert r["temperature"] == 21.5


@pytest.mark.parametrize("bad", [b"", b"\x01\x02", PAYLOAD[:-1]])
def test_wrong_length_raises(bad):
    with pytest.raises(ParseError):
        AirthingsWave1().parse(bad)


def test_unknown_version_raises():
    with pytest.raises(ParseError):
        AirthingsWave1().parse(struct.pack("<4B8H", 9, *([0] * 11)))


def test_registered_under_type_name():
    assert isinstance(get_driver("airthings_wave1"), AirthingsWave1)


def test_reading_keys_match_parse_output():
    d = AirthingsWave1()
    assert {s.key for s in d.readings} == set(d.parse(PAYLOAD))
