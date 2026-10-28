"""Make protocol.py importable without Home Assistant installed."""

import importlib.util
import pathlib
import sys

_root = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(_root))
_spec = importlib.util.spec_from_file_location(
    "ts_protocol", _root / "custom_components/technisat_receiver_ha/protocol.py"
)
protocol = importlib.util.module_from_spec(_spec)
sys.modules["ts_protocol"] = protocol
_spec.loader.exec_module(protocol)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _allow_sockets(request):
    """pytest-homeassistant-custom-component blocks sockets; we need localhost UDP."""
    try:
        request.getfixturevalue("socket_enabled")
    except pytest.FixtureLookupError:
        pass
    yield
