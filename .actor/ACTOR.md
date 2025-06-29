# Upwork Job Scraper

This Apify Actor scrapes job listings from Upwork based on a wide range of search criteria. It automates the login process, bypasses anti-bot measures, and extracts detailed information for each job into a structured format.

## Features

- **Advanced Search**: Filter jobs by keywords, job type, budget, client history, expertise level, and more.
- **Secure Login**: Handles Upwork authentication securely.
- **Captcha Solving**: Integrates captcha solving to handle Cloudflare challenges.
- **Detailed Data Extraction**: Scrapes over 50 data points for each job, including client information, job requirements, budget, and skills.
- **Flexible Input**: Configure the scraper using a simple JSON input.
- **Structured Output**: Provides results in a clean, machine-readable format (JSON).

## Input Schema

The actor is configured using a JSON object with the following properties.

### Credentials (Required)

You must provide your Upwork login credentials.

```json
{
  "credentials": {
    "username": "YOUR_UPWORK_EMAIL",
    "password": "YOUR_UPWORK_PASSWORD"
  }
}
```

### Search Parameters

Define your job search criteria within the `search` object. All fields below are supported:

```json
{
  "search": {
    "query": "Workflow Automation",
    "search_any": "make.com n8n tines Zapier",
    "search_exact": "",
    "search_none": "",
    "search_title": "",
    "category": ["Web, Mobile & Software Dev", "civil & structural engineering"],
    "projectDuration": ["week", "month", "semester", "ongoing"],
    "fixed": true,
    "hires_min": 1,
    "hires_max": 10,
    "hourly": true,
    "hourly_max": 70,
    "hourly_min": 10,
    "limit": 70,
    "payment_verified": true,
    "contract_to_hire": false,
    "previous_clients": false,
    "fixed_price_catagory_num": ["3"],
    "fixed_max": 100,
    "fixed_min": 30,
    "proposal_min": 0,
    "proposal_max": 0,
    "sort": "relevance",
    "expertise_level_number": ["1", "2", "3"],
    "workload": []
  }
}
```

#### All Search Fields

-   `query` (string): The primary keyword for the search (e.g., "web developer").
-   `search_any` (string): Space-separated words; jobs must contain at least one (e.g., "make.com n8n zapier").
-   `search_exact` (string): The exact phrase the job must contain.
-   `search_none` (string): Space-separated words to exclude from the search.
-   `search_title` (string): Words that must appear in the job title.
-   `category` (array of strings): List of job categories to include.
-   `projectDuration` (array of strings): List of durations. Options: `week`, `month`, `semester`, `ongoing`.
-   `fixed` (boolean): Include fixed-price jobs.
-   `hires_min` (integer): Minimum number of client hires.
-   `hires_max` (integer): Maximum number of client hires.
-   `hourly` (boolean): Include hourly jobs.
-   `hourly_max` (integer): Maximum hourly rate.
-   `hourly_min` (integer): Minimum hourly rate.
-   `limit` (integer): The maximum number of jobs to scrape.
-   `payment_verified` (boolean): Only jobs from clients with verified payment.
-   `contract_to_hire` (boolean): Only contract-to-hire jobs.
-   `previous_clients` (boolean): Only jobs from your previous clients.
-   `fixed_price_catagory_num` (array of strings): Pre-defined budget ranges. `"1"` ($0-99), `"2"` ($100-499), `"3"` ($500-999), `"4"` ($1k-5k), `"5"` ($5k+).
-   `fixed_max` (integer): Maximum fixed price budget.
-   `fixed_min` (integer): Minimum fixed price budget.
-   `proposal_min` (integer): Minimum number of proposals.
-   `proposal_max` (integer): Maximum number of proposals.
-   `sort` (string): The order to sort results. Options: `relevance`, `newest`, `client_total_charge`, `client_rating`.
-   `expertise_level_number` (array of strings): List of expertise levels. `"1"` (Entry), `"2"` (Intermediate), `"3"` (Expert).
-   `workload` (array of strings): List of workload preferences. Options: `part_time`, `full_time`.

## Output

The actor returns a dataset where each item represents a scraped job.

### Example Job Output Item

```json
{
  "job_id": "01abcdef1234567890",
  "url": "https://www.upwork.com/jobs/~01abcdef1234567890",
  "title": "Build a simple web scraper for product data",
  "description": "We need a script that can scrape product names, prices, and availability from an e-commerce website...",
  "type": "Fixed-price",
  "level": "INTERMEDIATE",
  "fixed_budget_amount": 500,
  "hourly_min": 0,
  "hourly_max": 0,
  "duration": "Less than a month",
  "skills": ["Web Scraping", "Python", "Beautiful Soup"],
  "applicants": "10",
  "connects_required": 6,
  "payment_verified": true,
  "phone_verified": true,
  "client_country": "United States",
  "buyer_location_city": "New York",
  "buyer_location_localTime": "10:30 am",
  "client_total_spent": 2500,
  "client_hires": 5,
  "client_rating": 4.95,
  "client_reviews": "12 reviews",
  "ts_publish": "2023-10-27T10:00:00.000Z"
}
```

### Output Fields

The actor extracts the following fields for each job, when available:

-   **Job Details**: `job_id`, `url`, `title`, `description`, `type` (Hourly/Fixed-price), `level`, `duration`, `skills`, `qualifications`, `questions`, `category_name`, `isContractToHire`, `premium`, `enterpriseJob`.
-   **Budget**: `fixed_budget_amount`, `hourly_min`, `hourly_max`, `currency`.
-   **Timestamps**: `ts_create`, `ts_publish`.
-   **Job Activity**: `applicants`, `clientActivity_invitationsSent`, `clientActivity_unansweredInvites`, `clientActivity_totalInvitedToInterview`, `lastBuyerActivity`.
-   **Client Info**: `payment_verified`, `phone_verified`, `client_country`, `buyer_location_city`, `buyer_location_localTime`, `client_industry`, `client_company_size`.
-   **Client Stats**: `client_total_spent`, `client_hires`, `client_rating`, `client_reviews`, `buyer_jobs_postedCount`, `buyer_jobs_openCount`, `buyer_avgHourlyJobsRate_amount`, `buyer_stats_hoursCount`.

## Usage

1.  Navigate to the Actor page on the Apify platform.
2.  Click "Try actor".
3.  Enter your input configuration in the JSON editor. At a minimum, provide your `credentials`.
4.  Click "Start" to run the actor.
5.  Once the run is complete, view and download the results from the "Dataset" tab. 