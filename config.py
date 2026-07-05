# ============================================================
# config.py — Edit this file to set your routes and schedule
# ============================================================

# ── Your fixed pickup point ──────────────────────────────────
# Replace with your actual pickup location name and coordinates
# Get coordinates from: https://www.latlong.net/
PICKUP = {
    "name": "IGDTUW",               # <-- change to your pickup
    "lat":  28.7538,                # <-- change to your pickup lat
    "lng":  77.1174,                # <-- change to your pickup lng
}

# ── Your 3 destinations ──────────────────────────────────────
DESTINATIONS = [
    {
        "name": "AIIMS Hospital Delhi",
        "lat":  28.5665,
        "lng":  77.2100,
    },
    {
        "name": "Connaught Place",
        "lat":  28.6289,
        "lng":  77.2065,
    },
    {
        "name": "IGI Airport Terminal 1",
        "lat":  28.5562,
        "lng":  77.1000,
    },
]

# ── Collection schedule ──────────────────────────────────────
INTERVAL_MINUTES = 30       # how often to collect (20 or 30 recommended)
TOTAL_HOURS      = 1        # how long to run in total
                            # set to 24 for a full day

# ── Output ───────────────────────────────────────────────────
CSV_OUTPUT_PATH = "data/fares.csv"
LOG_PATH        = "data/scraper.log"

# ── Android emulator / Appium settings ───────────────────────
APPIUM_SERVER_URL = "http://localhost:4723"

# These are the emulator capabilities — works with Android Studio AVD
DESIRED_CAPS_BASE = {
    "platformName":         "Android",
    "platformVersion":      "16",       # confirmed from Appium Inspector
    "deviceName":           "RZCY9135SJX",  # your phone serial
    "automationName":       "UiAutomator2",
    "noReset":              True,       # keeps you logged in between runs
    "fullReset":            False,
    "newCommandTimeout":    120,
    "autoGrantPermissions": False,
}

# ── App package names (do not change) ────────────────────────
APPS = {
    "uber": {
        "appPackage":  "com.ubercab",
        # appActivity removed — Appium launches default activity automatically
    },
    "ola": {
        "appPackage":  "com.olacabs.customer",
    },
    "rapido": {
        "appPackage":  "com.rapido.passenger",
    },
}
