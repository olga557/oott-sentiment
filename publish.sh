#!/bin/bash
# Публикация свежих данных на сайт: коммит + пуш в GitHub.
# GitHub Actions после пуша сам обновит https://olga557.github.io/oott-sentiment/
# Запускать в конце ежедневного пайплайна (после классификации и саммари).
set -euo pipefail
cd "$(dirname "$0")"

if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
  echo "Нет изменений — публиковать нечего."
  exit 0
fi

DAY="${1:-$(date -u +%Y-%m-%d)}"
git add -A
git commit -m "Data update: $DAY"
git push
echo "Опубликовано. Сайт обновится через 1-2 минуты."
