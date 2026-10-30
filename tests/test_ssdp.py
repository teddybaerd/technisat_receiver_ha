"""Power detection regressions independent of Home Assistant."""
import importlib.util
from pathlib import Path
import asyncio
import pytest

spec = importlib.util.spec_from_file_location(
    'ts_ssdp', Path(__file__).parents[1] / 'custom_components/technisat_receiver_ha/ssdp.py')
ssdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ssdp)


def test_power_cycle_and_loss():
    power = ssdp.RendererPower()
    baseline = {next(iter(ssdp.BASELINE))}
    power.update(baseline)
    assert not power.detected and power.power is None
    power.update({ssdp.RENDERER})
    assert power.detected and power.power is True
    power.update(baseline)
    assert power.power is True
    power.update(baseline)
    assert power.power is False
    power.update(set())
    assert power.power is None
    power.update(baseline)
    assert power.power is None
    power.update({ssdp.RENDERER})
    assert power.power is True


def test_search_response_validation():
    assert ssdp.response_type(b'NOTIFY * HTTP/1.1\r\nST: fake\r\n') is None
    assert ssdp.response_type(b'HTTP/1.1 200 OK\r\nst: renderer\r\n') == 'renderer'


@pytest.mark.asyncio
async def test_udp_search_changed_paths():
    class Device(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport
        def datagram_received(self, data, addr):
            assert b'M-SEARCH' in data
            for path in ('dev6', 'dev7'):
                self.transport.sendto((
                    'HTTP/1.1 200 OK\r\nST: ' + ssdp.RENDERER +
                    '\r\nLOCATION: http://127.0.0.1:9085/' + path + '/desc.xml\r\n\r\n'
                ).encode(), addr)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(Device, local_addr=('127.0.0.1', 0))
    try:
        result = await ssdp.async_search('127.0.0.1', port=transport.get_extra_info('sockname')[1], timeout=0.1)
        assert result == {ssdp.RENDERER}
    finally:
        transport.close()
