# NewDailySpotifyPodcastList

用 **Python + GitHub Actions** 每天把指定頻道「當天更新」的內容，覆寫進 Spotify 與／或 YouTube 播放清單。不依賴 IFTTT。

播放清單裡只會留下當天的單集或影片：前一天的內容會在下次同步時被清空。

播放清單與頻道對應寫在專案根目錄的 [`project.toml`](project.toml)。**排程或本機執行時才讀取**，套件被 import 時不會載入。

系統架構圖見 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 本機路徑

此 repo 可放在任何目錄。不要把某一台機器的絕對路徑寫進程式、文件或腳本。

```bash
git clone <你的-repo-URL>
cd NewDailySpotifyPodcastList
```

## 功能

- Spotify 與 YouTube 可並存：每個平台多個播放清單，每個清單對應多個頻道
- 依設定時區計算「今天」（預設 `Asia/Taipei`）
- HTTP 重試、分頁、批次寫入的迴圈上限皆為 **5**
- CI：pytest、ruff、mypy、bandit、pip-audit、gitleaks
- CD：排程 Action 每日同步，也可手動 `workflow_dispatch`

## 快速開始

### 1. 建立應用程式

**Spotify**

1. 開啟 [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. 建立 App，Redirect URI 設為 `http://127.0.0.1:43821/callback`
3. 記下 Client ID 與 Client Secret

**YouTube**

1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)
2. 啟用 YouTube Data API v3，建立 OAuth 用戶端
3. Redirect URI 設為 `http://127.0.0.1:43822/callback`

### 2. 本機安裝

需要 Python 3.11+。建議使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra dev
```

或使用 pip：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. 取得 refresh token（每個平台各一次，在本機執行）

```bash
uv run python -m spotify_daily_podcasts.auth \
  --client-id "$SPOTIFY_CLIENT_ID" \
  --client-secret "$SPOTIFY_CLIENT_SECRET"

uv run python -m spotify_daily_podcasts.youtube_auth \
  --client-id "$YOUTUBE_CLIENT_ID" \
  --client-secret "$YOUTUBE_CLIENT_SECRET"
```

瀏覽器授權後，把印出的值分別存成 GitHub Secret `SPOTIFY_REFRESH_TOKEN` 與 `YOUTUBE_REFRESH_TOKEN`。**不要 commit。**

### 4. 設定播放清單與頻道

編輯根目錄 `project.toml`：

```toml
timezone = "Asia/Taipei"
market = "TW"

[[spotify.playlists]]
name = "每日科技 Podcast"
playlist_id = "你的Spotify播放清單ID"
channel_ids = ["頻道ID一", "頻道ID二"]

[[youtube.playlists]]
name = "每日科技 YouTube"
playlist_id = "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
channel_ids = ["UCxxxxxxxxxxxxxxxxxxxxxx"]
```

ID 可從官方分享連結取得：

- Spotify 播放清單 `https://open.spotify.com/playlist/{playlist_id}`
- Spotify 頻道 `https://open.spotify.com/show/{show_id}`
- YouTube 播放清單 `https://www.youtube.com/playlist?list={playlist_id}`
- YouTube 頻道 `https://www.youtube.com/channel/{channel_id}`

請先在各平台帳號下**建立空白播放清單**（程式會覆寫其內容）。未使用的平台可省略對應的 `[[...playlists]]` 區塊。

驗證設定（只讀 `project.toml`，不呼叫 API）：

```bash
uv run python -m spotify_daily_podcasts --validate-config
```

預覽當天內容、不寫入：

```bash
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
export SPOTIFY_REFRESH_TOKEN=...
export YOUTUBE_CLIENT_ID=...
export YOUTUBE_CLIENT_SECRET=...
export YOUTUBE_REFRESH_TOKEN=...
uv run python -m spotify_daily_podcasts --dry-run
```

只跑單一平台：`--platform spotify` 或 `--platform youtube`。

### 5. GitHub Actions Secrets

在 repo Settings → Secrets and variables → Actions 新增實際會用到的項目：

| Secret | 說明 |
| --- | --- |
| `SPOTIFY_CLIENT_ID` | Spotify App Client ID |
| `SPOTIFY_CLIENT_SECRET` | Spotify App Client Secret |
| `SPOTIFY_REFRESH_TOKEN` | 本機授權取得的 Spotify refresh token |
| `YOUTUBE_CLIENT_ID` | Google OAuth Client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth Client Secret |
| `YOUTUBE_REFRESH_TOKEN` | 本機授權取得的 YouTube refresh token |

`project.toml` 裡有設定哪個平台，同步時就需要該平台的 Secrets。

推送到 GitHub 後：

- `.github/workflows/ci.yml` 會在 push / PR 跑測試與掃描
- `.github/workflows/sync.yml` 每天 22:00 UTC（台北約隔日 06:00）讀取當時的 `project.toml` 再同步；也可在 Actions 頁手動執行，並可勾選 dry-run

## 測試

```bash
uv run pytest
uv run ruff check src tests
uv run mypy src
uv run bandit -r src -c pyproject.toml
```

## 專案結構

```
NewDailySpotifyPodcastList/
  project.toml                 # 播放清單 ↔ 頻道（執行時才讀取）
  ARCHITECTURE.md
  src/spotify_daily_podcasts/  # 同步邏輯與 API 用戶端
  tests/
  .github/workflows/ci.yml
  .github/workflows/sync.yml
```

## 資安

見 [SECURITY.md](SECURITY.md)。`project.toml` 不得放入任何 token。
