import requests
import logging
import httpx
import random
import asyncio
from scraper.utils import dump_api_response

# Some basic API things

url = "https://www.olx.pl/apigateway/graphql"


query_total_elements = """
query ListingSearchQuery($searchParameters: [SearchParameter!] = []) {
  clientCompatibleListings(searchParameters: $searchParameters) {
    ... on ListingSuccess {
      metadata {
        total_elements
        visible_total_count
      }
    }
  }
}
"""

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
            {"key": "query", "value": "macbook pro 13 m1"},
            {"key": "price:from", "value": "1500"},
            {"key": "price:to", "value": "2500"},
            {"key": "state", "value": "used"},
            {"key": "offset", "value": "120"},
            {"key": "limit", "value": "50"},
        ]
    },
}


headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.olx.pl",
    "referer": "https://www.olx.pl/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-client": "DESKTOP",
    "authorization": "ANONYMOUS",
}


async def api_query(api_url: str, payload: dict, TIME_OUT=10, **kwargs) -> str:
    """
    Makes an API query and returns response text.
    """
    try:
        await asyncio.sleep(random.random() * 2)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, json=payload, timeout=TIME_OUT, **kwargs
            )

        if response.status_code == 403:
            logging.warning(
                f"Access forbidden (403) for {api_url}. Maybe IP is blocked."
            )
            return None
        elif response.status_code == 429:
            logging.warning("Too many requests (429). Need increased pause!")
            return None

        response.raise_for_status()
        return response.text

    except requests.exceptions.Timeout:
        logging.error(f"Timeout ({TIME_OUT} s) on loading {api_url}")
    except requests.exceptions.ConnectionError:
        logging.error(f"Network connection error while attempting to open {api_url}")
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error for {api_url}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error {type(e).__name__}: {e}", exc_info=True)

    return None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(funcName)s(): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    response = asyncio.run(api_query(url, payload, headers=headers))
    dump_api_response(response, "data/raw/1.jsonl")
