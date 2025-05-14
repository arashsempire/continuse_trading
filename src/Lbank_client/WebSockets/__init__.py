# __init__.py (inside your websocket client package, e.g., lbank_client/websocket/)

# Expose the primary client orchestrator
from .WSClient import WebSocketClient

# Expose the LBank-specific message processor and its base if needed externally
from .WSMessage_Processor import MessageProcessor, WSMessageProcessor

# Expose other key components if they are meant to be part of the public API of this package
from .WSConnection import WSConnectionManager
from .WSSubscription import SubscriptionManager, SubscriptionError


# Define what gets imported with "from <package> import *"
__all__ = [
    "WebSocketClient",
    "MessageProcessor",  # LBank-specific
    "WSMessageProcessor",  # Generic base
    "WSConnectionManager",
    "SubscriptionManager",
    "SubscriptionError",
]
