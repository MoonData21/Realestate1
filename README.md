# Real Estate Comp Puller — MCP Server

Pulls recently-sold comparable properties from **Zillow** and **Redfin** for any US address, deduplicates them, and returns a structured analysis: suggested value range, avg $/sqft, median sale price, avg days on market, and a full comp list.

---

## Connect via MCP

Add to your MCP client config (e.g. Claude Desktop `settings.json`):

```json
{
  "mcpServers": {
    "real-estate-comp-puller": {
      "type": "http",
      "url": "https://YOUR_USERNAME--real-estate-comp-puller.apify.actor/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

Replace `YOUR_USERNAME` with your Apify username and `YOUR_APIFY_TOKEN` with your Apify API token.

---

## Tool: `get_comps`

**Required:** `address` — full US street address, e.g. `"123 Main St, Austin, TX 78701"`

**Optional:** `beds`, `baths`, `sqft`, `radius_miles` (default 0.5), `sqft_tolerance_pct` (default 20), `max_results_per_source` (default 25)

**Example prompt:**
> "Pull comps for 456 Oak Ave, Austin TX 78704 — 3 bed, 2 bath, 1800 sqft"

If no comps are found at the requested radius, the search automatically expands to 2 mi then 5 mi.
