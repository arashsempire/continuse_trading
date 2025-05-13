import os
from dotenv import load_dotenv


def load_keys():
    load_dotenv()

    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")
    BASE_URL = os.getenv("BASE_URL")
    WEBSOCKET_URI = os.getenv("WEBSOCKET_URI")

    return {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "base_url": BASE_URL,
        "websocket_uri": WEBSOCKET_URI,
    }
