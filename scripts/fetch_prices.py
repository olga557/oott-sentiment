"""Дневные цены закрытия Brent для графика истории сентимента.

Источник — ICE Brent Crude Futures (product 219), тот же график, что на
https://www.ice.com/products/219/Brent-Crude-Futures/data (вкладка «3 Months»,
span=1 → historicalSpan=1 в API).

Контракт каждый раз выбирается автоматически: первый (front-month) из списка
контрактов ICE. В июле это Sep, в августе станет Oct — руками marketId менять
не нужно. Явный marketId в аргументе — только для отладки.

Если ICE недоступен — fallback:
https://www.investing.com/commodities/brent-oil-historical-data
(столбец Price, только будние дни Mon–Fri; сегодняшний незакрытый день не пишем).

Yahoo BZ=F — крайний fallback после Investing.

    python3 scripts/fetch_prices.py           # ICE, авто front-month
    python3 scripts/fetch_prices.py <marketId>  # редко: зафиксировать контракт

Пишет data/prices.json: {"2026-07-01": 71.57, ...} (торговые дни).
Существующие даты обновляются, история не затирается.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROJECT_ROOT

OUT = PROJECT_ROOT / "data" / "prices.json"

ICE_BASE = "https://www.ice.com/marketdata/DelayedMarkets.shtml"
ICE_PRODUCT_ID = 219  # Brent Crude Futures
ICE_HUB_ID = 403  # ICE Futures Europe
# span=1 на странице = вкладка «3 Months»
ICE_HISTORICAL_SPANS = (1, 3)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ice.com/products/219/Brent-Crude-Futures/data",
    "Origin": "https://www.ice.com",
}

# Investing.com Brent Oil Futures (historical Price column)
INVESTING_HIST_URL = "https://www.investing.com/commodities/brent-oil-historical-data"
INVESTING_AJAX_URL = "https://www.investing.com/instruments/HistoricalDataAjax"
INVESTING_CURR_ID = "8833"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F"

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    return s


def _is_weekday(day: str) -> bool:
    return datetime.strptime(day, "%Y-%m-%d").weekday() < 5  # Mon–Fri


def _drop_incomplete_today(prices: dict[str, float]) -> dict[str, float]:
    """Не сохраняем сегодняшний бар — сессия может быть ещё не закрыта."""
    today = datetime.now(timezone.utc).date().isoformat()
    return {d: v for d, v in prices.items() if d != today}


def _weekdays_only(prices: dict[str, float]) -> dict[str, float]:
    return {d: v for d, v in prices.items() if _is_weekday(d)}


def resolve_front_market_id(session: requests.Session) -> int:
    """Текущий front-month Brent — первый контракт в списке ICE."""
    resp = session.get(
        ICE_BASE,
        params={"getContractsAsJson": "", "productId": ICE_PRODUCT_ID, "hubId": ICE_HUB_ID},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    contracts = resp.json()
    if not contracts:
        raise RuntimeError("ICE вернул пустой список контрактов")
    first = contracts[0]
    mid = int(first["marketId"])
    print(f"ICE front-month: {first.get('marketStrip', '?')} (marketId {mid})")
    return mid


def _parse_ice_bars(bars: list) -> dict[str, float]:
    prices: dict[str, float] = {}
    for bar in bars:
        raw_date, close = bar[0], bar[1]
        if close is None:
            continue
        day = datetime.strptime(" ".join(str(raw_date).split()[:4]), "%a %b %d %Y").strftime("%Y-%m-%d")
        prices[day] = round(float(close), 2)
    return prices


def fetch_ice(market_id: int | None) -> dict[str, float]:
    session = _session()
    if market_id is None:
        market_id = resolve_front_market_id(session)

    last_err: Exception | None = None
    for span in ICE_HISTORICAL_SPANS:
        try:
            resp = session.get(
                ICE_BASE,
                params={
                    "getHistoricalChartDataAsJson": "",
                    "marketId": market_id,
                    "historicalSpan": span,
                },
                headers=HEADERS,
                timeout=45,
            )
            resp.raise_for_status()
            bars = resp.json().get("bars", [])
            prices = _parse_ice_bars(bars)
            if not prices:
                raise RuntimeError(f"ICE historicalSpan={span}: пустой график")
            print(f"  ICE OK (marketId={market_id}, historicalSpan={span}, точек={len(prices)})")
            return prices
        except Exception as e:
            last_err = e
            print(f"  ICE historicalSpan={span} не вышло: {type(e).__name__}: {e}")
    raise RuntimeError(f"ICE недоступен: {last_err}")


def _parse_investing_date(raw: str) -> str | None:
    """'Jul 13, 2026' / '07/13/2026' -> YYYY-MM-DD."""
    raw = unescape(raw).strip()
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", raw)
    if m:
        mon = MONTHS.get(m.group(1)[:3].title())
        if mon:
            return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _parse_investing_html(html: str) -> dict[str, float]:
    """Достаёт Date + Price из таблицы historical data (Ajax или страница)."""
    prices: dict[str, float] = {}
    # Строки вида: Jul 13, 2026 ... 83.30  или  в <td>
    row_re = re.compile(
        r"(?:data-real-value=\"(\d+)\"[^>]*>)?\s*"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s*\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{4})"
        r".{0,200}?"
        r"(?:class=\"[^\"]*?(?:pid-\d+-last|Price)[^\"]*\"[^>]*>|)"
        r"\s*([0-9]+(?:\.[0-9]+)?)",
        re.I | re.S,
    )
    for m in row_re.finditer(html):
        day = _parse_investing_date(m.group(2))
        if not day:
            continue
        prices[day] = round(float(m.group(3)), 2)

    # Markdown/plain fallback: |Jul 13, 2026|83.30|
    plain = re.compile(
        r"\|?\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s*\d{4})"
        r"\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|",
        re.I,
    )
    for m in plain.finditer(html):
        day = _parse_investing_date(m.group(1))
        if day:
            prices[day] = round(float(m.group(2)), 2)
    return prices


def fetch_investing() -> dict[str, float]:
    """Закрытия Brent со столбца Price на Investing.com — только будни."""
    session = _session()
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": INVESTING_HIST_URL,
        "X-Requested-With": "XMLHttpRequest",
    }
    end = date.today()
    start = end - timedelta(days=100)
    last_err: Exception | None = None

    try:
        resp = session.post(
            INVESTING_AJAX_URL,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "curr_id": INVESTING_CURR_ID,
                "smlID": "300028",
                "header": "Brent Oil Futures Historical Data",
                "st_date": start.strftime("%m/%d/%Y"),
                "end_date": end.strftime("%m/%d/%Y"),
                "interval_sec": "Daily",
                "sort_col": "date",
                "sort_ord": "DESC",
                "action": "historical_data",
            },
            timeout=45,
        )
        resp.raise_for_status()
        prices = _parse_investing_html(resp.text)
        if prices:
            prices = _drop_incomplete_today(_weekdays_only(prices))
            print(f"  Investing Ajax OK (точек={len(prices)}, только будни)")
            return prices
        raise RuntimeError("Investing Ajax: не разобрали таблицу")
    except Exception as e:
        last_err = e
        print(f"  Investing Ajax не вышло: {type(e).__name__}: {e}")

    try:
        resp = session.get(INVESTING_HIST_URL, headers=headers, timeout=45)
        resp.raise_for_status()
        prices = _parse_investing_html(resp.text)
        if not prices:
            raise RuntimeError("Investing page: пустая таблица")
        prices = _drop_incomplete_today(_weekdays_only(prices))
        print(f"  Investing page OK (точек={len(prices)}, только будни)")
        return prices
    except Exception as e:
        last_err = e
        print(f"  Investing page не вышло: {type(e).__name__}: {e}")

    raise RuntimeError(f"Investing недоступен: {last_err}")


def fetch_yahoo() -> dict[str, float]:
    """BZ=F ≈ ICE front-month, но пропускает дни, когда US закрыт, а ICE торгует."""
    resp = _session().get(
        YAHOO_URL,
        params={"range": "3mo", "interval": "1d"},
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    prices = {}
    for ts, close in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        prices[day] = round(float(close), 2)
    return _drop_incomplete_today(_weekdays_only(prices))


def main(market_id: int | None) -> None:
    try:
        fresh = fetch_ice(market_id)
        source = "ICE"
    except Exception as e:
        print(
            f"ICE недоступен ({type(e).__name__}: {e}), "
            "fallback -> Investing.com historical Price (будни).\n"
            f"  {INVESTING_HIST_URL}"
        )
        try:
            fresh = fetch_investing()
            source = "Investing (fallback)"
        except Exception as e2:
            print(
                f"Investing тоже недоступен ({type(e2).__name__}: {e2}), "
                "крайний fallback -> Yahoo BZ=F."
            )
            fresh = fetch_yahoo()
            source = "Yahoo (fallback)"

    prices = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    # Fallback не затирает уже известные дни (могли быть с ICE)
    if source.startswith(("Investing", "Yahoo")):
        for day, val in fresh.items():
            if day not in prices:
                prices[day] = val
    else:
        prices.update(fresh)

    # Страховка: выходные из любого источника не храним
    prices = _weekdays_only(prices)

    OUT.write_text(json.dumps(dict(sorted(prices.items())), indent=1) + "\n", encoding="utf-8")
    jul = {k: v for k, v in prices.items() if k >= "2026-07-01"}
    print(f"Brent [{source}]: обновлено {len(fresh)} точек, всего {len(prices)} -> data/prices.json")
    if jul:
        print("с 2026-07-01:", " ".join(f"{d}={jul[d]}" for d in sorted(jul)))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
