"""帶上限 5 次的 HTTP 重試與 Spotify Web API 用戶端。"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from spotify_daily_podcasts.constants import (
    HTTP_TIMEOUT_SECONDS,
    MAX_LOOP,
    PAGE_LIMIT,
    PLAYLIST_REPLACE_CHUNK,
    SPOTIFY_ACCOUNTS_BASE,
    SPOTIFY_API_BASE,
)
from spotify_daily_podcasts.security import redact, safe_headers
from spotify_daily_podcasts.settings import SpotifySecrets

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = {"api.spotify.com", "accounts.spotify.com"}


class SpotifyAPIError(RuntimeError):
    """Spotify API 呼叫失敗。"""


def _assert_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        msg = "拒絕連到非 Spotify 官方主機"
        raise SpotifyAPIError(msg)


class SpotifyClient:
    def __init__(
        self,
        secrets: SpotifySecrets,
        *,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._secrets = secrets
        self._access_token: str | None = None
        self._sleep = sleep
        self._owns_client = client is None
        self._http = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> SpotifyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def refresh_access_token(self) -> str:
        url = f"{SPOTIFY_ACCOUNTS_BASE}/api/token"
        _assert_allowed_url(url)
        basic = base64.b64encode(
            f"{self._secrets.client_id}:{self._secrets.client_secret}".encode()
        ).decode()
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._secrets.refresh_token,
        }
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = self._request_json("POST", url, headers=headers, data=data)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            msg = "token 回應缺少 access_token"
            raise SpotifyAPIError(msg)
        self._access_token = token
        logger.info("已更新 Spotify access token")
        return token

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            self.refresh_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        _assert_allowed_url(url)
        last_error: Exception | None = None
        for attempt in range(1, MAX_LOOP + 1):
            try:
                logger.debug(
                    "HTTP %s %s headers=%s attempt=%s/%s",
                    method,
                    url,
                    safe_headers(headers),
                    attempt,
                    MAX_LOOP,
                )
                response = self._http.request(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    json=json_body,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_LOOP:
                    retry_after = float(response.headers.get("Retry-After", attempt))
                    wait_s = min(max(retry_after, 0.0), 30.0)
                    logger.warning(
                        "Spotify 暫時失敗 status=%s，%ss 後重試",
                        response.status_code,
                        wait_s,
                    )
                    self._sleep(wait_s)
                    continue
                accounts_host = "accounts.spotify.com"
                if response.status_code == 401 and attempt < MAX_LOOP and accounts_host not in url:
                    logger.warning("access token 失效，重新整理後重試")
                    self.refresh_access_token()
                    headers = {**headers, **self._auth_headers()}
                    continue
                if response.status_code >= 400:
                    body = redact(response.text[:500])
                    msg = f"Spotify API {response.status_code}: {body}"
                    raise SpotifyAPIError(msg)
                if allow_empty and not response.content:
                    return {}
                parsed: Any = response.json()
                if not isinstance(parsed, dict):
                    msg = "Spotify 回應不是 JSON object"
                    raise SpotifyAPIError(msg)
                return parsed
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= MAX_LOOP:
                    break
                self._sleep(min(2**attempt, 8))
        msg = f"Spotify API 在 {MAX_LOOP} 次嘗試後仍失敗"
        raise SpotifyAPIError(msg) from last_error

    def list_show_episodes(self, show_id: str, market: str) -> list[dict[str, Any]]:
        """最多翻 MAX_LOOP 頁（每頁 PAGE_LIMIT 筆），由新到舊。"""
        items: list[dict[str, Any]] = []
        url: str | None = (
            f"{SPOTIFY_API_BASE}/shows/{show_id}/episodes?market={market}&limit={PAGE_LIMIT}"
        )
        for _page in range(MAX_LOOP):
            if url is None:
                break
            payload = self._request_json("GET", url, headers=self._auth_headers())
            page_items = payload.get("items") or []
            if not isinstance(page_items, list):
                msg = "episodes.items 格式錯誤"
                raise SpotifyAPIError(msg)
            for episode in page_items:
                if isinstance(episode, dict):
                    items.append(episode)
            next_url = payload.get("next")
            url = next_url if isinstance(next_url, str) else None
        return items

    def replace_playlist_items(self, playlist_id: str, episode_uris: list[str]) -> None:
        """以當天單集覆寫整個播放清單（空清單也會清空）。"""
        chunks: list[list[str]] = []
        if not episode_uris:
            chunks.append([])
        else:
            for index in range(0, len(episode_uris), PLAYLIST_REPLACE_CHUNK):
                chunks.append(episode_uris[index : index + PLAYLIST_REPLACE_CHUNK])
                if len(chunks) >= MAX_LOOP:
                    break
        first = True
        for chunk in chunks[:MAX_LOOP]:
            if first:
                url = f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks"
                self._request_json(
                    "PUT",
                    url,
                    headers=self._auth_headers(),
                    json_body={"uris": chunk},
                    allow_empty=True,
                )
                first = False
            else:
                url = f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks"
                self._request_json(
                    "POST",
                    url,
                    headers=self._auth_headers(),
                    json_body={"uris": chunk},
                    allow_empty=True,
                )
        logger.info("播放清單 %s 已覆寫，單集數=%s", playlist_id, len(episode_uris))
