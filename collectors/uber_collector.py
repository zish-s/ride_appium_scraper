# ============================================================
# collectors/uber_collector.py
# Scrapes Uber fare estimates for a fixed pickup point across
# multiple destinations.
#
# Selectors below were confirmed via real page-source dumps
# (see dump_page_source.py), not guessed:
#   - Home screen search bar has NO usable `text`, only a
#     content-desc of "Enter pickup location" (it's rendered
#     via Jetpack Compose).
#   - The pickup/destination fields on the address-entry screen
#     are custom Button widgets (not EditText) with their own
#     stable resource-ids, both visible on screen at once.
#   - Those fields don't respond to send_keys() (no set-text
#     accessibility action) — must type via 'mobile: type'.
# ============================================================

import logging
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base_collector import (
    get_driver, wait_and_find, wait_and_find_all,
    safe_tap, get_text_safe, polite_delay, type_into_field,
    debug_screenshot, ensure_home_screen
)
from config import PICKUP

logger = logging.getLogger(__name__)

SEL_WHERE_TO             = ("accessibility id", "Enter pickup location")
SEL_PICKUP_FIELD         = ("id", "com.ubercab:id/ub__location_edit_search_pickup_view")
SEL_DESTINATION_FIELD    = ("id", "com.ubercab:id/ub__location_edit_search_destination_view")
SEL_SUGGESTION_CONTAINER = ("id", "com.ubercab:id/ub__text_search_v2_results")
SEL_FARE_CARDS           = ("id", "order_selection_order_cell")

APP_PACKAGE = "com.ubercab"
MAX_ATTEMPTS_PER_DESTINATION = 2

# Fixed action rows that always appear in the suggestions list — not real
# address suggestions, so we skip them when picking the first result.
NON_ADDRESS_SUGGESTION_LABELS = {"Search in a different city", "Set location on map"}


def get_address_suggestions(driver, timeout=8):
    """Returns clickable Button elements from the suggestions list,
    excluding the fixed action rows that aren't actual address suggestions."""
    container = wait_and_find(driver, *SEL_SUGGESTION_CONTAINER, timeout=timeout)
    if not container:
        return []
    try:
        buttons = container.find_elements("class name", "android.widget.Button")
    except Exception:
        return []
    results = []
    for b in buttons:
        label = b.get_attribute("content-desc") or get_text_safe(b) or ""
        if label not in NON_ADDRESS_SUGGESTION_LABELS:
            results.append(b)
    return results


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

        if not ensure_home_screen(driver, SEL_WHERE_TO, APP_PACKAGE):
            logger.error("  [Uber] Could not reach home screen")
            debug_screenshot(driver, "uber_no_home_screen")
            return []

        if not safe_tap(driver, *SEL_WHERE_TO):
            logger.error("  [Uber] 'Enter pickup location' not found")
            debug_screenshot(driver, "uber_where_to_missing")
            return []

        # Let the address-entry bottom sheet finish animating in before
        # we go looking for its fields.
        polite_delay(2.5, 3.5)

        # --- Pickup field ---
        pickup_field = wait_and_find(driver, *SEL_PICKUP_FIELD, timeout=20)
        if not pickup_field:
            logger.error("  [Uber] Pickup field not found")
            debug_screenshot(driver, "uber_pickup_field_missing")
            return []

        type_into_field(driver, pickup_field, PICKUP["name"])
        polite_delay(1.5, 2.0)

        pickup_suggestions = get_address_suggestions(driver, timeout=8)
        if pickup_suggestions:
            pickup_suggestions[0].click()
        else:
            logger.error(f"  [Uber] No pickup suggestion found for {PICKUP['name']}")
            debug_screenshot(driver, "uber_pickup_suggestion_missing")
            return []

        polite_delay(1.0, 1.5)

        # --- Destination field ---
        destination_field = wait_and_find(driver, *SEL_DESTINATION_FIELD, timeout=15)
        if not destination_field:
            logger.error("  [Uber] Destination field not found after setting pickup")
            debug_screenshot(driver, "uber_destination_field_missing")
            return []

        type_into_field(driver, destination_field, destination["name"])
        polite_delay(1.5, 2.0)

        suggestions = get_address_suggestions(driver, timeout=8)
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