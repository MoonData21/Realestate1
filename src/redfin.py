"""Redfin recently-sold and pending comp scraper via Apify Actor."""
from __future__ import annotations

import logging
import os
from typing import Any

from apify_client import ApifyClient

from .constants import is_non_disclosure_state

logger = logging.getLogger(__name__)

REDFIN_ACTOR_ID = "automation-lab/redfin-scraper"


def _build_redfin_search_url(address: str, listing_type: str = "sold") -> str:
    encoded = address.replace(" ", "+").replace(",", "%2C")
    if listing_type == "pending":
        return f"https://www.redfin.com/city/pending?q={encoded}&status=2"
    return f"https://www.redfin.com/city/sold?q={encoded}&status=9"


def fetch_redfin_comps(
    address: str,
    radius_miles: float,
    beds: int | None,
    baths: float | None,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Call the Apify Redfin scraper and return recently-sold listings."""
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        logger.warning("APIFY_TOKEN not set — Redfin scraper will be skipped.")
        return []

    client = ApifyClient(token)
    non_disclosure = is_non_disclosure_state(address)

    start_urls = [{"url": _build_redfin_search_url(address, "sold")}]
    if non_disclosure:
        logger.info("Non-disclosure state detected — adding pending listings for %s", address)
        start_urls.append({"url": _build_redfin_search_url(address, "pending")})

    run_input: dict[str, Any] = {
        "startUrls": start_urls,
        "maxItems": max_results,
    }

    logger.info("Running Redfin actor with input: %s", run_input)

    try:
        run = client.actor(REDFIN_ACTOR_ID).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info("Redfin returned %d items", len(items))
        return [
            _normalize_redfin(item, non_disclosure)
            for item in items
            if item.get("price")
        ]
    except Exception as exc:
        logger.error("Redfin scraper failed: %s", exc)
        return []


def _normalize_redfin(item: dict[str, Any], non_disclosure: bool = False) -> dict[str, Any]:
    """Normalize a Redfin result into a common comp schema."""
    price = item.get("price") or 0
    sqft = item.get("sqFt") or item.get("sqft") or item.get("livingArea") or 0

    status = (item.get("status") or item.get("listingStatus") or "").upper()
    if "PENDING" in status or "CONTINGENT" in status:
        price_type = "pending"
    elif non_disclosure:
        price_type = "list"
    else:
        price_type = "sold"

    return {
        "source": "redfin",
        "address": item.get("address", ""),
        "price": int(str(price).replace(",", "").replace("$", "").strip() or 0),
        "price_type": price_type,
        "non_disclosure_state": non_disclosure,
        "beds": item.get("beds") or item.get("bedrooms"),
        "baths": item.get("baths") or item.get("bathrooms"),
        "sqft": int(str(sqft).replace(",", "").strip() or 0),
        "year_built": item.get("yearBuilt"),
        "days_on_market": item.get("daysOnMarket"),
        "sold_date": item.get("soldDate") or item.get("lastSoldDate"),
        "property_type": item.get("propertyType"),
        "zestimate": None,
        "url": item.get("url") or item.get("propertyUrl"),
        "lat": item.get("latitude") or item.get("lat"),
        "lon": item.get("longitude") or item.get("lon"),
    }
