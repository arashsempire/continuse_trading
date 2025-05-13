import time
import httpx
from typing import Optional
from API.WebSockets.WSSignature import SignatureManager
from utils import BaseLogger
import json


class SubscriptionManager(BaseLogger):
    def __init__(self, api_key: str, api_secret: str, pair: str):
        super().__init__()
        self.log = self.log.bind(class_name="SubscriptionManager")
        self.api_key = api_key
        self.api_secret = api_secret
        self.pair = pair
        self.subscribeKey: Optional[str] = None

    async def subscribe_kbar(self, connection, kbar: str = "1min") -> None:
        self.log.info(f"Subscribing for {kbar} kbar data")
        message = {
            "action": "subscribe",
            "subscribe": "kbar",
            "kbar": kbar,
            "pair": self.pair,
        }
        await self.send_message(connection, message)

    async def request_kbar(self, connection, kbar: str = "day") -> None:
        self.log.info("Requesting for daily kbar candles")
        message = {
            "action": "request",
            "request": "kbar",
            "size": 5,
            "kbar": kbar,
            "pair": self.pair,
        }
        await self.send_message(connection, message)

    async def update_subscribed_order(self, connection) -> None:
        self.log.info("Subscribing for order updates")
        if self.subscribeKey is None:
            if not await self.get_subscribe_key():
                return
        else:
            if not await self.extend_subscribe_key_validity():
                return
        message = {
            "action": "subscribe",
            "subscribe": "orderUpdate",
            "subscribeKey": self.subscribeKey,
            "pair": "all",
        }
        await self.send_message(connection, message)

    async def update_subscribed_asset(self, connection) -> None:
        self.log.info("Subscribing for asset updates")
        if self.subscribeKey is None:
            if not await self.get_subscribe_key():
                return
        else:
            if not await self.extend_subscribe_key_validity():
                return
        message = {
            "action": "subscribe",
            "subscribe": "assetUpdate",
            "subscribeKey": self.subscribeKey,
        }
        await self.send_message(connection, message)

    async def get_subscribe_key(self) -> bool:
        self.log.info("Getting subscription key")
        url = "https://api.lbank.info/v2/subscribe/get_key.do"
        params = {"api_key": self.api_key, "timestamp": int(time.time() * 1000)}
        params["sign"] = SignatureManager.create_signature(params, self.api_secret)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                self.log.info("Received response from server", response=data)
                if data.get("result") == "true":
                    self.subscribeKey = data["subscribeKey"]
                    self.log.info("Successfully retrieved subscribe key", subscribeKey=self.subscribeKey)
                    return True
                else:
                    self.log.error("Failed to retrieve subscribe key", error=data.get("error"), response=data)
                    return False
            except httpx.RequestError as exc:
                self.log.error(f"An error occurred while requesting {exc.request.url!r}.", error=str(exc))
                return False
            except httpx.HTTPStatusError as exc:
                self.log.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.",
                               error=str(exc))
                return False
            except Exception as e:
                self.log.error("An unexpected error occurred", error=str(e))
                return False

    async def extend_subscribe_key_validity(self) -> bool:
        self.log.info("Checking subscription key validity")
        url = "https://api.lbank.info/v2/subscribe/refresh_key.do"
        params = {"api_key": self.api_key, "timestamp": int(time.time() * 1000), "subscribeKey": self.subscribeKey}
        params["sign"] = SignatureManager.create_signature(params, self.api_secret)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                self.log.info("Received response from server", response=data)
                if data.get("result") == "true":
                    self.log.info("Successfully extended subscribe key validity", subscribeKey=self.subscribeKey)
                    return True
                else:
                    self.log.error("Failed to extend subscribe key validity", error=data.get("error"), response=data)
                    self.log.info("Trying to get a new one")
                    return await self.get_subscribe_key()
            except httpx.RequestError as exc:
                self.log.error(f"An error occurred while requesting {exc.request.url!r}.", error=str(exc))
                return False
            except httpx.HTTPStatusError as exc:
                self.log.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.",
                               error=str(exc))
                return False
            except Exception as e:
                self.log.error("An unexpected error occurred", error=str(e))
                return False

    async def delete_subscribe_key(self) -> bool:
        self.log.info("Deleting subscription key")
        url = "https://api.lbank.info/v2/subscribe/destroy_key.do"
        params = {"api_key": self.api_key, "timestamp": int(time.time() * 1000), "subscribeKey": self.subscribeKey}
        params["sign"] = SignatureManager.create_signature(params, self.api_secret)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                self.log.info("Received response from server", response=data)
                if data.get("result") == "true":
                    self.subscribeKey = None
                    self.log.info("Successfully deleted subscribe key")
                    return True
                else:
                    self.log.error("Failed to delete subscribe key", error=data.get("error"), response=data)
                    return False
            except httpx.RequestError as exc:
                self.log.error(f"An error occurred while requesting {exc.request.url!r}.", error=str(exc))
                return False
            except httpx.HTTPStatusError as exc:
                self.log.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.",
                               error=str(exc))
                return False
            except Exception as e:
                self.log.error("An unexpected error occurred", error=str(e))
                return False

    async def send_message(self, connection, message: dict) -> None:
        self.log.info("Sending message", message=message)
        try:
            if connection and connection.open:
                data = json.dumps(message)
                await connection.send(data)
                self.log.info("Message sent", message=message)
            else:
                self.log.warning("Connection is not open, cannot send message")
        except Exception as e:
            self.log.error("Failed to send message", error=str(e))
