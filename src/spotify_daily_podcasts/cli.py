"""命令列進入點。project.toml 只在此處（執行時）讀取。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from contextlib import ExitStack

from pydantic import ValidationError

from spotify_daily_podcasts.config import AppConfig, load_config
from spotify_daily_podcasts.constants import DEFAULT_CONFIG_PATH
from spotify_daily_podcasts.settings import SpotifySecrets, YouTubeSecrets
from spotify_daily_podcasts.spotify_client import SpotifyClient
from spotify_daily_podcasts.sync import PlaylistSyncResult, SyncReport, sync_all
from spotify_daily_podcasts.youtube_client import YouTubeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("spotify_daily_podcasts")


def _playlists_payload(playlists: list[PlaylistSyncResult]) -> list[dict[str, object]]:
    return [
        {
            "name": item.name,
            "playlist_id": item.playlist_id,
            "item_count": len(item.added),
            "items": [
                {
                    "id": media.id,
                    "name": media.name,
                    "channel_id": media.channel_id,
                    "release_date": media.release_date.isoformat(),
                }
                for media in item.added
            ],
        }
        for item in playlists
    ]


def _report_to_dict(report: SyncReport) -> dict[str, object]:
    return {
        "target_date": report.target_date.isoformat(),
        "dry_run": report.dry_run,
        "spotify": {"playlists": _playlists_payload(report.spotify)},
        "youtube": {"playlists": _playlists_payload(report.youtube)},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="同步 Spotify / YouTube 播放清單：只保留設定頻道當天更新的內容",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="播放清單 TOML 路徑（預設 project.toml，執行時才讀取）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只計算當天內容，不寫入播放清單",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="只驗證 project.toml，不呼叫外部 API",
    )
    parser.add_argument(
        "--platform",
        choices=("all", "spotify", "youtube"),
        default="all",
        help="要同步的平台",
    )
    return parser


def _platforms_for_run(config: AppConfig, platform: str) -> set[str]:
    wanted = {platform} if platform != "all" else {"spotify", "youtube"}
    selected: set[str] = set()
    if "spotify" in wanted and config.spotify.playlists:
        selected.add("spotify")
    if "youtube" in wanted and config.youtube.playlists:
        selected.add("youtube")
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("設定錯誤: %s", exc)
        return 2
    if args.validate_config:
        logger.info(
            "設定檔有效，spotify=%s youtube=%s",
            len(config.spotify.playlists),
            len(config.youtube.playlists),
        )
        return 0
    selected = _platforms_for_run(config, args.platform)
    if not selected:
        logger.error("project.toml 沒有符合 --platform=%s 的播放清單", args.platform)
        return 2
    try:
        spotify_secrets = SpotifySecrets() if "spotify" in selected else None  # type: ignore[call-arg]
        youtube_secrets = YouTubeSecrets() if "youtube" in selected else None  # type: ignore[call-arg]
    except ValidationError as exc:
        logger.error("缺少或無效的環境變數: %s", exc)
        return 2
    with ExitStack() as stack:
        spotify_client = (
            stack.enter_context(SpotifyClient(spotify_secrets)) if spotify_secrets else None
        )
        youtube_client = (
            stack.enter_context(YouTubeClient(youtube_secrets)) if youtube_secrets else None
        )
        report = sync_all(
            config,
            spotify_client=spotify_client,
            youtube_client=youtube_client,
            dry_run=args.dry_run,
            platforms=selected,
        )
    print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
