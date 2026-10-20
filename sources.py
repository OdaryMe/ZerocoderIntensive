"""
Источники вакансий.

Сейчас доступны два источника:

  1. Демо-источник — тестовые записи из data/demo_jobs.json.
     Они явно помечены (is_demo = true) и в интерфейсе — бейджем «ДЕМО».
  2. RSS/Atom-ленты — адреса задаются в переменной окружения SIGNAL_FEEDS
     (см. .env.example). Это единственный способ получить реальные вакансии
     без собственного API-ключа.

Как подключить новый источник (например, публичный API):
  1. Напишите функцию, которая возвращает список словарей с полями вакансии
     (образец — функция fetch_rss_feed ниже).
  2. Вызовите её в perform_update() и передайте результат в
     storage.merge_feed_jobs().
"""

import hashlib
import html
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import storage
from directions import detect_direction, extract_skills

USER_AGENT = "SignalJobDigest/0.1 (local research prototype)"
REQUEST_TIMEOUT = 15          # секунд на запрос к источнику
MAX_ITEMS_PER_FEED = 50       # сколько элементов берём из одной ленты
DESCRIPTION_LIMIT = 400       # ограничение описания, чтобы не раздувать базу


def get_feed_urls():
    """Читает адреса RSS/Atom-лент из переменной окружения SIGNAL_FEEDS.

    Адреса разделяются запятыми или пробелами. Некорректные адреса
    пропускаются с предупреждением в консоль — одна опечатка не должна
    ломать обновление целиком.
    """
    raw = os.getenv("SIGNAL_FEEDS", "")
    urls = []

    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        if part.startswith("http://") or part.startswith("https://"):
            urls.append(part)
        else:
            print(f"[sources] Пропущен некорректный адрес ленты: {part}", file=sys.stderr)

    return urls


def current_mode():
    """Режим работы приложения: «demo» или «demo+rss»."""
    return "demo+rss" if get_feed_urls() else "demo"


# ---------------------------------------------------------------------------
# Разбор RSS/Atom
# ---------------------------------------------------------------------------

def _local_name(tag):
    """Убирает XML-пространство имён: '{ns}item' -> 'item'."""
    return tag.rsplit("}", 1)[-1]


def _child_text(element, name):
    """Возвращает текст первого подэлемента с указанным именем (без учёта ns)."""
    for child in element:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _child_link(element):
    """Возвращает ссылку элемента: RSS хранит её в тексте, Atom — в атрибуте href."""
    for child in element:
        if _local_name(child.tag) == "link":
            href = (child.get("href") or "").strip()
            if href:
                return href
            return (child.text or "").strip()
    return ""


def _strip_html(text):
    """Оставляет от HTML-описания только чистый текст (и укорачивает его)."""
    plain = re.sub(r"<[^>]+>", " ", text or "")
    plain = " ".join(html.unescape(plain).split())
    return plain[:DESCRIPTION_LIMIT]


def _parse_date(value):
    """Разбирает дату публикации из популярных формат RSS и ISO-8601."""
    if not value:
        return None
    try:  # RFC-822, как в RSS: Mon, 12 Oct 2026 09:00:00 GMT
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:  # ISO-8601, как в Atom
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _detect_work_format(text):
    """Определяет формат работы по словам из описания вакансии."""
    text_low = (text or "").casefold()
    if any(word in text_low for word in ("remote", "удалённ", "удаленн")):
        return "remote"
    if "hybrid" in text_low or "гибрид" in text_low:
        return "hybrid"
    if any(word in text_low for word in ("on-site", "офис")):
        return "office"
    return "none"


def fetch_rss_feed(feed_url):
    """Загружает одну RSS/Atom-ленту и превращает её элементы в вакансии.

    Поле company для лент заполняется названием издания (оно есть не у всех),
    уровень, зарплата и страна остаются «не указаны» — мы их не выдумываем.
    """
    request = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        xml_bytes = response.read()

    root = ET.fromstring(xml_bytes)
    host = urlparse(feed_url).netloc
    feed_title = _child_text(root, "title") or host

    items = [el for el in root.iter() if _local_name(el.tag) in ("item", "entry")]
    jobs = []

    for item in items[:MAX_ITEMS_PER_FEED]:
        title = _child_text(item, "title")
        link = _child_link(item)

        if not title or not link.startswith("http"):
            continue

        raw_description = (
            _child_text(item, "description")
            or _child_text(item, "summary")
            or _child_text(item, "content")
        )
        description = _strip_html(raw_description)
        analysis_text = f"{title} {description}"

        source_id = (
            _child_text(item, "guid")
            or hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]
        )
        # Идентификатор вакансии внутри нашего приложения: он же ключ дедупликации
        job_id = "rss-" + hashlib.sha1(
            f"{host}|{source_id}".encode("utf-8")
        ).hexdigest()[:16]

        jobs.append({
            "id": job_id,
            "source": f"rss:{host}",
            "source_id": source_id,
            "is_demo": False,
            "title": title[:200],
            "company": feed_title[:120],
            "url": link,
            "direction": detect_direction(analysis_text),
            "skills": extract_skills(analysis_text),
            "level": "none",
            "work_format": _detect_work_format(analysis_text),
            "country": "none",
            "location": "",
            "employment": "none",
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "published_at": _parse_date(
                _child_text(item, "pubDate") or _child_text(item, "published")
            ),
            "detected_at": storage.now_iso(),
            "checked_at": storage.now_iso(),
            "description": description,
        })

    return jobs


# ---------------------------------------------------------------------------
# Обновление целиком
# ---------------------------------------------------------------------------

def perform_update(current_jobs):
    """Обновляет вакансии из всех настроенных источников.

    Возвращает пару (список_вакансий, отчёт). Ошибка одного источника
    не прерывает обновление остальных — она попадает в отчёт.
    """
    jobs = current_jobs
    sources_report = []
    mode = current_mode()

    # 1) Демонстрационные данные (тестовые) — они всегда доступны.
    try:
        demo_jobs = storage.build_demo_jobs()
        before = len(jobs)
        jobs = storage.merge_demo(jobs, demo_jobs)
        sources_report.append({
            "name": "Демо-данные (тестовые)",
            "kind": "demo",
            "ok": True,
            "added": max(0, len(jobs) - before),
            "checked": len(demo_jobs),
            "error": None,
        })
    except Exception as exc:  # noqa: BLE001 — отчёт важнее типа ошибки
        sources_report.append({
            "name": "Демо-данные (тестовые)",
            "kind": "demo",
            "ok": False,
            "added": 0,
            "checked": 0,
            "error": str(exc),
        })

    # 2) Реальные источники — RSS/Atom-ленты из переменной окружения.
    feed_urls = get_feed_urls()
    if not feed_urls:
        sources_report.append({
            "name": "RSS-ленты",
            "kind": "rss",
            "ok": True,
            "added": 0,
            "checked": 0,
            "error": None,
            "note": "Не заданы: укажите SIGNAL_FEEDS в файле .env",
        })

    for feed_url in feed_urls:
        host = urlparse(feed_url).netloc or feed_url
        try:
            incoming = fetch_rss_feed(feed_url)
            jobs, stats = storage.merge_feed_jobs(jobs, incoming)
            sources_report.append({
                "name": host,
                "kind": "rss",
                "ok": True,
                "added": stats["added"],
                "checked": stats["checked"],
                "error": None,
            })
        except Exception as exc:  # noqa: BLE001 — одна лента не должна ломать всё
            sources_report.append({
                "name": host,
                "kind": "rss",
                "ok": False,
                "added": 0,
                "checked": 0,
                "error": str(exc)[:200],
            })
            print(f"[sources] Ошибка ленты {feed_url}: {exc}", file=sys.stderr)

    return jobs, {
        "mode": mode,
        "last_attempt": storage.now_iso(),
        "sources": sources_report,
        "total_jobs": len(jobs),
    }
