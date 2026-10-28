"""Config flow: discovery or manual host, PIN check, options."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import network
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import async_acquire_client, async_release_client
from .const import (
    CONF_HW_VERSION,
    CONF_MAC,
    CONF_MODEL,
    CONF_PIN,
    CONF_POWER_THRESHOLD,
    CONF_SERIAL,
    CONF_STATUS_ENTITY,
    CONF_SW_VERSION,
    DEFAULT_PIN,
    DEFAULT_POWER_THRESHOLD,
    DOMAIN,
)
from .protocol import ReceiverInfo

_LOGGER = logging.getLogger(__name__)

_MANUAL = "manual"


async def _broadcast_addresses(hass) -> list[str]:
    """Directed broadcast address of every enabled IPv4 network + global one."""
    addresses = {"255.255.255.255"}
    for adapter in await network.async_get_adapters(hass):
        if not adapter["enabled"]:
            continue
        for ip4 in adapter["ipv4"]:
            try:
                net = ipaddress.ip_network(
                    f"{ip4['address']}/{ip4['network_prefix']}", strict=False
                )
            except ValueError:
                continue
            if not net.is_loopback:
                addresses.add(str(net.broadcast_address))
    return sorted(addresses)


class TechniSatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, ReceiverInfo] = {}
        self._info: ReceiverInfo | None = None

    # ------------------------------------------------------------------ steps

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Broadcast discovery, let the user pick a receiver or enter one."""
        if user_input is not None:
            if user_input[CONF_HOST] == _MANUAL:
                return await self.async_step_manual()
            self._info = self._found[user_input[CONF_HOST]]
            return await self.async_step_pin()

        client = await async_acquire_client(self.hass)
        try:
            found = await client.async_discover(await _broadcast_addresses(self.hass))
        finally:
            await async_release_client(self.hass)
        configured = {e.unique_id for e in self._async_current_entries()}
        self._found = {
            i.host: i for i in found if i.supported and i.serial not in configured
        }
        if not self._found:
            return await self.async_step_manual()

        options = {
            host: f"{info.name} ({host})" for host, info in self._found.items()
        }
        options[_MANUAL] = "—"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(options)}),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Enter the IP address by hand (discovery blocked, e.g. Docker bridge)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info = await self._async_query(host)
            if info is None:
                errors["base"] = "cannot_connect"
            elif not info.supported:
                errors["base"] = "unsupported_device"
            else:
                self._info = info
                return await self.async_step_pin()
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str}
            ),
            errors=errors,
        )

    async def async_step_pin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Verify the PIN, which also proves that app control is enabled."""
        assert self._info is not None
        info = self._info
        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN].strip()
            client = await async_acquire_client(self.hass)
            try:
                ok = await client.async_authenticate(info.host, pin)
                if not ok:
                    # Re-read the info: rcu is only listed with app control on.
                    fresh = await client.async_device_info(info.host)
                    if fresh is not None:
                        info = self._info = fresh
            finally:
                await async_release_client(self.hass)
            if ok:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: info.host})
                return self.async_create_entry(
                    title=info.name or "TechniSat",
                    data={
                        CONF_HOST: info.host,
                        CONF_PIN: pin,
                        CONF_SERIAL: info.serial,
                        CONF_NAME: info.name,
                        CONF_MODEL: info.name,
                        CONF_SW_VERSION: info.software_version,
                        CONF_HW_VERSION: info.hardware_version,
                        CONF_MAC: info.mac_lan,
                    },
                )
            errors["base"] = "auth_failed" if info.rcu_enabled else "rcu_disabled"
        return self.async_show_form(
            step_id="pin",
            data_schema=vol.Schema(
                {vol.Required(CONF_PIN, default=DEFAULT_PIN): str}
            ),
            description_placeholders={"name": info.name, "host": info.host},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change IP address or PIN."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            pin = user_input[CONF_PIN].strip()
            info = await self._async_query(host)
            if info is None:
                errors["base"] = "cannot_connect"
            elif info.serial != entry.unique_id:
                errors["base"] = "wrong_device"
            else:
                client = await async_acquire_client(self.hass)
                try:
                    ok = await client.async_authenticate(host, pin)
                finally:
                    await async_release_client(self.hass)
                if ok:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_HOST: host, CONF_PIN: pin}
                    )
                errors["base"] = "auth_failed" if info.rcu_enabled else "rcu_disabled"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PIN, default=entry.data[CONF_PIN]): str,
                }
            ),
            errors=errors,
        )

    # ---------------------------------------------------------------- helpers

    async def _async_query(self, host: str) -> ReceiverInfo | None:
        client = await async_acquire_client(self.hass)
        try:
            return await client.async_device_info(host)
        finally:
            await async_release_client(self.hass)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Options: optional status entity."""
        return TechniSatOptionsFlow()


class TechniSatOptionsFlow(OptionsFlow):
    """Optional entity that reports the real on/off state."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a status entity and threshold."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        entity_default = opts.get(CONF_STATUS_ENTITY)
        schema = {
            vol.Optional(
                CONF_STATUS_ENTITY,
                **({"description": {"suggested_value": entity_default}} if entity_default else {}),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["sensor", "binary_sensor", "switch", "input_boolean"]
                )
            ),
            vol.Optional(
                CONF_POWER_THRESHOLD,
                default=opts.get(CONF_POWER_THRESHOLD, DEFAULT_POWER_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=500, step=0.5, unit_of_measurement="W",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
