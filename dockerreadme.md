# Docker Usage for Upwork Job Scraper

This guide explains how to build and run the Upwork Job Scraper using Docker and Docker Compose.

## Prerequisites
- [Docker](https://www.docker.com/get-started) installed
- (Optional) [Docker Compose](https://docs.docker.com/compose/)
- Docker BuildX for multi-architecture builds

## 1. Build the Docker Image

### Single Architecture Build
Navigate to the project root and run:
```bash
docker build -t upwork-job-scraper .
```

### Multi-Architecture Build
To build for multiple architectures (amd64, arm64):

```bash
# Set up buildx builder
docker buildx create --name multiarch --driver docker-container --use

# Build and push for multiple architectures
docker buildx build --platform linux/amd64,linux/arm64 \
  -t yourusername/upwork-job-scraper:latest \
  --push .

# Or build locally without pushing
docker buildx build --platform linux/amd64,linux/arm64 \
  -t upwork-job-scraper:latest \
  --load .
```

## 2. Run the Container
You can provide your Upwork credentials and search parameters via the `jsonInput` environment variable:

```bash
docker run --rm -e 'jsonInput={
  "credentials": {
    "username": "<email>",
    "password": "<password>"
  },
  "search": {
    "q": "python developer",
    "hourly_min": "25",
    "hourly_max": "75",
    "fixed": true,
    "hourly": true,
    "limit": 50,
    "sort": "recency"
  }
}' upwork-job-scraper
```

## 3. Using Docker Compose
A `docker-compose.yml` is provided for convenience:

```yaml
services:
  upwork-job-scraper:
    build: .
    environment:
      - jsonInput={"credentials": {"username": "<email>", "password": "<password>"}, "search": {"q": "python developer"}}
    volumes:
      - ./data:/app/data  # Mount data directory for persistent storage
```

Run with:
```bash
docker compose up --build
```

## 4. Output and Data
- Job data: `/app/data/jobs/csv/job_results_<timestamp>.csv`
- Logs & screenshots: `/app/data/logging/states/<level>/`
- Debug screenshots: `/app/data/logging/states/debug/`

To persist data, mount these directories as volumes:
```bash
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -e 'jsonInput={"credentials":...}' \
  upwork-job-scraper
```

## 5. Search Configuration
The scraper supports various search parameters that can be passed via `jsonInput`:

```json
{
  "search": {
    "q": "search query",
    "all_words": "must include all these words",
    "any_words": "any of these words",
    "none_words": "exclude these words",
    "exact_phrase": "exact phrase match",
    "title_search": "search in title only",
    "fixed_price_catagory_num": ["1", "2", "3"],  // 1:$0-99, 2:$100-499, 3:$500-999, 4:$1000-4999, 5:$5000+
    "fixed_min": "100",
    "fixed_max": "500",
    "hourly_min": "25",
    "hourly_max": "75",
    "hires_min": "1",
    "hires_max": "10",
    "expertise_level_number": ["1", "2", "3"],  // 1:Entry, 2:Intermediate, 3:Expert
    "duration": ["weeks", "months", "semester", "ongoing"],
    "fixed": true,
    "hourly": true,
    "workload": ["part_time", "full_time"],
    "sort": "recency",  // or "relevance", "client_total_charge", "client_rating"
    "limit": 50  // max jobs to fetch (default: 5, max: 50 per page)
  }
}
```

## 6. Advanced Configuration
- Mount a custom `config.toml` for persistent configuration
- Use environment variables for sensitive data
- Debug mode: Set logger level to "DEBUG" for additional screenshots and logging

---
MIT License 