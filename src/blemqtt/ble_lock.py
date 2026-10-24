import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path


class LockTimeout(Exception):
    """Another process held the Bluetooth lock for the whole timeout."""


def _lock_path() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "blemqtt-ble.lock"


@asynccontextmanager
async def ble_lock(timeout: float = 60.0):
    fd = os.open(_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout("another blemqtt process is using Bluetooth") from None
                await asyncio.sleep(0.05)
        yield
    finally:
        os.close(fd)
