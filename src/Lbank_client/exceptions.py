from typing import Dict, Optional


class LBankAPIError(Exception):
    """Custom exception for LBank API errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        response_data: Optional[Dict] = None,
        request_params: Optional[Dict] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.response_data = response_data
        self.request_params = request_params

    def __str__(self):
        base_msg = f"LBankAPIError: {self.args[0]}"
        if self.error_code:
            base_msg = f"LBankAPIError(code={self.error_code}): {self.args[0]}"
        if self.request_params:
            base_msg += f" | Request Params: {self.request_params}"
        return base_msg


class SubscriptionError(Exception):
    """Custom exception for WebSocket subscription key related errors."""

    pass
