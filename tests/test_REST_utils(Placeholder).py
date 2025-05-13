import pytest
import httpx
from unittest.mock import AsyncMock, patch

# Assuming REST_utils is importable (adjust path as needed)
try:
    from ..REST_utils import LBankAuthUtils, LBankAPIError  # Example relative import
except (ImportError, ValueError):
    # Fallback if running tests from a different structure
    try:
        from REST_utils import LBankAuthUtils, LBankAPIError
    except ImportError:
        pytest.skip(
            "Skipping REST_utils tests: Module not found", allow_module_level=True
        )


# --- Fixtures ---


@pytest.fixture
def mock_config():
    """Provides mock API configuration."""
    return {
        "API_KEY": "test_api_key",
        "API_SECRET": "test_api_secret",
        "REST_BASE_URL": "https://test.lbank.info/v2/",
    }


@pytest.fixture
def auth_utils(mock_config):
    """Provides an instance of LBankAuthUtils with mock config."""
    return LBankAuthUtils(
        api_key=mock_config["API_KEY"],
        api_secret=mock_config["API_SECRET"],
        base_url=mock_config["REST_BASE_URL"],
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_get_timestamp_success(auth_utils, mock_config):
    """Tests successful fetching of timestamp."""
    mock_response_data = {
        "result": "true",
        "data": 1678886400000,
        "error_code": 0,
        "ts": 1678886400123,
    }
    mock_response = httpx.Response(200, json=mock_response_data)

    # Patch the internal httpx client's request method
    with patch.object(
        auth_utils.client, "get", new_callable=AsyncMock, return_value=mock_response
    ) as mock_get:
        timestamp_data = await auth_utils.get_timestamp()

        # Assertions
        mock_get.assert_called_once_with(
            "timestamp.do", params={}
        )  # Check endpoint and params
        assert timestamp_data == mock_response_data
        assert timestamp_data["result"] == "true"
        assert "data" in timestamp_data


@pytest.mark.asyncio
async def test_request_lbank_api_error(auth_utils):
    """Tests handling of LBank specific errors (result='false')."""
    mock_error_response_data = {
        "result": "false",
        "error_code": 10015,
        "msg": "Invalid signature",
        "ts": 1678886400123,
    }
    mock_response = httpx.Response(
        200, json=mock_error_response_data
    )  # HTTP 200 OK, but logical error

    # Patch the client's post method for this test
    with patch.object(
        auth_utils.client, "post", new_callable=AsyncMock, return_value=mock_response
    ):
        # Expect LBankAPIError to be raised
        with pytest.raises(LBankAPIError) as excinfo:
            # Use a method that triggers _request internally, e.g., a dummy POST call
            await auth_utils._request(
                "POST", "dummy_endpoint.do", params={"test": "data"}
            )

        # Assertions on the exception
        assert excinfo.value.error_code == 10015
        assert "Invalid signature" in str(excinfo.value)
        assert excinfo.value.response_data == mock_error_response_data


@pytest.mark.asyncio
async def test_request_http_error(auth_utils):
    """Tests handling of HTTP errors (e.g., 404 Not Found)."""
    # Simulate an HTTP error response
    mock_response = httpx.Response(404, json={"error": "Not Found"})

    # Patch the client's get method
    with patch.object(
        auth_utils.client, "get", new_callable=AsyncMock, return_value=mock_response
    ) as mock_get:
        # Expect httpx.HTTPStatusError to be raised
        with pytest.raises(httpx.HTTPStatusError):
            await auth_utils._request("GET", "nonexistent_endpoint.do")

        mock_get.assert_called_once()  # Ensure the request was attempted


# --- Placeholder for Signing Test (Requires correct implementation) ---
# @pytest.mark.asyncio
# async def test_sign_method(auth_utils):
#     """Tests the signing mechanism (needs correct implementation first)."""
#     # This test needs to be adapted once the _sign method uses the correct
#     # algorithm (HMAC-SHA256) and parameter handling based on LBank docs.
#     params_to_sign = {"symbol": "btc_usdt", "amount": "1"}
#     timestamp = "1678886400000"
#
#     # Call the sign method (assuming it's corrected)
#     # signed_params = auth_utils._sign(params_to_sign, timestamp)
#
#     # Assertions:
#     # - Check if 'api_key', 'sign', 'timestamp', 'signature_method', 'echostr' are present
#     # - Verify the calculated 'sign' value against a known correct signature
#     #   (requires generating a reference signature manually or using a trusted library)
#     # - Ensure original params are handled correctly (merged or separate based on API reqs)
#     pytest.skip("Signing test requires correct _sign implementation and verification.")


# Remember to close the client in tests if it's not managed by fixtures properly
@pytest.mark.asyncio
async def test_client_closure(auth_utils):
    """Ensures the client close method can be called."""
    with patch.object(
        auth_utils.client, "aclose", new_callable=AsyncMock
    ) as mock_aclose:
        await auth_utils.close_client()
        mock_aclose.assert_called_once()
