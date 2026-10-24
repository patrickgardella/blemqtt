import asyncio
import logging

import pytest

from blemqtt.config import AppConfig, MqttSettings, SensorConfig
from blemqtt.drivers.base import Driver, ParseError, ReadError
from blemqtt.models import ReadingSpec
from blemqtt.service import poll_once, run

A = SensorConfig("A", "AA:AA:AA:AA:AA:AA", "fake")
B = SensorConfig("B", "BB:BB:BB:BB:BB:BB", "fake")


class FakeDriver(Driver):
    type_name = "fake"
    manufacturer = "Fake"
    model = "Fake"
    readings = (ReadingSpec("x", "X", None, None),)

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def parse(self, payload):
        raise NotImplementedError

    async def read(self, address, timeout):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePublisher:
    def __init__(self):
        self.events = []

    def start(self):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")

    def publish_readings(self, sensor, readings):
        self.events.append(("publish", sensor.name, readings))

    def mark_unavailable(self, sensor):
        self.events.append(("unavailable", sensor.name))


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


async def test_failing_sensor_does_not_block_the_next_one():
    pub = FakePublisher()
    sensors = [(A, FakeDriver(ReadError("out of range"))), (B, FakeDriver({"x": 1.0}))]
    await poll_once(sensors, pub, {}, threshold=3)
    assert ("publish", "B", {"x": 1.0}) in pub.events


async def test_unavailable_after_threshold_exactly_once_then_recovers():
    pub, failures = FakePublisher(), {}
    bad = FakeDriver(ReadError("nope"))
    for _ in range(5):
        await poll_once([(A, bad)], pub, failures, threshold=3)
    assert pub.events.count(("unavailable", "A")) == 1
    good = FakeDriver({"x": 2.0})
    await poll_once([(A, good)], pub, failures, threshold=3)
    assert pub.events[-1] == ("publish", "A", {"x": 2.0})
    assert failures[A.node_id] == 0


async def test_parse_error_counts_as_failure(caplog):
    pub, failures = FakePublisher(), {}
    with caplog.at_level(logging.WARNING):
        await poll_once([(A, FakeDriver(ParseError("bad bytes")))], pub, failures, threshold=1)
    assert failures[A.node_id] == 1
    assert ("unavailable", "A") in pub.events
    assert "A" in caplog.text and "bad bytes" in caplog.text


async def test_unexpected_error_does_not_crash_the_cycle():
    pub = FakePublisher()
    sensors = [(A, FakeDriver(RuntimeError("boom"))), (B, FakeDriver({"x": 1.0}))]
    await poll_once(sensors, pub, {}, threshold=3)
    assert ("publish", "B", {"x": 1.0}) in pub.events


async def test_run_starts_polls_and_stops_cleanly(monkeypatch):
    pub = FakePublisher()
    stop = asyncio.Event()
    driver = FakeDriver({"x": 1.0})
    monkeypatch.setattr("blemqtt.service.get_driver", lambda name: driver)

    original = pub.publish_readings

    def publish_then_stop(sensor, readings):
        original(sensor, readings)
        stop.set()

    pub.publish_readings = publish_then_stop
    config = AppConfig(interval_seconds=3600, failure_threshold=3, sensors=[A])
    await asyncio.wait_for(
        run(config, MqttSettings("h", 1883, "u", "p"), publisher=pub, stop=stop), timeout=5
    )
    assert pub.events[0] == "start" and pub.events[-1] == "stop"
    assert ("publish", "A", {"x": 1.0}) in pub.events
