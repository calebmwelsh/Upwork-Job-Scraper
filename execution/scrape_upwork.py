"""
Execution script to scrape Upwork jobs and save to CSV.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
from typing import Any, Dict, List

# Add parent directory to sys.path for execution package imports
execution_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(execution_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from dotenv import load_dotenv

# Import existing scraper logic
try:
    from logger import Logger
    from upwork_core import main as scrape_main
except ImportError:
    from execution.logger import Logger
    from execution.upwork_core import main as scrape_main

# Load environment variables from .env directory
parent_dir = os.path.dirname(execution_dir)
env_dir = os.path.join(parent_dir, '.env')
load_dotenv(os.path.join(env_dir, '.env'))

# Setup Logging
logger = Logger(level="DEBUG").get_logger()

async def run_workflow(search_params_input: str, browser_type: str = 'camoufox', headless: bool = True, max_workers: int = 5, limit: int = 50):
    """
    Main workflow execution function.
    """
    try:
        # Check if input is a file path
        logger.info(f"Input: {search_params_input}")
        if os.path.isfile(search_params_input):
            logger.info(f"Reading search parameters from file: {search_params_input}")
            with open(search_params_input, 'r') as f:
                search_params = json.load(f)
        else:
            search_params = json.loads(search_params_input)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        return []

    # 1. Scrape Upwork
    logger.info("Step 1: Scraping Upwork...")
    
    username = os.environ.get("UPWORK_USERNAME")
    password = os.environ.get("UPWORK_PASSWORD")
    
    if not username or not password:
        logger.error("UPWORK_USERNAME and UPWORK_PASSWORD must be set in .env")
        return []

    # Override limit if provided in CLI
    if limit:
        search_params['limit'] = limit

    input_data = {
        "credentials": {
            "username": username,
            "password": password
        },
        "search": search_params,
        "general": {
            "save_csv": True, # Always save CSV in this refactored version
            "browser_type": browser_type,
            "headless": headless,
            "max_workers": max_workers
        }
    }
    
    # Run the scraper
    try:
        jobs = await scrape_main(input_data)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return []

    if not jobs:
        logger.warning("No jobs found.")
        return []

    logger.info(f"Scraping Complete. Found {len(jobs)} jobs.")
    
    # Identify the latest CSV created by the scraper
    execution_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(execution_dir, 'data', 'outputs', 'jobs', 'csv')
    if os.path.exists(data_dir):
        files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.csv')]
        if files:
            latest_file = max(files, key=os.path.getctime)
            logger.info(f"✅ Jobs saved to CSV: {latest_file}")
    
    return jobs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Upwork and save to CSV")
    parser.add_argument("--search_params", type=str, default="execution/data/inputs/default_upwork_search.json", help="JSON string or path to JSON file of search parameters")
    parser.add_argument('--browser', type=str, default='camoufox', choices=['selenium', 'camoufox', 'uc', 'cf'], 
                        help='Browser to use: camoufox (default) or selenium')
    parser.add_argument('--no-headless', action='store_true', help='Run browser in headful mode (visible). Default is headless.')
    parser.add_argument('--max_workers', type=int, default=5, help='Max workers for threaded requests')
    parser.add_argument('--limit', type=int, default=10, help='Max jobs to scrape')
    
    args = parser.parse_args()
    
    asyncio.run(run_workflow(
        args.search_params, 
        args.browser, 
        headless=not args.no_headless, 
        max_workers=args.max_workers,
        limit=args.limit
    ))
