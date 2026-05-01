import asyncio
import logging
import os
import signal
import sys

from pydantic import ValidationError

from schemas.raw_events import AaveRawEvent
from schemas.state_models import UserProtocolState
from src.infra.kafka.consumer import AsyncKafkaConsumer
from src.infra.kafka.producer import AsyncKafkaProducer
from src.infra.redis.client import AsyncRedisStateClient
from src.infra.redis.keys import get_user_state_key
from src.processing.feature_extractor import extract_features
from src.processing.state_updater import update_user_state


logger = logging.getLogger(__name__)


class RawEventProcessor:
    def __init__(
        self,
        *,
        kafka_bootstrap_servers: str,
        kafka_topic: str,
        features_topic: str,
        kafka_group_id: str,
        redis_url: str,
    ) -> None:
        self._consumer = AsyncKafkaConsumer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "group.id": kafka_group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        self._producer = AsyncKafkaProducer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "client.id": "aave-feature-producer-v1",
            }
        )
        self._redis = AsyncRedisStateClient(redis_url)
        self._kafka_topic = kafka_topic
        self._features_topic = features_topic
        self._shutdown_event = asyncio.Event()
        self._shutdown_started = False

    async def run(self) -> None:
        await self._redis.connect_with_retry()
        await self._producer.start()
        self._consumer.subscribe([self._kafka_topic])
        logger.info("Raw event consumer started topic=%s -> features=%s", self._kafka_topic, self._features_topic)

        try:
            async for msg in self._consumer.messages():
                if self._shutdown_event.is_set():
                    break
                await self._process_message(msg.value())
        except asyncio.CancelledError:
            logger.info("Raw event consumer cancelled.")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._shutdown_event.set()
        await self._consumer.close()
        await self._producer.close(flush_timeout_seconds=2.0)
        await self._redis.close()
        logger.info("Raw event consumer stopped cleanly.")

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _process_message(self, value: bytes | str | None) -> None:
        if value is None:
            return
        if isinstance(value, bytes):
            payload = value.decode("utf-8")
        else:
            payload = value

        try:
            event = AaveRawEvent.model_validate_json(payload)
        except ValidationError:
            logger.exception("Skipping invalid AaveRawEvent payload: %s", payload)
            return

        key = get_user_state_key(event.user_address)
        current_state = await self._redis.get_state(key, UserProtocolState)
        updated_state = update_user_state(event, current_state)
        await self._redis.set_state(key, updated_state)

        features = extract_features(updated_state)
        await self._producer.produce(
            topic=self._features_topic,
            key=updated_state.user_address,
            value=features.model_dump_json(),
        )
        logger.info("Updated state for user=%s", updated_state.user_address)


def _register_signal_handlers(processor: RawEventProcessor, run_task: asyncio.Task[None]) -> None:
    signal_seen = False

    def _handler(signum, frame) -> None:  # type: ignore[no-untyped-def,unused-argument]
        nonlocal signal_seen
        if signal_seen:
            return
        signal_seen = True
        logger.info("Received signal %s, requesting shutdown.", signum)
        processor.request_shutdown()
        run_task.cancel()

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


async def main() -> None:
    processor = RawEventProcessor(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_topic=os.getenv("AAVE_RAW_EVENTS_TOPIC", "aave_raw_events"),
        features_topic=os.getenv("FEATURES_TOPIC", "defi_features"),
        kafka_group_id=os.getenv("RAW_EVENT_CONSUMER_GROUP_ID", "aave-raw-state-processor-v1"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )

    run_task = asyncio.create_task(processor.run())
    _register_signal_handlers(processor, run_task)

    try:
        await run_task
    except asyncio.CancelledError:
        logger.info("Main processing task cancelled.")
    finally:
        try:
            await asyncio.wait_for(processor.shutdown(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Processing shutdown exceeded 5s, forcing exit.")
            sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
