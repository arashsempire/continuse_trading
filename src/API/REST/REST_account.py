from .REST_utils import LBankAuthUtils
from typing import Dict, Any


class AccountClient(LBankAuthUtils):
    """
    Provides methods for retrieving account information and historical data from the LBank API.
    """

    async def get_account_info(self) -> Dict[str, Any]:
        """
        Retrieve account information.

        Returns:
            Dict[str, Any]: Account details including balances.
        """
        self.log.debug("Fetching account information")
        params = {}
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/user_info_account.do", signed_params)

    async def get_transaction_history(
        self,
        symbol: str,
        startTime: str = None,
        endTime: str = None,
        fromId: str = None,
        limit: int = None
    ) -> Dict[str, Any]:
        """
        Retrieve historical transaction details.

        Args:
            symbol (str): Trading pair symbol.
            startTime (str, optional): Start time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            endTime (str, optional): End time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            fromId (str, optional): Starting transaction ID of the query. Defaults to None.
            limit (int, optional): Number of records to retrieve. Defaults to None.

        Returns:
            Dict[str, Any]: Transaction history data.
        """
        self.log.debug(
            "Fetching transaction history",
            symbol=symbol,
            startTime=startTime,
            endTime=endTime,
            fromId=fromId,
            limit=limit
        )
        params = {"symbol": symbol}
        if startTime:
            params["startTime"] = startTime
        if endTime:
            params["endTime"] = endTime
        if fromId:
            params["fromId"] = fromId
        if limit:
            params["limit"] = limit
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/transaction_history.do", signed_params)

    async def get_deposit_history(
        self, status: str, startTime: str = None, endTime: str = None, coin: str = None
    ) -> Dict[str, Any]:
        """
        Retrieve historical deposit details.

        Args:
            status (str): Deposit status filter.
            startTime (str, optional): Start time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            endTime (str, optional): End time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            coin (str, optional): Currency filter. Defaults to None.

        Returns:
            Dict[str, Any]: Deposit history data.
        """
        self.log.debug("Fetching deposit history", status=status, startTime=startTime, endTime=endTime, coin=coin)
        params = {"status": status}
        if startTime:
            params["startTime"] = startTime
        if endTime:
            params["endTime"] = endTime
        if coin:
            params["coin"] = coin
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/deposit_history.do", signed_params)

    async def get_withdraw_history(
        self, status: str, startTime: str = None, endTime: str = None, coin: str = None, withdrawOrderId: str = None
    ) -> Dict[str, Any]:
        """
        Retrieve historical withdrawal details.

        Args:
            status (str): Withdrawal status filter.
            startTime (str, optional): Start time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            endTime (str, optional): End time in 'yyyy-MM-dd HH:mm:ss' format. Defaults to None.
            coin (str, optional): Currency filter. Defaults to None.
            withdrawOrderId (str, optional): Custom withdrawal ID. Defaults to None.

        Returns:
            Dict[str, Any]: Withdrawal history data.
        """
        self.log.debug(
            "Fetching withdrawal history", status=status, startTime=startTime, endTime=endTime, coin=coin,
            withdrawOrderId=withdrawOrderId
        )
        params = {"status": status}
        if startTime:
            params["startTime"] = startTime
        if endTime:
            params["endTime"] = endTime
        if coin:
            params["coin"] = coin
        if withdrawOrderId:
            params["withdrawOrderId"] = withdrawOrderId
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/withdraws.do", signed_params)

    async def get_deposit_address(self, coin: str, networkName: str) -> Dict[str, Any]:
        """
        Retrieve deposit address.

        Args:
            coin (str): Currency.
            networkName (str): Network name.

        Returns:
            Dict[str, Any]: Deposit address data.
        """
        self.log.debug("Fetching deposit address", coin=coin, networkName=networkName)
        params = {"coin": coin}
        if networkName:
            params["networkName"] = networkName
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/get_deposit_address.do", signed_params)

    async def get_asset_detail(self, coin: str) -> Dict[str, Any]:
        """
        Retrieve asset detail.

        Args:
            coin (str): Currency.

        Returns:
            Dict[str, Any]: Asset detail data.
        """
        self.log.debug("Fetching asset detail", coin=coin)
        params = {}
        if coin:
            params["coin"] = coin
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/asset_detail.do", signed_params)

    async def get_trade_fee(self, category: str) -> Dict[str, Any]:
        """
        Retrieve customer trade fee.

        Args:
            category (str): Category.

        Returns:
            Dict[str, Any]: Trade fee data.
        """
        self.log.debug("Fetching trade fee", category=category)
        params = {}
        if category:
            params["category"] = category
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/customer_trade_fee.do", signed_params)

    async def get_trade_history_info(
        self, symbol: str, current_page: int = 1, page_length: int = 1, status: bool = True
    ) -> Dict[str, Any]:
        """Check all orders(The default query is for orders placed within 24 hours. When the status is empty,
           the default query is for cancelled and completely filled orders)"""
        params = {
            "symbol": symbol,
            "current_page": current_page,
            "page_length": page_length,
            "status": status
        }
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/orders_info_history.do", signed_params)

    async def get_usert_info(self) -> Dict[str, Any]:
        """Get user information."""
        # get all coin info / user info ?
        params = {}
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/userinfo.do", signed_params)

    async def do_withdraw(
        self, address: str, networkName: str, coin: str, amount: str, fee: float = None, memo: str = None,
        mark: str = None, name: str = None, withdrawOrderId: str = None, _type: int = None
    ) -> Dict[str, Any]:
        """Historical transaction details
        :address str: withdrawal address, when type=1, it is the transfer account
        :networkName str:  	Chain name, get it through the Get All Coin Information interface
        :coin str: currency
        :amount str: withdrawal amount
        :fee float: fee
        :memo str: 	memo: memo word of bts and dct
        :mark str: 	Withdrawal Notes
        :name str: 	Remarks of the address. After filling in this parameter,
                    it will be added to the withdrawal address book of the currency.
        :withdrawOrderId str: 	Custom withdrawal id
        :_type int: type=1 is for intra-site transfer
        """
        params = {"address": address, "networkName": networkName, "coin": coin, "amount": amount, "fee": fee}
        if memo:
            params["memo"] = memo
        if mark:
            params["mark"] = mark
        if name:
            params["name"] = name
        if withdrawOrderId:
            params["withdrawOrderId"] = withdrawOrderId
        if _type:
            params["type"] = _type
        signed_params = self._sign(params)
        return await self._request("POST", "supplement/withdraw.do", signed_params)
