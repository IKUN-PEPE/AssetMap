import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.exposure_search.providers.bing import BingProvider
from app.services.exposure_search.providers.base import ExposureSearchItem

@pytest.mark.asyncio
async def test_bing_provider_extraction():
    # Mock Playwright objects
    mock_pw = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    
    # Correctly mock the async context manager and async methods
    mock_pw.get_context.return_value.__aenter__.return_value = mock_context
    mock_pw.open_page = AsyncMock(return_value=mock_page)
    mock_pw.detect_captcha_or_login = AsyncMock(return_value=(False, None))
    
    # Mock search results
    mock_res = AsyncMock()
    mock_title_el = AsyncMock()
    mock_title_el.inner_text.return_value = "深圳地铁官网"
    mock_title_el.get_attribute.return_value = "https://www.szmc.net/"
    mock_snippet_el = AsyncMock()
    mock_snippet_el.inner_text.return_value = "深圳地铁集团官方网站..."
    
    # query_selector needs to be AsyncMock
    mock_res.query_selector = AsyncMock()
    mock_res.query_selector.side_effect = lambda s: {
        "h2 a, h3 a, a": mock_title_el,
        ".b_caption p, .b_algo_snippet, .st, p": mock_snippet_el
    }.get(s)
    
    mock_page.query_selector_all.return_value = [mock_res]
    
    provider = BingProvider(mock_pw)
    results = await provider.search("深圳地铁", max_results=10, max_pages=1)
    
    assert len(results) == 1
    assert results[0].title == "深圳地铁官网"
    assert results[0].url == "https://www.szmc.net/"
    assert results[0].source == "bing"

@pytest.mark.asyncio
async def test_provider_captcha_detection():
    mock_pw = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    
    mock_pw.get_context.return_value.__aenter__.return_value = mock_context
    mock_pw.open_page = AsyncMock(return_value=mock_page)
    # Simulate captcha
    mock_pw.detect_captcha_or_login = AsyncMock(return_value=(True, "检测到人机验证"))
    
    provider = BingProvider(mock_pw)
    results = await provider.search("深圳地铁", max_results=10, max_pages=1)
    
    assert len(results) == 0
    # Verify it stopped early
    assert mock_page.query_selector_all.called is False


@pytest.mark.asyncio
async def test_provider_does_not_wait_for_manual_done_on_normal_results():
    mock_pw = MagicMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_pw.get_context.return_value.__aenter__.return_value = mock_context
    mock_pw.open_page = AsyncMock(return_value=mock_page)
    mock_pw.detect_captcha_or_login = AsyncMock(return_value=(False, None))
    mock_pw.wait_for_user_done = AsyncMock(return_value=True)

    mock_res = AsyncMock()
    mock_title_el = AsyncMock()
    mock_title_el.inner_text.return_value = "Test"
    mock_title_el.get_attribute.return_value = "https://example.com"
    mock_snippet_el = AsyncMock()
    mock_snippet_el.inner_text.return_value = "snippet"

    mock_res.query_selector = AsyncMock()
    mock_res.query_selector.side_effect = lambda selector: {
        "h2 a, h3 a, a": mock_title_el,
        ".b_caption p, .b_algo_snippet, .st, p": mock_snippet_el,
    }.get(selector)
    mock_page.query_selector_all.return_value = [mock_res]

    provider = BingProvider(mock_pw)
    results = await provider.search("query", max_results=10, max_pages=1)

    assert len(results) == 1
    mock_pw.wait_for_user_done.assert_not_called()


@pytest.mark.asyncio
async def test_provider_requests_intervention_on_captcha_when_headful():
    mock_pw = MagicMock()
    mock_pw.headless = False
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_pw.get_context.return_value.__aenter__.return_value = mock_context
    mock_pw.open_page = AsyncMock(return_value=mock_page)
    mock_pw.detect_captcha_or_login = AsyncMock(return_value=(True, "captcha"))

    service = MagicMock()
    service.stop_check.return_value = False
    service.request_intervention = AsyncMock(return_value=False)

    provider = BingProvider(mock_pw)
    results = await provider.search(
        "query",
        max_results=10,
        max_pages=1,
        service=service,
        task_id="task-1",
        db=object(),
    )

    assert results == []
    service.request_intervention.assert_called()


@pytest.mark.asyncio
async def test_provider_skips_current_page_when_intervention_returns_finish():
    mock_pw = MagicMock()
    mock_pw.headless = False
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_pw.get_context.return_value.__aenter__.return_value = mock_context
    mock_pw.open_page = AsyncMock(return_value=mock_page)
    mock_pw.detect_captcha_or_login = AsyncMock(return_value=(True, "captcha"))

    service = MagicMock()
    service.stop_check.return_value = False
    service.request_intervention = AsyncMock(return_value="finish")

    provider = BingProvider(mock_pw)
    results = await provider.search(
        "query",
        max_results=10,
        max_pages=1,
        service=service,
        task_id="task-1",
        db=object(),
    )

    assert results == []
    assert mock_pw.open_page.call_count == 1
