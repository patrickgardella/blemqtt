import json
import logging
from types import SimpleNamespace

import pytest

from blemqtt.config import MqttSettings, SensorConfig
from blemqtt.discovery import DISCOVERY_FILTER, discovery_topic
from blemqtt.drivers.airthings_wave1 import AirthingsWave1
from blemqtt.publisher import Publisher

SENSOR = SensorConfig("Basement Radon", "AA:BB:CC:00:11:22", "airthings_wave1")
SETTINGS = MqttSettings("broker.example", 1883, "user", "s3cret-pw")


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscribed = []
        self.unsubscribed = []
        self.will = None
        self.credentials = None
        self.connected_to = None
        self.loop_started = False
        self.on_connect = None
        self.on_message = None

    def username_pw_set(self, username, password):
        self.credentials = (username, password)

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, payload, retain)

    def reconnect_delay_set(self, min_delay, max_delay):
        pass

    def connect_async(self, host, port):
        self.connected_to = (host, port)

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_started = False

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))
        return SimpleNamespace(wait_for_publish=lambda timeout=None: None)

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def unsubscribe(self, topic):
        self.unsubscribed.append(topic)


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def publisher(client):
    p = Publisher(SETTINGS, [(SENSOR, AirthingsWave1())], client=client, clear_wait=3600)
    yield p
    p.stop()


def connect(client):
    client.on_connect(client, None, {}, 0, None)


def retained(client, topic):
    return [(t, p) for t, p, r in client.published if t == topic and r]


def test_start_configures_will_credentials_and_connects(publisher, client):
    publisher.start()
    assert client.will == ("blemqtt/status", "offline", True)
    assert client.credentials == ("user", "s3cret-pw")
    assert client.connected_to == ("broker.example", 1883)
    assert client.loop_started


def test_connect_publishes_online_and_retained_discovery(publisher, client):
    publisher.start()
    connect(client)
    assert retained(client, "blemqtt/status") == [("blemqtt/status", "online")]
    for key in ("radon_sta", "radon_lta", "temperature", "humidity"):
        topic = discovery_topic("aabbcc001122", key)
        assert len(retained(client, topic)) == 1
        assert json.loads(retained(client, topic)[0][1])["unique_id"].endswith(key)


def test_reconnect_republishes_discovery_and_online(publisher, client):
    publisher.start()
    connect(client)
    connect(client)
    assert len(retained(client, "blemqtt/status")) == 2
    topic = discovery_topic("aabbcc001122", "radon_sta")
    assert len(retained(client, topic)) == 2


def test_connect_subscribes_to_discovery_filter_for_ghost_clearing(publisher, client):
    publisher.start()
    connect(client)
    assert client.subscribed == [DISCOVERY_FILTER]


def msg(topic, payload="{}"):
    return SimpleNamespace(topic=topic, payload=payload.encode())


def test_unconfigured_retained_discovery_is_cleared(publisher, client):
    publisher.start()
    connect(client)
    ghost = discovery_topic("deadbeef0000", "radon_sta")
    client.on_message(client, None, msg(ghost))
    assert (ghost, "", True) in client.published


def test_configured_and_foreign_discovery_topics_are_left_alone(publisher, client):
    publisher.start()
    connect(client)
    client.published.clear()
    client.on_message(client, None, msg(discovery_topic("aabbcc001122", "radon_sta")))
    client.on_message(client, None, msg("homeassistant/sensor/other_thing/x/config"))
    client.on_message(client, None, msg(discovery_topic("deadbeef0000", "radon_sta"), ""))
    assert client.published == []


def test_publish_readings_preserves_null(publisher, client):
    publisher.start()
    publisher.publish_readings(SENSOR, {"radon_sta": None, "temperature": 21.5})
    state = retained(client, "blemqtt/aabbcc001122/state")
    assert json.loads(state[0][1]) == {"radon_sta": None, "temperature": 21.5}
    assert '"radon_sta": null' in state[0][1]
    assert retained(client, "blemqtt/aabbcc001122/availability")[-1][1] == "online"


def test_mark_unavailable(publisher, client):
    publisher.start()
    publisher.mark_unavailable(SENSOR)
    assert retained(client, "blemqtt/aabbcc001122/availability")[-1][1] == "offline"


def test_stop_publishes_offline(client):
    p = Publisher(SETTINGS, [(SENSOR, AirthingsWave1())], client=client, clear_wait=3600)
    p.start()
    p.stop()
    assert retained(client, "blemqtt/status")[-1][1] == "offline"
    assert not client.loop_started


def test_password_never_logged_or_in_repr(publisher, client, caplog):
    with caplog.at_level(logging.DEBUG):
        publisher.start()
        connect(client)
        publisher.publish_readings(SENSOR, {"radon_sta": 1.0})
    assert "s3cret-pw" not in caplog.text
    assert "s3cret-pw" not in repr(publisher)
    assert "s3cret-pw" not in repr(SETTINGS)
