import pytest

from blemqtt.config import (
    ConfigError,
    SensorConfig,
    load_app_config,
    load_mqtt_settings,
)


def write_env(tmp_path, broker="mqtt://lab.example.com", user='"u"', password='"p w"'):
    lines = []
    if broker is not None:
        lines.append(f"export MQTTUI_BROKER={broker}")
    if user is not None:
        lines.append(f"export MQTTUI_USERNAME={user}")
    if password is not None:
        lines.append(f"export MQTTUI_PASSWORD={password}")
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_env_with_export_prefix_and_no_port(tmp_path):
    s = load_mqtt_settings(write_env(tmp_path))
    assert (s.host, s.port, s.username, s.password) == ("lab.example.com", 1883, "u", "p w")


def test_password_not_in_repr(tmp_path):
    s = load_mqtt_settings(write_env(tmp_path))
    assert "p w" not in repr(s)


def test_broker_with_explicit_port(tmp_path):
    s = load_mqtt_settings(write_env(tmp_path, broker="mqtt://h:1884"))
    assert (s.host, s.port) == ("h", 1884)


def test_tls_scheme_rejected(tmp_path):
    with pytest.raises(ConfigError, match="TLS"):
        load_mqtt_settings(write_env(tmp_path, broker="mqtts://h"))


def test_missing_variable_names_it_but_not_other_values(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_mqtt_settings(write_env(tmp_path, password=None))
    assert "MQTTUI_PASSWORD" in str(e.value)
    assert "lab.example.com" not in str(e.value)


def test_missing_env_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match=".env"):
        load_mqtt_settings(tmp_path / "nope.env")


def write_toml(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_app_config_defaults(tmp_path):
    cfg = load_app_config(write_toml(tmp_path, """
[[sensors]]
name = "Basement Radon"
address = "AA:BB:CC:00:11:22"
driver = "airthings_wave1"
"""))
    assert cfg.interval_seconds == 300
    assert cfg.failure_threshold == 3
    assert cfg.sensors == [SensorConfig("Basement Radon", "AA:BB:CC:00:11:22", "airthings_wave1")]


def test_app_config_overrides(tmp_path):
    cfg = load_app_config(write_toml(tmp_path, """
interval_seconds = 60
failure_threshold = 5
"""))
    assert (cfg.interval_seconds, cfg.failure_threshold, cfg.sensors) == (60, 5, [])


def test_unknown_driver_rejected(tmp_path):
    with pytest.raises(ConfigError, match="nope"):
        load_app_config(write_toml(tmp_path, """
[[sensors]]
name = "x"
address = "AA:BB:CC:00:11:22"
driver = "nope"
"""))


def test_sensor_missing_field_rejected(tmp_path):
    with pytest.raises(ConfigError, match="address"):
        load_app_config(write_toml(tmp_path, """
[[sensors]]
name = "x"
driver = "airthings_wave1"
"""))


def test_duplicate_sensor_addresses_rejected(tmp_path):
    with pytest.raises(ConfigError, match="duplicate"):
        load_app_config(write_toml(tmp_path, """
[[sensors]]
name = "a"
address = "AA:BB:CC:00:11:22"
driver = "airthings_wave1"
[[sensors]]
name = "b"
address = "aa-bb-cc-00-11-22"
driver = "airthings_wave1"
"""))


def test_invalid_interval_rejected(tmp_path):
    with pytest.raises(ConfigError, match="interval_seconds"):
        load_app_config(write_toml(tmp_path, "interval_seconds = 0\n"))


def test_node_id_strips_separators():
    assert SensorConfig("w", "AA:BB:CC:00:11:22", "airthings_wave1").node_id == "aabbcc001122"
