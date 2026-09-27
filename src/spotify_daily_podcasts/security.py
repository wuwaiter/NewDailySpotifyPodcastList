"""敏感資訊處理：禁止把 token / secret 寫進 log。"""

from __future__ import annotations

import re

_SECRET_KEYS = (
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "api_key",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_REFRESH_TOKEN",
    "SPOTIFY_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
    "YOUTUBE_CLIENT_ID",
)

_TOKEN_RE = re.compile(
    r"(Bearer\s+)[A-Za-z0-9._~+/-]+=*",
    re.IGNORECASE,
)


def redact(value: str) -> str:
    """將可能含 token 的字串遮罩後回傳。"""
    redacted = _TOKEN_RE.sub(r"\1[REDACTED]", value)
    for key in _SECRET_KEYS:
        redacted = re.sub(
            rf"({re.escape(key)}\s*[:=]\s*)([^\s&,]+)",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
    return redacted


def is_secret_key(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    return any(key.lower() == lowered or key.lower() in lowered for key in _SECRET_KEYS)


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """複製 headers，遮罩 Authorization。"""
    out: dict[str, str] = {}
    for key, val in headers.items():
        if key.lower() in {"authorization", "proxy-authorization"}:
            out[key] = "Bearer [REDACTED]"
        else:
            out[key] = val
    return out
