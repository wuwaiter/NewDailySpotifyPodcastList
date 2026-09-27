from __future__ import annotations

import httpx
import pytest

from spotify_daily_podcasts.constants import YOUTUBE_API_BASE
from spotify_daily_podcasts.settings import YouTubeSecrets
from spotify_daily_podcasts.youtube_client import YouTubeAPIError, YouTubeClient


def _secrets() -> YouTubeSecrets:
    return YouTubeSecrets.model_validate(
        {
            "client_id": "youtubeidvalue.apps.googleusercontent.com",
            "client_secret": "youtubesecretval",
            "refresh_token": "youtuberefreshval",
        }
    )


def test_rejects_non_google_host() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    client = YouTubeClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(YouTubeAPIError, match="官方主機"):
        client._request_json(  # noqa: SLF001
            "GET",
            "https://evil.example/v3",
            headers={"Authorization": "Bearer x"},
        )


def test_list_channel_videos() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "tok"})
        if "/channels" in url:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UUzzzzzzzzzzzzzzzzzzzzzz"}
                            }
                        }
                    ]
                },
            )
        if "/playlistItems" in url:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {
                                "title": "今日",
                                "publishedAt": "2026-09-21T08:00:00Z",
                                "resourceId": {"videoId": "abcdefghijk"},
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404, text="missing")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = YouTubeClient(_secrets(), client=http, sleep=lambda _: None)
    items = client.list_channel_videos("UCzzzzzzzzzzzzzzzzzzzzzz")
    assert len(items) == 1


def test_replace_playlist_deletes_then_inserts() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "tok"})
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "item-1"}]})
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = YouTubeClient(_secrets(), client=http, sleep=lambda _: None)
    client.replace_playlist_items("PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy", ["abcdefghijk"])
    assert methods == ["GET", "DELETE", "POST"]


def test_json_must_be_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = YouTubeClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(YouTubeAPIError, match="JSON object"):
        client.refresh_access_token()


def test_timeouts_stop_after_max_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = YouTubeClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(YouTubeAPIError, match="5 次"):
        client.refresh_access_token()


def test_youtube_api_base_is_official() -> None:
    assert YOUTUBE_API_BASE.startswith("https://www.googleapis.com/")
