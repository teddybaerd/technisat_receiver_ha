"""Remote platform: send arbitrary keys."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_HOLD_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TechniSatEntity
from .protocol import KEY_HOLD
from .receiver import TechniSatConfigEntry, TechniSatReceiver, resolve_command


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechniSatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remote."""
    async_add_entities([TechniSatRemote(entry.runtime_data)])


class TechniSatRemote(TechniSatEntity, RemoteEntity):
    """Send key names (see README) or raw key codes to the receiver."""

    _attr_translation_key = "remote"

    def __init__(self, receiver: TechniSatReceiver) -> None:
        super().__init__(receiver, "remote")

    @property
    def is_on(self) -> bool | None:
        """On, off or unknown."""
        return self.receiver.power

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Wake the receiver from standby."""
        await self.receiver.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the receiver into standby."""
        await self.receiver.async_set_power(False)

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send one or more keys, optionally repeated."""
        codes = [resolve_command(name) for name in command]  # validate everything first
        repeats = int(kwargs.get(ATTR_NUM_REPEATS, 1))
        delay = float(kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS))
        hold = float(kwargs.get(ATTR_HOLD_SECS) or KEY_HOLD)
        await self.receiver.async_send_codes(codes * max(repeats, 1), delay=delay, hold=hold)
