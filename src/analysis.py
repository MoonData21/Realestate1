"""Comp analysis: deduplication, filtering, and summary statistics."""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from .constants import NON_DISCLOSURE_STATES, is_non_disclosure_state

logger = logging.getLogger(__name__)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalize_address(addr: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", addr.lower()).strip()


def _deduplicate(comps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicates across sources. Prefer Zillow entries."""
    seen: dict[str, dict[str, Any]] = {}
    for comp in comps:
        key = _normalize_address(comp.get("address", ""))
        if key not in seen or comp["source"] == "zillow":
            seen[key] = comp
    return list(seen.values())


def _get_state_name(address: str) -> str | None:
    address_upper = address.upper()
    for state in NON_DISCLOSURE_STATES:
        if f" {state}" in address_upper or f", {state}" in address_upper:
            return state
    return None


def filter_comps(
    comps: list[dict[str, Any]],
    subject_lat: float | None,
    subject_lon: float | None,
    radius_miles: float,
    beds: int | None,
    baths: float | None,
    subject_sqft: int | None,
    sqft_tolerance_pct: float,
) -> list[dict[str, Any]]:
    """Filter comps by proximity, bed/bath match, and sqft tolerance."""
    filtered = []

    for comp in comps:
        if subject_lat and subject_lon and comp.get("lat") and comp.get("lon"):
            dist = haversine_miles(subject_lat, subject_lon, comp["lat"], comp["lon"])
            if dist > radius_miles:
                continue

        if beds is not None and comp.get("beds") is not None:
            if abs(int(comp["beds"]) - beds) > 1:
                continue

        if baths is not None and comp.get("baths") is not None:
            if abs(float(comp["baths"]) - baths) > 1:
                continue

        if subject_sqft and comp.get("sqft") and comp["sqft"] > 0:
            pct_diff = abs(comp["sqft"] - subject_sqft) / subject_sqft
            if pct_diff > (sqft_tolerance_pct / 100):
                continue

        if not comp.get("price") or comp["price"] <= 0:
            continue

        filtered.append(comp)

    return filtered


def analyze_comps(
    comps: list[dict[str, Any]],
    address: str = "",
) -> dict[str, Any]:
    """Return summary statistics for a filtered, deduped list of comps."""
    comps = _deduplicate(comps)
    non_disclosure = is_non_disclosure_state(address) if address else any(
        c.get("non_disclosure_state") for c in comps
    )

    if not comps:
        result: dict[str, Any] = {
            "comp_count": 0,
            "message": "No comps found matching the criteria. Try widening radius, sqft tolerance, or bed/bath filters.",
        }
        if non_disclosure:
            state = _get_state_name(address)
            result["non_disclosure_warning"] = (
                f"{state or 'This'} is a non-disclosure state. Sold prices are not public record "
                f"so results may be limited. Pending and list prices have been included as proxies."
            )
        return result

    price_type_counts: dict[str, int] = {}
    for comp in comps:
        pt = comp.get("price_type", "sold")
        price_type_counts[pt] = price_type_counts.get(pt, 0) + 1

    prices = [c["price"] for c in comps if c.get("price")]
    sqft_prices = [
        c["price"] / c["sqft"]
        for c in comps
        if c.get("price") and c.get("sqft") and c["sqft"] > 0
    ]
    dom_values = [c["days_on_market"] for c in comps if c.get("days_on_market") is not None]

    prices.sort()
    avg_price = int(sum(prices) / len(prices))
    mid = len(prices) // 2
    median_price = (prices[mid - 1] + prices[mid]) // 2 if len(prices) % 2 == 0 else prices[mid]
    low_price = prices[len(prices) // 4]
    high_price = prices[(3 * len(prices)) // 4]

    avg_ppsf = round(sum(sqft_prices) / len(sqft_prices), 2) if sqft_prices else None
    avg_dom = round(sum(dom_values) / len(dom_values), 1) if dom_values else None

    sorted_comps = sorted(
        comps,
        key=lambda x: x.get("sold_date") or "",
        reverse=True,
    )

    warnings = []
    if non_disclosure:
        state = _get_state_name(address)
        warnings.append(
            f"{state or 'This'} is a non-disclosure state. Sold prices are not public record. "
            f"Results may include pending and list prices as proxies."
        )
    if price_type_counts.get("pending", 0) > 0:
        warnings.append(
            f"{price_type_counts['pending']} pending listing(s) included. "
            f"Pending prices are asking prices — final sale price typically differs by ±3-5%."
        )
    if price_type_counts.get("list", 0) > 0:
        warnings.append(
            f"{price_type_counts['list']} list price(s) included due to unavailable sold data."
        )

    return {
        "comp_count": len(comps),
        "warnings": warnings,
        "summary": {
            "suggested_value_range": {
                "low": f"${low_price:,}",
                "high": f"${high_price:,}",
            },
            "avg_sale_price": f"${avg_price:,}",
            "median_sale_price": f"${median_price:,}",
            "avg_price_per_sqft": f"${avg_ppsf:,.2f}" if avg_ppsf else "N/A",
            "avg_days_on_market": avg_dom,
            "sources": list({c["source"] for c in comps}),
            "price_type_breakdown": {
                "sold": price_type_counts.get("sold", 0),
                "pending": price_type_counts.get("pending", 0),
                "list": price_type_counts.get("list", 0),
            },
        },
        "comps": [
            {
                "address": c.get("address"),
                "source": c.get("source"),
                "price": f"${c['price']:,}" if c.get("price") else None,
                "price_type": c.get("price_type", "sold"),
                "beds": c.get("beds"),
                "baths": c.get("baths"),
                "sqft": f"{c['sqft']:,}" if c.get("sqft") else None,
                "price_per_sqft": (
                    f"${c['price'] / c['sqft']:,.2f}"
                    if c.get("price") and c.get("sqft") and c["sqft"] > 0
                    else None
                ),
                "sold_date": c.get("sold_date"),
                "days_on_market": c.get("days_on_market"),
                "year_built": c.get("year_built"),
                "property_type": c.get("property_type"),
                "url": c.get("url"),
            }
            for c in sorted_comps
        ],
    }
