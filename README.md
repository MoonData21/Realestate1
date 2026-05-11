# 🏠 Real Estate Comp Puller — Apify MCP Server

An MCP (Model Context Protocol) server that pulls recently-sold comparable properties from **Zillow** and **Redfin** for any US address, deduplicates them, and returns a structured analysis with a suggested value range, avg $/sqft, and supporting comp list.

Built for homeowners and buyers who want a quick, AI-accessible answer to: *"What's this property worth?"*

---

## What it does

Given an address (plus optional beds/baths/sqft), the `get_comps` tool:

1. Fetches recently-sold listings from Zillow and Redfin via Apify scrapers
2. Deduplicates results across sources
3. Filters by bed/bath match (±1) and sqft tolerance (default ±20%)
4. Returns:
   - **Suggested value range** (±5% of avg comp price)
   - **Avg & median sale price**
   - **Avg price per sqft**
   - **Avg days on market**
   - **Full comp list** sorted by sold date

---

## Project structure

```
real-estate-comp-puller/
├── .actor/
│   ├── actor.json          # Apify Actor config (standby mode, MCP path)
│   ├── Dockerfile          # Container build
│   └── pay_per_event.json  # PPE pricing ($0.25/report)
├── src/
│   ├── __init__.py
│   ├── __main__.py         # Entrypoint
│   ├── main.py             # MCP server + Starlette app
│   ├── zillow.py           # Zillow scraper via Apify
│   ├── redfin.py           # Redfin scraper via Apify
│   └── analysis.py         # Dedup, filter, and analysis logic
├── requirements.txt
└── README.md
```

---

## Local development

### 1. Install deps

```bash
pip install -r requirements.txt
```

### 2. Set env vars

```bash
export APIFY_TOKEN=your_apify_token_here
export APIFY_META_ORIGIN=STANDBY
export ACTOR_STANDBY_PORT=3000
```

### 3. Run

```bash
python -m src
```

The MCP server will be available at: `http://localhost:3000/mcp`

---

## Deploy to Apify

### 1. Install Apify CLI

```bash
npm install -g apify-cli
apify login
```

### 2. Push the Actor

```bash
apify push
```

### 3. Enable Standby mode

In Apify Console → your Actor → Settings → enable **Standby mode**.

### 4. Set your APIFY_TOKEN env var

In Apify Console → your Actor → Settings → Environment variables:
- `APIFY_TOKEN` = your token (needed to call Zillow/Redfin sub-actors)

### 5. Connect from Claude or any MCP client

```json
{
  "mcpServers": {
    "real-estate-comp-puller": {
      "type": "http",
      "url": "https://YOUR_USERNAME--real-estate-comp-puller.apify.actor/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_APIFY_TOKEN"
      }
    }
  }
}
```

---

## Monetization

This Actor uses **Pay Per Event (PPE)** pricing at **$0.25 per comp report**.

- Users are charged once per successful `get_comps` call that returns results
- You earn 80% → **~$0.20/report** after Apify's 20% commission
- Platform costs (Zillow + Redfin actor runs, proxies) ~$0.03–0.07/run
- **Net ~$0.13–0.17 per report**

To activate monetization:
1. Go to Apify Console → your Actor → Publication
2. Select **Pay Per Event**
3. The events are pre-configured in `.actor/pay_per_event.json`

---

## Example prompt

> "Pull comps for 456 Oak Ave, Austin TX 78704 — 3 bed, 2 bath, 1800 sqft"

**Example response:**

```json
{
  "comp_count": 7,
  "summary": {
    "suggested_value_range": { "low": "$418,500", "high": "$461,900" },
    "avg_sale_price": "$440,200",
    "median_sale_price": "$435,000",
    "avg_price_per_sqft": "$241.50",
    "avg_days_on_market": 18.3,
    "sources": ["zillow", "redfin"]
  },
  "comps": [...]
}
```

---

## Roadmap

- [ ] Geocoding for true radius-based filtering (Google Maps / Nominatim)
- [ ] Realtor.com as a third source
- [ ] Price history trend chart
- [ ] Neighborhood median price trend (90-day, 180-day)
- [ ] Free tier: 1 free report, then PPE kicks in
