from spotify_daily_podcasts.security import is_secret_key, redact, safe_headers


def test_redact_bearer_and_named_secrets() -> None:
    raw = "Authorization: Bearer abcdefghijklmnop client_secret=supersecret"
    out = redact(raw)
    assert "abcdefghijklmnop" not in out
    assert "supersecret" not in out
    assert "[REDACTED]" in out


def test_is_secret_key() -> None:
    assert is_secret_key("Authorization")
    assert is_secret_key("SPOTIFY_CLIENT_SECRET")
    assert is_secret_key("YOUTUBE_CLIENT_SECRET")
    assert not is_secret_key("playlist_id")


def test_safe_headers_masks_authorization() -> None:
    masked = safe_headers({"Authorization": "Bearer tokentoken", "Accept": "application/json"})
    assert masked["Authorization"] == "Bearer [REDACTED]"
    assert masked["Accept"] == "application/json"
