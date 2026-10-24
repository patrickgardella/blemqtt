import json

import jinja2

from blemqtt.config import SensorConfig
from blemqtt.discovery import (
    DISCOVERY_FILTER,
    SERVICE_STATUS_TOPIC,
    availability_topic,
    clear_messages,
    discovery_messages,
    discovery_topic,
    node_id_from_discovery_topic,
    state_topic,
)
from blemqtt.drivers.airthings_wave1 import AirthingsWave1

SENSOR = SensorConfig("Basement Radon", "AA:BB:CC:00:11:22", "airthings_wave1")
DRIVER = AirthingsWave1()


def messages():
    return {topic: json.loads(payload) for topic, payload in discovery_messages(SENSOR, DRIVER)}


def test_topic_names():
    assert state_topic("aabbcc001122") == "blemqtt/aabbcc001122/state"
    assert availability_topic("aabbcc001122") == "blemqtt/aabbcc001122/availability"
    assert SERVICE_STATUS_TOPIC == "blemqtt/status"
    assert discovery_topic("aabbcc001122", "radon_sta") == (
        "homeassistant/sensor/blemqtt_aabbcc001122/radon_sta/config"
    )
    assert DISCOVERY_FILTER == "homeassistant/sensor/blemqtt_+/+/config"


def test_one_message_per_reading():
    assert len(messages()) == 4


def test_radon_message_contents():
    m = messages()["homeassistant/sensor/blemqtt_aabbcc001122/radon_sta/config"]
    assert m["unique_id"] == "blemqtt_aabbcc001122_radon_sta"
    assert m["state_topic"] == "blemqtt/aabbcc001122/state"
    assert m["unit_of_measurement"] == "Bq/m³"
    assert m["state_class"] == "measurement"
    assert m["device_class"] == "radon"


def test_temperature_device_class():
    m = messages()["homeassistant/sensor/blemqtt_aabbcc001122/temperature/config"]
    assert m["device_class"] == "temperature"
    assert m["unit_of_measurement"] == "°C"
    assert "icon" not in m


def test_availability_requires_service_and_sensor():
    for m in messages().values():
        assert m["availability_mode"] == "all"
        assert {a["topic"] for a in m["availability"]} == {
            "blemqtt/status",
            "blemqtt/aabbcc001122/availability",
        }


def test_device_is_shared_and_stable():
    devices = [m["device"] for m in messages().values()]
    assert all(d == devices[0] for d in devices)
    assert devices[0]["identifiers"] == ["blemqtt_aabbcc001122"]
    assert devices[0]["name"] == "Basement Radon"
    assert devices[0]["manufacturer"] == "Airthings"
    assert devices[0]["model"] == "Wave (Gen 1)"


def test_value_template_yields_unknown_for_null():
    m = messages()["homeassistant/sensor/blemqtt_aabbcc001122/radon_sta/config"]
    template = jinja2.Template(m["value_template"])
    assert template.render(value_json={"radon_sta": 45.0}) == "45.0"
    # Home Assistant documents the rendered string 'None' as the unknown state.
    assert template.render(value_json={"radon_sta": None}) == "None"


def test_clear_messages_are_empty_payloads_on_same_topics():
    cleared = clear_messages("aabbcc001122", ["radon_sta", "humidity"])
    assert cleared == [
        ("homeassistant/sensor/blemqtt_aabbcc001122/radon_sta/config", ""),
        ("homeassistant/sensor/blemqtt_aabbcc001122/humidity/config", ""),
    ]


def test_node_id_from_discovery_topic():
    topic = discovery_topic("aabbcc001122", "radon_sta")
    assert node_id_from_discovery_topic(topic) == "aabbcc001122"
    assert node_id_from_discovery_topic("homeassistant/sensor/other_thing/x/config") is None
    assert node_id_from_discovery_topic("homeassistant/light/blemqtt_aa/x/config") is None
