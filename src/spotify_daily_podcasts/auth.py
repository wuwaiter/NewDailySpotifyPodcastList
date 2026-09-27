"""本機一次性 OAuth：取得 refresh_token，供 GitHub Actions 使用。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import logging
import secrets
import sys
import urllib.parse
import webbrowser
from typing import Any

import httpx

from spotify_daily_podcasts.constants import (
    DEFAULT_REDIRECT_URI,
    HTTP_TIMEOUT_SECONDS,
    SPOTIFY_ACCOUNTS_BASE,
)
from spotify_daily_podcasts.security import redact
from spotify_daily_podcasts.spotify_client import SpotifyAPIError, _assert_allowed_url

logger = logging.getLogger(__name__)

SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    query: dict[str, list[str]] = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        type(self).query = urllib.parse.parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("授權完成，可以關閉此視窗。".encode())

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug(redact(fmt % args))


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


def run_auth(client_id: str, client_secret: str, redirect_uri: str) -> str:
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    authorize_url = f"{SPOTIFY_ACCOUNTS_BASE}/authorize?{urllib.parse.urlencode(params)}"
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    server = http.server.HTTPServer((host, port), _CallbackHandler)
    print("請在瀏覽器開啟以下網址完成 Spotify 授權：")
    print(authorize_url)
    try:
        webbrowser.open(authorize_url)
    except OSError:
        logger.debug("無法自動開啟瀏覽器")
    server.handle_request()
    server.server_close()
    query = _CallbackHandler.query
    if query.get("state", [None])[0] != state:
        msg = "OAuth state 不符，已中止"
        raise SpotifyAPIError(msg)
    error = query.get("error", [None])[0]
    if error:
        msg = f"授權被拒絕: {error}"
        raise SpotifyAPIError(msg)
    code = query.get("code", [None])[0]
    if not code:
        msg = "未取得 authorization code"
        raise SpotifyAPIError(msg)
    token_url = f"{SPOTIFY_ACCOUNTS_BASE}/api/token"
    _assert_allowed_url(token_url)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as token_client:
        response = token_client.post(
            token_url,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
    if response.status_code >= 400:
        msg = f"交換 token 失敗: {redact(response.text[:300])}"
        raise SpotifyAPIError(msg)
    payload = response.json()
    refresh = payload.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        msg = "回應缺少 refresh_token"
        raise SpotifyAPIError(msg)
    return refresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本機授權並印出 SPOTIFY_REFRESH_TOKEN")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args(argv)
    if not args.redirect_uri.startswith("http://127.0.0.1"):
        logger.error("redirect URI 只允許本機 127.0.0.1，避免把授權碼送到外部主機")
        return 2
    try:
        refresh = run_auth(args.client_id, args.client_secret, args.redirect_uri)
    except SpotifyAPIError as exc:
        logger.error("%s", exc)
        return 1
    print("請把下面這個值存成 GitHub Secret：SPOTIFY_REFRESH_TOKEN")
    print(refresh)
    print("請勿把 refresh token 提交到 git。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
