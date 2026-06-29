"""Client helpers for Philips Air Purifier CoAP communication."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from aiocoap import Context, Message, Unreliable
from aiocoap.numbers.codes import GET
from philips_airctrl import CoAPClient

_LOGGER = logging.getLogger(__name__)

# Delay before nudging, to let the observation register on the device.
_NUDGE_REGISTER_DELAY = 2.0
# How long to wait for a push after each nudge, and how many times to nudge.
_NUDGE_WAIT_TIMEOUT = 12.0
_NUDGE_ATTEMPTS = 2


async def async_create_client(
    host: str,
    timeout: float = 25,
    create_client: Any | None = None,
) -> CoAPClient:
    """Create a CoAP client for a host with timeout protection."""
    creator = create_client or CoAPClient.create
    return await asyncio.wait_for(creator(host), timeout=timeout)


async def async_fetch_status(
    host: str,
    connect_timeout: float = 30,
    status_timeout: float = 30,
    create_client: Any | None = None,
) -> dict[str, Any]:
    """Fetch current status using a temporary CoAP client and shut it down.

    Uses ``observe=False`` (philips-airctrl >= 1.1.0) so this one-shot read does
    not leave a CoAP observation registered on the device.
    """
    client = await async_create_client(host, timeout=connect_timeout, create_client=create_client)
    try:
        status, _ = await asyncio.wait_for(client.get_status(observe=False), timeout=status_timeout)
        return status
    finally:
        with contextlib.suppress(Exception):
            await client.shutdown()


async def async_fetch_device_info(host: str, port: int = 5683, timeout: float = 15) -> dict[str, Any]:
    """Fetch the plaintext ``sys/dev/info`` resource (model id, name, device id).

    This resource is served without the CoAP Observe mechanism and responds even
    on firmwares that never answer the encrypted ``sys/dev/status`` read, so it
    is used to identify a device whose status cannot be read directly.
    """
    context = await Context.create_client_context()
    try:
        request = Message(
            code=GET,
            transport_tuning=Unreliable,
            uri=f"coap://{host}:{port}/sys/dev/info",
        )
        response = await asyncio.wait_for(context.request(request).response, timeout=timeout)
        return json.loads(response.payload.decode())
    finally:
        with contextlib.suppress(Exception):
            await context.shutdown()


async def async_fetch_status_with_nudge(
    host: str,
    nudge: list[tuple[str, Any]],
    connect_timeout: float = 30,
    status_timeout: float = 30,
    create_client: Any | None = None,
) -> dict[str, Any]:
    """Fetch status from a device that only pushes on a real state change.

    Some firmwares never answer a status read; they only push the status
    resource to *other* observers when the device state changes. This opens an
    observation on one connection and sends ``nudge`` control writes from a
    second connection to force the first push, then returns that status.
    """
    _ = status_timeout  # bounded per-attempt by _NUDGE_WAIT_TIMEOUT below
    observer = await async_create_client(host, timeout=connect_timeout, create_client=create_client)
    nudger: CoAPClient | None = None
    result: dict[str, Any] = {}
    received = asyncio.Event()

    async def _watch() -> None:
        async for status in observer.observe_status():
            result["status"] = status
            received.set()
            return

    watch_task = asyncio.create_task(_watch())
    try:
        # Let the observation register on the device before changing state.
        await asyncio.sleep(_NUDGE_REGISTER_DELAY)
        nudger = await async_create_client(host, timeout=connect_timeout, create_client=create_client)
        for _attempt in range(_NUDGE_ATTEMPTS):
            for key, value in nudge:
                await nudger.set_control_value(key, value)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(received.wait(), timeout=_NUDGE_WAIT_TIMEOUT)
            if received.is_set():
                return result["status"]
        raise TimeoutError
    finally:
        watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watch_task
        if nudger is not None:
            with contextlib.suppress(Exception):
                await nudger.shutdown()
        with contextlib.suppress(Exception):
            await observer.shutdown()
