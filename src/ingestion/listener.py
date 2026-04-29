import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

from src.ingestion.decoder import decode_aave_raw_event, supported_topic_signatures
from src.infra.kafka.producer import AsyncKafkaProducer
from src.infra.web3.ws_client import PolygonWsClient


logger = logging.getLogger(__name__)

DEFAULT_AAVE_RAW_TOPIC = "aave_raw_events"


class AaveIngestionListener:
    def __init__(
        self,
        *,
        ws_url: str,
        pool_address: str,
        kafka_bootstrap_servers: str,
        kafka_topic: str = DEFAULT_AAVE_RAW_TOPIC,
    ) -> None:
        self._ws_client = PolygonWsClient(ws_url)
        self._producer = AsyncKafkaProducer(
            {"bootstrap.servers": kafka_bootstrap_servers, "client.id": "defi-ingestion-listener"}
        )
        self._pool_address = pool_address
        self._kafka_topic = kafka_topic
        self._shutdown_event = asyncio.Event()
        self._shutdown_started = False

    async def run(self) -> None:
        await self._producer.start()
        await self._subscribe_to_pool_logs()
        logger.info("Aave ingestion listener started.")

        try:
            async for raw_message in self._ws_client.messages():
                if self._shutdown_event.is_set():
                    break
                await self._handle_message(raw_message)
        except asyncio.CancelledError:
            logger.info("Listener run task cancelled.")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._shutdown_event.set()
        await self._ws_client.disconnect()
        await self._producer.close(flush_timeout_seconds=2.0)
        logger.info("Aave ingestion listener stopped cleanly.")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _subscribe_to_pool_logs(self) -> None:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": [
                "logs",
                {
                    "address": self._pool_address,
                    "topics": [supported_topic_signatures()],
                },
            ],
        }
        payload_json = json.dumps(payload)
        logger.debug("ETH_SUBSCRIBE PAYLOAD: %s", payload_json)
        await self._ws_client.send(payload_json)

    async def _handle_message(self, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.error("Invalid JSON message received from websocket.")
            return

        decoded = decode_aave_raw_event(message)
        if decoded is None:
            return

        await self._producer.produce(
            topic=self._kafka_topic,
            key=decoded.user_address,
            value=decoded.model_dump_json(),
        )


def _register_signal_handlers(listener: AaveIngestionListener, run_task: asyncio.Task[None]) -> None:
    signal_seen = False

    def _handler(signum, frame) -> None:  # type: ignore[no-untyped-def,unused-argument]
        nonlocal signal_seen
        if signal_seen:
            return
        signal_seen = True
        logger.info("Received signal %s, requesting shutdown.", signum)
        listener.request_shutdown()
        run_task.cancel()

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


async def main() -> None:
    ws_url = os.environ["POLYGON_WS_URL"]
    pool_address = os.environ["AAVE_V3_POOL_ADDRESS"]
    kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic = os.getenv("AAVE_RAW_EVENTS_TOPIC", DEFAULT_AAVE_RAW_TOPIC)

    listener = AaveIngestionListener(
        ws_url=ws_url,
        pool_address=pool_address,
        kafka_bootstrap_servers=kafka_bootstrap_servers,
        kafka_topic=kafka_topic,
    )
    run_task = asyncio.create_task(listener.run())
    _register_signal_handlers(listener, run_task)

    try:
        await run_task
    except asyncio.CancelledError:
        logger.info("Main task cancelled; continuing shutdown.")
    finally:
        try:
            await asyncio.wait_for(listener.shutdown(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Graceful shutdown exceeded 5s, forcing exit.")
            sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
