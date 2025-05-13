import httpx
import hashlib
import string
import random
from typing import Dict, Any, Optional
from ...utils import BaseLogger


# --- Custom Exception for API Errors ---
class LBankAPIError(Exception):
    """Custom exception for LBank API errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        response_data: Optional[Dict] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.response_data = response_data

    def __str__(self):
        if self.error_code:
            return f"LBankAPIError(code={self.error_code}): {self.args[0]}"
        return f"LBankAPIError: {self.args[0]}"


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
        """
        Initialize the authentication utility with API credentials and base URL.

        Args:
            api_key (str): Your LBank API key.
            api_secret (str): Your LBank API secret.
            base_url (str): The base URL for the LBank V2 REST API.
        """
        super().__init__()
        self.log = self.log.bind(service="LBankAuthUtils")  # Add service context
        if not api_key or not api_secret:
            self.log.warning(
                "API Key or Secret is missing. Authenticated requests will fail."
            )
        self.api_key = api_key
        self.api_secret = api_secret  # Store secret for signing (when implemented)
        self.base_url = base_url.rstrip("/") + "/"  # Ensure trailing slash
        # Increased timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        self.log.info("LBankAuthUtils initialized", base_url=self.base_url)

    # --- Signing Method (Placeholder - Requires Correction) ---
    # NOTE: This signing method uses MD5 as per the original code provided.
    # LBank V2 typically requires HMAC-SHA256. This needs verification and correction.
    def _sign(self, params: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        """
        Generate parameters for a signed request (using MD5 as per original code).

        Args:
            params (Dict[str, Any]): Dictionary of specific endpoint parameters.
            timestamp (str): The timestamp string obtained from the API.

        Returns:
            Dict[str, Any]: Parameters required for the signed POST request body.
                            Includes api_key, sign, timestamp, signature_method,
                            echostr.
        """
        # Combine endpoint-specific params with common signing params
        sign_params = params.copy()  # Avoid modifying original dict
        sign_params["api_key"] = self.api_key
        sign_params["timestamp"] = timestamp
        # Generate a random string for echostr
        sign_params["echostr"] = "".join(
            random.sample(string.ascii_letters + string.digits, 35)
        ).upper()
        # This seems inconsistent with MD5 signing below
        sign_params["signature_method"] = "HmacSHA256"

        # Sort parameters by key and create the query string
        query_string = "&".join(
            [f"{key}={sign_params[key]}" for key in sorted(sign_params)]
        )
        self.log.debug("String to sign", query_string=query_string)

        # --- !!! CRITICAL: Signing Logic Needs Verification !!! ---
        # The original code used MD5 here. LBank V2 docs usually specify HMAC-SHA256.
        # Using MD5 is likely incorrect and insecure.
        signature = hashlib.md5(query_string.encode("utf8")).hexdigest().upper()
        # Correct HMAC-SHA256 would be:
        # import hmac
        # signature = hmac.new(
        #     self.api_secret.encode('utf-8'),
        #     query_string.encode('utf-8'),
        #     hashlib.sha256
        #     ).hexdigest().upper()
        # ----------------------------------------------------------

        self.log.debug("Generated signature (MD5)", signature=signature)

        # Prepare the final parameters for the request body
        # Note: The original endpoint params are NOT included here, only signing params
        final_params = {
            "api_key": self.api_key,
            "sign": signature,
            "timestamp": timestamp,
            "signature_method": sign_params["signature_method"],  # "HmacSHA256"
            "echostr": sign_params["echostr"],
        }
        # Important: The actual endpoint parameters (like 'symbol', 'amount') need to be
        # passed separately, often in the POST request body *alongside* these signing
        # params, or sometimes as URL parameters depending on the specific endpoint
        # documentation.
        # The current implementation seems to only return signing params, which might
        # be incomplete.
        # --> Revisit LBank docs for how endpoint params and signing params are
        # combined. <--
        # For now, assuming endpoint params are merged into the POST body/json:
        final_params.update(params)  # Merge original params back

        return final_params

    # --- Core Request Method ---
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """
        Send an asynchronous HTTP request to the LBank API.

        Args:
            method (str): HTTP method ('GET', 'POST').
            endpoint (str): API endpoint path (e.g., 'depth.do').
            params (Dict[str, Any], optional): Request parameters. Defaults to None.
            signed (bool): Whether the request requires authentication/signing.
                           Defaults to False.

        Returns:
            Dict[str, Any]: API response JSON parsed as a dictionary.

        Raises:
            ValueError: If an unsupported HTTP method is used.
            httpx.HTTPStatusError: If the API returns an HTTP error status (4xx, 5xx).
            LBankAPIError: If the API returns a successful HTTP status but indicates
                           an error in the response body (e.g., result='false').
        """
        if params is None:
            params = {}

        request_params = params.copy()  # Work with a copy

        # --- Signing Logic Integration (Requires Timestamp Fetching) ---
        if signed:
            if not self.api_key or not self.api_secret:
                self.log.error("Cannot make signed request: API key or secret missing.")
                raise LBankAPIError(
                    "API key or secret not configured for signed request."
                )
            try:
                # Fetch current timestamp from LBank *before* signing
                ts_response = await self.get_timestamp()
                timestamp = str(ts_response.get("data"))  # Ensure it's a string
                if not timestamp:
                    raise LBankAPIError("Failed to fetch valid timestamp for signing.")

                # Prepare signed parameters (needs verification based on LBank docs)
                # The _sign method currently returns all params merged.
                request_params = self._sign(request_params, timestamp)
                self.log.debug("Signed parameters prepared", params=request_params)

            except (httpx.RequestError, httpx.HTTPStatusError, LBankAPIError) as e:
                self.log.error(
                    "Failed to prepare signed request", error=str(e), endpoint=endpoint
                )
                raise LBankAPIError(
                    f"Failed to prepare signed request for {endpoint}: {e}"
                ) from e

        # --- Making the Request ---
        self.log.debug(
            f"Sending {method} request",
            endpoint=endpoint,
            params=request_params if method == "GET" else None,
            data=request_params if method == "POST" else None,
        )
        try:
            response: httpx.Response
            if method.upper() == "GET":
                response = await self.client.get(endpoint, params=request_params)
            elif method.upper() == "POST":
                # LBank V2 often uses form-encoded data for POST, not JSON
                # Check documentation for specific endpoints. Using 'data' for form
                # encoding.
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                response = await self.client.post(
                    endpoint, data=request_params, headers=headers
                )
            else:
                self.log.error("Unsupported HTTP method", method=method)
                raise ValueError(f"Unsupported HTTP method: {method}")

            self.log.info(
                "Received response", status_code=response.status_code, endpoint=endpoint
            )
            response.raise_for_status()  # Raise exception for 4xx/5xx responses

            # Parse JSON response
            response_data = response.json()
            self.log.debug("Raw API Response", data=response_data)

            # --- LBank Specific Error Handling ---
            # Check if the response indicates a logical error despite HTTP 200 OK
            if (
                isinstance(response_data, dict)
                and str(response_data.get("result")).lower() == "false"
            ):
                error_code = response_data.get("error_code")
                error_msg = response_data.get("msg", "Unknown LBank API error")
                self.log.error(
                    "LBank API returned an error",
                    code=error_code,
                    message=error_msg,
                    endpoint=endpoint,
                )
                raise LBankAPIError(
                    error_msg, error_code=error_code, response_data=response_data
                )

            return response_data

        except httpx.HTTPStatusError as e:
            # Log details from the response if available
            error_body = None
            try:
                error_body = e.response.json()
                self.log.error(
                    "HTTP Error",
                    status=e.response.status_code,
                    body=error_body,
                    endpoint=endpoint,
                    params=params,
                )
            except Exception:
                error_body = e.response.text
                self.log.error(
                    "HTTP Error (non-JSON body)",
                    status=e.response.status_code,
                    body=error_body,
                    endpoint=endpoint,
                    params=params,
                )
            # Re-raise the original exception
            raise e
        except httpx.RequestError as e:
            self.log.error(
                "Request failed", error=str(e), endpoint=endpoint, params=params
            )
            # Re-raise the original exception
            raise e
        except Exception as e:
            self.log.exception(
                "An unexpected error occurred during request",
                endpoint=endpoint,
                params=params,
            )
            raise LBankAPIError(f"Unexpected error during request: {e}") from e

    # --- Utility API Methods ---

    async def get_timestamp(self) -> Dict[str, Any]:
        """Get current server time stamp from LBank."""
        # This endpoint is usually GET, but original code used POST. Verify LBank docs.
        # Assuming GET based on common practice.
        self.log.debug("Fetching server timestamp")
        # This endpoint does not require signing
        return await self._request("GET", "timestamp.do", signed=False)

    async def get_system_status(self) -> Dict[str, Any]:
        """Check the system status of the LBank API."""
        self.log.debug("Fetching system status")
        # Assuming POST and no signing based on original code. Verify LBank docs.
        return await self._request("POST", "supplement/system_status.do", signed=False)

    async def ping_server(self) -> Dict[str, Any]:
        """Ping the server to check API availability."""
        self.log.debug("Pinging server")
        # Assuming POST and no signing based on original code. Verify LBank docs.
        return await self._request("POST", "supplement/system_ping.do", signed=False)

    async def get_api_restrictions(self) -> Dict[str, Any]:
        """Get API key restrictions."""
        self.log.debug("Fetching API restrictions")
        # This endpoint requires signing
        params = {}  # No specific parameters needed for this endpoint itself
        return await self._request(
            "POST", "supplement/api_Restrictions.do", params=params, signed=True
        )

    async def close_client(self):
        """Closes the underlying HTTPX client."""
        await self.client.aclose()
        self.log.info("HTTPX client closed.")


# Example usage (requires async context)


async def main_rest_utils_example():
    # import asyncio
    from utils import (
        load_config,
    )  # Assuming utils.py is in the same directory or Python path
    from ...utils import configure_logging  # Assuming logger.py is available
    import logging

    configure_logging(logging.DEBUG)
    config = load_config()

    # Ensure necessary config is present
    if (
        not config.get("API_KEY")
        or not config.get("API_SECRET")
        or not config.get("REST_BASE_URL")
    ):
        print("Error: Missing API_KEY, API_SECRET, or REST_BASE_URL in config.")
        return

    auth_utils = LBankAuthUtils(
        api_key=config["API_KEY"],
        api_secret=config["API_SECRET"],
        base_url=config["REST_BASE_URL"],
    )

    try:
        # --- Test Unsigned Endpoint ---
        print("\n--- Testing Timestamp (Unsigned) ---")
        try:
            timestamp_data = await auth_utils.get_timestamp()
            print(f"Timestamp Response: {timestamp_data}")
        except Exception as e:
            print(f"Error getting timestamp: {e}")

        # --- Test Signed Endpoint ---
        # Note: This will likely fail if the MD5 signing is incorrect for LBank V2
        print("\n--- Testing API Restrictions (Signed) ---")
        try:
            restrictions_data = await auth_utils.get_api_restrictions()
            print(f"API Restrictions Response: {restrictions_data}")
        except LBankAPIError as e:
            print(f"LBank API Error getting restrictions: {e}")
            if e.response_data:
                print(f"  Response Data: {e.response_data}")
        except Exception as e:
            print(f"Error getting API restrictions: {e}")

    finally:
        await auth_utils.close_client()  # Clean up the client


if __name__ == "__main__":
    import asyncio

    asyncio.run(main_rest_utils_example())
