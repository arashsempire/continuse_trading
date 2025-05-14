import os
from dotenv import load_dotenv
from typing import Dict, Optional

import asyncio

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
        print(
            f"Warning: {API_KEY} or {API_SECRET} not found in environment variables"
            + "or .env file."
        )
        print("Authenticated endpoints will likely fail.")

    return config


class StateCache:
    """
    A thread-safe in-memory cache for storing balances, open orders, and kline (kbar) data.
    Uses asyncio locks to ensure safe concurrent access in async environments.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._balances = {}
        self._orders = {}
        self._kbars = {}  # format: {symbol: [list of kline data]}

    async def update_balances(self, data: dict):
        async with self._lock:
            self._balances.update(data)

    async def update_order(self, order_id: str, order_data: dict):
        async with self._lock:
            self._orders[order_id] = order_data

    async def close_order(self, order_id: str):
        async with self._lock:
            self._orders.pop(order_id, None)

    async def set_balances(self, full_snapshot: dict):
        async with self._lock:
            self._balances = full_snapshot

    async def set_orders(self, full_snapshot: dict):
        async with self._lock:
            self._orders = full_snapshot

    async def get_balances(self) -> dict:
        async with self._lock:
            return self._balances.copy()

    async def get_orders(self) -> dict:
        async with self._lock:
            return self._orders.copy()

    async def update_kbar(self, symbol: str, kbar_data: dict):
        """Append or update kbar data for a symbol."""
        async with self._lock:
            if symbol not in self._kbars:
                self._kbars[symbol] = []
            self._kbars[symbol].append(kbar_data)

    async def get_kbars(self, symbol: str) -> list:
        """Retrieve kbar data for a specific symbol."""
        async with self._lock:
            return list(self._kbars.get(symbol, []))

    async def set_kbars(self, symbol: str, kbars: list):
        """Set a full kbar list for a symbol."""
        async with self._lock:
            self._kbars[symbol] = kbars


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
