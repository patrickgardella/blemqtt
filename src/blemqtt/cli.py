import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from bleak import BleakScanner

from blemqtt.ble_lock import LockTimeout, ble_lock
from blemqtt.config import ConfigError, load_app_config
from blemqtt.drivers import get_driver
from blemqtt.drivers.base import ParseError, ReadError

READ_TIMEOUT = 60.0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (ConfigError, ReadError, ParseError, LockTimeout, KeyError) as e:
        print(f"error: {e.args[0] if isinstance(e, KeyError) else e}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blemqtt", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list nearby BLE devices")
    scan.add_argument("--timeout", type=float, default=10.0)
    scan.set_defaults(func=_scan)

    read = sub.add_parser("read", help="read one sensor once and print the values")
    target = read.add_mutually_exclusive_group(required=True)
    target.add_argument("--sensor", help="sensor name from the config file")
    target.add_argument("--address", help="BLE address (requires --driver)")
    read.add_argument("--driver", help="driver type, with --address")
    read.add_argument("--config", type=Path, default=Path("config.toml"))
    read.add_argument("--json", action="store_true")
    read.set_defaults(func=_read)

    run = sub.add_parser("run", help="poll sensors and publish to MQTT")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    run.add_argument("--env", type=Path, default=Path(".env"))
    run.set_defaults(func=_run)
    return parser


def _scan(args) -> int:
    async def scan():
        return await BleakScanner.discover(timeout=args.timeout, return_adv=True)

    found = asyncio.run(scan())
    for address, (device, adv) in sorted(found.items(), key=lambda kv: -kv[1][1].rssi):
        print(f"{address}  {adv.rssi:>4} dBm  {device.name or '(unnamed)'}")
    return 0


def _read(args) -> int:
    if args.address:
        if not args.driver:
            raise ConfigError("--address requires --driver")
        address, driver_name = args.address, args.driver
    else:
        config = load_app_config(args.config)
        sensor = next((s for s in config.sensors if s.name == args.sensor), None)
        if sensor is None:
            raise ConfigError(f"no sensor named {args.sensor!r} in {args.config}")
        address, driver_name = sensor.address, sensor.driver

    driver = get_driver(driver_name)

    async def read():
        async with ble_lock():
            return await driver.read(address, READ_TIMEOUT)

    readings = asyncio.run(read())
    if args.json:
        print(json.dumps(readings))
    else:
        for spec in driver.readings:
            value = readings.get(spec.key)
            text = "unknown" if value is None else f"{value} {spec.unit or ''}".strip()
            print(f"{spec.name}: {text}")
    return 0


def _run(args) -> int:
    from blemqtt.config import load_mqtt_settings
    from blemqtt.service import run

    config = load_app_config(args.config)
    settings = load_mqtt_settings(args.env)
    asyncio.run(run(config, settings))
    return 0
