import asyncio

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from app.services.exposure_search.playwright_client import PlaywrightClient

@pytest.mark.asyncio
async def test_playwright_client_injection():
    # Setup
    client = PlaywrightClient(headless=True)

    # Mock playwright
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    with patch("app.services.exposure_search.playwright_client.async_playwright", return_value=mock_playwright):
        mock_playwright.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        # set_default_timeout is not async in playwright
        mock_context.set_default_timeout = MagicMock()

        # Define callbacks
        def my_callback(data):
            pass

        async def my_resume_callback():
            return None

        async def my_finish_callback():
            return None

        # Call get_context
        async with client.get_context(
            record_callback=my_callback,
            resume_callback=my_resume_callback,
            finish_callback=my_finish_callback,
        ) as context:
            # Verify context was created
            assert context == mock_context

            # Verify expose_function was called for record, finish, finish-and-continue and resume callbacks
            assert mock_context.expose_function.call_count == 4
            mock_context.expose_function.assert_any_call("__am_record_clue", my_callback)
            calls = [c[0][0] for c in mock_context.expose_function.call_args_list]
            assert "__am_finish_capture" in calls
            assert "__am_finish_and_continue" in calls
            assert "__am_resume_auto" in calls

@pytest.mark.asyncio
async def test_playwright_client_no_injection():
    client = PlaywrightClient(headless=True)
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    with patch("app.services.exposure_search.playwright_client.async_playwright", return_value=mock_playwright):
        mock_playwright.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.set_default_timeout = MagicMock()

        async with client.get_context(record_callback=None) as context:
            assert context == mock_context
            # Should not call expose_function if no callback provided
            assert mock_context.expose_function.called is False


@pytest.mark.asyncio
async def test_wait_for_user_done_returns_quickly_after_finish_signal():
    client = PlaywrightClient(headless=False)
    client._user_done_event = asyncio.Event()

    class FakePage:
        @staticmethod
        def is_closed():
            return False

        url = "https://example.com"

    page = FakePage()

    async def trigger_finish():
        await asyncio.sleep(0.02)
        client._user_done_event.set()

    waiter = asyncio.create_task(client.wait_for_user_done(page, timeout_ms=1000))
    trigger = asyncio.create_task(trigger_finish())
    result = await waiter
    await trigger

    assert result is True
