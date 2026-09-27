from datetime import date

from spotify_daily_podcasts.cli import _report_to_dict, main
from spotify_daily_podcasts.sync import MediaRef, PlaylistSyncResult, SyncReport


def test_validate_config_ok() -> None:
    assert main(["--validate-config", "--config", "project.toml"]) == 0


def test_validate_config_missing() -> None:
    assert main(["--validate-config", "--config", "not-there.toml"]) == 2


def test_missing_secrets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for key in (
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REFRESH_TOKEN",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    assert main(["--config", "project.toml"]) == 2


def test_dry_run_with_fake_clients(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "clientidvalue")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "clientsecretvalue")
    monkeypatch.setenv("SPOTIFY_REFRESH_TOKEN", "refreshtokenvalue")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "youtubeidvalue.apps.googleusercontent.com")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "youtubesecretval")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "youtuberefreshval")

    class FakeSpotify:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def list_show_episodes(self, show_id: str, market: str) -> list[dict[str, str]]:
            return []

        def replace_playlist_items(self, playlist_id: str, uris: list[str]) -> None:
            raise AssertionError("dry-run 不應寫入")

    class FakeYouTube:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> object:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def list_channel_videos(self, channel_id: str) -> list[dict[str, str]]:
            return []

        def replace_playlist_items(self, playlist_id: str, video_ids: list[str]) -> None:
            raise AssertionError("dry-run 不應寫入")

    monkeypatch.setattr("spotify_daily_podcasts.cli.SpotifyClient", FakeSpotify)
    monkeypatch.setattr("spotify_daily_podcasts.cli.YouTubeClient", FakeYouTube)
    assert main(["--dry-run", "--config", "project.toml"]) == 0
    output = capsys.readouterr().out
    assert "item_count" in output
    assert "spotify" in output
    assert "youtube" in output


def test_report_to_dict_shape() -> None:
    report = SyncReport(
        target_date=date(2026, 9, 21),
        dry_run=True,
        spotify=[
            PlaylistSyncResult(
                platform="spotify",
                name="A",
                playlist_id="aaaaaaaaaaaaaaaaaaaaa1",
                added=[
                    MediaRef(
                        id="e",
                        uri="spotify:episode:e",
                        name="今日",
                        channel_id="s",
                        release_date=date(2026, 9, 21),
                        platform="spotify",
                    )
                ],
            )
        ],
    )
    payload = _report_to_dict(report)
    assert payload["target_date"] == "2026-09-21"
    spotify = payload["spotify"]
    assert isinstance(spotify, dict)
    playlists = spotify["playlists"]
    assert isinstance(playlists, list)
    assert playlists[0]["item_count"] == 1  # type: ignore[index]
