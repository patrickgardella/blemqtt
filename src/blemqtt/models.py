from dataclasses import dataclass

Readings = dict[str, float | None]


@dataclass(frozen=True)
class ReadingSpec:
    key: str
    name: str
    unit: str | None
    device_class: str | None
    icon: str | None = None
