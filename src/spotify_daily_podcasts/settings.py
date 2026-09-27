"""環境變數憑證。密鑰只來自環境，不寫入檔案、也不放進 project.toml。"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _no_whitespace(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        msg = "憑證不可為空或含空白"
        raise ValueError(msg)
    return cleaned


class SpotifySecrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPOTIFY_",
        extra="ignore",
        env_file=None,
    )

    client_id: str = Field(min_length=8, max_length=128)
    client_secret: str = Field(min_length=8, max_length=128)
    refresh_token: str = Field(min_length=8, max_length=2048)

    @field_validator("client_id", "client_secret", "refresh_token")
    @classmethod
    def no_whitespace(cls, value: str) -> str:
        return _no_whitespace(value)


class YouTubeSecrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YOUTUBE_",
        extra="ignore",
        env_file=None,
    )

    client_id: str = Field(min_length=8, max_length=256)
    client_secret: str = Field(min_length=8, max_length=128)
    refresh_token: str = Field(min_length=8, max_length=2048)

    @field_validator("client_id", "client_secret", "refresh_token")
    @classmethod
    def no_whitespace(cls, value: str) -> str:
        return _no_whitespace(value)
