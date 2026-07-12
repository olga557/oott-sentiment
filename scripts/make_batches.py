"""Готовит батчи твитов дня для LLM-классификации.

    python3 scripts/make_batches.py 2026-07-11 [размер_батча]

Создаёт data/batches/2026-07-11_NN.json — компактные файлы (id, text, quoted),
которые классификатор (агент или внешний API) читает вместе с prompts/classify.md.
Уже классифицированные твиты (есть в data/enriched/<день>.jsonl) пропускаются.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BATCHES_DIR, ENRICHED_DIR, RAW_DIR, read_jsonl


def main(day: str, batch_size: int = 40) -> None:
    raw = read_jsonl(RAW_DIR / f"{day}.jsonl")
    if not raw:
        sys.exit(f"Нет файла data/raw/{day}.jsonl")

    done_ids = {r["id"] for r in read_jsonl(ENRICHED_DIR / f"{day}.jsonl")}
    todo = [t for t in raw if t["id"] not in done_ids]
    if not todo:
        print(f"{day}: все {len(raw)} твитов уже классифицированы")
        return

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    for old in BATCHES_DIR.glob(f"{day}_*.json"):
        old.unlink()

    n_batches = 0
    for i in range(0, len(todo), batch_size):
        chunk = todo[i : i + batch_size]
        items = []
        for t in chunk:
            item = {"id": t["id"], "text": t["text"]}
            if t.get("quoted"):
                item["quoted_text"] = t["quoted"]["text"][:500]
            items.append(item)
        n_batches += 1
        path = BATCHES_DIR / f"{day}_{n_batches:02d}.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{day}: {len(todo)} твитов -> {n_batches} батчей в data/batches/")


if __name__ == "__main__":
    day = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    main(day, size)
