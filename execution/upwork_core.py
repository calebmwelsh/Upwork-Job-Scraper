import argparse
import ast
import asyncio
import concurrent.futures
import datetime
import json
import os
import random
import re
import sys
import time
from urllib.parse import urlencode, urlparse

import pandas as pd
import requests

# Import local modules - handle both execution contexts
try:
    # Try importing from current directory (running from execution/)
    import camoufox_utils
    import uchrome_utils
    from attr_extractor import extract_job_attributes
    from logger import Logger
except ImportError:
    # Fall back to importing from execution package (running from root)
    from execution.attr_extractor import extract_job_attributes
    from execution.logger import Logger
    import execution.uchrome_utils as uchrome_utils
    import execution.camoufox_utils as camoufox_utils

from bs4 import BeautifulSoup

# Initialize logger for module-level use
logger_obj = Logger(level="DEBUG")
logger = logger_obj.get_logger()

UPWORK_MAIN_CATEGORIES = {
    # Main Categories
    "accounting & consulting": "531770282584862721",
    "admin support": "531770282580668416",
    "customer service": "531770282580668417",
    "data science & analytics": "531770282580668420",
    "design & creative": "531770282580668421",
    "engineering & architecture": "531770282584862722",
    "it & networking": "531770282580668419",
    "legal": "531770282584862723",
    "sales & marketing": "531770282580668422",
    "translation": "531770282584862720",
    "web, mobile & software dev": "531770282580668418",
    "writing": "531770282580668423",
}
# Subcategories
UPWORK_SUBCATEGORIES = {
    # accounting & consulting
    "personal & professional coaching": "1534904461833879552",
    "accounting & bookkeeping": "531770282601639943",
    "financial planning": "531770282601639945",
    "recruiting & human resources": "531770282601639946",
    "management consulting & analysis": "531770282601639944",
    "other - accounting & consulting": "531770282601639947",
    # admin support
    "data entry & transcription services": "531770282584862724",
    "virtual assistance": "531770282584862725",
    "project management": "531770282584862728",
    "market research & product reviews": "531770282584862726",
    # customer service
    "community management & tagging": "1484275072572772352",
    "customer service & tech support": "531770282584862730",
    # data science & analytics
    "data analysis & testing": "531770282593251330",
    "data extraction & etl": "531770282593251331",
    "data mining & management": "531770282589057038",
    "ai & machine learning": "531770282593251329",
    # design & creative
    "art & illustration": "531770282593251335",
    "audio & music production": "531770282593251341",
    "branding & logo design": "1044578476142100480",
    "nft, ar/vr & game art": "1356688560628174848",
    "graphic, editorial & presentation design": "531770282593251334",
    "performing arts": "1356688565288046592",
    "photography": "531770282593251340",
    "product design": "531770282601639953",
    "video & animation": "1356688570056970240",
    # engineering & architecture
    "building & landscape architecture": "531770282601639949",
    "chemical engineering": "531770282605834240",
    "civil & structural engineering": "531770282601639950",
    "contract manufacturing": "531770282605834241",
    "electrical & electronic engineering": "531770282601639951",
    "interior & trade show design": "531770282605834242",
    "energy & mechanical engineering": "531770282601639952",
    "physical sciences": "1301900647896092672",
    "3d modeling & cad": "531770282601639948",
    # it & networking
    "database management & administration": "531770282589057033",
    "erp & crm software": "531770282589057034",
    "information security & compliance": "531770282589057036",
    "network & system administration": "531770282589057035",
    "devops & solution architecture": "531770282589057037",
    # legal
    "corporate & contract law": "531770282605834246",
    "international & immigration law": "1484275156546932736",
    "finance & tax law": "531770283696353280",
    "public law": "1484275408410693632",
    # sales & marketing
    "digital marketing": "531770282597445636",
    "lead generation & telemarketing": "531770282597445634",
    "marketing, pr & brand strategy": "531770282593251343",
    # translation
    "language tutoring & interpretation": "1534904461842268160",
    "translation & localization services": "531770282601639939",
    # web, mobile & software dev
    "blockchain, nft & cryptocurrency": "1517518458442309632",
    "ai apps and integration": "1737190722360750082",
    "desktop application development": "531770282589057025",
    "ecommerce development": "531770282589057026",
    "game design & development": "531770282589057027",
    "mobile development": "531770282589057024",
    "other - software development": "531770282589057032",
    "product management": "531770282589057030",
    "qa & testing": "531770282589057031",
    "scripts & utilities": "531770282589057028",
    "web & mobile design": "531770282589057029",
    "web development": "531770282584862733",
    # writing
    "sales & marketing copywriting": "1534904462131675136",
    "content writing": "1301900640421842944",
    "editing & proofreading services": "531770282597445644",
    "professional & business writing": "531770282597445646"
}

def normalize_search_params(params: dict, credentials_provided: bool, buffer: int = 5) -> tuple[dict, int]:
    """
    Normalize search parameters from config or input JSON for Upwork job search URL.

    :param params: Dictionary of search parameters (from config or user input)
    :type params: dict
    :param credentials_provided: Whether Upwork credentials are provided (affects access to some filters)
    :type credentials_provided: bool
    :return: Tuple of (normalized_params dict, limit int)
    """
    result = {}

    # Get and validate the limit (no buffer here)
    try:
        limit = int(params.get('limit', 5)) + buffer
    except (ValueError, TypeError):
        limit = 5
        logger.warning("Invalid limit value in config, using default limit of 5")
    
    # Set per_page parameter to the next allowed Upwork value >= limit
    allowed_per_page = [10, 20, 50]
    per_page = min([v for v in allowed_per_page if v >= limit] or [50])
    result['per_page'] = str(per_page)
    
    # Fixed price categories and custom range
    if 'fixed_price_catagory_num' in params:
        amount_ranges = {
            "1": "0-99",
            "2": "100-499",
            "3": "500-999",
            "4": "1000-4999",
            "5": "5000-"
        }
        ranges = []
        for cat in params['fixed_price_catagory_num']:
            if cat in amount_ranges:
                ranges.append(amount_ranges[cat])
        if params.get('fixed_min') and params.get('fixed_max'):
            ranges.append(f"{params['fixed_min']}-{params['fixed_max']}")
        if ranges:
            result['amount'] = ','.join(ranges)
    
    # Client hires (convert min/max to ranges)
    if 'hires_min' in params or 'hires_max' in params:
        ranges = []
        min_val = int(params.get('hires_min', 0))
        max_val = int(params.get('hires_max', float('inf')))
        if min_val <= 9 and max_val >= 1:
            ranges.append('1-9')
        if max_val >= 10:
            ranges.append('10-')
        if ranges:
            result['client_hires'] = ','.join(ranges)
    
    # Expertise level (contractor tier)
    if 'expertise_level_number' in params:
        result['contractor_tier'] = ','.join(params['expertise_level_number'])
    
    # Duration
    if 'projectDuration' in params:
        result['duration_v3'] = ','.join(params['projectDuration'])
    
    # Hourly rate range
    if 'hourly_min' in params and 'hourly_max' in params:
        result['hourly_rate'] = f"{params['hourly_min']}-{params['hourly_max']}"
    
    # Job type (hourly/fixed)
    job_types = []
    if params.get('hourly'):
        job_types.append('0')
    if params.get('fixed'):
        job_types.append('1')
    if job_types:
        result['t'] = ','.join(job_types)
    
    # Workload mapping
    if 'workload' in params:
        workload_map = {
            'part_time': 'as_needed',
            'full_time': 'full_time'
        }
        result['workload'] = ','.join(workload_map[w] for w in params['workload'] if w in workload_map)
    
    # Sort order
    if 'sort' in params:
        sort_map = {
            'relevance': 'relevance+desc',
            'newest': 'recency',
            'client_total_charge': 'client_total_charge+desc',
            'client_rating': 'client_rating+desc'
        }
        result['sort'] = sort_map.get(params['sort'], params['sort'])
    
    # Query building
    q_parts = []
    
    # Main query
    if params.get('query'):
        q_parts.append(params['query'])
    
    # Any words (OR)
    if params.get('search_any'):
        words = params['search_any'].split()
        q_parts.append(f"({' OR '.join(words)})")
    
    if q_parts:
        result['q'] = ' AND '.join(q_parts)
    
    # Pass through boolean/string params that map directly
    for key in ['contract_to_hire', 'previous_clients']:
        if key in params:
            result[key] = str(params[key]).lower()

    if 'days_posted' in params:
        result['days_posted'] = params['days_posted']

    # login required fields
    if not credentials_provided:
        result['proposals'] = ""
        result['payment_verified'] = ""
        result['previous_clients'] = ""
    else:
        # Proposal number (proposals filter) from a direct string input
        if 'proposal_num' in params and params['proposal_num']:
            result['proposals'] = ','.join(params['proposal_num'])
        # payment verified
        if 'payment_verified' in params and params['payment_verified']:
            result['payment_verified'] = '1'
    

    # Categories (main category UID and subcategory UID)
    if 'category' in params and params['category']:
        main_cat_uids = []
        sub_cat_uids = []
        for cat_name in params['category']:
            cat_name_lower = cat_name.lower()
            if cat_name_lower in UPWORK_MAIN_CATEGORIES:
                main_cat_uids.append(UPWORK_MAIN_CATEGORIES[cat_name_lower])
            elif cat_name_lower in UPWORK_SUBCATEGORIES:
                sub_cat_uids.append(UPWORK_SUBCATEGORIES[cat_name_lower])
            else:
                logger.warning(f"Category '{cat_name_lower}' not found in any category map {UPWORK_MAIN_CATEGORIES}, skipping.")

        if main_cat_uids:
            result['category2_uid'] = ','.join(main_cat_uids)
        if sub_cat_uids:
            result['subcategory2_uid'] = ','.join(sub_cat_uids)
    
    return result, limit

def build_upwork_search_url(params: dict) -> str:
    """
    Build an Upwork job search URL from the given parameters dict.

    :param params: Dictionary of normalized search parameters
    :type params: dict
    :return: Upwork job search URL as a string
    :rtype: str
    """
    base_url = params.get('base_url', 'https://www.upwork.com/nx/search/jobs/')
    # Advanced search logic for 'q'
    q_parts = []
    if params.get('all_words'):
        q_parts.append(params['all_words'])
    if params.get('any_words'):
        q_parts.append('(' + ' OR '.join(params['any_words'].split()) + ')')
    if params.get('none_words'):
        q_parts.append(' '.join(f'-{w}' for w in params['none_words'].split()))
    if params.get('exact_phrase'):
        q_parts.append(f'"{params["exact_phrase"]}"')
    if params.get('title_search'):
        q_parts.append(' '.join(f'title:{w}' for w in params['title_search'].split()))
    q = ' '.join(q_parts) if q_parts else params.get('q', '')
    # If only 'q' is present, return minimal URL
    minimal_keys = {'q', 'base_url'}
    if set(params.keys()).issubset(minimal_keys) or (q and len(params) == 1):
        return f"{base_url}?" + urlencode({'q': q})
    # Otherwise, add filters if present
    url_params = {'q': q}
    filter_keys = [
        'amount', 'client_hires', 'hourly_rate', 'payment_verified', 'per_page',
        'sort', 't', 'contract_to_hire', 'contractor_tier', 'duration_v3',
        'nbs', 'previous_clients', 'proposals', 'workload', 'category2_uid', 'subcategory2_uid'
    ]
    for k in filter_keys:
        if k in params:
            url_params[k] = params[k]
    # Add any extra params present in config/inputJson
    for k in params:
        if k not in url_params and k not in ['base_url', 'all_words', 'any_words', 'none_words', 'exact_phrase', 'title_search', 'q']:
            url_params[k] = params[k]
    return f"{base_url}?" + urlencode(url_params)




def parse_job_search_results(html_content: str) -> list[str]:
    """
    Parse HTML content of job search page to extract job URLs.
    
    :param html_content: HTML content of the search result page
    :return: List of valid Upwork job URLs
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = soup.find_all('article')
    logger.debug(f"[Parsing] Found {len(articles)} <article> elements.")
    
    if len(articles) == 0:
        # Debug: check for common 'no results' containers?
        # Just logging for now
        pass

    page_hrefs = []
    for i, article in enumerate(articles):
        a_tag = article.find('a', attrs={'data-test': 'job-tile-title-link UpLink'})
        if not a_tag:
            # Fallback scan
            for a in article.find_all('a', href=True):
                if '/jobs/' in a['href'] and '~' in a['href']:
                    a_tag = a
                    break
        
        if a_tag and a_tag.has_attr('href'):
            href = a_tag['href']
            match = re.search(r'~([0-9a-zA-Z]+)', href)
            if match:
                job_id = match.group(0)
                job_url = f"https://www.upwork.com/jobs/{job_id}"
                page_hrefs.append(job_url)
            else:
                logger.debug(f"[Parsing] Article {i}: Found link {href} but regex failed.")
        else:
             logger.debug(f"[Parsing] Article {i}: No job link found in article HTML snippet: {str(article)[:200]}...")
    
    return page_hrefs

def get_job_urls_selenium(driver, search_querys, search_urls, limit=50):
    """
    For each search query and URL, use Selenium to fetch the page within the browser and extract job URLs.
    
    :param driver: Selenium webdriver instance
    :param search_querys: List of search query strings
    :param search_urls: List of Upwork search URLs
    :param limit: Maximum number of job URLs to extract
    :return: Dictionary mapping each query to a list of job URLs
    """
    search_results = {}
    
    for query, base_url in zip(search_querys, search_urls):
        all_hrefs = []
        pages_needed = (limit + 49) // 50
        jobs_from_last_page = limit % 50 or 50
        
        for page_num in range(1, pages_needed + 1):
            url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
            logger.debug(f"[selenium] Navigating to URL: {url}")
            
            try:
                # Add random sleep before navigation
                time.sleep(random.uniform(5.5, 9.5))
                driver.get(url)
                
                # Check for "log in" string to detect sessions issues
                # Note: Cloudflare might also show distinct titles
                if "Just a moment" in driver.title:
                    logger.info("Waiting for Cloudflare challenge...")
                    time.sleep(random.uniform(15, 20))
                
                # Wait a bit for JS to load results
                time.sleep(random.uniform(5.0, 9.0))
                
                html = driver.page_source
                
                if page_num == 1 and query == search_querys[0]:
                    if "log in" in html.lower() and "sign up" in html.lower() and "user menu" not in html.lower():
                        # Simple heuristic, might get false positives if "Log In" button is always in header
                        # But if we are logged in, usually header changes.
                        logger.error("❌ Session validation failed: 'Log In' / 'Sign Up' text found on search page.")
                        raise Exception("Session Invalid: Appears to not be logged in.")

                page_hrefs = parse_job_search_results(html)
                
                logger.debug(f"Found {len(page_hrefs)} jobs on page {page_num} for query '{query}'")
                
                # If no jobs found
                if not page_hrefs:
                    if page_num == 1:
                        logger.error(f"❌ No jobs found on page 1 for query '{query}'. Search parameters might be invalid or Upwork is blocking.")
                        raise Exception("No jobs found on first page. Aborting pipeline.")
                        sys.exit(0)
                    
                    logger.warning(f"No jobs found on page {page_num}. Ending pagination for this query.")
                    
                    try:
                        driver.save_screenshot(f"execution/debug_no_jobs_page_{page_num}.png")
                        logger.info(f"Saved debug_no_jobs_page_{page_num}.png")
                    except:
                        pass
                    break

                if page_num == pages_needed:
                    page_hrefs = page_hrefs[:jobs_from_last_page]
                all_hrefs.extend(page_hrefs)
                if len(all_hrefs) >= limit:
                    all_hrefs = all_hrefs[:limit]
                    break
            except Exception as e:
                # If session invalid, abort immediately
                if "Session Invalid" in str(e):
                    logger.critical("Aborting search due to invalid session.")
                    raise e
                    
                logger.exception(f"[selenium] Skipping page {page_num} due to navigation failures: {e}")
                continue
        search_results[query] = all_hrefs
    logger.debug(f"[selenium] Search results: {search_results}\n")
    return search_results

def get_job_urls_requests(session, search_querys, search_urls, limit=50):
    """
    For each search query and URL, use requests to fetch the page and extract job URLs.
    """
    search_results = {}
    for query, base_url in zip(search_querys, search_urls):
        all_hrefs = []
        pages_needed = (limit + 49) // 50
        jobs_from_last_page = limit % 50 or 50
        for page_num in range(1, pages_needed + 1):
            url = f"{base_url}&page={page_num}" if page_num > 1 else base_url
            logger.debug(f"[requests] Fetching URL: {url}")
            try:
                # Add random sleep (more human-like)
                time.sleep(random.uniform(3.0, 7.0))
                resp = session.get(url, timeout=30)
                logger.debug(f"[requests] Response Status: {resp.status_code}")
                try:
                    soup_debug = BeautifulSoup(resp.text, 'html.parser')
                    body_debug = soup_debug.body.get_text(separator=' ', strip=True) if soup_debug.body else "No body tag found"
                    logger.debug(f"[requests] DEBUG BODY TEXT:\n{body_debug[:1500]}")
                except Exception as e:
                    logger.error(f"Failed to debug print body: {e}")
                try:
                     resp.raise_for_status()
                except Exception as e:
                     logger.error(f"[requests] Request failed: {e}")
                     logger.debug(f"[requests] Response content snippet: {resp.text[:1500]}")
                     continue
                html = resp.text
                logger.debug(f"[requests] Response content length: {len(html)}")
                # save html to file
                with open(f"execution/debug_requests_page_{page_num}.html", "w", encoding="utf-8") as f:
                     f.write(html)
                if len(html) < 2000:
                     logger.debug(f"[requests] Short response content: {html}")
                
                # Check for "log in" string in the first iteration
                if page_num == 1 and query == search_querys[0]:
                    if "log in" in html.lower() and "sign up" in html.lower() and "user menu" not in html.lower():
                         logger.warning("⚠️ 'log in' string detected. Session might be invalid.")
                         raise Exception("Session Invalid: 'log in' detected on search page.")

                page_hrefs = parse_job_search_results(html)
                logger.debug(f"Found {len(page_hrefs)} jobs on page {page_num} for query '{query}'")
                if not page_hrefs:
                     if page_num == 1:
                         logger.error(f"❌ No jobs found on page 1 for query '{query}'. Search parameters might be invalid or Upwork is blocking.")
                         raise Exception("No jobs found on first page. Aborting pipeline.")
                         sys.exit(0)
                     break
                
                if page_num == pages_needed:
                    page_hrefs = page_hrefs[:jobs_from_last_page]
                all_hrefs.extend(page_hrefs)
                if len(all_hrefs) >= limit:
                    all_hrefs = all_hrefs[:limit]
                    break
            except Exception as e:
                logger.exception(f"[requests] Skipping page {page_num} due to errors: {e}")
                sys.exit(0)
                
                continue
        search_results[query] = all_hrefs
    logger.debug(f"[requests] Search results: {search_results}\n")
    return search_results

def fetch_job_detail(session, url, credentials_provided):
    """
    Fetch job detail page and extract job attributes.
    """
    logger.debug(f"[requests] Fetching details for: {url}")
    try:
        # random sleep
        time.sleep(random.uniform(2.5, 5.5))
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
        job_id_match = re.search(r'~([0-9a-zA-Z]+)', url)
        job_id = job_id_match.group(1) if job_id_match else "0"
        attrs = extract_job_attributes(html)
        attrs['url'] = url
        attrs['job_id'] = job_id
        return attrs
    except Exception as e:
        logger.debug(f"[requests] Failed to process {url}: {e}")
        return None

def browser_worker_requests(session, job_urls, credentials_provided, max_workers=5):
    """
    Fetch job details in parallel using ThreadPoolExecutor with rate limiting.
    Pauses after every 25 requests to avoid 429 errors and simulate human behavior.
    """
    job_attributes = []
    total_urls = len(job_urls)
    # Process in smaller batches
    batch_size = 25 
    
    # Track requests for rate limiting
    request_count = 0
    rate_limit_threshold = 50
    
    for i in range(0, total_urls, batch_size):
        batch = job_urls[i:i + batch_size]
        
        # Check if we need to rate limit pause
        if request_count > 0 and request_count % rate_limit_threshold == 0:
            pause_time = random.uniform(90, 150)
            logger.info(f"🛑 Rate limit threshold reached ({request_count} requests). Pausing for {pause_time:.2f} seconds...")
            time.sleep(pause_time)
            
        logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} jobs)...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(fetch_job_detail, session, url, credentials_provided)
                for url in batch
            ]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    job_attributes.append(result)
        
        request_count += len(batch)
        # Larger pause between batches
        time.sleep(random.uniform(5, 10))

    return job_attributes

# Helper to normalize browser type string
def normalize_browser_type(b_type: str) -> str:
    b_type = str(b_type).lower().strip()
    if b_type in ['selenium', 'uc', 'chrome']:
        return 'selenium'
    if b_type in ['camoufox', 'cf', 'playwright', 'firefox']:
        return 'camoufox'
    return 'selenium'  # Default

async def main(jsonInput: dict) -> list[dict]:
    """
    Main entry point for the Upwork Job Scraper. Orchestrates browser setup, login, job search, and extraction.
    """
    logger.info("🏁 Starting Upwork Job Scraper...")
    start_time = time.time()

    # Extract credentials
    if "credentials" in jsonInput:
        credentials_json = jsonInput["credentials"]
    else:
        credentials_json = jsonInput
    # set username and password
    username = credentials_json.get('username', None)
    password = credentials_json.get('password', None)
    if (username and not password) or (password and not username):
        logger.warning("Both username and password must be provided for authentication. One is missing.")
    credentials_provided = username and password
    # Extract search params
    search_params = jsonInput.get('search', {})
    
    # If still not present, fallback to defaults
    if not search_params:
        search_params = {}
    # Extract general params
    general_params = jsonInput.get('general', {})
    save_csv = general_params.get('save_csv', False)
    
    # New optimization params
    headless = general_params.get('headless', False)
    max_workers_count = general_params.get('max_workers', 5)
    
    # Determine Browser Type
    browser_type_input = general_params.get('browser_type', jsonInput.get('browser_type', 'camoufox'))
    browser_type = normalize_browser_type(browser_type_input)
    logger.info(f"🤖 Browser selected: {browser_type.upper()}")

    # Normalize search params and get limit
    buffer = 20
    normalized_search_params, limit = normalize_search_params(search_params, credentials_provided, buffer)

    # Build search URL using the function
    logger.info("🏗️  Building search URL...")
    search_url = build_upwork_search_url(normalized_search_params)
    logger.info(f"Search URL: {search_url}")

    # Visit Upwork login page
    login_url = "https://www.upwork.com/ab/account-security/login"

    search_queries = [search_params.get('query', search_params.get('search_any', 'search'))]
    search_urls = [search_url]
    
    # proxy
    proxy_details = jsonInput.get('proxy_details', None)
    logger.debug(f"proxy_details: {proxy_details}")

    session = None
    
    if browser_type == 'selenium':
        # --- SELENIUM FLOW ---
        # Initialize Selenium driver for Login
        logger.info("🌐 Initializing Selenium driver for Login...") 
        driver = uchrome_utils.get_selenium_driver(proxy_details=proxy_details)
        
        try:
            # Login
            search_success = uchrome_utils.login_and_solve_selenium(driver, username, password, login_url, search_url)
            
            if not search_success:
                logger.error("❌ Login/Result validation failed.")
                driver.quit()
                return []

            logger.info("✅ Login successful. Proceeding with hybrid scraping (Selenium Search -> Requests Details)...")
            
            # --- Selenium for Search (Reliable) ---
            logger.info("💼 Getting Related Jobs (Selenium)...")
            # We need to make sure get_job_urls_selenium is available (it is in the file as I restored it earlier)
            job_urls_dict = get_job_urls_selenium(driver, search_queries, search_urls, limit=limit)
            job_urls = list(job_urls_dict.values())[0] if job_urls_dict else []
            logger.debug(f"Got {len(job_urls)} job URLs.")
            
            if not job_urls:
                logger.warning("No jobs URLs found. Exiting.")
                driver.quit()
                return []

            # --- Convert to Requests for Details (Fast) ---
            logger.info("✅ Converting cookies to requests session for detailed scraping...")
            session = uchrome_utils.selenium_cookies_to_requests(driver)
            
        except Exception as e:
            logger.error(f"Critical error during Selenium scraping logic: {e}")
            driver.quit()
            return []
            
        finally:
            # Close Selenium driver now that we have the session
            if 'driver' in locals():
                logger.info("🛑 Closing Selenium driver...")
                driver.quit()
    
    elif browser_type == 'camoufox':
        # --- CAMOUFOX FLOW ---
        try:
            # Login and get session (Browser closes automatically after this)
            session = await camoufox_utils.camoufox_login_flow(
                username, password, login_url, search_url, credentials_provided, proxy_details, headless=headless
            )
            logger.info("✅ Login successful (Camoufox). Got requests session.")
            
            # Debug: Check what the session sees immediately
            try:
                logger.debug("🔍 Fetching search page to debug session state...")
                debug_r = session.get(search_url, timeout=30)
                soup = BeautifulSoup(debug_r.text, 'html.parser')
                body_text = soup.body.get_text(separator=' ', strip=True) if soup.body else "No body tag found"
                logger.debug(f"DEBUG BODY TEXT (Status {debug_r.status_code}):\n{body_text[:500]}")
            except Exception as e:
                logger.error(f"Failed to fetch debug body: {e}")
            
            # --- Requests for Search (Fast, matching old script) ---
            logger.info("💼 Getting Related Jobs (Requests)...")
            job_urls_dict = get_job_urls_requests(session, search_queries, search_urls, limit=limit)
            job_urls = list(job_urls_dict.values())[0] if job_urls_dict else []
            logger.debug(f"Got {len(job_urls)} job URLs.")
             
        except Exception as e:
            logger.error(f"Critical error during Camoufox logic: {e}")
            return []

    # --- Requests-based Job Detail Scraping (Shared) ---
    if not session:
         logger.error("❌ No valid session established. Exiting.")
         return []

    try: 
        logger.info(f"🏢 Getting Job Attributes for {len(job_urls)} jobs with Requests (ThreadPool)...")
        job_attributes = browser_worker_requests(session, job_urls, credentials_provided, max_workers=max_workers_count)

    except Exception as e:
        logger.error(f"Critical error during detail scraping: {e}")
        return []

    # Filter out jobs where Nuxt data was missing (i.e., job is None)
    logger.debug(f"job_attributes after filter: {len(job_attributes)}")
    # Trim to the original limit
    logger.debug(f"limit: {limit-buffer}")
    # Filter by days_posted (Client-side enforcement)
    if 'days_posted' in search_params:
        try:
             days = int(search_params['days_posted'])
             cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
             logger.info(f"📅 Filtering jobs posted before {cutoff_time} (Last {days} days)")
             
             filtered_attributes = []
             for job in job_attributes:
                 ts_create_str = job.get('ts_create')
                 if ts_create_str:
                     try:
                         # Handle typical ISO format from Upwork: 2026-01-11T17:44:16.509Z
                         # Ensure it's treated as UTC
                         ts_create = datetime.datetime.fromisoformat(ts_create_str.replace('Z', '+00:00'))
                         if ts_create >= cutoff_time:
                             filtered_attributes.append(job)
                         else:
                             # Debug log for discarded jobs?
                             pass
                     except ValueError:
                         logger.warning(f"Failed to parse timestamp {ts_create_str}, keeping job.")
                         filtered_attributes.append(job)
                 else:
                     # Keep if no timestamp
                     filtered_attributes.append(job)
             
             logger.info(f"📉 Filtered out {len(job_attributes) - len(filtered_attributes)} old jobs. Remaining: {len(filtered_attributes)}")
             job_attributes = filtered_attributes

        except ValueError:
            logger.warning(f"Invalid days_posted value: {search_params['days_posted']}")

    job_attributes = job_attributes[:limit-buffer]
    
    if save_csv:
        # Ensure data directory is in execution/ folder, not project root
        execution_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(execution_dir, 'data', 'outputs', 'jobs', 'csv')
        os.makedirs(data_dir, exist_ok=True)
        csv_path = os.path.join(data_dir, f'job_results_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        df = pd.DataFrame(job_attributes)
        df.to_csv(csv_path, index=False)
        
    end_time = time.time()
    elapsed = end_time - start_time
    logger.info("🏁 Job Fetch Complete!")
    logger.info(f"🎯 Number of results: {len(job_attributes)}")
    # Log number of unique columns across all job records
    num_columns = len(set().union(*(job.keys() for job in job_attributes))) if job_attributes else 0
    logger.info(f"🧩 Number of columns: {num_columns}")
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    logger.info(f"🕒 Total run time: {minutes}m {seconds}s ({elapsed:.2f} seconds)")
    return job_attributes


if __name__ == "__main__":
    # set argparse
    parser = argparse.ArgumentParser(description="Upwork Job Scraper")
    parser.add_argument('--jsonInput', type=str, help='JSON string or path to JSON file with credentials and other info')
    parser.add_argument('--browser', type=str, default='camoufox', choices=['selenium', 'camoufox', 'uc', 'cf'], 
                        help='Browser to use: selenium (default) or camoufox')
    args = parser.parse_args()

    # set logger
    logger_obj = Logger(level="DEBUG")
    logger = logger_obj.get_logger()

    input_data = {}

    # Load credentials/input data from environment variable or argument
    if os.environ.get("jsonInput"):
        json_input_str = os.environ.get("jsonInput")
        try:
            input_data = json.loads(json_input_str)
        except json.JSONDecodeError:
            try:
                # It might be a dict string, so we can use ast.literal_eval
                input_data = ast.literal_eval(json_input_str)
            except (ValueError, SyntaxError) as e:
                logger.error(f"⚠️ Failed to parse jsonInput from environment variable: {e}")
                sys.exit(1)
    # load from argument
    elif args.jsonInput:
        try:
            input_data = json.loads(args.jsonInput)
        except json.JSONDecodeError as e:
            logger.error(f"⚠️ Failed to parse input JSON: {e}")
            sys.exit(1)
            
    # Add browser choice to input_data if specified via CLI args (override)
    if args.browser:
         if 'general' not in input_data:
             input_data['general'] = {}
         input_data['general']['browser_type'] = args.browser

    # Run the scraper
    asyncio.run(main(input_data))
