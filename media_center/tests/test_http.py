from __future__ import annotations

import httpx
import pytest
import respx

from core.errors import MediaCenterError
from core.http import request_with_retry


@respx.mock
async def test_retry_temporary_status() -> None:
    route = respx.get("https://retry.invalid/data").mock(
        side_effect=[
            httpx.Response(500, text="temporary"),
            httpx.Response(200, text="ok"),
        ]
    )
    async with httpx.AsyncClient() as client:
        response = await request_with_retry(client, "GET", "https://retry.invalid/data")
    assert response.text == "ok"
    assert route.call_count == 2


@respx.mock
async def test_404_is_not_retried() -> None:
    route = respx.get("https://retry.invalid/missing").mock(
        return_value=httpx.Response(404, text="missing")
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(MediaCenterError):
            await request_with_retry(client, "GET", "https://retry.invalid/missing")
    assert route.call_count == 1
