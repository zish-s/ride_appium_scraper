# ============================================================
# collectors/weather_collector.py
# Fetches weather for Delhi using Open-Meteo (free, no key)
# ============================================================

import requests
import logging
from config import PICKUP

logger = logging.getLogger(__name__)

# Open-Meteo WMO weather code → human-readable label
WMO_CODES = {
    0: "clear", 1: "mostly_clear", 2: "partly_cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy_rain",
    71: "snow", 73: "snow", 75: "heavy_snow",
    80: "showers", 81: "showers", 82: "heavy_showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def get_weather() -> dict:
    """
    Returns current weather at pickup coordinates.
    Falls back gracefully if the request fails.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":   PICKUP["lat"],
            "longitude":  PICKUP["lng"],
            "current":    "temperature_2m,precipitation,weathercode,windspeed_10m",
            "timezone":   "Asia/Kolkata",
            "forecast_days": 1,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        current = resp.json()["current"]

        code      = current.get("weathercode", 0)
        condition = WMO_CODES.get(code, "unknown")
        temp      = current.get("temperature_2m", "")
        rain      = current.get("precipitation", 0)

        logger.info(f"  [Weather] {condition}, {temp}°C, rain={rain}mm")
        return {"condition": condition, "temp_c": temp, "rain_mm": rain}

    except Exception as e:
        logger.warning(f"  [Weather] Failed to fetch: {e}")
        return {"condition": "", "temp_c": "", "rain_mm": ""}
