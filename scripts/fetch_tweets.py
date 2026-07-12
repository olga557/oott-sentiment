"""Ежедневный сбор твитов #OOTT через twitterapi.io.

Ключ читается из .env (TWITTERAPI_IO_KEY). По умолчанию собирает вчерашний
день UTC; можно явно указать даты:

    python3 scripts/fetch_tweets.py                # вчера (UTC)
    python3 scripts/fetch_tweets.py 2026-07-12     # конкретный день
    python3 scripts/fetch_tweets.py 2026-07-01 2026-07-05   # диапазон включительно

Результат: data/raw/YYYY-MM-DD.jsonl (перезаписывается целиком — запуск идемпотентен).
Логика пагинации с fallback по времени взята из исходного ноутбука пользователя.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROJECT_ROOT, RAW_DIR, normalize_api_tweet, parse_created_at, write_daily_jsonl

URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"
BASE_TAG = "#oott"

PAUSE_BETWEEN_PAGES = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_BACKOFF = 2
MAX_PAGES = 2000
MAX_FALLBACKS = 50


def load_api_key() -> str:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TWITTERAPI_IO_KEY=") and not line.startswith("#"):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key and key != "your_key_here":
                    return key
    sys.exit("Ошибка: не найден TWITTERAPI_IO_KEY. Скопируйте .env.example в .env и вставьте ключ.")


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def make_query(since_dt: datetime, until_dt: datetime) -> str:
    fmt = "%Y-%m-%d_%H:%M:%S_UTC"
    return f"{BASE_TAG} since:{since_dt.strftime(fmt)} until:{until_dt.strftime(fmt)}"


def fetch_page(session, headers, query, cursor):
    params = {"queryType": "Latest", "query": query, "cursor": cursor}
    resp = session.get(URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data.get("tweets", []), data.get("has_next_page", False), data.get("next_cursor", "")


def fetch_window(session, headers, since_dt: datetime, until_dt: datetime) -> list[dict]:
    """Собирает все твиты окна [since, until) с пагинацией и fallback по времени."""
    all_tweets: dict[str, dict] = {}
    window_until = until_dt
    query = make_query(since_dt, window_until)
    cursor = ""
    seen_cursors: set[str] = set()
    fallbacks = 0
    page = 1

    def time_fallback(tweets_on_page: list[dict]) -> bool:
        """Сдвигает окно к самому старому известному твиту. False = двигаться некуда."""
        nonlocal window_until, query, cursor, seen_cursors, fallbacks
        dates = [parse_created_at(t.get("createdAt", "")) for t in (tweets_on_page or list(all_tweets.values()))]
        dates = [d for d in dates if d is not None]
        if not dates or fallbacks >= MAX_FALLBACKS:
            return False
        window_until = min(dates) - timedelta(seconds=1)
        if window_until <= since_dt:
            return False
        query = make_query(since_dt, window_until)
        cursor = ""
        seen_cursors.clear()
        fallbacks += 1
        print(f"  fallback -> until {window_until:%Y-%m-%d %H:%M:%S} UTC")
        return True

    while page <= MAX_PAGES:
        if cursor in seen_cursors:
            if not time_fallback([]):
                break
            continue
        seen_cursors.add(cursor)

        tweets, has_next, next_cursor, = fetch_page(session, headers, query, cursor)
        new = 0
        for t in tweets:
            tid = str(t.get("id", ""))
            if tid and tid not in all_tweets:
                all_tweets[tid] = t
                new += 1
        print(f"  стр. {page}: {len(tweets)} твитов, новых {new}, всего {len(all_tweets)}")
        page += 1

        if not has_next:
            break
        if not next_cursor or next_cursor == cursor or (tweets and new == 0):
            if not time_fallback(tweets):
                break
            time.sleep(PAUSE_BETWEEN_PAGES)
            continue
        cursor = next_cursor
        time.sleep(PAUSE_BETWEEN_PAGES)

    return list(all_tweets.values())


def main() -> None:
    args = sys.argv[1:]
    if not args:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        start_date = end_date = day
    elif len(args) == 1:
        start_date = end_date = datetime.strptime(args[0], "%Y-%m-%d").date()
    else:
        start_date = datetime.strptime(args[0], "%Y-%m-%d").date()
        end_date = datetime.strptime(args[1], "%Y-%m-%d").date()

    headers = {"X-API-Key": load_api_key()}
    session = create_session()

    since_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    until_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    print(f"Сбор {BASE_TAG} за {start_date} .. {end_date} (UTC)")

    raw = fetch_window(session, headers, since_dt, until_dt)
    records = [r for r in (normalize_api_tweet(t) for t in raw) if r is not None]
    # Страховка от твитов за границей окна
    records = [r for r in records if str(start_date) <= r["date"] <= str(end_date)]

    counts = write_daily_jsonl(records, RAW_DIR)
    for day, n in sorted(counts.items()):
        print(f"  {day}: {n} твитов -> data/raw/{day}.jsonl")
    if not counts:
        print("Твитов не найдено.")


if __name__ == "__main__":
    main()
