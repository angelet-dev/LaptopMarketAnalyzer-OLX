import logging
import httpx
import random
import asyncio
from scraper.utils import dump_api_response, update_search_param
import json
import copy

# Some basic API things

url = "https://www.olx.pl/apigateway/graphql"
all_counts_url = "https://www.olx.pl/api/v1/offers/metadata/search/?offset=0&limit=40&category_id=1199&facets=%5B%7B%22field%22%3A%22category_without_exclusions%22%2C%22fetchLabel%22%3Atrue%2C%22fetchUrl%22%3Atrue%2C%22limit%22%3A100%7D%5D"

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

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.olx.pl",
    "referer": "https://www.olx.pl/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-client": "DESKTOP",
    "authorization": "ANONYMOUS",
}

payload = {
    "query": None,
    "variables": {
        "searchParameters": [
            {"key": "offset", "value": "0"},
            {"key": "limit", "value": "40"},
            {"key": "state", "value": "used"},
            {"key": "category_id", "value": "1199"},
        ]
    },
}


async def api_query(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    api_url: str,
    payload: dict,
    **kwargs,
) -> str:
    """
    Makes an API query and returns response text.
    """
    try:
        async with semaphore:
            await asyncio.sleep(random.uniform(1, 3))

            response = await client.post(api_url, json=payload, **kwargs)

            if response.status_code == 403:
                logging.warning(
                    f"Access forbidden (403) for {api_url}. Maybe IP is blocked."
                )
                return None
            elif response.status_code == 429:
                logging.warning("Too many requests (429). Need increased pause!")
                return None

            response.raise_for_status()
            logging.debug("Success get response from OLX API.")

            return response.text

    except httpx.TimeoutException:
        logging.error(f"Timeout ({kwargs.get('timeout', None)} s) on loading {api_url}")
    except httpx.RequestError as e:
        logging.error(f"Network request error for {api_url}: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP status error {e.response.status_code} for {api_url}")
    except Exception as e:
        logging.error(f"Unexpected error {type(e).__name__}: {e}", exc_info=True)

    return None


async def get_total_elements(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    api_url: str,
    payload: dict,
    **kwargs,
) -> int:
    """
    Get total numbers of ads for search target from OLX API query.
    """

    temp_payload = copy.deepcopy(payload)
    temp_payload["query"] = query_total_elements

    try:
        response = await api_query(client, semaphore, api_url, temp_payload, **kwargs)
        if not response:
            return 0

        dict_res = json.loads(response)

        if dict_res.get("errors"):
            logging.error(f"API returned an error: {dict_res.get('errors')}")
            return 0

        total_elements = (
            dict_res.get("data", {})
            .get("clientCompatibleListings", {})
            .get("metadata", {})
            .get("total_elements", 0)
        )

        logging.debug(f"For target find {total_elements} ads.")
        return total_elements

    except Exception as e:
        logging.error(f"Unexpected error {type(e).__name__}: {e}", exc_info=True)
        return 0


async def api_query_catalog(
    s_args: dict, semaphore: asyncio.Semaphore, api_url: str, payload: dict, **kwargs
) -> bool | None:
    """
    Get all ads and dump it from OLX API query for target of search.
    """

    try:
        target = s_args.get("target", "")

        if not target:
            return False

        update_search_param(payload["variables"]["searchParameters"], "query", target)

        async with httpx.AsyncClient() as client:
            total_elements = await get_total_elements(
                client, semaphore, api_url, payload, **kwargs
            )

            if not total_elements:
                logging.warning("No elements found or error occurred.")
                return False

            tasks = []
            payload["query"] = query

            limit = s_args.get("limit", 40)

            for offset in range(0, total_elements, limit):
                tasks_payload = copy.deepcopy(payload)
                update_search_param(
                    tasks_payload["variables"]["searchParameters"], "offset", offset
                )

                tasks.append(
                    asyncio.create_task(
                        api_query(client, semaphore, api_url, tasks_payload, **kwargs)
                    )
                )

            processed_tasks = await asyncio.gather(*tasks, return_exceptions=True)

            for response in processed_tasks:
                if isinstance(response, str):
                    dump_api_response(
                        response, s_args.get("path", f"data/raw/{target}.jsonl")
                    )
                else:
                    logging.error(f"Task failed with error: {response}")

            return True

    except Exception as e:
        logging.error(f"Unexpected error {type(e).__name__}: {e}", exc_info=True)
        return False


async def api_query_targets(
    api_url: str, payload: dict, args: dict, timeout: int, headers: dict
) -> None:
    """
    Distribute targets into async tasks and manage the execution of API queries.
    """

    targets = args.get("targets", [])

    if not targets:
        logging.warning("API got empty or incorrect list of targets.")
        return None

    semaphore = asyncio.Semaphore(5)

    tasks = []

    for i, target in enumerate(targets):
        task_payload = copy.deepcopy(payload)
        task_s_args = {
            "limit": args.get("limit", 40),
            "target": target,
            "path": f"data/raw/{target}_{i}.jsonl",
        }

        tasks.append(
            asyncio.create_task(
                api_query_catalog(
                    task_s_args,
                    semaphore,
                    api_url,
                    task_payload,
                    timeout=timeout,
                    headers=headers,
                )
            )
        )

    processed_tasks = await asyncio.gather(*tasks, return_exceptions=True)

    for i, task_res in enumerate(processed_tasks):
        if isinstance(task_res, Exception):
            logging.error(f"Error ({type(task_res).__name__}): {task_res}")
        elif not task_res:
            logging.warning(f"API query failed to process target {targets[i]}.")
        else:
            logging.info(f"Successfully fetched data for target {targets[i]}!")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(funcName)s(): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    TIME_OUT = 10
    targets = [
    'Apple MacBook Air M2',
    'Lenovo ThinkPad X1 Carbon',
    'Asus ROG Zephyrus G14',
    'Dell XPS 13',
    'Lenovo Legion 5',
    'HP Victus 15',
    'Asus TUF Gaming F15',
    'Acer Nitro 5',
    'Apple MacBook Pro M2',
    'Samsung Galaxy Book3',
    ]
    args = {"limit": 40, "targets": targets}

    asyncio.run(api_query_targets(url, payload, args, TIME_OUT, headers))
