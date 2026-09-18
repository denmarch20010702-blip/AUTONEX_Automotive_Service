#!/usr/bin/env bash
# Самостоятельная проверка текущего состояния проекта (шаги A1/A9/A2/A2.1).
# Запускать из корня репозитория: bash scripts/verify.sh [--full]
#
#   без флагов  — быстрые неразрушающие проверки (можно гонять когда угодно)
#   --full      — дополнительно прогоняет полный откат схемы тестовой БД до
#                 пустой и накат обратно. Живая БД `db` не меняется.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1. Контейнеры живы? =="
docker compose ps --format "{{.Name}}: {{.Status}}"

echo
echo "== 2. Backend health-check =="
curl -sf http://localhost:8000/health && echo " — OK" || { echo "FAIL: backend не отвечает"; exit 1; }

echo
echo "== 3. Frontend отвечает =="
code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173)
[ "$code" = "200" ] && echo "200 — OK" || { echo "FAIL: frontend вернул $code"; exit 1; }

echo
echo "== 4. Цепочка миграций без ветвления (одна head, изолированная БД) =="
docker compose --profile test run --rm backend_test alembic heads

echo
echo "== 5. Модели и тестовая БД не разошлись (alembic check) =="
docker compose --profile test run --rm backend_test alembic check

echo
echo "== 6. Тесты backend в db_test =="
docker compose --profile test run --rm backend_test pytest -q

if [ "${1:-}" = "--full" ]; then
  echo
  echo "== 7. [--full] Полный цикл test DB: downgrade base -> upgrade head =="
  docker compose --profile test run --rm backend_test alembic downgrade base
  docker compose --profile test run --rm backend_test alembic upgrade head
  echo "Цикл прошёл без ошибок — миграции реверсивны и изолированы от живых данных."
fi

echo
echo "Все проверки пройдены."
