"""
Оценка соответствия вакансии критериям пользователя.

Оценка — это прозрачный набор правил «сколько баллов за что», а не мнение
нейросети: рядом с процентом в интерфейсе всегда видно, из чего он сложился.
Критерии задаются пользователем в блоке «Мои критерии» и хранятся
в браузере (localStorage), поэтому сервер не требует регистрации.
"""

import json

DIRECTION_POINTS = 40    # вакансия в приоритетном направлении
SKILL_POINTS = 30        # доля желаемых навыков, которые нашлись в вакансии
KEYWORD_POINTS = 20      # желаемые навыки упомянуты прямо в заголовке
SALARY_POINTS = 10       # зарплата не ниже порога пользователя
MAX_SCORE = 100


def empty_criteria():
    """Пустые критерии — оценка соответствия в таком случае не считается."""
    return {"directions": [], "skills": [], "min_salary": None}


def parse_criteria(raw):
    """Безопасно разбирает критерии из JSON-строки параметров запроса.

    Любой некорректный ввод заменяется пустыми критериями, а не вызывает
    ошибку: запрос пришёл из браузера и не считается доверенным.
    """
    if not raw:
        return empty_criteria()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return empty_criteria()
    if not isinstance(data, dict):
        return empty_criteria()

    # Направления: список идентификаторов, не длиннее 20
    raw_directions = data.get("directions") or []
    if not isinstance(raw_directions, list):
        raw_directions = []
    direction_ids = [str(item)[:40] for item in raw_directions][:20]

    # Навыки: можно передать строку через запятую или список строк
    raw_skills = data.get("skills") or []
    if isinstance(raw_skills, str):
        raw_skills = raw_skills.split(",")
    if not isinstance(raw_skills, list):
        raw_skills = []
    skills = [str(item).strip()[:60] for item in raw_skills if str(item).strip()][:20]

    # Минимальная зарплата: целое число
    min_salary = data.get("min_salary")
    try:
        min_salary = int(min_salary) if min_salary not in (None, "") else None
    except (TypeError, ValueError):
        min_salary = None
    if min_salary is not None and min_salary < 0:
        min_salary = None

    return {"directions": direction_ids, "skills": skills, "min_salary": min_salary}


def is_active(criteria):
    """Есть ли хоть один критерий — определяет, показывать ли оценку."""
    if not criteria:
        return False
    return bool(criteria.get("directions") or criteria.get("skills")
                 or criteria.get("min_salary"))


def compute(job, criteria):
    """Считает соответствие вакансии критериям: балл 0–100 и список причин.

    Возвращает словарь {"score": int, "reasons": [str]}.
    """
    score = 0
    reasons = []

    # 1. Приоритетное направление
    priority_directions = criteria.get("directions") or []
    if job.get("direction") in priority_directions:
        score += DIRECTION_POINTS
        reasons.append("Направление входит в список приоритетных")

    # 2. Желаемые навыки: ищем и в списке навыков, и в тексте вакансии
    wanted_skills = [s.casefold() for s in criteria.get("skills") or []]
    if wanted_skills:
        job_skills = [str(s).casefold() for s in job.get("skills") or []]
        job_text = f"{job.get('title', '')} {job.get('description', '')}".casefold()

        matched = []
        for skill in wanted_skills:
            if any(skill in existing for existing in job_skills) or skill in job_text:
                matched.append(skill)

        if matched:
            score += round(SKILL_POINTS * len(matched) / len(wanted_skills))
            reasons.append("Совпавшие навыки: " + ", ".join(matched[:4]))
        else:
            reasons.append("Желаемые навыки в вакансии не найдены")

        # Бонус: навык назван прямо в заголовке вакансии — это сильный сигнал
        title_low = (job.get("title") or "").casefold()
        if any(skill in title_low for skill in matched):
            bonus = min(KEYWORD_POINTS, MAX_SCORE - score)
            score += bonus
            reasons.append("Ключевой навык указан в названии должности")

    # 3. Порог зарплаты
    min_salary = criteria.get("min_salary")
    if min_salary:
        top_salary = job.get("salary_max") or job.get("salary_min")
        if top_salary is None:
            reasons.append("Зарплата в вакансии не указана")
        elif top_salary >= min_salary:
            score += SALARY_POINTS
            reasons.append(f"Зарплата не ниже порога ({min_salary:,})")
        else:
            reasons.append(f"Зарплата ниже порога ({min_salary:,})")

    return {"score": max(0, min(MAX_SCORE, score)), "reasons": reasons}
