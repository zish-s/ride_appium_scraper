import logging
import time
import random
from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from appium.options.android import UiAutomator2Options

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import APPIUM_SERVER_URL, DESIRED_CAPS_BASE, APPS

logger = logging.getLogger(__name__)


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