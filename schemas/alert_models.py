from pydantic import BaseModel, ConfigDict, Field


class LiquidationAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_address: str = Field(min_length=1)
    predicted_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    timestamp: int = Field(ge=0, description="Unix timestamp in seconds.")
