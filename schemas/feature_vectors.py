from pydantic import BaseModel, ConfigDict, Field


class RiskFeatureVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_address: str = Field(min_length=1)
    current_health_factor: float = Field(ge=0.0)
    debt_to_collateral_ratio: float = Field(ge=0.0)
    recent_borrow_count: int = Field(ge=0, description="Borrow events observed over the last hour.")
    timestamp: int = Field(ge=0, description="Unix timestamp in seconds.")
