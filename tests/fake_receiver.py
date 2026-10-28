"""Fake TechniSat receiver (answers from a different port like the real one)."""

import asyncio
import re

INFO = (
    b'<deviceInformationResponse name="DIGIT ISIO STC+" serial="0008c92e78502c51">'
    b"<version>1.5</version><capabilities><type>STB</type><rcu/></capabilities>"
    b"</deviceInformationResponse>\x00"
)


class FakeReceiver(asyncio.DatagramProtocol):
    """Listens on 8090-like port, answers from a different source port (8093)."""

    def __init__(self, pin="0000", rcu=True):
        self.pin, self.rcu, self.keys, self.authed = pin, rcu, [], False

    async def start(self):
        loop = asyncio.get_running_loop()
        self.rx, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=("127.0.0.1", 0)
        )
        self.port = self.rx.get_extra_info("sockname")[1]
        self.tx, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )

    def datagram_received(self, data, addr):
        text = data.decode()
        if text.startswith("<keepAliveRequest"):
            self.tx.sendto(b"<keepAliveResponse/>\x00", addr)
        elif text.startswith("<deviceInformationRequest"):
            self.tx.sendto(INFO, addr)
        elif text.startswith("<deviceDiscoveryRequest"):
            self.tx.sendto(
                b'<deviceDiscoveryResponse name="DIGIT ISIO STC+" type="STB" '
                b'serial="0008c92e78502c51" version="1.5"/>\x00',
                addr,
            )
        elif text.startswith("<authenticationRequest"):
            if not self.rcu:
                return  # no answer when app control is disabled
            ok = f'pin="{self.pin}"' in text
            self.authed = ok
            result = "SUCCESS" if ok else "FAILED"
            self.tx.sendto(f'<authenticationResponse result="{result}" />\x00'.encode(), addr)
        elif text.startswith("<rcuButtonRequest"):
            m = re.search(r'code="(\d+)" state="(\w+)"', text)
            self.keys.append((int(m[1]), m[2]))

    def close(self):
        self.rx.close()
        self.tx.close()
