"""Дневные цены закрытия Brent для графика истории сентимента.

Основной источник — ICE (Brent Crude Futures, product 219), тот же график,
что на https://www.ice.com/products/219/Brent-Crude-Futures/data
(вкладка 3 Months). Контракт — фронтальный фьючерс: в июле 2026 это Sep26
(marketId 6018448). Скрипт сам определяет текущий front-month через список
контрактов ICE; если не вышло — берёт DEFAULT_MARKET_ID.

Запасной источник — Yahoo Finance (BZ=F): это тот же ICE Brent front-month,
используется только если ICE недоступен (Cloudflare и т.п.), чтобы ежедневный
пайплайн не падал.

    python3 scripts/fetch_prices.py            # ICE, автоопределение контракта
    python3 scripts/fetch_prices.py 6018448    # ICE, явный marketId

Пишет data/prices.json: {"2026-07-01": 71.57, ...} (только торговые дни).
Существующие даты обновляются, история не теряется.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROJECT_ROOT

OUT = PROJECT_ROOT / "data" / "prices.json"

ICE_BASE = "https://www.ice.com/marketdata/DelayedMarkets.shtml"
ICE_PRODUCT_ID = 219   # Brent Crude Futures
ICE_HUB_ID = 403       # ICE Futures Europe
DEFAULT_MARKET_ID = 6018448  # Sep26 — front month в июле 2026

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.ice.com/products/219/Brent-Crude-Futures/data",
}

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F"


def resolve_front_market_id(session: requests.Session) -> int:
    """Front-month контракт Brent (первый в списке контрактов ICE)."""
    resp = session.get(
        ICE_BASE,
        params={"getContractsAsJson": "", "productId": ICE_PRODUCT_ID, "hubId": ICE_HUB_ID},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    contracts = resp.json()
    first = contracts[0]
    mid = int(first["marketId"])
    print(f"ICE front-month: {first.get('marketStrip', '?')} (marketId {mid})")
    return mid


def fetch_ice(market_id: int | None) -> dict[str, float]:
    session = requests.Session()
    if market_id is None:
        try:
            market_id = resolve_front_market_id(session)
        except Exception as e:
            print(f"  не удалось определить front-month ({type(e).__name__}), беру marketId {DEFAULT_MARKET_ID}")
            market_id = DEFAULT_MARKET_ID

    # historicalSpan=3 соответствует вкладке «3 Months» на странице данных ICE
    resp = session.get(
        ICE_BASE,
        params={"getHistoricalChartDataAsJson": "", "marketId": market_id, "historicalSpan": 3},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    bars = resp.json().get("bars", [])

    prices: dict[str, float] = {}
    for bar in bars:
        # bar = ["Thu Jul 10 2026 ...", 76.01]
        raw_date, close = bar[0], bar[1]
        if close is None:
            continue
        day = datetime.strptime(" ".join(str(raw_date).split()[:4]), "%a %b %d %Y").strftime("%Y-%m-%d")
        prices[day] = round(float(close), 2)  # последний бар дня побеждает
    if not prices:
        raise RuntimeError("ICE вернул пустой график")
    return prices


def fetch_yahoo() -> dict[str, float]:
    resp = requests.get(
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
        print(f"ICE недоступен ({type(e).__name__}: {e}), fallback -> Yahoo (BZ=F, тот же ICE front-month)")
        fresh = fetch_yahoo()
        source = "Yahoo (fallback)"

    prices = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    prices.update(fresh)
    OUT.write_text(json.dumps(dict(sorted(prices.items())), indent=1), encoding="utf-8")
    print(f"Brent [{source}]: обновлено {len(fresh)} точек, всего {len(prices)} -> data/prices.json")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
