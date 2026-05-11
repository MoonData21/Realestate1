from __future__ import annotations

NON_DISCLOSURE_STATES = {
    "AK", "AZ", "ID", "KS", "LA", "ME", "MA",
    "MI", "MS", "MO", "MT", "NM", "ND", "TX", "WY"
}


def is_non_disclosure_state(address: str) -> bool:
    address_upper = address.upper()
    return any(
        f" {state}" in address_upper or f", {state}" in address_upper
        for state in NON_DISCLOSURE_STATES
    )
