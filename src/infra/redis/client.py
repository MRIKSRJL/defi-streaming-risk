import asyncio
import logging
from typing import TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


class AsyncRedisStateClient:
    def __init__(
        self,
        redis_url: str,
        *,
        socket_connect_timeout: float = 5.0,
        socket_timeout: float = 5.0,
        health_check_interval: int = 30,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        self._redis_url = redis_url
        self._socket_connect_timeout = socket_connect_timeout
        self._socket_timeout = socket_timeout
        self._health_check_interval = health_check_interval
        self._max_backoff_seconds = max_backoff_seconds
        self._client: Redis | None = None

    async def connect_with_retry(self) -> Redis:
        if self._client is not None:
            try:
                await self._client.ping()
                return self._client
            except RedisError:
                logger.warning("Redis ping failed on existing client; reconnecting.")

        attempt = 0
        while True:
            client = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=self._socket_connect_timeout,
                socket_timeout=self._socket_timeout,
                health_check_interval=self._health_check_interval,
            )
            try:
                await client.ping()
                self._client = client
                logger.info("Redis connection established.")
                return client
            except RedisError as exc:
                await client.aclose()
                delay = min(self._max_backoff_seconds, 2**attempt)
                logger.warning("Redis connection failed (attempt=%s): %s. Retrying in %ss.", attempt + 1, exc, delay)
                await asyncio.sleep(delay)
                attempt += 1

    async def get_state(self, key: str, model_cls: type[ModelT]) -> ModelT | None:
        client = await self.connect_with_retry()
        try:
            raw = await client.get(key)
            if raw is None:
                return None
            return model_cls.model_validate_json(raw)
        except RedisError:
            logger.exception("Redis get_state failed for key=%s", key)
            return None

    async def set_state(self, key: str, model: BaseModel, ttl_seconds: int | None = None) -> None:
        client = await self.connect_with_retry()
        payload = model.model_dump_json()
        try:
            if ttl_seconds is None:
                await client.set(key, payload)
            else:
                await client.set(key, payload, ex=ttl_seconds)
        except RedisError:
            logger.exception("Redis set_state failed for key=%s", key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
