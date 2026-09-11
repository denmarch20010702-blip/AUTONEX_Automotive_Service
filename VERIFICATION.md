# Как самостоятельно проверить, что сделано на шагах A1/A9/A2/A2.1

Это доказательство того, что текущий скелет проекта (docker-compose, схема БД: `Client`, `Car`, `Service`, `Post`, `Booking`, `TireSet`, `AdditionalWork`) — рабочий и внутренне непротиворечивый: миграции не расходятся с моделями, обратимы, приложение отвечает, тесты зелёные.

## Быстрый способ — один скрипт

```bash
docker compose up -d        # если ещё не запущено
bash scripts/verify.sh
```

Работает из Git Bash, WSL или обычного терминала на Windows/macOS/Linux — внутри только `docker compose exec`/`curl`, ничего платформозависимого.

Скрипт проверяет по порядку:

1. **Все три контейнера живы** (`db`/`backend`/`frontend`) — `docker compose ps`.
2. **Backend отвечает** — `GET /health` → `{"status":"ok"}`.
3. **Frontend отвечает** — `GET /` → `200`.
4. **Миграции не ветвятся** — `alembic heads` должен показать ровно одну "head"-ревизию. Если их больше одной — значит кто-то создал две параллельные миграции от одного родителя, и это конфликт, который нужно решать `alembic merge`.
5. **Код и реальная БД не разошлись** — `alembic check` сравнивает ORM-модели с фактической структурой БД и говорит `No new upgrade operations detected`, если они совпадают. Если бы кто-то поправил модель и забыл сделать миграцию — эта команда покажет расхождение.
6. **Тесты backend** — `pytest` внутри контейнера (та же среда, что видит and CI/проверяющий).

Флаг `--full` (`bash scripts/verify.sh --full`) добавляет седьмую, разрушающую проверку — полный откат схемы БД до пустой и накат обратно (`alembic downgrade base` → `alembic upgrade head`). Это самое сильное доказательство того, что миграции консистентны: если бы `upgrade` и `downgrade` не были зеркальны друг другу (как оказалось при первой проверке — см. ниже), команда бы упала. **Стирает все данные в БД** — сейчас безопасно (реальных данных ещё нет), но как только в проекте появятся настоящие данные — этот флаг только на копии БД, не на боевой.

## Что именно нашлось и было исправлено

При первом прогоне `--full` вскрылся реальный баг: автогенерация Alembic создаёт Postgres `ENUM`-тип при `CREATE TABLE`, но не удаляет его при `DROP TABLE` в `downgrade()` — это её собственное известное ограничение (отмечено в самих файлах миграций комментарием "please adjust!", который до этой проверки никто вручную не проверил). Из-за этого повторный `upgrade` после `downgrade` падал: `type "booking_status" already exists`.

Исправлено — в `downgrade()` обеих миграций (`backend/alembic/versions/909e4725fc6d_*.py` и `c1528f5a8b01_*.py`) добавлено явное удаление ENUM-типов. После фикса цикл `upgrade → downgrade → upgrade` проходит многократно без ошибок (проверено).

## Проверить руками (без скрипта), если хочется своими глазами

```bash
# Список таблиц и типов прямо в Postgres
docker compose exec db psql -U station -d station -c "\dt" -c "\dT"

# Структура конкретной таблицы
docker compose exec db psql -U station -d station -c "\d bookings"

# История миграций
docker compose exec backend alembic history --verbose
```

## Ручная проверка API (шаг A3: Клиент/Автомобиль/Каталог услуг)

### Вариант 1 — Swagger UI в браузере (самый простой)

Открой **`http://localhost:8000/docs`**. Там интерактивная документация по всем эндпоинтам (`/clients`, `/cars`, `/catalog`) — можно раскрыть любой, нажать "Try it out", ввести данные (включая кириллицу — в браузере проблем с кодировкой нет) и выполнить запрос прямо там же, увидеть код ответа и тело. Это самый надёжный способ, рекомендую начать с него.

Альтернатива с тем же API, но в виде читаемой документации — `http://localhost:8000/redoc`.

### Вариант 2 — PowerShell

```powershell
# Создать клиента
$json = @{ email = "test@example.com"; name = "Test Client" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/clients" -Method Post -Body $json -ContentType "application/json"

# Список клиентов
Invoke-RestMethod -Uri "http://localhost:8000/clients"

# Получить/обновить/удалить конкретного (подставь id из ответа выше)
Invoke-RestMethod -Uri "http://localhost:8000/clients/1"
Invoke-RestMethod -Uri "http://localhost:8000/clients/1" -Method Patch -Body '{"name":"New Name"}' -ContentType "application/json"
Invoke-RestMethod -Uri "http://localhost:8000/clients/1" -Method Delete
```

**Важный нюанс, если будешь вводить кириллицу прямо в PowerShell-консоли:** сама консоль Windows PowerShell 5.1 может **отображать** кириллический ответ как нечитаемую кашу (`Ð Ñ...`) — это проверено и это проблема отображения в консоли, а не данных. Реальные данные при этом долетают до БД и хранятся в корректном UTF-8 (я это отдельно проверил через `psql`, сравнив побайтово). Если видишь такую кашу в ответе — не паникуй, проверь то же самое через Swagger UI или напрямую в БД (ниже) прежде чем считать это багом.

## Ручная проверка БД

```bash
# Список таблиц
docker compose exec db psql -U station -d station -c "\dt"

# Содержимое конкретной таблицы
docker compose exec db psql -U station -d station -c "SELECT * FROM clients;"

# Произвольный запрос
docker compose exec db psql -U station -d station -c "SELECT c.name, a.make, a.model FROM cars a JOIN clients c ON c.id = a.client_id;"
```

Учётные данные (те же, что в `docker-compose.yml`): пользователь `station`, пароль `station`, база `station`, хост `localhost`, порт `5432` — этого достаточно, чтобы подключиться и любым GUI-клиентом (DBeaver, TablePlus, pgAdmin), если он уже стоит у тебя.

## Что это доказывает, а что — нет

**Доказывает:** инфраструктура (A1/A9) и схема БД (A2/A2.1) рабочие, согласованные между собой и с моделями в коде, миграции обратимы.

**Не доказывает** (потому что этого ещё нет в проекте): бизнес-логику — свободные слоты, статусную машину заявки, конкурентное бронирование, поток согласования доп. работ. Эти проверки появятся вместе с соответствующими шагами (A4, A5, A10, B1, B2) — см. `logs/EXECUTION_PLAN.md`.
