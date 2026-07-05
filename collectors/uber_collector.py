import logging
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base_collector import (
    get_driver, wait_and_find, wait_and_find_all,
    safe_tap, safe_type, get_text_safe, polite_delay,
    parse_fare, parse_eta
)
from config import PICKUP

logger = logging.getLogger(__name__)

SEL_WHERE_TO        = ("accessibility id", "Where to?")
SEL_EDIT_TEXT       = ("id", "com.ubercab:id/edit_text")
SEL_SUGGESTION_LIST = ("id", "com.ubercab:id/ub__text_search_v2_results")
SEL_FARE_LIST       = ("id", "order_selection_order_list")
SEL_FARE_CARDS      = ("id", "order_selection_order_cell")


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


def fetch_uber_fares(destination: dict, weather: dict = None) -> list:
    logger.info(f"  [Uber] {PICKUP['name']} -> {destination['name']}")
    driver = None
    results = []

    try:
        driver = get_driver("uber")
        polite_delay(3.0, 5.0)

        # IMPORTANT: make Uber's "Current location" become IGDTUW
        driver.set_location(
            float(PICKUP["lat"]),
            float(PICKUP["lng"]),
            0
        )
        polite_delay(3.0, 4.0)

        if not safe_tap(driver, *SEL_WHERE_TO):
            logger.error("  [Uber] 'Where to?' not found")
            return []

        polite_delay(1.5, 2.5)

        # Only type destination now.
        # Do NOT type pickup into fields[0], because fields[0] may be destination.
        fields = wait_and_find_all(driver, *SEL_EDIT_TEXT, timeout=10)
        if not fields:
            logger.error("  [Uber] No input fields found")
            return []

        target_field = fields[-1]
        target_field.clear()
        target_field.send_keys(destination["name"])
        polite_delay(1.5, 2.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_LIST, timeout=8)
        if suggestions:
            suggestions[0].click()
        else:
            logger.error(f"  [Uber] No suggestion found for {destination['name']}")
            return []

        polite_delay(4.0, 6.0)

        fare_cards = wait_and_find_all(driver, *SEL_FARE_CARDS, timeout=15)
        if not fare_cards:
            logger.warning("  [Uber] No fare cards found")
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

    finally:
        if driver:
            driver.quit()

    return results