import pytest

from blemqtt.ble_lock import LockTimeout, ble_lock


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


async def test_second_acquire_times_out_while_held():
    async with ble_lock(timeout=1):
        with pytest.raises(LockTimeout):
            async with ble_lock(timeout=0.1):
                pass


async def test_acquire_succeeds_after_release():
    async with ble_lock(timeout=1):
        pass
    async with ble_lock(timeout=0.1):
        pass
