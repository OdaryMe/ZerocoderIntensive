"""
Дайджест: локальная аналитика по вакансиям.

Всё здесь считается обычным кодом (счётчики, суммы, сортировка)
по реальным данным приложения — без нейросети. Текстовое резюме
от ИИ опционально и живёт отдельно: см. ai_summary.py.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import filters
import relevance
from directions import get_direction

# Доступные периоды дайджеста, в днях
PERIOD_OPTIONS = [1, 3, 7, 14, 30]


def _normalize_days(value):
    """Превращает параметр периода в допустимое число дней."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 7
    return days if days in PERIOD_OPTIONS else 7


def build(jobs, days=None, criteria=None):
    """Собирает аналитику для блока «Дайджест».

    Возвращает словарь с количеством новых вакансий, частыми навыками,
    направлениями, зарплатными диапазонами и списком свежих вакансий.
    """
    days = _normalize_days(days)
    criteria = criteria or relevance.empty_criteria()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # «Новые» — по дате обнаружения системой, а не по дате публикации:
    # важно, когда вакансия попала именно к нам в ленту.
    recent = []
    for job in jobs:
        stamp = filters.job_timestamp(job, "detected_at")
        if stamp is not None and stamp >= cutoff.timestamp():
            recent.append(job)
    recent.sort(key=lambda job: filters.job_timestamp(job, "detected_at") or 0, reverse=True)

    # Навыки и направления: обычные счётчики по новым вакансиям
    skill_counter = Counter(skill for job in recent for skill in job.get("skills") or [])
    direction_counter = Counter(job.get("direction") or "other" for job in recent)

    # Зарплатные диапазоны: группируем одинаково опубликованные вилки
    salary_counter = Counter(
        filters.salary_text(job) for job in recent if filters.salary_top(job)
    )

    # «Интересные»: сортируем по оценке соответствия, если критерии заданы,
    # иначе — по свежести обнаружения.
    if relevance.is_active(criteria):
        scored = []
        for job in recent:
            copy = dict(job)
            copy["relevance"] = relevance.compute(copy, criteria)
            scored.append(copy)
        scored.sort(key=lambda job: (job["relevance"]["score"],
                                     filters.job_timestamp(job, "detected_at") or 0),
                    reverse=True)
        interesting_pool = scored
    else:
        interesting_pool = recent

    interesting = [_mini(job) for job in interesting_pool[:6]]

    # Сколько вакансий вообще со свежими данными за период (по дате публикации)
    published_in_period = sum(
        1 for job in recent
        if filters.job_timestamp(job, "published_at") is not None
        and filters.job_timestamp(job, "published_at") >= cutoff.timestamp()
    )

    return {
        "days": days,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_jobs": len(jobs),
        "new_count": len(recent),
        "published_count": published_in_period,
        "top_skills": [
            {"name": name, "count": count}
            for name, count in skill_counter.most_common(8)
        ],
        "top_directions": [
            {
                "id": direction_id,
                "label": _direction_label(direction_id),
                "color": _direction_color(direction_id),
                "count": count,
            }
            for direction_id, count in direction_counter.most_common()
        ],
        "salary_ranges": [
            {"text": text, "count": count}
            for text, count in salary_counter.most_common(6)
        ],
        "salary_coverage": {
            "with_salary": sum(1 for job in recent if filters.salary_top(job)),
            "without_salary": sum(1 for job in recent if not filters.salary_top(job)),
        },
        "interesting": interesting,
        "empty_period": not recent,
    }


def _mini(job):
    """Краткие поля вакансии для списка «интересных» в дайджесте."""
    return {
        "id": job.get("id"),
        "title": job.get("title"),
        "company": job.get("company"),
        "direction": job.get("direction"),
        "detected_at": job.get("detected_at"),
        "is_demo": bool(job.get("is_demo")),
        "salary_text": filters.salary_text(job),
        "relevance": job.get("relevance"),
    }


def _direction_label(direction_id):
    from directions import get_direction
    return get_direction(direction_id)["label"]


def _direction_color(direction_id):
    from directions import get_direction
    return get_direction(direction_id)["color"]
