#!/bin/bash
# Локальный просмотр дашборда: http://localhost:8765
cd "$(dirname "$0")"
echo "Дашборд: http://localhost:8765  (Ctrl+C для остановки)"
python3 -m http.server 8765 --directory dashboard
