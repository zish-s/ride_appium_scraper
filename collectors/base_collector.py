# ============================================================
# collectors/base_collector.py
# Shared Appium driver setup and helper functions used by all
# ride-hailing app collectors (Uber, and later Ola/Rapido).
# ============================================================

import logging
import time
import random
import os
from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from appium.options.android import UiAutomator2Options

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import APPIUM_SERVER_URL, DESIRED_CAPS_BASE, APPS

logger = logging.getLogger(__name__)

DEBUG_SCREENSHOT_DIR = "data/debug_screenshots"
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)


def get_driver(app_name: str):
    """
    Starts an Appium session and launches the given app.

    NOTE: the appPackage capability is *supposed* to auto-launch the app
    at session start, but this is intermittently unreliable on real
    devices (a race between the automation service attaching and the
    launch command firing). We explicitly call activate_app() right
    after session start as a belt-and-suspenders step — this does NOT
    kill anything first, it just brings the app forward if it isn't
    already, so it's safe to call every time.
    """
    caps = {**DESIRED_CAPS_BASE, **APPS[app_name]}
    options = UiAutomator2Options().load_capabilities(caps)

    driver = webdriver.Remote(
        command_executor=APPIUM_SERVER_URL,
        options=options
    )

    app_package = caps.get("appium:appPackage") or caps.get("appPackage")
    if app_package:
        try:
            driver.activate_app(app_package)
            time.sleep(2.0)
        except Exception as e:
            logger.debug(f"  activate_app on launch failed (non-fatal): {e}")

    logger.info(f"  [{app_name}] App launched")
    return driver


def wait_and_find(driver, by, selector, timeout=15):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
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


def type_into_field(driver, field_element, text: str):
    """
    Clicks a field to focus it, then types via 'mobile: type' rather than
    send_keys(). Many custom-styled input widgets (e.g. Uber's pickup /
    destination fields, which are Button-class views, not real EditText)
    don't implement the accessibility set-text action send_keys() relies
    on — send_keys() silently does nothing on them. 'mobile: type'
    simulates real keyboard input via ADB into whatever currently has
    focus, which works regardless of the widget's internal class.
    """
    field_element.click()
    time.sleep(1.2)
    driver.execute_script('mobile: type', {'text': text})


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


def debug_screenshot(driver, label: str):
    """
    Saves a screenshot to data/debug_screenshots/ so we can see exactly
    what was on screen when a selector wasn't found, instead of guessing.
    """
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(DEBUG_SCREENSHOT_DIR, f"{label}_{ts}.png")
        driver.get_screenshot_as_file(path)
        logger.warning(f"  Saved debug screenshot: {path}")
    except Exception as e:
        logger.debug(f"  Could not save screenshot: {e}")


def ensure_home_screen(driver, home_marker, app_package, patient_timeout=25):
    """
    Confirms the app is actually sitting on the screen we expect (e.g.
    the pickup-search home screen) before we start interacting.

    On a real device the home screen can take a while to finish
    rendering (promo banners, network calls), so we wait patiently first
    — no navigation. Only if that genuinely fails do we try `back` once,
    as a gentle recovery for a leftover dialog. We deliberately do NOT
    force-kill and relaunch the app here — that requires an explicit
    appActivity to reliably work, and doing it without one has
    previously left the app closed with no way back in this function.

    home_marker: a (by, selector) tuple for an element that only exists
                 on the target screen.
    """
    by, selector = home_marker

    el = wait_and_find(driver, by, selector, timeout=patient_timeout)
    if el:
        return True

    logger.warning("  Home screen not detected after patient wait, trying back once")
    try:
        driver.back()
        time.sleep(2.0)
    except Exception:
        pass

    return wait_and_find(driver, by, selector, timeout=patient_timeout) is not None