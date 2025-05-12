import httpx
try:
    from utils import BaseLogger
except ImportError:
    from ...utils import BaseLogger
from typing import Dict, Any
# import time
# import hmac
import hashlib
import string
import random


class LBankAuthUtils(BaseLogger):
    """
    Handles authentication and utilities for interacting with the LBank API.

    Attributes:
        BASE_URL (str): Base URL for the LBank API.
        api_key (str): API key for authentication.
        api_secret (str): API secret for signing requests.
    """

    BASE_URL = "https://api.lbank.info/v2/"

    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize the authentication utility with API credentials.

        Args:
            api_key (str): Your LBank API key.
            api_secret (str): Your LBank API secret.
        """
        super().__init__()
        self.log = self.log.bind(service="LBankAuthUtils")
        self.api_key = api_key
        self.api_secret = api_secret

    def _sign(self, params: Dict[str, Any], ts) -> Dict[str, Any]:
        """
        Generate a signature for the given parameters.

        Args:
            params (Dict[str, Any]): Dictionary of request parameters.

        Returns:
            Dict[str, Any]: Signed parameters with the API key and signature included.
        """
        self.log.debug("Signing request parameters", params=params)
        params['api_key'] = self.api_key
        # params['timestamp'] = int(time.time() * 1000)
        params['echostr'] = "".join(random.sample(string.ascii_letters + string.digits, 35)).upper()
        params['signature_method'] = "HmacSHA256"
        params['timestamp'] = ts['data']
        query_string = "&".join([f"{key}={params[key]}" for key in sorted(params)])
        self.log.debug('test', data=query_string)
        # signature = hmac.new(self.api_secret.encode(), query_string.encode("utf8"), hashlib.sha256).hexdigest().upper()
        signature = hashlib.md5(query_string.encode("utf8")).hexdigest().upper()
        params['sign'] = signature
        self.log.debug("Generated signature", signature=signature)
        new_params = {'api_key': self.api_key, 'sign': signature, 'timestamp': ts['data'],
                      'signature_method': "HmacSHA256", 'echostr': params['echostr']}
        return new_params

    async def _request(self, method: str, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send an asynchronous HTTP request to the LBank API.

        Args:
            method (str): HTTP method (e.g., 'GET', 'POST').
            endpoint (str): API endpoint.
            params (Dict[str, Any], optional): Request parameters. Defaults to None.

        Returns:
            Dict[str, Any]: API response as a dictionary.

        Raises:
            ValueError: If an unsupported HTTP method is used.
        """
        self.log.info("Sending request", method=method, endpoint=endpoint, params=params)
        url = self.BASE_URL + endpoint
        if params is None:
            params = {}
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=params)
            else:
                raise ValueError("Unsupported HTTP method")
            self.log.info("Received response", status_code=response.status_code, endpoint=endpoint)
            response.raise_for_status()
            # message = response.json()
            # return message['data'] if message['result'] else {'error': message['msg']}
            return response.json()

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Check the system status of the LBank API.

        Returns:
            Dict[str, Any]: System status information.
        """
        self.log.debug("Fetching system status")
        return await self._request("POST", "supplement/system_status.do")

    async def ping_server(self) -> Dict[str, Any]:
        """
        Ping the server to check API availability.

        Returns:
            Dict[str, Any]: Server ping response.
        """
        self.log.debug("Pinging server")
        return await self._request("POST", "supplement/system_ping.do")

    async def get_api_Restrictions(self) -> Dict[str, Any]:
        """get api Restrictions"""
        params = {}
        ts = await self._request("GET", "timestamp.do", {})
        signed_params = self._sign(params, ts=ts)
        return await self._request("POST", "supplement/api_Restrictions.do", signed_params)
