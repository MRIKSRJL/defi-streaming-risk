from pydantic import BaseModel, ConfigDict, Field


class UserProtocolState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_address: str = Field(min_length=1)
    total_collateral_usd: float = Field(ge=0.0)
    total_debt_usd: float = Field(ge=0.0)
    health_factor: float = Field(ge=0.0)
    last_updated_timestamp: int = Field(ge=0)
