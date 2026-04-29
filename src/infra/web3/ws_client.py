import asyncio
import logging
import random
from collections.abc import AsyncIterator

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException


logger = logging.getLogger(__name__)


class PolygonWsClient:
    def __init__(
        self,
        ws_url: str,
        *,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        open_timeout: float = 20.0,
        close_timeout: float = 10.0,
        max_backoff_seconds: float = 60.0,
        base_backoff_seconds: float = 1.0,
    ) -> None:
        self.ws_url = ws_url
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.open_timeout = open_timeout
        self.close_timeout = close_timeout
        self.max_backoff_seconds = max_backoff_seconds
        self.base_backoff_seconds = base_backoff_seconds
        self._connection: ClientConnection | None = None

    async def connect_with_retry(self) -> ClientConnection:
        attempt = 0
        while True:
            try:
                logger.info("Connecting to Polygon node via WebSocket.")
                self._connection = await connect(
                    self.ws_url,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    open_timeout=self.open_timeout,
                    close_timeout=self.close_timeout,
                )
                logger.info("WebSocket connection established.")
                return self._connection
            except (OSError, WebSocketException) as exc:
                delay = self._compute_backoff(attempt)
                logger.warning(
                    "WebSocket connection failed (attempt=%s): %s. Retrying in %.2fs.",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def disconnect(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def recv(self) -> str:
        if self._connection is None:
            await self.connect_with_retry()
        assert self._connection is not None
        try:
            return await self._connection.recv()
        except (ConnectionClosed, WebSocketException):
            logger.warning("WebSocket recv failed; reconnecting.")
            await self.connect_with_retry()
            assert self._connection is not None
            return await self._connection.recv()

    async def send(self, payload: str) -> None:
        if self._connection is None:
            await self.connect_with_retry()
        assert self._connection is not None
        try:
            await self._connection.send(payload)
        except (ConnectionClosed, WebSocketException):
            logger.warning("WebSocket send failed; reconnecting and retrying.")
            await self.connect_with_retry()
            assert self._connection is not None
            await self._connection.send(payload)

    async def messages(self) -> AsyncIterator[str]:
        while True:
            try:
                yield await self.recv()
            except Exception as exc:  # pragma: no cover
                logger.exception("Unexpected WebSocket read error: %s", exc)
                await asyncio.sleep(self._compute_backoff(0))

    def _compute_backoff(self, attempt: int) -> float:
        exp_delay = min(self.max_backoff_seconds, self.base_backoff_seconds * (2**attempt))
        jitter = random.uniform(0, exp_delay * 0.2)
        return exp_delay + jitter
