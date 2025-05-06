import os
import hashlib
import hmac
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
BASE_URL = os.getenv("BASE_URL")


class LBankAPI:
    def __init__(self):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.base_url = BASE_URL

    def _generate_signature(self, params):
        """
        Generate HMAC SHA256 signature for API requests.
        """
        sorted_params = sorted(params.items())
        query_string = "&".join(f"{key}={value}" for key, value in sorted_params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, endpoint, method="GET", params=None):
        """
        Make a request to the LBank API.
        """
        if params is None:
            params = {}

        params['api_key'] = self.api_key
        params['timestamp'] = int(time.time() * 1000)
        params['sign'] = self._generate_signature(params)

        url = f"{self.base_url}/{endpoint}"
        if method == "GET":
            response = requests.get(url, params=params)
        elif method == "POST":
            response = requests.post(url, data=params)
        else:
            raise ValueError("Unsupported HTTP method")

        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()

    def get_account_info(self):
        """
        Example API call to get account information.
        """
        endpoint = "v2/user_info.do"
        return self._make_request(endpoint)

    def place_order(self, symbol, type_, price, amount):
        """
        Example API call to place an order.
        """
        endpoint = "v2/create_order.do"
        params = {  # noqa: F841 (flake8 warning suppression)
            "symbol": symbol,
            "type": type_,
            "price": price,
            "amount": amount
        }
        return self._make_request(endpoint, method="POST")
