# MadDevs — тестовое задание: Станция техобслуживания / MadDevs test task: Service Station

Репозиторий тестового задания для отбора на позицию Agentic Developer в MadDevs. Выбранный кейс — **Задание 12: Станция техобслуживания**, с кастомной фичей: роботизация станции + ИИ-модуль диагностики дополнительных работ.

*Repository of the MadDevs test task for the Agentic Developer position. The chosen case is **Task 12: Service Station**, with a custom feature: station robotization + an AI module for diagnosing additional work.*

## Структура репозитория / Repository structure

- `AGENTS.md` — точка входа для агента/ревьюера: безопасные команды запуска/проверки, правила изменений (миграции, где живёт источник истины для выручки, чего не делать).
  *Entry point for the agent/reviewer: safe run/check commands, change rules (migrations, where the source of truth for revenue lives, what not to do).*
- `.github/workflows/ci.yml` — GitHub Actions: миграции + тесты backend, `tsc` фронтенда на каждый push/PR.
  *GitHub Actions: migrations + backend tests, frontend `tsc` on every push/PR.*
- `buisness/` — бизнес-требования и архитектура:
  *business requirements and architecture:*
  - `buisness.md` — концепция AUTONEX (доп. фичи поверх Задания 12), автор — пользователь.
    *The AUTONEX concept (extra features on top of Task 12), authored by the user.*
  - `ARCHITECTURE.md` — стек, обоснование выбора, структура репозитория, модель данных, ключевые сценарии, бизнес-правила, принятые по ходу разработки.
    *Stack, rationale for the choices, repository structure, data model, key scenarios, business rules adopted during development.*
  - `BUSINESS_FEATURES_REVIEW.md` — разбор фич из `buisness.md`: конфликты, полезность, реализуемость, время.
    *Review of the features from `buisness.md`: conflicts, usefulness, feasibility, time.*
  - `UI_description.md` — живой список находок пользователя из ручного тестирования интерфейса (нумерованные пункты, дополняется по ходу работы).
    *A living list of the user's findings from manual UI testing (numbered items, extended as work progresses).*
- `logs/` — план и журналы работы:
  *work plan and logs:*
  - `EXECUTION_PLAN.md` — живой план работ с приоритетами (A/B/C/D), прогрессом по шагам и реестром найденных багов.
    *A living work plan with priorities (A/B/C/D), per-step progress and a registry of found bugs.*
  - `SESSION_LOG.md` — промпты и ответы ИИ-агента по ходу всей работы.
    *Prompts and AI-agent responses throughout the whole work.*
  - `DECISIONS_LOG.md` — ключевые решения, находки и действия с атрибуцией (кто сделал — пользователь или агент) и таймкодами.
    *Key decisions, findings and actions with attribution (who did it — the user or the agent) and timestamps.*
- `VERIFICATION.md` — как самостоятельно проверить текущее состояние проекта.
  *How to verify the current state of the project on your own.*
- `backend/` — FastAPI-приложение (`scripts/verify.sh`, `scripts/prove_concurrency.py` — конкурентность A10, `scripts/prove_full_cycle.py` — полный цикл C6, `scripts/cleanup_test_data.py`, `scripts/entrypoint.sh` — автоприменение миграций при старте контейнера).
  *FastAPI application (`scripts/verify.sh`, `scripts/prove_concurrency.py` — A10 concurrency proof, `scripts/prove_full_cycle.py` — C6 full-cycle proof, `scripts/cleanup_test_data.py`, `scripts/entrypoint.sh` — automatic migrations on container start).*
- `frontend/` — React/TypeScript-приложение (Vite).
  *React/TypeScript application (Vite).*
- `docker-compose.yml` — оркестрация `db` (PostgreSQL) + `backend` + `frontend`, плюс изолированные `db_test`/`backend_test` (профиль `test`, см. "Тесты" ниже).
  *Orchestration of `db` (PostgreSQL) + `backend` + `frontend`, plus isolated `db_test`/`backend_test` (the `test` profile, see "Tests" below).*

Входные материалы задания (письмо от MadDevs, PDF со всеми 14 кейсами, анализ выбора) не публикуются в этом репозитории — они содержат оригинальные материалы тестового задания MadDevs.

*The task's input materials (the letter from MadDevs, the PDF with all 14 cases, the selection analysis) are not published in this repository — they contain the original MadDevs test-task materials.*

## Как развернуть локально / Running locally

Предварительные требования: **Docker Desktop** (с WSL2-бэкендом на Windows) — больше ничего ставить не нужно, версии Python/Node зашиты в образы.

*Prerequisites: **Docker Desktop** (with the WSL2 backend on Windows) — nothing else to install, the Python/Node versions are baked into the images.*

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

После старта / After startup:
- backend: http://localhost:8000/health → `{"status":"ok"}`
- frontend: http://localhost:5173
- PostgreSQL: `localhost:5432` (пользователь/пароль/база — `station`/`station`/`station`, см. `docker-compose.yml`)
  *(user/password/database — `station`/`station`/`station`, see `docker-compose.yml`)*

Миграции применяются автоматически при старте контейнера (`backend/scripts/entrypoint.sh` → `alembic upgrade head` перед запуском `uvicorn`) — отдельно накатывать их не нужно.

*Migrations are applied automatically on container start (`backend/scripts/entrypoint.sh` → `alembic upgrade head` before launching `uvicorn`) — there is no need to run them separately.*

Проверено (2026-09-19): все три контейнера (`db`, `backend`, `frontend`) собираются и стартуют, `db` проходит healthcheck, `backend` отвечает на `/health`, `frontend` отдаёт страницу и достучивается до backend через CORS.

*Verified (2026-09-19): all three containers (`db`, `backend`, `frontend`) build and start, `db` passes its healthcheck, `backend` answers on `/health`, `frontend` serves the page and reaches the backend via CORS.*

### Демо-данные / Demo data

При запуске проекта база уже содержит демо-данные: каталог из 5 услуг и клиента Demo Client (`demo@email.com`) с автомобилем Hyundai Creta — подробности в абзаце ниже. Основной пользовательский сценарий можно проверить сразу: войдите под `demo@email.com`, выберите услугу из каталога и создайте запись на доступное время. При желании клиентов, автомобили и услуги можно создавать и вручную через интерфейс приложения.

*On startup the database already contains demo data: a catalog of 5 services and the client Demo Client (`demo@email.com`) with a Hyundai Creta — details in the paragraph below. The main user scenario can be checked right away: sign in as `demo@email.com`, pick a service from the catalog and create a booking for an available time. If you wish, clients, cars and services can also be created manually through the application interface.*

**С чем стартует свежая БД:** заявок нет — это реальные пользовательские данные, они закономерно не идут вместе с кодом. Но станция не буквально пустая: миграции сеют фиксированную физическую конфигурацию (3 поста, 6 парковочных мест, тариф по умолчанию), каталог из 5 демонстрационных услуг («Плановое ТО», «Замена масла», «Замена шин», «Замена тормозных колодок», «Диагностика подвески» — прямые примеры из условия задания), 2 защищённые услуги-проводника к хранению шин и демо-клиента **Demo Client** (`demo@email.com`, поиск по email нечувствителен к регистру, так что `Demo@email.com` тоже находится) с автомобилем Hyundai Creta (пробег 80 000 км, последнее ТО — 01.03.2026), чтобы проверяющему не приходилось создавать профиль с нуля. Для сквозной демонстрации без единого клика вручную — см. `backend/scripts/prove_concurrency.py`/`prove_full_cycle.py` в разделе "Тесты" ниже.

***What a fresh database starts with:** there are no bookings — that is real user data and naturally does not ship with the code. But the station is not literally empty: the migrations seed the fixed physical configuration (3 posts, 6 parking spots, the default tariff), a catalog of 5 demo services ("Плановое ТО", "Замена масла", "Замена шин", "Замена тормозных колодок", "Диагностика подвески" — direct examples from the task statement), 2 protected services that act as gateways to tire storage, and a demo client **Demo Client** (`demo@email.com`; the email lookup is case-insensitive, so `Demo@email.com` is found too) with a Hyundai Creta (80,000 km mileage, last service 01.03.2026), so a reviewer does not have to create a profile from scratch. For an end-to-end demonstration without a single manual click — see `backend/scripts/prove_concurrency.py`/`prove_full_cycle.py` in the "Tests" section below.*

## Тесты / Tests

Backend-тесты гоняются в отдельном контейнере с отдельной БД (`db_test`/`backend_test`, профиль `test` в `docker-compose.yml`), чтобы pytest не мог зацепить данные живой станции, которую параллельно тестируют руками:

*Backend tests run in a separate container with a separate database (`db_test`/`backend_test`, the `test` profile in `docker-compose.yml`), so that pytest cannot touch the data of the live station that is being tested by hand in parallel:*

```bash
docker compose --profile test run --rm backend_test pytest -q
```

Миграции для `db_test` тоже применяются автоматически тем же `entrypoint.sh` перед запуском `pytest` — вручную ничего накатывать не нужно.

*Migrations for `db_test` are also applied automatically by the same `entrypoint.sh` before `pytest` starts — nothing has to be applied manually.*

Так было не всегда — до 2026-09-15 тесты запускались через `docker compose exec backend pytest`, то есть на той же БД, что и живой backend; это несколько раз приводило к утечке тестовых данных и один раз испортило накопленную выручку станции (детали и разбор — `logs/DECISIONS_LOG.md`).

*It was not always like this — until 2026-09-15 tests were run via `docker compose exec backend pytest`, i.e. on the same database as the live backend; this repeatedly leaked test data and once corrupted the station's accumulated revenue (details and analysis — `logs/DECISIONS_LOG.md`).*

Быстрая неразрушающая проверка всего сразу (health-check двух сервисов + цепочка миграций + `alembic check` + тесты, всё против изолированной `db_test`) — `bash scripts/verify.sh`; `bash scripts/verify.sh --full` дополнительно прогоняет полный откат/накат схемы `db_test` (не трогает живую `db`).

*A quick non-destructive check of everything at once (health-check of two services + migration chain + `alembic check` + tests, all against the isolated `db_test`) — `bash scripts/verify.sh`; `bash scripts/verify.sh --full` additionally runs a full schema downgrade/upgrade of `db_test` (does not touch the live `db`).*

## Статус — финальный, на момент сдачи (2026-09-18) / Status — final, at the time of submission (2026-09-18)

**Работает и проверено:** весь грейд A (сквозной happy path — запись клиента, конкурентно-безопасное бронирование слотов, статусная машина заявки, realtime-обновления между несколькими открытыми клиентами), весь обязательный грейд B (хранение шин, согласование доп. работ, напоминания, перенос/отмена записи, проактивные предложения ТО и сезонное напоминание про шины, экран станции, тесты-доказательства edge-cases), и собственная фича проекта целиком — роботизация станции + ИИ-диагностика + умная парковка (C1–C7): автотаймер с очередью задач на посту, живая трансляция прогресса, ИИ-диагностика доп. работ (rule-based по умолчанию, реальный LLM опционально), сквозной сценарий-доказательство полного цикла (`backend/scripts/prove_full_cycle.py`), 6 парковочных мест с автоприёмом/автопарковкой, наценкой за простой, защитой от конфликтов постов/мест/слотов для одной машины.

***Works and verified:** all of grade A (end-to-end happy path — client booking, concurrency-safe slot reservation, the booking state machine, realtime updates across several open clients), all of the mandatory grade B (tire storage, approval of additional work, reminders, rescheduling/cancelling a booking, proactive maintenance suggestions and the seasonal tire reminder, the station screen, edge-case proof tests), and the project's own feature in full — station robotization + AI diagnostics + smart parking (C1–C7): an auto-timer with a task queue on the post, live progress broadcasting, AI diagnostics of additional work (rule-based by default, a real LLM optionally), an end-to-end full-cycle proof scenario (`backend/scripts/prove_full_cycle.py`), 6 parking spots with auto-acceptance/auto-parking, a downtime surcharge, and protection against post/spot/slot conflicts for a single car.*

**Проверено автоматически:** 155 backend-тестов (`pytest`) + 40 frontend-тестов (`vitest`) — 0 упавших. `ruff`, `eslint`, `tsc -b --force` — чисто. GitHub Actions (`.github/workflows/ci.yml`) гоняет то же самое на каждый push/PR; ветка `main` защищена (обязательные CI-чеки перед мержем, GitHub Rulesets).

***Verified automatically:** 155 backend tests (`pytest`) + 40 frontend tests (`vitest`) — 0 failures. `ruff`, `eslint`, `tsc -b --force` — clean. GitHub Actions (`.github/workflows/ci.yml`) runs the same on every push/PR; the `main` branch is protected (required CI checks before merging, GitHub Rulesets).*

**Не сделано, сознательно, по времени перед сдачей:** доп. AUTONEX-фичи C8–C13 (Real-time Control Center, AI Service Scheduler, автономный режим, автосчета, кастомер-дэшборд, рейтинги) — каждая зависит от C7 и могла бы наращиваться дальше, но не входила в обязательный объём Задания 12. Из полировки (грейд D) открыт только D4 (доп. фильтры в истории визитов) — остальное закрыто. Подробности и обоснование порядка отсечения — в `logs/EXECUTION_PLAN.md` (разделы "Итоговое состояние" и "Как режем, если время не хватит") и в разделе ниже.

***Deliberately not done, due to time before submission:** the additional AUTONEX features C8–C13 (Real-time Control Center, AI Service Scheduler, autonomous mode, automatic invoices, customer dashboard, ratings) — each depends on C7 and could be built up further, but they were not part of the mandatory scope of Task 12. Of the polish (grade D) only D4 (extra filters in the visit history) is open — everything else is closed. Details and the rationale for the cut-off order are in `logs/EXECUTION_PLAN.md` (the "Итоговое состояние" and "Как режем, если время не хватит" sections) and in the section below.*

**Важное для честности:** 2026-09-17 в проект отдельно запускался ещё один AI-инструмент для аудита (не в рамках этой основной сессии) — он нашёл реальную проблему (счётчик выручки `StationStats` мог расходиться с фактическими данными, см. регистр багов 2026-09-15) и переделал `/station/stats` на подсчёт из неизменяемого архива заявок; заодно добавил `AGENTS.md` и CI-workflow. Его собственная миграция при этом содержала баг (сравнение enum-статуса в неверном регистре) и не пересобрала Docker-образ — из-за чего на живом backend упала архивация КАЖДОЙ выданной машины. Оба факта — находка и поломка — зафиксированы честно в `logs/DECISIONS_LOG.md` (2026-09-18) и в реестре багов `logs/EXECUTION_PLAN.md`; поломка исправлена, находка (расчёт выручки из архива) — оставлена как более надёжное решение.

***For honesty:** on 2026-09-17 another AI tool was run on the project separately for an audit (outside this main session) — it found a real problem (the `StationStats` revenue counter could diverge from the actual data, see the 2026-09-15 bug registry) and reworked `/station/stats` to compute from the immutable booking archive; it also added `AGENTS.md` and the CI workflow. Its own migration, however, contained a bug (the enum status was compared in the wrong case) and it did not rebuild the Docker image — which made archiving of EVERY issued car fail on the live backend. Both facts — the finding and the breakage — are recorded honestly in `logs/DECISIONS_LOG.md` (2026-09-18) and in the bug registry of `logs/EXECUTION_PLAN.md`; the breakage was fixed, the finding (computing revenue from the archive) was kept as the more reliable solution.*

**Последний день работы (2026-09-18) целиком ушёл на укрепление уже сделанного, не на новые фичи:** починка чужого сломанного аудита, код-ревью найденных гонок в парковке, полная защита от конфликтов "одна машина — два поста/два места одновременно" (найдены по прямой просьбе пользователя придумать конфликтные сценарии), правило "не паркуй раньше часа до записи", резерв места под машину в работе, единая цветовая схема постов/парковки, обратный отсчёт для длинных услуг (часы, не голые минуты), логирование фоновых джобов, полный набор фронтенд-тестов (был 0), защита ветки `main`. Полный список — в `logs/EXECUTION_PLAN.md`, реестр багов там же.

***The last day of work (2026-09-18) went entirely into hardening what was already built, not into new features:** fixing the third-party audit's breakage, code review of the races found in parking, full protection against "one car — two posts/two spots at once" conflicts (found at the user's direct request to invent conflict scenarios), the "don't park earlier than an hour before the appointment" rule, a reserved spot for a car in service, a unified colour scheme for posts/parking, a countdown for long services (hours, not bare minutes), logging of background jobs, a full set of frontend tests (there were 0), and protection of the `main` branch. The full list is in `logs/EXECUTION_PLAN.md`, the bug registry is there too.*

Актуальный прогресс по шагам и реестр найденных багов — в `logs/EXECUTION_PLAN.md`, полная хронология решений — в `logs/DECISIONS_LOG.md`.

*Current per-step progress and the registry of found bugs are in `logs/EXECUTION_PLAN.md`, the full chronology of decisions is in `logs/DECISIONS_LOG.md`.*

## Что сделали бы следующим заходом / What we would do next

По приоритету, если бы работа над проектом продолжилась:

*In priority order, if work on the project were to continue:*

1. **C8 — Real-time AUTONEX Control Center.** Расширение экрана станции (B7): единая живая панель постов + парковки + агрегированных счётчиков на одном SSE-потоке, без разделения на отдельные виджеты, как сейчас.
   *An extension of the station screen (B7): a single live panel of posts + parking + aggregated counters on one SSE stream, without splitting into separate widgets as it is now.*
2. **C9 — AI Service Scheduler.** Подбор поста/слота с учётом типа услуги/автомобиля и текущей загрузки станции, а не первого свободного — реальная оптимизация, а не просто занятость.
   *Choosing a post/slot based on the service/car type and the station's current load, not just the first free one — real optimization, not mere availability.*
3. **C10–C11 — Autonomous Vehicle Mode + Automatic Invoice.** Полностью автономный цикл выдачи без единого ручного клика станции + автоматическая детализированная квитанция (услуги + доп. работы + наценка парковки в одном документе, не только в `total_price`).
   *A fully autonomous issuing cycle without a single manual station click + an automatic itemized receipt (services + additional work + parking surcharge in one document, not only in `total_price`).*
4. **C12–C13 — Customer Dashboard, Rating & AI Feedback Analysis.** Расширенный кабинет клиента с историей/аналитикой; оценка визита клиентом + агрегация ИИ по фидбеку.
   *An extended client cabinet with history/analytics; visit rating by the client + AI aggregation of the feedback.*
5. **Авторизация станции.** Сейчас экран станции открыт без входа (см. `buisness/ARCHITECTURE.md`, "Открытые вопросы") — зафиксировано честно, не забыто.
   ***Station authorization.** The station screen is currently open without login (see `buisness/ARCHITECTURE.md`, "Открытые вопросы") — recorded honestly, not forgotten.*
6. **Часовой пояс станции, а не устройства клиента**, для расчёта суток слотов — путь решения уже описан в `buisness/ARCHITECTURE.md`.
   ***The station's time zone, not the client device's**, for computing slot days — the solution path is already described in `buisness/ARCHITECTURE.md`.*
7. **Диагностика по реальным метаданным услуги**, а не по одному ключевому слову "ТО" — варианты развития уже зафиксированы в `buisness/ARCHITECTURE.md` (раздел про C4).
   ***Diagnostics based on real service metadata**, not on the single keyword "ТО" — the development options are already recorded in `buisness/ARCHITECTURE.md` (the C4 section).*
8. **D4** — доп. фильтры/поиск в истории визитов (`GET /station/archive`) — сейчас только пагинация.
   ***D4** — extra filters/search in the visit history (`GET /station/archive`) — currently only pagination.*
9. **`npm audit`** (2026-09-18, при добавлении `package-lock.json`) сообщает 4 уязвимости (3 moderate, 1 high) в `esbuild`/`react-router` — обе чинятся только через мажорное обновление (`vite@8`, `react-router-dom@7`) с breaking changes. Не тронуто прямо сейчас: риск сломать рабочий happy path выше пользы от исправления. Сознательно отложено, не забыто.
   ***`npm audit`** (2026-09-18, when `package-lock.json` was added) reports 4 vulnerabilities (3 moderate, 1 high) in `esbuild`/`react-router` — both are fixed only via a major upgrade (`vite@8`, `react-router-dom@7`) with breaking changes. Not touched for now: the risk of breaking the working happy path outweighs the benefit of the fix. Deliberately postponed, not forgotten.*
10. **Расширить фронтенд-тесты (D2) дальше unit-уровня** — сейчас 40 тестов покрывают чистые функции, статусную логику и дебаунс-хук; полноценные component-тесты (рендер страниц с моками API) не писали — не было времени, а из статических находок (линтер) уже вытащили больше реальных багов, чем ожидали.
    ***Extend the frontend tests (D2) beyond the unit level** — currently 40 tests cover pure functions, status logic and the debounce hook; full component tests (rendering pages with API mocks) were not written — there was no time, and the static findings (linter) already surfaced more real bugs than expected.*
11. **Единый реестр физических мест (посты + парковка) вместо двух параллельных проверок.** Сегодня закрыты конфликты "машина на двух постах"/"машина на посту и парковке" точечными проверками по `car_id` в нескольких местах (`bookings.py`, `parking.py`) — работает и покрыто тестами, но при следующей физической сущности (не пост и не парковка) придётся добавлять четвёртую копию той же проверки. Красивее — одна общая функция "где сейчас эта машина", вызываемая из всех точек входа.
    ***A single registry of physical places (posts + parking) instead of two parallel checks.** Today the "car on two posts"/"car on a post and in parking" conflicts are closed by targeted `car_id` checks in several places (`bookings.py`, `parking.py`) — it works and is covered by tests, but with the next physical entity (neither a post nor parking) a fourth copy of the same check would have to be added. Cleaner — one common "where is this car now" function called from all entry points.*

## Инструменты / Tools

Разработка ведётся с помощью Claude Code (модель Claude Sonnet 5). Основные причины выбора: модель понимает контекст всего проекта, пишет и правит код сразу в файлах, сама запускает команды и тесты, объясняет код простым языком, исправляет ошибки автоматически, экономит время на рутине, работает прямо в привычном интерфейсе VS Code, не требует переключения между окнами — подходит и новичкам, и опытным разработчикам.

*Development is done with Claude Code (the Claude Sonnet 5 model). The main reasons for choosing it: the model understands the context of the whole project, writes and edits code directly in the files, runs commands and tests itself, explains code in plain language, fixes errors automatically, saves time on routine work, works right inside the familiar VS Code interface, and does not require switching between windows — suitable for both beginners and experienced developers.*

Отдельно (2026-09-17, не в рамках этой сессии) в проекте запускался второй AI-инструмент для стороннего аудита — см. пояснение в разделе "Статус" выше и `logs/DECISIONS_LOG.md` (запись 2026-09-18) для честного разбора его находки и его же поломки.

*Separately (2026-09-17, outside this session) a second AI tool was run on the project for a third-party audit — see the explanation in the "Status" section above and `logs/DECISIONS_LOG.md` (the 2026-09-18 entry) for an honest breakdown of its finding and its breakage.*
