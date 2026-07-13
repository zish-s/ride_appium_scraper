# Ride-Hailing Fare Data Collector

This project is a Python + Appium based scraper for collecting real-time ride fare estimates from ride-hailing apps, currently focused on Uber.

It automates the Uber app on an Android device, enters a fixed pickup location and multiple destinations, reads the visible ride options, scrolls through the fare list, and stores selected fare data into a CSV file.

## Purpose

This tool is built as part of my research project on:

**Decision-Making Recommendation Framework for Riders in Ride-Hailing Services**

The collected data will be used to study how ride fares and ETAs change across different times, destinations, weather conditions, and vehicle types. This can later support a rider-facing recommendation system that suggests whether to **book now or wait**, based on fare trends and possible regret/loss from making a poor booking decision.

## Current Features

- Opens Uber using Appium
- Uses a fixed pickup point
- Collects fares for multiple destinations
- Reads fare data from visible screen text
- Scrolls to collect more vehicle options
- Captures fare, ETA, weather, temperature, timestamp, and destination
- Saves collected data into a CSV file
- Filters the dataset for selected vehicle types such as:
  - Uber Go AC
  - Auto
  - Bike

## Project Structure

```text
ride_appium_scraper/
│
├── scheduler.py              # Runs collection cycles and writes CSV data
├── config.py                 # Stores pickup, destinations, time interval, output path
│
├── collectors/
│   ├── uber_collector.py     # Uber automation and fare collection logic
│   ├── weather_collector.py  # Weather data collection
│   └── base_collector.py     # Shared Appium helper functions
│
├── data/                     # Output CSV files
├── logs/                     # Runtime logs
└── debug/                    # Screenshots and page-source debug dumps
```

## Future Updates

- Extend data collection to Ola and Rapido for cross-platform fare comparison.
- Scale data collection across more routes, pickup points, and time periods.
- Collect data across minimum 2 weeks, to study fare variation patterns.
- Add Google Maps traffic/ETA, route distance, rain intensity, and congestion features.
- Train fare prediction models using the collected dataset.
- Develop a rider decision recommendation system that suggests whether to book now or wait.
- Define an asymmetric regret loss function where the cost of wrongly recommending `Wait` when fares rise is treated as higher than wrongly recommending `Book Now` when fares later fall.
- Train and compare baseline models such as Always Book, Always Wait, Log-Linear Regression, Random Forest, and XGBoost.
