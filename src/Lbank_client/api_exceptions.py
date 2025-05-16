from typing import Dict, Optional


class LBankAPIError(Exception):
    """
    Custom exception for LBank REST API errors.

    Attributes:
        message (str): The error message.
        error_code (Optional[int]): The specific error code from the API, if available.
        response_data (Optional[Dict]): The full response data from the API, if available.
        request_params (Optional[Dict]): The parameters sent in the request, for context.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        response_data: Optional[Dict] = None,
        request_params: Optional[Dict] = None,
    ):
        """
        Initializes the LBankAPIError.

        Args:
            message (str): The primary error message.
            error_code (Optional[int]): API specific error code.
            response_data (Optional[Dict]): Raw response data from the API.
            request_params (Optional[Dict]): Parameters that were sent with the request.
        """
        super().__init__(message)
        self.error_code = error_code
        self.response_data = response_data
        self.request_params = request_params

    def __str__(self) -> str:
        """
        Provides a string representation of the error, including code and request params if available.
        """
        base_msg = f"LBankAPIError: {self.args[0]}"
        if self.error_code:
            base_msg = f"LBankAPIError(code={self.error_code}): {self.args[0]}"
        if self.request_params:
            # Avoid printing overly large request params directly in the string representation
            # For detailed debugging, one would inspect the attribute directly.
            params_summary = str(self.request_params)[:100]  # Truncate for brevity
            if len(str(self.request_params)) > 100:
                params_summary += "..."
            base_msg += f" | Request Params (summary): {params_summary}"
        return base_msg


class SubscriptionError(Exception):
    """
    Custom exception for errors related to WebSocket subscription key management
    or subscription process.
    """

    pass


if __name__ == "__main__":
    # Example usage of LBankAPIError
    try:
        # Simulate an API error condition
        raise LBankAPIError(
            "Failed to fetch user data",
            error_code=1004,
            response_data={
                "result": "false",
                "error_code": 1004,
                "msg": "User not found",
            },
            request_params={"user_id": "12345"},
        )
    except LBankAPIError as e:
        print(f"Caught LBank API Error: {e}")
        print(f"  Error Code: {e.error_code}")
        print(f"  Response Data: {e.response_data}")
        print(f"  Request Params: {e.request_params}")

    # Example usage of SubscriptionError
    try:
        # Simulate a subscription error condition
        raise SubscriptionError("Failed to obtain WebSocket subscription key.")
    except SubscriptionError as e:
        print(f"\nCaught Subscription Error: {e}")
