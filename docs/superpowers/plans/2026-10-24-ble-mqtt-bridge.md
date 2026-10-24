# BLE-to-MQTT Sensor Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python service and CLI that read an Airthings Wave Gen 1 over BLE and publish the readings, with Home Assistant discovery, to an MQTT broker.

**Architecture:** A `Driver` per sensor type turns a BLE device into named readings. A polling service loops over configured sensors, asks each driver to read, and hands the readings to a `Publisher` that owns all MQTT and discovery concerns. The CLI reuses drivers directly and never touches MQTT.

**Tech Stack:** Python 3.11+, `bleak`, `paho-mqtt` 2.x, `python-dotenv`, stdlib `tomllib`, `pytest`, `pytest-asyncio`. systemd user service.

**Spec:** `docs/superpowers/specs/2026-10-24-ble-mqtt-bridge-design.md`

## Global Constraints

- Language and libraries are fixed: Python, `bleak` (BLE), `paho-mqtt` (MQTT).
- Broker is plain port with username and password, no TLS. Credentials come from `.env` in the project root, using the existing names `MQTTUI_BROKER`, `MQTTUI_USERNAME`, `MQTTUI_PASSWORD`.
- The existing `.env` lines start with `export `. Load with `python-dotenv` (accepts it). systemd `EnvironmentFile=` must not be used.
- `MQTTUI_BROKER` has the form `scheme://host` with no port. Default port is 1883.
- `.env` is git-ignored. Credentials are never logged or printed.
- Default poll interval 300 seconds, configurable.
- Config file is `config.toml` in the project root, overridable with `--config`. Ship `config.example.toml`.
- Discovery topic prefix is `homeassistant`. Discovery messages are retained and republished on every broker connect.
- A sensor removed from config has its retained discovery topics cleared (empty payload) on the next start.
- Service availability uses an MQTT last-will. Home Assistant device identifier derives from the BLE address so restarts do not create new devices.
- Radon unit Bq/m³ with no assumed device class. Temperature °C with device class `temperature`. Humidity % with device class `humidity`.
- Null/invalid radon readings show as "unknown" in Home Assistant, never `0` or the string `None`.
- Service is a systemd user service. Only one BLE connection to the Wave at a time.
- Not a git repo yet: Task 1 runs `git init`.

## Review Focus

1. A sensor is out of range or times out mid-cycle: the other sensors are still read and published, the service keeps running.
2. Broker is unreachable at start or drops mid-run: the service reconnects and republishes discovery and availability.
3. Radon is invalid or not yet available (`None`): Home Assistant sees "unknown", not `0` or `"None"`.
4. `.env` has the `export ` prefix, quotes, and a broker URL with no port: it still loads, port defaults to 1883.
5. The password never appears in logs, exceptions, or `repr()` of the settings object.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | package metadata, deps, `blemqtt` console script, pytest config |
| `.gitignore` | `.env`, `config.toml`, venv, caches |
| `config.example.toml` | documented sample config |
| `src/blemqtt/models.py` | `ReadingSpec`, `Readings` type |
| `src/blemqtt/drivers/base.py` | `Driver` ABC, `ParseError` |
| `src/blemqtt/drivers/__init__.py` | `DRIVERS` registry, `get_driver(name)` |
| `src/blemqtt/drivers/airthings_wave1.py` | Wave Gen 1 parse + BLE read |
| `src/blemqtt/config.py` | `.env` + TOML loading |
| `src/blemqtt/discovery.py` | topic names, discovery and clearing messages |
| `src/blemqtt/publisher.py` | paho wrapper: connect, LWT, publish, ghost clearing |
| `src/blemqtt/ble_lock.py` | cross-process lock so CLI and service do not collide |
| `src/blemqtt/service.py` | poll loop, failure tracking |
| `src/blemqtt/cli.py` | `scan` and `read` commands |
| `systemd/blemqtt.service` | user unit |
| `README.md` | install and run |
| `tests/` | one test file per module |

---

### Task 1: Project scaffold, models, driver interface

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/blemqtt/__init__.py`, `src/blemqtt/models.py`, `src/blemqtt/drivers/__init__.py`, `src/blemqtt/drivers/base.py`, `tests/test_drivers_registry.py`

**Interfaces:**
- Produces:
  - `models.ReadingSpec(key: str, name: str, unit: str | None, device_class: str | None, icon: str | None = None)` frozen dataclass
  - `models.Readings = dict[str, float | None]`
  - `drivers.base.ParseError(Exception)`
  - `drivers.base.Driver` ABC with class attributes `type_name: str`, `manufacturer: str`, `model: str`, `readings: tuple[ReadingSpec, ...]`; `parse(self, payload: bytes) -> Readings`; `async read(self, address: str, timeout: float) -> Readings`
  - `drivers.get_driver(type_name: str) -> Driver`, raises `KeyError` with a message listing known types

- [ ] **Step 1: `git init`, write `.gitignore` and `pyproject.toml`** (package `blemqtt` under `src/`, console script `blemqtt = blemqtt.cli:main`, pytest `asyncio_mode = "auto"`). Create a venv and `pip install -e '.[dev]'` with `pytest` and `pytest-asyncio` as dev extras.
- [ ] **Step 2: Write failing test** in `tests/test_drivers_registry.py`:

```python
def test_unknown_driver_lists_known_types():
    with pytest.raises(KeyError, match="airthings_wave1"):
        get_driver("nope")
```

- [ ] **Step 3: Run** `pytest tests/test_drivers_registry.py -v`. Expected: FAIL (import error).
- [ ] **Step 4: Implement** `models.py`, `drivers/base.py`, and `drivers/__init__.py` with an initially empty-ish registry that the Wave driver registers into in Task 2 (the test's `match` makes Task 2 necessary; for this task, register a stub-free empty dict and let the test assert on the message format with `match="Known"`; update the match to `airthings_wave1` in Task 2).
- [ ] **Step 5: Run test, expect PASS. Commit** `chore: scaffold project and driver interface`.

---

### Task 2: Airthings Wave Gen 1 driver

**Files:**
- Create: `src/blemqtt/drivers/airthings_wave1.py`
- Modify: `src/blemqtt/drivers/__init__.py` (register `"airthings_wave1"`)
- Test: `tests/test_airthings_wave1.py`

**Interfaces:**
- Consumes: `Driver`, `ReadingSpec`, `ParseError`
- Produces: `AirthingsWave1(Driver)` with `type_name = "airthings_wave1"`, `manufacturer = "Airthings"`, `model = "Wave (Gen 1)"`, `readings` with keys `radon_sta`, `radon_lta`, `temperature`, `humidity`; module constant `CHAR_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"`

Layout and scaling are a **starting point from memory of open-source readers, to be confirmed on hardware in Task 8**: payload `struct "<4B8H"` = version, humidity raw, light, unused, radon short-term, radon long-term, temperature raw, then pressure/CO2/VOC fields (ignored). Humidity = raw/2, temperature = raw/100, radon in Bq/m³. Treat `0xFFFF` radon as invalid (`None`); confirm in Task 8.

- [ ] **Step 1: Write failing tests**:

```python
PAYLOAD = struct.pack("<4B8H", 1, 90, 0, 0, 45, 50, 2150, 0, 0, 0, 0, 0)

def test_parse_valid_payload():
    assert AirthingsWave1().parse(PAYLOAD) == {
        "radon_sta": 45.0, "radon_lta": 50.0, "temperature": 21.5, "humidity": 45.0}

def test_invalid_radon_becomes_none():
    p = struct.pack("<4B8H", 1, 90, 0, 0, 0xFFFF, 0xFFFF, 2150, 0, 0, 0, 0, 0)
    r = AirthingsWave1().parse(p)
    assert r["radon_sta"] is None and r["radon_lta"] is None
    assert r["temperature"] == 21.5

@pytest.mark.parametrize("bad", [b"", b"\x01\x02", PAYLOAD[:-1]])
def test_wrong_length_raises(bad):
    with pytest.raises(ParseError):
        AirthingsWave1().parse(bad)

def test_unknown_version_raises():
    with pytest.raises(ParseError):
        AirthingsWave1().parse(struct.pack("<4B8H", 9, *([0] * 11)))
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `parse`** as above. **Implement `async read(address, timeout)`** using `bleak.BleakClient(address, timeout=timeout)` to read `CHAR_UUID` and call `parse`; wrap `bleak` errors and `asyncio.TimeoutError` into one `ReadError(Exception)` defined in `drivers/base.py` (add it).
- [ ] **Step 4: Register** in `drivers/__init__.py`; update Task 1's test `match` to `airthings_wave1`. Run all tests, expect PASS.
- [ ] **Step 5: Commit** `feat: add Airthings Wave Gen 1 driver`.

---

### Task 3: Config loading

**Files:**
- Create: `src/blemqtt/config.py`, `config.example.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `get_driver` (to validate driver names)
- Produces:
  - `MqttSettings(host: str, port: int, username: str, password: str)` dataclass; `password` field uses `field(repr=False)`
  - `load_mqtt_settings(env_path: Path) -> MqttSettings`
  - `SensorConfig(name: str, address: str, driver: str)` with property `node_id -> str` (address lowercased, `:` and `-` removed)
  - `AppConfig(interval_seconds: int, failure_threshold: int, sensors: list[SensorConfig])`
  - `load_app_config(path: Path) -> AppConfig`; `ConfigError(Exception)` for any invalid input

- [ ] **Step 1: Write failing tests**, using `tmp_path` files:

```python
def test_env_with_export_prefix_and_no_port(tmp_path):
    (tmp_path / ".env").write_text(
        'export MQTTUI_BROKER=mqtt://lab.example.com\n'
        'export MQTTUI_USERNAME="u"\nexport MQTTUI_PASSWORD="p w"\n')
    s = load_mqtt_settings(tmp_path / ".env")
    assert (s.host, s.port, s.username, s.password) == ("lab.example.com", 1883, "u", "p w")

def test_password_not_in_repr(tmp_path): ...  # "p w" not in repr(s)
def test_broker_with_explicit_port(tmp_path): ...  # mqtt://h:1884 -> 1884
def test_tls_scheme_rejected(tmp_path): ...  # mqtts:// raises ConfigError
def test_missing_variable_names_it(tmp_path): ...  # error message names MQTTUI_PASSWORD, not its value
def test_app_config_defaults(tmp_path): ...  # interval 300, failure_threshold 3
def test_unknown_driver_rejected(tmp_path): ...
def test_node_id_strips_separators(): assert SensorConfig("w","AA:BB:CC:00:11:22","airthings_wave1").node_id == "aabbcc001122"
```

Write each elided test body in full.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `dotenv.dotenv_values` and `urllib.parse.urlsplit`; `tomllib` for TOML. Write `config.example.toml` with `interval_seconds = 300`, `failure_threshold = 3`, and one commented `[[sensors]]` entry.
- [ ] **Step 4: Run, expect PASS. Commit** `feat: load MQTT settings from .env and sensors from TOML`.

---

### Task 4: Discovery messages

**Files:**
- Create: `src/blemqtt/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `SensorConfig`, `Driver`, `ReadingSpec`
- Produces (all pure functions, no I/O):
  - `state_topic(node_id) -> str` = `blemqtt/{node_id}/state`
  - `availability_topic(node_id) -> str` = `blemqtt/{node_id}/availability`
  - `SERVICE_STATUS_TOPIC = "blemqtt/status"`
  - `discovery_topic(node_id, key) -> str` = `homeassistant/sensor/blemqtt_{node_id}/{key}/config`
  - `DISCOVERY_FILTER = "homeassistant/sensor/blemqtt_+/+/config"`
  - `node_id_from_discovery_topic(topic: str) -> str | None`
  - `discovery_messages(sensor: SensorConfig, driver: Driver) -> list[tuple[str, str]]` (topic, JSON payload), one per reading
  - `clear_messages(node_id: str, keys: Iterable[str]) -> list[tuple[str, str]]` with payload `""`

Each config payload sets: `name`, `unique_id = blemqtt_{node_id}_{key}`, `state_topic`, `value_template` that renders `unknown` when the JSON value is null, `unit_of_measurement`, `device_class` and `icon` only when set, `state_class = "measurement"`, `availability` list of the service-status and sensor-availability topics with `availability_mode = "all"`, and `device` with `identifiers = [f"blemqtt_{node_id}"]`, `name`, `manufacturer`, `model`.

- [ ] **Step 1: Write failing tests** asserting on the parsed JSON: unique_id and topic for the Wave's `radon_sta`; `device_class` absent for radon and `"temperature"` for temperature; both availability topics present with mode `all`; `identifiers` identical across all four messages of one sensor; `clear_messages` yields empty payloads on the same topics; `node_id_from_discovery_topic` round-trips and returns `None` for foreign topics; a test that renders the `value_template` with `jinja2` against `{"radon_sta": None}` and `{"radon_sta": 45.0}` and asserts `unknown` / `45.0` (add `jinja2` as a dev dependency).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Template shape: `{{ value_json.KEY if value_json.KEY is not none else 'unknown' }}`. Verify against current Home Assistant MQTT sensor docs that an `unknown` string is accepted for numeric sensors; if not, switch to the documented way to produce an unknown state and adjust the test.
- [ ] **Step 4: Run, expect PASS. Commit** `feat: build Home Assistant discovery messages`.

---

### Task 5: Publisher

**Files:**
- Create: `src/blemqtt/publisher.py`
- Test: `tests/test_publisher.py`

**Interfaces:**
- Consumes: `MqttSettings`, discovery functions, `SensorConfig`, `Driver`
- Produces `Publisher(settings: MqttSettings, sensors: list[tuple[SensorConfig, Driver]], client: mqtt.Client | None = None)` with:
  - `start() -> None`: connect, `loop_start()`; sets last-will on `SERVICE_STATUS_TOPIC` payload `offline` retained; on every (re)connect publish `online` retained to `SERVICE_STATUS_TOPIC`, republish all discovery messages retained, and run ghost clearing
  - `publish_readings(sensor: SensorConfig, readings: Readings) -> None`: JSON to `state_topic`, nulls preserved as `null`, and `online` to the sensor's availability topic
  - `mark_unavailable(sensor: SensorConfig) -> None`
  - `stop() -> None`: publish `offline`, disconnect
- Ghost clearing: on connect, subscribe to `DISCOVERY_FILTER`, wait up to 2 s for retained messages, publish `clear_messages` for any `node_id` not in the configured sensors, then unsubscribe.

Tests inject a fake client object recording `publish`, `will_set`, `subscribe` calls and let the test fire `on_connect` and `on_message` callbacks directly.

- [ ] **Step 1: Write failing tests** for: last-will configured to `blemqtt/status`/`offline`/retained; `on_connect` publishes retained discovery for every reading of every sensor and `online`; calling `on_connect` a second time republishes (reconnect, Review Focus 2); an unknown retained discovery topic for node `deadbeef0000` results in clear messages, while a configured node's topics are untouched; `publish_readings` with `radon_sta=None` produces JSON containing `"radon_sta": null`; password absent from every logged record (use `caplog`) and from `repr(publisher)`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `paho.mqtt.client.Client(CallbackAPIVersion.VERSION2)`, `username_pw_set`, `reconnect_delay_set(1, 60)`, `connect_async` so a down broker at start does not crash the process.
- [ ] **Step 4: Run, expect PASS. Commit** `feat: add MQTT publisher with discovery and ghost clearing`.

---

### Task 6: BLE lock and polling service

**Files:**
- Create: `src/blemqtt/ble_lock.py`, `src/blemqtt/service.py`
- Test: `tests/test_ble_lock.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `AppConfig`, `Driver`, `Publisher`, `ReadError`, `ParseError`
- Produces:
  - `ble_lock.ble_lock(timeout: float = 60.0)`: async context manager holding an exclusive `fcntl.flock` on `$XDG_RUNTIME_DIR/blemqtt-ble.lock` (fallback `/tmp`); raises `LockTimeout(Exception)` after `timeout`
  - `service.poll_once(sensors, publisher, failures: dict[str, int], threshold: int, read_timeout: float = 30.0) -> None`: reads each sensor under `ble_lock`; on success publishes and resets its failure count; on `ReadError`/`ParseError`/`LockTimeout` logs a warning (sensor name only, no secrets), increments count, and calls `mark_unavailable` once the count reaches `threshold`; never raises for one sensor's failure
  - `async service.run(config, settings) -> None`: builds drivers, starts the `Publisher`, loops `poll_once` every `interval_seconds`, stops cleanly on SIGTERM/SIGINT
  - `main()` entry reachable via `blemqtt run`

- [ ] **Step 1: Write failing tests** with fake drivers and a fake publisher (recording calls): two sensors where the first raises `ReadError` and the second succeeds, so the second is still published (Review Focus 1); failure count reaching 3 calls `mark_unavailable` exactly once, and a later success resets it and republishes `online`; `ParseError` counts as a failure; lock: a second concurrent acquire times out with `LockTimeout` when `timeout=0.1`, and succeeds after release.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Run the blocking `flock` in `asyncio.to_thread` with polling retry so it respects `timeout`.
- [ ] **Step 4: Run, expect PASS. Commit** `feat: add polling service with failure tracking and BLE lock`.

---

### Task 7: CLI

**Files:**
- Create: `src/blemqtt/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `get_driver`, `load_app_config`, `ble_lock`, `service.run`
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands:
  - `blemqtt scan [--timeout 10]`: lists nearby BLE devices (address, name, RSSI) using `bleak.BleakScanner`
  - `blemqtt read (--sensor NAME | --address MAC --driver TYPE) [--config PATH] [--json]`: reads once under `ble_lock`, prints `name: value unit` lines or a JSON object; exit 0 on success, non-zero with one-line message to stderr on `ReadError`, `ParseError`, `LockTimeout`, `ConfigError`
  - `blemqtt run [--config PATH] [--env PATH]`: starts the service
  - `read` with `--address` needs no config file and no MQTT settings

- [ ] **Step 1: Write failing tests** by monkeypatching the driver registry with a fake driver: `read --address X --driver fake --json` prints a JSON object with `null` for a `None` reading and returns 0; text output includes units; a driver raising `ReadError` returns non-zero and writes a one-line message to stderr; `read --sensor missing` returns non-zero naming the sensor; `read` never imports or constructs `Publisher`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** with `argparse` and `asyncio.run`.
- [ ] **Step 4: Run, expect PASS. Commit** `feat: add scan, read and run CLI`.

---

### Task 8: Real-hardware verification, systemd unit, README

**Files:**
- Create: `systemd/blemqtt.service`, `README.md`
- Modify: `src/blemqtt/drivers/airthings_wave1.py` and `tests/test_airthings_wave1.py` if the real payload differs

This task needs the physical Wave and Patrick's broker. Do it with Patrick.

- [ ] **Step 1: Find the Wave.** Run `blemqtt scan`; Patrick identifies the address (Airthings Wave devices advertise a name starting with `Airthings` or a manufacturer id; confirm with Patrick).
- [ ] **Step 2: Dump raw bytes.** Read `CHAR_UUID` once with a throwaway script in the scratchpad and save the hex.
- [ ] **Step 3: Compare to the Airthings phone app** values and fix `parse` layout, scaling, version byte and the invalid-radon sentinel to match. Add the real payload as a new test case in `tests/test_airthings_wave1.py` (this becomes the recorded-payload regression test). Confirm radon and temperature units are Bq/m³ and °C.
- [ ] **Step 4: Check Home Assistant radon support.** Look up whether current Home Assistant has a radon device class and which units it accepts for it. Patrick's dashboard uses pCi/L (the Airthings cloud integration lets him pick the unit). If Home Assistant has a radon device class that converts units, publish Bq/m³ with that class and let Home Assistant convert. If it does not, publish the radon entities in pCi/L (1 Bq/m³ = 0.027 pCi/L), converting in the Wave driver's `readings` metadata and `parse`, and keep the raw Bq/m³ only in the CLI output. Update `ReadingSpec`, the driver tests and the discovery tests to match.
- [ ] **Step 5: Create `config.toml`** with the Wave, run `blemqtt read --sensor <name>`, then `blemqtt run` in a terminal. In Home Assistant confirm one device, four entities, and "unknown" (not `0`) if radon has no data yet. Restart the service and confirm no duplicate device appears. Remove the sensor from config, restart, and confirm the device disappears.
- [ ] **Step 6: Contention check.** While `blemqtt run` is polling, run `blemqtt read`; confirm it waits and succeeds rather than erroring.
- [ ] **Step 7: Write `systemd/blemqtt.service`** (user unit, `ExecStart` pointing at the venv's `blemqtt run`, `WorkingDirectory` the project root, `Restart=on-failure`, `After=bluetooth.target network-online.target`) and `README.md` covering venv install, `.env` and `config.toml` setup, `systemctl --user enable --now blemqtt`, `loginctl enable-linger`, and the CLI. If BlueZ permissions block the user service, note it and fall back to a system unit.
- [ ] **Step 8: Run the full test suite and commit** `docs: add systemd unit and README; verify against real hardware`.
