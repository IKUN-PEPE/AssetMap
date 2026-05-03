import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.exposure_search.playwright_client import PlaywrightClient
import os

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
        
        # Define a callback
        def my_callback(data):
            pass
            
        # Call get_context
        async with client.get_context(record_callback=my_callback) as context:
            # Verify context was created
            assert context == mock_context
            
            # Verify expose_function was called
            mock_context.expose_function.assert_called_once_with("__am_record_clue", my_callback)
            
            # Verify add_init_script was called at least twice
            # 1. Anti-bot script
            # 2. Discovery script
            assert mock_context.add_init_script.call_count >= 2
            
            # Verify one of the calls contains the anti-bot script
            mock_context.add_init_script.assert_any_call("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Verify discovery script was loaded and injected
            # We can check if it was called with content from discovery_script.js
            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "services", "exposure_search", "discovery_script.js")
            with open(script_path, "r", encoding="utf-8") as f:
                expected_script = f.read()
            
            mock_context.add_init_script.assert_any_call(expected_script)

@pytest.mark.asyncio
async def test_playwright_client_no_injection():
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
        
        # Call get_context WITHOUT callback
        async with client.get_context() as context:
            # Verify expose_function was NOT called for __am_record_clue
            # (It shouldn't be called at all in this case)
            assert mock_context.expose_function.called is False
            
            # Verify add_init_script was called only once (for anti-bot)
            assert mock_context.add_init_script.call_count == 1
            mock_context.add_init_script.assert_called_once_with("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
