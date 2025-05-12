import pandas as pd
from typing import Optional
from utils import BaseLogger


class MessageProcessor(BaseLogger):
    def __init__(self):
        super().__init__()
        self.log = self.log.bind()
        self.latest_price: Optional[float] = None
        self.daily_open: Optional[float] = None
        self.daily_open_ts: Optional[float] = None

    async def process_incoming_message(self, data: dict) -> None:
        self.log.info("Processing incoming message")
        self.log.debug("debug data:", data=data)
        message_status = data.get("status")
        message_action = data.get("action")
        message_type = data.get("type")
        request_message = data if isinstance(data.get(message_type), str) else None
        subscribe_message = data if not isinstance(data.get(message_type), str) else None

        if subscribe_message and message_type == "kbar":
            self.latest_price = data["kbar"].get("c")
            self.log.info("KBar subscription message received")
            self.log.debug("debug data:", latest_price=self.latest_price)

        elif subscribe_message:
            self.log.info("Subscription message received")

        elif message_status:
            if message_status == "error":
                self.log.error("Error status received", data=data)
            else:
                self.log.info("Status message received")
                self.log.debug("debug data:", status=message_status)

        elif message_action:
            if message_action == "ping":
                self.log.info("Ping action received")
                self.log.debug("debug data:", data=data)
            elif message_action == "pong":
                self.log.info("Pong action received")
                self.log.debug("debug data:", data=data)
            else:
                self.log.info("Other action received")
                self.log.debug("debug data:", action=message_action)

        elif request_message and message_type == "kbar":
            self.log.info("KBar request message received")
            if "records" in data and "columns" in data:
                df = pd.DataFrame(data["records"], columns=data["columns"])
                self.daily_open, self.daily_open_ts = df[["timestamp", "close"]].iloc[-1]
                self.log.info(
                    "Daily open price and timestamp updated",
                    daily_open=self.daily_open,
                    daily_open_ts=self.daily_open_ts,
                )
            else:
                self.log.error("Invalid 'kbar' message format")

        elif request_message:
            self.log.info("Request message received")
            self.log.debug("debug data:", request_message=request_message)

        else:
            self.log.warning("Unknown message type received", data=data)
