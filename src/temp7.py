import requests
import time
import hmac
import hashlib
import json
from urllib.parse import urlencode
import random
import string # For potential echostr, though not used in main signing path currently

class LBankAPIError(Exception):
    """Custom exception for LBank API errors."""
    def __init__(self, status_code, error_response):
        self.status_code = status_code
        self.error_response = error_response
        try:
            # Attempt to get a structured error message
            self.message = f"LBank API Error (HTTP Status: {status_code if status_code else 'N/A'}): Error Code: {error_response.get('error_code', 'N/A')}, Message: {error_response.get('msg', str(error_response))}"
            if 'data' in error_response and error_response['data'] is None and 'ret' in error_response and not error_response['ret']: # Another observed error pattern
                 self.message = f"LBank API Error (HTTP Status: {status_code if status_code else 'N/A'}): Error Code: {error_response.get('error_code', 'N/A')}, Ret: False, Message: {error_response.get('msg', 'Operation failed, data is null.')}"

        except AttributeError:
            self.message = f"LBank API Error (HTTP Status: {status_code if status_code else 'N/A'}): {str(error_response)}"
        super().__init__(self.message)

class LBankSpotAPI:
    """
    A Python client for interacting with the LBank Spot API.
    This client attempts to use V2 conventions (e.g., HmacSHA256) where possible,
    but LBank's API documentation has historically shown inconsistencies.
    Users should always verify against the latest official LBank API documentation.
    """
    BASE_URL_V2 = "https://api.lbank.info/v2"  # Primary V2 base URL
    BASE_URL_V1 = "https://api.lbkex.com/v1"    # Fallback V1 base URL for some public endpoints

    def __init__(self, api_key=None, secret_key=None, timeout=10):
        """
        Initializes the LBankSpotAPI client.
        Args:
            api_key (str, optional): Your LBank API key.
            secret_key (str, optional): Your LBank secret key.
            timeout (int, optional): Request timeout in seconds. Defaults to 10.
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = requests.Session()
        self.timeout = timeout

    def _get_timestamp_ms(self):
        """Returns the current timestamp in milliseconds as a string."""
        return str(int(time.time() * 1000))

    def _sign_request_params(self, params: dict):
        """
        Signs the request parameters using HmacSHA256.
        The exact string-to-sign format and signing method should be confirmed
        with LBank's latest V2 Spot API documentation.
        This implementation uses a common approach: sort parameters, create a query string,
        then sign that string.
        """
        if not self.secret_key:
            raise ValueError("Secret Key must be provided for signed requests.")

        # Parameters should be sorted alphabetically by key
        sorted_params = sorted(params.items())
        query_string = urlencode(sorted_params)

        # Sign the query_string using HmacSHA256 with the secret_key
        # LBank's Node.js connector for Spot uses HmacSHA256.
        # Older V1 docs mentioned MD5. This client assumes HmacSHA256 for V2.
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()  # Exchanges often expect uppercase hex signatures

        params['sign'] = signature
        # Some LBank docs mention 'signature_method' (e.g., 'HmacSHA256' or 'RSA').
        # It's often implicitly HmacSHA256 if 'sign' is present with API key.
        # If required, add: params['signature_method'] = 'HmacSHA256'
        return params

    def _request(self, method: str, endpoint_v1: str = None, endpoint_v2: str = None,
                 params: dict = None, data: dict = None, signed: bool = False,
                 use_v1_base_for_public: bool = False):
        """
        Handles the HTTP request to the LBank API.
        Args:
            method (str): HTTP method (GET, POST).
            endpoint_v1 (str, optional): V1 API endpoint path.
            endpoint_v2 (str, optional): V2 API endpoint path.
            params (dict, optional): URL parameters for GET requests.
            data (dict, optional): Form data for POST requests (application/x-www-form-urlencoded).
            signed (bool): Whether the request needs to be signed.
            use_v1_base_for_public (bool): If true, use V1 base URL for public (non-signed) calls.
        Returns:
            dict: JSON response from the API.
        Raises:
            LBankAPIError: If an API error occurs or the response is malformed.
        """
        if params is None:
            params = {}
        if data is None:
            data = {}

        base_url = self.BASE_URL_V2
        endpoint = endpoint_v2

        if use_v1_base_for_public and not signed and endpoint_v1:
            base_url = self.BASE_URL_V1
            endpoint = endpoint_v1
        elif not endpoint_v2 and endpoint_v1: # Fallback to V1 endpoint if V2 not provided
            base_url = self.BASE_URL_V1
            endpoint = endpoint_v1
        elif not endpoint: # Ensure an endpoint is selected
            raise ValueError("API endpoint must be provided via endpoint_v1 or endpoint_v2.")

        full_url = f"{base_url}{endpoint}"
        headers = {}

        # Prepare payload for signing (either GET params or POST data)
        payload_to_sign = {}
        if method.upper() == "GET":
            payload_to_sign.update(params)
        elif method.upper() == "POST":
            payload_to_sign.update(data) # For application/x-www-form-urlencoded

        if signed:
            if not self.api_key:
                raise ValueError("API Key must be provided for signed requests.")
            
            payload_to_sign['api_key'] = self.api_key
            payload_to_sign['timestamp'] = self._get_timestamp_ms()
            # `echostr` is sometimes required, especially for initial auth or WebSocket setup.
            # For general spot trading API calls, it's less common.
            # If an endpoint specifically requires it, it should be added here or to `payload_to_sign` before this block.
            # Example: payload_to_sign['echostr'] = ''.join(random.choices(string.ascii_letters + string.digits, k=30))

            signed_payload = self._sign_request_params(payload_to_sign)

            if method.upper() == "GET":
                params = signed_payload
            elif method.upper() == "POST":
                data = signed_payload # Now data includes api_key, timestamp, and sign
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
        
        # For debugging:
        # print(f"Requesting {method} {full_url}")
        # if params: print(f"  Params: {params}")
        # if data: print(f"  Data: {data}")
        # if headers: print(f"  Headers: {headers}")

        try:
            if method.upper() == "GET":
                response = self.session.get(full_url, params=params, headers=headers, timeout=self.timeout)
            elif method.upper() == "POST":
                response = self.session.post(full_url, data=data, headers=headers, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # For debugging:
            # print(f"Response Status: {response.status_code}")
            # print(f"Response Text: {response.text}")
            
            response_json = response.json()

            if response.status_code >= 400: # HTTP level error
                raise LBankAPIError(response.status_code, response_json)
            
            # LBank specific error checking (can vary between V1 and V2 and specific endpoints)
            # V1 often used "result": "true"/"false" and "error_code".
            # V2 might use "code": 0 for success, or "ret": true.
            if 'result' in response_json and str(response_json.get('result')).lower() == 'false':
                raise LBankAPIError(response.status_code, response_json)
            if 'error_code' in response_json and response_json['error_code'] != 0: # Common error indicator
                raise LBankAPIError(response.status_code, response_json)
            # LBank V2 seems to use "ret": true/false and "data": null on error for some endpoints
            if 'ret' in response_json and not response_json['ret'] and response_json.get('data') is None:
                 raise LBankAPIError(response.status_code, response_json)
            # Another common pattern: "code" field, where 0 or 200 is success.
            if 'code' in response_json and response_json['code'] != 0 and response_json['code'] != 200:
                 raise LBankAPIError(response.status_code, response_json)

            return response_json

        except requests.exceptions.Timeout:
            raise LBankAPIError(None, {'error_code': 'TIMEOUT', 'msg': f'Request timed out after {self.timeout} seconds.'})
        except requests.exceptions.RequestException as e: # Covers connection errors, etc.
            raise LBankAPIError(None, {'error_code': 'NETWORK_ERROR', 'msg': str(e)})
        except ValueError: # Includes JSONDecodeError
            raise LBankAPIError(response.status_code if 'response' in locals() else None,
                                {'error_code': 'INVALID_JSON_RESPONSE', 'msg': response.text if 'response' in locals() else 'Failed to decode JSON.'})

    # --- Public Market Data Methods ---
    def get_ticker_information(self, symbol: str):
        """
        Fetches ticker information for a specific symbol.
        LBank symbol format is typically 'eth_usdt'.
        Uses V1 endpoint `/ticker.do` as it's clearly documented for this purpose.
        V2 equivalent might be `/v2/ticker.do` or `/v2/market/ticker`.
        The response for a single symbol from V1 is a dict, not a list.
        If 'all' is passed as symbol, it returns a list.
        """
        params = {'symbol': symbol.lower()}
        # Using V1 base for this public endpoint due to clearer V1 documentation for it.
        return self._request("GET", endpoint_v1="/ticker.do", endpoint_v2="/ticker.do", params=params, use_v1_base_for_public=True)

    # --- Authenticated Account/Trading Methods ---
    def get_account_balance(self):
        """
        Retrieves spot account balance information.
        V1 endpoint: `/user_info.do` (POST).
        V2 equivalent is likely `/v2/user_info.do` or similar like `/v2/account/asset_balance.do`.
        This implementation assumes `/v2/user_info.do` (POST) based on V1 pattern.
        """
        # Parameters for signing (api_key, timestamp) are added by `_request` method.
        # V1's user_info.do required api_key and sign as POST data.
        return self._request("POST", endpoint_v1="/user_info.do", endpoint_v2="/user_info.do", signed=True, data={})

    def create_spot_order(self, symbol: str, order_type: str, price: str, amount: str, custom_id: str = None):
        """
        Places a new spot order (typically a limit order).
        LBank V1 endpoint: `/create_order.do` (POST).
        V2 likely: `/v2/create_order.do` or `/v2/trade/orders.do`.
        Args:
            symbol (str): Trading pair, e.g., "eth_usdt".
            order_type (str): "buy" or "sell".
            price (str): Price for the order (for limit orders). Must be string.
            amount (str): Quantity to buy/sell. Must be string.
            custom_id (str, optional): A custom order ID (if supported by LBank).
        """
        if order_type.lower() not in ['buy', 'sell']:
            raise ValueError("order_type must be 'buy' or 'sell'")

        data = {
            'symbol': symbol.lower(),
            'type': order_type.lower(),
            'price': price,   # API expects string
            'amount': amount, # API expects string
        }
        if custom_id:
            data['custom_id'] = custom_id # Check LBank docs if this is supported for V2

        # This endpoint is POST, Content-Type: application/x-www-form-urlencoded handled by _request
        return self._request("POST", endpoint_v1="/create_order.do", endpoint_v2="/create_order.do", data=data, signed=True)

    def get_order_info(self, symbol: str, order_id: str):
        """
        Retrieves information about a specific order.
        V1 endpoint: `/orders_info.do` (POST).
        V2 likely: `/v2/orders_info.do` or `/v2/trade/orders/{order_id}`.
        """
        data = {
            'symbol': symbol.lower(),
            'order_id': order_id
        }
        return self._request("POST", endpoint_v1="/orders_info.do", endpoint_v2="/orders_info.do", data=data, signed=True)

    def cancel_spot_order(self, symbol: str, order_id: str):
        """
        Cancels an open spot order.
        V1 endpoint: `/cancel_order.do` (POST).
        V2 likely: `/v2/cancel_order.do` or `/v2/trade/orders/{order_id}/cancel`.
        """
        data = {
            'symbol': symbol.lower(),
            'order_id': order_id
        }
        return self._request("POST", endpoint_v1="/cancel_order.do", endpoint_v2="/cancel_order.do", data=data, signed=True)

# --- Wrapper classes for a more structured API ---

class LBankMarket:
    """Handles market data operations."""
    def __init__(self, client: LBankSpotAPI):
        self.client = client

    def get_price_info(self, pair: str):
        """
        Gets the latest ticker information for a given pair.
        Args:
            pair (str): The trading pair, e.g., "ETH_USDT".
        Returns:
            dict: Ticker information from LBank.
                  Example for ETH_USDT:
                  {
                    "symbol": "eth_usdt",
                    "ticker": {
                      "high": "2000.0", "vol": "10000.0", "low": "1800.0",
                      "change": "1.5", "turnover": "19000000.0", "latest": "1950.0"
                    },
                    "timestamp": 1678886400000
                  }
                  Returns the raw ticker data.
        """
        if not isinstance(pair, str) or '_' not in pair:
            raise ValueError("Pair must be a string in format like 'ETH_USDT'")
        
        symbol = pair.lower() # LBank uses lowercase symbols with underscore
        try:
            ticker_data = self.client.get_ticker_information(symbol)
            # Ensure the response is for the requested symbol if API behavior changes
            if isinstance(ticker_data, dict) and ticker_data.get('symbol') == symbol:
                return ticker_data
            elif isinstance(ticker_data, list): # Should not happen for single symbol request with /ticker.do
                for item in ticker_data:
                    if item.get('symbol') == symbol:
                        return item
                raise LBankAPIError(None, {"error_code": "DATA_NOT_FOUND", "msg": f"Ticker for {symbol} not found in list response."})
            else:
                # This case might indicate an error response not caught by _request, or unexpected structure
                raise LBankAPIError(None, {"error_code": "UNEXPECTED_RESPONSE", 
                                           "msg": f"Unexpected ticker data structure for {symbol}: {ticker_data}"})
        except LBankAPIError as e:
            # Log or handle error appropriately
            # print(f"Error fetching price info for {pair}: {e}")
            raise
        except Exception as e: # Catch any other unexpected errors
            # print(f"An unexpected error occurred when fetching price info for {pair}: {e}")
            raise LBankAPIError(None, {"error_code": "CLIENT_SIDE_ERROR", "msg": str(e)})

class LBankTrading:
    """Handles trading operations."""
    def __init__(self, client: LBankSpotAPI):
        self.client = client

    def place_order(self, pair: str, side: str, price: float, quantity: float, order_category: str = "limit"):
        """
        Places a trade order.
        Args:
            pair (str): The trading pair, e.g., "ETH_USDT".
            side (str): "long" for a buy order, "short" for a sell order (in spot context).
            price (float): The price for the limit order.
            quantity (float): The amount of the base currency to trade.
            order_category (str): Type of order, defaults to "limit".
        Returns:
            dict: The response from LBank, typically containing the order_id.
                  Example V1 success: {"result":"true", "order_id":"..."}
                  Example V2 success: {"ret":true, "data":{"order_id":"..."}, "error_code":0, "msg":"Success"}
        """
        if not isinstance(pair, str) or '_' not in pair:
            raise ValueError("Pair must be a string in format like 'ETH_USDT'")
        
        symbol = pair.lower()
        
        if side.lower() == "long":
            order_type = "buy"
        elif side.lower() == "short": # Spot sell
            order_type = "sell"
        else:
            raise ValueError("Side must be 'long' (buy) or 'short' (sell).")

        if order_category.lower() != "limit":
            # LBank V1 /create_order.do is a limit order.
            # If LBank V2 has explicit market orders via a different endpoint or parameter,
            # this logic would need to be expanded.
            raise NotImplementedError(f"Order category '{order_category}' is not currently supported. Only 'limit' is.")

        try:
            # LBank API expects price and amount as strings
            str_price = "%.8f" % price # Format to a reasonable number of decimal places, adjust if needed
            str_quantity = "%.8f" % quantity # Format, adjust if needed

            # print(f"Placing {order_type} order for {str_quantity} {symbol.split('_')[0]} at {str_price} {symbol.split('_')[1]}")
            response = self.client.create_spot_order(symbol=symbol, order_type=order_type, 
                                                     price=str_price, amount=str_quantity)
            return response
        except LBankAPIError as e:
            # print(f"Error placing order for {pair}: {e}")
            raise
        except Exception as e:
            # print(f"An unexpected error occurred when placing order for {pair}: {e}")
            raise LBankAPIError(None, {"error_code": "CLIENT_SIDE_ERROR", "msg": str(e)})

    def get_order_status(self, pair: str, order_id: str):
        """
        Retrieves the details/status of a specific order.
        Args:
            pair (str): The trading pair, e.g., "ETH_USDT".
            order_id (str): The ID of the order to retrieve.
        Returns:
            dict: Order details from LBank.
        """
        symbol = pair.lower()
        try:
            return self.client.get_order_info(symbol=symbol, order_id=order_id)
        except LBankAPIError as e:
            raise
        except Exception as e:
            raise LBankAPIError(None, {"error_code": "CLIENT_SIDE_ERROR", "msg": str(e)})

    def cancel_trade_order(self, pair: str, order_id: str):
        """
        Cancels an open trade order.
        Args:
            pair (str): The trading pair, e.g., "ETH_USDT".
            order_id (str): The ID of the order to cancel.
        Returns:
            dict: Confirmation of cancellation from LBank.
        """
        symbol = pair.lower()
        try:
            return self.client.cancel_spot_order(symbol=symbol, order_id=order_id)
        except LBankAPIError as e:
            raise
        except Exception as e:
            raise LBankAPIError(None, {"error_code": "CLIENT_SIDE_ERROR", "msg": str(e)})


class LBankExchangeAPI:
    """
    Main API facade that brings together Market Data and Trading functionalities.
    """
    def __init__(self, api_key: str = None, secret_key: str = None, timeout: int = 10):
        """
        Initializes the LBank Exchange API client.
        Args:
            api_key (str, optional): Your LBank API key. Required for trading and private endpoints.
            secret_key (str, optional): Your LBank API secret. Required for trading and private endpoints.
            timeout (int, optional): Request timeout in seconds. Defaults to 10.
        """
        self._client = LBankSpotAPI(api_key=api_key, secret_key=secret_key, timeout=timeout)
        self.market = LBankMarket(self._client)
        self.trading = LBankTrading(self._client)
        # You can also expose account-related methods directly if needed
        # self.account = LBankAccount(self._client) # If you create an LBankAccount class

    def get_eth_usdt_price(self):
        """Convenience method to get ETH_USDT ticker information."""
        ticker_info = self.market.get_price_info("ETH_USDT")
        if ticker_info and 'ticker' in ticker_info and 'latest' in ticker_info['ticker']:
            return {"symbol": ticker_info.get("symbol"), "price": float(ticker_info["ticker"]["latest"]), "full_data": ticker_info}
        return {"symbol": "eth_usdt", "price": None, "full_data": ticker_info, "notice": "Could not parse latest price."}


if __name__ == '__main__':
    # --- IMPORTANT: Configuration ---
    # 1. Replace with your actual API Key and Secret Key from LBank.
    # 2. For production, load keys from environment variables or a secure config file.
    #    NEVER hardcode them in production code.
    # Example using environment variables:
    # import os
    # API_KEY = os.environ.get("LBANK_API_KEY")
    # SECRET_KEY = os.environ.get("LBANK_SECRET_KEY")

    API_KEY = "YOUR_API_KEY"    # <-- REPLACE OR LOAD FROM ENV
    SECRET_KEY = "YOUR_SECRET_KEY"  # <-- REPLACE OR LOAD FROM ENV

    # --- Public API Endpoint Example (Market Data) ---
    print("--- Testing Market Data (Public Ticker for ETH_USDT) ---")
    # No API keys needed for public market data if using the LBankMarket directly with a keyless client
    # However, the LBankExchangeAPI facade will pass keys if configured.
    # For strictly public calls, you could instantiate LBankSpotAPI() without keys.
    public_api_facade = LBankExchangeAPI() # No keys passed, so only public methods of underlying client will work
                                           # or methods that don't require signing.
                                           # get_ticker_information is designed to work without keys.
    try:
        eth_price_details = public_api_facade.get_eth_usdt_price()
        print(f"ETH_USDT Price Details (via facade): {eth_price_details}")
        if eth_price_details and eth_price_details.get('price') is not None:
            print(f"Current ETH_USDT Price: {eth_price_details['price']}")
        else:
            print("Could not retrieve ETH_USDT price via facade or price was None.")
            print(f"Full data received: {eth_price_details.get('full_data')}")
    except LBankAPIError as e:
        print(f"API Error fetching ETH_USDT price: {e}")
    except Exception as e:
        print(f"Generic error fetching ETH_USDT price: {e}")
    print("-" * 40)

    # --- Authenticated API Endpoint Examples (Requires API Key and Secret Key) ---
    if API_KEY == "YOUR_API_KEY" or SECRET_KEY == "YOUR_SECRET_KEY" or not API_KEY or not SECRET_KEY:
        print("\nWARNING: API_KEY and/or SECRET_KEY are not set or are placeholders.")
        print("Skipping authenticated tests (account balance, trading).")
        print("Please set your actual LBank API credentials in the script to test these features.")
    else:
        print("\n--- Testing Authenticated Endpoints (Account Balance & Trading) ---")
        # Use the facade with API keys for authenticated operations
        lbank_api = LBankExchangeAPI(api_key=API_KEY, secret_key=SECRET_KEY)

        # Example: Get Account Balance
        try:
            print("\nFetching account balance...")
            # Accessing the underlying client's method directly for this example
            balance_info = lbank_api._client.get_account_balance()
            print(f"Account Balance Info: {balance_info}")
            # Parse and display free/frozen assets if structure is known, e.g.
            # if balance_info.get('ret') and balance_info.get('data'):
            #     print(f"Data: {balance_info['data']}") # V2 often has data nested
            # elif balance_info.get('result') == 'true' and 'info' in balance_info: # V1 style
            #     print(f"Free assets: {balance_info['info'].get('free', {})}")
        except LBankAPIError as e:
            print(f"API Error (Account Balance): {e}")
        except Exception as e:
            print(f"Generic error (Account Balance): {e}")

        # --- Trading Examples (Use with EXTREME CAUTION) ---
        # Ensure the pair is correct, you have funds, and understand the risk.
        # For testing, use a very small amount and a price far from the market
        # to prevent accidental execution, or use a LBank testnet if available.

        trade_pair = "eth_usdt"
        # Example: Try to buy 0.001 ETH at a price of 1000 USDT (adjust as needed for safe testing)
        # This price is likely far from market, so the order might not fill, which is fine for testing API call.
        test_buy_price = 1000.0  # Price in USDT per ETH
        test_buy_quantity = 0.001 # Amount of ETH to buy

        placed_order_id = None

        try:
            print(f"\nAttempting to place a test BUY order for {test_buy_quantity} {trade_pair.split('_')[0].upper()} at {test_buy_price} {trade_pair.split('_')[1].upper()}...")
            # Ensure you have sufficient USDT (quote currency) for this test buy.
            buy_order_response = lbank_api.trading.place_order(
                pair=trade_pair,
                side="long",  # "long" means buy
                price=test_buy_price,
                quantity=test_buy_quantity
            )
            print(f"Buy Order Response: {buy_order_response}")

            # Extract order_id based on potential V1 or V2 response structures
            if buy_order_response:
                if buy_order_response.get('result') == 'true' and 'order_id' in buy_order_response: # V1 style
                    placed_order_id = buy_order_response['order_id']
                elif buy_order_response.get('ret') and buy_order_response.get('data') and 'order_id' in buy_order_response['data']: # V2 style
                    placed_order_id = buy_order_response['data']['order_id']
                elif 'order_id' in buy_order_response: # Direct order_id
                     placed_order_id = buy_order_response['order_id']


            if placed_order_id:
                print(f"Test BUY order placed successfully. Order ID: {placed_order_id}")
            else:
                print("Test BUY order placement might have failed or order_id not found in response.")
                print("Full response was:", buy_order_response)

        except LBankAPIError as e:
            print(f"API Error (Placing Test BUY Order): {e}")
        except Exception as e:
            print(f"Generic error (Placing Test BUY Order): {e}")

        # Example: Get Order Status (if an order was placed)
        if placed_order_id:
            try:
                print(f"\nFetching status for order ID: {placed_order_id}...")
                order_status = lbank_api.trading.get_order_status(pair=trade_pair, order_id=placed_order_id)
                print(f"Order Status for {placed_order_id}: {order_status}")
            except LBankAPIError as e:
                print(f"API Error (Get Order Status): {e}")
            except Exception as e:
                print(f"Generic error (Get Order Status): {e}")

            # Example: Cancel Order (if the order is still open)
            # Be cautious: only cancel if you are sure it's a test order you want to cancel.
            try:
                print(f"\nAttempting to cancel order ID: {placed_order_id}...")
                cancel_response = lbank_api.trading.cancel_trade_order(pair=trade_pair, order_id=placed_order_id)
                print(f"Cancel Order Response for {placed_order_id}: {cancel_response}")
            except LBankAPIError as e:
                print(f"API Error (Cancel Order): {e}")
            except Exception as e:
                print(f"Generic error (Cancel Order): {e}")
        else:
            print("\nSkipping Get Order Status and Cancel Order tests as no order_id was successfully retrieved.")
        
        print("-" * 40)
        print("Authenticated tests finished. Review output carefully.")
