# Upwork Job Scraper

A specialized tool for scraping Upwork job listings based on advanced search criteria and saving results directly to CSV.

## Core Functionality

This repository is dedicated to the Upwork side of data acquisition:
- **Authenticated Scraping**: Uses `camoufox` or `selenium` to bypass Cloudflare and log in to Upwork.
- **Advanced Search**: Supports complex queries, categories, budget ranges, and expertise levels.
- **CSV Output**: Automatically saves scraped job data to timestamped CSV files in `execution/data/outputs/jobs/csv`.
- **Performance**: Uses parallel request handling (ThreadPool) for fast attribute extraction.

## Getting Started

### 1. Installation
```bash
pip install -r requirements.txt
playwright install  # Required for camoufox
```

### 2. Configuration
Create a `.env` file in the root directory (or in `.env/` folder) with your Upwork credentials:
```env
UPWORK_USERNAME=your_username
UPWORK_PASSWORD=your_password
```

### 3. Usage

#### Run Default Search
Runs the search defined in `execution/data/inputs/default_upwork_search.json`.
```bash
python execution/run_job_search.py
```

#### Run Custom Search
```bash
python execution/scrape_upwork.py --limit 50 --browser camoufox
```

#### CLI Arguments
- `--limit`: Max number of jobs to scrape.
- `--browser`: Choose between `camoufox` (default) or `selenium`.
- `--no-headless`: Run the browser in headful mode (visible).
- `--max_workers`: Number of parallel threads for detail scraping.

## Directory Structure

```
.
├── directives/         # Standard Operating Procedures
│   └── scrape_upwork.md
├── execution/          # Core Python Logic
│   ├── data/           # Inputs and CSV Outputs
│   ├── upwork_core.py  # Primary scraping engine
│   └── scrape_upwork.py # Main entry point
├── requirements.txt    # Project dependencies
└── README.md           # This file
```

## Architecture Principles

This project follows a 3-layer architecture for reliability:
1. **Directive**: Natural language SOPs in `directives/` define the process.
2. **Orchestration**: AI or orchestrator scripts (e.g., `run_job_search.py`) manage the flow.
3. **Execution**: Deterministic Python scripts in `execution/` handle the heavy lifting.

## Documentation
- **Detailed Scraper Guide**: See [directives/scrape_upwork.md](directives/scrape_upwork.md)
- **Refactoring Walkthrough**: See [walkthrough.md](file:///C:/Users/KDID/.gemini/antigravity/brain/e7cf4b05-cd4f-466f-a2a8-2bc760ebbda1/walkthrough.md)
