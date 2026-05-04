from pydantic import BaseModel, ConfigDict, Field


class UserProtocolState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_address: str = Field(min_length=1)
    total_collateral_usd: float = Field(ge=0.0)
    total_debt_usd: float = Field(ge=0.0)
    health_factor: float = Field(ge=0.0)
    last_updated_timestamp: int = Field(ge=0)
    last_reserve_asset: str | None = Field(
        default=None,
        description="Checksum address of the reserve touched by the latest event (for oracle mapping).",
    )
    last_event_type: str | None = Field(
        default=None,
        description="Aave event name from the latest update (e.g. Borrow, Supply).",
    )
