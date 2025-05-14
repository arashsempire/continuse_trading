import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from Lbank_client import ClientManager


@pytest.fixture
def mock_clients():
    with patch("ClientManager.RESTAccount") as mock_account, patch(
        "ClientManager.RESTTrading"
    ) as mock_trading, patch("ClientManager.RESTData") as mock_data, patch(
        "ClientManager.WSClient"
    ) as mock_ws:

        # Configure REST mocks
        mock_account.return_value.get_balances = AsyncMock(
            return_value={"USDT": "1000"}
        )
        mock_trading.return_value.get_open_orders = AsyncMock(return_value={})
        mock_trading.return_value.place_order = AsyncMock(
            return_value={"order_id": "123"}
        )

        # Configure WebSocket mocks
        mock_ws.return_value.connect = AsyncMock()
        mock_ws.return_value.disconnect = AsyncMock()
        mock_ws.return_value.subscribe_balances = AsyncMock()
        mock_ws.return_value.subscribe_orders = AsyncMock()
        mock_ws.return_value.is_connected = AsyncMock(return_value=True)

        yield {
            "account": mock_account,
            "trading": mock_trading,
            "data": mock_data,
            "ws": mock_ws,
        }


@pytest.mark.asyncio
async def test_start_and_stop(mock_clients):
    cm = ClientManager("key", "secret")
    await cm.start()
    await asyncio.sleep(0.1)
    await cm.stop()

    assert cm.balances == {"USDT": "1000"}
    assert cm.open_orders == {}
    assert cm._running is False


@pytest.mark.asyncio
async def test_place_order(mock_clients):
    cm = ClientManager("key", "secret")
    await cm.start()

    result = await cm.place_order("BTC/USDT", "buy", 0.01)
    assert result == {"order_id": "123"}

    await cm.stop()


@pytest.mark.asyncio
async def test_reconnection_logic(mock_clients):
    cm = ClientManager("key", "secret")
    cm.ws_client.is_connected = AsyncMock(side_effect=[True, False, False, True])
    await cm.start()
    await asyncio.sleep(6.5)  # allow reconnection watchdog to cycle
    await cm.stop()

    assert cm._running is False


@pytest.mark.asyncio
async def test_reconciliation_state_mismatch(mock_clients):
    cm = ClientManager("key", "secret")
    await cm.start()

    # Simulate desynchronization
    cm.balances = {"BTC": "0.5"}  # stale data
    cm.open_orders = {"abc": {"symbol": "BTC/USDT"}}

    # Manually call reconciliation once
    await cm._periodic_reconciliation()

    assert cm.balances == {"USDT": "1000"}  # reconciled
    assert cm.open_orders == {}  # reconciled

    await cm.stop()


@pytest.mark.asyncio
async def test_on_balance_update(mock_clients):
    cm = ClientManager("key", "secret")
    await cm.start()

    await cm._on_balance_update({"ETH": "10"})
    assert cm.balances["ETH"] == "10"

    await cm.stop()


@pytest.mark.asyncio
async def test_on_order_update(mock_clients):
    cm = ClientManager("key", "secret")
    await cm.start()

    await cm._on_order_update({"order_id": "001", "status": "open"})
    assert "001" in cm.open_orders

    await cm._on_order_update({"order_id": "001", "status": "closed"})
    assert "001" not in cm.open_orders

    await cm.stop()
