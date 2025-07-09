# Polygon Ticker Data ETL Script

This Python script fetches aggregated daily stock price data for specified tickers using the [Polygon.io API](https://polygon.io/).
Specifically, it parses the data, enchances the metadata and saves the deduplicated results to a JSON file after flattening it.

## Features

- An extensible framework for working with APIs
- Fetches price data for multiple tickers across a date range.
- Automatically constructs the appropriate API URLs.
- Includes retry logic with exponential backoff and jitter.
- Adds UTC datetime and a basic "bull/bear" outcome label based on price/volume changes.
- Logs processing steps and errors to `etl.log`.
- Outputs deduplicated results to `results.json`.

## Requirements

- Python 3.10+

### Python Dependencies

Install dependencies with:

```bash
pip install -r requirements.txt
