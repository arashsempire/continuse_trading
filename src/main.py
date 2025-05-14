from strategies import Strategy
# from API import WebSocketClient
from Lbank_client import LBankAPI
from utils import configure_logging
import time
import asyncio
import logging
import structlog
import inspect

# configure_logging(logging.WARNING)
# configure_logging(lvl=logging.INFO)
configure_logging(lvl=logging.DEBUG)


# async def main():
#     good1 = Strategy()
#     for i in range(10):
#         log.debug(f'{i}-long........-{inspect.currentframe().f_code.co_name}')
#         await good1.long_trades()
#         time.sleep(1)
#         await good1.short_trades()
#         log.debug(f'{i}-short........')


async def main():



if __name__ == "__main__":
    # logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    # logger = logging.getLogger(__name__)
    log = structlog.get_logger().bind(module='main')
    asyncio.run(main())

# import asyncio
# from API import LBankAPI


# async def main():
#     # Initialize the LBank API
#     lbank_api = LBankAPI()

#     # Test getting account information
#     try:
#         account_info = await lbank_api.get_account_info()
#         print("Account Info:", account_info)
#     except Exception as e:
#         print("Error fetching account info:", e)

#     # # Test placing an order (use realistic values for your account)
#     # try:
#     #     symbol = "btc_usdt"  # Example trading pair
#     #     order_type = "buy"  # "buy" or "sell"
#     #     price = "30000"  # Example price
#     #     amount = "0.01"  # Example amount
#     #     order_response = await lbank_api.place_order(symbol, order_type, price,
#     # amount)
#     #     print("Order Response:", order_response)
#     # except Exception as e:
#     #     print("Error placing order:", e)

#     await lbank_api.close()


# if __name__ == "__main__":
#     asyncio.run(main())
