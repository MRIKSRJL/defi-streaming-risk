"""
Polygon reserve address -> Binance spot base symbol (paired with USDT on Binance).

Extend this map as you add markets; unknown addresses fall back to MATIC / 18 decimals.
"""

from __future__ import annotations

# Keys are checksummed or lower; we normalize to lower in lookup.
POLYGON_RESERVE_TO_BINANCE_SYMBOL: dict[str, str] = {
    # WMATIC (PoS)
    "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": "MATIC",
    # WETH
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": "ETH",
    # USDC (bridged, common on Aave Polygon v3 deployments)
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC",
    # USDT
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": "USDT",
    # DAI
    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": "DAI",
    # WBTC
    "0x1bfd67037b42cf73acf04a66dfad3f9d421ae41f": "BTC",
}

# Human-readable decimals for converting on-chain uint amounts to float units.
SYMBOL_DECIMALS: dict[str, int] = {
    "MATIC": 18,
    "ETH": 18,
    "DAI": 18,
    "USDC": 6,
    "USDT": 6,
    "BTC": 8,
}


def binance_symbol_for_reserve(reserve_address: str) -> str:
    key = reserve_address.strip().lower()
    return POLYGON_RESERVE_TO_BINANCE_SYMBOL.get(key, "MATIC")


def decimals_for_symbol(symbol: str) -> int:
    return SYMBOL_DECIMALS.get(symbol.upper(), 18)
