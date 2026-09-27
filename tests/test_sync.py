from datetime import date, datetime
from zoneinfo import ZoneInfo

from spotify_daily_podcasts.sync import (
    parse_published_at,
    parse_release_date,
    select_today_episodes,
    select_today_videos,
    today_in_timezone,
)


def test_today_in_taipei_across_utc_midnight() -> None:
    now = datetime(2026, 9, 21, 16, 0, tzinfo=ZoneInfo("UTC"))
    assert today_in_timezone("Asia/Taipei", now) == date(2026, 9, 22)


def test_parse_release_date_requires_day_precision() -> None:
    assert parse_release_date("2026-09-21", "day") == date(2026, 9, 21)
    assert parse_release_date("2026-09", "month") is None
    assert parse_release_date("not-a-date", "day") is None


def test_parse_published_at() -> None:
    assert parse_published_at("2026-09-21T08:00:00Z") == date(2026, 9, 21)
    assert parse_published_at("not-a-date") is None


def test_select_today_episodes_filters_and_dedupes() -> None:
    episodes = [
        {
            "id": "aaaaaaaaaaaaaaaaaaaaaa",
            "uri": "spotify:episode:aaaaaaaaaaaaaaaaaaaaaa",
            "name": "今日集",
            "release_date": "2026-09-21",
            "release_date_precision": "day",
        },
        {
            "id": "aaaaaaaaaaaaaaaaaaaaaa",
            "uri": "spotify:episode:aaaaaaaaaaaaaaaaaaaaaa",
            "name": "重複",
            "release_date": "2026-09-21",
            "release_date_precision": "day",
        },
        {
            "id": "bbbbbbbbbbbbbbbbbbbbbb",
            "uri": "spotify:episode:bbbbbbbbbbbbbbbbbbbbbb",
            "name": "昨天",
            "release_date": "2026-09-20",
            "release_date_precision": "day",
        },
        {
            "id": "cccccccccccccccccccccc",
            "uri": "spotify:track:cccccccccccccccccccccc",
            "name": "不是單集",
            "release_date": "2026-09-21",
            "release_date_precision": "day",
        },
        {
            "id": None,
            "uri": "spotify:episode:dddddddddddddddddddddd",
            "name": "缺 id",
            "release_date": "2026-09-21",
            "release_date_precision": "day",
        },
    ]
    selected, skipped = select_today_episodes(
        episodes,
        channel_id="showshowshowshowshowsh",
        target=date(2026, 9, 21),
    )
    assert [ep.id for ep in selected] == ["aaaaaaaaaaaaaaaaaaaaaa"]
    assert skipped == 3


def test_select_today_videos_filters_and_dedupes() -> None:
    items = [
        {
            "snippet": {
                "title": "今日",
                "publishedAt": "2026-09-21T01:00:00Z",
                "resourceId": {"videoId": "abcdefghijk"},
            }
        },
        {
            "snippet": {
                "title": "重複",
                "publishedAt": "2026-09-21T02:00:00Z",
                "resourceId": {"videoId": "abcdefghijk"},
            }
        },
        {
            "snippet": {
                "title": "昨天",
                "publishedAt": "2026-09-20T01:00:00Z",
                "resourceId": {"videoId": "oldvideo111"},
            }
        },
        {"snippet": {"title": "缺 id", "publishedAt": "2026-09-21T01:00:00Z"}},
    ]
    selected, skipped = select_today_videos(
        items,
        channel_id="UCzzzzzzzzzzzzzzzzzzzzzz",
        target=date(2026, 9, 21),
    )
    assert [item.id for item in selected] == ["abcdefghijk"]
    assert skipped == 2
