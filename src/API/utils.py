import os
from dotenv import load_dotenv
from typing import Dict, Optional

# Define constants for configuration keys
API_KEY = "API_KEY"
API_SECRET = "API_SECRET"
REST_BASE_URL = "REST_BASE_URL"
WEBSOCKET_URI = "WEBSOCKET_URI"
WS_GET_KEY_URL = "WS_GET_KEY_URL"
WS_REFRESH_KEY_URL = "WS_REFRESH_KEY_URL"
WS_DESTROY_KEY_URL = "WS_DESTROY_KEY_URL"

# Default URLs if not found in environment variables
DEFAULT_REST_BASE_URL = "https://api.lbank.info/v2/"
DEFAULT_WEBSOCKET_URI = "wss://www.lbkex.net/ws/V2/"
DEFAULT_WS_GET_KEY_URL = "https://api.lbank.info/v2/subscribe/get_key.do"
DEFAULT_WS_REFRESH_KEY_URL = "https://api.lbank.info/v2/subscribe/refresh_key.do"
DEFAULT_WS_DESTROY_KEY_URL = "https://api.lbank.info/v2/subscribe/destroy_key.do"


def load_config() -> Dict[str, Optional[str]]:
    """
    Loads configuration from environment variables.

    Looks for API_KEY, API_SECRET, REST_BASE_URL, WEBSOCKET_URI,
    WS_GET_KEY_URL, WS_REFRESH_KEY_URL, WS_DESTROY_KEY_URL.
    Provides default values for URLs if not set.

    Returns:
        Dict[str, Optional[str]]: A dictionary containing the configuration values.
                                   API_KEY and API_SECRET might be None if not set.
    """
    load_dotenv()  # Load .env file if present

    config = {
        API_KEY: os.getenv(API_KEY),
        API_SECRET: os.getenv(API_SECRET),
        REST_BASE_URL: os.getenv(REST_BASE_URL, DEFAULT_REST_BASE_URL),
        WEBSOCKET_URI: os.getenv(WEBSOCKET_URI, DEFAULT_WEBSOCKET_URI),
        WS_GET_KEY_URL: os.getenv(WS_GET_KEY_URL, DEFAULT_WS_GET_KEY_URL),
        WS_REFRESH_KEY_URL: os.getenv(WS_REFRESH_KEY_URL, DEFAULT_WS_REFRESH_KEY_URL),
        WS_DESTROY_KEY_URL: os.getenv(WS_DESTROY_KEY_URL, DEFAULT_WS_DESTROY_KEY_URL),
    }

    # Basic validation/warning for missing credentials
    if not config[API_KEY] or not config[API_SECRET]:
        print(f"Warning: {API_KEY} or {API_SECRET} not found in environment variables"
              + "or .env file.")
        print("Authenticated endpoints will likely fail.")

    return config


# Example usage:
if __name__ == "__main__":
    config = load_config()
    print("Loaded Configuration:")
    for key, value in config.items():
        # Mask secrets for printing
        if key == API_SECRET and value:
            print(f"  {key}: {'*' * (len(value) - 4)}{value[-4:]}")
        else:
            print(f"  {key}: {value}")
