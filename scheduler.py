#!/usr/bin/env python3
import csv
import logging
import os
import sys
import time
import argparse
from datetime import datetime
import re

from config import (
    DESTINATIONS, INTERVAL_MINUTES, TOTAL_HOURS,
    CSV_OUTPUT_PATH, LOG_PATH
)
from collectors.uber_collector import fetch_uber_fares_for_destinations
# from collectors.ola_collector import fetch_ola_fares
# from collectors.rapido_collector import fetch_rapido_fares
from collectors.weather_collector import get_weather

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "timestamp", "date", "time", "day_of_week",
    "platform", "vehicle_type",
    "pickup", "destination",
    "fare", "eta_minutes",
    "weather", "temp_c",
    "cycle_number",
]

TARGET_VEHICLE_ALIASES = {
    "uber_go_ac": ["uber go ac", "go ac"],
    "auto": ["auto"],
    "bike": ["bike", "moto", "uber moto"],
}


def normalize_vehicle_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").lower().strip())


def get_target_vehicle_category(vehicle_name: str):
    name = normalize_vehicle_name(vehicle_name)

    for category, aliases in TARGET_VEHICLE_ALIASES.items():
        for alias in aliases:
            if alias in name:
                return category

    return None


def filter_target_vehicle_rows(rows: list) -> list:
    """
    Keeps only Uber Go AC, Auto, and Bike/Moto rows.
    """
    filtered = []

    for row in rows:
        category = get_target_vehicle_category(row.get("vehicle_type", ""))

        if category:
            filtered.append(row)

    return filtered


def write_rows(rows: list, cycle: int):
    if not rows:
        return
    file_exists = os.path.isfile(CSV_OUTPUT_PATH)
    with open(CSV_OUTPUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for row in rows:
            row["cycle_number"] = cycle
            writer.writerow(row)
    logger.info(f"  Saved {len(rows)} rows to {CSV_OUTPUT_PATH}")


def run_one_cycle(cycle: int) -> int:
    now       = datetime.now()
    timestamp = now.isoformat(timespec="seconds")
    date_str  = now.strftime("%Y-%m-%d")
    time_str  = now.strftime("%H:%M")
    day_str   = now.strftime("%A")

    logger.info(f"{'='*55}")
    logger.info(f"  CYCLE {cycle}  |  {timestamp}")
    logger.info(f"{'='*55}")

    weather  = get_weather()
    all_rows = []

    logger.info("-- Uber --")
    
    try:
        rows = fetch_uber_fares_for_destinations(DESTINATIONS, weather)
        
        # If you added filtering for only Uber Go AC / Auto / Bike, keep this line
        rows = filter_target_vehicle_rows(rows)
        
        for row in rows:
            row.update({
            "timestamp":   timestamp,
            "date":        date_str,
            "time":        time_str,
            "day_of_week": day_str,
            })
        
        all_rows.extend(rows)
        
    except Exception as e:
        logger.error(f"  [Uber] Failed: {e}")

    write_rows(all_rows, cycle)
    logger.info(f"  Cycle {cycle} complete - {len(all_rows)} rows collected")
    return len(all_rows)


def main():
    parser = argparse.ArgumentParser(description="Ride fare data collector")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--interval", type=int, default=INTERVAL_MINUTES)
    args = parser.parse_args()

    interval_sec  = args.interval * 60
    total_seconds = TOTAL_HOURS * 3600
    max_cycles    = 1 if args.once else int(total_seconds / interval_sec)

    logger.info(f"Starting fare collector")
    logger.info(f"  Interval  : every {args.interval} min")
    logger.info(f"  Duration  : {'1 cycle (--once)' if args.once else f'{TOTAL_HOURS} hour(s)'}")
    logger.info(f"  Max cycles: {max_cycles}")
    logger.info(f"  Output    : {CSV_OUTPUT_PATH}")

    total_rows = 0
    for cycle in range(1, max_cycles + 1):
        cycle_start = time.time()
        total_rows += run_one_cycle(cycle)

        if cycle < max_cycles:
            elapsed = time.time() - cycle_start
            sleep   = max(0, interval_sec - elapsed)
            wake_at = datetime.fromtimestamp(time.time() + sleep).strftime("%H:%M:%S")
            logger.info(f"  Sleeping {sleep/60:.1f} min - next run at {wake_at}")
            time.sleep(sleep)

    logger.info(f"Collection complete. Total rows: {total_rows}")


if __name__ == "__main__":
    main()