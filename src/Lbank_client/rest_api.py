import httpx
import hashlib
import string
import random
from typing import Dict, Any
import json

# import hmac  # Added for correct HMAC-SHA256 signing if implemented

from app_logging import BaseLogger
from exceptions import LBankAPIError


# --- Authentication and Request Utility ---
class LBankAuthUtils(BaseLogger):
    """
    Handles authentication and utilities for interacting with the LBank REST API V2.

    Attributes:
        base_url (str): Base URL for the LBank API.
        api_key (str): API key for authentication.
        api_secret (str): API secret for signing requests.
        client (httpx.AsyncClient): Asynchronous HTTP client.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        super().__init__()
        self.log = self.log.bind(service="LBankAuthUtils")
        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret is missing. Authenticated requests will fail."
            )
        if not base_url:
            self.log.error("Base URL is missing. Cannot initialize client.")
            raise ValueError("Base URL cannot be empty.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/") + "/"
        try:
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        except Exception as e:
            self.log.exception(
                "Failed to initialize HTTPX client", base_url=self.base_url
            )
            raise LBankAPIError(f"Failed to initialize HTTPX client: {e}") from e
        self.log.info("LBankAuthUtils initialized", base_url=self.base_url)

    def _sign(self, params: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        """
        Generate parameters for a signed request (using MD5 as per original code).

        Args:
            params (Dict[str, Any]): Dictionary of specific endpoint parameters.
            timestamp (str): The timestamp string obtained from the API.

        Returns:
            Dict[str, Any]: Parameters required for the signed POST request body.

        Raises:
            TypeError: If params is not a dictionary or timestamp is not a string.
            ValueError: If required parameters for signing are missing.
        """
        self.log.debug(
            "Attempting to sign parameters",
            params_keys=list(params.keys()) if params else None,
            has_timestamp=bool(timestamp),
        )
        if not isinstance(params, dict):
            self.log.error("Invalid type for params in _sign", type=type(params))
            raise TypeError("params must be a dictionary")
        if not isinstance(timestamp, str):
            self.log.error("Invalid type for timestamp in _sign", type=type(timestamp))
            raise TypeError("timestamp must be a string")
        if not self.api_key:
            self.log.error("API key is missing, cannot sign request.")
            raise ValueError("API key is required for signing.")

        sign_params = params.copy()
        sign_params["api_key"] = self.api_key
        sign_params["timestamp"] = timestamp
        try:
            sign_params["echostr"] = "".join(
                random.sample(string.ascii_letters + string.digits, 35)
            ).upper()
        except Exception as e:
            self.log.exception("Failed to generate echostr")
            raise LBankAPIError("Failed to generate echostr for signing") from e

        sign_params["signature_method"] = "HmacSHA256"  # As per original code comment

        # Exclude signature itself from the query string to be signed if it were already present
        query_string_parts = []
        for key in sorted(sign_params.keys()):
            value = sign_params[key]
            if value is not None:
                query_string_parts.append(f"{key}={value}")
        query_string = "&".join(query_string_parts)

        self.log.debug("String to sign", query_string=query_string)

        try:
            # The original code uses MD5. LBank V2 API documentation typically indicates HMAC-SHA256.
            # I'm keeping MD5 as per original code, but noting the discrepancy.
            signature = hashlib.md5(query_string.encode("utf8")).hexdigest().upper()
            # If HMAC-SHA256 is indeed required, use:
            # signature = hmac.new(
            #     self.api_secret.encode('utf-8'),
            #     query_string.encode('utf-8'),
            #     hashlib.sha256
            # ).hexdigest().upper()
        except Exception as e:
            self.log.exception("Error during signature generation (MD5)")
            raise LBankAPIError("Failed to generate signature") from e

        self.log.debug("Generated signature (MD5)", signature=signature)

        final_params = {
            "api_key": self.api_key,
            "sign": signature,
            "timestamp": timestamp,
            "signature_method": sign_params["signature_method"],
            "echostr": sign_params["echostr"],
        }
        final_params.update(params)  # Add original params to the final set
        self.log.debug(
            "Final signed parameters prepared",
            final_params_keys=list(final_params.keys()),
        )
        return final_params

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        data: Any = None,
    ) -> Dict[str, Any]:
        """
        Send an asynchronous HTTP request to the LBank API.  Handles errors and retries.

        Args:
            method (str): HTTP method (e.g., "GET", "POST").
            endpoint (str): API endpoint.
            params (Dict[str, Any], optional): Query parameters for the request.
            headers (Dict[str, str], optional): Custom headers.
            data (Any, optional): Data for POST/PUT requests (JSON-encoded).

        Returns:
            Dict[str, Any]: The JSON response from the API.

        Raises:
            LBankAPIError: If the API returns an error or the request fails.
            Exception: For other unexpected errors during the request.
        """
        url = self.base_url + endpoint
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "MyLBankAPIClient/1.0",  # A basic User-Agent
        }
        headers = {**default_headers, **(headers or {})}  # Combine defaults and custom

        self.log.debug(
            "Sending request",
            method=method,
            url=url,
            params_keys=list(params.keys()) if params else None,
            headers_keys=list(headers.keys()) if headers else None,
        )
        try:
            response = await self.client.request(
                method, url, params=params, headers=headers, json=data
            )
            response.raise_for_status()  # Raise HTTPStatusError for bad responses (4xx or 5xx)
        except httpx.HTTPStatusError as http_err:
            # Handle API error responses (4xx, 5xx)
            self.log.error(
                "HTTP error",
                status_code=http_err.response.status_code,
                error_message=str(http_err),
                url=url,
                response_content=http_err.response.text,
            )
            try:
                error_data = http_err.response.json()
                #  The original code did not include request_params in the error
                raise LBankAPIError(
                    message=error_data.get("message", "API Error"),
                    error_code=error_data.get("code"),
                    response_data=error_data,
                    request_params=params,  # Include the request parameters in the error context
                ) from http_err
            except ValueError:  # Handle cases where the response is not JSON
                raise LBankAPIError(
                    message=f"HTTP Error: {http_err.response.text}",
                    response_data=http_err.response.text,
                    request_params=params,
                ) from http_err
        except httpx.RequestError as req_err:
            # Handle network errors (e.g., connection refused, DNS lookup failed)
            self.log.error("Request error", error_message=str(req_err), url=url)
            raise LBankAPIError(f"Request Error: {req_err}") from req_err
        except Exception as e:
            # Handle any other unexpected exceptions
            self.log.exception("Unexpected error during request", url=url)
            raise Exception(f"Unexpected error: {e}") from e

        try:
            # Attempt to parse the JSON response.  Raise LBankAPIError if it's not valid JSON.
            response_json = response.json()
            self.log.debug(
                "Received valid JSON response",
                response_keys=list(response_json.keys()),
            )
            return response_json
        except json.JSONDecodeError:
            self.log.error(
                "Invalid JSON response",
                response_content=response.text,
                url=url,
            )
            raise LBankAPIError(
                "Invalid JSON response from server", response_data=response.text
            )

    # --- Account Endpoints ---
    async def get_timestamp(self) -> str:
        """
        Get the current server timestamp.

        Returns:
            str: The server timestamp.
        """
        response = await self._request("GET", "timestamp.do")
        return str(response["data"])

    async def get_account_info(self, asset_code: str = None) -> Dict[str, Any]:
        """
        Get account information.  If asset_code is provided, return only that asset.

        Args:
            asset_code (str, optional): The specific asset code to query.

        Returns:
            Dict[str, Any]: Account information."""
        params = {}
        if asset_code:
            params["asset_code"] = asset_code
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "user_info.do", signed_params)

    async def get_all_pending_orders_info(
        self, symbol: str, current_page: int = 1, page_length: int = 200
    ) -> Dict[str, Any]:
        """
        Get all pending (open) orders for a symbol.

        Args:
            symbol (str): Trading pair symbol.
            current_page (int, optional): Page number, default is 1.
            page_length (int, optional): Number of orders per page, default is 200.  Max 200.

        Returns:
            Dict[str, Any]: A dictionary containing a list of order dictionaries.
        """
        params = {
            "symbol": symbol,
            "current_page": current_page,
            "page_length": page_length,
        }
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "orders_info.do", signed_params)

    # --- Trading Endpoints ---
    async def get_create_order_info(
        self,
        symbol: str,
        order_type: str,  # "buy" or "sell"
        amount: str,
        price: str,
        client_order_id: str = None,
    ) -> Dict[str, Any]:
        """
        Create a new order.

        Args:
            symbol (str): Trading pair symbol.
            order_type (str): "buy" or "sell".
            amount (str): Order amount.
            price (str): Order price.
            client_order_id (str, optional):  Client-provided order ID.

        Returns:
            Dict[str, Any]: Result of the order creation.
        """
        params = {
            "symbol": symbol,
            "type": order_type,
            "amount": amount,
            "price": price,
        }
        if client_order_id:
            params["client_order_id"] = client_order_id
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "create_order.do", signed_params)

    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order.

        Args:
            symbol (str): Trading pair symbol.
            order_id (str): ID of the order to cancel.

        Returns:
            Dict[str, Any]: Result of the cancellation.
        """
        params = {"symbol": symbol, "order_id": order_id}
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "cancel_order.do", signed_params)

    # --- Withdrawal Endpoints ---
    async def get_withdraw_rule(
        self,
        asset_code: str,
        network_name: str,
    ) -> Dict[str, Any]:
        """
        Get withdrawal rules for a specific asset and network.

        Args:
            asset_code (str):  Asset code.
            network_name (str): Network name.

        Returns:
            Dict[str, Any]: Withdrawal rules.
        """
        params = {"asset_code": asset_code, "networkName": network_name}
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "withdraw_rule.do", signed_params)

    async def withdraw(
        self,
        address: str,
        networkName: str,
        coin: str,
        amount: str,
        fee: float = None,
        memo: str = None,
        mark: str = None,
        name: str = None,
        withdrawOrderId: str = None,
        _type: int = None,
    ) -> Dict[str, Any]:
        """
        Withdraw funds to a specified address.

        Args:
            address (str): Withdrawal address; if type=1, it is the transfer account.
            networkName (str): Chain name (get from Get All Coin Information).
            coin (str): Currency.
            amount (str): Withdrawal amount.
            fee (float, optional): Fee.
            memo (str, optional): Memo for BTS and DCT.
            mark (str, optional): Withdrawal notes.
            name (str, optional): Address book remarks.
            withdrawOrderId (str, optional): Custom withdrawal ID.
            _type (int, optional): 1 for intra-site transfer.

        Returns:
            Dict[str, Any]: Withdrawal result.
        """
        params = {
            "address": address,
            "networkName": networkName,
            "coin": coin,
            "amount": amount,
            "fee": fee,
        }
        if memo:
            params["memo"] = memo
        if mark:
            params["mark"] = mark
        if name:
            params["name"] = name
        if withdrawOrderId:
            params["withdrawOrderId"] = withdrawOrderId
        if _type:
            params["type"] = _type
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "withdraw.do", signed_params)

    async def get_deposit_address(
        self,
        asset_code: str,
        network_name: str,
    ) -> Dict[str, Any]:
        """
        Get deposit address

        Args:
            asset_code (str): Asset code.
            network_name (str):  Chain name.

        Returns:
            Dict[str, Any]: Deposit address information.
        """
        params = {"asset_code": asset_code, "networkName": network_name}
        signed_params = self._sign(params, await self.get_timestamp())
        return await self._request("POST", "deposit_address.do", signed_params)

    async def close(self):
        """
        Close the HTTPX client session.  This should be called when you're done
        with the REST API client.
        """
        await self.client.aclose()
        self.log.info("HTTPX client session closed.")

    async def __aenter__(self):
        """
        Async context manager entry.  Returns the instance.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.  Calls close().
        """
        await self.close()
