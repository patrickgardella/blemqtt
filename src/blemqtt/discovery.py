import json
import re
from collections.abc import Iterable

from blemqtt.config import SensorConfig
from blemqtt.drivers.base import Driver

SERVICE_STATUS_TOPIC = "blemqtt/status"
DISCOVERY_FILTER = "homeassistant/sensor/blemqtt_+/+/config"
_DISCOVERY_TOPIC_RE = re.compile(r"^homeassistant/sensor/blemqtt_([^/]+)/[^/]+/config$")


def state_topic(node_id: str) -> str:
    return f"blemqtt/{node_id}/state"


def availability_topic(node_id: str) -> str:
    return f"blemqtt/{node_id}/availability"


def discovery_topic(node_id: str, key: str) -> str:
    return f"homeassistant/sensor/blemqtt_{node_id}/{key}/config"


def node_id_from_discovery_topic(topic: str) -> str | None:
    match = _DISCOVERY_TOPIC_RE.match(topic)
    return match.group(1) if match else None


def discovery_messages(sensor: SensorConfig, driver: Driver) -> list[tuple[str, str]]:
    node_id = sensor.node_id
    device = {
        "identifiers": [f"blemqtt_{node_id}"],
        "name": sensor.name,
        "manufacturer": driver.manufacturer,
        "model": driver.model,
    }
    messages = []
    for spec in driver.readings:
        config: dict = {
            "name": spec.name,
            "unique_id": f"blemqtt_{node_id}_{spec.key}",
            "state_topic": state_topic(node_id),
            "value_template": f"{{{{ value_json.{spec.key} }}}}",
            "state_class": "measurement",
            "availability": [
                {"topic": SERVICE_STATUS_TOPIC},
                {"topic": availability_topic(node_id)},
            ],
            "availability_mode": "all",
            "device": device,
        }
        if spec.unit:
            config["unit_of_measurement"] = spec.unit
        if spec.device_class:
            config["device_class"] = spec.device_class
        if spec.icon:
            config["icon"] = spec.icon
        messages.append((discovery_topic(node_id, spec.key), json.dumps(config, ensure_ascii=False)))
    return messages


def clear_messages(node_id: str, keys: Iterable[str]) -> list[tuple[str, str]]:
    return [(discovery_topic(node_id, key), "") for key in keys]
