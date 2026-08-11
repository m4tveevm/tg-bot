import sys
from importlib.util import find_spec


def test_supported_python_runtime() -> None:
    assert sys.version_info >= (3, 11)


def test_source_package_is_discoverable() -> None:
    assert find_spec("source") is not None
