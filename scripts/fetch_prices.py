"""Дневные цены закрытия Brent для графика истории сентимента.

Источник — тот же график ICE, что на странице:
  https://www.ice.com/products/219/Brent-Crude-Futures/data?marketId=6018448&span=1
вкладка «3 Months» (параметр span=1 → historicalSpan=1 в API),
контракт — фронтальный фьючерс (в июле 2026 это Sep26, marketId 6018448).

Важно: Yahoo BZ=F — НЕ полный заменитель ICE. На US-праздниках (напр. 3 июля
2026, когда 4 июля выпало на субботу) BZ=F может не иметь бара, а ICE Europe
торгуется. Поэтому Yahoo — только аварийный fallback.

    python3 scripts/fetch_prices.py            # ICE, авто front-month
    python3 scripts/fetch_prices.py 6018448    # явный marketId

Пишет data/prices.json: {"2026-07-01": 71.57, ...} (торговые дни).
Существующие даты обновляются, история не затирается.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROJECT_ROOT

OUT = PROJECT_ROOT / "data" / "prices.json"

ICE_BASE = "https://www.ice.com/marketdata/DelayedMarkets.shtml"
ICE_PRODUCT_ID = 219  # Brent Crude Futures
ICE_HUB_ID = 403  # ICE Futures Europe
DEFAULT_MARKET_ID = 6018448  # Sep26 — front month в июле 2026
# span=1 на странице data?marketId=…&span=1 = вкладка «3 Months»
ICE_HISTORICAL_SPANS = (1, 3)  # 1 — как в URL; 3 — запасной вариант API

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ice.com/products/219/Brent-Crude-Futures/data?marketId=6018448&span=1",
    "Origin": "https://www.ice.com",
}

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F"


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False  # не ходить через proxy песочницы Cursor
    return s


def resolve_front_market_id(session: requests.Session) -> int:
    """Front-month контракт Brent (первый в списке контрактов ICE)."""
    resp = session.get(
        ICE_BASE,
        params={"getContractsAsJson": "", "productId": ICE_PRODUCT_ID, "hubId": ICE_HUB_ID},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    contracts = resp.json()
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
        try:
            market_id = resolve_front_market_id(session)
        except Exception as e:
            print(f"  не удалось определить front-month ({type(e).__name__}), беру marketId {DEFAULT_MARKET_ID}")
            market_id = DEFAULT_MARKET_ID

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
    return prices


def main(market_id: int | None) -> None:
    try:
        fresh = fetch_ice(market_id)
        source = "ICE"
    except Exception as e:
        print(
            f"ICE недоступен ({type(e).__name__}: {e}), fallback -> Yahoo BZ=F.\n"
            "  Внимание: Yahoo может пропускать дни ICE-сессии в US-праздники "
            "(как 2026-07-03). Запустите скрипт локально, когда ICE доступен."
        )
        fresh = fetch_yahoo()
        source = "Yahoo (fallback)"

    prices = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    # не затираем уже известные ICE-дни более дырявым fallback'ом
    if source.startswith("Yahoo"):
        for day, val in fresh.items():
            prices[day] = val
    else:
        prices.update(fresh)

    OUT.write_text(json.dumps(dict(sorted(prices.items())), indent=1), encoding="utf-8")
    jul = {k: v for k, v in prices.items() if k >= "2026-07-01"}
    print(f"Brent [{source}]: обновлено {len(fresh)} точек, всего {len(prices)} -> data/prices.json")
    print("с 2026-07-01:", " ".join(f"{d}={jul[d]}" for d in sorted(jul)))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
