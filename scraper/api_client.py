import requests
import logging
import json 
import time 
import random
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Some basic API things

url = "https://www.olx.pl/apigateway/graphql"

query = """
query ListingSearchQuery($searchParameters: [SearchParameter!] = []) {
  clientCompatibleListings(searchParameters: $searchParameters) {
    ... on ListingSuccess {
      metadata {
        total_elements
        visible_total_count
      }

      data {
        id        
        title
        description
        url
        created_time
        valid_to_time
        last_refresh_time
        status
        business
        location {
          city { name }
          region { name }
        }
        photos {
          link
          height
          rotation
          width
        }
        params {
          name
          value {
            ... on PriceParam { value currency }
            ... on GenericParam { key label }
          }
        }
        user {
          id
        }
      }
    }
    ... on ListingError {
      __typename
      error {
        code
        detail
        status
        title
        validation {
          detail
          field
          title
        }
      }
    }
  }
}
"""

payload = {
    "query": query,
    "variables": {
  "searchParameters": [
    { "key": "query", "value": "macbook pro 13 m1" },
    { "key": "price:from", "value": "1500" },
    { "key": "price:to", "value": "2500" },
    { "key": "state", "value": "used" },
    { "key": "offset", "value": "120" },
    { "key": "limit", "value": "50" }
  ]
}
}


headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.olx.pl",
    "referer": "https://www.olx.pl/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-client": "DESKTOP",
    "authorization": "ANONYMOUS" 
}


def fetch_api_catalog(api_url: str, payload: dict, header: dict, TIME_OUT = 10):
    """
    Fetch raw advertisement data from the OLX API via a POST request and append it to a JSONL file.
    """

    try:         
        time.sleep(random.randint(1,5))

        response = requests.post(api_url, json=payload, headers = header, timeout = TIME_OUT)

        if response.status_code == 403:
            logging.warning(f"Access forbidden (403) for {url}. Maybe IP is blocked.")
            return None
        elif response.status_code == 429:
            logging.warning("Too many requests (429). Need increased pause!")
            return None
        
        response.raise_for_status()
        
        if "error" in response.text:
            api_error_output = response.json()["data"]["clientCompatibleListings"]["error"]
            logging.warning(f"API return error: {api_error_output}")
            return api_error_output["code"]
        
        ads = response.json()["data"]["clientCompatibleListings"]["data"]

        with open('data/raw/1.jsonl','a',encoding='utf-8') as f:
            for ad in ads:
                json_string = json.dumps(ad, ensure_ascii=False)
                f.write(json_string + '\n')

        return True

    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error for {api_url}: {e}")
    except requests.exceptions.ConnectionError:
        logging.error(f"Network connection error while attempting to open {api_url}")
    except requests.exceptions.Timeout:
        logging.error(f"Timeout (10 s) on loading {api_url}")
    except Exception as e:
        logging.error(f"Unpredictable error: {e}", exc_info=True)
        
    return None

