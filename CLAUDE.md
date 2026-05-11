# Real Estate Comp Puller — MCP Server

## What this is
An Apify Actor running as an MCP (Model Context Protocol) server in Standby mode.
It exposes a `get_comps` tool that pulls recently-sold comps from Zillow and Redfin,
deduplicates them, and returns a structured analysis with suggested value range, avg $/sqft, etc.

## Stack
- Python 3.11+
- Apify SDK (`apify`, `apify-client`)
- MCP SDK (`mcp`)
- Starlette + Uvicorn (HTTP server)
- Runs on Windows (dev), Linux (Apify platform)

## Known issues / active debugging
- Pydantic version conflicts with apify + crawlee — need pydantic>=2.7.0
- Windows dev environment (path separators, venv activation differs)
- `apify-client` version must not be pinned separately — apify pulls the right version

## Dependencies — current requirements.txt
apify>=2.3.0
mcp~=1.6.0
starlette~=0.41.0
uvicorn~=0.32.0
httpx~=0.27.0
python-dotenv~=1.0.0
pydantic>=2.7.0