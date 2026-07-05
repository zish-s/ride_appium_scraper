# Setup Guide — Ride Fare Scraper (Appium + Android Emulator)

## Step 1 — Install Android Studio and create an emulator

1. Download Android Studio: https://developer.android.com/studio
2. Open it → Tools → Device Manager → Create Device
3. Pick **Pixel 6** (or any modern phone template)
4. Select system image: **Android 13 (API 33)**
5. Click Finish, then press the ▶ Play button to start the emulator
6. You'll see a virtual phone on your screen

---

## Step 2 — Install the 3 apps on the emulator

Inside the running emulator, open the Play Store and install:
- Uber
- Ola Cabs
- Rapido

Log into each app with your real account. Do this once — the
`noReset: True` setting in config.py keeps your session alive
between runs.

---

## Step 3 — Install Appium

```bash
npm install -g appium
appium driver install uiautomator2
```

Also install the Appium Inspector desktop app:
https://github.com/appium/appium-inspector/releases
(download the .exe or .dmg for your OS)

---

## Step 4 — Find the real selectors using Appium Inspector

This is the one manual step you do once per app.

**Start the Appium server first:**
```bash
appium
```
It should say "Appium REST http interface listener started"

**Open Appium Inspector:**
1. Set Server URL: `http://localhost`  Port: `4723`
2. Paste these Desired Capabilities:
```json
{
  "platformName": "Android",
  "platformVersion": "13",
  "deviceName": "emulator-5554",
  "automationName": "UiAutomator2",
  "appPackage": "com.ubercab",
  "appActivity": "com.ubercab.presidio.app.core.activity.AppMainActivity",
  "noReset": true
}
```
3. Click **Start Session** — Uber opens on the emulator
4. In the Inspector, click any element (e.g. the pickup field)
5. On the right panel you'll see **resource-id**, **content-desc**, etc.
6. Copy the resource-id value

**Replace the FIND_ME strings in the collector files:**

Open `collectors/uber_collector.py` and replace each `"FIND_ME_..."` 
with the real resource-id you found in Inspector.

Example — if Inspector shows:
```
resource-id: com.ubercab:id/ub__search_pick_up_container
```
Then change:
```python
# Before
SEL_PICKUP_FIELD = (By.ID, "FIND_ME_pickup_field")
# After
SEL_PICKUP_FIELD = (By.ID, "com.ubercab:id/ub__search_pick_up_container")
```

Repeat this for Ola (`ola_collector.py`) and Rapido (`rapido_collector.py`).

---

## Step 5 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 6 — Configure your routes

Open `config.py` and set your pickup and 3 destinations.
You can get latitude/longitude from https://www.latlong.net/

---

## Step 7 — Test with a single cycle first

With the emulator running and Appium server running:

```bash
python scheduler.py --once
```

Watch the terminal. You should see the script open each app,
search fares, and print results. Check `data/fares.csv` after.

---

## Step 8 — Run the full collection

```bash
# Collect every 30 min for 1 hour:
python scheduler.py

# Collect every 20 min for a full day:
python scheduler.py --interval 20
# (also set TOTAL_HOURS = 24 in config.py)
```

---

## What to expect per cycle

| | Rows per cycle |
|---|---|
| 3 apps × 3 destinations × ~3 vehicle types | ~27 rows |
| 1 hour at 30-min interval (2 cycles) | ~54 rows |
| 1 hour at 20-min interval (3 cycles) | ~81 rows |
| 1 full day at 30-min interval (48 cycles) | ~1,200–1,300 rows |

---

## If something breaks mid-run

Check `data/scraper.log` — every failure is logged with the
reason. The script continues to the next app/destination even
if one fails, so you won't lose the whole cycle over one error.
