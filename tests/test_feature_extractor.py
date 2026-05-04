"""Unit tests for async feature extraction with oracle pricing."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from schemas.state_models import UserProtocolState
from src.processing.feature_extractor import extract_features

# Polygon WETH (mapped to Binance "ETH" in token_map.py)
WETH_POLYGON = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"


@pytest.fixture
def mock_binance_client() -> AsyncMock:
    """ETH @ 2000 USD, USDC @ 1 USD (per test spec)."""

    async def get_price_usd(symbol: str) -> float:
        if symbol == "ETH":
            return 2000.0
        if symbol == "USDC":
            return 1.0
        return 0.0

    client = AsyncMock()
    client.get_price_usd = AsyncMock(side_effect=get_price_usd)
    return client


@pytest.mark.asyncio
async def test_extract_features_supply_weth_health_factor_and_usd(
    mock_binance_client: AsyncMock,
) -> None:
    """
    Supply + WETH reserve -> collateral leg priced as ETH, debt leg proxy as USDC.

    Raw totals (wei-style): 2e18 collateral units, 1000e6 debt units (USDC decimals).
    Expected: collateral_usd = 2 * 2000 = 4000, debt_usd = 1000 * 1 = 1000 -> HF = 4.0, D/C = 0.25.
    """
    state = UserProtocolState(
        user_address="0x0000000000000000000000000000000000000abc",
        total_collateral_usd=2.0 * (10**18),
        total_debt_usd=1000.0 * (10**6),
        health_factor=1.0,
        last_updated_timestamp=1_700_000_000,
        last_reserve_asset=WETH_POLYGON,
        last_event_type="Supply",
    )

    fv = await extract_features(state, mock_binance_client)

    assert fv.user_address == state.user_address
    assert fv.timestamp == state.last_updated_timestamp
    assert fv.recent_borrow_count == 0
    assert fv.current_health_factor == pytest.approx(4.0)
    assert fv.debt_to_collateral_ratio == pytest.approx(0.25)

    mock_binance_client.get_price_usd.assert_awaited()
    calls = [c.args[0] for c in mock_binance_client.get_price_usd.await_args_list]
    assert "ETH" in calls
    assert "USDC" in calls
