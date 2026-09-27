"""將各播放清單同步成「當天」更新的單集或影片。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from spotify_daily_podcasts.config import AppConfig, SpotifyPlaylistConfig, YouTubePlaylistConfig
from spotify_daily_podcasts.spotify_client import SpotifyClient
from spotify_daily_podcasts.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaRef:
    id: str
    uri: str
    name: str
    channel_id: str
    release_date: date
    platform: str


@dataclass
class PlaylistSyncResult:
    platform: str
    name: str
    playlist_id: str
    added: list[MediaRef] = field(default_factory=list)
    skipped_stale: int = 0


@dataclass
class SyncReport:
    target_date: date
    dry_run: bool
    spotify: list[PlaylistSyncResult] = field(default_factory=list)
    youtube: list[PlaylistSyncResult] = field(default_factory=list)


def today_in_timezone(tz_name: str, now: datetime | None = None) -> date:
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now is not None else datetime.now(tz)
    return current.date()


def parse_release_date(raw: str, precision: str) -> date | None:
    if precision != "day":
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_published_at(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def select_today_episodes(
    episodes: list[dict[str, Any]],
    *,
    channel_id: str,
    target: date,
) -> tuple[list[MediaRef], int]:
    selected: list[MediaRef] = []
    skipped = 0
    seen: set[str] = set()
    for item in episodes:
        episode_id = item.get("id")
        uri = item.get("uri")
        name = item.get("name") or ""
        raw_date = item.get("release_date") or ""
        precision = item.get("release_date_precision") or "day"
        if not isinstance(episode_id, str) or not isinstance(uri, str):
            skipped += 1
            continue
        if not uri.startswith("spotify:episode:"):
            skipped += 1
            continue
        released = parse_release_date(str(raw_date), str(precision))
        if released is None or released != target:
            skipped += 1
            continue
        if episode_id in seen:
            continue
        seen.add(episode_id)
        selected.append(
            MediaRef(
                id=episode_id,
                uri=uri,
                name=str(name),
                channel_id=channel_id,
                release_date=released,
                platform="spotify",
            )
        )
    selected.sort(key=lambda ep: (ep.release_date, ep.name, ep.id), reverse=True)
    return selected, skipped


def select_today_videos(
    items: list[dict[str, Any]],
    *,
    channel_id: str,
    target: date,
) -> tuple[list[MediaRef], int]:
    selected: list[MediaRef] = []
    skipped = 0
    seen: set[str] = set()
    for item in items:
        raw_snippet = item.get("snippet")
        snippet: dict[str, Any] = raw_snippet if isinstance(raw_snippet, dict) else {}
        raw_resource = snippet.get("resourceId")
        resource: dict[str, Any] = raw_resource if isinstance(raw_resource, dict) else {}
        raw_details = item.get("contentDetails")
        details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
        video_id = resource.get("videoId") or details.get("videoId")
        name = snippet.get("title") or ""
        published = snippet.get("publishedAt") or ""
        if not isinstance(video_id, str) or not video_id:
            skipped += 1
            continue
        released = parse_published_at(str(published))
        if released is None or released != target:
            skipped += 1
            continue
        if video_id in seen:
            continue
        seen.add(video_id)
        selected.append(
            MediaRef(
                id=video_id,
                uri=f"youtube:video:{video_id}",
                name=str(name),
                channel_id=channel_id,
                release_date=released,
                platform="youtube",
            )
        )
    selected.sort(key=lambda vid: (vid.release_date, vid.name, vid.id), reverse=True)
    return selected, skipped


def _dedupe_media(items: list[MediaRef]) -> list[MediaRef]:
    unique: list[MediaRef] = []
    seen_ids: set[str] = set()
    for item in items:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        unique.append(item)
    return unique


def sync_spotify_playlist(
    client: SpotifyClient,
    playlist: SpotifyPlaylistConfig,
    *,
    market: str,
    target: date,
    dry_run: bool,
) -> PlaylistSyncResult:
    collected: list[MediaRef] = []
    skipped_total = 0
    for channel_id in playlist.channel_ids:
        episodes = client.list_show_episodes(channel_id, market)
        today_eps, skipped = select_today_episodes(
            episodes,
            channel_id=channel_id,
            target=target,
        )
        collected.extend(today_eps)
        skipped_total += skipped
        logger.info(
            "Spotify 頻道 %s：當天 %s 集、略過 %s 筆",
            channel_id,
            len(today_eps),
            skipped,
        )
    unique = _dedupe_media(collected)
    result = PlaylistSyncResult(
        platform="spotify",
        name=playlist.name,
        playlist_id=playlist.playlist_id,
        added=unique,
        skipped_stale=skipped_total,
    )
    uris = [ep.uri for ep in unique]
    if dry_run:
        logger.info("[dry-run] Spotify %s 將寫入 %s 集", playlist.name, len(uris))
        return result
    client.replace_playlist_items(playlist.playlist_id, uris)
    return result


def sync_youtube_playlist(
    client: YouTubeClient,
    playlist: YouTubePlaylistConfig,
    *,
    target: date,
    dry_run: bool,
) -> PlaylistSyncResult:
    collected: list[MediaRef] = []
    skipped_total = 0
    for channel_id in playlist.channel_ids:
        videos = client.list_channel_videos(channel_id)
        today_videos, skipped = select_today_videos(
            videos,
            channel_id=channel_id,
            target=target,
        )
        collected.extend(today_videos)
        skipped_total += skipped
        logger.info(
            "YouTube 頻道 %s：當天 %s 部、略過 %s 筆",
            channel_id,
            len(today_videos),
            skipped,
        )
    unique = _dedupe_media(collected)
    result = PlaylistSyncResult(
        platform="youtube",
        name=playlist.name,
        playlist_id=playlist.playlist_id,
        added=unique,
        skipped_stale=skipped_total,
    )
    video_ids = [item.id for item in unique]
    if dry_run:
        logger.info("[dry-run] YouTube %s 將寫入 %s 部", playlist.name, len(video_ids))
        return result
    client.replace_playlist_items(playlist.playlist_id, video_ids)
    return result


def sync_all(
    config: AppConfig,
    *,
    spotify_client: SpotifyClient | None = None,
    youtube_client: YouTubeClient | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    platforms: set[str] | None = None,
) -> SyncReport:
    target = today_in_timezone(config.timezone, now)
    wanted = platforms or {"spotify", "youtube"}
    logger.info("目標日期 %s（時區 %s）dry_run=%s", target.isoformat(), config.timezone, dry_run)
    spotify_results: list[PlaylistSyncResult] = []
    youtube_results: list[PlaylistSyncResult] = []
    if "spotify" in wanted and config.spotify.playlists:
        if spotify_client is None:
            msg = "已設定 Spotify 播放清單但缺少 Spotify 用戶端"
            raise ValueError(msg)
        for spotify_playlist in config.spotify.playlists:
            spotify_results.append(
                sync_spotify_playlist(
                    spotify_client,
                    spotify_playlist,
                    market=config.market,
                    target=target,
                    dry_run=dry_run,
                )
            )
    if "youtube" in wanted and config.youtube.playlists:
        if youtube_client is None:
            msg = "已設定 YouTube 播放清單但缺少 YouTube 用戶端"
            raise ValueError(msg)
        for youtube_playlist in config.youtube.playlists:
            youtube_results.append(
                sync_youtube_playlist(
                    youtube_client,
                    youtube_playlist,
                    target=target,
                    dry_run=dry_run,
                )
            )
    return SyncReport(
        target_date=target,
        dry_run=dry_run,
        spotify=spotify_results,
        youtube=youtube_results,
    )
