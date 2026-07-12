"""Общие утилиты: канонический формат твита и парсинг дат.

Канонический сырой твит (data/raw/YYYY-MM-DD.jsonl, по одному JSON на строку)
имеет фиксированный набор полей независимо от источника (Excel-бэкфилл или
живой запрос к twitterapi.io). Всё остальное в пайплайне читает только его.
"""
from __future__ import annotations

import ast
import json
import math
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched"
DAILY_DIR = PROJECT_ROOT / "data" / "daily"
BATCHES_DIR = PROJECT_ROOT / "data" / "batches"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "dashboard" / "data"

TWITTER_DATE_FMT = "%a %b %d %H:%M:%S %z %Y"  # Sat Jul 11 23:53:46 +0000 2026


def parse_created_at(raw: str) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    for fmt in (TWITTER_DATE_FMT, "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _clean(value, default=None):
    """NaN/None -> default; остальное как есть."""
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return value


def _to_int(value) -> int:
    value = _clean(value, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_bool(value) -> bool:
    value = _clean(value, False)
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _to_str(value) -> str:
    value = _clean(value, "")
    return str(value).strip()


def parse_hashtags(value) -> list[str]:
    """entities.hashtags: список dict-ов (из API) либо их строковое представление (из Excel)."""
    value = _clean(value)
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return []
    if not isinstance(value, list):
        return []
    tags = []
    for item in value:
        if isinstance(item, dict) and item.get("text"):
            tags.append(str(item["text"]))
    return tags


def normalize_api_tweet(t: dict) -> dict | None:
    """Твит из ответа twitterapi.io -> канонический формат."""
    dt = parse_created_at(t.get("createdAt", ""))
    if dt is None or not t.get("id"):
        return None
    author = t.get("author") or {}
    quoted = t.get("quoted_tweet") or None
    return _build_record(
        tweet_id=str(t["id"]),
        url=_to_str(t.get("url")) or f"https://x.com/i/status/{t['id']}",
        text=_to_str(t.get("text")),
        dt=dt,
        lang=_to_str(t.get("lang")),
        source=_to_str(t.get("source")),
        retweets=_to_int(t.get("retweetCount")),
        replies=_to_int(t.get("replyCount")),
        likes=_to_int(t.get("likeCount")),
        quotes=_to_int(t.get("quoteCount")),
        views=_to_int(t.get("viewCount")),
        bookmarks=_to_int(t.get("bookmarkCount")),
        is_reply=_to_bool(t.get("isReply")),
        hashtags=parse_hashtags((t.get("entities") or {}).get("hashtags")),
        author_username=_to_str(author.get("userName")),
        author_name=_to_str(author.get("name")),
        author_followers=_to_int(author.get("followers")),
        author_blue=_to_bool(author.get("isBlueVerified")),
        author_automated=_to_bool(author.get("isAutomated")),
        author_location=_to_str(author.get("location")),
        quoted_text=_to_str(quoted.get("text")) if isinstance(quoted, dict) else "",
        quoted_author=_to_str((quoted.get("author") or {}).get("userName")) if isinstance(quoted, dict) else "",
    )


def normalize_excel_row(row: dict) -> dict | None:
    """Строка из pandas-экселя (плоские колонки с точками) -> канонический формат."""
    dt = parse_created_at(_to_str(row.get("createdAt")))
    tweet_id = _clean(row.get("id"))
    if dt is None or tweet_id is None:
        return None
    tweet_id = str(int(tweet_id)) if not isinstance(tweet_id, str) else tweet_id
    return _build_record(
        tweet_id=tweet_id,
        url=_to_str(row.get("url")) or f"https://x.com/i/status/{tweet_id}",
        text=_to_str(row.get("text")),
        dt=dt,
        lang=_to_str(row.get("lang")),
        source=_to_str(row.get("source")),
        retweets=_to_int(row.get("retweetCount")),
        replies=_to_int(row.get("replyCount")),
        likes=_to_int(row.get("likeCount")),
        quotes=_to_int(row.get("quoteCount")),
        views=_to_int(row.get("viewCount")),
        bookmarks=_to_int(row.get("bookmarkCount")),
        is_reply=_to_bool(row.get("isReply")),
        hashtags=parse_hashtags(row.get("entities.hashtags")),
        author_username=_to_str(row.get("author.userName")),
        author_name=_to_str(row.get("author.name")),
        author_followers=_to_int(row.get("author.followers")),
        author_blue=_to_bool(row.get("author.isBlueVerified")),
        author_automated=_to_bool(row.get("author.isAutomated")),
        author_location=_to_str(row.get("author.location")),
        quoted_text=_to_str(row.get("quoted_tweet.text")),
        quoted_author=_to_str(row.get("quoted_tweet.author.userName")),
    )


def _build_record(**kw) -> dict:
    return {
        "id": kw["tweet_id"],
        "url": kw["url"],
        "text": kw["text"],
        "created_at": kw["dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": kw["dt"].strftime("%Y-%m-%d"),
        "hour": kw["dt"].hour,
        "lang": kw["lang"],
        "source": kw["source"],
        "retweets": kw["retweets"],
        "replies": kw["replies"],
        "likes": kw["likes"],
        "quotes": kw["quotes"],
        "views": kw["views"],
        "bookmarks": kw["bookmarks"],
        "is_reply": kw["is_reply"],
        "hashtags": kw["hashtags"],
        "author": {
            "username": kw["author_username"],
            "name": kw["author_name"],
            "followers": kw["author_followers"],
            "blue_verified": kw["author_blue"],
            "automated": kw["author_automated"],
            "location": kw["author_location"],
        },
        "quoted": (
            {"text": kw["quoted_text"], "author": kw["quoted_author"]}
            if kw["quoted_text"]
            else None
        ),
    }


def write_daily_jsonl(records: list[dict], out_dir: Path = RAW_DIR) -> dict[str, int]:
    """Раскладывает записи по файлам data/raw/YYYY-MM-DD.jsonl (сортировка по времени)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, list[dict]] = {}
    for r in records:
        by_day.setdefault(r["date"], []).append(r)
    counts = {}
    for day, items in sorted(by_day.items()):
        items.sort(key=lambda r: r["created_at"])
        path = out_dir / f"{day}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in items:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[day] = len(items)
    return counts


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
