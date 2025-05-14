import time
import httpx
import json
from typing import Optional, Dict, Any

# Use relative import for WSSignature assuming it's in the same directory/package
from .WSSignature import SignatureManager
from .logger import BaseLogger


# --- Custom Exception (Optional but recommended) ---
class SubscriptionError(Exception):
    """Custom exception for subscription key related errors."""

    pass


class SubscriptionManager(BaseLogger):
    """Manages WebSocket subscriptions and the required subscription key."""

    def __init__(
        self, api_key: str, api_secret: str, pair: str, config: Dict[str, Optional[str]]
    ):
        """
        Initializes the SubscriptionManager.

        Args:
            api_key (str): LBank API key.
            api_secret (str): LBank API secret.
            pair (str): The default trading pair for subscriptions (can be overridden).
            config (Dict[str, Optional[str]]): Dictionary containing configuration,
                                                including URLs for subscribe key management.
        """
        super().__init__()
        # self.log = self.log.bind(class_name="SubscriptionManager") # Redundant
        self.api_key = api_key
        self.api_secret = api_secret
        self.pair = pair  # Default pair
        self.subscribeKey: Optional[str] = None

        # Get URLs from config
        self.get_key_url = config.get("WS_GET_KEY_URL")
        self.refresh_key_url = config.get("WS_REFRESH_KEY_URL")
        self.destroy_key_url = config.get("WS_DESTROY_KEY_URL")

        if not all([self.get_key_url, self.refresh_key_url, self.destroy_key_url]):
            self.log.error(
                "Missing one or more WebSocket subscription key URLs in configuration."
            )
            raise ValueError(
                "Missing WebSocket subscription key URLs in configuration."
            )

        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret is missing. Private subscriptions will fail."
            )

        self.client = httpx.AsyncClient(
            timeout=10.0
        )  # Client for REST calls to manage keys

    async def _make_key_request(
        self, url: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Helper function to make POST requests for key management."""
        # Add common parameters and sign
        params["api_key"] = self.api_key
        params["timestamp"] = int(time.time() * 1000)
        # Signature requires the API secret
        if not self.api_secret:
            raise SubscriptionError(
                "API secret is required for subscription key management."
            )
        params["sign"] = SignatureManager.create_signature(params, self.api_secret)
        self.log.debug("Making subscription key request", url=url, params=params)

        try:
            response = await self.client.post(url, data=params)  # LBank uses form data
            response.raise_for_status()  # Check for HTTP errors
            data = response.json()
            self.log.debug(
                "Received response from key management API", url=url, response_data=data
            )

            # Check LBank specific result field
            if str(data.get("result")).lower() != "true":
                error_msg = data.get("error", "Unknown error from key management API")
                self.log.error(
                    "Subscription key API call failed",
                    url=url,
                    error=error_msg,
                    response=data,
                )
                raise SubscriptionError(f"API call failed: {error_msg} (URL: {url})")

            return data  # Return successful response data

        except httpx.HTTPStatusError as exc:
            self.log.error(
                f"HTTP Error response {exc.response.status_code} while requesting {exc.request.url!r}.",
                error=str(exc),
            )
            raise SubscriptionError(
                f"HTTP Error {exc.response.status_code} for {url}"
            ) from exc
        except httpx.RequestError as exc:
            self.log.error(
                f"Network error occurred while requesting {exc.request.url!r}.",
                error=str(exc),
            )
            raise SubscriptionError(f"Network error for {url}") from exc
        except json.JSONDecodeError as exc:
            self.log.error(
                f"Failed to decode JSON response from {url}.",
                error=str(exc),
                response_text=response.text,
            )
            raise SubscriptionError(f"Invalid JSON response from {url}") from exc
        except Exception as e:
            self.log.exception(
                "An unexpected error occurred during subscription key request", url=url
            )
            raise SubscriptionError(f"Unexpected error for {url}: {e}") from e

    async def get_subscribe_key(self) -> bool:
        """Retrieves a new subscribe key from the LBank API."""
        self.log.info("Attempting to get a new subscription key.")
        try:
            data = await self._make_key_request(
                self.get_key_url, {}
            )  # No extra params needed
            new_key = data.get("data", {}).get(
                "subscribeKey"
            )  # Adjust based on actual response structure
            if new_key:
                self.subscribeKey = new_key
                self.log.info(
                    "Successfully retrieved new subscribe key.",
                    subscribeKey=f"{self.subscribeKey[:4]}...",
                )  # Log partial key
                return True
            else:
                self.log.error(
                    "Subscribe key not found in successful API response.",
                    response_data=data,
                )
                self.subscribeKey = None
                return False
        except SubscriptionError as e:
            self.log.error(f"Failed to get subscribe key: {e}")
            self.subscribeKey = None
            return False

    async def extend_subscribe_key_validity(self) -> bool:
        """Extends the validity of the current subscribe key."""
        if not self.subscribeKey:
            self.log.warning(
                "No subscribe key available to extend, attempting to get a new one."
            )
            return await self.get_subscribe_key()

        self.log.info(
            "Attempting to refresh subscription key validity.",
            subscribeKey=f"{self.subscribeKey[:4]}...",
        )
        params = {"subscribeKey": self.subscribeKey}
        try:
            await self._make_key_request(self.refresh_key_url, params)
            self.log.info("Successfully extended subscribe key validity.")
            return True
        except SubscriptionError as e:
            self.log.error(
                f"Failed to extend subscribe key validity: {e}. Attempting to get a new key."
            )
            # If refresh fails, try to get a completely new key
            return await self.get_subscribe_key()

    async def delete_subscribe_key(self) -> bool:
        """Deletes the current subscribe key on the LBank server."""
        if not self.subscribeKey:
            self.log.info("No subscribe key to delete.")
            return True  # Nothing to do

        self.log.info(
            "Attempting to delete subscription key.",
            subscribeKey=f"{self.subscribeKey[:4]}...",
        )
        params = {"subscribeKey": self.subscribeKey}
        try:
            await self._make_key_request(self.destroy_key_url, params)
            self.log.info("Successfully deleted subscribe key.")
            self.subscribeKey = None  # Clear local key
            return True
        except SubscriptionError as e:
            # Log error but still clear local key as it's likely invalid now
            self.log.error(
                f"Failed to delete subscribe key via API: {e}. Clearing local key anyway."
            )
            self.subscribeKey = None
            return False  # Indicate failure

    async def send_message(self, connection, message: dict) -> None:
        """Sends a JSON message over the WebSocket connection."""
        self.log.debug("Attempting to send WebSocket message", message_data=message)
        try:
            if connection and not connection.closed:
                data_str = json.dumps(message)
                await connection.send(data_str)
                self.log.info(
                    "WebSocket message sent successfully.",
                    action=message.get("action"),
                    type=message.get("subscribe") or message.get("request"),
                )
            elif connection and connection.closed:
                self.log.warning("Cannot send message: WebSocket connection is closed.")
            else:
                self.log.warning("Cannot send message: WebSocket connection is None.")
        except Exception as e:
            # Catch potential errors during send (e.g., connection closed unexpectedly)
            self.log.exception(
                "Failed to send WebSocket message", error=str(e), message_data=message
            )

    # --- Subscription Methods ---

    async def _ensure_key_for_private_subscription(self) -> bool:
        """Ensures a valid subscribeKey exists, getting/refreshing if needed."""
        if self.subscribeKey:
            # Periodically refresh the key if needed (e.g., every 50 minutes)
            # Simple approach: refresh before subscribing if key exists
            # More robust: track key expiry time
            if not await self.extend_subscribe_key_validity():
                return False  # Failed to refresh or get a new key
        else:
            # Key doesn't exist, get a new one
            if not await self.get_subscribe_key():
                return False  # Failed to get a key
        return True  # Key is likely valid

    async def subscribe_kbar(
        self, connection, pair: Optional[str] = None, kbar: str = "1min"
    ) -> None:
        """Subscribes to K-bar data for a specific pair."""
        target_pair = pair or self.pair
        self.log.info(f"Subscribing to {kbar} kbar data for {target_pair}")
        message = {
            "action": "subscribe",
            "subscribe": "kbar",
            "kbar": kbar,
            "pair": target_pair,
        }
        await self.send_message(connection, message)

    async def request_kbar(
        self, connection, pair: Optional[str] = None, kbar: str = "day", size: int = 5
    ) -> None:
        """Requests historical K-bar data."""
        target_pair = pair or self.pair
        self.log.info(f"Requesting last {size} {kbar} kbar candles for {target_pair}")
        message = {
            "action": "request",
            "request": "kbar",
            "size": size,
            "kbar": kbar,
            "pair": target_pair,
        }
        await self.send_message(connection, message)

    async def subscribe_order_updates(self, connection, pair: str = "all") -> None:
        """Subscribes to order updates (requires authentication)."""
        self.log.info(f"Attempting to subscribe to order updates for pair(s): {pair}")
        if not await self._ensure_key_for_private_subscription():
            self.log.error(
                "Failed to subscribe to order updates: Could not ensure valid subscribe key."
            )
            return

        message = {
            "action": "subscribe",
            "subscribe": "orderUpdate",
            "subscribeKey": self.subscribeKey,
            "pair": pair,  # 'all' or specific pair like 'btc_usdt'
        }
        await self.send_message(connection, message)

    async def subscribe_asset_updates(self, connection) -> None:
        """Subscribes to asset/balance updates (requires authentication)."""
        self.log.info("Attempting to subscribe to asset updates.")
        if not await self._ensure_key_for_private_subscription():
            self.log.error(
                "Failed to subscribe to asset updates: Could not ensure valid subscribe key."
            )
            return

        message = {
            "action": "subscribe",
            "subscribe": "assetUpdate",
            "subscribeKey": self.subscribeKey,
            # Asset updates are usually not pair-specific
        }
        await self.send_message(connection, message)

    async def close_client(self):
        """Closes the underlying HTTPX client used for key management."""
        await self.client.aclose()
        self.log.info("SubscriptionManager's HTTPX client closed.")
