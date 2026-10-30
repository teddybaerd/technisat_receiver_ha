"""Reachability polling."""

from __future__ import annotations

from datetime import timedelta
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .protocol import TechniSatClient
from .ssdp import RendererPower, async_search

_LOGGER = logging.getLogger(__name__)


class TechniSatCoordinator(DataUpdateCoordinator[bool]):
    """Poll a keep-alive; the data is simply "does the receiver answer"."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TechniSatClient,
        host: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {host}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            always_update=True,
        )
        self.renderer = RendererPower()
        self._client = client
        self._host = host

    async def _async_update_data(self) -> bool:
        # Not answering is a normal state (receiver without quick start in
        # standby, powered off), so this never raises UpdateFailed.
        reachable = await self._client.async_keepalive(self._host)
        services: set[str] = set()
        if reachable:
            try:
                services = await async_search(self._host)
            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.debug("SSDP status search failed for %s: %s", self._host, err)
        self.renderer.update(services)
        return reachable
