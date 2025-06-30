# ⚠️ Disclaimer

**Warning:** This tool is intended for educational and research purposes only. Scraping Upwork or automating interactions with their platform may violate Upwork's [Terms of Service](https://www.upwork.com/legal#terms-of-use) (TOS). Use of this tool could result in your Upwork account being suspended, banned, or otherwise penalized, especially if used excessively or in a way that disrupts Upwork's services. The authors and contributors of this project are not responsible for any misuse or consequences resulting from the use of this software. Use at your own risk.

# Upwork Job Scraper

A Python-based tool for scraping job listings from Upwork using Playwright and Camoufox for browser automation and anti-bot evasion. The project supports direct scraping, outputs results as CSV files, and can be run as an Apify Actor.

## Docker Hub

You can also pull and run this scraper from Docker Hub: [kdidtech/upwork-job-scraper](https://hub.docker.com/repository/docker/kdidtech/upwork-job-scraper/general)

## Run on Apify

This scraper is also available as an [Apify Actor](https://console.apify.com/actors/pmny1mh4qyCwAaG3l/), which allows you to run it on the Apify platform for scheduled and parallel scraping without managing your own infrastructure.

## Features
- Automated login and job search on Upwork
- Cloudflare and CAPTCHA bypass using Camoufox
- Advanced search parameters and filters
- Detailed job data extraction
- Output to CSV with timestamps
- Docker and Docker Compose support
- Multi-architecture support (amd64, arm64)
- Apify integration for cloud-based execution

## Directory Structure
- `main.py` - Main scraping script (Playwright + Camoufox)
- `utils/` - Utility modules
  - `settings.py` - Configuration and settings
  - `logger.py` - Logging setup
  - `.config.template.toml` - Template for credentials
- `data/jobs/csv/` - Output job data (CSV)
- `data/logging/states/` - Log files and debug screenshots
- `requirements.txt` - Python dependencies
- `Dockerfile` / `docker-compose.yml` - Containerization

## Setup
### 1. Clone the repository
```bash
git clone <repo-url>
cd Upwork-Job-Scraper
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
python -m playwright install --with-deps
pip install "camoufox[geoip]"
```

### 3. Configure credentials
Edit `config.toml` or set via environment:
```toml
[General]
save_csv = true  # Always save CSV output regardless of debug mode

[Credentials]
username = "your_upwork_email"
password = "your_upwork_password"

[Search]
query = "Workflow Automation"  # Main search query
search_any = "make.com n8n tines Zapier"  # Any of these words in search
search_exact = ""  # Exact phrase to search for
search_none = ""  # Exclude these words from search
search_title = ""  # Words that should appear in the job title
category = ["Web, Mobile & Software Dev", "civil & structural engineering"]  # Job categories
projectDuration = ["week", "month", "semester", "ongoing"]  # Project duration options
fixed = true  # Include fixed-price jobs
hourly = true  # Include hourly jobs
hourly_min = 10  # Minimum hourly rate
hourly_max = 70  # Maximum hourly rate
fixed_min = 30  # Minimum fixed price
fixed_max = 100  # Maximum fixed price
hires_min = 1  # Minimum number of hires
hires_max = 10  # Maximum number of hires
limit = 70  # Maximum number of results to return
payment_verified = true  # Only show jobs from payment verified clients
contract_to_hire = false  # Include contract to hire positions
previous_clients = false  # Include previous clients
fixed_price_catagory_num = ["3"]  # Fixed price category numbers (see below)
proposal_min = 0  # Minimum number of proposals
proposal_max = 0  # Maximum number of proposals
sort = "relevance"  # Sort order for results
expertise_level_number = ["1", "2", "3"]  # Experience level (1=Entry, 2=Intermediate, 3=Expert)
workload = ["part_time", "full_time"]  # Type of workload
```

## Usage
### Run directly (Python)
```bash
python main.py --jsonInput '{
  "general": {
    "save_csv": true
  },
  "credentials": {
    "username": "<email>",
    "password": "<password>"
  },
  "search": {
    "q": "python developer",
    "hourly_min": "25",
    "hourly_max": "75",
    "limit": 50
  }
}'
```

Or use config.toml:
```bash
python main.py
```

### Run with Docker
See `dockerreadme.md` for full Docker instructions, including multi-architecture builds.

## Search Parameters
The scraper supports comprehensive search parameters:

```json
{
  "general": {
    "save_csv": true
  },
  "credentials": {
    "username": "your_upwork_email",
    "password": "your_upwork_password"
  },
  "search": {
    "query": "Workflow Automation",
    "search_any": "make.com n8n tines Zapier",
    "search_exact": "",
    "search_none": "",
    "search_title": "",
    "category": ["Web, Mobile & Software Dev", "civil & structural engineering"],
    "projectDuration": ["week", "month", "semester", "ongoing"],
    "fixed": true,
    "hourly": true,
    "hourly_min": 10,
    "hourly_max": 70,
    "fixed_min": 30,
    "fixed_max": 100,
    "hires_min": 1,
    "hires_max": 10,
    "limit": 70,
    "payment_verified": true,
    "contract_to_hire": false,
    "previous_clients": false,
    "fixed_price_catagory_num": ["3"],
    "proposal_min": 0,
    "proposal_max": 0,
    "sort": "relevance",
    "expertise_level_number": ["1", "2", "3"],
    "workload": ["part_time", "full_time"]
  }
}
```

*Use this structure for the `--jsonInput` argument to match the config.toml layout.*

### Price Categories
- 1: $0-99
- 2: $100-499
- 3: $500-999
- 4: $1000-4999
- 5: $5000+

### Expertise Levels
- "entry": 🟢 Entry Level
- "intermediate": 🟡 Intermediate
- "expert": 🔴 Expert

### Duration Options
- "week": Less than one month
- "month": 1 to 3 months
- "semester": 3 to 6 months
- "ongoing": More than 6 months

### Sort Options
- recency
- relevance
- client_total_charge
- client_rating

## Output
- Job data: `data/jobs/csv/job_results_<timestamp>.csv`
  - CSV files are saved when in DEBUG mode or when `save_csv = true` in config.toml
- Logs & screenshots: `data/logging/states/<level>/`

## Configuration
- `config.toml` or `utils/.config.template.toml` for credentials and search parameters
  - `[General]` section controls global behavior
    - `save_csv`: Always save CSV output when true (default: only in DEBUG mode)
- Environment variables via `jsonInput`
- Debug mode: Set logger level to "DEBUG" for additional output

### Example `config.toml`
```toml
[General]
save_csv = true  # Always save CSV output regardless of debug mode

[Credentials]
username = "your_upwork_email"
password = "your_upwork_password"

[Search]
query = "Workflow Automation"  # Main search query
search_any = "make.com n8n tines Zapier"  # Any of these words in search
search_exact = ""  # Exact phrase to search for
search_none = ""  # Exclude these words from search
search_title = ""  # Words that should appear in the job title
category = ["Web, Mobile & Software Dev", "civil & structural engineering"]  # Job categories
projectDuration = ["week", "month", "semester", "ongoing"]  # Project duration options
fixed = true  # Include fixed-price jobs
hourly = true  # Include hourly jobs
hourly_min = 10  # Minimum hourly rate
hourly_max = 70  # Maximum hourly rate
fixed_min = 30  # Minimum fixed price
fixed_max = 100  # Maximum fixed price
hires_min = 1  # Minimum number of hires
hires_max = 10  # Maximum number of hires
limit = 70  # Maximum number of results to return
payment_verified = true  # Only show jobs from payment verified clients
contract_to_hire = false  # Include contract to hire positions
previous_clients = false  # Include previous clients
fixed_price_catagory_num = ["3"]  # Fixed price category numbers (see below)
proposal_min = 0  # Minimum number of proposals
proposal_max = 0  # Maximum number of proposals
sort = "relevance"  # Sort order for results
expertise_level_number = ["1", "2", "3"]  # Experience level (1=Entry, 2=Intermediate, 3=Expert)
workload = ["part_time", "full_time"]  # Type of workload
```

#### Price Categories
- 1: $0-99
- 2: $100-499
- 3: $500-999
- 4: $1000-4999
- 5: $5000+

#### Expertise Levels
- "1": Entry Level
- "2": Intermediate
- "3": Expert

#### Duration Options
- "week": Less than one month
- "month": 1 to 3 months
- "semester": 3 to 6 months
- "ongoing": More than 6 months

#### Sort Options
- recency
- relevance
- client_total_charge
- client_rating

## Contributing

We welcome contributions and pull requests to improve this project!

To help us process your pull request quickly, please:
- Provide a clear and concise description of your changes.
- Keep pull requests focused on a single feature, fix, or improvement.
- Reference any related issues or discussions in your PR description.
- Add or update documentation and tests as needed.
- Ensure your code follows the existing style and passes all checks.

If you have suggestions or ideas, feel free to open an issue or start a discussion. Thank you for helping make this project better!

## Dependencies
See `requirements.txt` for full list.
- [Playwright](https://playwright.dev/)
- [Camoufox](https://github.com/Legrandin/camoufox)
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)

## Camoufox Captcha

This project uses the excellent [camoufox-captcha](https://github.com/techinz/camoufox-captcha) library for advanced CAPTCHA solving. Special thanks to the authors and contributors of camoufox-captcha for their work.

