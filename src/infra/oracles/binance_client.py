from __future__ import annotations

import logging

import aiohttp
from redis.asyncio import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"


class BinancePriceClient:
    """
    Spot USDT prices from Binance public API, cached in Redis (EX=60).
    `symbol` is the Binance *base* asset (e.g. MATIC, ETH, USDC); the pair queried is {symbol}USDT.
    """

    def __init__(self, redis: Redis, *, request_timeout_seconds: float = 10.0) -> None:
        self._redis = redis
        self._request_timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._request_timeout)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def get_price_usd(self, symbol: str) -> float:
        # --- SHORT-CIRCUIT STABLECOIN ---
        STABLECOINS = {"USDC", "USDT", "DAI", "FDUSD"}
        if symbol in STABLECOINS:
            return 1.0
        # -----------------------------------
        base = symbol.strip().upper()
        if not base:
            return 0.0

        cache_key = f"price:{base}"
        try:
            cached = await self._redis.get(cache_key)
            if cached is not None:
                return float(cached)
        except (RedisError, TypeError, ValueError) as exc:
            logger.warning("Redis cache read failed for %s: %s", cache_key, exc)

        pair = f"{base}USDT"
        url = f"{BINANCE_TICKER_URL}?symbol={pair}"
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.warning("Binance HTTP %s for %s: %s", response.status, pair, body[:200])
                    return 0.0
                data = await response.json()
            price = float(data["price"])
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Binance price fetch failed for %s: %s", pair, exc)
            return 0.0

        try:
            await self._redis.set(cache_key, str(price), ex=60)
        except RedisError as exc:
            logger.warning("Redis cache write failed for %s: %s", cache_key, exc)

        return price
