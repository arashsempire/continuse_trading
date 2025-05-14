import pandas as pd
from typing import Callable, Optional, Dict, Any, Awaitable
from .logger import BaseLogger


class WSMessageProcessor(BaseLogger):
    """
    Generic WebSocket message dispatcher.
    Handlers are expected to be async.
    """

    def __init__(self):
        super().__init__()
        self.handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self.log.info(f"{self.__class__.__name__} initialized.")

    def register_handler(
        self, message_type: str, handler: Callable[[dict], Awaitable[None]]
    ):
        """Register an async handler function for a given message type."""
        self.handlers[message_type] = handler
        self.log.debug(f"Handler registered for message type: {message_type}")

    async def process_data_message(self, message: dict):
        """Process a data message by dispatching to the appropriate handler based on 'type'."""
        message_type = message.get("type")
        if not message_type:
            self.log.warning(
                "Data message missing 'type' field.", message_details=message
            )
            return

        handler = self.handlers.get(message_type)
        if handler:
            try:
                self.log.debug(f"Dispatching message type '{message_type}' to handler.")
                await handler(message)
            except Exception as e:
                self.log.error(
                    f"Error while processing data message type '{message_type}'.",
                    error=str(e),
                    message_details=message,
                )
        else:
            self.log.warning(
                f"No handler registered for data message type: '{message_type}'.",
                message_details=message,
            )


class MessageProcessor(WSMessageProcessor):
    """
    Processes incoming WebSocket messages specifically for LBank.
    It parses messages and invokes callbacks provided by a higher-level component (e.g., ClientManager)
    to handle the parsed data, such as updating a state cache.
    """

    def __init__(
        self,
        on_kbar_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_order_update_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_asset_update_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_historical_kbar_callback: Optional[
            Callable[[pd.DataFrame], Awaitable[None]]
        ] = None,
    ):
        super().__init__()
        self.on_kbar_callback = on_kbar_callback
        self.on_order_update_callback = on_order_update_callback
        self.on_asset_update_callback = on_asset_update_callback
        self.on_historical_kbar_callback = on_historical_kbar_callback

        # Register internal handlers for LBank specific 'type' fields in data messages
        # These internal handlers will then call the external callbacks.
        if self.on_kbar_callback:
            self.register_handler("kbar", self._handle_kbar_data)
        if self.on_order_update_callback:
            self.register_handler("orderUpdate", self._handle_order_update_data)
        if self.on_asset_update_callback:
            # Assuming 'assetUpdate' is a type. If it comes differently, adjust.
            # LBank's documentation might specify a different 'type' for asset updates,
            # or it might always be part of a general authenticated message structure.
            # For now, we assume it can appear as a 'type'.
            self.register_handler("assetUpdate", self._handle_asset_update_data)

        self.log.info("LBank MessageProcessor initialized with callbacks.")

    async def _handle_kbar_data(self, message: dict):
        """Internal handler for 'kbar' type messages."""
        kbar_data = message.get("kbar")
        pair = message.get("pair")
        if isinstance(kbar_data, dict) and pair:
            self.log.info(f"Parsed KBar data for {pair}.", data=kbar_data)
            if self.on_kbar_callback:
                # Construct a more structured data object if needed
                await self.on_kbar_callback({"pair": pair, **kbar_data})
        else:
            self.log.warning(
                "Received kbar message with unexpected data format.",
                message_details=message,
            )

    async def _handle_order_update_data(self, message: dict):
        """Internal handler for 'orderUpdate' type messages."""
        order_data = message.get("orderUpdate")
        pair = message.get("pair")
        if isinstance(
            order_data, dict
        ):  # LBank might send a list of orders or a single one
            self.log.info(
                f"Parsed Order Update data for {pair or 'N/A'}.", data=order_data
            )
            if self.on_order_update_callback:
                await self.on_order_update_callback({"pair": pair, **order_data})
        else:
            self.log.warning(
                "Received orderUpdate message with unexpected data format.",
                message_details=message,
            )

    async def _handle_asset_update_data(self, message: dict):
        """Internal handler for 'assetUpdate' type messages."""
        # Asset updates might not have a 'pair' field or a standard 'type' like kbar.
        # This depends heavily on LBank's specific asset update message structure.
        asset_data = message.get(
            "assetUpdate"
        )  # Or message.get("data") or message itself
        if asset_data:  # Could be a dict or list
            self.log.info("Parsed Asset Update data.", data=asset_data)
            if self.on_asset_update_callback:
                await self.on_asset_update_callback(
                    asset_data
                )  # Pass the relevant part
        else:
            self.log.warning(
                "Received assetUpdate message with unexpected data format.",
                message_details=message,
            )

    async def process_incoming_message(self, message: Dict[str, Any]) -> None:
        """
        Processes a single incoming WebSocket message from LBank.
        It distinguishes between status, action, request responses, and data messages.
        """
        self.log.debug("Processing incoming LBank message.", raw_data=message)

        if "status" in message:  # Error or success status messages
            self._handle_status_message(message)
        elif "action" in message:  # Ping/pong or other actions
            self._handle_action_message(message)
        elif (
            "request" in message and "records" in message
        ):  # Response to a "request" action
            await self._handle_request_response(message)
        elif "type" in message:  # Regular data update message (kbar, orderUpdate, etc.)
            await self.process_data_message(message)
        else:
            self.log.warning(
                "Unhandled LBank message structure.", message_details=message
            )

    def _handle_status_message(self, message: dict):
        """Handle status messages (e.g., errors, confirmations)."""
        status = message.get("status")
        if str(status).lower() == "error":
            error_details = message.get("error", "Unknown error")
            self.log.error(
                "WebSocket Error Status Received from LBank.",
                details=error_details,
                full_message=message,
            )
        else:
            self.log.info(
                "WebSocket Status Message Received from LBank.",
                status=status,
                details=message,
            )

    def _handle_action_message(self, message: dict):
        """Handle action messages (e.g., ping/pong)."""
        action = message.get("action")
        if action == "ping":
            self.log.info("Ping received from LBank.", data=message)
            # Pong should be sent by WSConnectionManager or WebSocketClient if required by LBank
        elif action == "pong":
            self.log.info("Pong received from LBank.", data=message)
        else:
            self.log.info(
                "WebSocket Action Message Received from LBank.",
                action=action,
                details=message,
            )

    async def _handle_request_response(self, message: dict):
        """Handle responses to specific 'request' actions, e.g., historical kbar."""
        request_type = message.get("request")
        if request_type == "kbar":
            await self._handle_kbar_request_response(message)
        else:
            self.log.info(
                "Request Response Received from LBank.",
                request_type=request_type,
                details=message,
            )

    async def _handle_kbar_request_response(self, message: dict):
        """Process 'kbar' request responses containing historical data."""
        if "records" in message and "columns" in message:
            try:
                df = pd.DataFrame(message["records"], columns=message["columns"])
                if not df.empty:
                    self.log.info(
                        f"Processed historical kbar data for pair: {message.get('pair', 'N/A')}. "
                        f"Shape: {df.shape}"
                    )
                    self.log.debug(
                        "Kbar DataFrame from request", df_head=df.head().to_string()
                    )
                    if self.on_historical_kbar_callback:
                        await self.on_historical_kbar_callback(df)  # Pass the DataFrame
                else:
                    self.log.warning(
                        "Historical kbar request response was empty.",
                        message_details=message,
                    )
            except (ValueError, TypeError, IndexError) as e:
                self.log.error(
                    "Error processing kbar request response DataFrame.",
                    error=str(e),
                    message_details=message,
                )
            except Exception as e:  # Catch any other unexpected errors
                self.log.exception(
                    "Unexpected error processing kbar request response.",
                    error=str(e),
                    message_details=message,
                )
        else:
            self.log.error(
                "Invalid 'kbar' request response format from LBank.",
                message_details=message,
            )
