"""
Real Estate Comp Puller — Apify MCP Server
Runs in Apify Standby mode and exposes an MCP tool: get_comps
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from apify import Actor
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from .analysis import analyze_comps, filter_comps
from .redfin import fetch_redfin_comps
from .zillow import fetch_zillow_comps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Tool definitions
# ---------------------------------------------------------------------------

GET_COMPS_TOOL = Tool(
    name="get_comps",
    description=(
        "Pull recently-sold comparable properties (comps) from Zillow and Redfin "
        "for a given address. Returns a summary analysis (suggested value range, "
        "avg $/sqft, median sale price, avg days on market) plus a list of "
        "supporting sold comps. Perfect for homeowners and buyers estimating "
        "a property's fair market value."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Full street address of the subject property, e.g. '123 Main St, Austin, TX 78701'",
            },
            "beds": {
                "type": "integer",
                "description": "Number of bedrooms of the subject property (used to filter comps ±1 bed). Optional.",
            },
            "baths": {
                "type": "number",
                "description": "Number of bathrooms of the subject property (used to filter comps ±1 bath). Optional.",
            },
            "sqft": {
                "type": "integer",
                "description": "Square footage of the subject property. Used to filter comps within sqft_tolerance_pct. Optional.",
            },
            "sqft_tolerance_pct": {
                "type": "number",
                "description": "Percentage tolerance for sqft matching. Default: 20 (±20%).",
                "default": 20,
            },
            "radius_miles": {
                "type": "number",
                "description": "Search radius in miles. Default: 0.5.",
                "default": 0.5,
            },
            "max_results_per_source": {
                "type": "integer",
                "description": "Max comps to fetch per source (Zillow + Redfin). Default: 25.",
                "default": 25,
            },
        },
        "required": ["address"],
    },
)


# ---------------------------------------------------------------------------
# Address validation guard
# ---------------------------------------------------------------------------

def _validate_address(address: str) -> bool:
    """
    Lightweight address guard — checks for minimum structure before
    spinning up Apify actors. Not a full geocode, just catches obvious
    bad inputs like empty strings, single words, or non-US addresses.
    """
    if not address or len(address.strip()) < 10:
        return False

    # Must contain a number (street number)
    if not any(c.isdigit() for c in address):
        return False

    # Must contain a comma (separates street from city/state)
    if "," not in address:
        return False

    # Must contain a US state abbreviation
    us_states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
    }
    address_upper = address.upper()
    has_state = any(
        f" {state}" in address_upper or f",{state}" in address_upper
        for state in us_states
    )
    if not has_state:
        return False

    return True


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp_server = Server("real-estate-comp-puller")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [GET_COMPS_TOOL]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "get_comps":
        raise ValueError(f"Unknown tool: {name}")

    address: str = arguments["address"]
    beds: int | None = arguments.get("beds")
    baths: float | None = arguments.get("baths")
    sqft: int | None = arguments.get("sqft")
    sqft_tolerance_pct: float = float(arguments.get("sqft_tolerance_pct", 20))
    radius_miles: float = float(arguments.get("radius_miles", 0.5))
    max_results: int = int(arguments.get("max_results_per_source", 25))

    logger.info("get_comps called for address: %s", address)

    # --- Lightweight address guard ---
    if not _validate_address(address):
        return [TextContent(type="text", text=json.dumps({
            "comp_count": 0,
            "error": "Invalid or incomplete address. Please provide a full US street address, e.g. '123 Main St, Austin, TX 78701'.",
        }, indent=2))]

    # --- Fetch from both sources concurrently ---
    zillow_comps, redfin_comps = await asyncio.gather(
        asyncio.to_thread(fetch_zillow_comps, address, radius_miles, beds, baths, max_results),
        asyncio.to_thread(fetch_redfin_comps, address, radius_miles, beds, baths, max_results),
    )
    all_comps = zillow_comps + redfin_comps

    logger.info(
        "Raw comps — Zillow: %d, Redfin: %d, Total: %d",
        len(zillow_comps),
        len(redfin_comps),
        len(all_comps),
    )

    # --- Filter ---
    filtered = filter_comps(
        comps=all_comps,
        subject_lat=None,
        subject_lon=None,
        radius_miles=radius_miles,
        beds=beds,
        baths=baths,
        subject_sqft=sqft,
        sqft_tolerance_pct=sqft_tolerance_pct,
    )

    # --- Analyze ---
    result = analyze_comps(filtered, address=address)

    # --- Charge PPE event ---
    if result.get("comp_count", 0) > 0:
        try:
            await Actor.charge(event_name="comp-report-generated", count=1)
            logger.info("PPE charged: comp-report-generated ($0.90)")
        except Exception as exc:
            logger.warning("PPE charge failed (non-fatal): %s", exc)
    else:
        try:
            await Actor.charge(event_name="comp-report-no-results", count=1)
            logger.info("PPE charged: comp-report-no-results ($0.10)")
        except Exception as exc:
            logger.warning("PPE charge failed (non-fatal): %s", exc)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Starlette app — wraps MCP over Streamable HTTP
# ---------------------------------------------------------------------------

session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    event_store=None,
    json_response=False,
    stateless=False,
)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        yield


async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


async def handle_health(request: Request) -> Response:
    """Readiness probe for Apify standby mode."""
    if "x-apify-container-server-readiness-probe" in request.headers:
        return Response("ok", status_code=200)
    return JSONResponse({"status": "ok", "server": "real-estate-comp-puller"})


async def handle_analyze(request: Request) -> JSONResponse:
    """REST endpoint — same logic as the get_comps MCP tool."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    address: str | None = body.get("address")
    if not address or not isinstance(address, str):
        return JSONResponse({"error": "address (string) is required"}, status_code=422)

    beds: int | None = body.get("beds")
    baths: float | None = body.get("baths")
    sqft: int | None = body.get("sqft")
    sqft_tolerance_pct: float = float(body.get("sqft_tolerance_pct", 20))
    radius_miles: float = float(body.get("radius_miles", 0.5))
    max_results: int = int(body.get("max_results_per_source", 25))

    if not _validate_address(address):
        return JSONResponse({
            "comp_count": 0,
            "error": "Invalid or incomplete address. Please provide a full US street address, e.g. '123 Main St, Austin, TX 78701'.",
        }, status_code=422)

    logger.info("analyze called for address: %s", address)

    zillow_comps, redfin_comps = await asyncio.gather(
        asyncio.to_thread(fetch_zillow_comps, address, radius_miles, beds, baths, max_results),
        asyncio.to_thread(fetch_redfin_comps, address, radius_miles, beds, baths, max_results),
    )
    all_comps = zillow_comps + redfin_comps

    filtered = filter_comps(
        comps=all_comps,
        subject_lat=None,
        subject_lon=None,
        radius_miles=radius_miles,
        beds=beds,
        baths=baths,
        subject_sqft=sqft,
        sqft_tolerance_pct=sqft_tolerance_pct,
    )

    result = analyze_comps(filtered, address=address)
    return JSONResponse(result)


async def handle_root(request: Request) -> HTMLResponse:
    """Landing page with MCP connection instructions."""
    actor_url = os.environ.get("ACTOR_STANDBY_URL", "https://YOUR_ACTOR_URL")
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Real Estate Comp Puller — MCP Server</title></head>
    <body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px">
      <h1>🏠 Real Estate Comp Puller</h1>
      <p>MCP server that pulls recently-sold comps from <strong>Zillow</strong> and
      <strong>Redfin</strong> and returns a structured analysis with suggested value
      range, avg $/sqft, and supporting comp list.</p>

      <h2>Connect via MCP</h2>
      <p>Add this to your MCP client config:</p>
      <pre style="background:#f4f4f4;padding:16px;border-radius:6px">{{
  "mcpServers": {{
    "real-estate-comp-puller": {{
      "type": "http",
      "url": "{actor_url}/mcp/",
      "headers": {{
        "Authorization": "Bearer YOUR_APIFY_TOKEN"
      }}
    }}
  }}
}}</pre>

      <h2>Tool: <code>get_comps</code></h2>
      <p>Provide an address plus optional beds/baths/sqft to get a comp report.</p>
      <p><strong>Example prompt:</strong> "Pull comps for 456 Oak Ave, Austin TX 78704, 3 bed 2 bath 1800 sqft"</p>
    </body>
    </html>
    """
    return HTMLResponse(html)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", handle_root),
        Route("/health", handle_health),
        Route("/analyze", handle_analyze, methods=["POST"]),
        Mount("/mcp", app=handle_mcp),
    ]
)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    async with Actor:
        port = int(os.environ.get("ACTOR_STANDBY_PORT", os.environ.get("APIFY_CONTAINER_PORT", os.environ.get("PORT", 3000))))
        logger.info("Starting Real Estate Comp Puller MCP server on port %d", port)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
