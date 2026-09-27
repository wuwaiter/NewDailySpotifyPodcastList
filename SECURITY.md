# 資安說明

## 密鑰存放

- Spotify：`SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`、`SPOTIFY_REFRESH_TOKEN`
- YouTube：`YOUTUBE_CLIENT_ID`、`YOUTUBE_CLIENT_SECRET`、`YOUTUBE_REFRESH_TOKEN`
- 以上只能放在環境變數或 GitHub Actions Secrets。
- 禁止寫進 `project.toml`、git commit 或 Issue。
- 本機請複製 `.env.example` 為 `.env`，該檔已列入 `.gitignore`。

## 程式內建防護

- Spotify 只連線 `api.spotify.com` 與 `accounts.spotify.com`（HTTPS）。
- YouTube 只連線 `www.googleapis.com` 與 `oauth2.googleapis.com`（HTTPS）。
- `project.toml` 使用標準庫 `tomllib` 解析，並拒絕含 `client_secret` / token / `api_key` 的設定檔。
- Spotify ID 只接受 22 字元 ID、`spotify:` URI 或 `open.spotify.com` URL。
- YouTube 只接受 `UC` 頻道 ID、`PL` 播放清單 ID，或 `youtube.com/channel`、`youtube.com/playlist` 官方 URL。
- HTTP 重試與分頁上限為 5，避免無限迴圈與過大請求。
- log 會遮罩 `Authorization` 與常見密鑰欄位。
- OAuth 授權碼流程限定 redirect 到 `http://127.0.0.1`。
- GitHub Actions 僅授予 `contents: read`。

## 若密鑰外洩

1. 到 Spotify Developer Dashboard 或 Google Cloud Console 輪替 Client Secret。
2. 撤銷並重新授權以取得新的 refresh token。
3. 更新 GitHub Secrets。
4. 檢查 git 歷史是否曾提交密鑰，必要時輪替後改寫歷史或廢棄該 token。
