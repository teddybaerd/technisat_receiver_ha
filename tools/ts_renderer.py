#!/usr/bin/env python3
"""Probe the UPnP MediaRenderer of a TechniSat receiver (diagnostic helper).

Usage: python3 ts_renderer.py 192.168.178.53
Run it with the receiver switched ON. It lists the SSDP services, the renderer
description and the answers of the AVTransport / RenderingControl status calls,
so you can see whether anything changes when you switch channel or volume.
"""
import re
import socket
import sys
import time
import urllib.request
from xml.etree import ElementTree as ET

if len(sys.argv) != 2:
    sys.exit(__doc__)
HOST = sys.argv[1]


def ssdp():
    """Unicast M-SEARCH to the receiver, return {search target: location}."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    request = (
        'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
        'MAN: "ssdp:discover"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n'
    ).encode()
    for _ in range(3):
        sock.sendto(request, (HOST, 1900))
    found = {}
    end = time.time() + 4
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        if addr[0] != HOST:
            continue
        lines = data.decode(errors="replace").splitlines()[1:]
        headers = {}
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        found[headers.get("st", "?")] = headers.get("location", "")
    return found


def soap(url, service, action, body=""):
    envelope = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action} xmlns:u="{service}">{body}</u:{action}>'
        '</s:Body></s:Envelope>'
    ).encode()
    request = urllib.request.Request(
        url,
        envelope,
        {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service}#{action}"',
        },
    )
    try:
        return urllib.request.urlopen(request, timeout=5).read().decode(errors="replace")
    except Exception as err:  # noqa: BLE001 - diagnostic tool
        return f"ERROR: {err}"


found = ssdp()
print("SSDP services answered by", HOST)
for kind in sorted(found):
    print("  ", kind)
location = next((v for k, v in found.items() if "MediaRenderer:" in k and ":device:" in k), None)
if not location:
    sys.exit(
        "\nNo MediaRenderer found. Is the receiver switched on? If the list above is "
        "empty, this machine gets no SSDP answers (try it on the Home Assistant host)."
    )

print("\nLOCATION:", location)
xml = urllib.request.urlopen(location, timeout=5).read().decode(errors="replace")
print(re.sub(r"\s+", " ", xml)[:1500])
root = ET.fromstring(re.sub(r' xmlns="[^"]+"', "", xml, count=1))
base = re.match(r"https?://[^/]+", location).group(0)
services = {
    s.findtext("serviceType"): (s.findtext("controlURL"), s.findtext("SCPDURL"))
    for s in root.iter("service")
}
print("\nServices:")
for stype, (control, scpd) in services.items():
    print("  ", stype, control, scpd)

for stype, (control, _) in services.items():
    url = base + control if control.startswith("/") else control
    if ":AVTransport:" in stype:
        for action in ("GetTransportInfo", "GetMediaInfo", "GetPositionInfo"):
            print(f"\n--- {action}")
            print(soap(url, stype, action, "<InstanceID>0</InstanceID>")[:1500])
    if ":RenderingControl:" in stype:
        for action in ("GetVolume", "GetMute"):
            print(f"\n--- {action}")
            body = "<InstanceID>0</InstanceID><Channel>Master</Channel>"
            print(soap(url, stype, action, body)[:800])
