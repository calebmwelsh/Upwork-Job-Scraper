# Scrape Upwork Jobs to CSV

## Goal
Scrape Upwork job listings based on specific search criteria and save the results to a CSV file for review and processing.

## Inputs
- **Search Parameters** (JSON string or file):
  - `query`: Main search term (e.g., "Workflow Automation")
  - `search_any`: Any of these words (OR condition)
  - `category`: List of categories (e.g., ["Web, Mobile & Software Dev"])
  - `projectDuration`: Project length (e.g., ["week", "month"])
  - `hourly`: Boolean for hourly jobs
  - `fixed`: Boolean for fixed-price jobs
  - `hourly_min/max`: Hourly rate range
  - `fixed_min/max`: Fixed price range
  - `limit`: Maximum number of jobs to scrape
  - ...and other standard Upwork filters
- **Default Configuration**: Use `execution/data/inputs/default_upwork_search.json` for standard search parameters.
- **CLI Arguments**:
  - `--limit`: Override the number of jobs to scrape (default: 10).
  - `--browser`: Browser to use (camoufox, selenium).
  - `--no-headless`: Run in headful mode.

## Tools/Scripts
- `execution/scrape_upwork.py` - Orchestrates the scraping and CSV generation.
- `execution/run_job_search.py` - Orchestrator script to run the scraping pipeline.

## Outputs
- **CSV File**: A timestamped CSV file in `execution/data/outputs/jobs/csv`.
- **Console Output**: Path to the generated CSV file.

## Edge Cases
- **Captcha Challenges**: The scraper uses `camoufox` and `camoufox_captcha` to handle Cloudflare challenges.
- **Login Failures**: Requires valid Upwork credentials in `.env`.
- **Rate Limiting**: Upwork may rate limit aggressive scraping; the script includes delays and simulates human behavior.
