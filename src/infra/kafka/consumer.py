import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from confluent_kafka import Consumer, Message


logger = logging.getLogger(__name__)


class AsyncKafkaConsumer:
    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        poll_timeout_seconds: float = 1.0,
    ) -> None:
        self._consumer = Consumer(dict(config))
        self._poll_timeout_seconds = poll_timeout_seconds
        self._closed = False

    def subscribe(self, topics: list[str]) -> None:
        self._consumer.subscribe(topics)

    async def messages(self) -> AsyncIterator[Message]:
        while not self._closed:
            message = await asyncio.to_thread(self._consumer.poll, self._poll_timeout_seconds)
            if message is None:
                continue
            if message.error() is not None:
                logger.error("Kafka consume error: %s", message.error())
                continue
            yield message

    async def close(self) -> None:
        self._closed = True
        await asyncio.to_thread(self._consumer.close)
