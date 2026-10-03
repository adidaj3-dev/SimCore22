import asyncio
import logging

logger = logging.getLogger(__name__)


class ForesightTransport:
    """
    Handles low-level communication with the Foresight LM → connector stream.
    Supports both TCP and UDP depending on device configuration.
    """

    def __init__(self, host: str, port: int, protocol: str = "tcp"):
        self.host = host
        self.port = port
        self.protocol = protocol.lower()

        self.reader = None
        self.writer = None
        self.transport = None
        self.protocol_instance = None

    async def connect(self):
        """
        Establishes a connection to the LM stream.
        """

        if self.protocol == "tcp":
            logger.info(f"Connecting via TCP to {self.host}:{self.port}")
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        elif self.protocol == "udp":
            logger.info(f"Connecting via UDP to {self.host}:{self.port}")
            loop = asyncio.get_running_loop()
            self.transport, self.protocol_instance = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(),
                remote_addr=(self.host, self.port)
            )

        else:
            raise ValueError("Protocol must be 'tcp' or 'udp'")

    async def read_packets(self):
        """
        Async generator yielding raw packets from the LM stream.
        """

        if self.protocol == "tcp":
            while True:
                try:
                    data = await self.reader.read(4096)
                    if not data:
                        logger.warning("TCP connection closed by LM.")
                        break
                    yield data
                except Exception as e:
                    logger.error(f"TCP read error: {e}")
                    break

        elif self.protocol == "udp":
            while True:
                try:
                    data = await self.protocol_instance.queue.get()
                    yield data
                except Exception as e:
                    logger.error(f"UDP read error: {e}")
                    break


class _UDPProtocol(asyncio.DatagramProtocol):
    """
    Internal helper class for UDP packet reception.
    """

    def __init__(self):
        self.queue = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.queue.put_nowait(data)
