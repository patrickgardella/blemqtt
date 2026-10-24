# blemqtt

Reads BLE environmental sensors (first: Airthings Wave Gen 1) and publishes the readings
to an MQTT broker, with Home Assistant MQTT discovery. A CLI reads a sensor once by hand.

## Install

    python -m venv .venv
    .venv/bin/pip install -e '.[dev]'

## Configure

- `.env` holds the broker login (not committed):

      MQTTUI_BROKER=mqtt://your-broker-host[:port]   # port defaults to 1883
      MQTTUI_USERNAME=...
      MQTTUI_PASSWORD=...

- `config.toml` lists the sensors (copy `config.example.toml`).

## CLI

    blemqtt scan                          # find nearby BLE devices and addresses
    blemqtt read --sensor "Basement Radon"
    blemqtt read --address AA:BB:CC:00:11:22 --driver airthings_wave1 --json
    blemqtt run                           # run the service in the foreground

`read` waits for the service if it is mid-read (only one Bluetooth connection at a time).

## Run as a service (systemd user unit)

    mkdir -p ~/.config/systemd/user
    cp systemd/blemqtt.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now blemqtt
    loginctl enable-linger "$USER"        # keep running when logged out
    journalctl --user -u blemqtt -f

Edit `WorkingDirectory` and `ExecStart` in the unit if the project lives elsewhere.

## Units

Radon is published in pCi/L (the Wave reports Bq/m³; converted by dividing by 37) because Home Assistant
cannot change the display unit of MQTT radon sensors. Temperature is °C (Home Assistant converts), humidity %.

## Adding a sensor type

Add a `Driver` subclass in `src/blemqtt/drivers/` (`parse` raw bytes into named readings, `read`
over BLE) and register it in `drivers/__init__.py`. MQTT and discovery code need no changes.
