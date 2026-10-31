"""Runtime object tying client, coordinator and power-state logic together."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_HW_VERSION,
    CONF_MAC,
    CONF_MODEL,
    CONF_PIN,
    CONF_POWER_THRESHOLD,
    CONF_SERIAL,
    CONF_STATUS_ENTITY,
    CONF_SW_VERSION,
    DEFAULT_POWER_THRESHOLD,
    DOMAIN,
    KEY_STANDBY,
    KEYS,
)
from .coordinator import TechniSatCoordinator
from .protocol import (
    KEY_DELAY,
    KEY_HOLD,
    MAX_KEY_CODE,
    TechniSatAuthError,
    TechniSatClient,
)

_LOGGER = logging.getLogger(__name__)

# After a standby command the SSDP observation lags (on: ~30 s, standby: ~60 s).
# Until it confirms the new state, or this time is up, the commanded state counts.
TRANSITION_SECONDS = 90.0

type TechniSatConfigEntry = ConfigEntry[TechniSatReceiver]


def power_from_state(state: State | None, threshold: float) -> bool | None:
    """Translate the state of a user supplied status entity into on/off.

    Sensors (power readings) are "on" above the threshold, everything else
    (binary_sensor, switch, input_boolean, ...) is "on" when its state is on.
    Returns None when the state cannot be used.
    """
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    if state.domain == "sensor":
        try:
            return float(state.state) > threshold
        except ValueError:
            return None
    return state.state == STATE_ON


def resolve_command(name: str) -> int:
    """Turn a key name ("vol_up") or a plain code ("36") into a key code."""
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    if key in KEYS:
        return KEYS[key]
    if key.isdigit() and 0 <= int(key) <= MAX_KEY_CODE:
        return int(key)
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_command",
        translation_placeholders={"command": str(name)},
    )


class TechniSatReceiver:
    """One configured receiver."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TechniSatClient
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.host: str = entry.data[CONF_HOST]
        self.pin: str = entry.data[CONF_PIN]
        self.serial: str = entry.data[CONF_SERIAL]
        self.coordinator = TechniSatCoordinator(hass, entry, client, self.host)
        self._status_entity: str | None = entry.options.get(CONF_STATUS_ENTITY) or None
        self._threshold = float(
            entry.options.get(CONF_POWER_THRESHOLD, DEFAULT_POWER_THRESHOLD)
        )
        self._power: bool | None = None
        self._expected: tuple[bool, float] | None = None  # (state, monotonic deadline)
        self._power_lock = asyncio.Lock()

    # ------------------------------------------------------------- properties

    @property
    def signal(self) -> str:
        """Dispatcher signal fired when the (assumed) power state changes."""
        return f"{DOMAIN}_{self.entry.entry_id}_state"

    @property
    def has_status_source(self) -> bool:
        """True when a user supplied entity reports the real power state."""
        return self._status_entity is not None

    @property
    def power(self) -> bool | None:
        """True/False/None (unknown)."""
        if not self.has_status_source and self.coordinator.renderer.detected:
            observed = self.coordinator.renderer.power
            if self._expected is not None:
                value, deadline = self._expected
                if observed == value or time.monotonic() >= deadline:
                    self._expected = None  # confirmed, or give up and trust SSDP
                else:
                    return value
            return observed
        return self._power

    @property
    def reachable(self) -> bool:
        """The receiver answered the last keep-alive."""
        return bool(self.coordinator.last_update_success and self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry."""
        data = self.entry.data
        info = DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            manufacturer="TechniSat",
            model=data.get(CONF_MODEL),
            name=self.entry.title,
            sw_version=data.get(CONF_SW_VERSION),
            hw_version=data.get(CONF_HW_VERSION),
        )
        if mac := data.get(CONF_MAC):
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(mac))}
        return info

    # ------------------------------------------------------------ state logic

    @callback
    def async_start(self) -> None:
        """Start following the optional status entity."""
        if self._status_entity is None:
            return
        self._apply_status(self.hass.states.get(self._status_entity))
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [self._status_entity], self._handle_status_event
            )
        )

    @callback
    def _handle_status_event(self, event: Event[EventStateChangedData]) -> None:
        self._apply_status(event.data["new_state"])

    @callback
    def _apply_status(self, state: State | None) -> None:
        value = power_from_state(state, self._threshold)
        if value is not None:
            self._set_power(value)

    @callback
    def _set_power(self, value: bool | None) -> None:
        if value != self._power:
            self._power = value
            async_dispatcher_send(self.hass, self.signal)

    @callback
    def _commanded(self, value: bool) -> None:
        """Remember a state we just commanded and tell the entities."""
        self._expected = (value, time.monotonic() + TRANSITION_SECONDS)
        if not self.has_status_source:
            self._power = value
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def restore_power(self, value: bool) -> None:
        """Seed the assumed state from the previous run."""
        if self._power is None and not self.has_status_source:
            self._power = value

    # ---------------------------------------------------------------- sending

    async def _async_send(
        self, codes: Sequence[int], delay: float, hold: float
    ) -> None:
        try:
            await self.client.async_send_keys(
                self.host, self.pin, codes, delay=delay, hold=hold
            )
        except TechniSatAuthError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"host": self.host},
            ) from err

    async def async_send_codes(
        self,
        codes: Sequence[int],
        *,
        delay: float = KEY_DELAY,
        hold: float = KEY_HOLD,
    ) -> None:
        """Send keys; keeps the assumed state in step when standby is pressed."""
        await self._async_send(codes, delay, hold)
        current = self.power
        if (
            not self.has_status_source
            and current is not None
            and list(codes).count(KEY_STANDBY) % 2
        ):
            self._commanded(not current)

    async def async_set_power(self, on: bool) -> None:
        """Switch on/off. The standby key is a toggle, so skip when already there."""
        async with self._power_lock:
            if self.power is on:
                return
            await self._async_send([KEY_STANDBY], KEY_DELAY, KEY_HOLD)
            if not self.has_status_source:
                self._commanded(on)
            await self.coordinator.async_request_refresh()
