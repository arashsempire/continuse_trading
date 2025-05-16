import asyncio
import websockets
import json
import time
import httpx
import hmac
import hashlib
import pandas as pd  # Retained for historical kbar processing
from typing import Optional, Dict, Any, Callable, Awaitable, List
import random

# Assuming logger_config.py, api_exceptions.py, and app_utils.py (for config)
# are in the same directory or accessible in PYTHONPATH
from logger_config import BaseLogger
from api_exceptions import SubscriptionError
from app_utility import (  # For config keys
    API_KEY_ENV,
    API_SECRET_ENV,
    WS_GET_KEY_URL_ENV,
    WS_REFRESH_KEY_URL_ENV,
    WS_DESTROY_KEY_URL_ENV,
    WEBSOCKET_URI_ENV,
)


# ===============================
# Signature Manager (for WS key management if needed)
# ===============================
class WSSignatureManager(
    BaseLogger
):  # Renamed to avoid conflict if a general one exists
    """
    Handles creation of signatures, specifically for LBank WebSocket key management
    which uses HMAC-SHA256.
    """

    def __init__(self):
        super().__init__()
        self.log = self.log.bind(service_name="WSSignatureManager")

    def create_signature(self, params: dict, secret_key: str) -> str:
        """
        Creates an HMAC-SHA256 signature for the given parameters.

        Args:
            params (dict): A dictionary of parameters to include in the signature.
                           These should be sorted alphabetically by key.
            secret_key (str): The API secret key.

        Returns:
            str: The hexadecimal representation of the HMAC-SHA256 signature.
        """
        if not secret_key:
            self.log.error("API secret key is missing for signature creation.")
            # Depending on context, might raise an error or return an empty string
            raise ValueError("API secret key is required for creating a signature.")

        # Sort parameters by key and create the query string
        query_string_parts = []
        for key in sorted(params.keys()):
            value = params[key]
            # Ensure values are consistently stringified for the signature
            query_string_parts.append(f"{key}={str(value)}")
        query_string = "&".join(query_string_parts)

        self.log.debug(
            "Creating HMAC-SHA256 signature", query_string_for_signature=query_string
        )
        try:
            signature = hmac.new(
                secret_key.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()  # LBank WS signature is typically lowercase hex
        except Exception as e:
            self.log.exception(
                "Error during HMAC-SHA256 signature generation.", error=str(e)
            )
            raise SubscriptionError(
                f"Failed to generate HMAC-SHA256 signature: {e}"
            ) from e

        self.log.debug(
            "HMAC-SHA256 signature generated successfully", signature=signature
        )
        return signature


# ===============================
# WSConnection Manager
# ===============================
class WSConnectionManager(BaseLogger):
    """Manages the WebSocket connection lifecycle, including reconnections."""

    def __init__(self, uri: str):
        super().__init__()
        self.log = self.log.bind(service_name="WSConnectionManager")
        if not uri:
            self.log.error(
                "WebSocket URI is missing. Cannot initialize connection manager."
            )
            raise ValueError("WebSocket URI cannot be empty.")
        self.uri = uri
        self.connection: Optional[websockets.WebSocketClientProtocol] = None
        self._keep_running: bool = True  # Internal flag to control loops
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10  # Example: Stop after 10 rapid failed attempts
        self.initial_reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 300  # 5 minutes

        self.log.info("WSConnectionManager initialized", websocket_uri=self.uri)

    async def connect(self) -> bool:
        """
        Establishes a WebSocket connection. Retries with exponential backoff.

        Returns:
            bool: True if connection is successful, False otherwise (e.g., if keep_running is False).
        """
        self.log.info("Attempting to connect to WebSocket.", uri=self.uri)
        self._keep_running = True  # Ensure it's set to true when explicitly connecting
        while self._keep_running:
            try:
                self.connection = await websockets.connect(self.uri)
                self.log.info("Successfully connected to WebSocket.", uri=self.uri)
                self.reconnect_attempts = 0  # Reset on successful connection
                return True  # Connection successful
            except websockets.exceptions.InvalidURI:
                self.log.error("Invalid WebSocket URI.", uri=self.uri)
                self._keep_running = False  # Stop trying for invalid URI
                raise  # Re-raise for the caller to handle this critical error
            except (
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
                ConnectionRefusedError,
                OSError,
            ) as e:
                self.log.warning(
                    f"Failed to connect to WebSocket: {type(e).__name__} - {e}",
                    uri=self.uri,
                )
                if (
                    not self._keep_running
                ):  # If stop was called during connection attempt
                    self.log.info(
                        "Connection attempt aborted as keep_running is false."
                    )
                    break

                self.reconnect_attempts += 1
                if self.reconnect_attempts > self.max_reconnect_attempts:
                    self.log.error(
                        "Maximum reconnect attempts reached. Stopping connection attempts.",
                        attempts=self.reconnect_attempts,
                    )
                    self._keep_running = False  # Stop trying after max attempts
                    # Consider raising an error here or letting it return False
                    return False

                # Exponential backoff with jitter
                delay = min(
                    self.initial_reconnect_delay * (2 ** (self.reconnect_attempts - 1)),
                    self.max_reconnect_delay,
                )
                jitter = delay * 0.1 * random.random()  # Add some jitter
                actual_delay = delay + jitter
                self.log.info(
                    f"Connection attempt {self.reconnect_attempts}. Retrying in {actual_delay:.2f} seconds."
                )
                await asyncio.sleep(actual_delay)
            except Exception as e:  # Catch any other unexpected errors during connect
                self.log.exception(
                    "Unexpected error during WebSocket connection attempt.",
                    error=str(e),
                )
                # Similar retry logic for unexpected errors, or decide to stop
                await asyncio.sleep(
                    self.initial_reconnect_delay
                )  # Wait before retrying generic error
        self.log.info("Exited connection loop.", keep_running=self._keep_running)
        return False  # Connection failed or was stopped

    async def ensure_connection(self):
        """Checks if connected, and if not, attempts to connect."""
        if self.connection is None or self.connection.closed:
            self.log.info(
                "Connection is not active. Attempting to establish connection."
            )
            await self.connect()

    async def send_message(self, message: Dict[str, Any]):
        """Sends a JSON-encoded message to the WebSocket server."""
        if self.connection and not self.connection.closed:
            try:
                json_message = json.dumps(message)
                await self.connection.send(json_message)
                self.log.debug("Sent WebSocket message", ws_message=message)
            except websockets.exceptions.ConnectionClosed as e:
                self.log.warning(
                    "Failed to send message: WebSocket connection closed.", error=str(e)
                )
                # Don't try to reconnect here, listener or watchdog should handle it.
                raise  # Re-raise for the caller (e.g. SubscriptionManager) to handle
            except Exception as e:
                self.log.exception(
                    "Error sending WebSocket message.",
                    error=str(e),
                    message_content=message,
                )
                raise  # Re-raise
        else:
            self.log.warning(
                "Cannot send message: WebSocket connection is not active or None."
            )
            # Optionally, raise an error or try to reconnect before sending
            raise websockets.exceptions.ConnectionClosedError(
                None, "Connection not active for sending"
            )

    async def listen(self, message_handler_callable: Callable[[dict], Awaitable[None]]):
        """
        Listens for incoming messages and passes them to the message_handler_callable.
        Handles reconnection on connection loss.
        """
        self.log.info("Starting WebSocket listener loop.")
        while self._keep_running:
            try:
                await self.ensure_connection()  # Make sure we are connected before listening
                if not self.connection or self.connection.closed:
                    self.log.warning(
                        "Listener: No active connection to listen on. Will retry connection."
                    )
                    await asyncio.sleep(
                        self.initial_reconnect_delay
                    )  # Wait before retrying connection
                    continue

                async for raw_message in self.connection:
                    try:
                        data = json.loads(raw_message)
                        self.log.debug(
                            "Received WebSocket message",
                            raw_data_snippet=str(data)[:100],
                        )
                        await message_handler_callable(data)
                    except json.JSONDecodeError:
                        self.log.error(
                            "Failed to decode JSON from WebSocket message.",
                            raw_message=raw_message,
                        )
                    except (
                        Exception
                    ) as e_handler:  # Catch errors from the message_handler_callable
                        self.log.exception(
                            "Error in message_handler_callable.",
                            error=str(e_handler),
                            received_data=data,
                        )

            except websockets.exceptions.ConnectionClosedError as e:
                self.log.warning(
                    f"WebSocket connection closed by server or network issue: {e}. Attempting to reconnect."
                )
                # ensure_connection in the next loop iteration will handle reconnection.
                # Brief sleep to prevent tight loop if ensure_connection fails repeatedly.
                await asyncio.sleep(1)
            except websockets.exceptions.ConnectionClosedOK:
                self.log.info("WebSocket connection closed gracefully by server.")
                # If keep_running is true, it will attempt to reconnect.
            except asyncio.CancelledError:
                self.log.info("WebSocket listener task cancelled.")
                self._keep_running = False  # Ensure loop terminates
                break  # Exit loop immediately
            except (
                Exception
            ) as e:  # Catch-all for other unexpected errors in the listen loop
                self.log.exception(
                    f"Unexpected error in WebSocket listen loop: {e}. Attempting to recover."
                )
                # Brief sleep before trying to re-establish connection and listening.
                await asyncio.sleep(self.initial_reconnect_delay)

        self.log.info("WebSocket listener loop terminated.")

    async def stop(self):
        """Stops the connection manager and closes the WebSocket connection."""
        self.log.info("Stopping WSConnectionManager.")
        self._keep_running = False  # Signal loops to terminate
        if self.connection and not self.connection.closed:
            try:
                await self.connection.close()
                self.log.info("WebSocket connection closed successfully via stop().")
            except Exception as e:
                self.log.exception(
                    "Error during WebSocket connection close on stop().", error=str(e)
                )
        else:
            self.log.info(
                "WebSocket connection was already closed or not established when stop() was called."
            )
        self.connection = None


# ===============================
# WSMessage Processor
# ===============================
class WSMessageProcessor(BaseLogger):
    """
    Generic WebSocket message dispatcher.
    Handlers are registered for specific 'type' fields within the message data.
    """

    def __init__(self):
        super().__init__()
        self.log = self.log.bind(service_name="WSMessageProcessor")
        self.handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self.log.info("WSMessageProcessor initialized.")

    def register_handler(
        self, message_type: str, handler: Callable[[dict], Awaitable[None]]
    ):
        """
        Registers an asynchronous handler function for a given message type.
        The message_type is expected to be a key within the 'data' part of the LBank WS message.
        """
        if not callable(handler):
            self.log.error(
                "Invalid handler provided: not callable.",
                handler_name=getattr(handler, "__name__", str(handler)),
            )
            raise ValueError("Handler must be a callable async function.")
        self.handlers[message_type] = handler
        self.log.debug(f"Handler registered for data message type: '{message_type}'")

    async def process_data_message(self, data_payload: dict):
        """
        Processes a 'data' payload from a WebSocket message by dispatching
        to the appropriate handler based on the 'type' field within this payload.
        """
        message_type = data_payload.get(
            "type"
        )  # LBank specific: "type" field in the "data" object
        if not message_type:
            self.log.warning(
                "Data message missing 'type' field.",
                data_payload_snippet=str(data_payload)[:100],
            )
            return

        handler = self.handlers.get(message_type)
        if handler:
            self.log.debug(
                f"Dispatching data message type '{message_type}' to its handler."
            )
            try:
                await handler(data_payload)  # Pass the whole data_payload
            except Exception as e:
                self.log.exception(
                    f"Error while processing data message type '{message_type}'.",
                    error=str(e),
                    data_payload_snippet=str(data_payload)[:100],
                )
        else:
            self.log.warning(
                f"No handler registered for data message type: '{message_type}'.",
                data_payload_snippet=str(data_payload)[:100],
            )


class LBankMessageProcessor(WSMessageProcessor):
    """
    Processes incoming WebSocket messages specifically for LBank by mapping LBank's
    message structure to user-defined callbacks.
    """

    def __init__(
        self,
        on_kbar_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_order_update_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_asset_update_callback: Optional[
            Callable[[List[dict]], Awaitable[None]]
        ] = None,  # LBank asset is a list
        on_historical_kbar_callback: Optional[
            Callable[[pd.DataFrame, str], Awaitable[None]]
        ] = None,  # DF and pair
    ):
        super().__init__()
        self.log = self.log.bind(service_name="LBankMessageProcessor")

        # Store callbacks
        self.on_kbar_callback = on_kbar_callback
        self.on_order_update_callback = on_order_update_callback
        self.on_asset_update_callback = on_asset_update_callback
        self.on_historical_kbar_callback = on_historical_kbar_callback

        # Register internal handlers for LBank specific 'type' fields in data messages
        if self.on_kbar_callback:
            self.register_handler(
                "kbar", self._handle_kbar_data
            )  # 'kbar' is a type in data
        if self.on_order_update_callback:
            # LBank WS sends order updates with type "ORDER_UPDATE" or similar in the main message,
            # and the actual data is in a "data" field.
            # The original code registered "orderUpdate". Let's assume "orderUpdate" is a type within the data field.
            self.register_handler("orderUpdate", self._handle_order_update_data)
        if self.on_asset_update_callback:
            # LBank WS asset updates: type: "asset", data: [{"assetCode":...}, ...]
            self.register_handler(
                "asset", self._handle_asset_data
            )  # 'asset' is a type in data

        self.log.info("LBankMessageProcessor initialized with callbacks.")

    async def _handle_kbar_data(self, kbar_message_payload: dict):
        """Internal handler for 'kbar' type messages from the data payload."""
        # kbar_message_payload is the content of "data" when "data.type" is "kbar"
        # Example: {"type":"kbar", "kbar":{"high": "123", ...}, "pair":"btc_usdt", "TS":"..."}
        kbar_data = kbar_message_payload.get("kbar")
        pair = kbar_message_payload.get("pair")
        timestamp_str = kbar_message_payload.get(
            "TS"
        )  # LBank uses "TS" for timestamp string

        if isinstance(kbar_data, dict) and pair:
            self.log.debug(
                f"Parsed KBar data for {pair}.",
                kbar_content=kbar_data,
                ts=timestamp_str,
            )
            if self.on_kbar_callback:
                # Construct a message similar to original for the callback
                await self.on_kbar_callback(
                    {"pair": pair, "kbar": kbar_data, "TS": timestamp_str}
                )
        else:
            self.log.warning(
                "Invalid 'kbar' data format received.",
                kbar_payload_snippet=str(kbar_message_payload)[:100],
            )

    async def _handle_order_update_data(self, order_update_payload: dict):
        """Internal handler for 'orderUpdate' type messages from the data payload."""
        # order_update_payload is the content of "data" when "data.type" is "orderUpdate"
        # Example: {"type":"orderUpdate", "uuid":"...", "status": "2", "pair":"btc_usdt", ...}
        # The original code expected `order_data = message.get("order")`.
        # LBank's typical structure for order updates is that the payload itself IS the order data.
        if (
            isinstance(order_update_payload, dict) and "uuid" in order_update_payload
        ):  # uuid is usually the order ID
            self.log.debug(
                "Parsed order update.", order_data_content=order_update_payload
            )
            if self.on_order_update_callback:
                await self.on_order_update_callback(
                    order_update_payload
                )  # Pass the whole payload
        else:
            self.log.warning(
                "Invalid 'orderUpdate' data format or missing 'uuid'.",
                order_payload_snippet=str(order_update_payload)[:100],
            )

    async def _handle_asset_data(self, asset_payload: dict):
        """Internal handler for 'asset' type messages from the data payload."""
        # asset_payload is the content of "data" when "data.type" is "asset"
        # Example: {"type":"asset", "data":[{"assetCode":"usdt","freeze":"0","available":"123"}, ...]}
        # The actual list of assets is nested under a "data" key *within* this asset_payload.
        asset_list = asset_payload.get("data")
        if isinstance(asset_list, list):
            self.log.debug(
                f"Parsed asset update, {len(asset_list)} items.",
                first_asset_snippet=(
                    str(asset_list[0])[:100] if asset_list else "Empty list"
                ),
            )
            if self.on_asset_update_callback:
                await self.on_asset_update_callback(asset_list)
        else:
            self.log.warning(
                "Invalid 'asset' data format: 'data' field is not a list.",
                asset_payload_snippet=str(asset_payload)[:100],
            )

    async def process_incoming_message(self, full_message: dict):
        """
        Processes any incoming WebSocket message. This is the main entry point
        from the WebSocket listener. It handles basic message structure and dispatches
        to type-specific handlers or the data message processor.
        """
        # LBank WS message structure:
        # General form: {"action": "ping/pong/subscribe/request", "data": ..., "pair": ..., "type": ..., "result": ...,
        # "error_code": ...}
        # Data messages often have: {"type": "push.personal.order", "data": {"type": "orderUpdate", ...}}
        # Or public data: {"type": "kbar", "pair": "btc_usdt", "data": {"type": "kbar", "kbar": {...}, "pair":
        # "btc_usdt", "TS": "..."}}
        # Historical kbar response: {"action":"request", "request":"kbar", "pair":"eth_usdt", "klineType":"1min",
        #                           "data":[...], "columns":["T","o","h","l","c","v","a"], "result":"true",
        # "error_code":0}

        if not isinstance(full_message, dict):
            self.log.error(
                "Received non-dictionary message from WebSocket.",
                received_message=full_message,
            )
            return

        action = full_message.get("action")
        message_type_top_level = full_message.get("type")  # Top-level type
        data_content = full_message.get("data")

        self.log.debug(
            "Processing incoming WS message",
            action=action,
            top_level_type=message_type_top_level,
            has_data=bool(data_content),
        )

        if action == "ping":
            self.log.debug(
                "Received ping, should be handled by WS client to send pong."
            )
            # Pong sending is usually handled by the WebSocketClient orchestrator or WSConnectionManager
            return
        if action == "pong":
            self.log.debug("Received pong.")
            return

        # Handle historical kbar data response (which is a list in 'data' field)
        if (
            action == "request"
            and full_message.get("request") == "kbar"
            and isinstance(data_content, list)
        ):
            if self.on_historical_kbar_callback:
                columns = full_message.get("columns")
                pair = full_message.get("pair")
                if isinstance(columns, list) and pair:
                    try:
                        df = pd.DataFrame(data_content, columns=columns)
                        if not df.empty:
                            self.log.info(
                                f"Processed historical kbar data for pair: {pair}.",
                                df_shape=df.shape,
                            )
                            await self.on_historical_kbar_callback(df, pair)
                        else:
                            self.log.warning(
                                "Historical kbar request response was empty list.",
                                full_message_snippet=str(full_message)[:100],
                            )
                    except (ValueError, TypeError, IndexError) as e:
                        self.log.error(
                            "Error processing historical kbar request response DataFrame.",
                            error=str(e),
                            full_message_snippet=str(full_message)[:100],
                        )
                else:
                    self.log.warning(
                        "Historical kbar response missing 'columns' or 'pair'.",
                        full_message_snippet=str(full_message)[:100],
                    )
            else:
                self.log.warning(
                    "Received historical kbar data but no callback is registered."
                )
            return

        # Handle general data messages that have a nested "data" field with its own "type"
        # LBank often has: {"type": "push.personal.order", "data": {"type": "orderUpdate", ...}}
        # Or public: {"type": "kbar", "data": {"type": "kbar", "kbar": {...}, "pair": "btc_usdt", "TS": "..."}}
        if isinstance(data_content, dict) and "type" in data_content:
            # This is a data message where the actual type is inside the 'data' field
            await self.process_data_message(data_content)
            return

        # Handle messages where the top-level 'type' indicates the data type directly
        # and 'data' might be the payload itself or a list (like for asset updates if not nested)
        # Example: if LBank sent {"type": "assetUpdate", "data": [{"assetCode":...}]}
        # This part might need adjustment based on exact LBank structures for all message types.
        # The original code had a path for this, but LBank is often more nested.
        # For now, we assume most typed data is inside the 'data' field as handled above.
        # If a top-level 'type' directly corresponds to a handler (e.g. asset list not in data.data)
        # then this logic would apply:
        # handler = self.handlers.get(message_type_top_level)
        # if handler and data_content is not None: # data_content could be dict or list
        #     await handler(data_content) # Pass the data_content directly
        #     return

        # Log unhandled structures or confirmations
        if (
            full_message.get("result") == "true" or full_message.get("result") is True
        ):  # Check boolean true also
            self.log.info(
                "Received successful confirmation/response from WS.",
                ws_response=full_message,
            )
        elif (
            full_message.get("result") == "false" or full_message.get("result") is False
        ):
            self.log.error(
                "Received error confirmation/response from WS.",
                ws_response=full_message,
                error_code=full_message.get("error_code"),
                message=full_message.get(
                    "message"
                ),  # LBank often uses 'message' for error details
            )
        else:
            self.log.warning(
                "Unhandled WebSocket message structure.", unhandled_message=full_message
            )


# ===============================
# WSSubscription Manager
# ===============================
class SubscriptionManager(BaseLogger):
    """Manages WebSocket subscriptions and the required subscription key from LBank API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        config: Dict[str, Optional[str]],  # Pass the whole app config
        ws_connection_manager: WSConnectionManager,  # Pass the connection manager instance
    ):
        super().__init__()
        self.log = self.log.bind(service_name="SubscriptionManager")
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config  # Store the app config
        self.ws_conn_manager = ws_connection_manager  # Use the passed instance

        self.subscribe_key_rest: Optional[str] = (
            None  # LBank calls it 'subscribeKey' in REST API
        )
        self.ws_signature_manager = WSSignatureManager()

        # Get URLs from config using constants from app_utils
        self.get_key_url = self.config.get(WS_GET_KEY_URL_ENV)
        self.refresh_key_url = self.config.get(WS_REFRESH_KEY_URL_ENV)
        self.destroy_key_url = self.config.get(WS_DESTROY_KEY_URL_ENV)

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
            # No error raised here, allows for public-only subscriptions if desired by design

        # HTTP client for REST calls to manage subscription keys
        # Base URL for key management might be different from general trading REST API.
        # For now, assume it's part of the full URL provided in config.
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.log.info("SubscriptionManager initialized.")

    async def _make_key_request(
        self, url: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Helper function to make POST requests for key management using httpx."""
        if (
            not self.api_key or not self.api_secret
        ):  # Guard for operations requiring auth
            self.log.error(
                "API key or secret is missing for subscription key management."
            )
            raise SubscriptionError("API key or secret is required for this operation.")

        # Add common parameters required by LBank for these key management endpoints
        # LBank's key management endpoints use HMAC-SHA256 signature
        request_params = params.copy()
        request_params["api_key"] = self.api_key
        request_params["timestamp"] = str(
            int(time.time() * 1000)
        )  # Milliseconds timestamp as string

        # Signature for key management uses HMAC-SHA256
        try:
            request_params["sign"] = self.ws_signature_manager.create_signature(
                request_params, self.api_secret
            )
        except (
            ValueError
        ) as e_sign_val:  # e.g. missing secret handled by WSSignatureManager
            self.log.error(
                f"ValueError during signature creation for key request: {e_sign_val}"
            )
            raise SubscriptionError(
                f"Signature creation failed: {e_sign_val}"
            ) from e_sign_val

        self.log.debug(
            "Making subscription key REST request", url=url, params_sent=request_params
        )

        try:
            # LBank key management endpoints are POST and expect form data
            response = await self.http_client.post(url, data=request_params)
            response.raise_for_status()  # Check for HTTP errors (4xx, 5xx)
            response_data = response.json()
            self.log.debug(
                "Received response from key management API",
                url=url,
                response_data_snippet=str(response_data)[:100],
            )

            # Check LBank specific result field (e.g., "result":"true" or "code":200)
            # LBank's subscribe key endpoints: {"result":"true", "data":{"subscribeKey":...}, "error_code":0, "ts":...}
            if str(response_data.get("result")).lower() != "true":
                error_code = response_data.get("error_code", "N/A")
                error_msg = response_data.get(
                    "msg",
                    f"Unknown error from key management API (result not true), code: {error_code}",
                )
                self.log.error(
                    "Subscription key API call indicated failure.",
                    url=url,
                    error_message=error_msg,
                    api_error_code=error_code,
                    response_data=response_data,
                )
                raise SubscriptionError(
                    f"API call failed: {error_msg} (URL: {url}, Code: {error_code})"
                )
            return response_data

        except httpx.HTTPStatusError as exc:
            self.log.error(
                f"HTTP Error response {exc.response.status_code} while requesting {exc.request.url!r}.",
                error=str(exc),
                response_text_snippet=exc.response.text[:100],
            )
            raise SubscriptionError(
                f"HTTP Error {exc.response.status_code} for {url}"
            ) from exc
        except httpx.RequestError as exc:  # Network errors
            self.log.error(
                f"Network error occurred while requesting {exc.request.url!r}.",
                error=str(exc),
            )
            raise SubscriptionError(f"Network error for {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            self.log.error(
                f"Failed to decode JSON response from {url}.",
                error=str(exc),
                response_text_snippet=response.text[:100],
            )
            raise SubscriptionError(f"Invalid JSON response from {url}") from exc
        except SubscriptionError:  # Re-raise if already a SubscriptionError
            raise
        except Exception as e:  # Catch any other unexpected error
            self.log.exception(
                "An unexpected error occurred during subscription key REST request.",
                url=url,
                error=str(e),
            )
            raise SubscriptionError(f"Unexpected error for {url}: {e}") from e

    async def get_ws_subscribe_key(self) -> bool:
        """Retrieves a new WebSocket subscribeKey from the LBank API."""
        self.log.info("Attempting to get a new WebSocket subscription key.")
        if not self.get_key_url:
            self.log.error("get_key_url is not configured.")
            return False
        try:
            # No extra params needed for get_key beyond api_key, timestamp, sign
            response_data = await self._make_key_request(self.get_key_url, {})
            new_key = response_data.get("data", {}).get("subscribeKey")
            if new_key:
                self.subscribe_key_rest = new_key
                self.log.info(
                    "Successfully retrieved new WebSocket subscribeKey.",
                    ws_key_snippet=new_key[:5] + "...",
                )
                return True
            else:
                self.log.error(
                    "Failed to retrieve subscribeKey: 'subscribeKey' not found in response data.",
                    response_data=response_data,
                )
                return False
        except SubscriptionError as e:
            self.log.error(f"Error getting WebSocket subscribeKey: {e}")
            return False
        except (
            Exception
        ) as e_unhandled:  # Catch any other unhandled error from _make_key_request
            self.log.exception(
                f"Unhandled exception while getting subscribe key: {e_unhandled}"
            )
            return False

    async def refresh_ws_subscribe_key(self) -> bool:
        """Refreshes the existing WebSocket subscribeKey."""
        if not self.subscribe_key_rest:
            self.log.warning(
                "No WebSocket subscribeKey available to refresh. Attempting to get a new one first."
            )
            return (
                await self.get_ws_subscribe_key()
            )  # Try to get a new key if none exists

        self.log.info(
            "Attempting to refresh the WebSocket subscribeKey.",
            current_key_snippet=self.subscribe_key_rest[:5] + "...",
        )
        if not self.refresh_key_url:
            self.log.error("refresh_key_url is not configured.")
            return False
        try:
            params = {"subscribeKey": self.subscribe_key_rest}
            response_data = await self._make_key_request(self.refresh_key_url, params)
            # LBank refresh key response also returns the key in data.subscribeKey
            refreshed_key = response_data.get("data", {}).get("subscribeKey")
            if refreshed_key == self.subscribe_key_rest:
                self.log.info("WebSocket subscribeKey refreshed successfully.")
                return True
            else:
                # This case should ideally not happen if refresh is successful.
                # If key changes, update it.
                self.log.warning(
                    "SubscribeKey changed after refresh or refresh response format unexpected.",
                    old_key_snippet=self.subscribe_key_rest[:5] + "...",
                    new_key_from_refresh=refreshed_key,
                )
                if refreshed_key:  # If a new key was returned, use it.
                    self.subscribe_key_rest = refreshed_key
                    return True
                return False  # Indicate potential issue
        except SubscriptionError as e:
            self.log.error(f"Error refreshing WebSocket subscribeKey: {e}")
            # If refresh fails, the key might be invalid. Clear it to force getting a new one next time.
            self.subscribe_key_rest = None
            return False
        except Exception as e_unhandled:
            self.log.exception(
                f"Unhandled exception while refreshing subscribe key: {e_unhandled}"
            )
            self.subscribe_key_rest = None  # Assume key is now invalid
            return False

    async def delete_ws_subscribe_key(self) -> bool:
        """Deletes the current WebSocket subscribeKey from the LBank server."""
        if not self.subscribe_key_rest:
            self.log.warning("No WebSocket subscribeKey to delete.")
            return False  # Or True if considered success as no key exists

        self.log.info(
            "Attempting to delete the WebSocket subscribeKey.",
            key_to_delete_snippet=self.subscribe_key_rest[:5] + "...",
        )
        if not self.destroy_key_url:
            self.log.error("destroy_key_url is not configured.")
            return False
        try:
            params = {"subscribeKey": self.subscribe_key_rest}
            # Response for destroy might just be {"result":"true", "error_code":0}
            await self._make_key_request(self.destroy_key_url, params)
            self.log.info("WebSocket subscribeKey deleted successfully from server.")
            self.subscribe_key_rest = None  # Clear the local key
            return True
        except SubscriptionError as e:
            self.log.error(f"Error deleting WebSocket subscribeKey: {e}")
            # Key might still be valid or invalid on server, but we failed to confirm deletion.
            # Depending on error, might keep local key or clear it. For safety, clear it.
            self.subscribe_key_rest = None
            return False
        except Exception as e_unhandled:
            self.log.exception(
                f"Unhandled exception while deleting subscribe key: {e_unhandled}"
            )
            self.subscribe_key_rest = None
            return False

    async def _ensure_key_for_private_subscription(self) -> bool:
        """Ensures a valid subscribeKey is available, getting/refreshing if needed."""
        if not self.api_key or not self.api_secret:
            self.log.warning(
                "Cannot ensure subscribe key: API credentials not provided."
            )
            return False  # Private subscriptions not possible

        if not self.subscribe_key_rest:
            self.log.info("No subscribeKey found. Attempting to obtain a new one.")
            if not await self.get_ws_subscribe_key():
                self.log.error(
                    "Failed to obtain subscribeKey for private subscription."
                )
                return False
        # Optional: Could add a check here to see if the key is "stale" and refresh it,
        # but typically refresh is handled periodically or on specific errors.
        return True

    async def _send_subscription_message(self, message: Dict[str, Any]):
        """Helper to send a subscription message via WSConnectionManager."""
        try:
            await self.ws_conn_manager.send_message(message)
            self.log.info("Subscription message sent successfully.", ws_message=message)
        except websockets.exceptions.ConnectionClosed:
            self.log.warning(
                "Failed to send subscription message: Connection closed. Will retry on next cycle if applicable."
            )
            # Don't re-raise here if the main client loop handles reconnections and resubscriptions.
            # Or re-raise if immediate feedback is needed by the caller.
            raise  # Re-raise to let the caller (e.g. WebSocketClient) handle it.
        except Exception as e:
            self.log.error(
                "Unexpected error sending subscription message.",
                error=str(e),
                ws_message=message,
            )
            raise  # Re-raise

    # --- Public Subscription Methods ---
    async def subscribe_to_stream(
        self, stream_name: str, pair: str, is_private: bool = False
    ):
        """
        Generic method to subscribe to a public or private stream.

        Args:
            stream_name (str): The name of the stream to subscribe to (e.g., "kbar", "depth").
                               For LBank, this is the value for "subscribe" key in the message.
                               e.g., "1min" for 1-minute klines, "orderUpdate", "assetUpdate".
            pair (str): The trading pair (e.g., "btc_usdt"). For some streams like 'assetUpdate',
                        pair might not be applicable or set to 'all'. LBank uses 'all' for orderUpdate.
            is_private (bool): True if the stream requires authentication (and thus a subscribeKey).
        """
        self.log.info(
            f"Attempting to subscribe to stream: '{stream_name}' for pair: '{pair}' (Private: {is_private})"
        )
        message = {
            "action": "subscribe",
            "subscribe": stream_name,  # This is the kline type (1min, 5min) or "orderUpdate", "assetUpdate"
            "pair": pair,
        }
        if is_private:
            if not await self._ensure_key_for_private_subscription():
                self.log.error(
                    f"Failed to subscribe to private stream '{stream_name}': Could not ensure valid subscribeKey."
                )
                # Raise an error to signal failure to the orchestrator
                raise SubscriptionError(
                    f"Failed to get subscribeKey for private stream {stream_name}"
                )
            message["subscribeKey"] = self.subscribe_key_rest

        await self._send_subscription_message(message)

    async def unsubscribe_from_stream(self, stream_name: str, pair: str):
        """
        Generic method to unsubscribe from a stream.
        Note: LBank private stream unsubscription might also require subscribeKey.
        """
        self.log.info(
            f"Attempting to unsubscribe from stream: '{stream_name}' for pair: '{pair}'"
        )
        message = {
            "action": "unsubscribe",
            "unsubscribe": stream_name,
            "pair": pair,
        }
        # LBank docs are unclear if subscribeKey is needed for unsubscribing private streams.
        # Assuming it might be, or doesn't hurt if included when available.
        if self.subscribe_key_rest:  # If we have a key, include it.
            message["subscribeKey"] = self.subscribe_key_rest

        await self._send_subscription_message(message)

    async def request_historical_kline(
        self, pair: str, kline_type: str, start_time_ms: int, end_time_ms: int
    ):
        """
        Requests historical kline data within a specified time range.

        Args:
            pair (str): The trading pair (e.g., "btc_usdt").
            kline_type (str): The kline type (e.g., "1min", "1hour", "1day").
            start_time_ms (int): The start timestamp in milliseconds.
            end_time_ms (int): The end timestamp in milliseconds.
        """
        self.log.info(
            f"Requesting historical {kline_type} klines for {pair} from {start_time_ms} to {end_time_ms}."
        )
        message = {
            "action": "request",
            "request": "kbar",  # LBank specific request type for historical kbars
            "pair": pair,
            "klineType": kline_type,  # LBank uses klineType for this request
            "startTime": start_time_ms,
            "endTime": end_time_ms,
        }
        # Historical data requests are typically public, no subscribeKey needed.
        await self._send_subscription_message(message)

    async def close_http_client(self):
        """Closes the underlying HTTPX client used for key management."""
        await self.http_client.aclose()
        self.log.info("SubscriptionManager's HTTPX client closed.")


# ===============================
# WebSocket Client Orchestrator
# ===============================
class WebSocketClient(BaseLogger):
    """
    Main WebSocket client orchestrator for LBank.
    Manages connection, subscriptions, and delegates message processing.
    """

    def __init__(
        self,
        config: Dict[str, Optional[str]],  # Full application config
        message_processor: LBankMessageProcessor,  # Expects the LBank specific processor
    ):
        super().__init__()
        self.log = self.log.bind(service_name="WebSocketClientOrchestrator")
        self.config = config
        self.message_processor = message_processor
        self._running = False
        self._tasks: List[asyncio.Task] = []

        ws_uri = self.config.get(WEBSOCKET_URI_ENV)
        api_key = self.config.get(API_KEY_ENV)
        api_secret = self.config.get(API_SECRET_ENV)

        if not ws_uri:
            self.log.error(
                "WebSocket URI is missing in configuration. Cannot start client."
            )
            raise ValueError(
                "WebSocket URI (WEBSOCKET_URI_ENV) not found in configuration."
            )

        # Initialize core components
        self.connection_manager = WSConnectionManager(ws_uri)
        self.subscription_manager = SubscriptionManager(
            api_key=api_key,
            api_secret=api_secret,
            config=self.config,
            ws_connection_manager=self.connection_manager,  # Pass the connection manager instance
        )

        # Define subscriptions (example, can be made more dynamic)
        # Pair for public subscriptions can be passed or configured.
        self.default_public_pair = self.config.get(
            "DEFAULT_WS_PAIR", "eth_usdt"
        )  # From app_utils constants
        self.subscriptions_to_make = [
            {
                "stream": "1min",
                "pair": self.default_public_pair,
                "private": False,
                "type": "kbar",
            },  # LBank kline type
            {
                "stream": "depth.20",
                "pair": self.default_public_pair,
                "private": False,
                "type": "depth",
            },  # LBank depth
            {
                "stream": "trade",
                "pair": self.default_public_pair,
                "private": False,
                "type": "trade",
            },  # LBank trades
            # Private subscriptions
            {
                "stream": "orderUpdate",
                "pair": "all",
                "private": True,
                "type": "orderUpdate",
            },  # LBank order updates for all pairs
            {
                "stream": "assetUpdate",
                "pair": "",
                "private": True,
                "type": "assetUpdate",
            },  # LBank asset updates (pair not usually applicable)
        ]
        self.ping_interval = (
            25  # seconds, LBank expects ping every 30s, send a bit earlier
        )
        self.key_refresh_interval = (
            10 * 60
        )  # Refresh key every 10 minutes (LBank key validity is 24h)

        self.log.info("WebSocketClient orchestrator initialized.")

    async def _ping_loop(self):
        """Periodically sends ping messages to keep the connection alive."""
        self.log.info("Starting WebSocket ping loop.")
        while self._running:
            try:
                await asyncio.sleep(self.ping_interval)
                if not self._running:
                    break  # Exit if stopped

                if (
                    self.connection_manager.connection
                    and not self.connection_manager.connection.closed
                ):
                    ping_message = {
                        "action": "ping",
                        "ping": str(int(time.time() * 1000)),
                    }
                    await self.connection_manager.send_message(ping_message)
                    self.log.debug(
                        "Sent ping to WebSocket server.", ping_id=ping_message["ping"]
                    )
                else:
                    self.log.warning("Ping loop: Connection not active, skipping ping.")
            except asyncio.CancelledError:
                self.log.info("Ping loop cancelled.")
                break
            except Exception as e:
                self.log.error(f"Error in WebSocket ping loop: {e}", exc_info=True)
                # Avoid tight loop on continuous errors
                await asyncio.sleep(
                    self.ping_interval / 2
                )  # Shorter sleep before next attempt if error

    async def _subscribe_to_configured_streams(self):
        """Subscribes to all streams defined in self.subscriptions_to_make."""
        self.log.info("Attempting to subscribe to configured streams.")
        if (
            not self.connection_manager.connection
            or self.connection_manager.connection.closed
        ):
            self.log.warning("Cannot subscribe: No active WebSocket connection.")
            return False  # Indicate failure to subscribe

        success_all = True
        for sub_info in self.subscriptions_to_make:
            if not self._running:
                break  # Stop if client is stopping
            try:
                self.log.info(
                    f"Subscribing to: {sub_info['stream']} for pair {sub_info['pair']}"
                )
                await self.subscription_manager.subscribe_to_stream(
                    stream_name=sub_info["stream"],
                    pair=sub_info["pair"],
                    is_private=sub_info["private"],
                )
                await asyncio.sleep(0.2)  # Small delay between subscriptions
            except (
                SubscriptionError
            ) as e:  # Catch specific error from subscribe_to_stream
                self.log.error(
                    f"SubscriptionError for stream {sub_info['stream']} ({sub_info['pair']}): {e}"
                )
                success_all = False  # Mark that at least one subscription failed
                # Depending on severity, might want to break or continue with others
            except Exception as e:
                self.log.exception(
                    f"Failed to subscribe to stream {sub_info['stream']} ({sub_info['pair']}).",
                    error=str(e),
                )
                success_all = False
        if success_all:
            self.log.info("Successfully initiated all configured subscriptions.")
        else:
            self.log.warning("One or more subscriptions failed to initiate.")
        return success_all

    async def _maintain_subscribe_key_loop(self):
        """Periodically refreshes the WebSocket subscription key if using private streams."""
        # Check if any private subscriptions are configured
        has_private_subs = any(
            sub.get("private", False) for sub in self.subscriptions_to_make
        )
        if not has_private_subs:
            self.log.info(
                "No private subscriptions configured. Subscribe key maintenance loop will not run."
            )
            return

        self.log.info("Starting subscribe key maintenance loop.")
        while self._running:
            try:
                await asyncio.sleep(self.key_refresh_interval)
                if not self._running:
                    break

                self.log.info("Attempting periodic refresh of WebSocket subscribeKey.")
                if await self.subscription_manager.refresh_ws_subscribe_key():
                    self.log.info(
                        "WebSocket subscribeKey refreshed successfully by maintenance loop."
                    )
                    # If key was refreshed, and connection is active, re-subscribe to ensure continuity
                    # This is important if the key actually changed or if subscriptions are tied to key sessions.
                    if (
                        self.connection_manager.connection
                        and not self.connection_manager.connection.closed
                    ):
                        self.log.info("Re-subscribing to streams after key refresh.")
                        await self._subscribe_to_configured_streams()
                else:
                    self.log.warning(
                        "Failed to refresh WebSocket subscribeKey in maintenance loop. Will retry later."
                    )
                    # If key refresh fails, the old key might become invalid.
                    # The next private subscription attempt will try to get a new key via _ensure_key.
            except asyncio.CancelledError:
                self.log.info("Subscribe key maintenance loop cancelled.")
                break
            except Exception as e:
                self.log.error(
                    f"Error in subscribe key maintenance loop: {e}", exc_info=True
                )
                await asyncio.sleep(
                    60
                )  # Wait a bit longer if the loop itself has an error

    async def start(self):
        """Connects to the WebSocket, starts listening, and manages subscriptions."""
        if self._running:
            self.log.warning(
                "WebSocketClient is already running. Start command ignored."
            )
            return
        self.log.info("Starting WebSocketClient orchestrator...")
        self._running = True

        # Attempt initial connection
        if not await self.connection_manager.connect():
            self.log.error(
                "Initial WebSocket connection failed. Client will not start core tasks."
            )
            self._running = False  # Ensure it's marked as not running
            # Clean up any resources if partially started
            await self.subscription_manager.close_http_client()
            return

        # Subscribe to initial streams
        # This might fail if private subscriptions are involved and key retrieval fails.
        try:
            await self._subscribe_to_configured_streams()
        except SubscriptionError as e_sub_init:
            self.log.error(
                f"Initial subscription failed critically: {e_sub_init}. Stopping client."
            )
            await self.stop()  # Graceful stop
            return
        except Exception as e_sub_unhandled:
            self.log.exception(
                f"Unhandled error during initial subscriptions: {e_sub_unhandled}. Stopping client."
            )
            await self.stop()
            return

        # Start background tasks
        self._tasks.append(
            asyncio.create_task(
                self.connection_manager.listen(
                    self.message_processor.process_incoming_message
                ),
                name="WSListenerLoop",
            )
        )
        self._tasks.append(asyncio.create_task(self._ping_loop(), name="WSPingLoop"))
        self._tasks.append(
            asyncio.create_task(
                self._maintain_subscribe_key_loop(), name="WSKeyMaintenanceLoop"
            )
        )

        self.log.info("WebSocketClient core tasks started.")
        # Keep running until stop() is called or a critical error occurs in a task
        try:
            await asyncio.gather(*self._tasks)
        except Exception as e_gather:
            # This part is tricky. If a task fails critically and isn't caught inside the task,
            # asyncio.gather will raise it.
            self.log.critical(
                f"A critical error occurred in one of the WebSocketClient tasks: {e_gather}",
                exc_info=True,
            )
            # Initiate a stop if not already stopping
            if self._running:
                await self.stop()

    async def stop(self):
        """Stops all running tasks and cleans up resources."""
        if not self._running and not self._tasks:
            self.log.info(
                "WebSocketClient is not running or already stopped. Stop command ignored."
            )
            return

        self.log.info("Stopping WebSocketClient orchestrator...")
        self._running = False  # Signal all loops to terminate

        # Cancel all background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            # Wait for tasks to finish cancellation, with a timeout
            # return_exceptions=True ensures gather doesn't stop on the first CancelledError
            results = await asyncio.gather(*self._tasks, return_exceptions=True)
            for i, res in enumerate(results):
                task_name = (
                    self._tasks[i].get_name()
                    if hasattr(self._tasks[i], "get_name")
                    else f"Task-{i}"
                )
                if isinstance(res, asyncio.CancelledError):
                    self.log.info(f"Task '{task_name}' successfully cancelled.")
                elif isinstance(res, Exception):
                    self.log.error(
                        f"Task '{task_name}' raised an exception during shutdown: {res}",
                        exc_info=res,
                    )
        self._tasks = []

        # Clean up resources
        if self.subscription_manager:
            # Delete the key from LBank server if it exists and API keys are present
            if (
                self.subscription_manager.subscribe_key_rest
                and self.config.get(API_KEY_ENV)
                and self.config.get(API_SECRET_ENV)
            ):
                await self.subscription_manager.delete_ws_subscribe_key()
            await self.subscription_manager.close_http_client()

        if self.connection_manager:
            await self.connection_manager.stop()  # Close WebSocket connection

        self.log.info("WebSocketClient orchestrator stopped gracefully.")

    def is_connected(self) -> bool:
        """Checks if the WebSocket connection is currently active."""
        return (
            self.connection_manager.connection is not None
            and not self.connection_manager.connection.closed
        )


# ===============================
# Main (Example Usage for websocket_handler.py)
# ===============================
async def example_main():
    from app_utility import load_config  # For loading API_KEY etc.
    from logger_config import configure_logging
    import logging

    # 1. Configure Logging
    configure_logging(logging.DEBUG)  # Use DEBUG for verbose output during testing
    main_log = BaseLogger().log.bind(service_name="WS_Example_Main")

    # 2. Load Configuration
    app_config = load_config()
    # Ensure critical WS config is present
    if not app_config.get(WEBSOCKET_URI_ENV):
        main_log.critical(f"{WEBSOCKET_URI_ENV} not found in configuration. Exiting.")
        return
    # API keys are needed for private streams and key management
    if not app_config.get(API_KEY_ENV) or not app_config.get(API_SECRET_ENV):
        main_log.warning(
            "API_KEY or API_SECRET not found. Private streams will not work."
        )

    # 3. Define callback functions for the LBankMessageProcessor
    async def on_kbar_data_received(kbar_message: dict):
        main_log.info("Callback: KBar Data Received", data=kbar_message)
        # Example: kbar_message will be like {"pair": "btc_usdt", "kbar": {"high": ..., "low": ...}, "TS": "..."}

    async def on_order_update_received(order_data: dict):
        main_log.info("Callback: Order Update Received", data=order_data)
        # Example: order_data will be like {"uuid": "order123", "status": "2", ...}

    async def on_asset_update_received(asset_list: List[dict]):  # LBank sends a list
        main_log.info(
            f"Callback: Asset Update Received ({len(asset_list)} assets)",
            first_asset_if_any=asset_list[0] if asset_list else "Empty",
        )
        # Example: asset_list will be like [{"assetCode": "usdt", "available": "100", "freeze": "10"}, ...]

    async def on_historical_kbar_df_received(historical_df: pd.DataFrame, pair: str):
        main_log.info(
            f"Callback: Historical KBar DataFrame for {pair} Received (Shape: {historical_df.shape})"
        )
        if not historical_df.empty:
            main_log.info(
                "Historical KBar DataFrame Head:\n" + historical_df.head().to_string()
            )

    # 4. Instantiate LBankMessageProcessor with callbacks
    lbank_processor = LBankMessageProcessor(
        on_kbar_callback=on_kbar_data_received,
        on_order_update_callback=on_order_update_received,
        on_asset_update_callback=on_asset_update_received,
        on_historical_kbar_callback=on_historical_kbar_df_received,
    )

    # 5. Instantiate WebSocketClient (the orchestrator)
    ws_client = WebSocketClient(config=app_config, message_processor=lbank_processor)

    # 6. Start the client and run it
    try:
        main_log.info("Starting WebSocket client example...")
        # Run ws_client.start() as a task to allow other operations or graceful shutdown
        client_task = asyncio.create_task(ws_client.start(), name="MainWSClientTask")

        # Keep main alive, or do other work.
        # Example: Request historical klines after a delay
        await asyncio.sleep(10)  # Wait for connection and initial subscriptions
        if ws_client.is_connected():
            main_log.info(
                "Client connected. Requesting historical klines for btc_usdt (1min)..."
            )
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - (60 * 60 * 1000)  # 1 hour ago
            try:
                await ws_client.subscription_manager.request_historical_kline(
                    pair="btc_usdt",  # Ensure this pair is reasonable
                    kline_type="1min",  # LBank kline type for 1 minute
                    start_time_ms=start_ms,
                    end_time_ms=now_ms,
                )
            except Exception as e_hist_req:
                main_log.error(f"Error requesting historical klines: {e_hist_req}")
        else:
            main_log.warning(
                "Client not connected after 10s, cannot request historical klines."
            )

        # Let it run for a while
        await asyncio.sleep(120)  # Run for 2 minutes then stop for this example
        # Or await client_task directly if you want it to run indefinitely until an error or external stop
        # await client_task

    except KeyboardInterrupt:
        main_log.info("KeyboardInterrupt received. Stopping client example...")
    except Exception as e:
        main_log.critical(
            f"An unexpected error occurred in example_main: {e}", exc_info=True
        )
    finally:
        main_log.info("Initiating shutdown of WebSocket client example...")
        if "ws_client" in locals() and (
            ws_client._running or ws_client._tasks
        ):  # Check if it was started
            await ws_client.stop()
        main_log.info("WebSocket client example shutdown complete.")


if __name__ == "__main__":
    # This example main requires your other modules (logger_config, app_utils, api_exceptions)
    # to be correctly structured for relative imports or be in PYTHONPATH.
    # Ensure you have a .env file with API_KEY, API_SECRET, and relevant URLs for full functionality.
    asyncio.run(example_main())
