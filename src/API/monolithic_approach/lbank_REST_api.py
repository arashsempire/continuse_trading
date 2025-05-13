import hashlib
import hmac
import time
import httpx
from .utils import load_keys


class LBankAPI:
    def __init__(self):
        keys = load_keys()
        self.api_key = keys['api_key']
        self.api_secret = keys['api_secret']
        self.base_url = keys['base_url']
        self.client = httpx.AsyncClient()

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

    async def _make_request(self, endpoint, method="GET", params=None):
        """
        Make an asynchronous request to the LBank API.
        """
        if params is None:
            params = {}

        params['api_key'] = self.api_key
        params['timestamp'] = int(time.time() * 1000)
        params['sign'] = self._generate_signature(params)

        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                response = await self.client.get(url, params=params)
            elif method == "POST":
                response = await self.client.post(url, data=params)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"HTTP error occurred: {exc}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Request error occurred: {exc}") from exc

    async def get_account_info(self):
        """
        Example API call to get account information.
        """
        endpoint = "v2/user_info.do"
        return await self._make_request(endpoint)

    async def place_order(self, symbol, type_, price, amount):
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
        return await self._make_request(endpoint, method="POST")

    async def close(self):
        """
        Properly close the httpx.AsyncClient session.
        """
        await self.client.aclose()
