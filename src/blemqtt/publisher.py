import json
import logging
import threading

import paho.mqtt.client as mqtt

from blemqtt.config import MqttSettings, SensorConfig
from blemqtt.discovery import (
    DISCOVERY_FILTER,
    SERVICE_STATUS_TOPIC,
    availability_topic,
    discovery_messages,
    node_id_from_discovery_topic,
    state_topic,
)
from blemqtt.drivers.base import Driver
from blemqtt.models import Readings

log = logging.getLogger(__name__)


class Publisher:
    def __init__(
        self,
        settings: MqttSettings,
        sensors: list[tuple[SensorConfig, Driver]],
        client: mqtt.Client | None = None,
        clear_wait: float = 2.0,
    ):
        self._settings = settings
        self._sensors = sensors
        self._known_nodes = {sensor.node_id for sensor, _ in sensors}
        self._clear_wait = clear_wait
        self._timer: threading.Timer | None = None
        self._client = client or mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def start(self) -> None:
        c = self._client
        c.username_pw_set(self._settings.username, self._settings.password)
        c.will_set(SERVICE_STATUS_TOPIC, "offline", qos=1, retain=True)
        c.reconnect_delay_set(1, 60)
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        c.connect_async(self._settings.host, self._settings.port)
        c.loop_start()

    def publish_readings(self, sensor: SensorConfig, readings: Readings) -> None:
        self._publish(state_topic(sensor.node_id), json.dumps(readings))
        self._publish(availability_topic(sensor.node_id), "online")

    def mark_unavailable(self, sensor: SensorConfig) -> None:
        self._publish(availability_topic(sensor.node_id), "offline")

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._publish(SERVICE_STATUS_TOPIC, "offline").wait_for_publish(timeout=5)
        self._client.disconnect()
        self._client.loop_stop()

    def _publish(self, topic: str, payload: str):
        return self._client.publish(topic, payload, qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if getattr(reason_code, "is_failure", reason_code != 0):
            log.warning("MQTT connect refused: %s", reason_code)
            return
        log.info("connected to MQTT broker %s:%s", self._settings.host, self._settings.port)
        self._publish(SERVICE_STATUS_TOPIC, "online")
        for sensor, driver in self._sensors:
            for topic, payload in discovery_messages(sensor, driver):
                self._publish(topic, payload)
        client.subscribe(DISCOVERY_FILTER)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self._clear_wait, self._finish_clearing)
        self._timer.daemon = True
        self._timer.start()

    def _on_message(self, client, userdata, message) -> None:
        node_id = node_id_from_discovery_topic(message.topic)
        if node_id is None or node_id in self._known_nodes or not message.payload:
            return
        log.info("clearing discovery for removed sensor %s", node_id)
        self._publish(message.topic, "")

    def _finish_clearing(self) -> None:
        self._client.unsubscribe(DISCOVERY_FILTER)
