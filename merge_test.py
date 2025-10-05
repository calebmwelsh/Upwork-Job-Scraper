import argparse
import ast
import asyncio
import concurrent.futures
import contextlib
import csv
import datetime
import io
import json
import logging
import os
import re
import sys
import time
from collections import deque

import js2py
import pandas as pd
import requests
from bs4 import BeautifulSoup
from camoufox import AsyncCamoufox
from playwright._impl._errors import TargetClosedError
from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from camoufox_captcha import solve_captcha
from utils.logger import Logger

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
                logger.warning(f"Category '{cat_name}' not found in any category map, skipping.")

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
        from urllib.parse import urlencode
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
    from urllib.parse import urlencode
    return f"{base_url}?" + urlencode(url_params)

async def safe_goto(
    page: Page,
    url: str,
    browser_context: BrowserContext,
    max_retries: int = 3,
    timeout: int = 30000,
    wait_untils: list[str] = ["domcontentloaded", "networkidle"]
) -> Page:
    """
    Safely navigate a Playwright page to a URL with retries and error handling.

    :param page: Playwright Page object to navigate
    :type page: Page
    :param url: URL to navigate to
    :type url: str
    :param browser_context: Playwright BrowserContext for creating new pages if needed
    :type browser_context: BrowserContext
    :param max_retries: Maximum number of navigation attempts
    :type max_retries: int
    :param timeout: Timeout for each navigation attempt (ms)
    :type timeout: int
    :param wait_untils: List of waitUntil events for navigation
    :type wait_untils: list[str]
    :return: The navigated Playwright Page object
    :rtype: Page
    """
    last_exc = None

    for attempt in range(1, max_retries + 1):
        for wait_until in wait_untils:
            try:
                logger.debug(f"[Attempt {attempt}] goto({url}) waitUntil={wait_until}")
                response = await page.goto(url, timeout=timeout, wait_until=wait_until)
                logger.debug(f"[Attempt {attempt}] Navigation succeeded (waitUntil={wait_until})")
                # return working page
                return page  
            except TargetClosedError:
                logger.warning("Page or browser crashed. Creating new page...")
                try:
                    page = await browser_context.new_page()
                except Exception as create_exc:
                    logger.exception("Failed to create new page after crash.")
                    raise create_exc
            except Exception as e:
                last_exc = e
                logger.debug(f"[Attempt {attempt}] goto failed: {e}")

    logger.error(f"⚠️ Failed to navigate to {url} after {max_retries} attempts", exc_info=last_exc)
    raise last_exc

async def login_process(
    login_url: str,
    page: Page,
    context: BrowserContext,
    username: str,
    password: str,
    max_attempts: int = 2
) -> bool:
    """
    Automate the Upwork login process using Playwright, with robust retry logic.
    Tries reloading and creating a new page, but does NOT clear cookies unless all else fails.

    :param login_url: Upwork login URL
    :type login_url: str
    :param page: Playwright Page object
    :type page: Page
    :param context: Playwright BrowserContext
    :type context: BrowserContext
    :param username: Upwork username/email
    :type username: str
    :param password: Upwork password
    :type password: str
    :param max_attempts: Maximum number of login attempts
    :type max_attempts: int
    :return: True if login succeeded, False otherwise
    :rtype: bool
    """
    for attempt in range(1, max_attempts + 1):
        try:
            page = await safe_goto(page, login_url, context, timeout=60000)
            await page.wait_for_selector('#login_username', timeout=10000)
            await page.fill('#login_username', username)
            logger.debug(f"Username entered: {username}")
            await page.press('#login_username', 'Enter')
            await asyncio.sleep(2)
            await page.wait_for_selector('#login_password', timeout=10000)
            await page.fill('#login_password', password)
            logger.debug(f"Password entered.")
            await page.press('#login_password', 'Enter')
            await asyncio.sleep(3)
            body_text = await page.locator('body').inner_text()
            if 'Verification failed. Please try again.' in body_text[:100] or 'Please fix the errors below' in body_text[:100]:
                logger.debug(f"Verification on login failed. Attempt {attempt}/{max_attempts}")
                # Try reloading or creating a new page, but do NOT clear cookies yet
                if attempt == max_attempts // 2:
                    logger.debug("Creating a new page due to repeated login failures.")
                    page = await context.new_page()
                continue
            logger.debug(f"Login process complete.")
            logger.debug(f"Body text: {body_text[:100]}")
            return True
        except Exception as e:
            logger.debug(f"Login attempt {attempt} failed: {e}")
            await asyncio.sleep(3)
    logger.error("⚠️ All login attempts failed.")
    return False

async def login_and_solve(
    page: Page,
    context: BrowserContext,
    username: str,
    password: str,
    search_url: str,
    login_url: str,
    credentials_provided: bool
) -> None:
    """
    Navigate to Upwork, solve captcha if present, and log in if credentials are provided.
    If a new context or cookies are cleared, re-solve captcha before login.

    :param page: Playwright Page object to use for navigation and interaction
    :type page: Page
    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param username: Upwork username/email
    :type username: str
    :param password: Upwork password
    :type password: str
    :param search_url: Upwork job search URL to visit initially
    :type search_url: str
    :param login_url: Upwork login URL
    :type login_url: str
    :param credentials_provided: Whether Upwork credentials are provided (affects login behavior)
    :type credentials_provided: bool
    :return: Tuple of (page, context) after login/captcha (or attempted login)
    :rtype: tuple[Page, BrowserContext]
    """
    # go to search url
    await safe_goto(page, search_url, context)
    # bypass captcha
    logger.debug(f"Checking for captcha challenge...")
    captcha_solved = await solve_captcha(queryable=page, browser_context=context, captcha_type='cloudflare', challenge_type='interstitial', solve_attempts = 5, solve_click_delay = 6, wait_checkbox_attempts = 5, wait_checkbox_delay = 5, checkbox_click_attempts = 3, attempt_delay = 5)
    if captcha_solved:
        logger.debug(f"Successfully solved captcha challenge!")
    else:
        logger.warning(f"⚠️ No captcha challenge detected or failed to solve captcha.")
    # if credentials are provided, login
    if credentials_provided:
        logger.debug(f"Logging in...")
        login_success = await login_process(login_url, page, context, username, password)
        # if login fails, try clearing cookies and re-solving captcha
        if not login_success:
            logger.error("⚠️ Login failed after all attempts.")
            logger.info("🔴 Attempting last resort: clear cookies, re-solve captcha, and retry login...")
            try:
                await context.clear_cookies()
                page = await context.new_page()
                await safe_goto(page, search_url, context)
                # Re-solve captcha
                captcha_solved = await solve_captcha(queryable=page, browser_context=context, captcha_type='cloudflare', challenge_type='interstitial', solve_attempts = 5, solve_click_delay = 6, wait_checkbox_attempts = 5, wait_checkbox_delay = 5, checkbox_click_attempts = 3, attempt_delay = 5)
                if captcha_solved:
                    logger.info("✅ Captcha solved after clearing cookies. Retrying login...")
                else:
                    logger.warning("⚠️ Captcha could not be solved after clearing cookies.")
                # Retry login
                login_success = await login_process(login_url, page, context, username, password)
                if not login_success:
                    logger.error("⚠️Login still failed after last resort attempt (clear cookies, re-solve captcha, retry login). Aborting.")
                    # print body text
                    body_text = await page.locator('body').inner_text()
                    logger.debug(f"Body text: {body_text}")
                else:
                    logger.info("✅ Login succeeded after last resort attempt.")
                    # return page and context so that new context is used for scraping
                    return page, context
            except Exception as e:
                logger.error(f"⚠️ Exception during last resort login attempt: {e}")
    return page, context

def extract_nuxt_json_using_js2py(html: str) -> dict | None:
    """
    Extract and evaluate the window.__NUXT__ script content from HTML using js2py.

    :param html: HTML content as a string
    :type html: str
    :return: Parsed __NUXT__ JSON as a dict, or None if not found/parsable
    :rtype: dict or None
    """
    # Match script that initializes __NUXT__ using window/self/globalThis
    match = re.search(r'<script[^>]*>\s*(?:window|self|globalThis)\.__NUXT__=([\s\S]*?)</script>', html)
    if not match:
        return None
    js_code = match.group(1).strip().rstrip(';')
    js_code = "var nuxt = " + js_code
    try:
        # Capture only js2py stdout, suppressing PyJs_LONG_1_ output
        with contextlib.redirect_stdout(io.StringIO()):
            context = js2py.EvalJs()
            context.execute(js_code)
        return context.nuxt.to_dict()
    except Exception as e:
        logger.debug(f"Error evaluating window.__NUXT__ with js2py: {e}")
        return None

def extract_inner_script_nuxt_data(text: str) -> str:
    """
    Extract inner JSON from <script id="__NUXT_DATA__"> tags.
    """
    m = re.search(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', text, re.S | re.I)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith('['):
        return s
    # Save the raw input for debugging when regex does not match
    try:
        os.makedirs('testing', exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"testing/nuxt_data_extraction_failed_{ts}.html"
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text if isinstance(text, str) else repr(text))
        if 'logger' in globals():
            logger.debug(f"Saved NUXT_DATA miss sample to {out_path}")
    except Exception:
        pass
    
    exit(0)
    raise ValueError("Could not find __NUXT_DATA__ script content in input.")

def iter_dicts_and_lists_nuxt(obj):
    queue = deque([(obj, ())])
    while queue:
        cur, path = queue.popleft()
        if isinstance(cur, dict):
            yield cur, path
            for k, v in cur.items():
                queue.append((v, path + (k,)))
        elif isinstance(cur, list):
            for i, item in enumerate(cur):
                queue.append((item, path + (i,)))

JOB_KEYS_NUXT = {
    "job_id", "uid", "title", "description", "postedOn", "publishTime", "posted_on",
    "amount", "currencyCode", "hourlyBudgetMin", "hourlyBudgetMax", "hourlyBudgetType",
    "workload", "durationLabel", "category", "categoryGroup", "slug", "jobSlug", "id",
    "status", "skills", "languages", "client", "buyer", "name", "city", "country",
    "timezone", "totalApplicants", "totalHired", "invitationsSent", "unansweredInvites",
    "numberOfPositionsToHire", "type", "access"
}

CLIENT_KEYS_NUXT = {"client", "buyer", "owner", "company", "profile", "name", "city", "country", "timezone"}

def score_candidate_nuxt(d: dict) -> int:
    if not isinstance(d, dict):
        return 0
    keys = set(d.keys())
    return sum(1 for k in keys if k in JOB_KEYS_NUXT or k.lower() in JOB_KEYS_NUXT)

def try_resolve_reference_nuxt(root, val):
    if not (isinstance(val, int) and isinstance(root, list)):
        return val
    if 0 <= val < len(root):
        candidate = root[val]
        if isinstance(candidate, (str, int, float, bool, type(None))):
            return candidate
        if isinstance(candidate, dict):
            primitive_count = sum(1 for v in candidate.values() if isinstance(v, (str, int, float, bool, type(None))))
            if primitive_count >= max(1, len(candidate) // 2):
                return candidate
        if isinstance(candidate, list) and len(candidate) <= 20 and all(isinstance(x, (str, int, float, bool, type(None))) for x in candidate):
            return candidate
    return val

def merge_dicts_prefer(target: dict, src: dict):
    for k, v in src.items():
        if k not in target or target[k] in (None, "", [], {}):
            target[k] = v
    return target

def find_job_candidate_nuxt(root) -> dict:
    best = None
    best_score = -1
    for d, path in iter_dicts_and_lists_nuxt(root):
        sc = score_candidate_nuxt(d)
        if sc > best_score:
            best_score = sc
            best = d
    return best if best_score > 0 else None

def extract_job_fields_from_nuxt_data(root: object, try_resolve_refs: bool = True) -> dict:
    out: dict = {}
    if isinstance(root, list):
        job_cand = find_job_candidate_nuxt(root)
    elif isinstance(root, dict):
        job_cand = root
    else:
        job_cand = None

    collected = {}
    for d, path in iter_dicts_and_lists_nuxt(root):
        if not isinstance(d, dict):
            continue
        for key in d.keys():
            k_lower = key.lower()
            if key in JOB_KEYS_NUXT or k_lower in JOB_KEYS_NUXT or key in CLIENT_KEYS_NUXT:
                val = d[key]
                if try_resolve_refs:
                    val = try_resolve_reference_nuxt(root, val)
                collected.setdefault(key, []).append((val, path))
        for candidate_text_key in ("description", "Title", "title", "shortDescription"):
            if candidate_text_key in d:
                val = d[candidate_text_key]
                if try_resolve_refs:
                    val = try_resolve_reference_nuxt(root, val)
                collected.setdefault("description", []).append((val, path))

    def pick_first(keyname):
        vals = collected.get(keyname) or collected.get(keyname.lower())
        if not vals:
            return None
        candidates = [v for v, p in vals]
        candidates = [c for c in candidates if c not in (None, "", [], {})]
        if not candidates:
            return vals[0][0]
        if all(isinstance(c, str) for c in candidates):
            return max(candidates, key=len)
        return candidates[0]

    for k in [
        "title", "uid", "id", "job_id", "slug", "jobSlug", "publishTime", "postedOn", "posted_on", "description",
        "amount", "currencyCode", "hourlyBudgetMin", "hourlyBudgetMax", "workload", "durationLabel",
        "category", "categoryGroup", "name", "city", "country", "timezone",
        "totalApplicants", "totalHired", "invitationsSent", "unansweredInvites", "numberOfPositionsToHire"
    ]:
        val = pick_first(k)
        if val is not None:
            out[k] = val

    if job_cand and isinstance(job_cand, dict):
        for k, v in job_cand.items():
            if k not in out or out.get(k) in (None, "", {}, []):
                if try_resolve_refs:
                    v = try_resolve_reference_nuxt(root, v)
                out[k] = v

    # Buyer/client flattening
    for d, path in iter_dicts_and_lists_nuxt(root):
        if not isinstance(d, dict):
            continue
        path_keys = {p for p in path if isinstance(p, str)}

        if "buyer" in d and isinstance(d["buyer"], dict):
            buyer_obj = d["buyer"]
            resolved_buyer = {}
            for bk, bv in buyer_obj.items():
                resolved_buyer[bk] = try_resolve_reference_nuxt(root, bv) if try_resolve_refs else bv
            if isinstance(resolved_buyer.get("location"), dict):
                loc = resolved_buyer["location"]
                if "city" in loc:
                    out.setdefault("buyer_location_city", loc["city"])
                if "countryTimezone" in loc:
                    out.setdefault("buyer_location_countryTimezone", loc["countryTimezone"])
                if "offsetFromUtcMillis" in loc:
                    out.setdefault("buyer_location_offsetFromUtcMillis", loc["offsetFromUtcMillis"])
                if "localTime" in loc:
                    out.setdefault("buyer_location_localTime", loc["localTime"])
            if isinstance(resolved_buyer.get("stats"), dict):
                st = resolved_buyer["stats"]
                if "activeAssignmentsCount" in st:
                    out.setdefault("buyer_stats_activeAssignmentsCount", st["activeAssignmentsCount"])
                if "hoursCount" in st:
                    out.setdefault("buyer_stats_hoursCount", st["hoursCount"])
                if "totalJobsWithHires" in st:
                    out.setdefault("buyer_stats_totalJobsWithHires", st["totalJobsWithHires"])
            if isinstance(resolved_buyer.get("jobs"), dict):
                jb = resolved_buyer["jobs"]
                if "openCount" in jb:
                    out.setdefault("buyer_jobs_openCount", jb["openCount"])
                if "postedCount" in jb:
                    out.setdefault("buyer_jobs_postedCount", jb["postedCount"])
            if isinstance(resolved_buyer.get("company"), dict):
                co = resolved_buyer["company"]
                if "contractDate" in co:
                    out.setdefault("buyer_company_contractDate", co["contractDate"])
                if "size" in co:
                    out.setdefault("buyer_company_size", co["size"])
            if isinstance(resolved_buyer.get("avgHourlyJobsRate"), dict) and "amount" in resolved_buyer["avgHourlyJobsRate"]:
                out.setdefault("buyer_avgHourlyJobsRate_amount", resolved_buyer["avgHourlyJobsRate"]["amount"])
            if "isEnterprise" in resolved_buyer and "enterpriseJob" not in out:
                out["enterpriseJob"] = bool(resolved_buyer.get("isEnterprise"))

        if "clientActivity" in d and isinstance(d["clientActivity"], dict):
            ca = d["clientActivity"]
            ca_resolved = {ck: try_resolve_reference_nuxt(root, cv) if try_resolve_refs else cv for ck, cv in ca.items()}
            if "invitationsSent" in ca_resolved:
                out.setdefault("clientActivity_invitationsSent", ca_resolved["invitationsSent"])
            if "totalHired" in ca_resolved:
                out.setdefault("clientActivity_totalHired", ca_resolved["totalHired"])
            if "totalInvitedToInterview" in ca_resolved:
                out.setdefault("clientActivity_totalInvitedToInterview", ca_resolved["totalInvitedToInterview"])
            if "unansweredInvites" in ca_resolved:
                out.setdefault("clientActivity_unansweredInvites", ca_resolved["unansweredInvites"])
            if "lastBuyerActivity" in ca_resolved:
                out.setdefault("lastBuyerActivity", ca_resolved["lastBuyerActivity"])

        if "buyer" in path_keys and "location" in path_keys:
            if "city" in d:
                out.setdefault("buyer_location_city", try_resolve_reference_nuxt(root, d.get("city")) if try_resolve_refs else d.get("city"))
            if "countryTimezone" in d:
                out.setdefault("buyer_location_countryTimezone", try_resolve_reference_nuxt(root, d.get("countryTimezone")) if try_resolve_refs else d.get("countryTimezone"))
            if "offsetFromUtcMillis" in d:
                out.setdefault("buyer_location_offsetFromUtcMillis", try_resolve_reference_nuxt(root, d.get("offsetFromUtcMillis")) if try_resolve_refs else d.get("offsetFromUtcMillis"))
            if "localTime" in d:
                out.setdefault("buyer_location_localTime", try_resolve_reference_nuxt(root, d.get("localTime")) if try_resolve_refs else d.get("localTime"))

        if "buyer" in path_keys and "stats" in path_keys:
            if "activeAssignmentsCount" in d:
                out.setdefault("buyer_stats_activeAssignmentsCount", try_resolve_reference_nuxt(root, d.get("activeAssignmentsCount")) if try_resolve_refs else d.get("activeAssignmentsCount"))
            if "hoursCount" in d:
                out.setdefault("buyer_stats_hoursCount", try_resolve_reference_nuxt(root, d.get("hoursCount")) if try_resolve_refs else d.get("hoursCount"))
            if "totalJobsWithHires" in d:
                out.setdefault("buyer_stats_totalJobsWithHires", try_resolve_reference_nuxt(root, d.get("totalJobsWithHires")) if try_resolve_refs else d.get("totalJobsWithHires"))

        if "buyer" in path_keys and "jobs" in path_keys:
            if "openCount" in d:
                out.setdefault("buyer_jobs_openCount", try_resolve_reference_nuxt(root, d.get("openCount")) if try_resolve_refs else d.get("openCount"))
            if "postedCount" in d:
                out.setdefault("buyer_jobs_postedCount", try_resolve_reference_nuxt(root, d.get("postedCount")) if try_resolve_refs else d.get("postedCount"))

        if "buyer" in path_keys and "company" in path_keys:
            if "contractDate" in d:
                out.setdefault("buyer_company_contractDate", try_resolve_reference_nuxt(root, d.get("contractDate")) if try_resolve_refs else d.get("contractDate"))
            if "size" in d:
                out.setdefault("buyer_company_size", try_resolve_reference_nuxt(root, d.get("size")) if try_resolve_refs else d.get("size"))

        if "buyer" in path_keys and "avgHourlyJobsRate" in path_keys and "amount" in d:
            out.setdefault("buyer_avgHourlyJobsRate_amount", try_resolve_reference_nuxt(root, d.get("amount")) if try_resolve_refs else d.get("amount"))

        if "enterpriseJobAdditionalInfo" in path_keys:
            out["enterpriseJob"] = True

        if "category" in path_keys:
            if "name" in d:
                out.setdefault("category_name", try_resolve_reference_nuxt(root, d.get("name")) if try_resolve_refs else d.get("name"))
            if "urlSlug" in d:
                out.setdefault("category_urlSlug", try_resolve_reference_nuxt(root, d.get("urlSlug")) if try_resolve_refs else d.get("urlSlug"))
        if "categoryGroup" in path_keys:
            if "name" in d:
                out.setdefault("categoryGroup_name", try_resolve_reference_nuxt(root, d.get("name")) if try_resolve_refs else d.get("name"))
            if "urlSlug" in d:
                out.setdefault("categoryGroup_urlSlug", try_resolve_reference_nuxt(root, d.get("urlSlug")) if try_resolve_refs else d.get("urlSlug"))

        if "budget" in path_keys and "amount" in d:
            out.setdefault("fixed_budget_amount", try_resolve_reference_nuxt(root, d.get("amount")) if try_resolve_refs else d.get("amount"))
            if not isinstance(out.get("type"), str):
                out["type"] = "fixed"

        if "requiredConnects" in d:
            out.setdefault("connects_required", try_resolve_reference_nuxt(root, d.get("requiredConnects")) if try_resolve_refs else d.get("requiredConnects"))

        if "isPhoneVerified" in d:
            out.setdefault("phone_verified", bool(try_resolve_reference_nuxt(root, d.get("isPhoneVerified")) if try_resolve_refs else d.get("isPhoneVerified")))

        if "isPremium" in d:
            out.setdefault("premium", bool(try_resolve_reference_nuxt(root, d.get("isPremium")) if try_resolve_refs else d.get("isPremium")))

        if "qualifications" in d and "qualifications" not in out:
            out["qualifications"] = try_resolve_reference_nuxt(root, d.get("qualifications")) if try_resolve_refs else d.get("qualifications")
        if "questions" in d and "questions" not in out:
            out["questions"] = try_resolve_reference_nuxt(root, d.get("questions")) if try_resolve_refs else d.get("questions")

        if "url" in d and "url" not in out:
            val = try_resolve_reference_nuxt(root, d.get("url")) if try_resolve_refs else d.get("url")
            if isinstance(val, str):
                out["url"] = val

    if "totalApplicants" in out and "applicants" not in out:
        out["applicants"] = out.get("totalApplicants")
    if "currencyCode" in out and "currency" not in out:
        out["currency"] = out.get("currencyCode")
    if "durationLabel" in out and "duration" not in out:
        out["duration"] = out.get("durationLabel")
    if "hourlyBudgetMin" in out and "hourly_min" not in out:
        out["hourly_min"] = out.get("hourlyBudgetMin")
    if "hourlyBudgetMax" in out and "hourly_max" not in out:
        out["hourly_max"] = out.get("hourlyBudgetMax")
    if "publishTime" in out and "ts_publish" not in out:
        out["ts_publish"] = out.get("publishTime")
    elif "postedOn" in out and "ts_publish" not in out:
        out["ts_publish"] = out.get("postedOn")
    if "createdOn" in out and "ts_create" not in out:
        out["ts_create"] = out.get("createdOn")
    elif "postedOn" in out and "ts_create" not in out:
        out["ts_create"] = out.get("postedOn")

    # Normalize URL
    if isinstance(out.get("url"), str) and out["url"].startswith("/"):
        out["url"] = "https://www.upwork.com" + out["url"]

    # Derive type if not string
    if not isinstance(out.get("type"), str):
        has_hourly_bounds = (
            isinstance(out.get("hourly_min"), (int, float)) or isinstance(out.get("hourly_max"), (int, float))
            or isinstance(out.get("hourlyBudgetMin"), (int, float)) or isinstance(out.get("hourlyBudgetMax"), (int, float))
        )
        if has_hourly_bounds:
            out["type"] = "hourly"
        elif isinstance(out.get("fixed_budget_amount"), (int, float)):
            out["type"] = "fixed"

    return out

def extract_nuxt_data_fallback(html: str) -> dict | None:
    """
    Parse __NUXT_DATA__ from HTML and extract job fields as a fallback.
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        script_tag = soup.find('script', id='__NUXT_DATA__')
        if script_tag and script_tag.string:
            inner = script_tag.string.strip()
        else:
            inner = extract_inner_script_nuxt_data(html)
        data = json.loads(inner)
        out = extract_job_fields_from_nuxt_data(data, try_resolve_refs=True)
        return out
    except Exception as e:
        if 'logger' in globals():
            logger.debug(f"NUXT_DATA fallback extraction failed: {e}")
        return None

def parse_attributes_from_window_nuxt(html: str, credentials_provided: bool, missing_fields: set[str]) -> dict:
    data = {}
    nuxt_data = extract_nuxt_json_using_js2py(html)
    if not nuxt_data:
        return data
    nuxt_job = None
    nuxt_buyer = None
    try:
        nuxt_job = nuxt_data['state']['jobDetails']['job']
        nuxt_buyer = nuxt_data['state']['jobDetails']['buyer']
    except Exception:
        return data

    # Job-level fields
    if 'title' in missing_fields:
        data['title'] = nuxt_job.get('title')
    if 'description' in missing_fields:
        data['description'] = nuxt_job.get('description')
    if 'fixed_budget_amount' in missing_fields and 'budget' in nuxt_job and 'amount' in nuxt_job['budget']:
        data['fixed_budget_amount'] = nuxt_job['budget']['amount']
    if ('hourly_min' in missing_fields or 'hourly_max' in missing_fields) and 'extendedBudgetInfo' in nuxt_job:
        if 'hourly_min' in missing_fields:
            data['hourly_min'] = nuxt_job['extendedBudgetInfo'].get('hourlyBudgetMin')
        if 'hourly_max' in missing_fields:
            data['hourly_max'] = nuxt_job['extendedBudgetInfo'].get('hourlyBudgetMax')
    if 'duration' in missing_fields and 'engagementDuration' in nuxt_job:
        data['duration'] = nuxt_job['engagementDuration'].get('label')
    if 'level' in missing_fields and 'contractorTier' in nuxt_job:
        tier = nuxt_job['contractorTier']
        if tier == 1:
            data['level'] = 'ENTRY_LEVEL'
        elif tier == 2:
            data['level'] = 'INTERMEDIATE'
        elif tier == 3:
            data['level'] = 'EXPERT'
        else:
            data['level'] = tier
    if 'type' in missing_fields and 'type' in nuxt_job:
        data['type'] = 'Hourly' if nuxt_job['type'] == 2 else 'Fixed-price' if nuxt_job['type'] == 1 else None
    # skills from sands
    if 'skills' in missing_fields and 'sands' in nuxt_data['state']['jobDetails']:
        skills = []
        sands = nuxt_data['state']['jobDetails']['sands']
        if 'ontologySkills' in sands:
            for group in sands['ontologySkills']:
                for child in group.get('children', []):
                    if 'name' in child:
                        skills.append(child['name'])
        if 'additionalSkills' in sands:
            for skill in sands['additionalSkills']:
                if 'name' in skill:
                    skills.append(skill['name'])
        if skills:
            data['skills'] = skills
    # client activity
    if 'clientActivity_totalHired' in missing_fields or 'clientActivity_totalInvitedToInterview' in missing_fields or 'applicants' in missing_fields or 'clientActivity_invitationsSent' in missing_fields or 'clientActivity_unansweredInvites' in missing_fields:
        ca = nuxt_job.get('clientActivity', {})
        if 'clientActivity_totalHired' in missing_fields:
            data['clientActivity_totalHired'] = ca.get('totalHired')
        if 'clientActivity_totalInvitedToInterview' in missing_fields:
            data['clientActivity_totalInvitedToInterview'] = ca.get('totalInvitedToInterview')
        if 'applicants' in missing_fields:
            data['applicants'] = ca.get('totalApplicants')
        if 'clientActivity_invitationsSent' in missing_fields:
            data['clientActivity_invitationsSent'] = ca.get('invitationsSent')
        if 'clientActivity_unansweredInvites' in missing_fields:
            data['clientActivity_unansweredInvites'] = ca.get('unansweredInvites')
        if 'lastBuyerActivity' in missing_fields:
            data['lastBuyerActivity'] = ca.get('lastBuyerActivity')
    # credentials-gated connects
    if credentials_provided and 'connects_required' in missing_fields:
        connects = nuxt_data['state']['jobDetails'].get('connects')
        if connects and 'requiredConnects' in connects:
            data['connects_required'] = connects['requiredConnects']
    # buyer fields
    if nuxt_buyer:
        if 'payment_verified' in missing_fields and 'isPaymentMethodVerified' in nuxt_buyer:
            data['payment_verified'] = nuxt_buyer['isPaymentMethodVerified']
        if 'buyer_company_contractDate' in missing_fields and 'company' in nuxt_buyer and 'contractDate' in nuxt_buyer['company']:
            data['buyer_company_contractDate'] = nuxt_buyer['company']['contractDate']
        if 'buyer_location_countryTimezone' in missing_fields and 'location' in nuxt_buyer and 'countryTimezone' in nuxt_buyer['location']:
            data['buyer_location_countryTimezone'] = nuxt_buyer['location']['countryTimezone']
        if 'buyer_location_offsetFromUtcMillis' in missing_fields and 'location' in nuxt_buyer and 'offsetFromUtcMillis' in nuxt_buyer['location']:
            data['buyer_location_offsetFromUtcMillis'] = nuxt_buyer['location']['offsetFromUtcMillis']
        if 'buyer_stats_totalJobsWithHires' in missing_fields and 'stats' in nuxt_buyer and 'totalJobsWithHires' in nuxt_buyer['stats']:
            data['buyer_stats_totalJobsWithHires'] = nuxt_buyer['stats']['totalJobsWithHires']
        if 'enterpriseJob' in missing_fields and 'isEnterprise' in nuxt_buyer:
            data['enterpriseJob'] = nuxt_buyer['isEnterprise']
    # category/categoryGroup/currency/contractorTier/isContractToHire etc
    if 'category_name' in missing_fields and 'category' in nuxt_job and 'name' in nuxt_job['category']:
        data['category_name'] = nuxt_job['category']['name']
    if 'category_urlSlug' in missing_fields and 'category' in nuxt_job and 'urlSlug' in nuxt_job['category']:
        data['category_urlSlug'] = nuxt_job['category']['urlSlug']
    if 'categoryGroup_name' in missing_fields and 'categoryGroup' in nuxt_job and 'name' in nuxt_job['categoryGroup']:
        data['categoryGroup_name'] = nuxt_job['categoryGroup']['name']
    if 'categoryGroup_urlSlug' in missing_fields and 'categoryGroup' in nuxt_job and 'urlSlug' in nuxt_job['categoryGroup']:
        data['categoryGroup_urlSlug'] = nuxt_job['categoryGroup']['urlSlug']
    if 'contractorTier' in missing_fields and 'contractorTier' in nuxt_job:
        data['contractorTier'] = nuxt_job['contractorTier']
    if 'currency' in missing_fields and 'budget' in nuxt_job and 'currencyCode' in nuxt_job['budget']:
        data['currency'] = nuxt_job['budget']['currencyCode']
    if 'isContractToHire' in missing_fields and 'isContractToHire' in nuxt_job:
        data['isContractToHire'] = nuxt_job['isContractToHire']
    if 'numberOfPositionsToHire' in missing_fields and 'numberOfPositionsToHire' in nuxt_job:
        data['numberOfPositionsToHire'] = nuxt_job['numberOfPositionsToHire']
    if 'premium' in missing_fields and 'isPremium' in nuxt_job:
        data['premium'] = nuxt_job['isPremium']
    if 'ts_create' in missing_fields and 'createdOn' in nuxt_job:
        data['ts_create'] = nuxt_job['createdOn']
    if 'ts_publish' in missing_fields and 'publishTime' in nuxt_job:
        data['ts_publish'] = nuxt_job['publishTime']
    if 'qualifications' in missing_fields and 'qualifications' in nuxt_job:
        data['qualifications'] = nuxt_job['qualifications']
    if 'questions' in missing_fields and 'questions' in nuxt_job:
        data['questions'] = nuxt_job['questions']
    return {k: v for k, v in data.items() if k in ORDERED_FIELDS}

def parse_attributes_from_html(html: str, job_id: str, credentials_provided: bool, missing_fields: set[str]) -> dict:
    data = {}
    soup = BeautifulSoup(html, 'html.parser')
    # Category from title
    if 'category' in missing_fields:
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if ' - ' in title_text:
                data['category'] = title_text.split(' - ')[-1].strip()
    # Phone verified
    if 'phone_verified' in missing_fields:
        phone_verified = False
        for parent in soup.find_all('div', class_='d-flex'):
            icon = parent.find('div', class_='payment-verified')
            strong = parent.find('strong')
            if icon and strong and 'Phone number verified' in strong.get_text(strip=True):
                phone_verified = True
                break
        data['phone_verified'] = phone_verified
    job_details_div = soup.find('div', class_='job-details-content')
    if not job_details_div:
        return {k: v for k, v in data.items() if k in ORDERED_FIELDS}

    # features block
    features_ul = soup.find('ul', class_='features')
    hourly_vals = []
    if features_ul:
        for item in features_ul.find_all('li'):
            strong = item.find('strong')
            desc_div = item.find('div', class_='description')
            desc_text = desc_div.get_text(strip=True) if desc_div else None
            # fixed budget
            if 'fixed_budget_amount' in missing_fields and desc_div and desc_text == 'Fixed-price':
                budget_div = item.find('div', {'data-test': 'BudgetAmount'})
                if budget_div:
                    strong_budget = budget_div.find('strong')
                    if strong_budget:
                        budget_text = strong_budget.get_text(strip=True)
                        budget_match = re.search(r'\$([\d,.]+)', budget_text)
                        if budget_match:
                            try:
                                data['fixed_budget_amount'] = float(budget_match.group(1).replace(',', ''))
                            except Exception:
                                pass
            # type
            if 'type' in missing_fields and desc_text in ['Hourly', 'Fixed-price']:
                data['type'] = desc_text
            # duration
            if 'duration' in missing_fields and desc_text and 'Duration' in desc_text and strong:
                data['duration'] = strong.get_text(strip=True)
            # level
            if 'level' in missing_fields and desc_text and 'Experience Level' in desc_text and strong:
                level_text = strong.get_text(strip=True).lower()
                if 'entry' in level_text:
                    data['level'] = 'ENTRY_LEVEL'
                elif 'intermediate' in level_text:
                    data['level'] = 'INTERMEDIATE'
                elif 'expert' in level_text:
                    data['level'] = 'EXPERT'
                else:
                    data['level'] = strong.get_text(strip=True)
            # hourly min/max values collection
            if ('hourly_min' in missing_fields or 'hourly_max' in missing_fields) and strong:
                text = strong.get_text(strip=True)
                if text.startswith('$'):
                    try:
                        hourly_vals.append(float(text.replace('$','').replace(',','')))
                    except Exception:
                        pass
    if 'hourly_min' in missing_fields or 'hourly_max' in missing_fields:
        if len(hourly_vals) >= 2:
            if 'hourly_min' in missing_fields:
                data['hourly_min'] = hourly_vals[0]
            if 'hourly_max' in missing_fields:
                data['hourly_max'] = hourly_vals[1]
        elif len(hourly_vals) == 1 and 'hourly_min' in missing_fields:
            data['hourly_min'] = hourly_vals[0]

    # Title
    if 'title' in missing_fields:
        title_tag = job_details_div.find('h4')
        if title_tag:
            data['title'] = title_tag.get_text(strip=True)
    # Description
    if 'description' in missing_fields:
        desc_div = job_details_div.find('div', {'data-test': 'Description'})
        if desc_div:
            desc_p = desc_div.find('p')
            if desc_p:
                data['description'] = desc_p.get_text(separator='\n', strip=True)

    # Client info via top features list
    client_features = soup.find('ul', class_='features')
    if client_features:
        for li in client_features.find_all('li', recursive=False):
            data_qa = li.get('data-qa', '')
            if data_qa == 'client-location' and ('client_country' in missing_fields or 'buyer_location_city' in missing_fields or 'buyer_location_localTime' in missing_fields):
                strong = li.find('strong')
                if strong and 'client_country' in missing_fields:
                    data['client_country'] = strong.get_text(strip=True)
                div = li.find('div')
                if div:
                    spans = div.find_all('span', class_='nowrap')
                    if len(spans) > 0 and 'buyer_location_city' in missing_fields:
                        data['buyer_location_city'] = spans[0].get_text(strip=True)
                    if len(spans) > 1 and 'buyer_location_localTime' in missing_fields:
                        data['buyer_location_localTime'] = spans[1].get_text(strip=True)
            elif data_qa == 'client-job-posting-stats' and ('buyer_jobs_postedCount' in missing_fields or 'buyer_jobs_openCount' in missing_fields):
                strong = li.find('strong')
                if strong and 'buyer_jobs_postedCount' in missing_fields:
                    m = re.search(r'(\d+)\s+jobs posted', strong.get_text())
                    if m:
                        data['buyer_jobs_postedCount'] = int(m.group(1))
                div = li.find('div')
                if div and 'buyer_jobs_openCount' in missing_fields:
                    m = re.search(r'(\d+)\s+open jobs?', div.get_text())
                    if m:
                        data['buyer_jobs_openCount'] = int(m.group(1))
            elif li.find('strong', {'data-qa': 'client-spend'}) and ('client_total_spent' in missing_fields or 'client_hires' in missing_fields or 'buyer_stats_activeAssignmentsCount' in missing_fields):
                spend_strong = li.find('strong', {'data-qa': 'client-spend'})
                if spend_strong and 'client_total_spent' in missing_fields:
                    m = re.search(r'\$([\dKk,\.]+)', spend_strong.get_text())
                    if m:
                        val = m.group(1).replace(',', '')
                        try:
                            data['client_total_spent'] = float(val.replace('K','').replace('k','')) * 1000 if ('K' in val or 'k' in val) else float(val)
                        except Exception:
                            pass
                hires_div = li.find('div', {'data-qa': 'client-hires'})
                if hires_div:
                    hires_text = hires_div.get_text()
                    if 'client_hires' in missing_fields:
                        m = re.search(r'(\d+)\s+hires', hires_text)
                        if m:
                            data['client_hires'] = int(m.group(1))
                            if 'clientActivity_totalHired' in missing_fields:
                                data['clientActivity_totalHired'] = int(m.group(1))
                    if 'buyer_stats_activeAssignmentsCount' in missing_fields:
                        m = re.search(r'(\d+)\s+active', hires_text)
                        if m:
                            data['buyer_stats_activeAssignmentsCount'] = int(m.group(1))
            elif li.find('strong', {'data-qa': 'client-hourly-rate'}) and ('buyer_avgHourlyJobsRate_amount' in missing_fields or 'buyer_stats_hoursCount' in missing_fields):
                rate_strong = li.find('strong', {'data-qa': 'client-hourly-rate'})
                if rate_strong and 'buyer_avgHourlyJobsRate_amount' in missing_fields:
                    m = re.search(r'\$([\d\.]+)', rate_strong.get_text())
                    if m:
                        data['buyer_avgHourlyJobsRate_amount'] = float(m.group(1))
                hours_div = li.find('div', {'data-qa': 'client-hours'})
                if hours_div and 'buyer_stats_hoursCount' in missing_fields:
                    m = re.search(r'(\d+)', hours_div.get_text().replace(',', ''))
                    if m:
                        data['buyer_stats_hoursCount'] = int(m.group(1))
            elif data_qa == 'client-company-profile' and ('client_industry' in missing_fields or 'client_company_size' in missing_fields):
                industry_strong = li.find('strong', {'data-qa': 'client-company-profile-industry'})
                if industry_strong and 'client_industry' in missing_fields:
                    data['client_industry'] = industry_strong.get_text(strip=True)
                size_div = li.find('div', {'data-qa': 'client-company-profile-size'})
                if size_div and 'client_company_size' in missing_fields:
                    data['client_company_size'] = size_div.get_text(strip=True)

    # Client section details (rating, reviews, etc.)
    if any(k in missing_fields for k in ('client_rating','client_reviews','buyer_jobs_postedCount','buyer_jobs_openCount','client_country','buyer_location_city','buyer_location_localTime')):
        client_section = (
            job_details_div.find('div', {'data-test': 'about-client-container'})
            or job_details_div.find('div', {'data-test': 'AboutClientUser'})
            or job_details_div.find('div', {'data-test': 'AboutClientVisitor'})
        )
        if client_section:
            if 'client_rating' in missing_fields:
                rating_div = client_section.find('div', class_='air3-rating-value-text')
                if rating_div:
                    data['client_rating'] = rating_div.get_text(strip=True)
            if 'client_reviews' in missing_fields:
                reviews_span = client_section.find('span', class_='nowrap mt-1')
                if reviews_span:
                    data['client_reviews'] = reviews_span.get_text(strip=True)
            # Also scan nested features for location/stats if still missing
            features_ul = client_section.find('ul', class_='features')
            if features_ul:
                for li in features_ul.find_all('li', recursive=False):
                    data_qa = li.get('data-qa', '')
                    if data_qa == 'client-location':
                        strong = li.find('strong')
                        if strong and 'client_country' in missing_fields:
                            data['client_country'] = strong.get_text(strip=True)
                        div = li.find('div')
                        if div:
                            spans = div.find_all('span', class_='nowrap')
                            if len(spans) > 0 and 'buyer_location_city' in missing_fields:
                                data['buyer_location_city'] = spans[0].get_text(strip=True)
                            if len(spans) > 1 and 'buyer_location_localTime' in missing_fields:
                                data['buyer_location_localTime'] = spans[1].get_text(strip=True)
                    elif data_qa == 'client-job-posting-stats':
                        strong = li.find('strong')
                        if strong and 'buyer_jobs_postedCount' in missing_fields:
                            m = re.search(r'(\d+)\s+jobs posted', strong.get_text())
                            if m:
                                data['buyer_jobs_postedCount'] = int(m.group(1))
                        div = li.find('div')
                        if div and 'buyer_jobs_openCount' in missing_fields:
                            m = re.search(r'(\d+)\s+open jobs?', div.get_text())
                            if m:
                                data['buyer_jobs_openCount'] = int(m.group(1))

    # Activity on this job
    if 'clientActivity_totalHired' in missing_fields or 'clientActivity_totalInvitedToInterview' in missing_fields:
        activity_section = job_details_div.find('section', {'data-test': 'ClientActivity'})
        if activity_section:
            for li in activity_section.find_all('li', class_='ca-item'):
                title_span = li.find('span', class_='title')
                value_div = li.find('div', class_='value')
                if title_span and value_div:
                    title = title_span.get_text(strip=True)
                    value = value_div.get_text(strip=True)
                    if title.startswith('Hires') and 'clientActivity_totalHired' in missing_fields:
                        try:
                            data['clientActivity_totalHired'] = int(value)
                        except Exception:
                            pass
                    elif title.startswith('Interviewing') and 'clientActivity_totalInvitedToInterview' in missing_fields:
                        try:
                            data['clientActivity_totalInvitedToInterview'] = int(value)
                        except Exception:
                            pass

    # Invites and unanswered invites
    if 'clientActivity_invitationsSent' in missing_fields or 'clientActivity_unansweredInvites' in missing_fields:
        for li in job_details_div.find_all('li'):
            text = li.get_text()
            if 'clientActivity_invitationsSent' in missing_fields and 'Invites sent:' in text:
                val_div = li.find('div', class_='value')
                if val_div:
                    data['clientActivity_invitationsSent'] = val_div.get_text(strip=True)
                else:
                    m = re.search(r'Invites sent:\s*(\d+)', li.get_text(strip=True))
                    if m:
                        data['clientActivity_invitationsSent'] = m.group(1)
            if 'clientActivity_unansweredInvites' in missing_fields and 'Unanswered invites:' in text:
                val_div = li.find('div', class_='value')
                if val_div:
                    data['clientActivity_unansweredInvites'] = val_div.get_text(strip=True)
                else:
                    m = re.search(r'Unanswered invites:\s*(\d+)', li.get_text(strip=True))
                    if m:
                        data['clientActivity_unansweredInvites'] = m.group(1)

    # Connects required
    if 'connects_required' in missing_fields:
        connects_div = job_details_div.find('div', {'data-test': 'ConnectsDesktop'})
        if connects_div:
            connects_text = connects_div.get_text(strip=True)
            match = re.search(r'Required Connects to submit a proposal:\s*(\d+)', connects_text)
            if match:
                data['connects_required'] = int(match.group(1))

    # Payment method verified
    if 'payment_verified' in missing_fields:
        payment_verified = False
        if job_details_div.find(string=re.compile('Payment method verified')):
            payment_verified = True
        data['payment_verified'] = payment_verified

    return {k: v for k, v in data.items() if k in ORDERED_FIELDS}

def parse_attributes_from_nuxt_data_attributes(html: str, missing_fields: set[str]) -> dict:
    out = extract_nuxt_data_fallback(html)
    if not out:
        return {}
    # Normalize type from lowercase to UI style
    if 'type' in out and out.get('type') in ('hourly', 'fixed'):
        out['type'] = 'Hourly' if out['type'] == 'hourly' else 'Fixed-price'
    return {k: v for k, v in out.items() if k in missing_fields and k in ORDERED_FIELDS}

def extract_job_attributes(html: str, job_id: str, credentials_provided: bool) -> dict:
    result: dict = {"job_id": job_id}
    missing = set(ORDERED_FIELDS)
    missing.discard('url')
    # Step 1: window.__NUXT__ JSON via js2py
    add1 = parse_attributes_from_window_nuxt(html, credentials_provided, missing)
    result = fill_missing_fields(result, add1, set(ORDERED_FIELDS))
    missing = {k for k in ORDERED_FIELDS if k not in result or result[k] in (None, "", [], {})}
    # Step 2: HTML parse
    add2 = parse_attributes_from_html(html, job_id, credentials_provided, missing)
    result = fill_missing_fields(result, add2, set(ORDERED_FIELDS))
    missing = {k for k in ORDERED_FIELDS if k not in result or result[k] in (None, "", [], {})}
    # Step 3: __NUXT_DATA__ fallback
    if missing:
        add3 = parse_attributes_from_nuxt_data_attributes(html, missing)
        result = fill_missing_fields(result, add3, set(ORDERED_FIELDS))
    return result



ORDERED_FIELDS = [
    "applicants",
    "buyer_avgHourlyJobsRate_amount",
    "buyer_company_contractDate",
    "buyer_jobs_openCount",
    "buyer_jobs_postedCount",
    "buyer_location_city",
    "buyer_location_countryTimezone",
    "buyer_location_localTime",
    "buyer_location_offsetFromUtcMillis",
    "buyer_stats_activeAssignmentsCount",
    "buyer_stats_hoursCount",
    "buyer_stats_totalJobsWithHires",
    "category",
    "categoryGroup_name",
    "categoryGroup_urlSlug",
    "category_name",
    "category_urlSlug",
    "clientActivity_invitationsSent",
    "clientActivity_totalHired",
    "clientActivity_totalInvitedToInterview",
    "clientActivity_unansweredInvites",
    "client_company_size",
    "client_country",
    "client_hires",
    "client_industry",
    "client_rating",
    "client_reviews",
    "client_total_spent",
    "connects_required",
    "contractorTier",
    "currency",
    "description",
    "duration",
    "enterpriseJob",
    "fixed_budget_amount",
    "hourly_max",
    "hourly_min",
    "isContractToHire",
    "job_id",
    "lastBuyerActivity",
    "level",
    "numberOfPositionsToHire",
    "payment_verified",
    "phone_verified",
    "premium",
    "qualifications",
    "questions",
    "skills",
    "title",
    "ts_create",
    "ts_publish",
    "type",
    "url",
]

def fill_missing_fields(dest: dict, src: dict, allowed_fields: set[str]) -> dict:
    for k, v in src.items():
        if k in allowed_fields and (k not in dest or dest[k] in (None, "", [], {})):
            dest[k] = v
    return dest

def playwright_cookies_to_requests(cookies):
    """
    Convert Playwright cookies to a RequestsCookieJar.

    :param cookies: List of cookies from Playwright context
    :type cookies: list[dict]
    :return: RequestsCookieJar containing the cookies
    :rtype: requests.cookies.RequestsCookieJar
    """
    jar = requests.cookies.RequestsCookieJar()
    for cookie in cookies:
        jar.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
    return jar

async def get_requests_session_from_playwright(context, page, max_retries=3, retry_delay=1):
    """
    Extract cookies and user-agent from Playwright context and page, and build a requests.Session.
    Retries user-agent extraction if the execution context is destroyed.

    :param context: Playwright BrowserContext object
    :type context: BrowserContext
    :param page: Playwright Page object
    :type page: Page
    :param max_retries: Maximum number of retries for user-agent extraction if execution context is destroyed (default: 3)
    :type max_retries: int
    :param retry_delay: Delay in seconds between retries (default: 1)
    :type retry_delay: int
    :return: requests.Session object with cookies and user-agent set
    :rtype: requests.Session
    """
    cookies = await context.cookies()
    user_agent = None
    for attempt in range(1, max_retries + 1):
        try:
            user_agent = await page.evaluate("() => navigator.userAgent")
            break
        except Exception as e:
            if "Execution context was destroyed" in str(e):
                logger.warning(f"Attempt {attempt}: Execution context destroyed while getting user-agent. Retrying...")
                await asyncio.sleep(retry_delay)
                if attempt == max_retries:
                    logger.error("Failed to get user-agent after multiple retries due to navigation/context loss. Using fallback user-agent.")
                    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            else:
                logger.error(f"Unexpected error while getting user-agent: {e}. Using fallback user-agent.")
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
                break
    if not user_agent:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    session = requests.Session()
    session.cookies = playwright_cookies_to_requests(cookies)
    session.headers.update({'User-Agent': user_agent})
    return session


def get_job_urls_requests(session, search_querys, search_urls, limit=50):
    """
    For each search query and URL, use requests to fetch the page and extract job URLs.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param search_querys: List of search query strings
    :type search_querys: list[str]
    :param search_urls: List of Upwork search URLs corresponding to the queries
    :type search_urls: list[str]
    :param limit: Maximum number of job URLs to extract per query
    :type limit: int, optional
    :return: Dictionary mapping each query to a list of job URLs
    :rtype: dict[str, list[str]]
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
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                articles = soup.find_all('article')
                page_hrefs = []
                for i, article in enumerate(articles):
                    a_tag = article.find('a', attrs={'data-test': 'job-tile-title-link UpLink'})
                    if not a_tag:
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
                logger.debug(f"Found {len(page_hrefs)} jobs on page {page_num} for query '{query}'")
                if page_num == pages_needed:
                    page_hrefs = page_hrefs[:jobs_from_last_page]
                all_hrefs.extend(page_hrefs)
                if len(all_hrefs) >= limit:
                    all_hrefs = all_hrefs[:limit]
                    break
            except Exception as e:
                logger.exception(f"[requests] Skipping page {page_num} due to navigation failures: {e}")
                continue
        search_results[query] = all_hrefs
    logger.debug(f"[requests] Search results: {search_results}\n")
    return search_results


def fetch_job_detail(session, url, credentials_provided):
    """
    Fetch job detail page and extract job attributes.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param url: URL of the job detail page
    :type url: str
    :param credentials_provided: Whether Upwork credentials are provided (affects restricted fields)
    :type credentials_provided: bool
    :return: Dictionary of job attributes, or None if failed
    :rtype: dict or None
    """
    try:
        logger.debug(f"[requests] Processing URL: {url}")
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text
        job_id_match = re.search(r'~([0-9a-zA-Z]+)', url)
        job_id = job_id_match.group(1) if job_id_match else "0"
        attrs = extract_job_attributes(html, job_id, credentials_provided)
        attrs['url'] = url
        return attrs
    except Exception:
        logger.debug(f"[requests] Failed to process {url}")
        return None

def browser_worker_requests(session, job_urls, credentials_provided, max_workers=20):
    """
    Fetch job details in parallel using ThreadPoolExecutor for speed.

    :param session: requests.Session object with cookies and headers set
    :type session: requests.Session
    :param job_urls: List of job detail page URLs to fetch
    :type job_urls: list[str]
    :param credentials_provided: Whether Upwork credentials are provided (affects restricted fields)
    :type credentials_provided: bool
    :param max_workers: Maximum number of worker threads to use
    :type max_workers: int, optional
    :return: List of job attribute dictionaries
    :rtype: list[dict]
    """
    job_attributes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(fetch_job_detail, session, url, credentials_provided)
            for url in job_urls
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                job_attributes.append(result)
    return job_attributes


async def main(jsonInput: dict) -> list[dict]:
    """
    Main entry point for the Upwork Job Scraper. Orchestrates browser setup, login, job search, and extraction.

    :param jsonInput: Input dictionary containing credentials, search, and general parameters
    :type jsonInput: dict
    :return: List of job attribute dictionaries
    :rtype: list[dict]
    """
    logger.info("🏁 Starting Upwork Job Scraper...")
    # log the current time
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
    
    search_params = {
  "contract_to_hire": False,
  "expertise_level_number": [
    "1",
    "2",
    "3"
  ],
  "fixed": True,
  "fixed_max": 70,
  "fixed_min": 30,
  "hires_max": 0,
  "hires_min": 2,
  "hourly": True,
  "hourly_max": 50,
  "hourly_min": 10,
  "limit": 100,
  "log_level": "DEBUG",
  "password": "4wrTYj7w3Q6sKF",
  "payment_verified": False,
  "previous_clients": False,
  "proposal_max": 0,
  "proposal_min": 0,
  "query": "Workflow Automation",
  "search_any": "tines zapier make.com n8n",
  "sort": "relevance",
  "username": "ditto@calebwelsh.com",
  "category": [],
  "fixed_price_catagory_num": [],
  "workload": [],
  "projectDuration": []
}
    # If still not present, fallback to defaults
    if not search_params:
        search_params = {}
    # Extract general params
    general_params = jsonInput.get('general', {})
    save_csv = general_params.get('save_csv', False)

    # Normalize search params and get limit
    buffer = 20
    normalized_search_params, limit = normalize_search_params(search_params, credentials_provided, buffer)

    # Build search URL using the function
    logger.info("🏗️  Building search URL...")
    search_url = build_upwork_search_url(normalized_search_params)
    logger.debug(f"Search URL: {search_url}")

    # Visit Upwork login page
    login_url = "https://www.upwork.com/ab/account-security/login"

    NUM_DETAIL_WORKERS = 25

    search_queries = [search_params.get('query', search_params.get('search_any', 'search'))]
    search_urls = [search_url]
    # Only one browser for login/captcha
    async with AsyncCamoufox(headless=True, geoip=True, humanize=True, i_know_what_im_doing=True, config={'forceScopeAccess': True}, disable_coop=True) as browser:
        logger.info("🌐 Creating browser/context/page for login...")
        try:
            context = await browser.new_context()
            page = await context.new_page()
        except Exception as e:
            logger.error(f"⚠️ Error creating browser: {e}")
            sys.exit(1)
        try:
            logger.info("🔒 Solving Captcha and Logging in...")
            page, context = await login_and_solve(page, context, username, password, search_url, login_url, credentials_provided)
        except Exception as e:
            logger.error(f"⚠️ Error logging in: {e}")
            sys.exit(1)
        # Extract cookies and user-agent, build requests session
        session = await get_requests_session_from_playwright(context, page)
    # Use requests for all scraping
    try:
        logger.info("💼 Getting Related Jobs...")
        job_urls_dict = get_job_urls_requests(session, search_queries, search_urls, limit=limit)
        job_urls = list(job_urls_dict.values())[0]
        logger.debug(f"Got {len(job_urls)} job URLs.")
    except Exception as e:
        logger.error(f"⚠️ Error getting jobs: {e}")
        sys.exit(1)
    # Process jobs with requests
    try:
        logger.info("🏢 Getting Job Attributes with requests...")
        job_attributes = browser_worker_requests(session, job_urls, credentials_provided, max_workers=NUM_DETAIL_WORKERS)
    except Exception as e:
        logger.error(f"⚠️ Error getting job attributes: {e}")
        sys.exit(1)
    # Filter out jobs where Nuxt data was missing (i.e., job is None)
    # job_attributes = [job for job in job_attributes if job is not None and all(v is not None for v in job.values())]
    logger.debug(f"job_attributes after filter: {len(job_attributes)}")
    # Trim to the original limit
    logger.debug(f"limit: {limit-buffer}")
    job_attributes = job_attributes[:limit-buffer]
    # Push to Apify dataset if running on Apify
    if os.environ.get("ACTOR_INPUT_KEY"):
        for item in job_attributes:
            await Actor.push_data(item)
    if save_csv:
        df = pd.DataFrame(job_attributes)
        df = df.sort_index(axis=1)
        df.to_csv(f'data/jobs/csv/job_results_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', index=False)
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
    args = parser.parse_args()

    # set logger
    logger_obj = Logger(level="DEBUG")
    logger = logger_obj.get_logger()

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
    # load from apify
    elif os.environ.get("ACTOR_INPUT_KEY"):
        from apify import Actor

        async def run_actor():
            # Initialize the Actor (fetches env, sets up storage, etc.)
            await Actor.init()
            # Pull input.json from the default KVS and parse it
            run_data = await Actor.get_input()
            # convert to expected json
            search_data = run_data.copy()
            input_data = {
                'credentials': {
                    'username': search_data.pop('username', None),
                    'password': search_data.pop('password', None)
                },
                'search': search_data,
                'general': {}
            }
            # set logger
            log_level = search_data.pop('log_level', None)
            if log_level:
                logger_obj = Logger(level=log_level)
                logger = logger_obj.get_logger()
            # Run your existing scraper logic
            logger.debug(f"input_data: {input_data}")
            result = await main(input_data)
            # exit
            await Actor.exit()
        # start
        asyncio.run(run_actor())
        sys.exit(0)
    # load from config.toml
    else:
        from utils.settings import config
        input_data = {
            'credentials': {
                'username': config['Credentials']['username'],
                'password': config['Credentials']['password']
            },
            'search': config.get('Search', {}),
            'general': config.get('General', {})
        }

    logger.debug(f"input_data: {input_data}")
    asyncio.run(main(input_data))
    sys.exit(0)
