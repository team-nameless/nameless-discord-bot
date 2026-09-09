# ruff: noqa: PLC0415


from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import quickjs
from nameless.command.music_downloader.downloader.utils.health_check import HEALTH_CACHE, check_service_health
from nameless.command.music_downloader.downloader.utils.js_mocks import register_mocks_in_context


def test_js_mocks_completeness() -> None:
    # initialize quickjs context and mocks
    ctx = quickjs.Context()
    ctx.eval("var registeredExtension = null;")
    ctx.eval("function registerExtension(ext) { registeredExtension = ext; }")

    manifest = {
        "name": "test-mock-service",
        "minAppVersion": "1.0.0",
        "qualityOptions": [],
        "serviceHealth": [],
        "settings": [],
    }

    register_mocks_in_context(ctx, Path(), manifest)  # type: ignore

    # test utils.sleep mock
    sleep_res = ctx.eval("utils.sleep(10)")
    assert sleep_res is True

    # test gobackend.getLyricsLRC mock
    lyrics_json = ctx.eval('JSON.stringify(gobackend.getLyricsLRC("spotify_id", "title", "artist", "album", 123))')
    lyrics_res = json.loads(lyrics_json)
    assert isinstance(lyrics_res, dict)
    assert lyrics_res.get("error") == "not implemented"
    assert lyrics_res.get("lyrics") == ""


def test_service_health_check() -> None:
    # clear cache before testing
    HEALTH_CACHE.clear()

    # healthy service manifest
    manifest_healthy = {
        "name": "test-healthy-service",
        "minAppVersion": "1.0.0",
        "qualityOptions": [],
        "serviceHealth": [
            {
                "id": "test-api",
                "label": "Test API",
                "url": "https://api.test.com/health",
                "method": "GET",
                "serviceKey": "deezer",
                "timeoutMs": 1000,
                "cacheTtlSeconds": 60,
                "required": True,
            }
        ],
        "settings": [],
    }

    # mock httpx.Client.get to return status 200 and json showing deezer is ok
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"status": "degraded", "services": {"deezer": {"ok": true, "status": 200}}}'
    mock_client.get.return_value = mock_response
    mock_client.__enter__.return_value = mock_client

    with patch("nameless.command.music_downloader.downloader.utils.health_check.httpx.Client", return_value=mock_client):
        res = check_service_health(manifest_healthy)  # type: ignore
        assert res is True
        mock_client.get.assert_called_once_with(
            "https://api.test.com/health",
            timeout=1.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

    # cached result should return True without calling httpx
    with patch("nameless.command.music_downloader.downloader.utils.health_check.httpx.Client") as mock_client_cls:
        res_cached = check_service_health(manifest_healthy)  # type: ignore
        assert res_cached is True
        mock_client_cls.assert_not_called()

    # clear cache for unhealthy key test
    HEALTH_CACHE.clear()

    # mock httpx to return status 200 but deezer is not ok
    mock_unhealthy_client = MagicMock()
    mock_unhealthy_response = MagicMock()
    mock_unhealthy_response.status_code = 200
    mock_unhealthy_response.content = b'{"status": "degraded", "services": {"deezer": {"ok": false, "status": 500}}}'
    mock_unhealthy_client.get.return_value = mock_unhealthy_response
    mock_unhealthy_client.__enter__.return_value = mock_unhealthy_client

    with patch("nameless.command.music_downloader.downloader.utils.health_check.httpx.Client", return_value=mock_unhealthy_client):
        res_unhealthy = check_service_health(manifest_healthy)  # type: ignore
        assert res_unhealthy is False

    # clear cache for HTTP exception test
    HEALTH_CACHE.clear()

    # mock httpx.Client to raise Exception
    mock_exception_client = MagicMock()
    mock_exception_client.get.side_effect = Exception("connection error")
    mock_exception_client.__enter__.return_value = mock_exception_client

    with patch("nameless.command.music_downloader.downloader.utils.health_check.httpx.Client", return_value=mock_exception_client):
        res_exception = check_service_health(manifest_healthy)  # type: ignore
        assert res_exception is False

    # check cache respects required: False
    HEALTH_CACHE.clear()
    manifest_optional = {
        "name": "test-optional-service",
        "minAppVersion": "1.0.0",
        "qualityOptions": [],
        "serviceHealth": [
            {
                "id": "test-api-opt",
                "label": "Test API Optional",
                "url": "https://api.test.com/health-opt",
                "method": "GET",
                "serviceKey": "test",
                "timeoutMs": 1000,
                "cacheTtlSeconds": 60,
                "required": False,
            }
        ],
        "settings": [],
    }
    with patch("nameless.command.music_downloader.downloader.utils.health_check.httpx.Client", return_value=mock_exception_client):
        res_optional = check_service_health(manifest_optional)  # type: ignore
        assert res_optional is True


def test_get_provider_unhealthy() -> None:
    # clear cache before testing
    HEALTH_CACHE.clear()

    from nameless.command.music_downloader.downloader.downloader import MusicDownloader

    # healthy test
    downloader = MusicDownloader()

    # patch health check to return True
    with patch("nameless.command.music_downloader.downloader.downloader.check_service_health", return_value=True):
        provider = downloader.get_provider("youtube")
        assert provider is not None

    # patch health check to return False
    with (
        patch("nameless.command.music_downloader.downloader.downloader.check_service_health", return_value=False),
        pytest.raises(RuntimeError, match="service youtube is unhealthy/unavailable"),
    ):
        downloader.get_provider("youtube")
