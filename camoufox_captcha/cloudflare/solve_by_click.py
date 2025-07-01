import asyncio
import logging
from typing import Optional, Union, Literal

from playwright.async_api import Page, BrowserContext, ElementHandle, Frame, TimeoutError as PlaywrightTimeoutError 
from playwright._impl._errors import TargetClosedError, Error as CrashedError

from utils.logger import Logger
logger = Logger().get_logger()

from camoufox_captcha.cloudflare.utils.detection import detect_cloudflare_challenge
from camoufox_captcha.cloudflare.utils.dom_helpers import get_ready_checkbox
from camoufox_captcha.common.detection import detect_expected_content
from camoufox_captcha.common.shadow_root import search_shadow_root_iframes, search_shadow_root_elements


async def solve_cloudflare_by_click(
        queryable: Union[Page, Frame, ElementHandle],
        browser_context: BrowserContext,
        challenge_type: Literal["interstitial", "turnstile"] = "interstitial",
        expected_content_selector: Optional[str] = None,
        solve_attempts: int = 3,
        solve_click_delay: int = 6,
        wait_checkbox_attempts: int = 10,
        wait_checkbox_delay: int = 6,
        checkbox_click_attempts: int = 3,
        attempt_delay: int = 5
) -> bool:
    """
    Solve Cloudflare challenge by searching for & clicking the checkbox input

    :param queryable: Page, Frame, ElementHandle
    :param challenge_type: Type of Cloudflare challenge: "interstitial" or "turnstile"
    :param expected_content_selector: Optional CSS selector to verify page content is accessible after solving
    :param solve_attempts: Maximum number of attempts to solve the Cloudflare challenge
    :param solve_click_delay: Delay after clicking the checkbox to allow Cloudflare to process the click
    :param wait_checkbox_attempts: Maximum number of attempts to find the checkbox and wait for it to be ready
    :param wait_checkbox_delay: Delay between wait_checkbox_attempts in seconds to find the checkbox and wait for it to be ready
    :param checkbox_click_attempts: Maximum number of attempts to click the checkbox
    :param attempt_delay: Delay between solve attempts in seconds
    :return: True if solved, False otherwise
    """

    logger.debug(f'Starting Cloudflare {challenge_type} challenge solving by click...')

    for attempt in range(solve_attempts):
        if attempt > 0:
            await asyncio.sleep(attempt_delay)

            logger.debug(f'Retrying to solve ({attempt + 1}/{solve_attempts})...')
            
        # attempt to get the body text and print for debugging
        if logger.isEnabledFor(logging.DEBUG):
            try:
                body_text = await queryable.locator('body').inner_text()
                logger.debug(f"Current page body: {body_text[:300]}") 
            except TargetClosedError:
                logger.warning("Page or browser crashed. Creating new page...")
                try:
                    queryable = await browser_context.new_page()
                except Exception as create_exc:
                    logger.exception("Failed to create new page after crash. - the browser likely crashed")
                    raise create_exc


        # 1. check if Cloudflare challenge is present
        cloudflare_detected = await detect_cloudflare_challenge(queryable, challenge_type)
        expected_content_detected = await detect_expected_content(queryable, expected_content_selector)
        if not cloudflare_detected or expected_content_detected:
            logger.debug('No Cloudflare challenge detected')

            # attempt to get the body text and print for debugging
            if logger.isEnabledFor(logging.DEBUG):
                try:
                    body_text = await queryable.locator('body').inner_text()
                    logger.debug(f"Current page body: {body_text[:300]}") 
                except TargetClosedError:
                    logger.warning("Page or browser crashed. Creating new page...")
                    try:
                        queryable = await browser_context.new_page()
                    except Exception as create_exc:
                        logger.exception("Failed to create new page after crash. - the browser likely crashed")
                        raise create_exc

            return True
        
        # wait for page to load
        try:
            await queryable.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeoutError:
            logger.debug(f"Page did not reach 'domcontentloaded'.")
        except CrashedError:
            logger.debug("Caught CrashedError – page was already closed")
            logger.debug(f"page: {queryable}")
            # return False

        # 2. find Cloudflare iframes
        cf_iframes = await search_shadow_root_iframes(
            queryable, 'https://challenges.cloudflare.com/cdn-cgi/challenge-platform/'
        )
        if not cf_iframes:
            logger.debug(f'Cloudflare iframes not found')
            continue

        # 3. in all found iframes, search for the valid checkbox input and wait until it's ready to be clicked
        checkbox_data = await get_ready_checkbox(cf_iframes,delay=wait_checkbox_delay,attempts=wait_checkbox_attempts)
        if not checkbox_data:
            logger.debug(f'Cloudflare checkbox not found or not ready')
            continue
        iframe, checkbox = checkbox_data
        # located checkbox in the iframe
        logger.debug('Found checkbox in Cloudflare iframe')

        # 4. click the checkbox
        for checkbox_click_attempt in range(checkbox_click_attempts):
            try:
                await checkbox.click()
                logger.debug('Checkbox clicked successfully')
                break
            except Exception as e:
                logger.debug(f'Error clicking checkbox ({checkbox_click_attempt + 1}/{checkbox_click_attempts} attempt): {e}')
        else:
            logger.debug(f'Failed to click checkbox after maximum attempts')
            continue

        # attempt to get the body text and print for debugging
        if logger.isEnabledFor(logging.DEBUG):
            try:
                body_text = await queryable.locator('body').inner_text()
                logger.debug(f"Current page body: {body_text[:300]}") 
            except TargetClosedError:
                logger.warning("Page or browser crashed. Creating new page...")
                try:
                    queryable = await browser_context.new_page()
                except Exception as create_exc:
                    logger.exception("Failed to create new page after crash. - the browser likely crashed")
                    raise create_exc

        # 5. verify success
        if challenge_type == "turnstile":
            logger.debug("verifying turnstile")
            # for turnstile, check for success element in the cf's iframe or expected content is present
            cloudflare_detected = await detect_cloudflare_challenge(queryable, challenge_type)
            challenge_solved = not cloudflare_detected
            # success_elements = await search_shadow_root_elements(iframe, 'div[id="success"]')
            # challenge_solved = bool(success_elements)
        else:
            logger.debug("verifying interstitial")
            # for interstitial, check if challenge is gone or expected content is present
            cloudflare_detected = await detect_cloudflare_challenge(queryable, challenge_type)
            challenge_solved = not cloudflare_detected

        expected_content_detected = await detect_expected_content(queryable, expected_content_selector)
        if challenge_solved or expected_content_detected:
            logger.debug('Solved successfully')
            logger.debug(f"challenge_solved: {challenge_solved}")
            logger.debug(f"expected_content_detected: {expected_content_detected}")

            # attempt to get the body text and print for debugging
            if logger.isEnabledFor(logging.DEBUG):
                try:
                    body_text = await queryable.locator('body').inner_text()    
                    logger.debug(f"Current page body: {body_text[:300]}") 
                except TargetClosedError:
                    logger.warning("Page or browser crashed. Creating new page...")
                    try:
                        queryable = await browser_context.new_page()
                    except Exception as create_exc:
                        logger.exception("Failed to create new page after crash. - the browser likely crashed")
                        raise create_exc

            return True

        logger.debug('Failed to solve Cloudflare challenge')

    logger.debug('Max solving attempts reached, giving up')
    await asyncio.sleep(2)
    return False
