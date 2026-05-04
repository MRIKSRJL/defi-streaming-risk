from schemas.raw_events import AaveEventType, AaveRawEvent
from schemas.state_models import UserProtocolState


DEFAULT_HEALTH_FACTOR_NO_DEBT = 999.0


def make_initial_state(user_address: str, timestamp: int) -> UserProtocolState:
    return UserProtocolState(
        user_address=user_address,
        total_collateral_usd=0.0,
        total_debt_usd=0.0,
        health_factor=DEFAULT_HEALTH_FACTOR_NO_DEBT,
        last_updated_timestamp=timestamp,
    )


def update_user_state(event: AaveRawEvent, current_state: UserProtocolState | None) -> UserProtocolState:
    state = current_state or make_initial_state(event.user_address, event.timestamp)
    amount = float(event.amount)

    collateral = state.total_collateral_usd
    debt = state.total_debt_usd

    if event.event_type == AaveEventType.BORROW:
        debt += amount
    elif event.event_type == AaveEventType.REPAY:
        debt = max(0.0, debt - amount)
    elif event.event_type == AaveEventType.SUPPLY:
        collateral += amount
    elif event.event_type == AaveEventType.WITHDRAW:
        collateral = max(0.0, collateral - amount)
    elif event.event_type == AaveEventType.LIQUIDATION_CALL:
        # Liquidation handling can be made richer later with full collateral/debt fields.
        debt = max(0.0, debt - amount)

    health_factor = DEFAULT_HEALTH_FACTOR_NO_DEBT if debt <= 0.0 else collateral / debt

    return UserProtocolState(
        user_address=state.user_address,
        total_collateral_usd=collateral,
        total_debt_usd=debt,
        health_factor=health_factor,
        last_updated_timestamp=event.timestamp,
        last_reserve_asset=event.reserve_asset,
        last_event_type=event.event_type.value,
    )
