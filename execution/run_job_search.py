
"""
Directive / Orchestrator Script for the Upwork Job Scraper.
Only handles the scraping of data and saving it to CSV.
"""

import argparse
import asyncio
import os
import sys

from logger import Logger

# Ensure execution directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import scrape_upwork

# Setup Logging
logger = Logger(level="DEBUG").get_logger()

async def run_directive(search_params_input: str, browser_type: str = 'camoufox', headless: bool = True, max_workers: int = 5, limit: int = 50):
    logger.info("🚀 Starting Job Search Scraping...")

    try:
        # Check if search params input file exists if it's a path
        if os.path.isfile(search_params_input) and not os.path.exists(search_params_input):
             logger.error(f"Search params file not found: {search_params_input}")
             return

        # Execute existing scraper workflow
        await scrape_upwork.run_workflow(
            search_params_input=search_params_input,
            browser_type=browser_type,
            headless=headless,
            max_workers=max_workers,
            limit=limit
        )
    except Exception as e:
        logger.error(f"❌ Scraping process failed: {e}")
        return

    logger.info("✅ Job Search Scraping Complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Upwork Job Scraper")
    parser.add_argument("--search_params", type=str, default="execution/data/inputs/default_upwork_search.json", help="Path to search params")
    parser.add_argument('--browser', type=str, default='camoufox', choices=['selenium', 'camoufox', 'uc', 'cf'], 
                        help='Browser to use (default: camoufox)')
    parser.add_argument('--no-headless', action='store_true', help='Run browser visible')
    parser.add_argument('--max_workers', type=int, default=5, help='Worker threads')
    parser.add_argument('--limit', type=int, default=10, help='Max jobs to scrape')

    args = parser.parse_args()

    asyncio.run(run_directive(
        search_params_input=args.search_params,
        browser_type=args.browser,
        headless=not args.no_headless,
        max_workers=args.max_workers,
        limit=args.limit
    ))

