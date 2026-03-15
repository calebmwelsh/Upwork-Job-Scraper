# Generate Upwork Search URL

## Goal

Generate an Upwork job search URL based on specific criteria to be used in subsequent scraping or analysis steps.

## Inputs

- **Search Parameters**: JSON string or file containing search criteria (e.g., query, category, budget).

## Tools

- `execution/generate_upwork_url.py`

## Process

1.  **Define Search Parameters**: Create a JSON object with your search criteria.
    *   Example: `{"query": "python developer", "category": ["Web Development"], "hourly_min": 20}`
2.  **Execute Script**: Run the generation script.
    *   `python execution/generate_upwork_url.py --jsonInput '{"query": "python"}'`
3.  **Retrieve Output**: The script will print the URL to stdout and save it to a file in `execution/data/outputs/urls/`.

## Outputs

- **URL File**: A text file containing the generated URL, saved in `execution/data/outputs/urls/`.
- **Stdout**: The generated URL is also printed to the console.
