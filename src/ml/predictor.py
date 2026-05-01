from schemas.alert_models import LiquidationAlert
from schemas.feature_vectors import RiskFeatureVector


class RiskPredictor:
    def __init__(self) -> None:
        # TODO: Replace heuristic with loaded XGBoost model + feature pipeline.
        pass

    def predict(self, feature_vector: RiskFeatureVector) -> LiquidationAlert:
        hf = feature_vector.current_health_factor

        if hf < 1.05:
            risk_level = "CRITICAL"
            probability = 0.95
        elif hf < 1.15:
            risk_level = "HIGH"
            probability = 0.82
        elif hf < 1.30:
            risk_level = "MEDIUM"
            probability = 0.45
        else:
            risk_level = "LOW"
            probability = 0.10

        return LiquidationAlert(
            user_address=feature_vector.user_address,
            predicted_probability=probability,
            risk_level=risk_level,
            timestamp=feature_vector.timestamp,
        )
