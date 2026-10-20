"""
Фильтрация, сортировка и выгрузка вакансий.

Здесь только чистые функции: принимают список вакансий и параметры запроса —
возвращают новый список. Сети и файлов нет, поэтому логику легко проверять.
"""

import csv
import io
from collections import Counter
from datetime import datetime, timezone

import directions
import relevance

# Вакансия считается «новой» столько дней после обнаружения
NEW_WINDOW_DAYS = 3
MAX_QUERY_LENGTH = 200
MAX_RESPONSE_ITEMS = 500   # защита: сервер не отдаёт больше этого за раз

# Допустимые варианты значений параметра сортировки
SORT_OPTIONS = {"detected", "published", "salary", "relevance"}
# Допустимые периоды публикации (в днях)
DATE_RANGE_OPTIONS = {1, 3, 7, 14, 30, 90}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def parse_datetime(value):
    """Превращает строку даты/времени в объект datetime (всегда в UTC).

    Понимает и «2026-10-15», и «2026-10-15T09:30:00Z». Неверные строки
    дают None — так некорректные данные из источника не ломают сортировку.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def job_timestamp(job, field):
    """Метка времени поля вакансии в секундах (или None)."""
    parsed = parse_datetime(job.get(field))
    return parsed.timestamp() if parsed else None


def is_new(job):
    """True, если вакансия обнаружена недавно (см. NEW_WINDOW_DAYS)."""
    stamp = job_timestamp(job, "detected_at")
    if stamp is None:
        return False
    age_days = (datetime.now(timezone.utc).timestamp() - stamp) / 86400
    return age_days <= NEW_WINDOW_DAYS


def salary_top(job):
    """Верхняя граница зарплатной вилки или None, если зарплаты нет."""
    return job.get("salary_max") or job.get("salary_min")


def salary_text(job):
    """Человекочитаемая строка зарплаты или «Не указана».

    Мы никогда не подставляем предполагаемую сумму — только то,
    что опубликовано в самой вакансии.
    """
    low = job.get("salary_min")
    high = job.get("salary_max")
    if low is None and high is None:
        return "Не указана"

    currency = job.get("salary_currency") or ""
    period = job.get("salary_period")
    period_suffix = {"month": "/мес", "year": "/год", "hour": "/час"}.get(period, "")

    def fmt(value):
        return f"{value:,.0f}".replace(",", " ")

    if low is not None and high is not None and low != high:
        return f"{fmt(low)} – {fmt(high)} {currency}{period_suffix}".strip()
    value = low if low is not None else high
    return f"{fmt(value)} {currency}{period_suffix}".strip()


def _job_search_text(job):
    """Единый текст для полнотекстового поиска: название, компания,
    описание, навыки и подпись направления."""
    parts = [
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", ""),
        job.get("location", ""),
        " ".join(job.get("skills") or []),
        directions.get_direction(job.get("direction")).get("label", ""),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _split_multi(value):
    """Разбивает «a,b,c» на список значений фильтра."""
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _positive_int(value):
    """Целое положительное число из параметра запроса или None."""
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# ---------------------------------------------------------------------------
# Фильтрация
# ---------------------------------------------------------------------------

def apply_filters(jobs, params, criteria=None, skip=None):
    """Применяет все фильтры и сортировку к списку вакансий.

    jobs     — полный список вакансий;
    params   — параметры запроса (request.args);
    criteria — критерии пользователя (для оценки соответствия);
    skip     — множество имён фильтров, которые НЕ применять.
               Нужно, чтобы посчитать счётчики «сколько будет,
               если выбрать другой вариант этого же фильтра».
    """
    criteria = criteria or relevance.empty_criteria()
    skip = skip or set()
    now_stamp = datetime.now(timezone.utc).timestamp()

    query = (params.get("q") or "").strip()[:MAX_QUERY_LENGTH].casefold()

    direction = params.get("direction") if "direction" not in skip else ""
    levels = _split_multi(params.get("level")) if "level" not in skip else []
    formats = _split_multi(params.get("work_format")) if "work_format" not in skip else []
    countries = _split_multi(params.get("country")) if "country" not in skip else []
    employments = _split_multi(params.get("employment")) if "employment" not in skip else []

    # Значения фильтров сверяем со справочниками: мусор из запроса игнорируется
    known_levels = {item["id"] for item in directions.LEVELS}
    levels = [value for value in levels if value in known_levels]
    known_formats = {item["id"] for item in directions.WORK_FORMATS}
    formats = [value for value in formats if value in known_formats]
    known_employment = {item["id"] for item in directions.EMPLOYMENT_TYPES}
    employments = [value for value in employments if value in known_employment]

    salary_min = _positive_int(params.get("salary_min")) if "salary_min" not in skip else None
    salary_currency = ""
    if "salary_min" not in skip:
        raw_currency = (params.get("salary_currency") or "").strip().upper()
        # Валюта — три буквы; всё остальное отбрасываем
        if len(raw_currency) == 3 and raw_currency.isalpha():
            salary_currency = raw_currency
    publish_days = None
    if "days" not in skip:
        days_value = _positive_int(params.get("days"))
        if days_value in DATE_RANGE_OPTIONS:
            publish_days = days_value

    new_only = params.get("new") == "1" and "new" not in skip
    only_favorites = params.get("fav") == "1" and "fav" not in skip
    favorite_ids = set(_split_multi(params.get("fav_ids")))
    hidden_ids = set(_split_multi(params.get("hide_ids")))

    result = []
    for job in jobs:
        # Исключённые пользователем вакансии (кнопка «скрыть»)
        if job.get("id") in hidden_ids:
            continue
        # Режим «только избранное»: список id приходит с клиента,
        # потому что избранное хранится в браузере
        if only_favorites and job.get("id") not in favorite_ids:
            continue

        if query and query not in _job_search_text(job):
            continue
        if direction and job.get("direction") != direction:
            continue
        if levels and job.get("level") not in levels:
            continue
        if formats and job.get("work_format") not in formats:
            continue
        if countries and (job.get("country") or "none") not in countries:
            continue
        if employments and (job.get("employment") or "none") not in employments:
            continue

        # Зарплатный фильтр: вакансии без зарплаты сюда не попадают.
        # Если указана валюта — сравниваем только суммы в ней,
        # без (выдуманного) пересчёта курсов.
        if salary_currency and (job.get("salary_currency") or "") != salary_currency:
            continue
        if salary_min is not None:
            top = salary_top(job)
            if top is None or top < salary_min:
                continue

        # Фильтр по дате публикации
        if publish_days is not None:
            published = job_timestamp(job, "published_at")
            if published is None or published < now_stamp - publish_days * 86400:
                continue

        if new_only and not is_new(job):
            continue

        # Оценка соответствия добавляется только при заданных критериях
        if relevance.is_active(criteria):
            job = dict(job)
            job["relevance"] = relevance.compute(job, criteria)

        result.append(job)

    return sort_jobs(result, params.get("sort"), criteria)


def sort_jobs(jobs, order, criteria=None):
    """Сортирует вакансии. Записи без данных по полю уходят в конец."""
    if order not in SORT_OPTIONS:
        order = "detected"

    def detected(job):
        return job_timestamp(job, "detected_at")

    def published(job):
        return job_timestamp(job, "published_at")

    def score(job):
        return (job.get("relevance") or {}).get("score") or 0

    if order == "published":
        key = lambda job: (1 if published(job) else 0, published(job) or 0, detected(job) or 0)
    elif order == "salary":
        key = lambda job: (1 if salary_top(job) else 0, salary_top(job) or 0, detected(job) or 0)
    elif order == "relevance":
        key = lambda job: (score(job), detected(job) or 0)
    else:  # по дате обнаружения
        key = lambda job: (1 if detected(job) else 0, detected(job) or 0)

    return sorted(jobs, key=key, reverse=True)


# ---------------------------------------------------------------------------
# Счётчики для интерфейса фильтров
# ---------------------------------------------------------------------------

FACET_FIELDS = ("direction", "level", "work_format", "country", "employment")


def build_facet_counts(jobs, params, criteria=None):
    """Считает, сколько вакансий подходит под каждый вариант каждого фильтра.

    Для каждого поля фильтры применяются заново, кроме самого этого поля:
    так счётчик не «замерзает» на уже выбранном значении, а показывает,
    сколько ещё результатов можно получить.
    """
    counts = {}
    for field in FACET_FIELDS:
        candidates = apply_filters(jobs, params, criteria, skip={field})
        counter = Counter((job.get(field) or "none") for job in candidates)
        counts[field] = dict(counter)
    return counts


# ---------------------------------------------------------------------------
# Выгрузка в CSV
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    ("Название", lambda job: job.get("title") or ""),
    ("Компания", lambda job: job.get("company") or ""),
    ("Направление", lambda job: directions.get_direction(job.get("direction"))["label"]),
    ("Уровень", lambda job: job.get("level") or "none"),
    ("Формат работы", lambda job: job.get("work_format") or "none"),
    ("Страна / регион", lambda job: job.get("country") or ""),
    ("Занятость", lambda job: job.get("employment") or "none"),
    ("Зарплата", lambda job: salary_text(job)),
    ("Опубликована", lambda job: job.get("published_at") or ""),
    ("Обнаружена", lambda job: job.get("detected_at") or ""),
    ("Источник", lambda job: job.get("source") or ""),
    ("Тестовые данные", lambda job: "да" if job.get("is_demo") else "нет"),
    ("Ссылка", lambda job: job.get("url") or ""),
]


def jobs_to_csv(jobs):
    """Собирает список вакансий в строку CSV.

    Используется точка с запятой как разделитель и BOM в начале файла —
    тогда Excel корректно открывает кириллицу.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([title for title, _ in CSV_COLUMNS])
    for job in jobs:
        writer.writerow([getter(job) for _, getter in CSV_COLUMNS])
    # BOM в начале файла, чтобы Excel правильно открывал кириллицу
    return "﻿" + buffer.getvalue()
