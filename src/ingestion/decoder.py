import logging
import time
from typing import Any

from pydantic import ValidationError
from web3 import Web3
from web3._utils.events import event_abi_to_log_topic, get_event_data

from schemas.raw_events import AaveRawEvent, AaveEventType
from src.infra.web3.abi_registry import AAVE_V3_POOL_EVENT_ABIS


logger = logging.getLogger(__name__)

_WEB3 = Web3()


def _event_topic_hex(abi: dict) -> str:
    """Canonical 0x-prefixed topic0 for JSON-RPC (eth_subscribe) and log decoding."""
    return Web3.to_hex(event_abi_to_log_topic(abi)).lower()


_EVENT_ABI_BY_TOPIC = {_event_topic_hex(abi): abi for abi in AAVE_V3_POOL_EVENT_ABIS}


def supported_topic_signatures() -> list[str]:
    """Topic0 hashes with strict 0x prefix (required by Alchemy / eth_subscribe)."""
    return list(_EVENT_ABI_BY_TOPIC.keys())


def _normalize_tx_hash(value: Any) -> str:
    """Alchemy returns hex strings; web3 may return HexBytes."""
    if isinstance(value, str):
        return value
    if hasattr(value, "hex") and callable(value.hex):
        return Web3.to_hex(value)
    return str(value)


def _normalize_block_number(value: Any) -> int:
    """JSON-RPC logs use hex strings; decoded structs may use int or bytes."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.startswith("0x") or value.startswith("0X"):
            return Web3.to_int(hexstr=value)
        return int(value)
    return Web3.to_int(primitive=value)


def decode_aave_raw_event(message: dict[str, Any]) -> AaveRawEvent | None:
    """
    Decode a websocket payload into an AaveRawEvent.
    Returns None when payload is not a decodable/valid Aave event.
    """
    try:
        log = message.get("params", {}).get("result", {})
        topics = log.get("topics", [])
        if not topics:
            logger.debug("Skipping websocket message without log topics: %s", message)
            return None

        topic0_raw = topics[0]
        if isinstance(topic0_raw, str):
            topic0 = topic0_raw.lower()
            if not topic0.startswith("0x"):
                topic0 = f"0x{topic0}"
        else:
            topic0 = Web3.to_hex(topic0_raw).lower()

        abi = _EVENT_ABI_BY_TOPIC.get(topic0)
        if abi is None:
            logger.debug("Unsupported topic signature topic0=%s raw_log=%s", topic0, log)
            return None

        decoded = get_event_data(_WEB3.codec, abi, log)
        args = decoded.get("args", {})
        event_name = decoded.get("event")
        event_type = AaveEventType(event_name)

        amount_field_by_event = {
            AaveEventType.BORROW: "amount",
            AaveEventType.REPAY: "amount",
            AaveEventType.SUPPLY: "amount",
            AaveEventType.WITHDRAW: "amount",
            AaveEventType.LIQUIDATION_CALL: "debtToCover",
        }
        reserve_field_by_event = {
            AaveEventType.BORROW: "reserve",
            AaveEventType.REPAY: "reserve",
            AaveEventType.SUPPLY: "reserve",
            AaveEventType.WITHDRAW: "reserve",
            AaveEventType.LIQUIDATION_CALL: "debtAsset",
        }

        raw_timestamp = log.get("timestamp", int(time.time()))
        if isinstance(raw_timestamp, str) and raw_timestamp.startswith("0x"):
            timestamp = int(raw_timestamp, 16)
        else:
            timestamp = int(raw_timestamp)

        user_address = args.get("user") or args.get("onBehalfOf")
        reserve_asset = args[reserve_field_by_event[event_type]]
        amount = args[amount_field_by_event[event_type]]

        return AaveRawEvent(
            transaction_hash=_normalize_tx_hash(decoded["transactionHash"]),
            block_number=_normalize_block_number(decoded["blockNumber"]),
            timestamp=timestamp,
            event_type=event_type,
            user_address=Web3.to_checksum_address(user_address),
            reserve_asset=Web3.to_checksum_address(reserve_asset),
            amount=amount,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        logger.error("Failed to decode/validate Aave log: %s | raw_log=%s", exc, log, exc_info=True)
        return None
    except Exception as exc:  # pragma: no cover
        logger.error("Unexpected decoder failure: %s | raw_log=%s", exc, log, exc_info=True)
        return None
