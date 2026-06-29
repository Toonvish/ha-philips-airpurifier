"""Tests for the CoAP client helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.philips_airpurifier.client import (
    async_fetch_device_info,
    async_fetch_status_with_nudge,
)

_CLIENT = "custom_components.philips_airpurifier.client"


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    """Yield the given items as an async iterator."""
    for item in items:
        yield item


async def test_async_fetch_device_info_parses_payload() -> None:
    """Test sys/dev/info is fetched and parsed as JSON."""
    info = {"modelid": "CX7550/01", "name": "Büro", "device_id": "abc"}
    response = MagicMock()
    response.payload = json.dumps(info).encode()
    future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    future.set_result(response)
    handle = MagicMock()
    handle.response = future
    context = MagicMock()
    context.request = MagicMock(return_value=handle)
    context.shutdown = AsyncMock()

    with patch(
        f"{_CLIENT}.Context.create_client_context",
        AsyncMock(return_value=context),
    ):
        result = await async_fetch_device_info("1.2.3.4")

    assert result == info
    context.shutdown.assert_awaited()


async def test_async_fetch_status_with_nudge_success() -> None:
    """Test the observe-plus-nudge fetch returns the first pushed status."""
    status = {"D01S05": "CX7550/01", "D03102": 1}
    observer = MagicMock()
    observer.observe_status = MagicMock(return_value=_aiter([status]))
    observer.shutdown = AsyncMock()
    nudger = MagicMock()
    nudger.set_control_value = AsyncMock()
    nudger.shutdown = AsyncMock()

    with (
        patch(f"{_CLIENT}.async_create_client", AsyncMock(side_effect=[observer, nudger])),
        patch(f"{_CLIENT}._NUDGE_REGISTER_DELAY", 0),
    ):
        result = await async_fetch_status_with_nudge("1.2.3.4", [("D03105", 0), ("D03105", 115)])

    assert result == status
    nudger.set_control_value.assert_awaited()
    nudger.shutdown.assert_awaited()
    observer.shutdown.assert_awaited()


async def test_async_fetch_status_with_nudge_timeout() -> None:
    """Test the nudge fetch raises TimeoutError when no push arrives."""
    observer = MagicMock()
    observer.observe_status = MagicMock(return_value=_aiter([]))
    observer.shutdown = AsyncMock()
    nudger = MagicMock()
    nudger.set_control_value = AsyncMock()
    nudger.shutdown = AsyncMock()

    with (
        patch(f"{_CLIENT}.async_create_client", AsyncMock(side_effect=[observer, nudger])),
        patch(f"{_CLIENT}._NUDGE_REGISTER_DELAY", 0),
        patch(f"{_CLIENT}._NUDGE_WAIT_TIMEOUT", 0.01),
        pytest.raises(TimeoutError),
    ):
        await async_fetch_status_with_nudge("1.2.3.4", [("D03105", 0)])

    observer.shutdown.assert_awaited()
