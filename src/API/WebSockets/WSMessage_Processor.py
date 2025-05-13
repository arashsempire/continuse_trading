import pandas as pd
from typing import Optional, Dict, Any
from ...utils import BaseLogger


class MessageProcessor(BaseLogger):
    """Processes incoming WebSocket messages from LBank."""

    def __init__(self):
        """Initializes the message processor."""
        super().__init__()
        # No need to re-bind self.log here, BaseLogger does it.
        # self.log = self.log.bind() # This is redundant
        self.latest_price: Optional[float] = None
        self.daily_open: Optional[float] = None
        self.daily_open_ts: Optional[int] = None  # Timestamps are usually ints

    async def process_incoming_message(self, data: Dict[str, Any]) -> None:
        """
        Processes a single incoming WebSocket message.

        Args:
            data (Dict[str, Any]): The parsed JSON message received from the WebSocket.
        """
        self.log.debug(
            "Processing incoming message", raw_data=data
        )  # Log raw data only at debug

        message_status = data.get("status")
        message_action = data.get("action")
        message_type = data.get(
            "type"
        )  # For subscription updates (kbar, orderUpdate, assetUpdate)
        request_type = data.get(
            "request"
        )  # For request responses (e.g., 'kbar' request)
        subscribe_type = data.get("subscribe")  # For subscription confirmations/updates

        # --- Handle Status Messages (Errors, Success Confirmations) ---
        if message_status:
            if str(message_status).lower() == "error":
                error_details = data.get("error", "Unknown error")
                self.log.error(
                    "WebSocket Error Status Received",
                    details=error_details,
                    full_message=data,
                )
            else:
                # Could be success confirmations for subscribe/unsubscribe etc.
                self.log.info(
                    "WebSocket Status Message Received",
                    status=message_status,
                    details=data,
                )
            return  # Typically no further processing needed for status messages

        # --- Handle Action Messages (Ping/Pong) ---
        elif message_action:
            if message_action == "ping":
                self.log.info("Ping received", data=data)
                # NOTE: A robust client should respond with a pong message.
                # This is usually handled by the WSConnectionManager or WSClient.
            elif message_action == "pong":
                self.log.info("Pong received (likely response to our ping)", data=data)
            else:
                # Could be subscribe/unsubscribe confirmations if not handled by 'status'
                self.log.info(
                    "WebSocket Action Message Received",
                    action=message_action,
                    details=data,
                )
            return

        # --- Handle Subscription Data Pushes (Real-time Updates) ---
        # These messages usually have a 'type' field indicating the data stream
        elif message_type:
            if message_type == "kbar":
                kbar_data = data.get("kbar")
                if isinstance(kbar_data, dict):
                    self.latest_price = kbar_data.get("c")  # Close price
                    pair = data.get("pair", "N/A")
                    self.log.info(
                        "KBar Update Received", pair=pair, price=self.latest_price
                    )
                    self.log.debug("KBar Data", kbar_details=kbar_data)
                    # Add more processing if needed (e.g., update internal state, trigger callbacks)
                else:
                    self.log.warning(
                        "Received kbar message with unexpected data format", data=data
                    )

            elif message_type == "orderUpdate":
                # Placeholder: Implement logic to handle order updates
                order_data = data.get(
                    "orderUpdate"
                )  # Structure needs verification from LBank docs
                pair = data.get("pair", "N/A")
                self.log.info("Order Update Received", pair=pair, details=order_data)
                # Example: Check order status, update internal order book, notify user, etc.
                # if isinstance(order_data, dict):
                #     order_id = order_data.get("orderId")
                #     status = order_data.get("status")
                #     self.log.info(f"Order {order_id} updated to status {status}")
                # else:
                #     self.log.warning("Received orderUpdate with unexpected data format", data=data)

            elif message_type == "assetUpdate":
                # Placeholder: Implement logic to handle asset/balance updates
                asset_data = data.get(
                    "assetUpdate"
                )  # Structure needs verification from LBank docs
                self.log.info("Asset Update Received", details=asset_data)
                # Example: Update internal balance tracking, check for specific assets
                # if isinstance(asset_data, dict):
                #    asset = asset_data.get("asset")
                #    free_balance = asset_data.get("free")
                #    locked_balance = asset_data.get("locked")
                #    self.log.info(f"Asset {asset}: Free={free_balance}, Locked={locked_balance}")
                # else:
                #    self.log.warning("Received assetUpdate with unexpected data format", data=data)

            else:
                # Handle other potential subscription types
                self.log.info(
                    "Subscription Data Received", type=message_type, details=data
                )

        # --- Handle Responses to Specific Requests ---
        # These messages usually echo the 'request' field from the original request
        elif request_type:
            if request_type == "kbar":
                # This is the response to a `request_kbar` call
                self.log.info("KBar Request Response Received")
                if "records" in data and "columns" in data:
                    try:
                        df = pd.DataFrame(data["records"], columns=data["columns"])
                        # Ensure columns exist and data is not empty before accessing
                        if (
                            not df.empty
                            and "timestamp" in df.columns
                            and "close" in df.columns
                        ):
                            # Assuming the request was for daily data and we want the *last* record's close
                            # Adjust logic based on the actual request parameters (size, type)
                            last_candle = df.iloc[-1]
                            self.daily_open = float(
                                last_candle["close"]
                            )  # Assuming last close is relevant 'open' for next period
                            self.daily_open_ts = int(last_candle["timestamp"])
                            self.log.info(
                                "Daily 'open' price and timestamp updated from kbar request",
                                daily_open=self.daily_open,
                                daily_open_ts=self.daily_open_ts,
                            )
                            self.log.debug(
                                "Kbar DataFrame from request", df_repr=df.to_string()
                            )
                        else:
                            self.log.warning(
                                "Kbar request response missing data or columns",
                                data=data,
                            )
                    except (ValueError, TypeError, IndexError) as e:
                        self.log.error(
                            "Error processing kbar request response DataFrame",
                            error=str(e),
                            data=data,
                        )
                    except Exception as e:
                        self.log.exception(
                            f"Unexpected error {e} processing kbar request response",
                            data=data,
                        )
                else:
                    self.log.error("Invalid 'kbar' request response format", data=data)
            else:
                # Handle responses to other potential requests
                self.log.info(
                    "Request Response Received", request_type=request_type, details=data
                )

        # --- Handle Unrecognized Messages ---
        else:
            self.log.warning("Unknown WebSocket message type received", data=data)
