from blemqtt.drivers.base import Driver

DRIVERS: dict[str, type[Driver]] = {}


def get_driver(type_name: str) -> Driver:
    try:
        return DRIVERS[type_name]()
    except KeyError:
        known = ", ".join(sorted(DRIVERS)) or "none"
        raise KeyError(f"Unknown driver {type_name!r}. Known drivers: {known}") from None


def _register() -> None:
    from blemqtt.drivers.airthings_wave1 import AirthingsWave1

    DRIVERS[AirthingsWave1.type_name] = AirthingsWave1


_register()
