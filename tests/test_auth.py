from spotify_daily_podcasts.auth import SpotifyAPIError, _pkce_pair, build_parser, main


def test_pkce_pair_is_urlsafe() -> None:
    verifier, challenge = _pkce_pair()
    assert len(verifier) > 32
    assert len(challenge) > 20
    assert verifier != challenge


def test_auth_rejects_non_local_redirect() -> None:
    assert (
        main(
            [
                "--client-id",
                "clientidvalue",
                "--client-secret",
                "clientsecretvalue",
                "--redirect-uri",
                "https://evil.example/callback",
            ]
        )
        == 2
    )


def test_auth_parser_defaults() -> None:
    args = build_parser().parse_args(["--client-id", "abc", "--client-secret", "def"])
    assert "127.0.0.1" in args.redirect_uri


def test_auth_success_prints_refresh(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "spotify_daily_podcasts.auth.run_auth",
        lambda *a, **k: "refresh-token-value",
    )
    assert main(["--client-id", "clientidvalue", "--client-secret", "clientsecretvalue"]) == 0
    assert "refresh-token-value" in capsys.readouterr().out


def test_auth_api_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def boom(*args: object, **kwargs: object) -> str:
        raise SpotifyAPIError("denied")

    monkeypatch.setattr("spotify_daily_podcasts.auth.run_auth", boom)
    assert main(["--client-id", "clientidvalue", "--client-secret", "clientsecretvalue"]) == 1
