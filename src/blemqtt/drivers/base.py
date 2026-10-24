from abc import ABC, abstractmethod

from blemqtt.models import ReadingSpec, Readings


class ParseError(Exception):
    """The payload from a device could not be understood."""


class Driver(ABC):
    type_name: str
    manufacturer: str
    model: str
    readings: tuple[ReadingSpec, ...]

    @abstractmethod
    def parse(self, payload: bytes) -> Readings: ...

    @abstractmethod
    async def read(self, address: str, timeout: float) -> Readings: ...
