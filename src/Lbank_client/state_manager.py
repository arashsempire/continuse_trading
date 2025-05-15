import asyncio
from typing import Dict, Any, List


class StateCache:
    """
    Manages in-memory state for balances, open orders, and kline data.
    Uses asyncio.Lock to ensure thread-safe access for async operations.
    """

    def __init__(self):
        self._balances: Dict[str, Any] = {}  # {coin: {free: ..., freeze: ...}}
        self._orders: Dict[str, Any] = {}  # {order_id: {order_details}}
        self._kbars: Dict[str, List[Dict[str, Any]]] = {}  # {symbol: [{kbar_data}]}
        self._lock = asyncio.Lock()  # Ensure thread-safe updates

    async def update_balance(self, coin: str, free: str, freeze: str):
        """Update or add a single balance."""
        async with self._lock:
            self._balances[coin] = {"free": free, "freeze": freeze}

    async def update_order(self, order_id: str, order_details: Dict[str, Any]):
        """Update or add a single order."""
        async with self._lock:
            self._orders[order_id] = order_details

    async def remove_order(self, order_id: str):
        """Remove an order by ID."""
        async with self._lock:
            self._orders.pop(order_id, None)

    async def set_balances(self, full_snapshot: Dict[str, Any]):
        """Set a full snapshot of balances."""
        async with self._lock:
            self._balances = full_snapshot

    async def set_orders(self, full_snapshot: Dict[str, Any]):
        """Set a full snapshot of orders."""
        async with self._lock:
            self._orders = full_snapshot

    async def get_balances(self) -> Dict[str, Any]:
        """Retrieve a copy of current balances."""
        async with self._lock:
            return self._balances.copy()

    async def get_orders(self) -> Dict[str, Any]:
        """Retrieve a copy of current open orders."""
        async with self._lock:
            return self._orders.copy()

    async def update_kbar(self, symbol: str, kbar_data: dict):
        """Append or update kbar data for a symbol."""
        async with self._lock:
            if symbol not in self._kbars:
                self._kbars[symbol] = []
            self._kbars[symbol].append(kbar_data)

    async def get_kbars(self, symbol: str) -> List[Dict[str, Any]]:
        """Retrieve kbar data for a specific symbol."""
        async with self._lock:
            return list(self._kbars.get(symbol, []))

    async def set_kbars(self, symbol: str, kbars: list):
        """Set a full kbar list for a symbol."""
        async with self._lock:
            self._kbars[symbol] = kbars
