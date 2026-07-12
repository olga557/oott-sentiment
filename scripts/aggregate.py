"""Строит все агрегаты для дашборда из data/raw + data/enriched + summaries.

    python3 scripts/aggregate.py            # пересчитать всё
    python3 scripts/aggregate.py 2026-07-11 # пересчитать один день + общие файлы

Выход (dashboard/data/):
    index.json          — список дней, диапазон, время генерации
    history.json        — все ряды по дням/месяцам (счётчики, вовлечённость,
                          авторы, индексы сентимента, цена Brent, теплокарта)
    day/YYYY-MM-DD.json — всё для виджетов выбранного дня
    month/YYYY-MM.json  — агрегаты месяца (языки, страны, эмодзи, хэштеги)
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DAILY_DIR, DASHBOARD_DATA_DIR, ENRICHED_DIR, PROJECT_ROOT, RAW_DIR, read_jsonl
from locations import resolve_country

SUMMARIES_DIR = PROJECT_ROOT / "data" / "summaries"
PRICES_FILE = PROJECT_ROOT / "data" / "prices.json"

METRICS = ["views", "likes", "replies", "retweets", "quotes", "bookmarks"]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF\U0001F1E6-\U0001F1FF]"
)
FLAG_RE = re.compile("[\U0001F1E6-\U0001F1FF]{2}")

URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#\w+")
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z''-]{2,}")

STOPWORDS = set("""
the and for are but not you all any can had her was one our out day get has him
his how man new now old see two way who boy did its let put say she too use that
this with have from they will been were said each which their time would there
what about when make like just know take into year your good some could them
than then look only come over think also back after work first well even want
because these give most via amp per says say said gets got getting still being
off very much where why while our ours yours his hers theirs myself yourself
more less many few lot lots every both between during before under above again
does doing done don didn won isn aren wasn weren hasn haven hadn wouldn couldn
shouldn other others another next last week month today yesterday tomorrow
""".split())
# Токены, бессмысленные в облаке слов нефтяного дашборда
DOMAIN_STOP = {"oott", "oil", "crude", "the", "https", "http", "amp"}


# ---------------------------------------------------------------- helpers

def month_of(day: str) -> str:
    return day[:7]


def pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def metric_stats(tweets: list[dict]) -> dict:
    out = {"tweets": len(tweets)}
    for m in METRICS:
        vals = [t[m] for t in tweets]
        out["sum_" + m] = sum(vals)
        out["avg_" + m] = round(sum(vals) / len(vals), 1) if vals else 0
        out["med_" + m] = statistics.median(vals) if vals else 0
    likes, views = out["sum_likes"], out["sum_views"]
    out["engagement_rate"] = round(100.0 * likes / views, 2) if views else 0
    return out


def lang_bucket(lang: str) -> str:
    if not lang or lang in ("und", "zxx", "art"):
        return "unknown"
    if lang in ("qht", "qme", "qam", "qst", "qct"):
        return "service"  # только хэштеги/медиа — не язык
    return lang


def extract_emojis(text: str) -> list[str]:
    found = FLAG_RE.findall(text)
    cleaned = FLAG_RE.sub("", text)
    found += EMOJI_RE.findall(cleaned)
    return found


def extract_words(text: str) -> list[str]:
    text = URL_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = HASHTAG_RE.sub(" ", text)
    words = [w.lower().strip("'-") for w in TOKEN_RE.findall(text)]
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS and w not in DOMAIN_STOP]


def sentiment_counts(tweets: list[dict], field: str, positive: str, negative: str) -> dict:
    """Считает индекс и распределение по полю labels[field]."""
    labeled = [t for t in tweets if t.get("labels")]
    relevant = [t for t in labeled if t["labels"]["relevant"]]
    n = len(relevant)
    pos = sum(1 for t in relevant if t["labels"][field] == positive)
    neg = sum(1 for t in relevant if t["labels"][field] == negative)
    neu = n - pos - neg

    w_total = sum(t["views"] for t in relevant)
    w_pos = sum(t["views"] for t in relevant if t["labels"][field] == positive)
    w_neg = sum(t["views"] for t in relevant if t["labels"][field] == negative)

    return {
        "labeled": len(labeled),
        "relevant": n,
        "pos": pos,
        "neg": neg,
        "neu": neu,
        "index": round(100.0 * (pos - neg) / n, 1) if n else None,
        "index_weighted": round(100.0 * (w_pos - w_neg) / w_total, 1) if w_total else None,
        "opinion_share": pct(pos + neg, n),
    }


def hourly_sentiment(tweets: list[dict], field: str, positive: str, negative: str) -> list[dict]:
    rows = []
    for h in range(24):
        ts = [t for t in tweets if t["hour"] == h and t.get("labels") and t["labels"]["relevant"]]
        rows.append({
            "hour": h,
            "pos": sum(1 for t in ts if t["labels"][field] == positive),
            "neg": sum(1 for t in ts if t["labels"][field] == negative),
            "neu": sum(1 for t in ts if t["labels"][field] not in (positive, negative)),
        })
    return rows


def tweet_card(t: dict) -> dict:
    return {
        "id": t["id"],
        "url": t["url"],
        "text": t["text"][:300],
        "time": t["created_at"][11:16],
        "author": t["author"]["username"],
        "author_name": t["author"]["name"],
        "followers": t["author"]["followers"],
        **{m: t[m] for m in METRICS},
        "labels": t.get("labels"),
    }


# ---------------------------------------------------------------- per-day

def build_day(day: str, all_seen_authors_before: set[str]) -> dict:
    raw = read_jsonl(RAW_DIR / f"{day}.jsonl")
    enriched = {t["id"]: t for t in read_jsonl(ENRICHED_DIR / f"{day}.jsonl")}
    tweets = [enriched.get(t["id"], t) for t in raw]

    authors_today = {t["author"]["username"] for t in tweets}
    new_authors = authors_today - all_seen_authors_before

    hours = [0] * 24
    for t in tweets:
        hours[t["hour"]] += 1

    hourly_eng = []
    for h in range(24):
        ts = [t for t in tweets if t["hour"] == h]
        row = {"tweets": len(ts)}
        for m in METRICS:
            vals = [t[m] for t in ts]
            row["sum_" + m] = sum(vals)
            row["avg_" + m] = round(sum(vals) / len(vals), 1) if vals else 0
            row["med_" + m] = statistics.median(vals) if vals else 0
        hourly_eng.append(row)

    langs = Counter(lang_bucket(t["lang"]) for t in tweets)

    countries: Counter = Counter()
    country_authors: dict[str, set] = defaultdict(set)
    unresolved = 0
    for t in tweets:
        c = resolve_country(t["author"]["location"])
        if c:
            countries[c] += 1
            country_authors[c].add(t["author"]["username"])
        else:
            unresolved += 1

    emojis = Counter()
    for t in tweets:
        emojis.update(extract_emojis(t["text"]))

    words_all, words_bull, words_bear = Counter(), Counter(), Counter()
    for t in tweets:
        ws = extract_words(t["text"])
        words_all.update(ws)
        lab = t.get("labels")
        if lab and lab["relevant"]:
            if lab["price_sentiment"] == "Bullish":
                words_bull.update(ws)
            elif lab["price_sentiment"] == "Bearish":
                words_bear.update(ws)

    tag_counts = Counter()
    edge_counts = Counter()
    for t in tweets:
        tags = sorted({h.lower() for h in t["hashtags"]} - {"oott"})
        tag_counts.update(tags)
        for a, b in combinations(tags, 2):
            edge_counts[(a, b)] += 1
    top_tags = dict(tag_counts.most_common(30))
    edges = [
        {"a": a, "b": b, "w": w}
        for (a, b), w in edge_counts.most_common(120)
        if a in top_tags and b in top_tags
    ]

    top_ids = set()
    for m in METRICS:
        for t in sorted(tweets, key=lambda x: x[m], reverse=True)[:10]:
            top_ids.add(t["id"])
    top_tweets = [tweet_card(t) for t in tweets if t["id"] in top_ids]

    by_author: dict[str, list[dict]] = defaultdict(list)
    for t in tweets:
        by_author[t["author"]["username"]].append(t)
    author_rows = []
    for u, ts in by_author.items():
        author_rows.append({
            "username": u,
            "name": ts[0]["author"]["name"],
            "followers": max(t["author"]["followers"] for t in ts),
            "tweets": len(ts),
            "views": sum(t["views"] for t in ts),
            "likes": sum(t["likes"] for t in ts),
        })
    top_by_tweets = sorted(author_rows, key=lambda a: a["tweets"], reverse=True)[:10]
    top_by_views = sorted(author_rows, key=lambda a: a["views"], reverse=True)[:10]

    bots = sum(1 for t in tweets if t["author"]["automated"])

    price = sentiment_counts(tweets, "price_sentiment", "Bullish", "Bearish")
    emo = sentiment_counts(tweets, "emotional_sentiment", "Positive", "Negative")

    topics = Counter()
    topic_sent: dict[str, Counter] = defaultdict(Counter)
    for t in tweets:
        lab = t.get("labels")
        if lab and lab["relevant"]:
            for topic in lab["topics"]:
                topics[topic] += 1
                topic_sent[topic][lab["price_sentiment"]] += 1
    topic_rows = [
        {"topic": k, "tweets": v, **{s.lower(): topic_sent[k].get(s, 0) for s in ("Bullish", "Bearish", "Neutral")}}
        for k, v in topics.most_common(12)
    ]

    summary = None
    sfile = SUMMARIES_DIR / f"{day}.json"
    if sfile.exists():
        summary = json.loads(sfile.read_text(encoding="utf-8"))

    return {
        "date": day,
        "stats": metric_stats(tweets),
        "unique_authors": len(authors_today),
        "new_authors": len(new_authors),
        "bots": bots,
        "bots_pct": pct(bots, len(tweets)),
        "hours": hours,
        "hourly_engagement": hourly_eng,
        "languages": dict(langs.most_common()),
        "countries": {
            c: {"tweets": n, "authors": len(country_authors[c])} for c, n in countries.most_common()
        },
        "countries_unresolved": unresolved,
        "emojis": dict(emojis.most_common(60)),
        "words": dict(words_all.most_common(80)),
        "words_bullish": dict(words_bull.most_common(60)),
        "words_bearish": dict(words_bear.most_common(60)),
        "hashtags": {"nodes": top_tags, "edges": edges},
        "top_tweets": top_tweets,
        "top_authors_by_tweets": top_by_tweets,
        "top_authors_by_views": top_by_views,
        "sentiment": {
            "price": {**price, "hourly": hourly_sentiment(tweets, "price_sentiment", "Bullish", "Bearish")},
            "emotional": {**emo, "hourly": hourly_sentiment(tweets, "emotional_sentiment", "Positive", "Negative")},
        },
        "topics": topic_rows,
        "summary": summary,
    }


# ---------------------------------------------------------------- per-month

def build_month(month: str, days: list[str]) -> dict:
    tweets = []
    for day in days:
        raw = read_jsonl(RAW_DIR / f"{day}.jsonl")
        enriched = {t["id"]: t for t in read_jsonl(ENRICHED_DIR / f"{day}.jsonl")}
        tweets += [enriched.get(t["id"], t) for t in raw]

    langs = Counter(lang_bucket(t["lang"]) for t in tweets)
    countries: Counter = Counter()
    country_authors: dict[str, set] = defaultdict(set)
    unresolved = 0
    for t in tweets:
        c = resolve_country(t["author"]["location"])
        if c:
            countries[c] += 1
            country_authors[c].add(t["author"]["username"])
        else:
            unresolved += 1
    emojis = Counter()
    for t in tweets:
        emojis.update(extract_emojis(t["text"]))

    return {
        "month": month,
        "stats": metric_stats(tweets),
        "unique_authors": len({t["author"]["username"] for t in tweets}),
        "languages": dict(langs.most_common()),
        "countries": {
            c: {"tweets": n, "authors": len(country_authors[c])} for c, n in countries.most_common()
        },
        "countries_unresolved": unresolved,
        "emojis": dict(emojis.most_common(60)),
    }


# ---------------------------------------------------------------- history

def build_history(days: list[str]) -> dict:
    per_day = []
    seen_authors: set[str] = set()
    heatmap = [[0] * 24 for _ in range(7)]  # [день недели][час]
    hours_total = [0] * 24
    langs_all = Counter()
    countries_all: Counter = Counter()
    country_authors_all: dict[str, set] = defaultdict(set)
    unresolved_all = 0
    author_totals: dict[str, dict] = {}

    for day in days:
        raw = read_jsonl(RAW_DIR / f"{day}.jsonl")
        enriched = {t["id"]: t for t in read_jsonl(ENRICHED_DIR / f"{day}.jsonl")}
        tweets = [enriched.get(t["id"], t) for t in raw]

        weekday = datetime.strptime(day, "%Y-%m-%d").weekday()
        for t in tweets:
            heatmap[weekday][t["hour"]] += 1
            hours_total[t["hour"]] += 1
            langs_all[lang_bucket(t["lang"])] += 1
            c = resolve_country(t["author"]["location"])
            if c:
                countries_all[c] += 1
                country_authors_all[c].add(t["author"]["username"])
            else:
                unresolved_all += 1
            u = t["author"]["username"]
            rec = author_totals.setdefault(
                u, {"username": u, "name": t["author"]["name"], "followers": 0, "tweets": 0, "views": 0}
            )
            rec["tweets"] += 1
            rec["views"] += t["views"]
            rec["followers"] = max(rec["followers"], t["author"]["followers"])

        authors_today = {t["author"]["username"] for t in tweets}
        price = sentiment_counts(tweets, "price_sentiment", "Bullish", "Bearish")
        emo = sentiment_counts(tweets, "emotional_sentiment", "Positive", "Negative")

        row = {
            "date": day,
            **metric_stats(tweets),
            "unique_authors": len(authors_today),
            "new_authors": len(authors_today - seen_authors),
            "price_index": price["index"],
            "price_index_weighted": price["index_weighted"],
            "price_opinion_share": price["opinion_share"] if price["relevant"] else None,
            "emo_index": emo["index"],
            "emo_index_weighted": emo["index_weighted"],
            "labeled": price["labeled"],
        }
        per_day.append(row)
        seen_authors |= authors_today

    months = sorted({month_of(d) for d in days})
    per_month = []
    for m in months:
        rows = [r for r in per_day if r["date"].startswith(m)]
        agg = {"month": m, "tweets": sum(r["tweets"] for r in rows)}
        for metric in METRICS:
            agg["sum_" + metric] = sum(r["sum_" + metric] for r in rows)
            agg["avg_" + metric] = round(agg["sum_" + metric] / agg["tweets"], 1) if agg["tweets"] else 0
        idx = [r["price_index"] for r in rows if r["price_index"] is not None]
        agg["price_index"] = round(sum(idx) / len(idx), 1) if idx else None
        per_month.append(agg)

    prices = {}
    if PRICES_FILE.exists():
        prices = json.loads(PRICES_FILE.read_text(encoding="utf-8"))

    return {
        "per_day": per_day,
        "per_month": per_month,
        "hours_total": hours_total,
        "heatmap": heatmap,
        "languages_all": dict(langs_all.most_common()),
        "countries_all": {
            c: {"tweets": n, "authors": len(country_authors_all[c])}
            for c, n in countries_all.most_common()
        },
        "countries_unresolved_all": unresolved_all,
        "top_authors_all": sorted(author_totals.values(), key=lambda a: a["views"], reverse=True)[:15],
        "brent": prices,
    }


# ---------------------------------------------------------------- main

def main() -> None:
    only_day = sys.argv[1] if len(sys.argv) > 1 else None
    days = sorted(p.stem for p in RAW_DIR.glob("*.jsonl"))
    if not days:
        sys.exit("Нет данных в data/raw/")

    out_day_dir = DASHBOARD_DATA_DIR / "day"
    out_month_dir = DASHBOARD_DATA_DIR / "month"
    out_day_dir.mkdir(parents=True, exist_ok=True)
    out_month_dir.mkdir(parents=True, exist_ok=True)

    # Дни (нужен накопленный набор авторов «до дня» для new_authors)
    seen: set[str] = set()
    for day in days:
        raw_tweets = read_jsonl(RAW_DIR / f"{day}.jsonl")
        if only_day is None or day == only_day:
            data = build_day(day, seen)
            (out_day_dir / f"{day}.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        seen |= {t["author"]["username"] for t in raw_tweets}

    # Месяцы, затронутые пересчётом
    months = sorted({month_of(d) for d in days if only_day is None or month_of(d) == month_of(only_day)})
    for m in months:
        mdays = [d for d in days if d.startswith(m)]
        (out_month_dir / f"{m}.json").write_text(
            json.dumps(build_month(m, mdays), ensure_ascii=False), encoding="utf-8"
        )

    (DASHBOARD_DATA_DIR / "history.json").write_text(
        json.dumps(build_history(days), ensure_ascii=False), encoding="utf-8"
    )
    (DASHBOARD_DATA_DIR / "index.json").write_text(
        json.dumps({
            "days": days,
            "months": sorted({month_of(d) for d in days}),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Готово: {len(days)} дней, {len(months)} месяцев пересчитано -> dashboard/data/")


if __name__ == "__main__":
    main()
