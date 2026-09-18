# AUTONEX — инструкция для агента и ревьюера

## Контекст

Это тестовый проект станции техобслуживания: FastAPI/SQLAlchemy/Alembic/PostgreSQL в `backend/` и React/TypeScript/Vite в `frontend/`. Бизнес-требования находятся в `buisness/`, а актуальный план и решения — в `logs/`.

Перед изменением бизнес-логики прочитайте `buisness/buisness.md`, `buisness/ARCHITECTURE.md`, `logs/EXECUTION_PLAN.md`, последние записи `logs/DECISIONS_LOG.md` и подходящий раздел `VERIFICATION.md`.

## Безопасный запуск и проверки

```bash
docker compose up --build
docker compose --profile test run --rm backend_test pytest -q
bash scripts/verify.sh
```

`backend/scripts/entrypoint.sh` применяет `alembic upgrade head` перед запуском backend и перед командой в `backend_test`. Не запускайте `pytest` через `docker compose exec backend`: это рабочая БД `db`. Любые миграции с откатом и эксперименты выполняйте только через профиль `test` и `db_test`.

Нельзя удалять Docker volume `db_data`, менять реальные записи SQL-скриптами или выполнять `scripts/verify.sh --full` против живой базы. `--full` в актуальной версии работает только с `db_test`.

## Правила изменений

- Для каждого изменения ORM-модели добавляйте отдельную Alembic-миграцию и проверяйте `alembic check`.
- Выручка отображается из `BookingArchive` со статусом `issued`; `StationStats.total_revenue` — legacy-кэш, не источник истины.
- Сумма архива должна быть разложена на `service_price` и `parking_surcharge`; исторические суммы не пересчитываются по текущему тарифу.
- Не обходите статусную машину заявки и не начисляйте деньги до `issued`.
- Не расширяйте права открытого demo API незаметно. Полная авторизация клиента/станции — отдельное решение и должна быть согласована до реализации.
- Не перезаписывайте чужие незакоммиченные изменения. Перед началом и перед передачей проверяйте `git status` и `git diff --check`.

## Документация и журналирование

После существенной правки обновите: `logs/EXECUTION_PLAN.md` (статус/реестр багов), `logs/DECISIONS_LOG.md` (хронологическая запись с атрибуцией), `logs/SESSION_LOG.md` и соответствующий раздел `VERIFICATION.md`. В записи указывайте, что действительно проверено, а что ожидает запуска; не заявляйте зелёные тесты без фактического прогона.
