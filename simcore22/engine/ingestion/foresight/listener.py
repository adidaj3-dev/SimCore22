# simcore22/engine/ingestion/foresight/listener.py
import asyncio
import datetime
import logging

from simcore22.engine.ingestion.foresight.transport import ForesightTransport
from simcore22.engine.ingestion.foresight.parser import parse_foresight_packet
from simcore22.engine.ingestion.dispatcher import EventDispatcher
from simcore22.engine.models.events import ShotEvent

logger = logging.getLogger(__name__)


class ForesightLiveListener:
    """
    Universal Foresight listener for Falcon, Hawk, GC3, GCQuad.
    - Connects to LM stream
    - Parses raw packets into normalized shot payloads
    - Emits ShotEvent objects into the dispatcher
    """

    def __init__(self, host: str, port: int, dispatcher: EventDispatcher):
        self.host = host
        self.port = port
        self.transport = ForesightTransport(host, port)
        self.dispatcher = dispatcher

    async def start(self) -> None:
        logger.info(f"Starting Foresight listener on {self.host}:{self.port}")

        while True:
            try:
                await self.transport.connect()
                logger.info("Connected to Foresight LM stream.")
                await self._listen()
            except ConnectionRefusedError:
                logger.error("Foresight connection refused. Retrying in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"Unexpected Foresight listener error: {e}")
                await asyncio.sleep(3)

    async def _listen(self) -> None:
        async for raw_packet in self.transport.read_packets():
            await self._process_packet(raw_packet)

    async def _process_packet(self, raw_packet: bytes) -> None:
        timestamp = datetime.datetime.now()

        try:
            payload = parse_foresight_packet(raw_packet)
        except Exception as e:
            logger.error(f"Packet parsing failed: {e}")
            return

        if payload is None:
            return

        logger.info(f"Received Foresight shot payload: {payload}")

        shot = ShotEvent(
            source_device=payload.get("device", "Foresight"),
            timestamp=timestamp,
            ball_speed=payload.get("ball_speed"),
            launch_angle=payload.get("launch_angle"),
            azimuth=payload.get("azimuth"),
            spin_rate=payload.get("spin_rate"),
            spin_axis=payload.get("spin_axis"),
            club_speed=payload.get("club_speed"),
            carry_distance=payload.get("carry"),
            total_distance=payload.get("total"),
        )

        self.dispatcher.emit(shot)
