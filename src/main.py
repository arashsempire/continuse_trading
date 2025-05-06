from api.lbank_api import LBankAPI


def main():
    # Initialize the LBank API
    lbank_api = LBankAPI()

    # Test getting account information
    try:
        account_info = lbank_api.get_account_info()
        print("Account Info:", account_info)
    except Exception as e:
        print("Error fetching account info:", e)

    # Test placing an order (use realistic values for your account)
    try:
        symbol = "btc_usdt"  # Example trading pair
        order_type = "buy"  # "buy" or "sell"
        price = "30000"  # Example price
        amount = "0.01"  # Example amount
        order_response = lbank_api.place_order(symbol, order_type, price, amount)
        print("Order Response:", order_response)
    except Exception as e:
        print("Error placing order:", e)


if __name__ == "__main__":
    main()
