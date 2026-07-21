#!/usr/bin/env python
"""CLI tool for ingesting content into the Knowledge Repository.

Currently supports 'firecrawl' for crawling websites.
"""

import argparse
import asyncio
import logging
from pathlib import Path

from app.company_config import company_config
from app.config import settings
from app.utils.logger import logger

async def main():
    parser = argparse.ArgumentParser(description="Ingest content into the knowledge repository.")
    parser.add_argument(
        "--type", 
        type=str, 
        choices=["website"], 
        required=True, 
        help="Type of content to ingest (currently only 'website' via Firecrawl is supported)."
    )
    parser.add_argument(
        "--url", 
        type=str, 
        required=True, 
        help="The URL or source identifier to ingest."
    )
    
    args = parser.parse_args()
    
    # Ensure config is initialized
    company_config.initialize()
    
    base_repo_dir = Path(company_config.knowledge_repository_directory)
    
    if args.type == "website":
        from app.services.knowledge import knowledge_service
        try:
            report = await knowledge_service.trigger_ingestion("website", args.url)
            logger.info("Ingestion & Quality Pipeline completed successfully!")
            logger.info("Metadata Report:")
            for k, v in report.items():
                logger.info(f"  {k}: {v}")
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            raise
    else:
        logger.error(f"Unsupported ingestion type: {args.type}")


if __name__ == "__main__":
    asyncio.run(main())
