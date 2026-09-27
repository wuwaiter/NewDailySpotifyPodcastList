from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from spotify_daily_podcasts.config import AppConfig
from spotify_daily_podcasts.sync import sync_all


class FakeSpotifyClient:
    def __init__(self) -> None:
        self.replaced: dict[str, list[str]] = {}

    def list_show_episodes(self, show_id: str, market: str) -> list[dict[str, Any]]:
        today = "2026-09-21"
        return [
            {
                "id": f"{show_id[:12]}todayxxxxxx",
                "uri": f"spotify:episode:{show_id[:12]}todayxxxxxx",
                "name": f"{show_id} today",
                "release_date": today,
                "release_date_precision": "day",
            },
            {
                "id": f"{show_id[:12]}oldxxxxxxxx",
                "uri": f"spotify:episode:{show_id[:12]}oldxxxxxxxx",
                "name": "old",
                "release_date": "2026-09-20",
                "release_date_precision": "day",
            },
        ]

    def replace_playlist_items(self, playlist_id: str, episode_uris: list[str]) -> None:
        self.replaced[playlist_id] = episode_uris


class FakeYouTubeClient:
    def __init__(self) -> None:
        self.replaced: dict[str, list[str]] = {}

    def list_channel_videos(self, channel_id: str) -> list[dict[str, Any]]:
        return [
            {
                "snippet": {
                    "title": f"{channel_id} today",
                    "publishedAt": "2026-09-21T08:00:00Z",
                    "resourceId": {"kind": "youtube#video", "videoId": f"{channel_id[:8]}today01"},
                }
            },
            {
                "snippet": {
                    "title": "old",
                    "publishedAt": "2026-09-20T08:00:00Z",
                    "resourceId": {"kind": "youtube#video", "videoId": f"{channel_id[:8]}old0001"},
                }
            },
        ]

    def replace_playlist_items(self, playlist_id: str, video_ids: list[str]) -> None:
        self.replaced[playlist_id] = video_ids


def test_sync_all_multiple_playlists() -> None:
    config = AppConfig.model_validate(
        {
            "timezone": "Asia/Taipei",
            "market": "TW",
            "spotify": {
                "playlists": [
                    {
                        "name": "清單一",
                        "playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
                        "channel_ids": ["4rOoJ6Egrf8K2IrywzwOMk", "2MAi0BvDc6GTFvKFPXnkCL"],
                    },
                    {
                        "name": "清單二",
                        "playlist_id": "37i9dQZF1DX0XUsuxWHRQd",
                        "channel_ids": ["5CnDmMUG0S5bSSw612fs8C"],
                    },
                ]
            },
        }
    )
    fake = FakeSpotifyClient()
    report = sync_all(
        config,
        spotify_client=fake,  # type: ignore[arg-type]
        dry_run=False,
        now=datetime(2026, 9, 21, 1, 0, tzinfo=ZoneInfo("Asia/Taipei")),
        platforms={"spotify"},
    )
    assert report.target_date == date(2026, 9, 21)
    assert len(report.spotify) == 2
    assert len(report.spotify[0].added) == 2
    assert len(report.spotify[1].added) == 1
    assert len(fake.replaced) == 2


def test_dry_run_does_not_write() -> None:
    config = AppConfig.model_validate(
        {
            "timezone": "UTC",
            "market": "US",
            "spotify": {
                "playlists": [
                    {
                        "name": "Only",
                        "playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
                        "channel_ids": ["4rOoJ6Egrf8K2IrywzwOMk"],
                    }
                ]
            },
        }
    )
    fake = FakeSpotifyClient()
    report = sync_all(
        config,
        spotify_client=fake,  # type: ignore[arg-type]
        dry_run=True,
        now=datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo("UTC")),
        platforms={"spotify"},
    )
    assert report.dry_run is True
    assert fake.replaced == {}
    assert len(report.spotify[0].added) == 1


def test_cross_show_episode_dedupe() -> None:
    class DupClient:
        replaced: dict[str, list[str]] = {}

        def list_show_episodes(self, show_id: str, market: str) -> list[dict[str, Any]]:
            return [
                {
                    "id": "sharedsharedsharedshar1",
                    "uri": "spotify:episode:sharedsharedsharedshar1",
                    "name": "同一集",
                    "release_date": "2026-09-21",
                    "release_date_precision": "day",
                }
            ]

        def replace_playlist_items(self, playlist_id: str, episode_uris: list[str]) -> None:
            self.replaced[playlist_id] = episode_uris

    config = AppConfig.model_validate(
        {
            "timezone": "UTC",
            "market": "US",
            "spotify": {
                "playlists": [
                    {
                        "name": "Only",
                        "playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
                        "channel_ids": ["4rOoJ6Egrf8K2IrywzwOMk", "2MAi0BvDc6GTFvKFPXnkCL"],
                    }
                ]
            },
        }
    )
    client = DupClient()
    report = sync_all(
        config,
        spotify_client=client,  # type: ignore[arg-type]
        now=datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo("UTC")),
        platforms={"spotify"},
    )
    assert len(report.spotify[0].added) == 1
    assert client.replaced["37i9dQZF1DXcBWIGoYBM5M"] == ["spotify:episode:sharedsharedsharedshar1"]


def test_youtube_sync_filters_today() -> None:
    config = AppConfig.model_validate(
        {
            "timezone": "UTC",
            "market": "US",
            "youtube": {
                "playlists": [
                    {
                        "name": "YT",
                        "playlist_id": "PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
                        "channel_ids": ["UCzzzzzzzzzzzzzzzzzzzzzz"],
                    }
                ]
            },
        }
    )
    fake = FakeYouTubeClient()
    report = sync_all(
        config,
        youtube_client=fake,  # type: ignore[arg-type]
        now=datetime(2026, 9, 21, 12, 0, tzinfo=ZoneInfo("UTC")),
        platforms={"youtube"},
    )
    assert len(report.youtube) == 1
    assert len(report.youtube[0].added) == 1
    assert fake.replaced["PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"] == ["UCzzzzzztoday01"]
