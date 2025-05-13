import pandas as pd
from typing import Callable, Optional, Dict, Any
from ...utils import BaseLogger


class WSMessageProcessor(BaseLogger):
    """Generic WebSocket message dispatcher."""

    def __init__(self):
        super().__init__()
        self.handlers: Dict[str, Callable[[dict], Any]] = {}

    def register_handler(self, message_type: str, handler: Callable[[dict], Any]):
        """Register a handler function for a given message type."""
        self.handlers[message_type] = handler
        self.log.debug("Handler registered.", message_type=message_type)

    async def process(self, message: dict):
        """Process a message by dispatching to the appropriate handler."""
        message_type = message.get("type")
        if not message_type:
            self.log.warning("Message missing 'type' field.", message=message)
            return

        handler = self.handlers.get(message_type)
        if handler:
            try:
                await handler(message)
            except Exception as e:
                self.log.error(
                    "Error while processing message.", type=message_type, error=str(e)
                )
        else:
            self.log.warning(
                "Unhandled message type.", type=message_type, message=message
            )


class MessageProcessor(WSMessageProcessor):
    """Processes incoming WebSocket messages from LBank."""

    def __init__(self):
        super().__init__()
        self.latest_price: Optional[float] = None
        self.daily_open: Optional[float] = None
        self.daily_open_ts: Optional[int] = None

        # Register handlers for LBank-specific message types
        self.register_handler("kbar", self.handle_kbar)
        self.register_handler("orderUpdate", self.handle_order_update)
        self.register_handler("assetUpdate", self.handle_asset_update)

    async def handle_kbar(self, data: dict):
        """Handle 'kbar' messages."""
        kbar_data = data.get("kbar")
        if isinstance(kbar_data, dict):
            self.latest_price = kbar_data.get("c")  # Close price
            pair = data.get("pair", "N/A")
            self.log.info("KBar Update Received", pair=pair, price=self.latest_price)
            self.log.debug("KBar Data", kbar_details=kbar_data)
        else:
            self.log.warning(
                "Received kbar message with unexpected data format", data=data
            )

    async def handle_order_update(self, data: dict):
        """Handle 'orderUpdate' messages."""
        order_data = data.get("orderUpdate")
        pair = data.get("pair", "N/A")
        self.log.info("Order Update Received", pair=pair, details=order_data)

    async def handle_asset_update(self, data: dict):
        """Handle 'assetUpdate' messages."""
        asset_data = data.get("assetUpdate")
        self.log.info("Asset Update Received", details=asset_data)

    async def process_incoming_message(self, data: Dict[str, Any]) -> None:
        """Processes a single incoming WebSocket message."""
        self.log.debug("Processing incoming message", raw_data=data)

        message_status = data.get("status")
        message_action = data.get("action")
        request_type = data.get("request")

        if message_status:
            self.handle_status_message(data)
        elif message_action:
            self.handle_action_message(data)
        elif request_type:
            await self.handle_request_response(data)
        else:
            await self.process(data)

    def handle_status_message(self, data: dict):
        """Handle status messages (e.g., errors, confirmations)."""
        message_status = data.get("status")
        if str(message_status).lower() == "error":
            error_details = data.get("error", "Unknown error")
            self.log.error(
                "WebSocket Error Status Received",
                details=error_details,
                full_message=data,
            )
        else:
            self.log.info(
                "WebSocket Status Message Received", status=message_status, details=data
            )

    def handle_action_message(self, data: dict):
        """Handle action messages (e.g., ping/pong)."""
        message_action = data.get("action")
        if message_action == "ping":
            self.log.info("Ping received", data=data)
        elif message_action == "pong":
            self.log.info("Pong received", data=data)
        else:
            self.log.info(
                "WebSocket Action Message Received", action=message_action, details=data
            )

    async def handle_request_response(self, data: dict):
        """Handle responses to specific requests."""
        request_type = data.get("request")
        if request_type == "kbar":
            self.handle_kbar_request_response(data)
        else:
            self.log.info(
                "Request Response Received", request_type=request_type, details=data
            )

    def handle_kbar_request_response(self, data: dict):
        """Process 'kbar' request responses."""
        if "records" in data and "columns" in data:
            try:
                df = pd.DataFrame(data["records"], columns=data["columns"])
                if not df.empty and "timestamp" in df.columns and "close" in df.columns:
                    last_candle = df.iloc[-1]
                    self.daily_open = float(last_candle["close"])
                    self.daily_open_ts = int(last_candle["timestamp"])
                    self.log.info(
                        "Daily 'open' price and timestamp updated",
                        daily_open=self.daily_open,
                        daily_open_ts=self.daily_open_ts,
                    )
                    self.log.debug(
                        "Kbar DataFrame from request", df_repr=df.to_string()
                    )
                else:
                    self.log.warning(
                        "Kbar request response missing data or columns", data=data
                    )
            except (ValueError, TypeError, IndexError) as e:
                self.log.error(
                    "Error processing kbar request response DataFrame",
                    error=str(e),
                    data=data,
                )
            except Exception as e:
                self.log.exception(
                    f"Unexpected error {e} processing kbar request response", data=data
                )
        else:
            self.log.error("Invalid 'kbar' request response format", data=data)
