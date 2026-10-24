import pytest

from blemqtt.drivers import get_driver


def test_unknown_driver_lists_known_types():
    with pytest.raises(KeyError, match="Known"):
        get_driver("nope")
