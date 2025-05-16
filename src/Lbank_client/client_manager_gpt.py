import asyncio

# from typing import Optional

from app_utility import load_config, StateCache
from rest_client import LBankAPI
from ws_handler import WSConnectionManager, LBankMessageProcessor, SubscriptionManager
from app_utility import (
    API_KEY_ENV,
    API_SECRET_ENV,
    REST_BASE_URL_ENV,
    WEBSOCKET_URI_ENV,
)


class ClientManager:
    """
    A high-level manager that coordinates WebSocket and REST clients,
    message processing, and shared state cache for the LBank client.
    """

    def __init__(self):
        self.config = load_config()

        self.api_key = self.config.get(API_KEY_ENV)
        self.api_secret = self.config.get(API_SECRET_ENV)
        self.rest_base_url = self.config.get(REST_BASE_URL_ENV)
        self.ws_uri = self.config.get(WEBSOCKET_URI_ENV)

        self.cache = StateCache()
        self.rest_client = LBankAPI(
            api_key=self.api_key,
            api_secret=self.api_secret,
            base_url=self.rest_base_url,
        )
        self.ws_connection_manager = WSConnectionManager(uri=self.ws_uri)
        self.subscription_manager = SubscriptionManager(
            api_key=self.api_key,
            api_secret=self.api_secret,
            config=self.config,
            ws_connection_manager=self.ws_connection_manager,
        )

        # Message processor with shared state update callbacks
        self.ws_processor = LBankMessageProcessor(
            on_kbar_callback=self._on_kbar,
            on_order_update_callback=self._on_order_update,
            on_asset_update_callback=self._on_asset_update,
        )

    async def start(self):
        """Starts the WebSocket listener and subscription key fetch."""
        await self.subscription_manager.get_ws_subscribe_key()
        await self.ws_connection_manager.connect()
        asyncio.create_task(
            self.ws_connection_manager.listen(
                self.ws_processor.process_incoming_message
            )
        )

    async def stop(self):
        """Stops the WebSocket connection and cleans up."""
        await self.ws_connection_manager.stop()
        await self.subscription_manager.delete_ws_subscribe_key()
        await self.rest_client.close_client()

    # ==== Internal callbacks ====
    async def _on_kbar(self, message: dict):
        pair = message.get("pair")
        kbar = message.get("kbar")
        if pair and kbar:
            await self.cache.update_kbar(pair, kbar)

    async def _on_order_update(self, order_data: dict):
        order_id = order_data.get("uuid")
        if order_id:
            if order_data.get("status") in ("closed", "cancelled", "filled"):
                await self.cache.close_order(order_id)
            else:
                await self.cache.update_order(order_id, order_data)

    async def _on_asset_update(self, asset_list: list):
        updates = {}
        for asset in asset_list:
            code = asset.get("assetCode")
            if code:
                updates[code.upper()] = {
                    "free": asset.get("available", "0"),
                    "frozen": asset.get("freeze", "0"),
                }
        await self.cache.update_balances(updates)

    # ==== Public access methods ====
    async def get_balances(self):
        return await self.cache.get_balances()

    async def get_orders(self):
        return await self.cache.get_orders()

    async def get_kbars(self, symbol: str):
        return await self.cache.get_kbars(symbol)

    async def place_order(self, **kwargs):
        return await self.rest_client.place_order(**kwargs)

    async def get_latest_price(self, symbol: str):
        return await self.rest_client.get_latest_price(symbol)


# Example usage
if __name__ == "__main__":

    async def main():
        manager = ClientManager()
        await manager.start()

        # Do stuff...
        await asyncio.sleep(60)  # Run for 1 minute

        await manager.stop()

    asyncio.run(main())
