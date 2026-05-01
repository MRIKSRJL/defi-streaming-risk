from __future__ import annotations

from pathlib import Path

import pandas as pd
import xgboost as xgb

from schemas.alert_models import LiquidationAlert
from schemas.feature_vectors import RiskFeatureVector

# Must match training notebook column order.
FEATURE_ORDER = [
    "current_health_factor",
    "debt_to_collateral_ratio",
    "recent_borrow_count",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_model_path() -> Path:
    return _project_root() / "models" / "xgboost_risk_model.json"


def _risk_level_from_probability(probability: float) -> str:
    if probability > 0.8:
        return "CRITICAL"
    if probability > 0.5:
        return "HIGH"
    if probability > 0.2:
        return "MEDIUM"
    return "LOW"


class RiskPredictor:
    def __init__(self, model_path: Path | None = None) -> None:
        path = model_path or _default_model_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"XGBoost model not found at {path}. Train with notebooks/01_train_xgboost.ipynb first."
            )
        self._model = xgb.XGBClassifier()
        self._model.load_model(str(path.resolve()))

    def predict(self, feature_vector: RiskFeatureVector) -> LiquidationAlert:
        row = {
            "current_health_factor": feature_vector.current_health_factor,
            "debt_to_collateral_ratio": feature_vector.debt_to_collateral_ratio,
            "recent_borrow_count": feature_vector.recent_borrow_count,
        }
        X = pd.DataFrame([row], columns=FEATURE_ORDER)
        proba = self._model.predict_proba(X)[0, 1]
        risk_level = _risk_level_from_probability(float(proba))

        return LiquidationAlert(
            user_address=feature_vector.user_address,
            predicted_probability=float(proba),
            risk_level=risk_level,
            timestamp=feature_vector.timestamp,
        )
