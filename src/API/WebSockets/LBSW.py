import os
import websockets
import asyncio
import json
import hmac
import hashlib
from utils import BaseLogger
from typing import Optional
import pandas as pd
import httpx
import time
from dotenv import load_dotenv
from API.REST.REST_data import MarketDataClient

# Load environment variables from a .env file
load_dotenv()


class KBarWebSocketClient(BaseLogger):
    """WebSocket client for interacting with market data.

    Attributes:
        uri (str): WebSocket server URI.
        api_key (str): API key for LBank.
        api_secret (str): API secret for LBank.
        pair (str): Currency pair for market data.
        latest_price (Optional[float]): Latest market price.
        daily_open (Optional[float]): Daily open price.
        daily_open_ts (Optional[float]): Timestamp for daily open price.
        connection (Optional[websockets.WebSocketClientProtocol]): WebSocket connection.
        keep_running (bool): Flag to keep the WebSocket running.
        subscribeKey (Optional[str]): Subscription key for updates.
    """

    ACTION = "action"
    SUBSCRIBE = "subscribe"
    REQUEST = "request"
    PING = "ping"
    PONG = "pong"
    KBAR = "kbar"
    STATUS = "status"
    ERROR = "error"

    def __init__(self, uri: str, api_key: str, api_secret: str, pair: str = "eth_usdt"):
        """Initialize the WebSocket client with default values.

        Args:
            uri (str): WebSocket server URI.
            api_key (str): API key for LBank.
            api_secret (str): API secret for LBank.
            pair (str): Currency pair for market data. Defaults to "eth_usdt".
        """
        super().__init__()
        self.log = self.log.bind()
        self.uri = uri
        self.api_key = api_key
        self.api_secret = api_secret
        self.pair = pair
        self.latest_price: Optional[float] = None
        self.daily_open: Optional[float] = None
        self.daily_open_ts: Optional[float] = None
        self.connection: Optional[websockets.WebSocketClientProtocol] = None
        self.keep_running: bool = True
        self.subscribeKey: Optional[str] = None
        self.listen_task: Optional[asyncio.Task] = None  # To manage the listen task
        self.tasks = []  # List to keep track of asynchronous tasks
        self.reconnect_attempts = 0  # Counter for reconnection attempts
        self.DataClient = MarketDataClient(api_key, api_secret)

        self.log.info("KBarWebSocketClient initialized", uri=self.uri, pair=self.pair)

    async def connect(self) -> None:
        """Establish a WebSocket connection."""
        while self.keep_running:
            try:
                self.log.debug("Attempting to connect to WebSocket", uri=self.uri)
                self.connection = await websockets.connect(self.uri)
                self.log.info("Connected to WebSocket", uri=self.uri)
                self.reconnect_attempts = 0  # Reset reconnect attempts on successful connection
                break
            except Exception as e:
                self.log.error("Failed to connect to WebSocket", error=str(e))
                self.reconnect_attempts += 1
                self.log.debug("Reconnect attempt", attempt=self.reconnect_attempts)
                await asyncio.sleep(min(2**self.reconnect_attempts, 300))  # Exponential backoff with a maximum delay

    async def check_connection(self) -> None:
        """Periodically check the WebSocket connection and reconnect if necessary."""
        self.log.debug("Starting connection check loop")
        while self.keep_running:
            await asyncio.sleep(30)
            if self.connection is None or self.connection.closed:
                self.log.warning("Connection lost, attempting to reconnect")
                await self.reconnect()

    async def reconnect(self) -> None:
        """Reconnect to the WebSocket."""
        self.log.info("Reconnecting to WebSocket")
        await self.stop()
        await self.start()

    async def start(self) -> None:
        """Start the WebSocket client."""
        self.log.info("Starting WebSocket client")
        self.tasks = [
            asyncio.create_task(self.connect()),
            asyncio.create_task(self.listen()),
            asyncio.create_task(self.check_connection()),
            asyncio.create_task(self.subscribe_kbar()),
            asyncio.create_task(self.request_kbar()),
            asyncio.create_task(self.update_subscribed_order()),
            asyncio.create_task(self.update_subscribed_asset()),
        ]
        await asyncio.gather(*self.tasks)

    async def stop(self) -> None:
        """Gracefully stop the WebSocket client."""
        self.log.info("Stopping WebSocket client")
        self.keep_running = False
        await self._close_tasks()
        await self._close()
        self.log.info("WebSocket client stopped")

    async def _close_tasks(self) -> None:
        """Close all running tasks."""
        self.log.info("Closing all running tasks")
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks = []

    async def _close(self) -> None:
        """Close the WebSocket connection."""
        if self.connection and not self.connection.closed:
            self.log.info("Closing WebSocket connection")
            await self.connection.close()
            self.log.info("WebSocket connection closed")

    async def listen(self) -> None:
        """Listen for incoming WebSocket messages."""
        self.log.info("Listening for incoming WebSocket messages")
        while self.keep_running:
            try:
                async for message in self.connection:
                    self.log.debug("Received message", message=message)
                    data = json.loads(message)
                    await self.process_incoming_message(data)
            except json.JSONDecodeError as je:
                self.log.error("JSON Decode Error", error=str(je))
            except websockets.ConnectionClosed:
                self.log.warning("WebSocket connection closed, reconnecting")
                await self.reconnect()
            except Exception as e:
                self.log.error("An error occurred", error=str(e))
                await self.reconnect()

    async def process_incoming_message(self, data: dict) -> None:
        """Process incoming WebSocket data.

        Args:
            data (dict): Incoming data from the WebSocket.
        """
        self.log.debug("Processing incoming message", data=data)
        message_status = data.get(self.STATUS)
        message_action = data.get(self.ACTION)
        message_type = data.get("type")
        request_message = data if isinstance(data.get(message_type), str) else None
        subscribe_message = data if not isinstance(data.get(message_type), str) else None

        if subscribe_message and message_type == self.KBAR:
            self.latest_price = data[self.KBAR].get("c")
            self.log.info("KBar subscription message received", latest_price=self.latest_price)

        elif subscribe_message:
            self.log.info("Subscription message received")

        elif message_status:
            if message_status == self.ERROR:
                self.log.error("Error status received", data=data)
                await self.reconnect()
            else:
                self.log.info("Status message received", status=message_status)

        elif message_action:
            if message_action == self.PING:
                self.log.info("Ping action received", data=data)
                await self._send_message({self.ACTION: self.PONG, "pong": data[self.PING]})
            elif message_action == self.PONG:
                self.log.info("Pong action received", data=data)
                # await self._ping(data)
                # ============================================================================================
                await self._ping('')
            else:
                self.log.info("Other action received", action=message_action)

        elif request_message and message_type == self.KBAR:
            self.log.info("KBar request message received")
            if "records" in data and "columns" in data:
                df = pd.DataFrame(data["records"], columns=data["columns"])
                self.daily_open, self.daily_open_ts = df[["timestamp", "close"]].iloc[-1]
                self.log.info("Daily open price and timestamp updated",
                              daily_open=self.daily_open,
                              daily_open_ts=self.daily_open_ts)
            else:
                self.log.error("Invalid 'kbar' message format")

        elif request_message:
            self.log.info("Request message received", request_message=request_message)

        else:
            self.log.warning("Unknown message type received", data=data)

    async def _send_message(self, message: dict) -> None:
        """Send a JSON message to the WebSocket.

        Args:
            message (dict): Message to send.
        """
        try:
            if self.connection and self.connection.open:
                data = json.dumps(message)
                response = await self.connection.send(data)
                self.log.info("Message sent", message=message)
                self.log.debug("Message sent", response=response)
        except Exception as e:
            self.log.error("Failed to send message", error=str(e))

    async def _ping(self, data: Optional[dict] = None) -> None:
        """Send a ping message to the WebSocket server.

        Args:
            data (Optional[dict]): Ping data. Defaults to None.
        """
        # ===========================================================================
        self.log.info("Sending ping message", data=data)
        if data:
            pass
        else:
            ping_message = "AAAAAAA!"
            message = {self.ACTION: self.PING, "ping": ping_message}
            await self._send_message(message)

    async def subscribe_kbar(self, kbar: str = "1min") -> None:
        """Subscribe to a specific market data feed.

        Args:
            kbar (str): KBar interval. Defaults to "1min".
        """
        self.log.info("Subscribing to KBar", kbar=kbar, pair=self.pair)
        message = {
            self.ACTION: self.SUBSCRIBE,
            self.SUBSCRIBE: self.KBAR,
            self.KBAR: kbar,
            "pair": self.pair,
        }
        await self._send_message(message)

    async def request_kbar(self, kbar: str = "day") -> None:
        """Request specific market data.

        Args:
            kbar (str): KBar interval. Defaults to "day".
        """
        self.log.info("Requesting KBar data", kbar=kbar, pair=self.pair)
        message = {
            self.ACTION: self.REQUEST,
            self.REQUEST: self.KBAR,
            "size": 5,
            self.KBAR: kbar,
            "pair": self.pair,
        }
        await self._send_message(message)

    async def update_subscribed_order(self) -> None:
        """Update subscribed order details."""
        self.log.info("Updating subscribed order details")
        if self.subscribeKey is None:
            self.log.info("Subscribe key not found, retrieving new key")
            await self.get_subscribe_key()
        else:
            self.log.info("Extending subscribe key validity")
            await self.extend_subscribe_key_validity()
        message = {
            self.ACTION: self.SUBSCRIBE,
            self.SUBSCRIBE: "orderUpdate",
            "subscribeKey": self.subscribeKey,
            "pair": "all",
        }
        await self._send_message(message)

    async def update_subscribed_asset(self) -> None:
        """Update subscribed asset details."""
        self.log.info("Updating subscribed asset details")
        if self.subscribeKey is None:
            self.log.info("Subscribe key not found, retrieving new key")
            await self.get_subscribe_key()
        else:
            self.log.info("Extending subscribe key validity")
            await self.extend_subscribe_key_validity()
        message = {
            self.ACTION: self.SUBSCRIBE,
            self.SUBSCRIBE: "assetUpdate",
            "subscribeKey": self.subscribeKey,
        }
        await self._send_message(message)

    async def get_subscribe_key(self) -> None:
        """Retrieve the subscription key from the LBank API."""
        self.log.info("Retrieving subscribe key from LBank API")
        url = "https://api.lbank.info/v2/subscribe/get_key.do"

        ts = await self.DataClient.get_timestamp()
        ts1 = ts['data']
        ts2 = str(int(time.time() * 1000))
        diff = str(int(ts1)-int(ts2))
        # self.log.debug('timestamp from DataClient:', data=ts1)
        # self.log.debug('my own time stamp:', data=ts2)
        self.log.debug('difference:', data=diff)
        api_notice = await self.DataClient.get_api_Restrictions()
        if api_notice.get('result') == 'true':
            self.log.debug('api notice:', data=api_notice)
        else:
            self.log.warning('api notice:', data=api_notice)
        # TODO:--------------------------------------------------------------------------------------------------------------

        params = {"api_key": self.api_key, "timestamp": ts1}

        self.log.debug("Params before generating signature", params=params)
        params["sign"] = self._create_signature(params, self.api_secret)
        self.log.debug("Params after generating signature", params=params)

        async with httpx.AsyncClient() as client:
            self.log.debug("Sending request to get subscribe key", url=url, params=params)
            try:
                data = json.dumps(params)
                response = await client.post(url, data=data)
            except Exception as e:
                self.log.error('error in get_subscribe_key', exc_info=e)
            self.log.debug("Received response for subscribe key request", status_code=response.status_code,
                           response=response.text)
            if response.status_code == 200:
                data = response.json()
                if data["result"] == "true":
                    self.subscribeKey = data["subscribeKey"]
                    self.log.info("Successfully retrieved subscribe key", subscribeKey=self.subscribeKey)
                else:
                    self.log.error("Failed to retrieve subscribe key", error=data["error"])
            else:
                self.log.error("HTTP request failed", status_code=response.status_code, response=response.text)

    async def extend_subscribe_key_validity(self) -> None:
        """Extend the validity of the subscribeKey."""
        self.log.info("Extending subscribe key validity")
        url = "https://api.lbank.info/v2/subscribe/refresh_key.do"
        params = {
            "api_key": self.api_key,
            "timestamp": int(time.time() * 1000),
            "subscribeKey": self.subscribeKey,
        }
        params["sign"] = self._create_signature(params, self.api_secret)

        async with httpx.AsyncClient() as client:
            self.log.debug("Sending request to extend subscribe key validity", url=url, params=params)
            response = await client.post(url, data=params)
            self.log.debug("Received response for extend subscribe key request", status_code=response.status_code,
                           response=response.text)
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "true":
                    self.log.info("Successfully extended subscribe key validity", subscribeKey=self.subscribeKey)
                else:
                    self.log.error("Failed to extend subscribe key validity", error=data.get("error"))
                    self.log.info("Trying to get a new subscribe key")
                    await self.get_subscribe_key()
            else:
                self.log.error("HTTP request failed", status_code=response.status_code, response=response.text)

    async def delete_subscribe_key(self) -> bool:
        """Delete the current subscribeKey.

        Returns:
            bool: True if the subscribe key was successfully deleted, False otherwise.
        """
        self.log.info("Deleting subscribe key")
        url = "https://api.lbank.info/v2/subscribe/destroy_key.do"
        params = {
            "api_key": self.api_key,
            "timestamp": int(time.time() * 1000),
            "subscribeKey": self.subscribeKey,
        }
        params["sign"] = self._create_signature(params, self.api_secret)

        async with httpx.AsyncClient() as client:
            self.log.debug("Sending request to delete subscribe key", url=url, params=params)
            response = await client.post(url, data=params)
            self.log.debug("Received response for delete subscribe key request", status_code=response.status_code,
                           response=response.text)
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "true":
                    self.subscribeKey = None  # Clear the subscribeKey
                    self.log.info("Successfully deleted subscribe key")
                    return True
                else:
                    self.log.error("Failed to delete subscribe key", error=data.get("error"))
                    return False
            else:
                self.log.error("HTTP request failed", status_code=response.status_code, response=response.text)
                return False

    def _create_signature(self, params: dict, secret_key: str) -> str:
        """Create a signature for a given set of parameters using a secret key.

        Args:
            params (dict): Parameters to sign.
            secret_key (str): Secret key used for signing.

        Returns:
            str: Generated HMAC signature.
        """
        self.log.debug("Creating HMAC signature", params=params)
        query_string = "&".join([f"{key}={value}" for key, value in sorted(params.items())])
        signature = hmac.new(secret_key.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        self.log.debug("Generated HMAC signature", signature=signature)
        return signature

    def get_latest_price(self) -> Optional[float]:
        """Get the latest price.

        Returns:
            Optional[float]: Latest market price.
        """
        self.log.debug("Getting latest price", latest_price=self.latest_price)
        return self.latest_price

    def get_daily_open(self) -> Optional[float]:
        """Get the daily open price.

        Returns:
            Optional[float]: Daily open price.
        """
        self.log.debug("Getting daily open price", daily_open=self.daily_open)
        return self.daily_open


async def main() -> None:
    """Main function to initiate the WebSocket client."""
    uri = os.getenv("WEBSOCKET_URI", "wss://your.websocket.server")  # Load WebSocket URI from environment variables
    api_key = os.getenv("LBANK_API_KEY")  # Load LBank API key from environment variables
    api_secret = os.getenv("LBANK_API_SECRET")  # Load LBank API secret from environment variables

    if not api_key or not api_secret:
        raise ValueError("API key and secret must be set as environment variables")

    client = KBarWebSocketClient(uri, api_key, api_secret)
    await client.get_subscribe_key()
    await client.connect()


if __name__ == "__main__":
    asyncio.run(main())
