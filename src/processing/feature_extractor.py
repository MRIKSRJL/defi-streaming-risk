from schemas.feature_vectors import RiskFeatureVector
from schemas.state_models import UserProtocolState


def extract_features(state: UserProtocolState) -> RiskFeatureVector:
    debt_to_collateral_ratio = 0.0
    if state.total_collateral_usd > 0.0:
        debt_to_collateral_ratio = state.total_debt_usd / state.total_collateral_usd

    return RiskFeatureVector(
        user_address=state.user_address,
        current_health_factor=state.health_factor,
        debt_to_collateral_ratio=debt_to_collateral_ratio,
        recent_borrow_count=0,
        timestamp=state.last_updated_timestamp,
    )
