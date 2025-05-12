from .REST_utils import LBankAuthUtils
from typing import Dict, Any


class MarketDataClient(LBankAuthUtils):
    """
    Provides methods for retrieving market-related data from the LBank API.
    """

    async def get_market_depth(self, symbol: str, size: int) -> Dict[str, Any]:
        """
        Retrieve the order book depth for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol (e.g., 'btc_usdt').
            size (int): Number of orders to retrieve.

        Returns:
            Dict[str, Any]: Order book depth data.
        """
        self.log.debug("Fetching market depth", symbol=symbol, size=size)
        params = {"symbol": symbol, "size": size}
        return await self._request("GET", "depth.do", params)

    async def get_latest_price(self, symbol: str = None) -> Dict[str, Any]:
        """
        Retrieve the latest price of a specific trading pair or all pairs.

        Args:
            symbol (str, optional): Trading pair symbol. If None, retrieves prices for all pairs.

        Returns:
            Dict[str, Any]: Latest price data.
        """
        self.log.debug("Fetching latest price", symbol=symbol)
        params = {"symbol": symbol} if symbol else None
        return await self._request("GET", "supplement/ticker/price.do", params)

    async def get_24hr_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieve 24-hour ticker data for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol.

        Returns:
            Dict[str, Any]: 24-hour ticker data.
        """
        self.log.debug("Fetching 24-hour ticker", symbol=symbol)
        params = {"symbol": symbol}
        return await self._request("GET", "ticker/24hr.do", params)

    async def get_trades(self, symbol: str, size: int, _time: str = None) -> Dict[str, Any]:
        """
        Retrieve recent trades for a specific trading pair.

        Args:
            symbol (str): Trading pair symbol.
            size (int): Number of trades to retrieve.
            _time (str, optional): Timestamp for filtering trades. Defaults to None.

        Returns:
            Dict[str, Any]: Recent trades data.
        """
        self.log.debug("Fetching trades", symbol=symbol, size=size, _time=_time)
        params = {"symbol": symbol, "size": size}
        if _time:
            params["time"] = _time
        return await self._request("GET", "supplement/trades.do", params)

    async def get_kbar(self, symbol: str, size: int, _type: str, _time: str = None) -> Dict[str, Any]:
        """
        Query K Bar Data.

        Args:
            symbol (str): Trading pair symbol.
            size (int): Count of the bars (1-2000).
            _type (str): Type of the bars (e.g., 'minute1', 'hour1').
            _time (str, optional): Timestamp (of Seconds). Defaults to None.

        Returns:
            Dict[str, Any]: K Bar data.
        """
        self.log.debug("Fetching K Bar data", symbol=symbol, size=size, _type=_type, _time=_time)
        params = {"symbol": symbol, "size": size, "type": _type}
        if _time:
            params["time"] = _time
        return await self._request("GET", "kline.do", params)

    async def get_available_trading_pairs(self) -> Dict[str, Any]:
        """Get all tradeble pairs."""
        params = {}
        return await self._request("GET", "currencyPairs.do", params)

    async def get_info_trading_pairs(self) -> Dict[str, Any]:
        """Acquiring the basic information of all trading pairs"""
        params = {}
        return await self._request("GET", "accuracy.do", params)

    async def get_asset_config(self, assetCode: str) -> Dict[str, Any]:
        """Get coin information (deposit and withdrawal)"""
        params = {"assetCode": assetCode}
        return await self._request("GET", "assetConfigs.do", params)

    async def get_timestamp(self) -> Dict[str, Any]:
        """Get time stamp"""
        params = {}
        return await self._request("GET", "timestamp.do", params)

    async def get_Symbol_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Get Symbol Order Book Ticker (The current optimal pending order)"""
        params = {"symbol": symbol}
        return await self._request("GET", "supplement/ticker/bookTicker.do", params)

    async def get_24hr_leveraged_tokens_ticker(self, symbol: str) -> Dict[str, Any]:
        """GET the LBank coin quote data (Such as: btc3l_usdt、all)"""
        params = {"symbol": symbol}
        return await self._request("GET", "etfTicker/24hr.do", params)
