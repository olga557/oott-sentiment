#!/bin/bash
# Ежедневный пайплайн #OOTT + from:JavierBlas: сбор -> батчи -> агрегаты.
# Классификацию и саммари делает агент Cursor (см. README, раздел «Ежедневный запуск»).
#
#   ./run_daily.sh              # вчерашний день UTC
#   ./run_daily.sh 2026-07-12   # конкретный день
set -euo pipefail
cd "$(dirname "$0")"

DAY="${1:-$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d)}"

echo "=== 1/4 Сбор твитов за $DAY"
python3 scripts/fetch_tweets.py "$DAY"

echo "=== 2/4 Обновление цен Brent"
python3 scripts/fetch_prices.py || echo "(не критично: цены обновим в следующий раз)"

echo "=== 3/4 Подготовка батчей для классификации"
python3 scripts/make_batches.py "$DAY"

echo "=== 4/4 Пересчёт агрегатов"
python3 scripts/aggregate.py

echo
echo "Готово. Дальше агент должен:"
echo "  1) классифицировать батчи data/batches/${DAY}_*.json по prompts/classify.md"
echo "  2) слить метки:   python3 scripts/merge_labels.py $DAY <файлы меток>"
echo "  3) саммари дня по prompts/summarize.md -> data/summaries/$DAY.json"
echo "  4) пересчитать:   python3 scripts/aggregate.py $DAY"
