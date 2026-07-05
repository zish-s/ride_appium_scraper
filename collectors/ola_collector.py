# ============================================================
# collectors/ola_collector.py
# Scrapes fare + ETA from Ola Android app via Appium
#
# Fill in selectors using Appium Inspector — see SETUP_GUIDE.md
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

SEL_PICKUP_FIELD        = (By.ID, "FIND_ME_pickup_field")
    # Pickup text field on the booking screen

SEL_DROPOFF_FIELD       = (By.ID, "FIND_ME_dropoff_field")
    # Dropoff text field

SEL_SUGGESTION_ITEMS    = (By.ID, "FIND_ME_suggestion_item")
    # Each autocomplete suggestion row

SEL_SEARCH_BUTTON       = (By.ID, "FIND_ME_search_button")
    # The button that triggers the fare search
    # (some Ola versions search automatically, skip if so)

SEL_FARE_CARDS          = (By.ID, "FIND_ME_ride_type_card")
    # Each ride-type card (Mini, Auto, Bike, Prime)

SEL_VEHICLE_NAME        = (By.ID, "FIND_ME_ride_category_name")
SEL_VEHICLE_FARE        = (By.ID, "FIND_ME_ride_fare_amount")
SEL_VEHICLE_ETA         = (By.ID, "FIND_ME_ride_eta")

SEL_BACK_BUTTON         = (By.ACCESSIBILITY_ID, "FIND_ME_back")
# ─────────────────────────────────────────────────────────────


def fetch_ola_fares(destination: dict, weather: dict = None) -> list:
    """
    Opens Ola, searches pickup → destination, reads all fare cards.
    """
    logger.info(f"  [Ola] Searching: {PICKUP['name']} → {destination['name']}")
    driver  = None
    results = []

    try:
        driver = get_driver("ola")
        polite_delay(3.0, 5.0)

        # Step 1: Enter pickup
        if not safe_type(driver, *SEL_PICKUP_FIELD, PICKUP["name"]):
            logger.error("  [Ola] Could not find pickup field")
            return []
        polite_delay(1.5, 2.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_ITEMS, timeout=8)
        if suggestions:
            suggestions[0].click()
        polite_delay(1.0, 1.5)

        # Step 2: Enter destination
        if not safe_type(driver, *SEL_DROPOFF_FIELD, destination["name"]):
            logger.error("  [Ola] Could not find dropoff field")
            return []
        polite_delay(1.5, 2.0)

        suggestions = wait_and_find_all(driver, *SEL_SUGGESTION_ITEMS, timeout=8)
        if suggestions:
            suggestions[0].click()
        polite_delay(1.0, 1.5)

        # Step 3: Tap search if button exists (not all versions have it)
        safe_tap(driver, *SEL_SEARCH_BUTTON, timeout=5)
        polite_delay(4.0, 6.0)  # Ola can be slow to load fares

        # Step 4: Read fare cards
        fare_cards = wait_and_find_all(driver, *SEL_FARE_CARDS, timeout=15)
        if not fare_cards:
            logger.warning(f"  [Ola] No fare cards found for {destination['name']}")
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
                    "platform":     "ola",
                    "vehicle_type": name,
                    "pickup":       PICKUP["name"],
                    "destination":  destination["name"],
                    "fare":         fare,
                    "eta_minutes":  eta,
                    "weather":      weather.get("condition", "") if weather else "",
                    "temp_c":       weather.get("temp_c", "") if weather else "",
                })
                logger.info(f"    ola {name}: ₹{fare}  ETA={eta}min")

            except Exception as e:
                logger.debug(f"  [Ola] Card parse error: {e}")
                continue

        safe_tap(driver, *SEL_BACK_BUTTON, timeout=5)

    except Exception as e:
        logger.error(f"  [Ola] Driver error: {e}")

    finally:
        if driver:
            driver.quit()

    return results
