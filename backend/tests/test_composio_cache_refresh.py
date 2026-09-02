import asyncio
from unittest.mock import AsyncMock, patch

import composio_service


def test_get_all_connection_statuses_accepts_force_refresh():
    async def _run():
        with patch.object(composio_service, "_get_key", return_value="key"), \
             patch.object(composio_service, "_v3_list_user_accounts", AsyncMock(return_value=[])) as mock_list:
            result = await composio_service.get_all_connection_statuses("user-123", force_refresh=True)
        return result, mock_list

    result, mock_list = asyncio.run(_run())

    assert result == {toolkit: False for toolkit in composio_service.ALL_TOOLKITS}
    assert mock_list.await_count == 1


def test_get_connection_status_force_refresh_bypasses_stale_cache():
    async def _run():
        composio_service._ACCOUNTS_CACHE.clear()
        composio_service._ACCOUNTS_CACHE["user-123"] = (0, [{"status": "PENDING", "id": "old"}])

        with patch.object(composio_service, "_get_key", return_value="key"), \
             patch.object(
                 composio_service,
                 "_v3_list_user_accounts",
                 AsyncMock(return_value=[{"status": "ACTIVE", "id": "new", "toolkit": {"slug": "gmail"}}]),
             ) as mock_list:
            result = await composio_service.get_connection_status("user-123", "gmail", force_refresh=True)
        return result, mock_list

    result, mock_list = asyncio.run(_run())

    assert result == {"connected": True, "connection_id": "new"}
    assert "user-123" not in composio_service._ACCOUNTS_CACHE
    assert mock_list.await_count == 1
