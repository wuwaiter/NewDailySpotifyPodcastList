# NewDailySpotifyPodcastList 系統架構

本專案沒有常駐伺服器。排程與執行都在 **GitHub Actions**；Python 程式只在 CI 或本機一次性跑完即結束。

工作目錄可以是任何本機路徑，不要寫死某一台開發機的絕對路徑。

播放清單與頻道定義在根目錄 `project.toml`，**只在排程 / CLI 執行時讀取**。

## 1. 部署與執行環境

```mermaid
flowchart TB
  subgraph local ["本機開發環境"]
    src["工作複本（任意路徑）"]
    toml["project.toml\nspotify / youtube 播放清單 ↔ 頻道"]
    authS["Spotify 一次性 OAuth"]
    authY["YouTube 一次性 OAuth"]
    src --> toml
    src --> authS
    src --> authY
  end

  subgraph gha ["GitHub Actions"]
    secrets["GitHub Secrets\nSPOTIFY_* / YOUTUBE_*"]
    ci["ci.yml\nlint · 測試 · bandit · pip-audit · gitleaks"]
    sync["sync.yml\ncron 每天 22:00 UTC\n執行時讀取 project.toml"]
  end

  subgraph py ["Python 套件 spotify_daily_podcasts"]
    cli["cli.py\n執行時 load_config"]
    cfg["config.py\nTOML 驗證"]
    sec["security.py\nlog 遮罩"]
    spotify["spotify_client.py"]
    youtube["youtube_client.py"]
    engine["sync.py\n只保留當天內容"]
    cli --> cfg
    cli --> spotify
    cli --> youtube
    cli --> engine
    spotify --> sec
    youtube --> sec
  end

  subgraph apis ["外部 API"]
    spotifyApi["api.spotify.com"]
    youtubeApi["www.googleapis.com/youtube"]
  end

  toml --> sync
  authS --> secrets
  authY --> secrets
  secrets --> sync
  src -->|push / PR| ci
  ci --> py
  sync --> py
  engine --> spotify
  engine --> youtube
  spotify --> spotifyApi
  youtube --> youtubeApi
```

## 2. 每日同步資料流

```mermaid
sequenceDiagram
  autonumber
  participant Cron as GitHub Actions 排程
  participant CLI as python -m spotify_daily_podcasts
  participant Cfg as project.toml
  participant S as Spotify API
  participant Y as YouTube Data API

  Cron->>CLI: checkout 後注入 Secrets
  CLI->>Cfg: 此時才讀取並驗證
  alt 有 Spotify 播放清單
    CLI->>S: refresh token → 讀頻道單集 → 覆寫清單
  end
  alt 有 YouTube 播放清單
    CLI->>Y: refresh token → 讀頻道影片 → 覆寫清單
  end
```

## 3. 設定模型

```mermaid
erDiagram
  APP_CONFIG ||--o{ SPOTIFY_PLAYLIST : spotify
  APP_CONFIG ||--o{ YOUTUBE_PLAYLIST : youtube
  SPOTIFY_PLAYLIST ||--|{ SPOTIFY_CHANNEL : channel_ids
  YOUTUBE_PLAYLIST ||--|{ YOUTUBE_CHANNEL : channel_ids
  APP_CONFIG {
    string timezone
    string market
  }
  SPOTIFY_PLAYLIST {
    string name
    string playlist_id
  }
  YOUTUBE_PLAYLIST {
    string name
    string playlist_id
  }
```

同一份 `project.toml` 可同時宣告兩個平台；平台之間互不共用清單內容。至少需要一個播放清單。

## 4. CI/CD

```mermaid
flowchart LR
  push["git push / PR"] --> ciJob["CI job"]
  ciJob --> ruff["ruff"]
  ciJob --> mypy["mypy"]
  ciJob --> tests["pytest cov≥80%"]
  ciJob --> bandit["bandit"]
  ciJob --> audit["pip-audit"]
  ciJob --> leaks["gitleaks"]
  ciJob --> validate["--validate-config"]

  sched["cron / 手動"] --> syncJob["Sync job"]
  syncJob --> readToml["讀取當下的 project.toml"]
  syncJob --> run["同步或 --dry-run"]
```

Dependabot 每週掃描 `pip` 與 `github-actions` 依賴。

## 5. 資安邊界

```mermaid
flowchart TB
  ok["允許"]
  deny["拒絕"]

  ok --> env["環境變數 / GitHub Secrets"]
  ok --> hosts["Spotify 官方主機與 Google YouTube API 主機"]
  ok --> ids["Spotify 22 字元 ID、YouTube UC/PL ID、官方 URL"]

  deny --> tomlSecrets["project.toml 內的 secret / token / api_key"]
  deny --> ssrf["任意外部 URL"]
  deny --> loop["超過 5 次的重試或分頁"]
  deny --> logs["明文 Authorization header"]
```

OAuth 授權碼流程僅允許 redirect 到 `http://127.0.0.1`，在本機完成後把 refresh token 存進 GitHub Secrets。
