"""Share one UDP endpoint between all config entries."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .protocol import TechniSatClient

_CLIENT = "client"
_REFS = "refs"


async def async_acquire_client(hass: HomeAssistant) -> TechniSatClient:
    """Return the shared client, opening the UDP socket on first use."""
    data = hass.data.setdefault(DOMAIN, {})
    client: TechniSatClient | None = data.get(_CLIENT)
    if client is None:
        client = TechniSatClient()
        await client.async_start()
        data[_CLIENT] = client
        data[_REFS] = 0
    data[_REFS] += 1
    return client


async def async_release_client(hass: HomeAssistant) -> None:
    """Drop one reference; the socket closes with the last one."""
    data = hass.data.get(DOMAIN)
    if not data or _CLIENT not in data:
        return
    data[_REFS] -= 1
    if data[_REFS] <= 0:
        data.pop(_CLIENT).close()
        data.pop(_REFS, None)
        if not data:
            hass.data.pop(DOMAIN, None)
