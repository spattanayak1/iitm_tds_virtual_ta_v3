# TDS Virtual TA Project

## Overview

This project creates a Virtual Teaching Assistant (TA) API for the IIT Madras Tools in Data Science (TDS) course.

The API answers student questions automatically by using course content and forum posts from the TDS Discourse.

---

## Step 1: Data Scraping (Discourse Posts)

I wrote a Python script `scrape_discourse.py` that downloads posts from the TDS Discourse forum between January 1, 2025 and April 14, 2025.

This script collects useful forum discussions to help answer questions accurately.

To run the scraper:

```bash
python scrape_discourse.py
