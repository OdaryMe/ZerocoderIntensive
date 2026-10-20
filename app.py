"""
Signal — AI Job Digest
Flask-приложение для поиска и анализа AI-вакансий.

Запуск:  python app.py
Откройте в браузере: http://127.0.0.1:5000
"""

import os
import sys

# На некоторых сборках Python (например, встроенный в приложение)
# папка скрипта не добавляется в sys.path автоматически — добавляем сами,
# чтобы работали локальные импорты (storage, sources и другие).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

load_dotenv()  # читает переменные окружения из файла .env (если он есть)

import ai_summary
import directions
import digest as digest_module
import filters
import relevance
import sources
import storage

app = Flask(__name__)
app.json.ensure_ascii = False  # кириллица в JSON-ответах без \uXXXX

# Один раз при старте: создаём или обновляем локальные данные (демо-режим)
storage.startup_sync()


# ---------------------------------------------------------------------------
# Вспомогательные функции и фильтры шаблонов
# ---------------------------------------------------------------------------

def build_page_context():
    """Общие данные для главной страницы: статистика, статус, справочники."""
    jobs = storage.load_jobs()
    status = storage.load_status()

    stats = {
        "total": len(jobs),
        "demo": sum(1 for job in jobs if job.get("is_demo")),
        "directions": len(directions.DIRECTIONS),
        "new": sum(1 for job in jobs if filters.is_new(job)),
        "last_success": status.get("last_success"),
    }

    # Валюты, реально встречающиеся в данных — для фильтра по зарплате
    currencies = sorted({job.get("salary_currency") for job in jobs
                         if job.get("salary_currency")})

    return {
        "stats": stats,
        "status": status,
        "status_label": make_status_label(status),
        "mode": sources.current_mode(),
        "feeds": sources.get_feed_urls(),
        "directions": directions.DIRECTIONS,
        "levels": directions.LEVELS,
        "formats": directions.WORK_FORMATS,
        "employments": directions.EMPLOYMENT_TYPES,
        "currencies": currencies,
        "period_options": digest_module.PERIOD_OPTIONS,
        "ai": ai_summary.ai_status(),
    }


def make_status_label(status):
    """Короткая подпись статуса данных для шапки сайта."""
    last_success = status.get("last_success")
    if not last_success:
        return "Данные ещё не обновлялись"
    parsed = filters.parse_datetime(last_success)
    if parsed is None:
        return "Данные ещё не обновлялись"
    return "Обновлено " + parsed.strftime("%d.%m, %H:%M")


def decorate_job(job, criteria=None):
    """Добавляет к вакансии поля, нужные интерфейсу (подписи, флаги, оценку)."""
    direction = directions.get_direction(job.get("direction"))
    item = dict(job)
    item["direction_label"] = direction["label"]
    item["direction_color"] = direction["color"]
    item["is_new"] = filters.is_new(job)
    item["salary_text"] = filters.salary_text(job)
    if criteria is not None and "relevance" not in item and relevance.is_active(criteria):
        item["relevance"] = relevance.compute(item, criteria)
    return item


@app.template_filter("dt")
def date_filter(value, fmt="%d.%m.%Y"):
    """Фильтр шаблона: показать дату/время в удобном виде, а не сырую строку."""
    parsed = filters.parse_datetime(value)
    if parsed is None:
        return "—"
    return parsed.strftime(fmt)


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Главная страница: первый экран, лента вакансий, дайджест, источники."""
    return render_template("index.html", **build_page_context())


@app.errorhandler(404)
def page_not_found(_error):
    ctx = build_page_context()
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Запись не найдена"}), 404
    ctx["message"] = "Такой страницы нет: возможно, ссылка устарела или в адресе опечатка."
    return render_template("404.html", **ctx), 404


@app.errorhandler(500)
def server_error(_error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Внутренняя ошибка сервера"}), 500
    ctx = build_page_context()
    ctx["message"] = "Что-то пошло не так"
    return render_template("404.html", **ctx), 500


# ---------------------------------------------------------------------------
# API: вакансии
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
def api_jobs():
    """Список вакансий с учётом всех фильтров, сортировки и критериев."""
    jobs = storage.load_jobs()
    params = request.args
    criteria = relevance.parse_criteria(params.get("criteria"))

    matched = filters.apply_filters(jobs, params, criteria)

    return jsonify({
        "ok": True,
        "total": len(matched),
        "items": [decorate_job(job, criteria) for job in matched[:filters.MAX_RESPONSE_ITEMS]],
        "facets": filters.build_facet_counts(jobs, params, criteria),
        "criteria_active": relevance.is_active(criteria),
    })


@app.get("/api/jobs/<job_id>")
def api_job_detail(job_id):
    """Полная информация об одной вакансии (для панели подробностей)."""
    if len(job_id) > 100:
        return jsonify({"ok": False, "error": "Некорректный идентификатор"}), 404

    job = storage.find_job(job_id)
    if job is None:
        return jsonify({"ok": False, "error": "Вакансия не найдена"}), 404

    criteria = relevance.parse_criteria(request.args.get("criteria"))
    item = decorate_job(job, criteria)
    item["source_status"] = job.get("checked_at")
    return jsonify({"ok": True, "job": item})


# ---------------------------------------------------------------------------
# API: обновление данных и статус
# ---------------------------------------------------------------------------

@app.post("/api/update")
def api_update():
    """Запускает обновление из всех настроенных источников (вручную).

    Реальных источников пока может не быть — тогда демо-источник честно
    сообщает, что данные тестовые, а отчёт показывает, что RSS не заданы.
    """
    jobs = storage.load_jobs()
    jobs, report = sources.perform_update(jobs)
    storage.save_jobs(jobs)

    any_ok = any(source.get("ok") for source in report["sources"])
    status = dict(report)
    status["note"] = (
        "Обновление выполнено" if any_ok else "Ни один источник не ответил"
    )
    if any_ok:
        status["last_success"] = report["last_attempt"]
    else:
        previous = storage.load_status().get("last_success")
        status["last_success"] = previous  # не выдаём неудачу за успех
    status["total_jobs"] = len(jobs)
    storage.save_status(status)

    return jsonify({"ok": any_ok, "status": status, "status_label": make_status_label(status)})


@app.get("/api/status")
def api_status():
    """Текущий статус данных: режим, время, отчёт по источникам."""
    status = storage.load_status()
    status["mode"] = sources.current_mode()
    return jsonify({
        "ok": True,
        "status": status,
        "status_label": make_status_label(status),
    })


# ---------------------------------------------------------------------------
# API: дайджест, AI-резюме, выгрузка
# ---------------------------------------------------------------------------

@app.get("/api/digest")
def api_digest():
    """Локальная аналитика по вакансиям за выбранный период."""
    jobs = storage.load_jobs()
    criteria = relevance.parse_criteria(request.args.get("criteria"))
    data = digest_module.build(jobs, request.args.get("days"), criteria)
    return jsonify({"ok": True, "digest": data})


@app.post("/api/ai-summary")
def api_ai_summary():
    """Текстовое резюме дайджеста от внешнего AI-сервиса (опционально).

    Если ключ не настроен — возвращаем понятную подсказку, а не ошибку
    выдуманной «заглушке».
    """
    payload = request.get_json(silent=True) or {}
    jobs = storage.load_jobs()
    criteria = relevance.parse_criteria(payload.get("criteria"))
    data = digest_module.build(jobs, payload.get("days"), criteria)
    result = ai_summary.generate_summary(data)
    return jsonify({"ok": result["ok"], "result": result})


@app.get("/api/export.csv")
def api_export_csv():
    """Выгрузка текущей выборки в CSV (те же фильтры, что и в ленте)."""
    jobs = storage.load_jobs()
    params = request.args
    criteria = relevance.parse_criteria(params.get("criteria"))
    matched = filters.apply_filters(jobs, params, criteria)[:filters.MAX_RESPONSE_ITEMS]

    csv_text = filters.jobs_to_csv(matched)
    filename = f"signal-jobs-{storage.utc_now().strftime('%Y%m%d-%H%M')}.csv"

    # stream_with_context нужен, потому что мы работаем с request внутри
    # генератора ответа
    return Response(
        stream_with_context(iter([csv_text])),
        mimetype="text/csv",
        headers={"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    print("=" * 60)
    print("Signal — AI Job Digest")
    print(f"  Адрес:  http://{host}:{port}")
    print(f"  Режим:  {sources.current_mode()}")
    print(f"  Источники RSS: {len(sources.get_feed_urls())}")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug)
