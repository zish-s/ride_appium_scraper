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
#   - The fare screen has no reliable resource-id for each fare
#     row (it kept drifting across app versions), so fares are
#     parsed from visible text + on-screen position instead.
# ============================================================

import logging
import re
import xml.etree.ElementTree as ET

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base_collector import (
    get_driver, wait_and_find,
    safe_tap, get_text_safe, polite_delay, type_into_field,
    debug_screenshot, ensure_home_screen
)
from config import PICKUP

logger = logging.getLogger(__name__)

SEL_WHERE_TO             = ("accessibility id", "Enter pickup location")
SEL_PICKUP_FIELD         = ("id", "com.ubercab:id/ub__location_edit_search_pickup_view")
SEL_DESTINATION_FIELD    = ("id", "com.ubercab:id/ub__location_edit_search_destination_edit")
SEL_SUGGESTION_CONTAINER = ("id", "com.ubercab:id/ub__text_search_v2_results")

APP_PACKAGE = "com.ubercab"
MAX_ATTEMPTS_PER_DESTINATION = 2

# Fixed action rows that always appear in the suggestions list — not real
# address suggestions, so we skip them when picking the first result.
NON_ADDRESS_SUGGESTION_LABELS = {"Search in a different city", "Set location on map"}

PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.\d+)?)", re.I)
ETA_RE = re.compile(r"(\d+)\s*(?:min|minute)", re.I)


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


def _parse_bounds(bounds: str):
    """Converts Android bounds like '[112,325][230,356]' into x1, y1, x2, y2."""
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    return tuple(map(int, m.groups()))


def _visible_text_nodes(driver):
    """Reads all visible text/content-desc nodes from the page source,
    along with their screen positions."""
    nodes = []

    try:
        root = ET.fromstring(driver.page_source)
    except Exception as e:
        logger.error(f"  [Uber] Could not parse page source: {e}")
        return nodes

    for el in root.iter():
        label = (
            el.attrib.get("text")
            or el.attrib.get("content-desc")
            or ""
        ).replace("\xa0", " ").strip()

        bounds = _parse_bounds(el.attrib.get("bounds", ""))

        if not label or not bounds:
            continue

        x1, y1, x2, y2 = bounds

        nodes.append({
            "label": label,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
        })

    return nodes


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").replace("\xa0", " ")).strip()


def _extract_eta(label: str):
    m = ETA_RE.search(label or "")
    if m:
        return int(m.group(1))
    return None


def _extract_vehicle_from_combined_label(label: str):
    """
    Handles labels like:
    'selected,Uber Go AC,Fare ₹260.51,estimated drop-off 17:20,...'
    'Auto,Fare ₹258.05,estimated drop-off 17:21,...'
    """
    label = _normalize_label(label)

    price_match = PRICE_RE.search(label)
    if not price_match:
        return None

    # Everything before the ₹ price.
    before_price = label[:price_match.start()].strip(" ,·•|-")

    if not before_price:
        return None

    bad_words = [
        "choose a ride", "choose", "faster", "trial", "cash", "back",
        "pickup", "where to", "set location", "saved places",
        "recommended", "selected", "earn", "uber one"
    ]

    parts = [
        p.strip(" ,·•|-")
        for p in re.split(r"[,·•|\n]+", before_price)
        if p.strip(" ,·•|-")
    ]

    useful = []

    for p in parts:
        lower = p.lower().strip()

        if any(bad in lower for bad in bad_words):
            continue

        # Important: Uber puts the word "Fare" before the price.
        # We do NOT want to treat "Fare" as the vehicle name.
        if lower == "fare" or lower.startswith("fare "):
            continue

        if PRICE_RE.search(p):
            continue

        if ETA_RE.search(p):
            continue

        if re.fullmatch(r"\d+", p):
            continue

        useful.append(p)

    if not useful:
        return None

    return useful[-1]


def collect_fare_rows_from_source(driver, destination: dict, weather: dict = None) -> list:
    """
    Reads Uber fare screen from visible text/content-desc.

    Works for both:
    1. Separate nodes: vehicle name node + price node + ETA node
    2. Combined node: 'Uber Go AC, ₹286.26, 15:30 · 2 min'
    """
    nodes = _visible_text_nodes(driver)
    results = []

    logger.info(f"  [Uber] Visible text nodes found: {len(nodes)}")

    if not nodes:
        return results

    price_nodes = []

    for n in nodes:
        label = _normalize_label(n["label"])
        lower = label.lower()

        if not label:
            continue

        # Skip non-fare money rows.
        if any(bad in lower for bad in ["cash", "trial", "uber one", "earn 10"]):
            continue

        m = PRICE_RE.search(label.replace(",", ""))

        if m:
            fare = float(m.group(1).replace(",", ""))
            price_nodes.append((n, fare))

    logger.info(f"  [Uber] Price nodes found: {len(price_nodes)}")

    used_y_positions = []

    for price_node, fare in price_nodes:
        label = _normalize_label(price_node["label"])

        # Avoid duplicate parent/child nodes from the same row.
        if any(abs(price_node["cy"] - y) < 20 for y in used_y_positions):
            continue

        used_y_positions.append(price_node["cy"])

        # First try same-node parsing.
        vehicle_name = _extract_vehicle_from_combined_label(label)
        eta = _extract_eta(label)

        nearby = [
            n for n in nodes
            if price_node["y1"] - 80 <= n["cy"] <= price_node["y2"] + 110
        ]

        # Fallback: search nearby separate text nodes.
        if not vehicle_name:
            name_candidates = []

            for n in nearby:
                candidate = _normalize_label(n["label"])
                lower = candidate.lower()

                if n == price_node:
                    continue

                if PRICE_RE.search(candidate.replace(",", "")):
                    continue

                if ETA_RE.search(candidate):
                    continue

                if any(bad in lower for bad in [
                    "choose a ride", "choose", "faster", "trial", "cash", "back",
                    "pickup", "where to", "set location", "saved places",
                    "uber one", "earn"
                ]):
                    continue

                # Vehicle name should be on the left side of the price.
                if n["x1"] < price_node["x1"]:
                    name_candidates.append(n)

            if name_candidates:
                vehicle_node = sorted(
                    name_candidates,
                    key=lambda n: (abs(n["cy"] - price_node["cy"]), -n["x1"])
                )[0]
                vehicle_name = _normalize_label(vehicle_node["label"])

        # Fallback ETA search.
        if eta is None:
            for n in nearby:
                eta = _extract_eta(n["label"])
                if eta is not None:
                    break

        if not vehicle_name:
            logger.warning(f"  [Uber] Found fare Rs.{fare}, but no vehicle name. Raw label: {label}")
            continue

        results.append({
            "platform":     "uber",
            "vehicle_type": vehicle_name,
            "pickup":       PICKUP["name"],
            "destination":  destination["name"],
            "fare":         fare,
            "eta_minutes":  eta,
            "weather":      weather.get("condition", "") if weather else "",
            "temp_c":       weather.get("temp_c", "") if weather else "",
        })

    return results

def normalize_vehicle_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").lower().strip())


def merge_fare_rows(existing: dict, new_rows: list):
    """
    Store all unique vehicle fares.
    If same vehicle appears again after scrolling, keep the first collected row.
    """
    for row in new_rows:
        key = normalize_vehicle_name(row.get("vehicle_type", ""))

        if not key:
            continue

        if key not in existing:
            existing[key] = row

    return existing


def scroll_ride_list_down(driver):
    """
    Swipes upward inside the ride-options list.
    This should reveal lower vehicles like Bike/Moto.
    """
    size = driver.get_window_size()
    width = size["width"]
    height = size["height"]

    x = int(width * 0.50)

    # Start inside the ride list, not on the bottom button.
    start_y = int(height * 0.72)
    end_y = int(height * 0.38)

    try:
        driver.swipe(x, start_y, x, end_y, 900)
    except Exception:
        try:
            driver.execute_script("mobile: dragGesture", {
                "startX": x,
                "startY": start_y,
                "endX": x,
                "endY": end_y,
                "speed": 700
            })
        except Exception as e:
            logger.warning(f"  [Uber] Scroll failed: {e}")


def collect_all_fares_with_scroll(driver, destination: dict, weather: dict = None, max_scrolls: int = 3) -> list:
    """
    Collects fares from current visible screen, scrolls, collects again,
    and returns all unique vehicle fares.
    """
    all_fares = {}

    for scroll_no in range(max_scrolls + 1):
        rows = collect_fare_rows_from_source(driver, destination, weather)

        logger.info(f"  [Uber] Scroll {scroll_no}: collected {len(rows)} visible fares")

        before = len(all_fares)
        merge_fare_rows(all_fares, rows)
        after = len(all_fares)

        logger.info(f"  [Uber] Total unique fares so far: {after}")

        if scroll_no == max_scrolls:
            break

        # If nothing new was added after a scroll, still try once more naturally through loop.
        scroll_ride_list_down(driver)
        polite_delay(1.0, 1.5)

    return list(all_fares.values())

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
        
        debug_visible_nodes(driver, "uber_fare_screen_nodes")
        
        # --- Fare collection with scrolling ---
        results = collect_all_fares_with_scroll(driver, destination, weather, max_scrolls=3)

        if not results:
            logger.warning("  [Uber] No fares parsed from visible text")
            debug_screenshot(driver, "uber_no_fare_text")
            return []

        for row in results:
            logger.info(
                f"    uber {row['vehicle_type']}: Rs.{row['fare']} ETA={row['eta_minutes']}min"
            )

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

def _fetch_uber_fares_on_existing_driver(driver, destination: dict, weather: dict = None) -> list:
    """
    Fetch fares for one destination using an already-open Uber driver.
    Does NOT create or quit the driver.
    """
    logger.info(f"  [Uber] {PICKUP['name']} -> {destination['name']}")

    results = []

    if not ensure_home_screen(driver, SEL_WHERE_TO, APP_PACKAGE):
        logger.error("  [Uber] Could not reach home screen")
        debug_screenshot(driver, "uber_no_home_screen")
        return []

    if not safe_tap(driver, *SEL_WHERE_TO):
        logger.error("  [Uber] 'Enter pickup location' not found")
        debug_screenshot(driver, "uber_where_to_missing")
        return []

    polite_delay(2.5, 3.5)

    # --- Pickup field ---
    pickup_field = wait_and_find(driver, *SEL_PICKUP_FIELD, timeout=20)
    if not pickup_field:
        logger.error("  [Uber] Pickup field not found")
        debug_screenshot(driver, "uber_pickup_field_missing")
        return []

    pickup_field.click()
    polite_delay(0.5, 1.0)
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

    destination_field.click()
    polite_delay(0.5, 1.0)
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

    # --- Fare collection with scrolling ---
    results = collect_all_fares_with_scroll(driver, destination, weather, max_scrolls=3)

    if not results:
        logger.warning("  [Uber] No fares parsed from visible text")
        debug_screenshot(driver, "uber_no_fare_text")
        return []

    for row in results:
        logger.info(
            f"    uber {row['vehicle_type']}: Rs.{row['fare']} ETA={row['eta_minutes']}min"
        )

    # Go back to home screen for next destination
    driver.back()
    polite_delay(1.0, 1.5)
    driver.back()
    polite_delay(1.5, 2.0)

    return results

def fetch_uber_fares_for_destinations(destinations: list, weather: dict = None) -> list:
    """
    Opens Uber once, collects fares for all destinations, then quits driver.
    """
    driver = None
    all_results = []

    try:
        driver = get_driver("uber")
        polite_delay(3.0, 5.0)

        for destination in destinations:
            destination_results = []

            for attempt in range(1, MAX_ATTEMPTS_PER_DESTINATION + 1):
                try:
                    destination_results = _fetch_uber_fares_on_existing_driver(
                        driver,
                        destination,
                        weather
                    )

                    if destination_results:
                        break

                    logger.warning(
                        f"  [Uber] Attempt {attempt} failed for {destination['name']}"
                    )

                    # Try to reset to home before retrying same destination
                    ensure_home_screen(driver, SEL_WHERE_TO, APP_PACKAGE)
                    polite_delay(2.0, 3.0)

                except Exception as e:
                    logger.error(f"  [Uber] Error for {destination['name']}: {e}")
                    debug_screenshot(driver, f"uber_exception_{destination['name']}")

            if destination_results:
                all_results.extend(destination_results)
            else:
                logger.error(f"  [Uber] All attempts failed for {destination['name']}")

        return all_results

    except Exception as e:
        logger.error(f"  [Uber] Driver error: {e}")
        if driver:
            debug_screenshot(driver, "uber_multi_destination_exception")
        return all_results

    finally:
        if driver:
            driver.quit()


def fetch_uber_fares(destination: dict, weather: dict = None) -> list:
    """
    Single-destination wrapper.
    Keeps old scheduler/code compatible.
    """
    return fetch_uber_fares_for_destinations([destination], weather)

def debug_visible_nodes(driver, name="uber_visible_nodes"):
    os.makedirs("debug", exist_ok=True)

    nodes = _visible_text_nodes(driver)
    path = os.path.join("debug", f"{name}.txt")

    with open(path, "w", encoding="utf-8") as f:
        for n in nodes:
            f.write(
                f"{n['label']} | "
                f"x={n['x1']}-{n['x2']} y={n['y1']}-{n['y2']} "
                f"cx={n['cx']} cy={n['cy']}\n"
            )

    logger.info(f"  [Uber] Saved visible nodes dump: {path}")