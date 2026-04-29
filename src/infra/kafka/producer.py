import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from confluent_kafka import Producer


logger = logging.getLogger(__name__)


class AsyncKafkaProducer:
    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self._producer = Producer(dict(config))
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def produce(self, topic: str, value: str, key: str | None = None) -> None:
        if self._closed:
            raise RuntimeError("Producer is closed.")
        if self._poll_task is None:
            await self.start()

        loop = asyncio.get_running_loop()
        delivery_future: asyncio.Future[None] = loop.create_future()

        def delivery_report(err, msg) -> None:  # type: ignore[no-untyped-def]
            if delivery_future.done():
                return
            if err is not None:
                logger.error("Delivery failed for topic=%s: %s", topic, err)
                loop.call_soon_threadsafe(delivery_future.set_exception, RuntimeError(str(err)))
                return
            logger.debug(
                "Delivered message topic=%s partition=%s offset=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )
            loop.call_soon_threadsafe(delivery_future.set_result, None)

        await asyncio.to_thread(
            self._producer.produce,
            topic,
            value=value,
            key=key,
            on_delivery=delivery_report,
        )
        await delivery_future

    async def close(self, flush_timeout_seconds: float = 2.0) -> None:
        self._closed = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._producer.flush, flush_timeout_seconds),
                timeout=flush_timeout_seconds + 0.5,
            )
        except asyncio.TimeoutError:
            logger.error("Kafka producer flush timed out after %.2fs.", flush_timeout_seconds)

    async def _poll_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.to_thread(self._producer.poll, 0.5)
                await asyncio.sleep(self._poll_interval_seconds)
        except asyncio.CancelledError:
            raise
