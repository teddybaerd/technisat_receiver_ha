"""TechniSat Receiver HA - control TechniSat DIGIT receivers over the network."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .client import async_acquire_client, async_release_client
from .receiver import TechniSatConfigEntry, TechniSatReceiver

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.REMOTE]


async def async_setup_entry(hass: HomeAssistant, entry: TechniSatConfigEntry) -> bool:
    """Set up a receiver."""
    client = await async_acquire_client(hass)
    try:
        receiver = TechniSatReceiver(hass, entry, client)
        entry.runtime_data = receiver
        receiver.async_start()
        # Never raises: an unreachable receiver (standby without quick start)
        # is a normal state and just makes the entities unavailable.
        await receiver.coordinator.async_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await async_release_client(hass)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: TechniSatConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TechniSatConfigEntry) -> bool:
    """Unload a receiver."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await async_release_client(hass)
    return unload_ok
