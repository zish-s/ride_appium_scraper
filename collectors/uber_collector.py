import logging
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base_collector import (
    get_driver, wait_and_find, wait_and_find_all,
    safe_tap, safe_type, get_text_safe, polite_delay,
    parse_fare, parse_eta, debug_screenshot, ensure_home_screen
)
from config import PICKUP

logger = logging.getLogger(__name__)

SEL_WHERE_TO        = ("accessibility id", "Where to?")
SEL_EDIT_TEXT       = ("id", "com.ubercab:id/edit_text")
SEL_SUGGESTION_LIST = ("id", "com.ubercab:id/ub__text_search_v2_results")
SEL_FARE_LIST       = ("id", "order_selection_order_list")
SEL_FARE_CARDS      = ("id", "order_selection_order_cell")

APP_PACKAGE = "com.ubercab"
MAX_ATTEMPTS_PER_DESTINATION = 2


def parse_card_content_desc(content_desc: str) -> dict:
    result = {"name": None, "fare": None, "eta": None}
    if not content_desc:
        return result

    parts = [p.strip() for p in content_desc.split(",")]

    for i, part in enumerate(parts):
        if "fare" in part.lower():
            if i > 0:
                result["name"] = parts[i - 1]
            fare_match = re.search(r'[\d]+(?:\.\d+)?', part.replace(',', ''))
            if fare_match:
                result["fare"] = float(fare_match.group())
        if "minute" in part.lower() or "min away" in part.lower():
            eta_match = re.search(r'(\d+)', part)
            if eta_match:
                result["eta"] = int(eta_match.group(1))

    return result


def _attempt_uber_fetch(destination: dict, weather: dict = None) -> list:
    """One attempt at fetching fares for a single destination. Returns [] on failure."""
    logger.info(f"  [Uber] {PICKUP['name']} -> {destination['name']}")
    driver = None
    results = []

    try:
        driver = get_driver("uber")
        polite_delay(3.0, 5.0)

        # Confirm we're actually on the home screen before doing anything.
        # noReset can leave the app mid-flow from a previous run/quit, which
        # is the #1 cause of "'Where to?' not found" errors.
        if not ensure_home_screen(driver, SEL_WHERE_TO, APP_PACKAGE):
            logger.error("  [Uber] Could not reach home screen")
            debug_screenshot(driver, "uber_no_home_screen")
            return []

        if not safe_tap(driver, *SEL_WHERE_TO):
            logger.error("  [Uber] 'Where to?' not found")
            debug_screenshot(driver, "uber_where_to_missing")
            return []

        polite_delay(1.5, 2.5)

        # The "Where to?" screen normally shows 2 edit_text fields:
        # fields[0] = pickup (pre-filled with current-location text)
        # fields[-1] = destination (empty)
        # NOTE: if this stops matching your app version, re-check the
        # order/ids in Appium Inspector — don't assume blindly.
        fields = wait_and_find_all(driver, *SEL_EDIT_TEXT, timeout=10)
        if len(fields) < 2:
            logger.error(f"  [Uber] Expected 2 input fields, found {len(fields)}")
            debug_screenshot(driver, "uber_missing_fields")
            return []

        # Step 1: overwrite pickup with our fixed location
        pickup_field = fields[0]
        pickup_field.clear()
        pickup_field.send_keys(PICKUP["name"])
        polite_delay(1.5, 2.0)

        pickup_suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_LIST, timeout=8)
        if pickup_suggestions:
            pickup_suggestions[0].click()
        else:
            logger.error(f"  [Uber] No pickup suggestion found for {PICKUP['name']}")
            debug_screenshot(driver, "uber_pickup_suggestion_missing")
            return []

        polite_delay(1.0, 1.5)

        # Re-fetch fields — selecting the pickup suggestion can re-render the screen
        fields = wait_and_find_all(driver, *SEL_EDIT_TEXT, timeout=10)
        if not fields:
            logger.error("  [Uber] No input fields found after setting pickup")
            debug_screenshot(driver, "uber_missing_fields_after_pickup")
            return []

        # Step 2: type destination
        target_field = fields[-1]
        target_field.clear()
        target_field.send_keys(destination["name"])
        polite_delay(1.5, 2.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_LIST, timeout=8)
        if suggestions:
            suggestions[0].click()
        else:
            logger.error(f"  [Uber] No suggestion found for {destination['name']}")
            debug_screenshot(driver, "uber_destination_suggestion_missing")
            return []

        polite_delay(4.0, 6.0)

        fare_cards = wait_and_find_all(driver, *SEL_FARE_CARDS, timeout=20)
        if not fare_cards:
            logger.warning("  [Uber] No fare cards found")
            debug_screenshot(driver, "uber_no_fare_cards")
            return []

        for card in fare_cards:
            try:
                content_desc = card.get_attribute("content-desc")
                if not content_desc:
                    parent = card.find_element("xpath", "..")
                    content_desc = parent.get_attribute("content-desc")

                parsed = parse_card_content_desc(content_desc)

                if not parsed["name"] or parsed["fare"] is None:
                    continue

                results.append({
                    "platform":     "uber",
                    "vehicle_type": parsed["name"],
                    "pickup":       PICKUP["name"],
                    "destination":  destination["name"],
                    "fare":         parsed["fare"],
                    "eta_minutes":  parsed["eta"],
                    "weather":      weather.get("condition", "") if weather else "",
                    "temp_c":       weather.get("temp_c", "") if weather else "",
                })

                logger.info(
                    f"    uber {parsed['name']}: Rs.{parsed['fare']} ETA={parsed['eta']}min"
                )

            except Exception as e:
                logger.debug(f"  [Uber] Card parse error: {e}")
                continue

        driver.back()
        polite_delay(1.0, 2.0)
        driver.back()

    except Exception as e:
        logger.error(f"  [Uber] Driver error: {e}")
        if driver:
            debug_screenshot(driver, "uber_exception")

    finally:
        if driver:
            driver.quit()

    return results


def fetch_uber_fares(destination: dict, weather: dict = None) -> list:
    """Fetches fares for one destination, retrying once if the first attempt fails."""
    for attempt in range(1, MAX_ATTEMPTS_PER_DESTINATION + 1):
        results = _attempt_uber_fetch(destination, weather)
        if results:
            return results
        if attempt < MAX_ATTEMPTS_PER_DESTINATION:
            logger.warning(f"  [Uber] Attempt {attempt} failed for {destination['name']}, retrying")
            polite_delay(2.0, 3.0)

    logger.error(f"  [Uber] All attempts failed for {destination['name']}")
    return []