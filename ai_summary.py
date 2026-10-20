"""
Опциональная AI-интеграция: текстовое резюме дайджеста.

Важно: аналитика в блоке «Дайджест» (навыки, направления, зарплаты)
считается локально и не зависит от этого модуля. Здесь — только
дополнительный текстовый пересказ, для которого нужен внешний API-ключ.

Настройка (подробнее в README):
  1. Скопируйте .env.example в .env.
  2. Заполните AI_API_KEY и AI_API_URL (любой OpenAI-совместимый API).
  3. Перезапустите приложение — кнопка появится в блоке дайджеста.

Ключи хранятся только в переменных окружения, в коде их нет.
"""

import json
import os
import urllib.error
import urllib.request

REQUEST_TIMEOUT = 45  # секунд на ответ модели


def ai_status():
    """Показывает, настроен ли AI-сервис (ключ и адрес обязательно оба)."""
    api_key = os.getenv("AI_API_KEY", "").strip()
    api_url = os.getenv("AI_API_URL", "").strip()
    model = os.getenv("AI_MODEL", "").strip() or "gpt-4o-mini"

    configured = bool(api_key and api_url)
    return {
        "configured": configured,
        "model": model if configured else None,
        "hint": (
            "AI-резюме настроено, можно запрашивать."
            if configured else
            "Текстовое AI-резюме не настроено. Вся аналитика выше рассчитана "
            "локально — без нейросети. Чтобы включить резюме, задайте "
            "AI_API_KEY и AI_API_URL в файле .env (см. README) и перезапустите "
            "приложение."
        ),
    }


def _build_prompt(digest):
    """Собирает короткий запрос для модели из данных дайджеста.

    Модель отвечает по нашим данным — она не выдумывает вакансии,
    а пересказывает то, что уже посчитано локально.
    """
    skills = ", ".join(item["name"] for item in digest["top_skills"][:8]) or "нет данных"
    job_titles = "\n".join(
        f"- {item['title']} ({item['company']})" for item in digest["interesting"]
    ) or "нет данных"

    return (
        "Ты — аналитик рынка AI-вакансий. Ниже — данные локального агрегатора "
        "за последние {days} дн. Кратко (не больше 5 предложений) опиши, что "
        "нового в вакансиях, какие навыки чаще всего требуются и что стоит "
        "изучить кандидату. Не выдумывай факты, которых нет в данных.\n\n"
        f"Новых вакансий: {digest['new_count']} из {digest['total_jobs']} в базе.\n"
        f"Частые навыки: {skills}.\n"
        f"Примеры вакансий:\n{job_titles}"
    ).format(days=digest["days"])


def generate_summary(digest):
    """Запрашивает текстовое резюме у внешнего AI-сервиса.

    Возвращает {"ok": True, "text": ...} или {"ok": False, "error": ...}.
    Ошибки (нет ключа, таймаут, недоступный сервис) не роняют приложение —
    они превращаются в понятное сообщение для интерфейса.
    """
    status = ai_status()
    if not status["configured"]:
        return {"ok": False, "configured": False, "error": status["hint"]}

    api_url = os.getenv("AI_API_URL", "").strip()
    api_key = os.getenv("AI_API_KEY", "").strip()

    payload = {
        "model": status["model"],
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": "Ты отвечаешь кратко и по-русски."},
            {"role": "user", "content": _build_prompt(digest)},
        ],
    }

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
        return {"ok": True, "configured": True, "text": text, "model": status["model"]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "configured": True,
                "error": f"Сервис ответил ошибкой {exc.code}. Проверьте AI_API_URL и ключ."}
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "configured": True,
                "error": "Не удалось подключиться к AI-сервису. Проверьте адрес в .env и интернет."}
    except (KeyError, IndexError, json.JSONDecodeError, AttributeError):
        return {"ok": False, "configured": True,
                "error": "AI-сервис вернул неожиданный формат ответа. Проверьте AI_API_URL."}
