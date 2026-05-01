def get_user_state_key(user_address: str) -> str:
    normalized = user_address.strip().lower()
    return f"defi_risk:state:aave:{normalized}"
