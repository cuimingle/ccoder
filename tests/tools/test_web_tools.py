"""Tests for WebFetchTool and WebSearchTool."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.web_fetch_tool import WebFetchTool
from app.tools.web_search_tool import WebSearchTool
from app.tool import ToolContext

@pytest.fixture
def ctx(tmp_path):
    return ToolContext(cwd=str(tmp_path))

# --- WebFetchTool ---

@pytest.mark.asyncio
async def test_web_fetch_converts_html_to_markdown(ctx):
    html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.headers = {"content-type": "text/html"}
    mock_response.url = "https://example.com"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client

        result = await WebFetchTool().call({"url": "https://example.com", "prompt": "summarize"}, ctx)

    assert result.is_error is False
    assert "Hello" in result.content or "example" in result.content.lower()

@pytest.mark.asyncio
async def test_web_fetch_handles_error(ctx):
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        MockClient.return_value = mock_client

        result = await WebFetchTool().call({"url": "https://bad.example.com", "prompt": "test"}, ctx)

    assert result.is_error is True

# --- WebSearchTool ---

@pytest.mark.asyncio
async def test_web_search_returns_results(ctx, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    mock_results = {
        "results": [
            {"title": "Python docs", "url": "https://python.org", "content": "Python is great"},
        ]
    }
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=mock_results)
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        MockClient.return_value = mock_client

        result = await WebSearchTool().call({"query": "python programming"}, ctx)

    assert result.is_error is False

@pytest.mark.asyncio
async def test_web_search_no_api_key_returns_error(ctx, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    result = await WebSearchTool().call({"query": "test"}, ctx)
    assert result.is_error is True
    assert "api key" in result.content.lower() or "not configured" in result.content.lower()
