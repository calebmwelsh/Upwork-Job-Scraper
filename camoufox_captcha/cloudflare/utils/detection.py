from typing import Literal, Union
import asyncio

from playwright.async_api import ElementHandle, Frame, Page

from utils.logger import Logger
logger = Logger().get_logger()


from playwright._impl._errors import Error as PlaywrightError

async def safe_query(page, selector, retries=3, delay=2):
    for attempt in range(retries):
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
            return await page.query_selector(selector)
        except PlaywrightError as e:
            if 'Execution context was destroyed' in str(e) and attempt < retries-1:
                logger.debug(f"Execution context was destroyed in detection.py, retrying... {attempt}")
                await asyncio.sleep(delay)
                continue
            raise
        

# selectors for detecting Cloudflare interstitial challenge (page)
CF_INTERSTITIAL_INDICATORS_SELECTORS = [
    'script[src*="/cdn-cgi/challenge-platform/"]',
]

# selectors for detecting Cloudflare turnstile challenge (small embedded captcha)
CF_TURNSTILE_INDICATORS_SELECTORS = [
    'input[name="cf-turnstile-response"]',
    'script[src*="challenges.cloudflare.com/turnstile/v0"]',
]


async def detect_cloudflare_challenge(
        queryable: Union[Page, Frame, ElementHandle],
        challenge_type: Literal['turnstile', 'interstitial'] = 'turnstile'
) -> bool:
    """
    Detect if a Cloudflare challenge is present in the provided queryable object by checking for specific predefined selectors

    :param queryable: Page, Frame, ElementHandle
    :param challenge_type: Type of challenge to detect ('turnstile' or 'interstitial')
    :return: True if Cloudflare challenge is detected, False otherwise
    """

    selectors = CF_TURNSTILE_INDICATORS_SELECTORS if challenge_type == 'turnstile' else CF_INTERSTITIAL_INDICATORS_SELECTORS
    for selector in selectors:
        # element = await queryable.query_selector(selector)
        element = await safe_query(queryable, selector)
        if not element:
            continue
        logger.debug(f"Cloudflare {challenge_type} challenge detected by selector: {selector}")
        return True

    return False
