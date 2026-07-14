"""Ежедневный сбор твитов через twitterapi.io: #OOTT + from:JavierBlas.

Ключ читается из .env (TWITTERAPI_IO_KEY). По умолчанию собирает вчерашний
день UTC; можно явно указать даты:

    python3 scripts/fetch_tweets.py                # вчера (UTC), оба источника
    python3 scripts/fetch_tweets.py 2026-07-12     # конкретный день
    python3 scripts/fetch_tweets.py 2026-07-01 2026-07-05   # диапазон включительно

    # только JavierBlas с вливанием в уже собранные raw-файлы (бэкфилл автора):
    python3 scripts/fetch_tweets.py 2026-06-01 2026-07-13 --only from:JavierBlas --merge

Результат: data/raw/YYYY-MM-DD.jsonl.
Без --merge файл дня перезаписывается целиком (идемпотентный дневной запуск).
С --merge новые твиты дополняют существующие по id.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    PROJECT_ROOT,
    RAW_DIR,
    normalize_api_tweet,
    parse_created_at,
    read_jsonl,
    write_daily_jsonl,
)

URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"

# Оба источника ежедневно; пересечения (#oott у JavierBlas) дедуплируются по id.
DEFAULT_QUERIES = ["#oott", "from:JavierBlas"]

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


def make_query(base: str, since_dt: datetime, until_dt: datetime) -> str:
    fmt = "%Y-%m-%d_%H:%M:%S_UTC"
    return f"{base} since:{since_dt.strftime(fmt)} until:{until_dt.strftime(fmt)}"


def fetch_page(session, headers, query, cursor):
    params = {"queryType": "Latest", "query": query, "cursor": cursor}
    resp = session.get(URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data.get("tweets", []), data.get("has_next_page", False), data.get("next_cursor", "")


def fetch_window(session, headers, base: str, since_dt: datetime, until_dt: datetime) -> list[dict]:
    """Собирает все твиты окна [since, until) по одному query base с пагинацией и fallback."""
    all_tweets: dict[str, dict] = {}
    window_until = until_dt
    query = make_query(base, since_dt, window_until)
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
        query = make_query(base, since_dt, window_until)
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

        tweets, has_next, next_cursor = fetch_page(session, headers, query, cursor)
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


def write_records(records: list[dict], *, merge: bool) -> dict[str, int]:
    """Пишет data/raw; при merge дополняет существующие дни по tweet id."""
    if not merge:
        return write_daily_jsonl(records, RAW_DIR)

    by_day: dict[str, dict[str, dict]] = {}
    for r in records:
        by_day.setdefault(r["date"], {})[r["id"]] = r

    counts: dict[str, int] = {}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for day, incoming in sorted(by_day.items()):
        path = RAW_DIR / f"{day}.jsonl"
        existing = {r["id"]: r for r in read_jsonl(path)}
        before = len(existing)
        existing.update(incoming)
        merged = sorted(existing.values(), key=lambda r: r["created_at"])
        with open(path, "w", encoding="utf-8") as f:
            for r in merged:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        added = len(existing) - before
        counts[day] = len(merged)
        print(f"  merge {day}: было {before}, +{added} новых, итого {len(merged)}")
    return counts


def parse_args(argv: list[str]):
    only: str | None = None
    merge = False
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--merge":
            merge = True
        elif a == "--only":
            i += 1
            if i >= len(argv):
                sys.exit("Ошибка: --only требует значение, напр. from:JavierBlas")
            only = argv[i]
        elif a.startswith("-"):
            sys.exit(f"Неизвестный флаг: {a}")
        else:
            pos.append(a)
        i += 1

    if not pos:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        start_date = end_date = day
    elif len(pos) == 1:
        start_date = end_date = datetime.strptime(pos[0], "%Y-%m-%d").date()
    else:
        start_date = datetime.strptime(pos[0], "%Y-%m-%d").date()
        end_date = datetime.strptime(pos[1], "%Y-%m-%d").date()

    queries = [only] if only else list(DEFAULT_QUERIES)
    return start_date, end_date, queries, merge


def main() -> None:
    start_date, end_date, queries, merge = parse_args(sys.argv[1:])

    headers = {"X-API-Key": load_api_key()}
    session = create_session()

    since_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    until_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    print(f"Сбор {', '.join(queries)} за {start_date} .. {end_date} (UTC)"
          + (" [merge]" if merge else ""))

    by_id: dict[str, dict] = {}
    for base in queries:
        print(f"→ {base}")
        for t in fetch_window(session, headers, base, since_dt, until_dt):
            tid = str(t.get("id", ""))
            if tid:
                by_id[tid] = t

    records = [r for r in (normalize_api_tweet(t) for t in by_id.values()) if r is not None]
    records = [r for r in records if str(start_date) <= r["date"] <= str(end_date)]

    counts = write_records(records, merge=merge)
    for day, n in sorted(counts.items()):
        print(f"  {day}: {n} твитов -> data/raw/{day}.jsonl")
    if not counts:
        print("Твитов не найдено.")


if __name__ == "__main__":
    main()
