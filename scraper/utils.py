import json
import logging

def dump_api_response(response: str, path: str) -> bool:
    """
    Dump in JSONL file raw data from API response.
    Returns True if successful, False otherwise.
    """

    if not response:
        logging.warning("Received empty or None response. Skipping.")
        return False

    try:
        dict_response = (
            json.loads(response).get("data", {}).get("clientCompatibleListings", {})
        )
        response_keys = dict_response.keys()
    except Exception as e:
        logging.error(f"Failed to parse JSON structure. Error {type(e).__name__}: {e}")
        return False

    for key in response_keys:
        match key:
            case "error":
                logging.error(f"API returned an error: {dict_response.get('error')}")

            case "metadata":
                logging.info("This response contains metadata.")

            case "data":
                try:
                    ads = dict_response.get("data", [])

                    with open(path, "a", encoding="utf-8") as f:
                        for ad in ads:
                            json_string = json.dumps(ad, ensure_ascii=False)
                            f.write(json_string + "\n")

                    logging.debug(f"Successfully dumped {len(ads)} ads.")
                except Exception as e:
                    logging.error(f"File write error {type(e).__name__}: {e}")
                    return False

            case _:
                logging.warning(f"Unexpected key found in response: {key}")

    return True

def update_search_param(search_parameters: list, key: str, value: str):
    """
    Update search parameters in payload.
    """
    for param in search_parameters:
        if param.get("key") == key:
            param["value"] = str(value)
            return

    search_parameters.append({"key": key, "value": str(value)})