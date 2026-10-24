import json
import subprocess
import sys

import pytest

from blemqtt import cli
from blemqtt.drivers.base import Driver, ReadError
from blemqtt.models import ReadingSpec


class FakeDriver(Driver):
    type_name = "fake"
    manufacturer = "Fake"
    model = "Fake"
    readings = (
        ReadingSpec("temperature", "Temperature", "°C", "temperature"),
        ReadingSpec("radon", "Radon", "Bq/m³", None),
    )
    result = {"temperature": 21.5, "radon": None}

    def parse(self, payload):
        raise NotImplementedError

    async def read(self, address, timeout):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def fake_driver(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "get_driver", lambda name: FakeDriver())
    FakeDriver.result = {"temperature": 21.5, "radon": None}


def test_read_json_has_null_for_missing_reading(capsys):
    assert cli.main(["read", "--address", "AA:BB", "--driver", "fake", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"temperature": 21.5, "radon": None}


def test_read_text_shows_units_and_unknown(capsys):
    assert cli.main(["read", "--address", "AA:BB", "--driver", "fake"]) == 0
    out = capsys.readouterr().out
    assert "Temperature: 21.5 °C" in out
    assert "Radon: unknown" in out


def test_read_failure_is_nonzero_with_one_line_on_stderr(capsys):
    FakeDriver.result = ReadError("AA:BB: device not found")
    assert cli.main(["read", "--address", "AA:BB", "--driver", "fake"]) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().count("\n") == 0
    assert "device not found" in captured.err


def test_read_sensor_by_name_uses_config(tmp_path, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[[sensors]]\nname = "Basement"\naddress = "AA:BB"\ndriver = "airthings_wave1"\n')
    assert cli.main(["read", "--sensor", "Basement", "--config", str(cfg)]) == 0
    assert "Temperature: 21.5" in capsys.readouterr().out


def test_read_unknown_sensor_name_is_nonzero_and_named(tmp_path, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("")
    assert cli.main(["read", "--sensor", "Missing", "--config", str(cfg)]) != 0
    assert "Missing" in capsys.readouterr().err


def test_read_needs_sensor_or_address(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["read"])
    assert e.value.code != 0


def test_read_never_loads_mqtt_code():
    code = (
        "import sys; from blemqtt import cli; "
        "sys.exit(1 if 'paho' in ' '.join(sys.modules) else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_scan_lists_devices(monkeypatch, capsys):
    class Dev:
        address, name = "AA:BB:CC:00:11:22", "Airthings 123"

    class Adv:
        rssi = -60

    async def discover(timeout, return_adv):
        return {"AA:BB:CC:00:11:22": (Dev(), Adv())}

    monkeypatch.setattr(cli.BleakScanner, "discover", discover)
    assert cli.main(["scan", "--timeout", "1"]) == 0
    out = capsys.readouterr().out
    assert "AA:BB:CC:00:11:22" in out and "Airthings 123" in out and "-60" in out
