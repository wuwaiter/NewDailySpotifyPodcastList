"""project.toml：Spotify / YouTube 播放清單與頻道對應。僅在執行時載入。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from spotify_daily_podcasts.constants import (
    DEFAULT_TIMEZONE,
    SPOTIFY_ID_LENGTH,
    YOUTUBE_CHANNEL_ID_LENGTH,
    YOUTUBE_PLAYLIST_ID_MAX,
    YOUTUBE_PLAYLIST_ID_MIN,
)

_SPOTIFY_ID_RE = re.compile(rf"^[A-Za-z0-9]{{{SPOTIFY_ID_LENGTH}}}$")
_YOUTUBE_CHANNEL_RE = re.compile(rf"^UC[A-Za-z0-9_-]{{{YOUTUBE_CHANNEL_ID_LENGTH - 2}}}$")
_YOUTUBE_PLAYLIST_RE = re.compile(
    rf"^PL[A-Za-z0-9_-]{{{YOUTUBE_PLAYLIST_ID_MIN - 2},{YOUTUBE_PLAYLIST_ID_MAX - 2}}}$"
)
_NAME_RE = re.compile(r"^[\w\s\-./（）()（）：:：]+$", re.UNICODE)
_FORBIDDEN_SECRET_MARKERS = (
    "client_secret",
    "refresh_token",
    "access_token",
    "api_key",
    "SPOTIFY_CLIENT_SECRET",
    "YOUTUBE_CLIENT_SECRET",
)


def _validate_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or not _NAME_RE.match(cleaned):
        msg = "playlist name 含有不允許的字元"
        raise ValueError(msg)
    return cleaned


def _dedupe(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


class SpotifyPlaylistConfig(BaseModel):
    """單一 Spotify 播放清單：對應多個 Podcast 頻道（show）。"""

    name: str = Field(min_length=1, max_length=200)
    playlist_id: str
    channel_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_name(value)

    @field_validator("playlist_id")
    @classmethod
    def validate_playlist_id(cls, value: str) -> str:
        return _require_spotify_id(value, "playlist_id")

    @field_validator("channel_ids")
    @classmethod
    def validate_channel_ids(cls, values: list[str]) -> list[str]:
        unique = _dedupe([_require_spotify_id(item, "channel_id") for item in values])
        if not unique:
            msg = "channel_ids 不可為空"
            raise ValueError(msg)
        return unique


class YouTubePlaylistConfig(BaseModel):
    """單一 YouTube 播放清單：對應多個頻道。"""

    name: str = Field(min_length=1, max_length=200)
    playlist_id: str
    channel_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_name(value)

    @field_validator("playlist_id")
    @classmethod
    def validate_playlist_id(cls, value: str) -> str:
        extracted = extract_youtube_playlist_id(value)
        if extracted is None:
            msg = "youtube playlist_id 必須是 PL 開頭的官方 ID 或 youtube.com/playlist URL"
            raise ValueError(msg)
        return extracted

    @field_validator("channel_ids")
    @classmethod
    def validate_channel_ids(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in values:
            cid = extract_youtube_channel_id(item)
            if cid is None:
                msg = "youtube channel_id 必須是 UC 開頭的官方 ID 或 youtube.com/channel URL"
                raise ValueError(msg)
            if cid in seen:
                continue
            seen.add(cid)
            unique.append(cid)
        if not unique:
            msg = "channel_ids 不可為空"
            raise ValueError(msg)
        return unique


class SpotifySection(BaseModel):
    playlists: list[SpotifyPlaylistConfig] = Field(default_factory=list, max_length=20)


class YouTubeSection(BaseModel):
    playlists: list[YouTubePlaylistConfig] = Field(default_factory=list, max_length=20)


class AppConfig(BaseModel):
    timezone: str = DEFAULT_TIMEZONE
    market: str = "TW"
    spotify: SpotifySection = Field(default_factory=SpotifySection)
    youtube: YouTubeSection = Field(default_factory=YouTubeSection)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            msg = f"未知時區: {value}"
            raise ValueError(msg) from exc
        return value

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{2}", value):
            msg = "market 必須是 ISO 3166-1 alpha-2（例如 TW）"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def unique_playlist_ids_and_nonempty(self) -> AppConfig:
        spotify_ids = [p.playlist_id for p in self.spotify.playlists]
        youtube_ids = [p.playlist_id for p in self.youtube.playlists]
        if len(spotify_ids) != len(set(spotify_ids)):
            msg = "spotify playlist_id 不可重複"
            raise ValueError(msg)
        if len(youtube_ids) != len(set(youtube_ids)):
            msg = "youtube playlist_id 不可重複"
            raise ValueError(msg)
        if not spotify_ids and not youtube_ids:
            msg = "project.toml 至少需要一個 spotify 或 youtube 播放清單"
            raise ValueError(msg)
        return self


def _require_spotify_id(value: str, field: str) -> str:
    extracted = extract_spotify_id(value)
    if extracted is None or not _SPOTIFY_ID_RE.fullmatch(extracted):
        msg = f"{field} 必須是 22 字元 Spotify ID 或官方 URL/URI"
        raise ValueError(msg)
    return extracted


def extract_spotify_id(value: str) -> str | None:
    """只接受 Spotify ID、spotify: URI 或 open.spotify.com URL，拒絕任意外部網址。"""
    raw = value.strip()
    if _SPOTIFY_ID_RE.fullmatch(raw):
        return raw
    uri = re.fullmatch(r"spotify:(?:playlist|show):([A-Za-z0-9]{22})", raw)
    if uri:
        return uri.group(1)
    url = re.fullmatch(
        r"https://open\.spotify\.com/(?:playlist|show)/([A-Za-z0-9]{22})(?:\?.*)?",
        raw,
    )
    if url:
        return url.group(1)
    return None


def extract_youtube_playlist_id(value: str) -> str | None:
    raw = value.strip()
    if _YOUTUBE_PLAYLIST_RE.fullmatch(raw):
        return raw
    url = re.fullmatch(
        r"https://(?:www\.)?youtube\.com/playlist\?list=(PL[A-Za-z0-9_-]+)",
        raw,
    )
    if url and _YOUTUBE_PLAYLIST_RE.fullmatch(url.group(1)):
        return url.group(1)
    return None


def extract_youtube_channel_id(value: str) -> str | None:
    raw = value.strip()
    if _YOUTUBE_CHANNEL_RE.fullmatch(raw):
        return raw
    url = re.fullmatch(
        r"https://(?:www\.)?youtube\.com/channel/(UC[A-Za-z0-9_-]{22})(?:[/?].*)?",
        raw,
    )
    if url and _YOUTUBE_CHANNEL_RE.fullmatch(url.group(1)):
        return url.group(1)
    return None


def load_config(path: str | Path) -> AppConfig:
    """讀取 project.toml。呼叫端應只在 CLI / 排程執行時使用，勿在模組 import 時呼叫。"""
    config_path = Path(path)
    if not config_path.is_file():
        msg = f"找不到設定檔: {config_path}"
        raise FileNotFoundError(msg)
    text = config_path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"project.toml 不是有效的 TOML: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(data, dict):
        msg = "設定檔根節點必須是 table"
        raise ValueError(msg)
    if _contains_forbidden_keys(data):
        msg = "設定檔不可包含密鑰欄位，請改用環境變數 / GitHub Secrets"
        raise ValueError(msg)
    return AppConfig.model_validate(data)


def _contains_forbidden_keys(data: object) -> bool:
    if isinstance(data, dict):
        for key, value in data.items():
            lowered = str(key).lower()
            if any(marker.lower() == lowered for marker in _FORBIDDEN_SECRET_MARKERS):
                return True
            if _contains_forbidden_keys(value):
                return True
        return False
    if isinstance(data, list):
        return any(_contains_forbidden_keys(item) for item in data)
    return False
