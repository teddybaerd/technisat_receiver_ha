"""Integration tests (need pytest-homeassistant-custom-component)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_HOST  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.technisat_receiver_ha.const import (  # noqa: E402
    CONF_PIN,
    CONF_SERIAL,
    CONF_STATUS_ENTITY,
    DOMAIN,
)
from fake_receiver import FakeReceiver  # noqa: E402
from ts_protocol import TechniSatClient  # noqa: E402




@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    with patch("custom_components.technisat_receiver_ha.coordinator.async_search", return_value=set()):
        yield


@pytest.fixture
async def receiver(socket_enabled):
    rec = FakeReceiver()
    await rec.start()

    def factory():
        return TechniSatClient(port=rec.port, local_port=0, request_timeout=0.3)

    with patch("custom_components.technisat_receiver_ha.client.TechniSatClient", factory):
        yield rec
    rec.close()


async def test_manual_flow_and_control(hass, receiver):
    with patch(
        "custom_components.technisat_receiver_ha.config_flow._broadcast_addresses",
        return_value=["127.0.0.1"],
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    # no broadcast reachable in the sandbox -> falls through to manual or list
    assert result["type"] is FlowResultType.FORM
    if result["step_id"] == "user":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "manual"}
        )
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["step_id"] == "pin"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1111"})
    assert result["errors"] == {"base": "auth_failed"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "0000"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERIAL] == "0008c92e78502c51"

    entry = result["result"]
    await hass.async_block_till_done()
    state = hass.states.get("media_player.digit_isio_stc")
    assert state is not None
    assert state.state == "unknown"  # nothing known about power yet

    await hass.services.async_call(
        "remote", "send_command",
        {"entity_id": "remote.digit_isio_stc_remote", "command": ["menu", "36"], "delay_secs": 0.01},
        blocking=True,
    )
    await asyncio.sleep(0.1)
    assert [k for k in receiver.keys if k[1] == "pressed"] == [(32, "pressed"), (36, "pressed")]

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_status_entity_drives_state(hass, receiver):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="0008c92e78502c51",
        title="DIGIT ISIO STC+",
        data={CONF_HOST: "127.0.0.1", CONF_PIN: "0000", CONF_SERIAL: "0008c92e78502c51"},
        options={CONF_STATUS_ENTITY: "sensor.plug_power"},
    )
    hass.states.async_set("sensor.plug_power", "13.5")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("media_player.digit_isio_stc").state == "on"
    hass.states.async_set("sensor.plug_power", "5.0")
    await hass.async_block_till_done()
    assert hass.states.get("media_player.digit_isio_stc").state == "off"

    await hass.services.async_call(
        "media_player", "turn_on", {"entity_id": "media_player.digit_isio_stc"}, blocking=True
    )
    await asyncio.sleep(0.1)
    assert (11, "pressed") in receiver.keys



async def test_renderer_power_and_unreachable(hass, receiver):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="renderer-test", title="Receiver",
        data={CONF_HOST: "127.0.0.1", CONF_PIN: "0000", CONF_SERIAL: "renderer-test"},
    )
    entry.add_to_hass(hass)
    renderer = {"urn:schemas-upnp-org:device:MediaRenderer:1"}
    baseline = {"urn:schemas-upnp-org:device:MediaServer:1"}
    with patch("custom_components.technisat_receiver_ha.coordinator.async_search", return_value=renderer):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    entity_id = "media_player.receiver"
    assert hass.states.get(entity_id).state == "on"
    with patch("custom_components.technisat_receiver_ha.coordinator.async_search", return_value=baseline):
        await coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "on"
        await coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "off"
    with patch("custom_components.technisat_receiver_ha.coordinator.async_search", return_value=set()):
        await coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "unknown"
    with patch.object(entry.runtime_data.client, "async_keepalive", return_value=False):
        await coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "unavailable"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_commanded_state_bridges_ssdp_lag(hass, receiver):
    """Right after a command the commanded state counts; turn_on must not be skipped."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="lag-test", title="Receiver",
        data={CONF_HOST: "127.0.0.1", CONF_PIN: "0000", CONF_SERIAL: "lag-test"},
    )
    entry.add_to_hass(hass)
    renderer = {"urn:schemas-upnp-org:device:MediaRenderer:1"}
    baseline = {"urn:schemas-upnp-org:device:MediaServer:1"}
    target = "custom_components.technisat_receiver_ha.coordinator.async_search"
    entity_id = "media_player.receiver"
    with patch(target, return_value=renderer):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "on"

        # turn off: SSDP still reports the renderer (stale) -> state is already "off"
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": entity_id}, blocking=True
        )
        await asyncio.sleep(0.1)
        await entry.runtime_data.coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "off"
        assert receiver.keys.count((11, "pressed")) == 1

        # turn on again right away must send the key (no skip on stale "on")
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": entity_id}, blocking=True
        )
        await asyncio.sleep(0.1)
        assert receiver.keys.count((11, "pressed")) == 2
        assert hass.states.get(entity_id).state == "on"

    # standby commanded, SSDP catches up: confirmed after two misses
    with patch(target, return_value=baseline):
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": entity_id}, blocking=True
        )
        await asyncio.sleep(0.1)
        coordinator = entry.runtime_data.coordinator
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "off"

    # transition time over and SSDP says the receiver is on (e.g. physical remote)
    entry.runtime_data._expected = (False, 0.0)
    with patch(target, return_value=renderer):
        await entry.runtime_data.coordinator.async_refresh()
        assert hass.states.get(entity_id).state == "on"
    await hass.config_entries.async_unload(entry.entry_id)
