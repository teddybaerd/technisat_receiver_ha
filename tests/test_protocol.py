"""Protocol tests against a fake receiver that answers from another port."""

from __future__ import annotations

import asyncio

import pytest

from fake_receiver import FakeReceiver
from ts_protocol import (
    TechniSatAuthError,
    TechniSatClient,
)

@pytest.fixture
async def setup():
    rec = FakeReceiver()
    await rec.start()
    client = TechniSatClient(port=rec.port, local_port=0, request_timeout=0.3)
    await client.async_start()
    yield rec, client
    client.close()
    rec.close()


async def test_keepalive(setup):
    _, client = setup
    assert await client.async_keepalive("127.0.0.1") is True


async def test_keepalive_no_answer():
    client = TechniSatClient(port=9, local_port=0, request_timeout=0.1)
    await client.async_start()
    try:
        assert await client.async_keepalive("127.0.0.1") is False
    finally:
        client.close()


async def test_device_info(setup):
    _, client = setup
    info = await client.async_device_info("127.0.0.1")
    assert info.name == "DIGIT ISIO STC+"
    assert info.serial == "0008c92e78502c51"
    assert info.rcu_enabled and info.supported


async def test_auth_ok_and_wrong_pin(setup):
    _, client = setup
    assert await client.async_authenticate("127.0.0.1", "0000") is True
    assert await client.async_authenticate("127.0.0.1", "1111") is False


async def test_send_keys_pressed_released(setup):
    rec, client = setup
    await client.async_send_keys("127.0.0.1", "0000", [11, 32], delay=0.01, hold=0.01)
    await asyncio.sleep(0.1)
    assert rec.keys == [(11, "pressed"), (11, "released"), (32, "pressed"), (32, "released")]


async def test_send_keys_wrong_pin(setup):
    rec, client = setup
    with pytest.raises(TechniSatAuthError):
        await client.async_send_keys("127.0.0.1", "9999", [11])
    assert rec.keys == []


async def test_send_keys_out_of_range(setup):
    _, client = setup
    with pytest.raises(ValueError):
        await client.async_send_keys("127.0.0.1", "0000", [999])


async def test_discovery(setup):
    _, client = setup
    found = await client.async_discover(["127.0.0.1"], timeout=0.6)
    assert [f.serial for f in found] == ["0008c92e78502c51"]
