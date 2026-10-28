"""Base entity."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TechniSatCoordinator
from .receiver import TechniSatReceiver


class TechniSatEntity(CoordinatorEntity[TechniSatCoordinator]):
    """Common behaviour: availability follows reachability, power is shared."""

    _attr_has_entity_name = True

    def __init__(self, receiver: TechniSatReceiver, key: str) -> None:
        super().__init__(receiver.coordinator)
        self.receiver = receiver
        self._attr_unique_id = f"{receiver.serial}_{key}"
        self._attr_device_info = receiver.device_info

    @property
    def available(self) -> bool:
        """Unavailable while the receiver does not answer."""
        return super().available and bool(self.coordinator.data)

    @property
    def assumed_state(self) -> bool:
        """Without a status entity the on/off state is only a guess."""
        return not self.receiver.has_status_source

    async def async_added_to_hass(self) -> None:
        """Follow power state changes."""
        await super().async_added_to_hass()

        @callback
        def _power_changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.receiver.signal, _power_changed)
        )
