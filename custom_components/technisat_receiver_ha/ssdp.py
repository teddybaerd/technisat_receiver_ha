"""Targeted SSDP polling; no fixed renderer URL or device number."""
from __future__ import annotations

import asyncio
import socket

RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
BASELINE = {"urn:schemas-upnp-org:device:MediaServer:1",
            "urn:pv-com:device:NMCQueueHandlerDevice:1"}


def response_type(data: bytes) -> str | None:
    """Only accept an SSDP search response, not an arbitrary UDP packet."""
    lines = data.decode("utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip().upper() != "HTTP/1.1 200 OK":
        return None
    headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
    return next((value.strip() for key, value in headers.items()
                 if key.strip().lower() == "st"), None)


async def async_search(host: str, *, port: int = 1900,
                       timeout: float = 2.5) -> set[str]:
    """Search only this receiver, using a fresh ephemeral socket each time.

    Send twice to tolerate loss. Unicast avoids depending on multicast routing
    in VM/container networks. An empty result is inconclusive, never standby.
    """
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(host, port, family=socket.AF_INET,
                                      type=socket.SOCK_DGRAM)
    target = addresses[0][4]
    request = (
        'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
        'MAN: "ssdp:discover"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n'
    ).encode()
    found: set[str] = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        sock.bind(("0.0.0.0", 0))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        if port == 1900:
            await loop.sock_sendto(sock, request, ("239.255.255.250", port))
        for _ in range(2):
            await loop.sock_sendto(sock, request, target)
        deadline = loop.time() + timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                data, source = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 65535), remaining)
            except TimeoutError:
                break
            if source[0] == target[0] and (kind := response_type(data)):
                found.add(kind)
    return found


class RendererPower:
    """Infer standby only after renderer support has been observed.

    Two consecutive searches with baseline services but no renderer are needed.
    Missing all SSDP replies invalidates the observation instead of guessing off.
    """
    def __init__(self) -> None:
        self.detected = False
        self.power: bool | None = None
        self._misses = 0

    def update(self, services: set[str]) -> None:
        if RENDERER in services:
            self.detected = True
            self.power = True
            self._misses = 0
        elif self.detected and services & BASELINE:
            self._misses += 1
            if self._misses >= 2:
                self.power = False
        else:
            self.power = None
            self._misses = 0
