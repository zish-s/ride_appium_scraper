# ============================================================
# collectors/rapido_collector.py
# Scrapes fare + ETA from Rapido Android app via Appium
#
# Fill in selectors using Appium Inspector — see SETUP_GUIDE.md
#
# NOTE: Rapido uses heavy animations. The delays here are
# intentionally longer than Uber/Ola. Don't reduce them or
# you'll read a loading state instead of the actual fare.
# ============================================================

import logging
from selenium.webdriver.common.by import By

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base_collector import (
    get_driver, wait_and_find, wait_and_find_all,
    safe_tap, safe_type, get_text_safe, polite_delay,
    parse_fare, parse_eta
)
from config import PICKUP

logger = logging.getLogger(__name__)

# ── SELECTORS — fill these in using Appium Inspector ─────────

SEL_PICKUP_FIELD        = (By.ID, "FIND_ME_pickup_edittext")
SEL_DROPOFF_FIELD       = (By.ID, "FIND_ME_dropoff_edittext")
SEL_SUGGESTION_ITEMS    = (By.ID, "FIND_ME_autocomplete_row")

SEL_FARE_CARDS          = (By.ID, "FIND_ME_service_card")
    # Each service card: Bike, Auto, Cab

SEL_VEHICLE_NAME        = (By.ID, "FIND_ME_service_name_text")
SEL_VEHICLE_FARE        = (By.ID, "FIND_ME_fare_text")
SEL_VEHICLE_ETA         = (By.ID, "FIND_ME_eta_text")

SEL_BACK_BUTTON         = (By.ACCESSIBILITY_ID, "FIND_ME_navigate_up")
# ─────────────────────────────────────────────────────────────


def fetch_rapido_fares(destination: dict, weather: dict = None) -> list:
    """
    Opens Rapido, searches pickup → destination, reads all service cards.
    """
    logger.info(f"  [Rapido] Searching: {PICKUP['name']} → {destination['name']}")
    driver  = None
    results = []

    try:
        driver = get_driver("rapido")
        polite_delay(4.0, 6.0)  # Rapido splash is slower

        # Step 1: Enter pickup
        if not safe_type(driver, *SEL_PICKUP_FIELD, PICKUP["name"]):
            logger.error("  [Rapido] Could not find pickup field")
            return []
        polite_delay(2.0, 3.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_ITEMS, timeout=10)
        if suggestions:
            suggestions[0].click()
        polite_delay(1.5, 2.0)

        # Step 2: Enter destination
        if not safe_type(driver, *SEL_DROPOFF_FIELD, destination["name"]):
            logger.error("  [Rapido] Could not find dropoff field")
            return []
        polite_delay(2.0, 3.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_ITEMS, timeout=10)
        if suggestions:
            suggestions[0].click()

        # Rapido animates heavily — wait longer than other apps
        polite_delay(5.0, 7.0)

        # Step 3: Read service cards
        fare_cards = wait_and_find_all(driver, *SEL_FARE_CARDS, timeout=18)
        if not fare_cards:
            logger.warning(f"  [Rapido] No fare cards found for {destination['name']}")
            return []

        for card in fare_cards:
            try:
                name_el = card.find_element(*SEL_VEHICLE_NAME)
                fare_el = card.find_element(*SEL_VEHICLE_FARE)
                eta_el  = card.find_element(*SEL_VEHICLE_ETA)

                name = get_text_safe(name_el)
                fare = parse_fare(get_text_safe(fare_el))
                eta  = parse_eta(get_text_safe(eta_el))

                if not name or fare is None:
                    continue

                results.append({
                    "platform":     "rapido",
                    "vehicle_type": name,
                    "pickup":       PICKUP["name"],
                    "destination":  destination["name"],
                    "fare":         fare,
                    "eta_minutes":  eta,
                    "weather":      weather.get("condition", "") if weather else "",
                    "temp_c":       weather.get("temp_c", "") if weather else "",
                })
                logger.info(f"    rapido {name}: ₹{fare}  ETA={eta}min")

            except Exception as e:
                logger.debug(f"  [Rapido] Card parse error: {e}")
                continue

        safe_tap(driver, *SEL_BACK_BUTTON, timeout=5)

    except Exception as e:
        logger.error(f"  [Rapido] Driver error: {e}")

    finally:
        if driver:
            driver.quit()

    return results