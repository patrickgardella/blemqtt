import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from blemqtt.drivers import DRIVERS

DEFAULT_MQTT_PORT = 1883
DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_FAILURE_THRESHOLD = 3


class ConfigError(Exception):
    """Configuration is missing or invalid. Messages never contain secret values."""


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class SensorConfig:
    name: str
    address: str
    driver: str

    @property
    def node_id(self) -> str:
        return self.address.lower().replace(":", "").replace("-", "")


@dataclass(frozen=True)
class AppConfig:
    interval_seconds: int
    failure_threshold: int
    sensors: list[SensorConfig]


def load_mqtt_settings(env_path: Path) -> MqttSettings:
    if not Path(env_path).is_file():
        raise ConfigError(f"env file not found: {env_path}")
    values = dotenv_values(env_path)
    missing = [k for k in ("MQTTUI_BROKER", "MQTTUI_USERNAME", "MQTTUI_PASSWORD") if not values.get(k)]
    if missing:
        raise ConfigError(f"missing in {env_path}: {', '.join(missing)}")
    broker = urlsplit(values["MQTTUI_BROKER"])
    if broker.scheme == "mqtts":
        raise ConfigError("TLS brokers (mqtts://) are not supported")
    if not broker.hostname:
        raise ConfigError("MQTTUI_BROKER must look like mqtt://host[:port]")
    try:
        port = broker.port or DEFAULT_MQTT_PORT
    except ValueError:
        raise ConfigError("MQTTUI_BROKER has an invalid port") from None
    return MqttSettings(broker.hostname, port, values["MQTTUI_USERNAME"], values["MQTTUI_PASSWORD"])


def load_app_config(path: Path) -> AppConfig:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None

    interval = data.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
    threshold = data.get("failure_threshold", DEFAULT_FAILURE_THRESHOLD)
    for key, value in (("interval_seconds", interval), ("failure_threshold", threshold)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ConfigError(f"{key} must be a positive integer")

    sensors: list[SensorConfig] = []
    for entry in data.get("sensors", []):
        for key in ("name", "address", "driver"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ConfigError(f"sensor entry is missing {key!r}: {entry}")
        if entry["driver"] not in DRIVERS:
            raise ConfigError(
                f"unknown driver {entry['driver']!r} for sensor {entry['name']!r}; "
                f"known: {', '.join(sorted(DRIVERS))}"
            )
        sensor = SensorConfig(entry["name"], entry["address"], entry["driver"])
        if any(s.node_id == sensor.node_id for s in sensors):
            raise ConfigError(f"duplicate sensor address: {sensor.address}")
        sensors.append(sensor)
    return AppConfig(interval, threshold, sensors)
