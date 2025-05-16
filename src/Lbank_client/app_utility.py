import os
import asyncio
from typing import Dict, Optional, List, Any
from dotenv import load_dotenv

# Define constants for configuration keys to ensure consistency
API_KEY_ENV = "API_KEY"
API_SECRET_ENV = "API_SECRET"
REST_BASE_URL_ENV = "REST_BASE_URL"
WEBSOCKET_URI_ENV = "WEBSOCKET_URI"
WS_GET_KEY_URL_ENV = "WS_GET_KEY_URL"
WS_REFRESH_KEY_URL_ENV = "WS_REFRESH_KEY_URL"
WS_DESTROY_KEY_URL_ENV = "WS_DESTROY_KEY_URL"
DEFAULT_WS_PAIR_ENV = "DEFAULT_WS_PAIR"  # Added for ClientManager default pair

# Default URLs if not found in environment variables
DEFAULT_REST_BASE_URL = "https://api.lbank.info/v2/"
DEFAULT_WEBSOCKET_URI = "wss://www.lbkex.net/ws/V2/"  # Note: Original was wss://www.lbkex.net, LBank docs often
# show ws://openapi-ws.lbank.info/ws/V2/
DEFAULT_WS_GET_KEY_URL = (
    "https://api.lbank.info/v2/subscribe/get_key.do"  # Original: user/subscribe/key
)
# Original: user/subscribe/key/refresh
DEFAULT_WS_REFRESH_KEY_URL = "https://api.lbank.info/v2/subscribe/refresh_key.do"
# Original: user/subscribe/key/destroy
DEFAULT_WS_DESTROY_KEY_URL = "https://api.lbank.info/v2/subscribe/destroy_key.do"
DEFAULT_DEFAULT_WS_PAIR = "eth_usdt"


def load_config() -> Dict[str, Optional[str]]:
    """
    Loads configuration from environment variables using python-dotenv.

    Looks for API_KEY, API_SECRET, REST_BASE_URL, WEBSOCKET_URI,
    WS_GET_KEY_URL, WS_REFRESH_KEY_URL, WS_DESTROY_KEY_URL, and DEFAULT_WS_PAIR.
    Provides default values for URLs and the default pair if not set in the environment.

    Returns:
        Dict[str, Optional[str]]: A dictionary containing the configuration values.
                                   API_KEY and API_SECRET might be None if not set,
                                   triggering a warning.
    """
    load_dotenv()  # Load .env file if present in the current directory or parent directories

    config = {
        API_KEY_ENV: os.getenv(API_KEY_ENV),
        API_SECRET_ENV: os.getenv(API_SECRET_ENV),
        REST_BASE_URL_ENV: os.getenv(REST_BASE_URL_ENV, DEFAULT_REST_BASE_URL),
        WEBSOCKET_URI_ENV: os.getenv(WEBSOCKET_URI_ENV, DEFAULT_WEBSOCKET_URI),
        WS_GET_KEY_URL_ENV: os.getenv(WS_GET_KEY_URL_ENV, DEFAULT_WS_GET_KEY_URL),
        WS_REFRESH_KEY_URL_ENV: os.getenv(
            WS_REFRESH_KEY_URL_ENV, DEFAULT_WS_REFRESH_KEY_URL
        ),
        WS_DESTROY_KEY_URL_ENV: os.getenv(
            WS_DESTROY_KEY_URL_ENV, DEFAULT_WS_DESTROY_KEY_URL
        ),
        DEFAULT_WS_PAIR_ENV: os.getenv(DEFAULT_WS_PAIR_ENV, DEFAULT_DEFAULT_WS_PAIR),
    }

    # Basic validation/warning for missing credentials
    if not config[API_KEY_ENV] or not config[API_SECRET_ENV]:
        # Using print as logger might not be configured when this module is imported.
        print(
            f"Warning: {API_KEY_ENV} or {API_SECRET_ENV} not found in environment variables "
            "or .env file. Authenticated API features will be unavailable or fail."
        )

    return config


class StateCache:
    """
    An asynchronous, in-memory cache for storing application state like
    balances, open orders, and kline (kbar) data.
    Uses asyncio.Lock to ensure safe concurrent access from different async tasks.
    """

    def __init__(self):
        """Initializes the StateCache with empty stores and an asyncio Lock."""
        self._lock = asyncio.Lock()
        self._balances: Dict[str, Dict[str, str]] = (
            {}
        )  # e.g., {"USDT": {"free": "100", "frozen": "10"}}
        self._orders: Dict[str, Dict[str, Any]] = (
            {}
        )  # e.g., {"order_id_123": {"symbol": "btc_usdt", ...}}
        self._kbars: Dict[str, List[Dict[str, Any]]] = (
            {}
        )  # e.g., {"btc_usdt": [{"time": 123, "open": ...}, ...]}

    async def update_balances(self, balance_data: Dict[str, Dict[str, str]]):
        """
        Updates existing balances or adds new ones. Merges with current data.

        Args:
            balance_data (Dict[str, Dict[str, str]]): A dictionary where keys are asset symbols
                                                     (e.g., "USDT") and values are dictionaries
                                                     with "free" and "frozen" amounts.
        """
        async with self._lock:
            for asset, amounts in balance_data.items():
                if asset not in self._balances:
                    self._balances[asset] = {}
                self._balances[asset].update(amounts)

    async def set_balances(self, full_snapshot: Dict[str, Dict[str, str]]):
        """
        Overwrites the entire balances cache with a new snapshot.

        Args:
            full_snapshot (Dict[str, Dict[str, str]]): The complete new set of balances.
        """
        async with self._lock:
            self._balances = full_snapshot

    async def get_balances(self) -> Dict[str, Dict[str, str]]:
        """
        Retrieves a copy of the current balances.

        Returns:
            Dict[str, Dict[str, str]]: A copy of the balances dictionary.
        """
        async with self._lock:
            return self._balances.copy()

    async def update_order(self, order_id: str, order_data: Dict[str, Any]):
        """
        Adds a new order or updates an existing one in the cache.

        Args:
            order_id (str): The unique identifier of the order.
            order_data (Dict[str, Any]): The dictionary containing order details.
        """
        async with self._lock:
            self._orders[order_id] = order_data

    async def close_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Removes an order from the cache, typically when it's closed or cancelled.

        Args:
            order_id (str): The ID of the order to remove.

        Returns:
            Optional[Dict[str, Any]]: The data of the removed order if it existed, else None.
        """
        async with self._lock:
            return self._orders.pop(order_id, None)

    async def set_orders(self, full_snapshot: Dict[str, Dict[str, Any]]):
        """
        Overwrites the entire open orders cache with a new snapshot.

        Args:
            full_snapshot (Dict[str, Dict[str, Any]]): The complete new set of open orders.
        """
        async with self._lock:
            self._orders = full_snapshot

    async def get_orders(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves a copy of the current open orders.

        Returns:
            Dict[str, Dict[str, Any]]: A copy of the open orders dictionary.
        """
        async with self._lock:
            return self._orders.copy()

    async def update_kbar(self, symbol: str, kbar_data: Dict[str, Any]):
        """
        Appends a new kbar (candlestick) data point to the list for a given symbol.
        If the symbol doesn't exist, it initializes a new list.
        Optionally, this method could be extended to manage fixed-size kbar lists.

        Args:
            symbol (str): The trading symbol (e.g., "btc_usdt").
            kbar_data (Dict[str, Any]): The kbar data point (a dictionary).
        """
        async with self._lock:
            if symbol not in self._kbars:
                self._kbars[symbol] = []
            self._kbars[symbol].append(kbar_data)
            # Optional: Trim the list if it exceeds a certain size
            # max_kbars = 1000
            # if len(self._kbars[symbol]) > max_kbars:
            #     self._kbars[symbol] = self._kbars[symbol][-max_kbars:]

    async def set_kbars(self, symbol: str, kbars_list: List[Dict[str, Any]]):
        """
        Overwrites the kbar data for a specific symbol with a new list.

        Args:
            symbol (str): The trading symbol.
            kbars_list (List[Dict[str, Any]]): The new list of kbar data points.
        """
        async with self._lock:
            self._kbars[symbol] = kbars_list

    async def get_kbars(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Retrieves a copy of the kbar data list for a specific symbol.

        Returns:
            List[Dict[str, Any]]: A copy of the kbar data list, or an empty list if the
                                 symbol is not found.
        """
        async with self._lock:
            return list(self._kbars.get(symbol, []))  # Return a copy


if __name__ == "__main__":
    print("--- Testing load_config ---")
    config = load_config()
    print("Loaded Configuration:")
    for key, value in config.items():
        # Mask secrets for printing
        if key == API_SECRET_ENV and value:
            print(
                f"  {key}: {'*' * (len(value) - 4)}{value[-4:] if len(value) > 4 else '*' * len(value)}"
            )
        else:
            print(f"  {key}: {value}")
    print("-" * 30)

    async def test_state_cache():
        print("\n--- Testing StateCache ---")
        cache = StateCache()

        # Test Balances
        await cache.set_balances({"BTC": {"free": "1.0", "frozen": "0.1"}})
        await cache.update_balances({"ETH": {"free": "10.5", "frozen": "0.5"}})
        await cache.update_balances({"BTC": {"free": "1.2"}})  # Update existing
        balances = await cache.get_balances()
        print(f"Current Balances: {balances}")
        assert balances["BTC"]["free"] == "1.2"
        assert balances["ETH"]["frozen"] == "0.5"

        # Test Orders
        order1_data = {
            "symbol": "BTC_USDT",
            "price": "30000",
            "amount": "0.1",
            "status": "open",
        }
        order2_data = {
            "symbol": "ETH_USDT",
            "price": "2000",
            "amount": "1.0",
            "status": "open",
        }
        await cache.update_order("order1", order1_data)
        await cache.set_orders({"order2": order2_data})  # set_orders overwrites
        orders = await cache.get_orders()
        print(f"Current Orders: {orders}")
        assert "order1" not in orders
        assert orders["order2"]["symbol"] == "ETH_USDT"
        await cache.update_order("order3", {"symbol": "LTC_USDT", "status": "partial"})
        closed_order = await cache.close_order("order2")
        print(f"Closed order 'order2' data: {closed_order}")
        assert closed_order == order2_data
        orders_after_close = await cache.get_orders()
        print(f"Orders after closing 'order2': {orders_after_close}")
        assert "order2" not in orders_after_close
        assert "order3" in orders_after_close

        # Test Kbars
        await cache.update_kbar("BTC_USDT", {"time": 1, "open": 30000, "close": 30100})
        await cache.update_kbar("BTC_USDT", {"time": 2, "open": 30100, "close": 30050})
        await cache.set_kbars("ETH_USDT", [{"time": 1, "open": 2000, "close": 2010}])
        btc_kbars = await cache.get_kbars("BTC_USDT")
        eth_kbars = await cache.get_kbars("ETH_USDT")
        print(f"BTC Kbars: {btc_kbars}")
        print(f"ETH Kbars: {eth_kbars}")
        assert len(btc_kbars) == 2
        assert eth_kbars[0]["open"] == 2000
        print("StateCache tests passed (basic assertions).")
        print("-" * 30)

    asyncio.run(test_state_cache())
