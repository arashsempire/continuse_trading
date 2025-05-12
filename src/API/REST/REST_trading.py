from .REST_utils import LBankAuthUtils
from typing import Dict, Any


class TradingClient(LBankAuthUtils):
    """
    Provides methods for placing and managing orders on the LBank API.
    """

    async def place_order(
        self,
        symbol: str,
        _type: str,
        price: float,
        amount: float,
        custom_id: str = None,
        window: str = None
    ) -> Dict[str, Any]:
        """
        Place an order in the market.

        Args:
            symbol (str): Trading pair symbol.
            _type (str): Order type (e.g., 'buy', 'sell').
            price (float): Order price.
            amount (float): Order amount.
            custom_id (str, optional): Custom order ID. Defaults to None.
            window (str, optional): Time window for the order. Defaults to None.

        Returns:
            Dict[str, Any]: Order placement response.
        """
        self.log.info("Placing order", symbol=symbol, _type=_type, price=price, amount=amount)
        params = {
            "symbol": symbol,
            "type": _type,
            "price": price,
            "amount": amount,
        }
        if custom_id:
            params["custom_id"] = custom_id
        if window:
            params["window"] = window
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/create_order.do", signed_params)

    async def cancel_order(self, symbol: str, order_id: str, origClientOrderId: str) -> Dict[str, Any]:
        """
        Cancel an existing order.

        Args:
            symbol (str): Trading pair symbol.
            order_id (str): Order ID to cancel.
            origClientOrderId (str): Original client order ID.

        Returns:
            Dict[str, Any]: Order cancellation response.
        """
        self.log.info("Cancelling order", symbol=symbol, order_id=order_id)
        params = {
            "symbol": symbol,
            "order_id": order_id,
            "origClientOrderId": origClientOrderId
        }
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/cancel_order.do", signed_params)

    async def get_order_info(self, symbol: str, order_id: str, origClientOrderId: str) -> Dict[str, Any]:
        """
        Retrieve information about a specific order.

        Args:
            symbol (str): Trading pair symbol.
            order_id (str): Order ID.
            origClientOrderId (str): Original client order ID.

        Returns:
            Dict[str, Any]: Order information.
        """
        self.log.debug("Fetching order info", symbol=symbol, order_id=order_id)
        params = {
            "symbol": symbol,
            "order_id": order_id,
            "origClientOrderId": origClientOrderId
        }
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/orders_info.do", signed_params)

    async def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """
        Cancel all the orders of a single trading pair.

        Args:
            symbol (str): Trading pair symbol.

        Returns:
            Dict[str, Any]: Order cancellation response.
        """
        self.log.info("Cancelling all orders", symbol=symbol)
        params = {"symbol": symbol}
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/cancel_order_by_symbol.do", signed_params)

    async def place_test_order(
        self,
        symbol: str,
        _type: str,
        price: float,
        amount: float,
        custom_id: str = None,
        window: str = None
    ) -> Dict[str, Any]:
        """Place a test order."""
        params = {
            "symbol": symbol,
            "type": _type,
            "price": price,
            "amount": amount,
        }
        if custom_id:
            params["custom_id"] = custom_id
        if window:
            params["window"] = window
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/create_order_test.do", signed_params)

    async def get_all_pending_orders_info(
        self,
        symbol: str,
        current_page: int = 1,
        page_length: int = 20
    ) -> Dict[str, Any]:
        """Get all pending orders information."""
        params = {
            "symbol": symbol,
            "current_page": current_page,
            "page_length": page_length
        }
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/orders_info_no_deal.do", signed_params)
