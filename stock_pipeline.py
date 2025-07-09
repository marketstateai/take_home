import os
import requests
from pydantic import BaseModel
import logging
import time
import datetime
import random
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd

path = Path(__file__).parent

BASE_URL="https://api.polygon.io"

def logger_config():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(path / 'etl.log', mode='a')
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)

    # Avoid duplicate handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)
    return logger

logger = logger_config()

class APIClient():
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key

    def get_ticker_urls(
            self, 
            tickers: list[str],
            from_date: str,
            to_date: str,
            timespan: str = "day",
            multiplier: int = 1,
            limit: int = 500,
            offset: int = 0,
            **kwargs
        ) -> dict:
        """
        Example:
            GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}  
        """
        ENDPOINT="/v2/aggs/ticker/"

        URLS={}
        for ticker in tickers:
            URLS[ticker]=self.base_url+ENDPOINT+f"{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}?apiKey={self.api_key}&adjusted=FALSE&sort=desc&limit={limit}&{offset}=0"

        return URLS
    

    def get_json_response(
            self, 
            url: str, 
            max_retries: int = 2
            ) -> dict:
        """       
            Fetches JSON response from the given URL with retry and exponential backoff logic.
            Params:
        """
        retry_delay = 1  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                response = requests.get(url)
                response.raise_for_status()
                return response.json()
            
            except requests.RequestException:
                time.sleep(retry_delay)
                retry_delay *= 2  # Double the delay for the next attempt
                retry_delay += random.uniform(0, 1)  # Add jitter

        raise Exception("Maximum retry attempts reached")


# Initilize client
polygon = APIClient(base_url=BASE_URL, api_key=os.getenv("POLYGON_API"))
logger.info(f"Initialized API client with base URL: {polygon.base_url}")


""" We should definitely consider implementing some model validation here, i.e., Pydantic"""
class Delivery(BaseModel):
    v: float
    vw: float
    h: float
    l: float
    t: int
    vw: float
    n: float
    status: str
    ticker: str
    request_id: str
    queryCount: int



tickers = ['AAPL', 'MSFT', 'GOOGL']

logger.info(f"Fetching data for tickers: {tickers}")
urls = polygon.get_ticker_urls( 
    tickers=tickers,
    from_date="2025-01-01",
    to_date="2025-01-03"
    )

logger.info(f"First URL to be processed: {list(urls.keys())[0]}")

responses=[]

for k, v in urls.items():
    start = datetime.datetime.now()
    
    try:
        response = polygon.get_json_response(v)
        results = response.get('results', None)

        # Sort by unix timestamp
        results = sorted(results, key=lambda x: x['t'])

        day_before = None  # initialize the previous day variable
        for day in results:
            # Convert ET to UTC
            unix_nano = day['t']
            unix = unix_nano / 1_000
            dt_et = datetime.datetime.fromtimestamp(unix, tz=ZoneInfo("America/New_York"))
            day['datetime_utc'] = dt_et.astimezone(ZoneInfo("UTC"))

            # Outcome logic
            if day_before:
                if day['c'] > day['o'] and day['v'] > day_before['v']:
                    day['outcome'] = 'bull'
                elif day['c'] < day['o'] and day['v'] > day_before['v']:
                    day['outcome'] = 'bear'
                else:
                    day['outcome'] = 'neutral'

        day_before = day

        status = "success"
    except Exception as e:
        logger.error(f"Error fetching data for {k}: {e}")
        status = "error"

    t2 = datetime.datetime.now()

    responses.append({
            "url": k,
            "response": response,
            "execution_time": start,
            "execution_duration": t2-start,
            "status": status
        })

#  Deduplication, since the response is of two granularities, a single set metadata per response and N-set of prices for the given period and frequency, we must define these explicitly.
#  For brevity, you might not deduplicate until the staging layer, and split out the metadata and prices into separate tables.
#  While this creates some redudancy in the extraction process, the data can be normalized later in the pipeline and you can leverage Pandas vast set of methods. 
if responses:
    try:
        df = pd.json_normalize(
            responses,
            record_path=['response', 'results'],
            meta=[
                'status',
                'url',
                ['response', 'adjusted'],
                ['response', 'count'],
                ['response', 'queryCount'],
                ['response', 'request_id'],
                ['response', 'resultsCount'],
                ['response', 'status'],
                ['response', 'ticker'],
                ['execution_time'],
                ['execution_duration']
            ]
        )

        df = df.drop_duplicates()

        df.to_json(path/"results.json", indent=4)
        logger.info(f"Successfully deduped and saved results to {path/'results.json'}")
    except Exception as e:
        logger.error(f"Error during deduplication or saving results: {e}")