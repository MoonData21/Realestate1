"""Zillow recently-sold and pending comp scraper via Apify Actor."""
from __future__ import annotations

import logging
import os
from typing import Any

from apify_client import ApifyClient

from .constants import is_non_disclosure_state

logger = logging.getLogger(__name__)

ZILLOW_ACTOR_ID = "magicfingers/zillow-scraper"


def _build_zillow_search_url(address: str, listing_type: str = "sold") -> str:
    encoded = address.replace(" ", "-").replace(",", "")
    if listing_type == "pending":
        return f"https://www.zillow.com/homes/{encoded}_rb/?searchQueryState=%7B%22isListedByAgent%22%3Atrue%7D&status_type=Pending"
    return f"https://www.zillow.com/homes/recently_sold/{encoded}_rb/"


def fetch_zillow_comps(
    address: str,
    radius_miles: float,
    beds: int | None,
    baths: float | None,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Call the Apify Zillow scraper and return recently-sold listings."""
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        logger.warning("APIFY_TOKEN not set — Zillow scraper will be skipped.")
        return []

    client = ApifyClient(token)
    non_disclosure = is_non_disclosure_state(address)

    search_urls = [{"url": _build_zillow_search_url(address, "sold")}]
    if non_disclosure:
        logger.info("Non-disclosure state detected — adding pending listings for %s", address)
        search_urls.append({"url": _build_zillow_search_url(address, "pending")})

    run_input: dict[str, Any] = {
        "searchUrls": search_urls,
        "type": "sold",
        "maxItems": max_results,
    }

    logger.info("Running Zillow actor with input: %s", run_input)

    try:
        run = client.actor(ZILLOW_ACTOR_ID).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info("Zillow returned %d items", len(items))
        return [
            _normalize_zillow(item, non_disclosure)
            for item in items
            if item.get("price")
        ]
    except Exception as exc:
        logger.error("Zillow scraper failed: %s", exc)
        return []


def _normalize_zillow(item: dict[str, Any], non_disclosure: bool = False) -> dict[str, Any]:
    """Normalize a Zillow result into a common comp schema."""
    price = item.get("price") or item.get("unformattedPrice") or 0
    sqft = item.get("livingArea") or item.get("sqft") or 0

    status = (item.get("homeStatus") or item.get("statusType") or "").upper()
    if "PENDING" in status:
        price_type = "pending"
    elif non_disclosure:
        price_type = "list"
    else:
        price_type = "sold"

    return {
        "source": "zillow",
        "address": item.get("address", ""),
        "price": int(str(price).replace(",", "").replace("$", "").strip() or 0),
        "price_type": price_type,
        "non_disclosure_state": non_disclosure,
        "beds": item.get("bedrooms") or item.get("beds"),
        "baths": item.get("bathrooms") or item.get("baths"),
        "sqft": int(str(sqft).replace(",", "").strip() or 0),
        "year_built": item.get("yearBuilt"),
        "days_on_market": item.get("daysOnMarket"),
        "sold_date": item.get("dateSold") or item.get("soldDate"),
        "property_type": item.get("homeType") or item.get("propertyType"),
        "zestimate": item.get("zestimate"),
        "url": item.get("url") or item.get("detailUrl"),
        "lat": item.get("latitude") or item.get("lat"),
        "lon": item.get("longitude") or item.get("lon"),
    }
