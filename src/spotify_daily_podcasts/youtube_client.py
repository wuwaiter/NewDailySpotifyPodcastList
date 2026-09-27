"""帶上限 5 次的 HTTP 重試與 YouTube Data API 用戶端。"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from spotify_daily_podcasts.constants import (
    GOOGLE_OAUTH_URL,
    HTTP_TIMEOUT_SECONDS,
    MAX_LOOP,
    PAGE_LIMIT,
    YOUTUBE_API_BASE,
)
from spotify_daily_podcasts.security import redact, safe_headers
from spotify_daily_podcasts.settings import YouTubeSecrets

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = {"www.googleapis.com", "oauth2.googleapis.com"}


class YouTubeAPIError(RuntimeError):
    """YouTube API 呼叫失敗。"""


def _assert_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        msg = "拒絕連到非 YouTube / Google API 官方主機"
        raise YouTubeAPIError(msg)


class YouTubeClient:
    def __init__(
        self,
        secrets: YouTubeSecrets,
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

    def __enter__(self) -> YouTubeClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def refresh_access_token(self) -> str:
        _assert_allowed_url(GOOGLE_OAUTH_URL)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._secrets.refresh_token,
            "client_id": self._secrets.client_id,
            "client_secret": self._secrets.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = self._request_json("POST", GOOGLE_OAUTH_URL, headers=headers, data=data)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            msg = "token 回應缺少 access_token"
            raise YouTubeAPIError(msg)
        self._access_token = token
        logger.info("已更新 YouTube access token")
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
        params: dict[str, str] | None = None,
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
                    params=params,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_LOOP:
                    retry_after = float(response.headers.get("Retry-After", attempt))
                    wait_s = min(max(retry_after, 0.0), 30.0)
                    logger.warning(
                        "YouTube 暫時失敗 status=%s，%ss 後重試",
                        response.status_code,
                        wait_s,
                    )
                    self._sleep(wait_s)
                    continue
                if (
                    response.status_code == 401
                    and attempt < MAX_LOOP
                    and "oauth2.googleapis.com" not in url
                ):
                    logger.warning("access token 失效，重新整理後重試")
                    self.refresh_access_token()
                    headers = {**headers, **self._auth_headers()}
                    continue
                if response.status_code >= 400:
                    body = redact(response.text[:500])
                    msg = f"YouTube API {response.status_code}: {body}"
                    raise YouTubeAPIError(msg)
                if allow_empty and not response.content:
                    return {}
                parsed: Any = response.json()
                if not isinstance(parsed, dict):
                    msg = "YouTube 回應不是 JSON object"
                    raise YouTubeAPIError(msg)
                return parsed
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= MAX_LOOP:
                    break
                self._sleep(min(2**attempt, 8))
        msg = f"YouTube API 在 {MAX_LOOP} 次嘗試後仍失敗"
        raise YouTubeAPIError(msg) from last_error

    def list_channel_videos(self, channel_id: str) -> list[dict[str, Any]]:
        """讀取頻道上傳清單，最多翻 MAX_LOOP 頁。"""
        uploads = self._uploads_playlist_id(channel_id)
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        for _page in range(MAX_LOOP):
            params = {
                "part": "snippet,contentDetails",
                "playlistId": uploads,
                "maxResults": str(PAGE_LIMIT),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                "GET",
                f"{YOUTUBE_API_BASE}/playlistItems",
                headers=self._auth_headers(),
                params=params,
            )
            page_items = payload.get("items") or []
            if not isinstance(page_items, list):
                msg = "playlistItems.items 格式錯誤"
                raise YouTubeAPIError(msg)
            for video in page_items:
                if isinstance(video, dict):
                    items.append(video)
            next_token = payload.get("nextPageToken")
            page_token = next_token if isinstance(next_token, str) and next_token else None
            if page_token is None:
                break
        return items

    def _uploads_playlist_id(self, channel_id: str) -> str:
        payload = self._request_json(
            "GET",
            f"{YOUTUBE_API_BASE}/channels",
            headers=self._auth_headers(),
            params={"part": "contentDetails", "id": channel_id},
        )
        items = payload.get("items") or []
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            msg = "找不到 YouTube 頻道或 contentDetails"
            raise YouTubeAPIError(msg)
        details = items[0].get("contentDetails")
        if not isinstance(details, dict):
            msg = "頻道缺少 contentDetails"
            raise YouTubeAPIError(msg)
        related = details.get("relatedPlaylists")
        if not isinstance(related, dict):
            msg = "頻道缺少 relatedPlaylists"
            raise YouTubeAPIError(msg)
        uploads = related.get("uploads")
        if not isinstance(uploads, str) or not uploads:
            msg = "頻道缺少 uploads playlist"
            raise YouTubeAPIError(msg)
        return uploads

    def replace_playlist_items(self, playlist_id: str, video_ids: list[str]) -> None:
        """刪除現有項目後寫入當天影片（空清單會清空）。"""
        existing = self._list_playlist_item_ids(playlist_id)
        for item_id in existing:
            self._request_json(
                "DELETE",
                f"{YOUTUBE_API_BASE}/playlistItems",
                headers=self._auth_headers(),
                params={"id": item_id},
                allow_empty=True,
            )
        for video_id in video_ids[: PAGE_LIMIT * MAX_LOOP]:
            self._request_json(
                "POST",
                f"{YOUTUBE_API_BASE}/playlistItems",
                headers=self._auth_headers(),
                params={"part": "snippet"},
                json_body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            )
        logger.info("YouTube 播放清單 %s 已覆寫，影片數=%s", playlist_id, len(video_ids))

    def _list_playlist_item_ids(self, playlist_id: str) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        for _page in range(MAX_LOOP):
            params = {
                "part": "id",
                "playlistId": playlist_id,
                "maxResults": str(PAGE_LIMIT),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                "GET",
                f"{YOUTUBE_API_BASE}/playlistItems",
                headers=self._auth_headers(),
                params=params,
            )
            page_items = payload.get("items") or []
            if not isinstance(page_items, list):
                msg = "playlistItems.items 格式錯誤"
                raise YouTubeAPIError(msg)
            for item in page_items:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    ids.append(str(item["id"]))
            next_token = payload.get("nextPageToken")
            page_token = next_token if isinstance(next_token, str) and next_token else None
            if page_token is None:
                break
        return ids
