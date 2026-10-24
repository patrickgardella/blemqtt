import asyncio
import logging
import signal

from blemqtt.ble_lock import ble_lock
from blemqtt.config import AppConfig, MqttSettings, SensorConfig
from blemqtt.drivers import get_driver
from blemqtt.drivers.base import Driver
from blemqtt.publisher import Publisher

log = logging.getLogger(__name__)


async def poll_once(
    sensors: list[tuple[SensorConfig, Driver]],
    publisher: Publisher,
    failures: dict[str, int],
    threshold: int,
    read_timeout: float = 60.0,
    lock_timeout: float = 60.0,
) -> None:
    for sensor, driver in sensors:
        try:
            async with ble_lock(lock_timeout):
                # bleak bounds connect and each read, not the disconnect; cap the whole read
                readings = await asyncio.wait_for(driver.read(sensor.address, read_timeout), read_timeout * 2)
        except Exception as e:
            count = failures.get(sensor.node_id, 0) + 1
            failures[sensor.node_id] = count
            log.warning("reading %s failed (%d in a row): %s", sensor.name, count, str(e) or type(e).__name__)
            if count == threshold:
                publisher.mark_unavailable(sensor)
            continue
        failures[sensor.node_id] = 0
        publisher.publish_readings(sensor, readings)


async def run(
    config: AppConfig,
    settings: MqttSettings,
    publisher: Publisher | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    stop = stop or asyncio.Event()
    sensors = [(s, get_driver(s.driver)) for s in config.sensors]
    publisher = publisher or Publisher(settings, sensors)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    publisher.start()
    failures: dict[str, int] = {}
    try:
        while not stop.is_set():
            await poll_once(sensors, publisher, failures, config.failure_threshold)
            try:
                await asyncio.wait_for(stop.wait(), config.interval_seconds)
            except asyncio.TimeoutError:
                pass
    finally:
        publisher.stop()
