"""Asyncio UDP client for the TechniSat network remote protocol.

This module deliberately has no Home Assistant imports so that it can be
tested stand-alone.

Protocol summary (observed on a DIGIT ISIO STC+, protocol version 1.5):

* Everything is small XML strings sent as UDP datagrams to port 8090 of the
  receiver.
* The receiver answers from its own source port (8093 on the tested device),
  not from the port the request was sent to.
* ``<keepAliveRequest/>``            -> ``<keepAliveResponse/>``
* ``<deviceInformationRequest/>``    -> ``<deviceInformationResponse .../>``
* ``<deviceDiscoveryRequest/>``      -> ``<deviceDiscoveryResponse .../>``
  (usually sent as broadcast)
* ``<authenticationRequest pin=".."/>`` -> ``<authenticationResponse result="SUCCESS"/>``
  The receiver does not answer at all while remote control via app is switched
  off in its menu.
* ``<rcuButtonRequest code="N" state="pressed|released"/>`` is never answered.

The wire format was first documented by the TechniSatAPI project
(https://github.com/feuster/TechniSatAPI). This is an independent
implementation.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.sax.saxutils import quoteattr

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8090
REQUEST_TIMEOUT = 1.5  # seconds to wait for an answer
REQUEST_ATTEMPTS = 2  # UDP is lossy: ask twice before giving up
KEY_HOLD = 0.1  # seconds between "pressed" and "released"
KEY_DELAY = 0.4  # seconds between two keys of one command
MAX_KEY_CODE = 127

SUPPORTED_DEVICE_TYPE = "STB"


class TechniSatError(Exception):
    """Base error."""


class TechniSatConnectionError(TechniSatError):
    """The UDP endpoint could not be opened."""


class TechniSatAuthError(TechniSatError):
    """The receiver did not accept the PIN (or does not answer at all)."""


@dataclass(slots=True)
class ReceiverInfo:
    """What a receiver tells about itself."""

    host: str
    name: str
    serial: str
    device_type: str | None = None
    protocol_version: str | None = None
    software_version: str | None = None
    hardware_version: str | None = None
    mac_lan: str | None = None
    rcu_enabled: bool = False

    @property
    def supported(self) -> bool:
        """Only set-top boxes were verified; unknown types are rejected."""
        return self.device_type in (None, SUPPORTED_DEVICE_TYPE)


def _parse(data: bytes) -> ElementTree.Element | None:
    """Parse a datagram, returning None for anything that is not plain XML."""
    text = data.decode("utf-8", errors="replace").strip("\x00 \r\n\t")
    if not text or "<!" in text:  # refuse DOCTYPE / entity declarations
        return None
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None


def _info_from_root(host: str, root: ElementTree.Element) -> ReceiverInfo:
    """Build ReceiverInfo from a discovery or information response."""
    attrib = root.attrib
    device_type = attrib.get("type")
    rcu_enabled = False
    caps = root.find("capabilities")
    if caps is not None:
        type_node = caps.find("type")
        if type_node is not None and type_node.text:
            device_type = type_node.text.strip()
        rcu_enabled = caps.find("rcu") is not None
    return ReceiverInfo(
        host=host,
        name=attrib.get("name") or host,
        serial=attrib.get("serial") or "",
        device_type=device_type,
        protocol_version=attrib.get("protocolVer") or attrib.get("version"),
        software_version=attrib.get("softwareVer"),
        hardware_version=attrib.get("hardwareVer"),
        mac_lan=attrib.get("macLan") or None,
        rcu_enabled=rcu_enabled,
    )


def _button_xml(code: int, state: str) -> str:
    return f'<rcuButtonRequest code="{int(code)}" state="{state}"/>'


class _Protocol(asyncio.DatagramProtocol):
    """Forward datagrams to the client."""

    def __init__(self, client: TechniSatClient) -> None:
        self._client = client

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._client._on_datagram(data, addr)  # noqa: SLF001

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UDP error: %s", exc)


class TechniSatClient:
    """One UDP endpoint shared by all receivers of a Home Assistant instance."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        local_port: int | None = DEFAULT_PORT,
        request_timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        self._port = port
        self._local_port = DEFAULT_PORT if local_port is None else local_port
        self._request_timeout = request_timeout
        self._transport: asyncio.DatagramTransport | None = None
        self._waiters: dict[tuple[str, str], list[asyncio.Future]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._collector: list[tuple[str, ElementTree.Element]] | None = None

    # ------------------------------------------------------------------ setup

    async def async_start(self) -> None:
        """Open the UDP socket (prefers local port 8090, falls back to any)."""
        loop = asyncio.get_running_loop()
        last_error: OSError | None = None
        for local_port in dict.fromkeys((self._local_port, 0)):
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _Protocol(self),
                    local_addr=("0.0.0.0", local_port),
                    allow_broadcast=True,
                )
            except OSError as err:
                last_error = err
                _LOGGER.debug("Cannot bind UDP port %s: %s", local_port, err)
                continue
            self._transport = transport  # type: ignore[assignment]
            _LOGGER.debug("UDP endpoint bound to %s", transport.get_extra_info("sockname"))
            return
        raise TechniSatConnectionError(f"Cannot open UDP socket: {last_error}")

    def close(self) -> None:
        """Close the socket and abort everything that is waiting."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        for futures in self._waiters.values():
            for future in futures:
                future.cancel()
        self._waiters.clear()

    # --------------------------------------------------------------- plumbing

    def _lock(self, host: str) -> asyncio.Lock:
        return self._locks.setdefault(host, asyncio.Lock())

    def _send(self, host: str, payload: str) -> None:
        if self._transport is None:
            raise TechniSatConnectionError("UDP endpoint not started")
        self._transport.sendto(payload.encode(), (host, self._port))

    def _on_datagram(self, data: bytes, addr: tuple) -> None:
        root = _parse(data)
        if root is None:
            return
        host = addr[0]
        if root.tag == "deviceDiscoveryResponse" and self._collector is not None:
            self._collector.append((host, root))
            return
        for future in self._waiters.pop((host, root.tag), []):
            if not future.done():
                future.set_result(root)

    async def _request(
        self, host: str, payload: str, expect: str
    ) -> ElementTree.Element | None:
        """Send a request and wait for the matching response tag (or None)."""
        loop = asyncio.get_running_loop()
        key = (host, expect)
        for _ in range(REQUEST_ATTEMPTS):
            future: asyncio.Future = loop.create_future()
            self._waiters.setdefault(key, []).append(future)
            self._send(host, payload)
            try:
                return await asyncio.wait_for(future, self._request_timeout)
            except TimeoutError:
                continue
            finally:
                waiting = self._waiters.get(key)
                if waiting is not None:
                    if future in waiting:
                        waiting.remove(future)
                    if not waiting:
                        del self._waiters[key]
        return None

    async def _auth(self, host: str, pin: str) -> bool:
        """Authenticate (caller holds the host lock)."""
        root = await self._request(
            host, f"<authenticationRequest pin={quoteattr(pin)}/>", "authenticationResponse"
        )
        return root is not None and root.attrib.get("result", "").upper() == "SUCCESS"

    # -------------------------------------------------------------- public API

    async def async_keepalive(self, host: str) -> bool:
        """Return True when the receiver answers a keep-alive."""
        async with self._lock(host):
            root = await self._request(host, "<keepAliveRequest/>", "keepAliveResponse")
        return root is not None

    async def async_device_info(self, host: str) -> ReceiverInfo | None:
        """Ask a receiver about itself; None when it does not answer."""
        async with self._lock(host):
            root = await self._request(
                host, "<deviceInformationRequest/>", "deviceInformationResponse"
            )
        return None if root is None else _info_from_root(host, root)

    async def async_authenticate(self, host: str, pin: str) -> bool:
        """Check a PIN. False for a wrong PIN *and* for no answer at all."""
        async with self._lock(host):
            return await self._auth(host, pin)

    async def async_send_keys(
        self,
        host: str,
        pin: str,
        codes: Sequence[int],
        *,
        delay: float = KEY_DELAY,
        hold: float = KEY_HOLD,
    ) -> None:
        """Authenticate, then press and release each key code in turn."""
        for code in codes:
            if not 0 <= int(code) <= MAX_KEY_CODE:
                raise ValueError(f"Key code out of range: {code}")
        async with self._lock(host):
            if not await self._auth(host, pin):
                raise TechniSatAuthError(f"{host} did not accept the PIN")
            last = len(codes) - 1
            for index, code in enumerate(codes):
                self._send(host, _button_xml(code, "pressed"))
                await asyncio.sleep(hold)
                self._send(host, _button_xml(code, "released"))
                if index < last:
                    await asyncio.sleep(delay)

    async def async_discover(
        self, broadcast_addresses: Iterable[str], timeout: float = 2.0
    ) -> list[ReceiverInfo]:
        """Broadcast a discovery request and collect the answers."""
        addresses = list(broadcast_addresses)
        self._collector = []
        try:
            for _ in range(3):  # the original tools send it three times
                for address in addresses:
                    try:
                        self._send(address, "<deviceDiscoveryRequest/>")
                    except (OSError, ValueError) as err:
                        _LOGGER.debug("Discovery to %s failed: %s", address, err)
                await asyncio.sleep(timeout / 3)
            found: dict[str, ReceiverInfo] = {}
            for host, root in self._collector:
                found[host] = _info_from_root(host, root)
        finally:
            self._collector = None
        return list(found.values())


def local_port_in_use(port: int = DEFAULT_PORT) -> bool:
    """Best-effort check whether a UDP port is already taken locally."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False
