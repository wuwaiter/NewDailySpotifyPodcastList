from pathlib import Path

import pytest

from spotify_daily_podcasts.config import (
    extract_spotify_id,
    extract_youtube_channel_id,
    extract_youtube_playlist_id,
    load_config,
)
from spotify_daily_podcasts.constants import DEFAULT_CONFIG_PATH


def test_default_config_path_is_project_toml() -> None:
    assert DEFAULT_CONFIG_PATH == "project.toml"


def test_load_project_toml() -> None:
    config = load_config(Path("project.toml"))
    assert len(config.spotify.playlists) == 2
    assert config.spotify.playlists[0].channel_ids
    assert config.spotify.playlists[1].channel_ids
    assert len(config.youtube.playlists) == 1
    assert config.youtube.playlists[0].channel_ids[0].startswith("UC")


def test_import_does_not_require_project_toml() -> None:
    from spotify_daily_podcasts import config as config_module

    assert callable(config_module.load_config)


def test_rejects_secrets_in_toml(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(
        'timezone = "Asia/Taipei"\nmarket = "TW"\nclient_secret = "leaked"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="密鑰"):
        load_config(path)


def test_rejects_duplicate_playlist_ids(tmp_path: Path) -> None:
    path = tmp_path / "dup.toml"
    path.write_text(
        """
timezone = "UTC"
market = "US"

[[spotify.playlists]]
name = "A"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = ["4rOoJ6Egrf8K2IrywzwOMk"]

[[spotify.playlists]]
name = "B"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = ["2MAi0BvDc6GTFvKFPXnkCL"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重複"):
        load_config(path)


def test_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("does-not-exist.toml")


def test_rejects_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("this is not toml [[[", encoding="utf-8")
    with pytest.raises(ValueError, match="TOML"):
        load_config(path)


def test_requires_at_least_one_playlist(tmp_path: Path) -> None:
    path = tmp_path / "empty.toml"
    path.write_text('timezone = "UTC"\nmarket = "US"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="至少需要一個"):
        load_config(path)


def test_invalid_timezone_and_market(tmp_path: Path) -> None:
    path = tmp_path / "tz.toml"
    path.write_text(
        """
timezone = "Not/AZone"
market = "TW"

[[spotify.playlists]]
name = "A"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = ["4rOoJ6Egrf8K2IrywzwOMk"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="時區"):
        load_config(path)

    path.write_text(
        """
timezone = "UTC"
market = "tw"

[[spotify.playlists]]
name = "A"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = ["4rOoJ6Egrf8K2IrywzwOMk"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="market"):
        load_config(path)


def test_invalid_playlist_name(tmp_path: Path) -> None:
    path = tmp_path / "name.toml"
    path.write_text(
        """
timezone = "UTC"
market = "US"

[[spotify.playlists]]
name = "bad <script>"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = ["4rOoJ6Egrf8K2IrywzwOMk"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="不允許"):
        load_config(path)


def test_extract_spotify_id_blocks_arbitrary_urls() -> None:
    assert extract_spotify_id("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"
    assert (
        extract_spotify_id("https://open.spotify.com/show/4rOoJ6Egrf8K2IrywzwOMk")
        == "4rOoJ6Egrf8K2IrywzwOMk"
    )
    assert extract_spotify_id("https://evil.example/show/4rOoJ6Egrf8K2IrywzwOMk") is None
    assert extract_spotify_id("spotify:show:4rOoJ6Egrf8K2IrywzwOMk") == "4rOoJ6Egrf8K2IrywzwOMk"


def test_extract_youtube_ids_blocks_arbitrary_urls() -> None:
    playlist = "PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
    channel = "UCzzzzzzzzzzzzzzzzzzzzzz"
    assert extract_youtube_playlist_id(playlist) == playlist
    assert (
        extract_youtube_playlist_id(f"https://www.youtube.com/playlist?list={playlist}")
        == playlist
    )
    assert extract_youtube_playlist_id("https://evil.example/playlist?list=" + playlist) is None
    assert extract_youtube_channel_id(channel) == channel
    assert extract_youtube_channel_id(f"https://www.youtube.com/channel/{channel}") == channel
    assert extract_youtube_channel_id("https://evil.example/channel/" + channel) is None


def test_duplicate_channel_ids_are_deduped(tmp_path: Path) -> None:
    path = tmp_path / "shows.toml"
    path.write_text(
        """
timezone = "UTC"
market = "US"

[[spotify.playlists]]
name = "A"
playlist_id = "37i9dQZF1DXcBWIGoYBM5M"
channel_ids = [
  "4rOoJ6Egrf8K2IrywzwOMk",
  "4rOoJ6Egrf8K2IrywzwOMk",
]
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.spotify.playlists[0].channel_ids == ["4rOoJ6Egrf8K2IrywzwOMk"]
