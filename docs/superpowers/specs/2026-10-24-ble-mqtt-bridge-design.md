# BLE-to-MQTT Sensor Bridge: Design

Date: 2026-10-24
Status: draft, awaiting approval

## Intent

Patrick has an Airthings Wave (Gen 1) radon detector, a battery-powered BLE
radon, temperature and humidity sensor (model confirmed by Patrick). He wants its readings in Home Assistant
without the phone app. Home Assistant (on lab.thetelos.com) will pull the data
from an MQTT broker (also on lab.thetelos.com), so this project's job ends at
publishing to MQTT.

The Wave is the first of several Bluetooth sensors. Later ones are expected to
be weather or environmental sensors producing similar kinds of numeric readings.

## Goals

- A long-running service on Patrick's always-on Linux machine (Arch, BlueZ)
  that polls each configured BLE sensor every 5 minutes and publishes readings
  to MQTT.
- Home Assistant MQTT discovery messages, so each sensor appears in Home
  Assistant as one device with one entity per reading (for the Wave: radon
  short-term average, radon long-term average, temperature, humidity) with no
  manual Home Assistant configuration.
- A CLI that reads a sensor once and prints the values to the terminal. It does
  not touch MQTT.
- A sensor "driver" boundary: each sensor type is a small module that connects
  to or listens to a device and returns named readings with units and a Home
  Assistant device class. Adding a sensor means adding a driver and a config
  entry. MQTT, discovery, scheduling and config code do not change.

## Non-goals

- No web UI, no database or history (Home Assistant stores history).
- No direct Home Assistant API use; MQTT is the only output.
- No Bluetooth gateway/relay for other machines.
- No support for Airthings devices other than Wave Gen 1 in v1 (Wave Plus,
  Wave Mini etc. are drivers to add later, if wanted).
- No TLS or other broker auth modes in v1 (see Constraints).

## Anti-goals (failure even if it technically works)

- Sensors appearing in Home Assistant as duplicates or "unavailable" after a
  service restart, because discovery or availability handling is wrong.
- Service dying silently on a Bluetooth hiccup instead of logging and retrying
  on the next cycle.
- Credentials committed to the repo or printed in logs.
- Adding the second sensor type requires editing MQTT or discovery code.

## Constraints

- Runs on this machine only (Linux, BlueZ, Python). Bluetooth adapter is local.
- Language and libraries are decided: Python, `bleak` for BLE, `paho-mqtt` for
  MQTT. (Patrick chose Python after considering Go/Rust/Node.)
- Broker: plain port, username and password, no TLS. Credentials come from a
  `.env` file in the project root.
  - The existing `.env` already defines `MQTTUI_BROKER`, `MQTTUI_USERNAME` and
    `MQTTUI_PASSWORD`, each written with a leading `export ` (shell style).
    `MQTTUI_BROKER` is a URL of the form `scheme://host` with no port. Reuse
    these names rather than inventing new ones.
  - systemd's `EnvironmentFile=` does not accept the `export ` prefix, so the
    service must load the file itself (for example python-dotenv, which accepts
    `export`) rather than relying on systemd to parse it.
  - If no port is given, default to the standard MQTT port 1883.
  - `.env` must be git-ignored and never logged.
- Poll interval: 5 minutes by default, configurable. The Wave's short-term
  radon value only changes roughly hourly, so faster polling gains little.
- The Wave Gen 1 does not push data. It must be connected to over GATT and its
  measurement characteristic read. Only one connection at a time is possible, so
  the CLI and the service must not collide (see Left to the builder).

## Behavior

### Service
- Reads config (sensor list, interval, MQTT settings) at start.
- On connecting to the broker, publishes retained discovery config for every
  entity of every configured sensor, and an availability topic using an MQTT
  last-will so Home Assistant shows sensors unavailable if the service dies.
- Each cycle, for each sensor: read, publish values (state topics), mark
  available. If a read fails, log it, leave the previous state, and try again
  next cycle. Repeated failure for a sensor should mark that sensor unavailable
  rather than keep showing stale data indefinitely (threshold is the builder's
  call).
- Runs as a systemd service, restarts on failure, logs to the journal.

### CLI
- Reads one named or addressed sensor once and prints readings with units. A
  `--json` option is welcome. Also useful: a way to scan for nearby BLE devices
  so Patrick can find the Wave's address.
- Exits non-zero with a clear message on failure.

### Sensor identification
- Sensors are identified in config by BLE address (MAC) plus a friendly name
  and driver type. The Home Assistant device identifier derives from something
  stable (the address, or the Wave's serial number) so restarts don't create new
  devices.

### Wave Gen 1 driver (to verify against real hardware)
- Reads the Wave's measurement characteristic, which is believed to be UUID
  `b42e2a68-ade7-11e4-89d3-123b93f75cba`, returning a small fixed-size packed
  structure. Believed contents: humidity (raw / 2, in %RH), radon short-term
  average and long-term average (Bq/m³), temperature (raw / 100, in °C).
  Treat these offsets, scaling and UUID as a starting point to confirm against
  the actual device and existing open-source Wave readers, not as fact.
- Radon values are not meaningful immediately after the Wave is set up
  (short-term needs about an hour of data, long-term about a week); the driver
  should not publish obviously invalid sentinel values as real readings.
- Units: radon in Bq/m³ (Home Assistant has no radon device class, so publish as
  a plain measurement sensor with an appropriate icon); temperature °C;
  humidity %.

## Decisions made by Claude (not Patrick) — please check

- Python project layout, packaging and CLI framework.
- Config file format and location for the sensor list (suggest TOML or YAML);
  the broker credentials stay in `.env`.
- Home Assistant discovery topic prefix `homeassistant`, retained discovery
  messages, and state topic naming.
- 5-minute default interval (Patrick agreed).
- Reusing the existing `MQTTUI_*` variable names from `.env`.
- Sensor "driver" interface shape.

## More calls made after the builder check (Claude's, not Patrick's)

- Sentinel/invalid radon values (for example the Wave's "not yet available"
  marker): the driver returns `None` for that reading, and the service publishes
  an empty/unknown state for that entity rather than skipping, so Home Assistant
  shows "unknown" until real data exists. Confirm the actual sentinel value
  against the device.
- Config file: TOML, `config.toml` in the project root, with a `--config` flag
  to override. Git-ignored if it holds anything personal; ship a
  `config.example.toml`.
- Discovery is republished (retained) on every broker connect. A sensor removed
  from config has its retained discovery topics cleared (empty payload) on the
  next start, so no ghost devices remain. Sensors seen only in retained
  discovery topics this service published are the ones cleared.
- Service runs as a systemd user service by default, for simpler access to
  `.env` and the user's Bluetooth permissions; a system unit is acceptable if
  BlueZ permissions make that necessary.

## Left to the builder

- Module structure, test strategy (BLE and MQTT should be mockable so drivers
  can be tested from recorded byte payloads), logging format.
- How the CLI and the service avoid fighting over the single BLE connection
  (for example the CLI stops or defers to a running service, or retries).
- Failure thresholds, backoff, and timeouts.
- systemd unit details (user vs system service, Bluetooth group/permissions).
- Installation instructions (venv, enabling the unit).

## Success

Patrick can start the service, see an "Airthings Wave" device in Home Assistant
with four entities that update about every five minutes, and run the CLI by hand
to see the same numbers. Adding a different BLE sensor later is a new driver
file and a config entry.
