"""Одноразовый бэкфилл: конвертация экселя с твитами в data/raw/*.jsonl.

Запуск: python3 scripts/ingest_excel.py data/tweet_oil_june_july.xlsx
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, normalize_excel_row, write_daily_jsonl


def main(xlsx_path: str) -> None:
    df = pd.read_excel(xlsx_path)
    records, skipped = [], 0
    seen = set()
    for row in df.to_dict(orient="records"):
        rec = normalize_excel_row(row)
        if rec is None:
            skipped += 1
            continue
        if rec["id"] in seen:
            continue
        seen.add(rec["id"])
        records.append(rec)

    counts = write_daily_jsonl(records, RAW_DIR)
    total = sum(counts.values())
    print(f"Записано {total} твитов в {len(counts)} дневных файлов ({min(counts)} .. {max(counts)})")
    if skipped:
        print(f"Пропущено строк без id/даты: {skipped}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/tweet_oil_june_july.xlsx")
