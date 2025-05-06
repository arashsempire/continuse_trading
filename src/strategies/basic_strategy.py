# from api.lbank_api import LBankAPI


class BasicTradingStrategy:
    def __init__(self, lbank_api, buy_threshold, sell_threshold):
        self.lbank_api = lbank_api
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def execute(self, symbol):
        # Fetch account info or market data (mocked here for simplicity)
        market_price = self.get_market_price(symbol)

        if market_price < self.buy_threshold:
            print(f"Buying {symbol} at {market_price}")
            self.lbank_api.place_order(symbol, "buy", str(market_price), "0.01")
        elif market_price > self.sell_threshold:
            print(f"Selling {symbol} at {market_price}")
            self.lbank_api.place_order(symbol, "sell", str(market_price), "0.01")

    def get_market_price(self, symbol):
        # Mocked market price; replace with actual API call to fetch price
        return 29000  # Example price
