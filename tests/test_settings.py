import pytest
from pydantic import ValidationError

from spotify_daily_podcasts.settings import SpotifySecrets, YouTubeSecrets


def test_secrets_reject_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "clientidvalue")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "client secret")
    monkeypatch.setenv("SPOTIFY_REFRESH_TOKEN", "refreshtokenvalue")
    with pytest.raises(ValidationError):
        SpotifySecrets()  # type: ignore[call-arg]


def test_secrets_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "clientidvalue")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "clientsecretvalue")
    monkeypatch.setenv("SPOTIFY_REFRESH_TOKEN", "refreshtokenvalue")
    secrets = SpotifySecrets()  # type: ignore[call-arg]
    assert secrets.client_id == "clientidvalue"


def test_youtube_secrets_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "youtubeidvalue.apps.googleusercontent.com")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "youtubesecretval")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "youtuberefreshval")
    secrets = YouTubeSecrets()  # type: ignore[call-arg]
    assert secrets.client_id.endswith("googleusercontent.com")
