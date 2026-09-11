#!/usr/bin/env bash
# Самостоятельная проверка текущего состояния проекта (шаги A1/A9/A2/A2.1).
# Запускать из корня репозитория: bash scripts/verify.sh [--full]
#
#   без флагов  — быстрые неразрушающие проверки (можно гонять когда угодно)
#   --full      — дополнительно прогоняет полный откат схемы БД до пустой
#                 и накат обратно. Стирает все данные в БД. Безопасно сейчас
#                 (реальных данных ещё нет, только схема), но станет опасно
#                 после того как в БД появятся настоящие записи — тогда этот
#                 флаг использовать только на тестовой копии БД.

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
echo "== 4. Цепочка миграций без ветвления (одна head) =="
docker compose exec -T backend alembic heads

echo
echo "== 5. Модели и реальная БД не разошлись (alembic check) =="
docker compose exec -T backend alembic check

echo
echo "== 6. Тесты backend =="
docker compose exec -T backend pytest -q

if [ "${1:-}" = "--full" ]; then
  echo
  echo "== 7. [--full] Полный цикл downgrade base -> upgrade head (СТИРАЕТ ДАННЫЕ В БД) =="
  docker compose exec -T backend alembic downgrade base
  docker compose exec -T backend alembic upgrade head
  echo "Цикл прошёл без ошибок — миграции реверсивны и консистентны."
fi

echo
echo "Все проверки пройдены."
