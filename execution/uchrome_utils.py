

import random
import time

import requests
import undetected_chromedriver as uc
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Initialize logger
try:
    from .logger import Logger
except ImportError:
    from logger import Logger

logger_obj = Logger(level="DEBUG")
logger = logger_obj.get_logger()

def get_selenium_driver(proxy_details: dict | None = None, headless: bool = False):
    """
    Initialize and return an undetected_chromedriver instance.
    """
    options = uc.ChromeOptions()
    if proxy_details:
        server = proxy_details.get('server')
        if server:
             options.add_argument(f'--proxy-server={server}')

    # Add any other standard options
    # options.add_argument("--window-size=1920,1080")

    try:
        # Explicit version_main to match installed Chrome if needed (e.g. 142)
        driver = uc.Chrome(options=options, headless=headless, use_subprocess=True, version_main=142)
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        raise e

def human_type(element, text: str):
    """
    Type text into an element with random delays to simulate human typing.
    """
    for char in text:
        element.send_keys(char)
        # Random sleep between 0.15 and 0.45 seconds
        time.sleep(random.uniform(0.15, 0.45))

def login_and_solve_selenium(driver, username, password, login_url, search_url):
    """
    navigate to search_url (to trigger CF), solve if needed, then login.
    Returns True if successful, False otherwise.
    """
    try:
        # 3. Login
        logger.info(f"Navigating to Login URL: {login_url}")
        driver.get(login_url)
        
        # Handle Cookies
        try:
            accept_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            if accept_btn:
                logger.info("Found cookie banner. Accepting...")
                accept_btn.click()
                time.sleep(random.uniform(2, 4))
        except:
             pass

        wait = WebDriverWait(driver, 20)
        
        # Username
        logger.info("Waiting for username field...")
        username_field = wait.until(EC.element_to_be_clickable((By.ID, "login_username")))
        username_field.click()
        username_field.clear()
        time.sleep(random.uniform(1.5, 3.0))
        human_type(username_field, username)
        time.sleep(random.uniform(1.5, 3.0))
        
        # Click Continue/Next button
        logger.info("Looking for Continue button...")
        continue_btn = None
        try:
            continue_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "login_password_continue"))
            )
        except:
            pass
        
        if not continue_btn:
             try:
                continue_btn = driver.find_element(By.XPATH, "//button[@id='login_password_continue']")
             except:
                pass

        if not continue_btn:
             try:
                continue_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue with Email')]")
             except:
                pass

        if continue_btn:
            logger.info("Found Continue button. Clicking...")
            try:
                driver.execute_script("arguments[0].click();", continue_btn)
            except:
                continue_btn.click()
        else:
            logger.info("Continue button not found, trying Return key...")
            username_field.send_keys(Keys.RETURN)
        
        time.sleep(random.uniform(4, 7))
        
        try:
            logger.info("Waiting for password field...")
            password_field = wait.until(EC.visibility_of_element_located((By.ID, "login_password")))
            
            # Click password field to ensure focus
            try:
                driver.execute_script("arguments[0].click();", password_field)
                password_field.click()
            except:
                pass
            
            human_type(password_field, password)
            time.sleep(random.uniform(1.5, 3.0))
            
            # STRATEGY 1: Return Key First
            logger.info("Sending Return key for password...")
            password_field.send_keys(Keys.RETURN)
            
            # Wait and check if we moved on
            try:
                WebDriverWait(driver, 5).until(lambda d: "login" not in d.current_url)
                logger.info("Return key triggered navigation.")
            except TimeoutException:
                logger.info("Return key didn't trigger navigation. Trying 'Log in' button...")
                try:
                    # try explicitly identified button ID
                    login_btn = driver.find_element(By.ID, "login_control_continue")
                    driver.execute_script("arguments[0].click();", login_btn)
                except:
                    try:
                        # try text match (Log in)
                        login_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Log in')]")
                        login_btn.click()
                    except:
                        logger.warning("Could not find explicit Log in button.")
            
            time.sleep(random.uniform(7, 10))

        except TimeoutException:
            logger.error("Timed out waiting for password field.")
            if "login_password" not in driver.page_source:
                 logger.error("Password field not found in source. We might be stuck on username.")
            raise
        
        time.sleep(random.uniform(7, 10))

        # Check for success (e.g. not on login page, or specific element)
        if "login" not in driver.current_url:
             logger.info("Login appears successful (URL changed).")
             
             # Double check for positive indicators
             try:
                 # Look for avatar or nav item
                 wait.until(lambda d: d.find_elements(By.CLASS_NAME, "nav-user-avatar") or d.find_elements(By.CLASS_NAME, "nav-item") or "Sign Up" not in d.page_source)
                 logger.info("Confirmed login with positive indicators.")
                 return True
             except TimeoutException:
                 logger.warning("URL changed but could not find specific positive login indicators (avatar/nav). Continuing with caution.")
                 return True
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "Verification failed" in body_text or "Technical difficulties" in body_text:
             logger.error("Login failed: Verification failed or Technical Difficulties.")
             return False

        if "login" in driver.current_url:
             logger.error("Login failed: Still on login URL after attempts.")
             try:
                 driver.save_screenshot("execution/debug_login_failed.png")
                 with open("execution/debug_login_failed.html", "w", encoding="utf-8") as f:
                     f.write(driver.page_source)
                 logger.info("Saved debug_login_failed.png and .html")
             except:
                 pass
             return False

        logger.info("Login flow completed (unexpected state).")
        return False

    except Exception as e:
        logger.error(f"Error during login/solve: {e}")
        return False

def selenium_cookies_to_requests(driver):
    """
    Convert Selenium cookies to a requests.Session.
    """
    session = requests.Session()
    
    # Cookies
    selenium_cookies = driver.get_cookies()
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
    
    # User-Agent
    user_agent = driver.execute_script("return navigator.userAgent;")
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.upwork.com/',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    })
    
    return session
