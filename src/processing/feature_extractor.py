from __future__ import annotations

import logging

from schemas.feature_vectors import RiskFeatureVector
from schemas.state_models import UserProtocolState
from src.infra.oracles.binance_client import BinancePriceClient
from src.infra.oracles.token_map import binance_symbol_for_reserve, decimals_for_symbol

logger = logging.getLogger(__name__)

DEFAULT_HEALTH_FACTOR_NO_DEBT = 999.0


def _leg_symbols_for_state(state: UserProtocolState) -> tuple[str, str, int, int]:
    """
    Map the latest on-chain action to (collateral_symbol, debt_symbol, coll_decimals, debt_decimals).

    Level-1 heuristic: the touched reserve prices the active leg; the opposite leg uses a liquid
    proxy (MATIC for collateral-weighted USD, USDC for debt-weighted USD) until per-reserve buckets exist.
    """
    reserve = state.last_reserve_asset or ""
    primary = binance_symbol_for_reserve(reserve) if reserve else "MATIC"
    primary_dec = decimals_for_symbol(primary)

    et = state.last_event_type or ""
    if et in ("Supply", "Withdraw"):
        return primary, "USDC", primary_dec, decimals_for_symbol("USDC")
    if et in ("Borrow", "Repay"):
        return "MATIC", primary, decimals_for_symbol("MATIC"), primary_dec
    if et == "LiquidationCall":
        return "MATIC", primary, decimals_for_symbol("MATIC"), primary_dec
    return "MATIC", "USDC", 18, decimals_for_symbol("USDC")


async def extract_features(state: UserProtocolState, price_client: BinancePriceClient) -> RiskFeatureVector:
    collateral_sym, debt_sym, coll_decimals, debt_decimals = _leg_symbols_for_state(state)

    collateral_price = await price_client.get_price_usd(collateral_sym)
    debt_price = await price_client.get_price_usd(debt_sym)

    if collateral_price <= 0.0 or debt_price <= 0.0:
        logger.debug(
            "Missing oracle price (collateral=%s @ %s, debt=%s @ %s); falling back to ratio-only view.",
            collateral_sym,
            collateral_price,
            debt_sym,
            debt_price,
        )

    collateral_human = state.total_collateral_usd / (10**coll_decimals)
    debt_human = state.total_debt_usd / (10**debt_decimals)

    collateral_usd = max(0.0, collateral_human * collateral_price)
    debt_usd = max(0.0, debt_human * debt_price)

    if debt_usd <= 1e-12:
        current_health_factor = DEFAULT_HEALTH_FACTOR_NO_DEBT
        debt_to_collateral_ratio = 0.0
    else:
        current_health_factor = collateral_usd / debt_usd
        debt_to_collateral_ratio = 0.0 if collateral_usd <= 1e-12 else debt_usd / collateral_usd

    return RiskFeatureVector(
        user_address=state.user_address,
        current_health_factor=current_health_factor,
        debt_to_collateral_ratio=debt_to_collateral_ratio,
        recent_borrow_count=0,
        timestamp=state.last_updated_timestamp,
    )
