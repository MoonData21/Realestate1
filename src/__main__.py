"""Entrypoint for the Apify Actor MCP server."""
import asyncio
import logging

from .main import main

logging.basicConfig(level=logging.INFO)

asyncio.run(main())
