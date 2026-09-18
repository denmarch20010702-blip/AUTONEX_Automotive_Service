import logging

from app.core.config import settings

# D3 (2026-09-18, полировка перед сдачей): раньше в проекте не было ни
# одного `logging.getLogger` — единственная видимость происходящего внутри
# фоновых джобов (sweep'ы) и pluggable-путей (ИИ-диагностика C4) — это то,
# что вручную печатает uvicorn для HTTP-запросов. Несколько мест в коде
# намеренно проглатывают исключения (гонки в sweep'ах, честный фолбэк LLM ->
# rule-based) — оправданно с точки зрения бизнес-логики (см. комментарии на
# местах), но раньше это было и не отличить от "молча ничего не произошло".
# Простой `logging` стандартной библиотеки достаточен для демо-проекта —
# внешний APM/структурированный JSON-лог был бы избыточен для скоупа
# задания и добавил бы зависимость без реальной пользы здесь.
_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _CONFIGURED = True
