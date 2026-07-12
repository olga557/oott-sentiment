"""Валидирует и сливает метки классификатора в data/enriched/<день>.jsonl.

    python3 scripts/merge_labels.py 2026-07-11 data/batches/2026-07-11_01.labels.jsonl [...]

Каждая строка входного файла: {"id", "relevant", "price_sentiment",
"emotional_sentiment", "topics"}. Скрипт проверяет схему, что id существуют в
raw-файле дня, и записывает enriched-строки = raw-твит + блок labels.
Повторная заливка того же id перезаписывает старую метку (идемпотентно).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENRICHED_DIR, RAW_DIR, read_jsonl

PRICE_LABELS = {"Bullish", "Bearish", "Neutral"}
EMO_LABELS = {"Positive", "Negative", "Neutral"}


def validate(label: dict) -> str | None:
    if not isinstance(label.get("id"), str) or not label["id"]:
        return "нет id"
    if not isinstance(label.get("relevant"), bool):
        return "relevant не bool"
    if label.get("price_sentiment") not in PRICE_LABELS:
        return f"price_sentiment={label.get('price_sentiment')!r}"
    if label.get("emotional_sentiment") not in EMO_LABELS:
        return f"emotional_sentiment={label.get('emotional_sentiment')!r}"
    topics = label.get("topics")
    if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
        return "topics не список строк"
    return None


def main(day: str, label_files: list[str]) -> None:
    raw = {t["id"]: t for t in read_jsonl(RAW_DIR / f"{day}.jsonl")}
    if not raw:
        sys.exit(f"Нет файла data/raw/{day}.jsonl")

    existing = {r["id"]: r for r in read_jsonl(ENRICHED_DIR / f"{day}.jsonl")}

    added, errors = 0, []
    for lf in label_files:
        for line_no, line in enumerate(Path(lf).read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                label = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{lf}:{line_no}: не JSON ({e})")
                continue
            err = validate(label)
            if err:
                errors.append(f"{lf}:{line_no}: {err}")
                continue
            if label["id"] not in raw:
                errors.append(f"{lf}:{line_no}: id {label['id']} нет в raw за {day}")
                continue
            rec = dict(raw[label["id"]])
            rec["labels"] = {
                "relevant": label["relevant"],
                "price_sentiment": label["price_sentiment"],
                "emotional_sentiment": label["emotional_sentiment"],
                "topics": label["topics"][:3],
            }
            existing[label["id"]] = rec
            added += 1

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    out = ENRICHED_DIR / f"{day}.jsonl"
    ordered = sorted(existing.values(), key=lambda r: r["created_at"])
    with open(out, "w", encoding="utf-8") as f:
        for rec in ordered:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"{day}: слито меток {added}, всего в enriched {len(existing)}/{len(raw)}")
    if errors:
        print(f"ОШИБКИ ({len(errors)}):")
        for e in errors[:20]:
            print(" ", e)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
