import asyncio

from . import RESTAccount, RESTTrading, RESTData
from . import WSClient
from ..utils import BaseLogger

from .API_utils import StateCache


class ClientManager(BaseLogger):
    """
    A unified manager for coordinating REST and WebSocket interactions.
    Maintains synchronized internal state for balances and open orders.
    Automatically handles reconnection and reconciliation to ensure reliability.
    """

    def __init__(self, api_key: str, secret_key: str):
        """
        Initializes the ClientManager with API credentials and clients.

        Args:
            api_key (str): API key for authentication.
            secret_key (str): Secret key for authentication.
        """
        super().__init__()

        # Initialize REST modules
        self.rest_account = RESTAccount(api_key, secret_key)
        self.rest_trading = RESTTrading(api_key, secret_key)
        self.rest_data = RESTData(api_key, secret_key)

        # Initialize WebSocket client
        self.ws_client = WSClient(api_key, secret_key)

        # Internal state
        self.state = StateCache()

        # Event loop tasks
        self._reconnect_task = None
        self._reconcile_task = None
        self._running = False

    async def start(self):
        """Starts the manager, initializes connections, and launches background tasks."""
        self.log.info("Starting ClientManager...")
        self._running = True
        await self._connect_and_subscribe()

        # Launch background tasks
        self._reconnect_task = asyncio.create_task(self._reconnection_watchdog())
        self._reconcile_task = asyncio.create_task(self._periodic_reconciliation())

        # Fetch initial state via REST
        await self._sync_initial_state()

    async def _connect_and_subscribe(self):
        """Connects to WebSocket and subscribes to balance and order streams."""
        try:
            await self.ws_client.connect()
            await self.ws_client.subscribe_balances(self._on_balance_update)
            await self.ws_client.subscribe_orders(self._on_order_update)
            self.log.info("WebSocket connected and subscribed.")
        except Exception as e:
            self.log.error("Failed to connect or subscribe to WebSocket.", error=str(e))

    async def _reconnection_watchdog(self):
        """Monitors WebSocket connection and reconnects if disconnected."""
        while self._running:
            if not self.ws_client.is_connected():
                self.log.warning("WebSocket disconnected. Attempting to reconnect...")
                try:
                    await self._connect_and_subscribe()
                    await self._sync_initial_state()
                    self.log.info("Reconnection and resubscription successful.")
                except Exception as e:
                    self.log.error("Reconnection failed.", error=str(e))
            await asyncio.sleep(5)

    async def _periodic_reconciliation(self):
        """Periodically validates internal state against REST snapshot."""
        while self._running:
            try:
                rest_balances = await self.rest_account.get_balances()
                rest_orders = await self.rest_trading.get_open_orders()

                current_balances = await self.state.get_balances()
                current_orders = await self.state.get_orders()

                if rest_balances != current_balances:
                    self.log.warning(
                        "Balance discrepancy detected.",
                        ws=current_balances,
                        rest=rest_balances,
                    )
                    await self.state.set_balances(rest_balances)

                if rest_orders != current_orders:
                    self.log.warning(
                        "Order discrepancy detected.",
                        ws=current_orders,
                        rest=rest_orders,
                    )
                    await self.state.set_orders(rest_orders)

                self.log.debug("Periodic reconciliation complete.")
            except Exception as e:
                self.log.error("Error during reconciliation.", error=str(e))

            await asyncio.sleep(300)  # every 5 minutes

    async def _sync_initial_state(self):
        """Fetches initial balances and open orders via REST and updates internal state."""
        balances = await self.rest_account.get_balances()
        orders = await self.rest_trading.get_open_orders()
        await self.state.set_balances(balances)
        await self.state.set_orders(orders)
        self.log.info("Initial REST snapshot fetched.", balances=balances)

    async def _on_balance_update(self, data):
        """Callback for handling balance updates from WebSocket."""
        await self.state.update_balances(data)
        balances = await self.state.get_balances()
        self.log.debug("Balance updated from WS.", balances=balances)

    async def _on_order_update(self, data):
        """Callback for handling order updates from WebSocket."""
        order_id = data.get("order_id")
        if data.get("status") == "closed":
            await self.state.close_order(order_id)
        else:
            await self.state.update_order(order_id, data)
        self.log.debug("Order updated from WS.", order=data)

    async def place_order(self, symbol, side, quantity, price=None):
        """
        Places an order using the REST API.

        Args:
            symbol (str): The trading pair (e.g., "BTC/USDT").
            side (str): Either "buy" or "sell".
            quantity (float): Amount to buy or sell.
            price (float, optional): Limit price. If None, a market order is assumed.

        Returns:
            dict: The response from the REST API.
        """
        try:
            result = await self.rest_trading.place_order(symbol, side, quantity, price)
            self.log.info("Order placed via REST.", result=result)
            return result
        except Exception as e:
            self.log.error("Failed to place order via REST.", error=str(e))
            raise

    async def stop(self):
        """Stops background tasks and disconnects WebSocket client."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._reconcile_task:
            self._reconcile_task.cancel()
        await self.ws_client.disconnect()
        self.log.info("ClientManager stopped.")
