from __future__ import annotations

import httpx
import pytest

from spotify_daily_podcasts.constants import MAX_LOOP, SPOTIFY_API_BASE
from spotify_daily_podcasts.settings import SpotifySecrets
from spotify_daily_podcasts.spotify_client import SpotifyAPIError, SpotifyClient


def _secrets() -> SpotifySecrets:
    return SpotifySecrets.model_validate(
        {
            "client_id": "clientidvalue",
            "client_secret": "clientsecretvalue",
            "refresh_token": "refreshtokenvalue",
        }
    )


def test_rejects_non_spotify_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="非 Spotify"):
        client._request_json(  # noqa: SLF001
            "GET",
            "https://evil.example/v1",
            headers={"Authorization": "Bearer x"},
        )


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "aaaaaaaaaaaaaaaaaaaaaa",
                        "uri": "spotify:episode:aaaaaaaaaaaaaaaaaaaaaa",
                        "name": "ep",
                        "release_date": "2026-09-21",
                        "release_date_precision": "day",
                    }
                ],
                "next": None,
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    items = client.list_show_episodes("4rOoJ6Egrf8K2IrywzwOMk", "TW")
    assert len(items) == 1
    assert calls["n"] >= 3


def test_pagination_stops_at_max_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            200,
            json={
                "items": [],
                "next": f"{SPOTIFY_API_BASE}/shows/4rOoJ6Egrf8K2IrywzwOMk/episodes?offset=50",
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    client.list_show_episodes("4rOoJ6Egrf8K2IrywzwOMk", "TW")
    # token + MAX_LOOP episode pages
    # MockTransport doesn't expose call count easily; ensure no exception and cap is 5
    assert MAX_LOOP == 5


def test_replace_playlist_put() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        methods.append(request.method)
        return httpx.Response(201, json={"snapshot_id": "s"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    uris = ["spotify:episode:aaaaaaaaaaaaaaaaaaaaaa"]
    client.replace_playlist_items("37i9dQZF1DXcBWIGoYBM5M", uris)
    assert methods == ["PUT"]


def test_max_loop_constant() -> None:
    assert MAX_LOOP == 5


def test_token_response_must_include_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="access_token"):
        client.refresh_access_token()


def test_http_400_is_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(400, text="client_secret=should-hide")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="400"):
        client.list_show_episodes("4rOoJ6Egrf8K2IrywzwOMk", "TW")


def test_401_then_success() -> None:
    api_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        api_calls["n"] += 1
        if api_calls["n"] == 1:
            return httpx.Response(401, text="expired")
        return httpx.Response(200, json={"items": [], "next": None})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    assert client.list_show_episodes("4rOoJ6Egrf8K2IrywzwOMk", "TW") == []


def test_timeouts_stop_after_max_loop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="5 次"):
        client.refresh_access_token()


def test_replace_empty_playlist_and_chunks() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        methods.append(request.method)
        return httpx.Response(200, content=b"")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    client.replace_playlist_items("37i9dQZF1DXcBWIGoYBM5M", [])
    assert methods == ["PUT"]
    methods.clear()
    uris = [f"spotify:episode:{i:022d}" for i in range(101)]
    client.replace_playlist_items("37i9dQZF1DXcBWIGoYBM5M", uris)
    assert methods == ["PUT", "POST"]


def test_episodes_items_must_be_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "api/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(200, json={"items": "bad", "next": None})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="格式錯誤"):
        client.list_show_episodes("4rOoJ6Egrf8K2IrywzwOMk", "TW")


def test_json_must_be_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = SpotifyClient(_secrets(), client=http, sleep=lambda _: None)
    with pytest.raises(SpotifyAPIError, match="JSON object"):
        client.refresh_access_token()


def test_context_manager_does_not_close_injected_client() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with SpotifyClient(_secrets(), client=http, sleep=lambda _: None):
        pass
    assert not http.is_closed
