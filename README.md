# TDS Virtual TA Project

## Overview

This project builds a Virtual Teaching Assistant (TA) API for the IIT Madras Tools in Data Science (TDS) course.

The API automatically answers student questions based on:

- Course content for TDS Jan 2025 as of April 15, 2025
- TDS Discourse forum posts from Jan 1, 2025 to Apr 14, 2025

---

## Project Structure

- `scrape_discourse.py`: Python script to scrape TDS forum posts from Discourse.
- `tds_knowledge.db`: Database containing course and forum data.
- `app.py`: Flask API server that processes student questions and returns answers.
- `requirements.txt`: Python dependencies.

---

## How to Use

### 1. Run the Scraper

This script downloads forum posts and saves data locally.

```bash
python scrape_discourse.py
