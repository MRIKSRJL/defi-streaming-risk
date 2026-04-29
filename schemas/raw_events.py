from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AaveEventType(str, Enum):
    BORROW = "Borrow"
    REPAY = "Repay"
    SUPPLY = "Supply"
    WITHDRAW = "Withdraw"
    LIQUIDATION_CALL = "LiquidationCall"


class AaveRawEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_hash: str = Field(min_length=1)
    block_number: int = Field(ge=0)
    timestamp: int = Field(ge=0, description="Unix timestamp in seconds.")
    event_type: AaveEventType
    user_address: str = Field(min_length=1)
    reserve_asset: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
