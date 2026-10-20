"""
Хранение данных Signal.

Всё лежит в обычных JSON-файлах внутри папки data/:

  jobs.json          — текущий набор вакансий (демо + полученные из источников)
  demo_jobs.json     — демонстрационные записи (тестовые данные, их вы вы редактируете)
  update_status.json — статус и отчёт последнего обновления

JSON выбран вместо SQLite намеренно: на первом объёме данных файлы проще
смотреть, править руками и объяснять начинающему разработчику.
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
JOBS_FILE = DATA_DIR / "jobs.json"
DEMO_FILE = DATA_DIR / "demo_jobs.json"
STATUS_FILE = DATA_DIR / "update_status.json"


# ---------------------------------------------------------------------------
# Время и работа с JSON
# ---------------------------------------------------------------------------

def utc_now():
    """Текущие дату и время в UTC (единый часовой пояс для всех данных)."""
    return datetime.now(timezone.utc)


def now_iso():
    """Текущее время в формате ISO — так оно хранится в JSON."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path, default):
    """Читает JSON-файл; при отсутствии или повреждении возвращает default.

    Ошибка файла не должна ронять приложение — поэтому мы ловим исключения
    и аккуратно сообщаем о проблеме в консоль разработчика.
    """
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        print(f"[storage] Файл {path.name} повреждён, используется значение по умолчанию",
              file=sys.stderr)
        return default


def write_json(path, data):
    """Записывает JSON атомарно: сначала во временный файл, потом подменяет.

    Так обычный сбой записи не оставит вместо базы полузаписанный мусор.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temp_path.replace(path)


# ---------------------------------------------------------------------------
# Демонстрационные данные
# ---------------------------------------------------------------------------

def build_demo_jobs():
    """Собирает вакансии из data/demo_jobs.json с актуальными датами.

    В демо-файле даты хранятся как «сколько дней назад» (published_days_ago,
    detected_days_ago). Здесь они превращаются в конкретные календарные даты,
    поэтому демонстрация выглядит свежей даже через неделю после первого запуска.
    """
    raw = read_json(DEMO_FILE, [])
    if not isinstance(raw, list):
        print("[storage] data/demo_jobs.json должен содержать список", file=sys.stderr)
        return []

    today = date.today()
    now = utc_now()
    jobs = []

    for position, item in enumerate(raw):
        if not isinstance(item, dict) or not item.get("title"):
            continue  # пропускаем заведомо неполные записи

        job = dict(item)

        published_days = job.pop("published_days_ago", None)
        detected_days = job.pop("detected_days_ago", 0)

        job["published_at"] = (
            (today - timedelta(days=published_days)).isoformat()
            if published_days is not None else None
        )
        # Время обнаружения слегка разбросано, чтобы записи не совпадали
        # до минуты и корректно сортировались.
        job["detected_at"] = (
            now - timedelta(days=detected_days, minutes=position * 17 % 240)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        job["checked_at"] = now_iso()

        job["source"] = "demo"
        job["source_id"] = str(job.get("source_id") or f"{position + 1:03d}")
        job["is_demo"] = True
        job["id"] = f"demo-{job['source_id']}"
        job["url"] = job.get("url")  # у демо-записей ссылки нет — это нормально

        jobs.append(job)

    return jobs


def merge_demo(current_jobs, demo_jobs):
    """Заменяет демо-записи на свежие, сохраняя вакансии из реальных источников."""
    real_jobs = [job for job in current_jobs if not job.get("is_demo")]
    real_ids = {job.get("id") for job in real_jobs}

    fresh_demo = []
    seen = set()
    for job in demo_jobs:
        if job["id"] in seen or job["id"] in real_ids:
            continue  # защита от дублей
        seen.add(job["id"])
        fresh_demo.append(job)

    return real_jobs + fresh_demo


def merge_feed_jobs(current_jobs, incoming_jobs):
    """Добавляет вакансии из источника, убирая дубли по паре (source, source_id).

    Если запись уже есть — обновляем меняющиеся поля и время последней
    проверки, но сохраняем исходную дату обнаружения.
    """
    index = {(job.get("source"), job.get("source_id")): job for job in current_jobs}
    added, checked = 0, 0

    for job in incoming_jobs:
        key = (job.get("source"), job.get("source_id"))
        existing = index.get(key)

        if existing is None:
            current_jobs.append(job)
            index[key] = job
            added += 1
        else:
            for field in ("title", "company", "description", "url", "published_at",
                          "skills", "direction", "level", "work_format"):
                new_value = job.get(field)
                if new_value not in (None, "") and new_value != existing.get(field):
                    existing[field] = new_value
            existing["checked_at"] = job.get("checked_at") or now_iso()
        checked += 1

    return current_jobs, {"added": added, "checked": checked}


# ---------------------------------------------------------------------------
# Основные операции с базой вакансий
# ---------------------------------------------------------------------------

def load_jobs():
    """Возвращает список всех вакансий; при первом запуске создаёт базу из демо."""
    if not JOBS_FILE.exists():
        jobs = build_demo_jobs()
        write_json(JOBS_FILE, jobs)
        return jobs

    data = read_json(JOBS_FILE, None)
    if not isinstance(data, list):
        # Файл потерян или испорчен — честно пересоздаём из демо-файла.
        jobs = build_demo_jobs()
        write_json(JOBS_FILE, jobs)
        return jobs

    return [job for job in data if isinstance(job, dict) and job.get("id")]


def save_jobs(jobs):
    """Сохраняет список вакансий в data/jobs.json."""
    write_json(JOBS_FILE, jobs)


def find_job(job_id):
    """Возвращает вакансию по её идентификатору или None."""
    for job in load_jobs():
        if job.get("id") == job_id:
            return job
    return None


# ---------------------------------------------------------------------------
# Статус обновления
# ---------------------------------------------------------------------------

def load_status():
    """Возвращает статус последнего обновления данных."""
    status = read_json(STATUS_FILE, None)
    if not isinstance(status, dict):
        return {
            "mode": "demo",
            "last_attempt": None,
            "last_success": None,
            "note": "Данные ещё не обновлялись",
            "sources": [],
            "total_jobs": 0,
        }
    return status


def save_status(status):
    """Сохраняет статус обновления."""
    write_json(STATUS_FILE, status)


def startup_sync():
    """Первичная подготовка данных при запуске сервера.

    Демо-записи пересобираются с датами относительно текущего дня,
    вакансии из реальных источников не трогаем.
    """
    jobs = load_jobs()
    demo_jobs = build_demo_jobs()
    jobs = merge_demo(jobs, demo_jobs)
    save_jobs(jobs)

    status = load_status()
    status.update({
        "last_attempt": now_iso(),
        "last_success": now_iso(),
        "note": "Демо-данные перегенерированы при запуске сервера",
        "sources": [{
            "name": "Демо-данные (тестовые)",
            "kind": "demo",
            "ok": True,
            "added": 0,
            "checked": len(demo_jobs),
            "error": None,
        }],
        "total_jobs": len(jobs),
    })
    save_status(status)
    return jobs
