import httpx
import hashlib
import string
import random
from typing import Dict, Any, Optional

# Assuming logger_config.py and api_exceptions.py are in the same directory or accessible in PYTHONPATH
from logger_config import BaseLogger
from api_exceptions import LBankAPIError


class LBankAuthUtils(BaseLogger):
    """
    Handles authentication, request signing, and base HTTP request utilities
    for interacting with the LBank REST API V2.

    Attributes:
        base_url (str): Base URL for the LBank API.
        api_key (str): API key for authentication.
        api_secret (str): API secret for signing requests.
        client (httpx.AsyncClient): Asynchronous HTTP client for making requests.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """
        Initializes the LBankAuthUtils with API credentials and base URL.

        Args:
            api_key (str): Your LBank API key.
            api_secret (str): Your LBank API secret.
            base_url (str): The base URL for the LBank V2 REST API.
        """
        super().__init__()  # Initializes self.log from BaseLogger
        self.log = self.log.bind(service_name="LBankAuthUtils")  # Add service context

        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret is missing. Authenticated requests will fail."
            )
        if not base_url:
            self.log.error("Base URL is missing. Cannot initialize client.")
            raise ValueError("Base URL cannot be empty for LBankAuthUtils.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/") + "/"  # Ensure trailing slash
        try:
            # Set a reasonable default timeout for HTTP requests
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        except Exception as e:
            self.log.exception(
                "Failed to initialize HTTPX client",
                base_url=self.base_url,
                error=str(e),
            )
            # Wrap in LBankAPIError or a more generic init error if preferred
            raise LBankAPIError(f"Failed to initialize HTTPX client: {e}") from e
        self.log.info("LBankAuthUtils initialized", base_url=self.base_url)

    def _sign(self, params: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        """
        Generates parameters for a signed request using MD5 (as per original LBank V2 docs).
        Note: LBank's V2 documentation specifies MD5 for `sign` but also `signature_method=HmacSHA256`.
        This implementation follows the MD5 for `sign` based on typical V2 patterns.
        If HmacSHA256 is truly needed for the `sign` parameter itself, this method needs adjustment.

        Args:
            params (Dict[str, Any]): Dictionary of specific endpoint parameters.
            timestamp (str): The timestamp string (usually obtained from API or current time).

        Returns:
            Dict[str, Any]: Parameters required for the signed POST request body,
                            including the signature and other auth fields.
        Raises:
            TypeError: If params is not a dictionary or timestamp is not a string.
            ValueError: If API key is missing.
            LBankAPIError: For errors during echostr generation or signature creation.
        """
        self.log.debug(
            "Attempting to sign parameters",
            params_keys=list(params.keys()) if params else "No params",
            has_timestamp=bool(timestamp),
        )
        if not isinstance(params, dict):
            self.log.error(
                "Invalid type for params in _sign", type=type(params).__name__
            )
            raise TypeError("params must be a dictionary")
        if not isinstance(timestamp, str):
            self.log.error(
                "Invalid type for timestamp in _sign", type=type(timestamp).__name__
            )
            raise TypeError("timestamp must be a string")
        if not self.api_key:
            self.log.error("API key is missing, cannot sign request.")
            raise ValueError("API key is required for signing.")

        # Prepare parameters for signing string
        sign_params_build = params.copy()
        sign_params_build["api_key"] = self.api_key
        sign_params_build["timestamp"] = timestamp
        try:
            # echostr is a random string, LBank docs suggest its presence
            sign_params_build["echostr"] = "".join(
                random.sample(string.ascii_letters + string.digits, 35)
            ).upper()
        except Exception as e:
            self.log.exception("Failed to generate echostr for signing.")
            raise LBankAPIError("Failed to generate echostr for signing") from e

        # signature_method is part of the signed payload, but the actual signature
        # generation method (MD5 vs HMAC-SHA256) for the 'sign' field itself is key.
        # Original code implies MD5 for 'sign', while 'signature_method' states 'HmacSHA256'.
        # This is a common ambiguity in some exchange APIs.
        # We'll stick to MD5 for 'sign' as per the hash used.
        sign_params_build["signature_method"] = "HmacSHA256"

        # Create the query string for signing: sort by key, join key=value pairs
        # Filter out None values before joining, as they shouldn't be in the signature string
        query_string_parts = []
        for key in sorted(sign_params_build.keys()):
            value = sign_params_build[key]
            if (
                value is not None
            ):  # Important: Do not include None values in query string
                query_string_parts.append(f"{key}={value}")
        query_string = "&".join(query_string_parts)

        self.log.debug("String to sign", query_string_to_sign=query_string)

        try:
            # As per original code, using MD5 for the 'sign' parameter.
            # If HMAC-SHA256 is required for 'sign', the following lines should change to:
            # import hmac
            # signature = hmac.new(
            #     self.api_secret.encode('utf-8'),
            #     query_string.encode('utf-8'),
            #     hashlib.sha256
            # ).hexdigest().upper()
            signature = hashlib.md5(query_string.encode("utf-8")).hexdigest().upper()
        except Exception as e:
            self.log.exception("Error during MD5 signature generation.")
            raise LBankAPIError("Failed to generate MD5 signature") from e

        self.log.debug("Generated MD5 signature", signature=signature)

        # Final parameters to be sent in the request body
        # These include the original parameters plus the authentication fields
        final_request_params = (
            params.copy()
        )  # Start with original endpoint-specific params
        final_request_params.update(
            {
                "api_key": self.api_key,
                "sign": signature,
                "timestamp": timestamp,
                "signature_method": sign_params_build["signature_method"],
                "echostr": sign_params_build["echostr"],
            }
        )
        self.log.debug(
            "Final signed parameters prepared",
            final_params_keys=list(final_request_params.keys()),
        )
        return final_request_params

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """
        Makes an asynchronous HTTP request to the LBank API.

        Args:
            method (str): HTTP method (e.g., "GET", "POST").
            endpoint (str): API endpoint path (e.g., "depth.do").
            params (Optional[Dict[str, Any]]): Request parameters. For GET, these are URL query params.
                                               For POST, these are form data. Defaults to None.
            signed (bool): Whether the request needs to be signed. Defaults to False.

        Returns:
            Dict[str, Any]: The JSON response from the API as a dictionary.

        Raises:
            LBankAPIError: For API-specific errors, HTTP errors, or network issues.
            ValueError: If an unsupported HTTP method is used.
        """
        self.log.debug(
            "Initiating request",
            method=method,
            endpoint=endpoint,
            signed=signed,
            has_params=bool(params),
        )
        if params is None:
            params = {}

        # Log a copy of parameters that might be modified or used in signing
        # Be cautious about logging sensitive info from params if any exists before signing
        loggable_params = {
            k: v for k, v in params.items() if k not in [self.api_secret]
        }  # Example filter
        original_params_for_error = (
            params.copy()
        )  # Preserve original params for error reporting

        actual_request_params = params.copy()  # Default to original params

        try:
            if signed:
                if not self.api_key or not self.api_secret:
                    self.log.error(
                        "Cannot make signed request: API key or secret missing."
                    )
                    raise LBankAPIError(
                        "API key or secret not configured for signed request.",
                        request_params=original_params_for_error,
                    )
                try:
                    # Fetch fresh timestamp for signing
                    ts_response = (
                        await self.get_timestamp()
                    )  # get_timestamp has its own logging
                    timestamp_str = str(ts_response.get("data"))
                    if not timestamp_str:  # Check if data field exists and is not empty
                        self.log.error(
                            "Failed to fetch valid timestamp for signing. 'data' field missing or empty.",
                            response=ts_response,
                        )
                        raise LBankAPIError(
                            "Failed to fetch valid timestamp for signing.",
                            request_params=original_params_for_error,
                            response_data=ts_response,
                        )
                    # `_sign` returns all parameters needed for the body, including original ones
                    actual_request_params = self._sign(params, timestamp_str)
                    self.log.debug(
                        "Parameters signed successfully for request.", endpoint=endpoint
                    )

                except (
                    TypeError,
                    ValueError,
                    LBankAPIError,
                ) as e:  # Catch errors from _sign or get_timestamp
                    self.log.error(
                        "Error during signing process or timestamp fetching",
                        error=str(e),
                        endpoint=endpoint,
                    )
                    raise LBankAPIError(  # Re-wrap or pass through if already LBankAPIError
                        f"Signing process failed for {endpoint}: {e}",
                        request_params=original_params_for_error,
                    ) from e
                except (
                    httpx.RequestError
                ) as e_ts:  # Network error during timestamp fetch
                    self.log.error(
                        "Network error during timestamp fetch for signing",
                        error=str(e_ts),
                        endpoint=endpoint,
                    )
                    raise LBankAPIError(
                        f"Network error fetching timestamp for {endpoint}: {e_ts}",
                        request_params=original_params_for_error,
                    ) from e_ts

            self.log.debug(
                f"Sending {method.upper()} request",
                endpoint=endpoint,
                params_for_get=(
                    actual_request_params if method.upper() == "GET" else None
                ),
                data_keys_for_post=(
                    list(actual_request_params.keys())
                    if method.upper() == "POST"
                    else None
                ),
            )

            response: httpx.Response
            if method.upper() == "GET":
                response = await self.client.get(endpoint, params=actual_request_params)
            elif method.upper() == "POST":
                # LBank API V2 typically uses application/x-www-form-urlencoded for POST
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                response = await self.client.post(
                    endpoint, data=actual_request_params, headers=headers
                )
            else:
                self.log.error(
                    "Unsupported HTTP method used",
                    http_method=method,
                    endpoint=endpoint,
                )
                raise ValueError(f"Unsupported HTTP method: {method}")

            self.log.info(
                "Received response",
                status_code=response.status_code,
                endpoint=endpoint,
                method=method.upper(),
            )
            response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx responses

            try:
                response_data = response.json()
                # Log keys or type for brevity, not full data unless in very verbose debug mode
                self.log.debug(
                    "Raw API Response JSON parsed",
                    data_keys=(
                        list(response_data.keys())
                        if isinstance(response_data, dict)
                        else type(response_data).__name__
                    ),
                    endpoint=endpoint,
                )
            except ValueError as e_json:  # JSONDecodeError is a subclass
                self.log.error(
                    "Failed to decode JSON response",
                    endpoint=endpoint,
                    response_text_snippet=response.text[:200],  # Log a snippet
                    error=str(e_json),
                )
                raise LBankAPIError(
                    f"Invalid JSON response from {endpoint}: {e_json}",
                    response_data={"text": response.text},
                    request_params=original_params_for_error,
                ) from e_json

            # LBank specific error checking: "result":"false"
            if (
                isinstance(response_data, dict)
                and str(response_data.get("result")).lower() == "false"
            ):
                error_code_api = response_data.get("error_code")
                error_msg_api = response_data.get(
                    "msg", f"Unknown LBank API error (result:false) for {endpoint}"
                )
                self.log.error(
                    "LBank API returned a logical error",
                    api_error_code=error_code_api,
                    api_message=error_msg_api,
                    endpoint=endpoint,
                    response_data_snippet=str(response_data)[:200],
                )
                raise LBankAPIError(
                    error_msg_api,
                    error_code=error_code_api,
                    response_data=response_data,
                    request_params=original_params_for_error,
                )
            self.log.debug(
                "Request successful and API result is true (or not applicable).",
                endpoint=endpoint,
                method=method.upper(),
            )
            return response_data

        except httpx.HTTPStatusError as e_http:
            error_body_log = "Could not parse error body as JSON"
            try:
                error_body = e_http.response.json()
                error_body_log = error_body
            except ValueError:  # JSONDecodeError
                error_body_log = e_http.response.text[:200]  # Log snippet of text
            self.log.error(
                "HTTP Error occurred",
                status_code=e_http.response.status_code,
                error_body_snippet=error_body_log,
                endpoint=endpoint,
                method=method.upper(),
                # Log the params that were attempted (actual_request_params might contain signature)
                # For signed requests, original_params_for_error is safer if sensitive info was in signature.
                request_params_logged=loggable_params,
            )
            raise LBankAPIError(
                f"HTTP error {e_http.response.status_code} for {endpoint}: {e_http.response.text[:200]}",
                error_code=e_http.response.status_code,  # Use HTTP status as a general error code
                response_data={
                    "text": e_http.response.text,
                    "status_code": e_http.response.status_code,
                },
                request_params=original_params_for_error,
            ) from e_http
        except httpx.RequestError as e_req:  # Covers network errors, timeouts etc.
            self.log.error(
                "Request failed due to network or connection error",
                error_type=type(e_req).__name__,
                error_message=str(e_req),
                endpoint=endpoint,
                method=method.upper(),
                request_params_logged=loggable_params,
            )
            raise LBankAPIError(
                f"Request failed for {endpoint}: {type(e_req).__name__} - {e_req}",
                request_params=original_params_for_error,
            ) from e_req
        except (
            LBankAPIError
        ):  # Re-raise if it's already an LBankAPIError (e.g., from signing)
            raise
        except Exception as e_unexpected:  # Catch any other unexpected errors
            self.log.exception(  # Use .exception to include stack trace for unexpected errors
                "An unexpected error occurred during API request",
                endpoint=endpoint,
                method=method.upper(),
                request_params_logged=loggable_params,
                error=str(e_unexpected),
            )
            raise LBankAPIError(
                f"Unexpected error during request to {endpoint}: {e_unexpected}",
                request_params=original_params_for_error,
            ) from e_unexpected

    async def get_timestamp(self) -> Dict[str, Any]:
        """
        Fetches the current server timestamp from LBank.
        This is often required for signing requests.

        Returns:
            Dict[str, Any]: The API response containing the timestamp.
                            Typically {"result": "true", "data": "1600000000000", "error_code":0,"ts":...}

        Raises:
            LBankAPIError: If the timestamp cannot be fetched or the API returns an error.
        """
        self.log.debug("Attempting to fetch server timestamp")
        try:
            # Timestamp endpoint is typically GET and does not require signing
            response = await self._request("GET", "timestamp.do", signed=False)
            self.log.info(
                "Server timestamp fetched successfully",
                timestamp_data_field=response.get("data"),  # LBank specific field
            )
            return response
        except LBankAPIError as e:  # Re-raise specific API errors
            self.log.error(
                "Failed to get server timestamp due to API error",
                error=str(e),
                api_error_code=e.error_code,
            )
            raise
        except (
            Exception
        ) as e_unexpected:  # Catch any other error from _request or httpx
            self.log.exception("Unexpected error fetching server timestamp")
            raise LBankAPIError(
                f"Unexpected error fetching timestamp: {e_unexpected}"
            ) from e_unexpected

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Retrieves the current system status from LBank.

        Returns:
            Dict[str, Any]: The API response containing system status information.
        """
        self.log.debug("Attempting to fetch system status")
        # System status endpoint is typically GET and does not require signing
        return await self._request("GET", "supplement/system_status.do", signed=False)

    async def close_client(self):
        """
        Closes the underlying HTTPX client session.
        This should be called when the API client is no longer needed to free resources.
        """
        if self.client:
            await self.client.aclose()
            self.log.info("HTTPX client closed successfully.")


class LBankAPI(LBankAuthUtils):
    """
    Provides methods for interacting with specific LBank API V2 endpoints,
    covering market data, trading operations, and account management.
    Inherits authentication and request handling from LBankAuthUtils.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """
        Initializes the LBankAPI client.

        Args:
            api_key (str): Your LBank API key.
            api_secret (str): Your LBank API secret.
            base_url (str): The base URL for the LBank V2 REST API.
        """
        super().__init__(api_key, api_secret, base_url)
        self.log = self.log.bind(
            service_name="LBankAPI"
        )  # Bind specific service context
        self.log.info("LBankAPI client initialized.")

    # --- Market Data Endpoints ---
    async def get_market_depth(self, symbol: str, size: int) -> Dict[str, Any]:
        """
        Retrieve the order book depth for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            size (int): Number of depth entries to retrieve (e.g., 50, 100).

        Returns:
            Dict[str, Any]: Order book depth data.
        """
        self.log.info("Fetching market depth", symbol=symbol, size=size)
        if not symbol:
            raise ValueError("Symbol cannot be empty for get_market_depth.")
        if not isinstance(size, int) or size <= 0:
            raise ValueError("Size must be a positive integer for get_market_depth.")

        params = {
            "symbol": symbol,
            "size": str(size),
        }  # API might expect size as string
        return await self._request("GET", "depth.do", params=params, signed=False)

    async def get_latest_price(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve the latest price of a specific trading pair or all pairs if symbol is None.

        Args:
            symbol (str, optional): Trading pair symbol (e.g., 'btc_usdt').
                                    If None, retrieves prices for all available pairs.

        Returns:
            Dict[str, Any]: Latest price data. For a single symbol, it's usually a dict.
                            For all symbols, it's often a list of dicts or a dict of dicts.
                            LBank: {"result":"true","data":[{"symbol":"eth_usdt","price":"3000"},...],
                            "error_code":0,"ts":...}
                            or for single: {"result":"true","data":{"symbol":"eth_usdt","price":"3000"},
                            "error_code":0,"ts":...}
                            The provided `REST.py` implies it returns a dict where data is a list for all,
                            and a dict for one. Let's assume that.
        """
        self.log.info("Fetching latest price", symbol=symbol if symbol else "ALL")
        params = {}
        if symbol:
            if not isinstance(symbol, str) or not symbol.strip():  # Basic validation
                raise ValueError("Symbol must be a non-empty string if provided.")
            params["symbol"] = symbol
        # Endpoint: supplement/ticker/price.do
        return await self._request(
            "GET", "supplement/ticker/price.do", params=params, signed=False
        )

    async def get_24hr_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieve the 24-hour ticker data (price change, volume, etc.) for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').

        Returns:
            Dict[str, Any]: 24-hour ticker data.
        """
        self.log.info("Fetching 24hr ticker", symbol=symbol)
        if not symbol:
            raise ValueError("Symbol cannot be empty for get_24hr_ticker.")
        params = {"symbol": symbol}
        # Endpoint: supplement/ticker.do
        return await self._request(
            "GET", "supplement/ticker.do", params=params, signed=False
        )

    async def get_klines(
        self,
        symbol: str,
        size: int,
        kline_type: str,
        timestamp_sec: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve K-line (candlestick) data for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            size (int): The number of klines to retrieve (e.g., 100).
            kline_type (str): The kline interval type (e.g., 'minute1', 'hour1', 'day1').
                              Refer to LBank API documentation for valid types.
            timestamp_sec (int, optional): Timestamp in seconds. Kline data prior to this time will be returned.
                                       If None, returns the latest klines.

        Returns:
            Dict[str, Any]: K-line data, typically a list of [time, open, high, low, close, volume, ...].
        """
        endpoint = "supplement/klines.do"
        self.log.info(
            "Fetching klines",
            endpoint=endpoint,
            symbol=symbol,
            size=size,
            type=kline_type,
            time=timestamp_sec,
        )
        if not all([symbol, isinstance(size, int) and size > 0, kline_type]):
            raise ValueError(
                "Symbol, a positive size, and kline_type are required for klines."
            )

        params = {"symbol": symbol, "size": str(size), "type": kline_type}
        if timestamp_sec is not None:
            if not isinstance(timestamp_sec, int) or timestamp_sec < 0:
                raise ValueError(
                    "Timestamp must be a non-negative integer if provided."
                )
            params["time"] = str(timestamp_sec)

        return await self._request("GET", endpoint, params=params, signed=False)

    async def get_available_trading_pairs(self) -> Dict[str, Any]:
        """
        Get all available trading pairs on the exchange.

        Returns:
            Dict[str, Any]: A list of trading pair symbols or detailed information.
                            LBank: {"result":"true","data":["eth_btc","ltc_btc",...],"error_code":0,"ts":...}
        """
        self.log.info("Fetching available trading pairs")
        # Endpoint: currencyPairs.do
        return await self._request("GET", "currencyPairs.do", params={}, signed=False)

    async def get_trading_pair_info(self) -> Dict[str, Any]:
        """
        Acquires the basic accuracy information (precision) of all trading pairs.

        Returns:
            Dict[str, Any]: Information about trading pair precisions.
                            LBank: {"result":"true","data":[{"symbol":"eth_usdt","quantityAccuracy":"4",...},...],
                              "error_code":0,"ts":...}
        """
        self.log.info("Fetching trading pair accuracy information")
        # Endpoint: accuracy.do
        return await self._request("GET", "accuracy.do", params={}, signed=False)

    async def get_asset_config(self, asset_code: str) -> Dict[str, Any]:
        """
        Get coin information, such as deposit and withdrawal status and fees.

        Args:
            asset_code (str): The asset code (e.g., 'btc', 'usdt').

        Returns:
            Dict[str, Any]: Configuration details for the specified asset.
        """
        self.log.info("Fetching asset configuration", asset_code=asset_code)
        if not asset_code:
            raise ValueError("Asset code cannot be empty for get_asset_config.")
        params = {"assetCode": asset_code}
        # Endpoint: assetConfigs.do
        return await self._request(
            "GET", "assetConfigs.do", params=params, signed=False
        )

    async def get_symbol_orderbook_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get the current best bid and ask price and quantity for a symbol (Order Book Ticker).

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').

        Returns:
            Dict[str, Any]: Order book ticker data.
        """
        self.log.info("Fetching symbol order book ticker", symbol=symbol)
        if not symbol:
            raise ValueError("Symbol cannot be empty for get_symbol_orderbook_ticker.")
        params = {"symbol": symbol}
        # Endpoint: supplement/ticker/bookTicker.do
        return await self._request(
            "GET", "supplement/ticker/bookTicker.do", params=params, signed=False
        )

    async def get_24hr_leveraged_tokens_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieves 24-hour ticker data for specific leveraged tokens.

        Args:
            symbol (str): Leveraged token symbol (e.g., 'BTC3L_USDT').

        Returns:
            Dict[str, Any]: 24-hour ticker data for the leveraged token.
        """
        self.log.info("Fetching 24hr leveraged tokens ticker", symbol=symbol)
        if not symbol:
            raise ValueError(
                "Symbol cannot be empty for get_24hr_leveraged_tokens_ticker."
            )
        params = {"symbol": symbol}
        # Endpoint: supplement/leveraged_token_24h.do
        return await self._request(
            "GET", "supplement/leveraged_token_24h.do", params=params, signed=False
        )

    # --- Trading Endpoints ---
    async def place_order(
        self,
        symbol: str,
        order_type: str,  # LBank specific: 'buy', 'sell', 'buy_market', 'sell_market'
        price: str,  # For limit orders; for buy_market, it's quote amount; for sell_market, can be "0" for market price
        amount: str,  # For limit/sell orders, it's base asset amount; for buy_market, it's quote asset amount to spend
        custom_id: Optional[str] = None,  # Optional client order id
    ) -> Dict[str, Any]:
        """
        Places a new order on the LBank exchange.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            order_type (str): The type of order. Valid LBank types include:
                              'buy' (limit buy), 'sell' (limit sell),
                              'buy_market' (market buy), 'sell_market' (market sell).
            price (str): Order price.
                         For limit orders: the price per unit of the base asset.
                         For 'buy_market': LBank states this is the total amount of quote currency to spend.
                                           (Original REST.py used 'price' for this)
                         For 'sell_market': LBank states this is the market price (can be set to "0", API determines).
            amount (str): Order amount.
                          For 'buy'/'sell' (limit): quantity of the base asset.
                          For 'sell_market': quantity of the base asset to sell.
                          For 'buy_market': LBank's API documentation for `create_order` states `amount` is
                                            the quantity of quote currency to spend.
                                            This interpretation aligns with the original REST.py's `price` for
                                              buy_market.
                                            The `amount` field in `create_order` for `buy_market` is the total quote
                                              amount.
                                            Let's assume `amount` here is the LBank `amount` field.
                                            If `order_type` is 'buy_market', `price` is market price (can be "0"),
                                            `amount` is total quote to spend.
                                            If `order_type` is 'sell_market', `price` is market price (can be "0"),
                                            `amount` is base quantity to sell.
            custom_id (str, optional): A unique custom order ID provided by the client.

        Returns:
            Dict[str, Any]: Result of the order placement, typically includes an 'order_id'.
        """
        endpoint = "supplement/create_order.do"
        self.log.info(
            "Attempting to place order",
            endpoint=endpoint,
            symbol=symbol,
            type=order_type,
            price=price,
            amount=amount,
            custom_id=custom_id,
        )

        # Basic validation
        if not all([symbol, order_type, price, amount]):
            missing = [
                k
                for k, v in {
                    "symbol": symbol,
                    "type": order_type,
                    "price": price,
                    "amount": amount,
                }.items()
                if not v
            ]
            err_msg = (
                f"Missing required parameters for placing order: {', '.join(missing)}"
            )
            self.log.error(err_msg, missing_params=missing)
            raise ValueError(err_msg)

        valid_order_types = ["buy", "sell", "buy_market", "sell_market"]
        if order_type not in valid_order_types:
            self.log.error(
                f"Invalid order type: {order_type}", valid_types=valid_order_types
            )
            raise ValueError(
                f"Invalid order type: {order_type}. Must be one of {valid_order_types}"
            )

        params = {
            "symbol": symbol,
            "type": order_type,
            "price": str(price),  # API expects strings
            "amount": str(amount),  # API expects strings
        }
        if custom_id:
            if not isinstance(custom_id, str) or not custom_id.strip():
                raise ValueError("custom_id must be a non-empty string if provided.")
            params["custom_id"] = custom_id

        # Order placement is always a signed request
        response = await self._request("POST", endpoint, params=params, signed=True)
        self.log.info(
            "Order placement response received",
            endpoint=endpoint,
            symbol=symbol,
            type=order_type,
            order_id_in_response=(
                response.get("data", {}).get("order_id")
                if isinstance(response, dict)
                else "N/A"
            ),
        )
        return response

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
    ) -> Dict[str, Any]:
        """
        Cancels an existing open order.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            order_id (str): The ID of the order to cancel.

        Returns:
            Dict[str, Any]: Result of the order cancellation.
        """
        endpoint = "supplement/cancel_order.do"
        self.log.info(
            "Attempting to cancel order",
            endpoint=endpoint,
            symbol=symbol,
            order_id=order_id,
        )
        if not all([symbol, order_id]):
            missing = [
                k for k, v in {"symbol": symbol, "order_id": order_id}.items() if not v
            ]
            err_msg = f"Missing required parameters for cancelling order: {', '.join(missing)}"
            self.log.error(err_msg, missing_params=missing)
            raise ValueError(err_msg)

        params = {"symbol": symbol, "order_id": order_id}
        # Order cancellation is a signed request
        response = await self._request("POST", endpoint, params=params, signed=True)
        self.log.info(
            "Order cancellation response received",
            endpoint=endpoint,
            symbol=symbol,
            order_id=order_id,
            success_in_response=(
                response.get("result") if isinstance(response, dict) else "N/A"
            ),
        )
        return response

    async def get_order_details(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        Retrieve details of a specific order by its ID.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            order_id (str): The order ID.

        Returns:
            Dict[str, Any]: Detailed information about the order.
        """
        endpoint = "supplement/order_detail.do"
        self.log.info(
            "Fetching order details",
            endpoint=endpoint,
            symbol=symbol,
            order_id=order_id,
        )
        if not all([symbol, order_id]):
            raise ValueError("Symbol and order_id are required for get_order_details.")
        params = {"symbol": symbol, "order_id": order_id}
        return await self._request("POST", endpoint, params=params, signed=True)

    async def get_pending_orders(
        self,
        symbol: str,
        current_page: Optional[int] = 1,
        page_length: Optional[int] = 20,
    ) -> Dict[str, Any]:
        """
        Retrieve a list of pending (open) orders for a specific trading pair.
        LBank's API calls this "order_list.do" and it's for "uncompleted orders".

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            current_page (int, optional): Page number to retrieve. Defaults to 1.
            page_length (int, optional): Number of orders per page. Defaults to 20. Max 100.

        Returns:
            Dict[str, Any]: List of pending orders and pagination info.
        """
        endpoint = "supplement/order_list.do"  # This is for uncompleted orders
        self.log.info(
            "Fetching pending orders",
            endpoint=endpoint,
            symbol=symbol,
            current_page=current_page,
            page_length=page_length,
        )
        if not symbol:
            raise ValueError("Symbol is required for get_pending_orders.")
        if not (isinstance(current_page, int) and current_page > 0):
            raise ValueError("current_page must be a positive integer.")
        if not (
            isinstance(page_length, int) and 0 < page_length <= 100
        ):  # LBank max is 100 for this
            raise ValueError("page_length must be an integer between 1 and 100.")

        params = {
            "symbol": symbol,
            "current_page": str(current_page),
            "page_length": str(page_length),
        }
        return await self._request("POST", endpoint, params=params, signed=True)

    # --- Account Endpoints ---
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Retrieve account information, including asset balances.

        Returns:
            Dict[str, Any]: Account details including a list of assets and their balances.
                            LBank: data field contains `asset_list` and other user info.
        """
        self.log.info("Fetching account information")
        params = {}  # No specific parameters usually needed for main account info
        # This endpoint requires signing. _request will handle timestamp and signing.
        return await self._request(
            "POST", "supplement/user_info_account.do", params=params, signed=True
        )

    async def get_transaction_history(
        self,
        symbol: str,
        start_time: Optional[str] = None,  # Format 'yyyy-MM-dd HH:mm:ss'
        end_time: Optional[str] = None,  # Format 'yyyy-MM-dd HH:mm:ss'
        from_id: Optional[str] = None,
        limit: Optional[
            int
        ] = 100,  # Default to 100 if not specified, check API docs for max
    ) -> Dict[str, Any]:
        """
        Retrieve historical transaction (trade) details for a symbol.
        LBank's API calls this "hisorders.do".

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            start_time (str, optional): Start time in 'yyyy-MM-dd HH:mm:ss' format.
            end_time (str, optional): End time in 'yyyy-MM-dd HH:mm:ss' format.
            from_id (str, optional): Query starts from this transaction ID.
            limit (int, optional): Number of records to retrieve. Defaults to 100.

        Returns:
            Dict[str, Any]: Transaction history data.
        """
        self.log.info(
            "Fetching transaction history",
            symbol=symbol,
            startTime=start_time,
            endTime=end_time,
            fromId=from_id,
            limit=limit,
        )
        if not symbol:
            raise ValueError("Symbol is required for get_transaction_history.")

        params = {"symbol": symbol}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        if from_id:
            params["fromId"] = from_id
        if limit is not None:  # Allow 0 if API supports, but typically positive
            if not (
                isinstance(limit, int) and limit > 0
            ):  # Assuming limit must be positive
                raise ValueError("Limit must be a positive integer if provided.")
            params["limit"] = str(limit)

        return await self._request(
            "POST", "supplement/hisorders.do", params=params, signed=True
        )

    async def withdraw(
        self,
        address: str,
        network_name: str,  # LBank calls this 'networkName'
        coin: str,
        amount: str,
        fee: Optional[str] = None,  # API might expect fee as string
        memo: Optional[
            str
        ] = None,  # For currencies like EOS, XRP, etc. (LBank: 'memo')
        mark: Optional[str] = None,  # Withdrawal notes/remarks (LBank: 'mark')
        name: Optional[
            str
        ] = None,  # Address book remarks (LBank: 'name') - unclear if for new address or existing
        withdraw_order_id: Optional[
            str
        ] = None,  # Custom withdrawal ID (LBank: 'withdrawOrderId')
        transfer_type: Optional[
            int
        ] = None,  # 1 for intra-site transfer (LBank: 'type')
    ) -> Dict[str, Any]:
        """
        Initiates a withdrawal of funds to a specified address.

        Args:
            address (str): The destination withdrawal address. If transfer_type=1, this is the target LBank account.
            network_name (str): The chain name (e.g., "ERC20", "TRC20"). Get from assetConfigs.do.
            coin (str): The currency code to withdraw (e.g., 'USDT', 'BTC').
            amount (str): The amount to withdraw.
            fee (str, optional): The fee for the withdrawal. API might deduct automatically or require it.
                                 LBank docs are unclear if this is user-settable or informational.
                                 Often, fee is determined by the system.
            memo (str, optional): Memo or tag for currencies that require it.
            mark (str, optional): User-defined withdrawal notes.
            name (str, optional): Remark for the address if adding to address book (LBank specific usage unclear).
            withdraw_order_id (str, optional): Custom client-side ID for the withdrawal request.
            transfer_type (int, optional): Set to 1 for internal transfer between LBank accounts.

        Returns:
            Dict[str, Any]: The result of the withdrawal request, typically includes a withdrawal ID.
        """
        self.log.info(
            "Attempting to withdraw funds",
            coin=coin,
            amount=amount,
            address=address,
            network=network_name,
        )
        if not all([address, network_name, coin, amount]):
            raise ValueError(
                "Address, networkName, coin, and amount are required for withdrawal."
            )

        params = {
            "address": address,
            "networkName": network_name,
            "coin": coin,
            "amount": str(amount),  # Ensure string
        }
        if fee is not None:  # API might expect fee as string
            params["fee"] = str(fee)
        if memo:
            params["memo"] = memo
        if mark:
            params["mark"] = mark
        if (
            name
        ):  # Use with caution, LBank docs are sparse on this 'name' field's exact role
            params["name"] = name
        if withdraw_order_id:
            params["withdrawOrderId"] = withdraw_order_id
        if transfer_type is not None:
            if not isinstance(transfer_type, int):
                raise ValueError(
                    "transfer_type must be an integer if provided (e.g., 1 for internal)."
                )
            params["type"] = transfer_type  # LBank uses 'type' for this

        # Withdrawal is a signed request
        # The original `REST.py` called `self._sign(params)` directly here.
        # This is corrected to let `self._request` handle the signing process.
        return await self._request("POST", "withdraw.do", params=params, signed=True)


if __name__ == "__main__":
    import asyncio
    from app_utility import (
        load_config,
    )  # Assuming app_utils.py is in the same directory

    async def main():
        # This is an example. For actual use, ensure your .env file or environment variables
        # are set with API_KEY, API_SECRET, and other relevant URLs.
        config = load_config()
        api_key = config.get("API_KEY")
        api_secret = config.get("API_SECRET")
        base_url = config.get("REST_BASE_URL")

        if not api_key or not api_secret:
            print(
                "API_KEY and API_SECRET must be set in .env or environment for testing."
            )
            print("Skipping most authenticated client tests.")
            # Test a public endpoint
            public_client = LBankAPI("dummy_key", "dummy_secret", base_url)
            try:
                print("\nTesting get_timestamp (public)...")
                timestamp_data = await public_client.get_timestamp()
                print(f"Timestamp data: {timestamp_data}")

                print("\nTesting get_market_depth (public)...")
                depth = await public_client.get_market_depth("btc_usdt", 10)
                print(
                    f"BTC_USDT Depth (sample): asks: {depth.get('data', {}).get('asks')[:2]}, bids:"
                    + f" {depth.get('data', {}).get('bids')[:2]}"
                )

            except LBankAPIError as e:
                print(f"Public API Error: {e}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
            finally:
                await public_client.close_client()
            return

        # Proceed with authenticated client if keys are present
        client = LBankAPI(api_key, api_secret, base_url)
        try:
            print("LBankAPI client initialized with credentials.")

            print("\nTesting get_timestamp...")
            ts = await client.get_timestamp()
            print(f"Timestamp: {ts}")

            print("\nTesting get_system_status...")
            status = await client.get_system_status()
            print(f"System Status: {status}")

            print("\nTesting get_available_trading_pairs...")
            pairs = await client.get_available_trading_pairs()
            print(
                f"Available pairs (sample): {pairs.get('data')[:5] if pairs.get('data') else 'N/A'}"
            )

            print("\nTesting get_account_info (Authenticated)...")
            # This requires valid API keys with permissions
            try:
                acc_info = await client.get_account_info()
                print(
                    f"Account Info (balances sample): {acc_info.get('data', {}).get('asset_list', [])[:2]}"
                )
            except LBankAPIError as e:
                print(
                    f"Could not fetch account info (likely permissions or invalid keys): {e}"
                )

            # Example: Place a test order (USE WITH EXTREME CAUTION ON A LIVE ACCOUNT)
            # Ensure the symbol, price, and amount are appropriate for testing and you understand the risk.
            # This is commented out by default to prevent accidental orders.
            # try:
            #     print("\nAttempting to place a test order (ensure parameters are safe)...")
            #     # Example: buy 0.0001 BTC at $20000 USDT (adjust price to be far from market if just testing API call)
            #     # For market orders, price/amount interpretation is tricky.
            #     # Using a limit order for more predictable test:
            #     order_response = await client.place_order(
            #         symbol="btc_usdt",
            #         order_type="buy", # limit buy
            #         price="20000.00", # A price unlikely to fill immediately for testing
            #         amount="0.0001",
            #         custom_id=f"test_{int(asyncio.get_event_loop().time() * 1000)}"
            #     )
            #     print(f"Place order response: {order_response}")
            #     if order_response.get("result") == "true" and order_response.get("data", {}).get("order_id"):
            #         order_id_to_cancel = order_response["data"]["order_id"]
            #         print(f"Order placed: {order_id_to_cancel}. Attempting to cancel...")
            #         await asyncio.sleep(1) # Give a moment
            #         cancel_response = await client.cancel_order("btc_usdt", order_id_to_cancel)
            #         print(f"Cancel order response: {cancel_response}")
            # except LBankAPIError as e:
            #     print(f"Error during test order placement/cancellation: {e}")
            # except ValueError as e:
            #     print(f"Input validation error for order: {e}")

        except LBankAPIError as e:
            print(f"LBank API Error: {e}")
            print(f"  Error Code: {e.error_code}")
            if e.response_data:
                print(f"  Response Data: {str(e.response_data)[:200]}...")
            if e.request_params:
                print(f"  Request Params: {str(e.request_params)[:200]}...")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            print("\nClosing client session...")
            await client.close_client()
            print("Client session closed.")

    # Configure logging (optional, if you want to see structlog output from the client)
    # from logger_config import configure_logging
    # import logging
    # configure_logging(logging.DEBUG) # Set to DEBUG to see detailed logs

    asyncio.run(main())
