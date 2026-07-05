import logging
import time
import random
import os
from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from appium.options.android import UiAutomator2Options

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import APPIUM_SERVER_URL, DESIRED_CAPS_BASE, APPS

logger = logging.getLogger(__name__)

DEBUG_SCREENSHOT_DIR = "data/debug_screenshots"
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)


def get_driver(app_name: str):
    caps = {**DESIRED_CAPS_BASE, **APPS[app_name]}

    options = UiAutomator2Options().load_capabilities(caps)

    logger.info(f"Using base_collector from: {__file__}")

    driver = webdriver.Remote(
        command_executor=APPIUM_SERVER_URL,
        options=options
    )

    logger.info(f"  [{app_name}] App launched")
    return driver


def wait_and_find(driver, by, selector, timeout=15):
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return el
    except TimeoutException:
        logger.warning(f"  Element not found in {timeout}s: {selector}")
        return None


def wait_and_find_all(driver, by, selector, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return driver.find_elements(by, selector)
    except TimeoutException:
        logger.warning(f"  Elements not found in {timeout}s: {selector}")
        return []


def safe_tap(driver, by, selector, timeout=10):
    el = wait_and_find(driver, by, selector, timeout)
    if el:
        el.click()
        return True
    return False


def safe_type(driver, by, selector, text, clear_first=True, timeout=10):
    el = wait_and_find(driver, by, selector, timeout)
    if el:
        if clear_first:
            el.clear()
        el.send_keys(text)
        return True
    return False


def get_text_safe(element):
    try:
        text = element.text.strip()
        return text if text else None
    except Exception:
        return None


def polite_delay(min_sec=1.5, max_sec=3.0):
    time.sleep(random.uniform(min_sec, max_sec))


def parse_fare(raw_text: str):
    if not raw_text:
        return None
    import re
    match = re.search(r'[\d,]+(?:\.\d+)?', raw_text.replace(',', ''))
    if match:
        try:
            return float(match.group().replace(',', ''))
        except ValueError:
            return None
    return None


def parse_eta(raw_text: str):
    if not raw_text:
        return None
    import re
    match = re.search(r'(\d+)', raw_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


# ── New helpers ───────────────────────────────────────────────

def debug_screenshot(driver, label: str):
    """
    Saves a screenshot so you can see what was actually on screen
    when a selector wasn't found. Check data/debug_screenshots/
    after a failed run to diagnose blocked dialogs, wrong screens, etc.
    """
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(DEBUG_SCREENSHOT_DIR, f"{label}_{ts}.png")
        driver.get_screenshot_as_file(path)
        logger.warning(f"  Saved debug screenshot: {path}")
    except Exception as e:
        logger.debug(f"  Could not save screenshot: {e}")


def ensure_home_screen(driver, home_marker, app_package, max_attempts=3):
    """
    Confirms the app is actually sitting on the screen we expect
    (e.g. the 'Where to?' home screen) before we start interacting.
    If it's not there (leftover dialog, resumed mid-flow, promo
    interstitial, etc.) this presses back a few times and, as a
    last resort, force-restarts the app fresh.

    home_marker: a (by, selector) tuple for an element that only
                 exists on the home/landing screen.
    """
    by, selector = home_marker

    for attempt in range(max_attempts):
        el = wait_and_find(driver, by, selector, timeout=6)
        if el:
            return True

        logger.warning(f"  Not on home screen (attempt {attempt + 1}/{max_attempts}), pressing back")
        try:
            driver.back()
            time.sleep(1.5)
        except Exception:
            pass

    # Last resort: force-stop and relaunch fresh (keeps login, resets nav stack)
    logger.warning("  Forcing app restart to recover a clean home screen")
    try:
        driver.terminate_app(app_package)
        time.sleep(1.0)
        driver.activate_app(app_package)
        time.sleep(4.0)
    except Exception as e:
        logger.debug(f"  Force restart failed: {e}")

    return wait_and_find(driver, by, selector, timeout=10) is not None