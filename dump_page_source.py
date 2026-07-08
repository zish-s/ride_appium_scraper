"""
Standalone diagnostic: launches Uber via Appium (using the real get_driver
function), taps into the pickup/destination search screen, and dumps the
raw accessibility tree so we can see EXACTLY how the pickup and destination
input fields are represented — instead of guessing at selectors again.

Run this directly:  python dump_page_source.py
"""
import time
from collectors.base_collector import get_driver, wait_and_find, wait_and_find_all

SEL_WHERE_TO = ("accessibility id", "Enter pickup location")
SEL_EDIT_TEXT = ("id", "com.ubercab:id/edit_text")

print("Launching Uber (via the real get_driver function)...")
driver = get_driver("uber")

print("Waiting 15s for the home screen to fully render...")
time.sleep(15)

print("Tapping 'Enter pickup location'...")
el = wait_and_find(driver, *SEL_WHERE_TO, timeout=20)
if el:
    el.click()
    time.sleep(3)
else:
    print("Could not find 'Enter pickup location' — dumping home screen instead.")

source = driver.page_source
with open("page_source_dump.xml", "w", encoding="utf-8") as f:
    f.write(source)

print("Saved to page_source_dump.xml")
print()

# Quick sanity checks
if "com.ubercab" in source:
    print("SUCCESS: com.ubercab found in the page source.")
else:
    print("Uber NOT found in page source — still on some other screen.")

edit_text_count = source.count('resource-id="com.ubercab:id/edit_text"')
print(f"Elements matching resource-id 'com.ubercab:id/edit_text': {edit_text_count}")
print()

# Print anything that looks like an input field, hint, or pickup/destination label
for line in source.splitlines():
    line_lower = line.lower()
    if any(kw in line_lower for kw in ["edittext", "edit_text", "pickup", "destination", "where to", "search"]):
        print(line.strip())
        print()

driver.quit()