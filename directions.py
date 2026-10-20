"""
Справочники Signal: направления поиска, уровни, форматы работы, навыки.

Это «пространство имён» проекта, а не логика приложения.
Чтобы добавить новое направление поиска — допишите словарь в список
DIRECTIONS: оно сразу появится в фильтрах, дайджесте и в расчёте
соответствия вакансии критериям пользователя.
"""

# ---------------------------------------------------------------------------
# Направления поиска вакансий.
#   queries  — названия должностей (то, что ищется в заголовках вакансий);
#   keywords — слова и фразы из описаний обязанностей и требований.
# Направление вакансии определяется по тому, сколько совпадений нашлось.
# ---------------------------------------------------------------------------

DIRECTIONS = [
    {
        "id": "vibe-coding",
        "label": "Вайб-кодинг и AI-разработка",
        "short": "Вайб-кодинг",
        "color": "#8b5cf6",
        "queries": [
            "Vibe Coder",
            "Vibe Coding Engineer",
            "AI App Builder",
            "AI Prototyper",
            "AI Product Builder",
            "AI Application Developer",
            "AI Full-Stack Developer",
        ],
        "keywords": [
            "vibe coding",
            "prompt to app",
            "prompt-to-app",
            "generative ui",
            "ai prototype",
            "ai-прототип",
            "ai-приложение",
        ],
    },
    {
        "id": "prompt",
        "label": "Промпт-инжиниринг",
        "short": "Промпты",
        "color": "#22d3ee",
        "queries": [
            "Prompt Engineer",
            "Prompt Designer",
            "Prompt Architect",
            "LLM Evaluator",
            "GenAI Prompt Specialist",
        ],
        "keywords": [
            "prompt engineering",
            "промпт-инжиниринг",
            "промпт",
            "prompt patterns",
            "llm evaluation",
            "prompt tuning",
            "few-shot",
            "цепочка промптов",
        ],
    },
    {
        "id": "automation",
        "label": "AI-автоматизация",
        "short": "Автоматизация",
        "color": "#a3e635",
        "queries": [
            "AI Automation Specialist",
            "Workflow Automation",
            "No-code Specialist",
            "Low-code Specialist",
            "Automation Engineer",
            "Integration Specialist",
        ],
        "keywords": [
            "workflow automation",
            "no-code",
            "low-code",
            "автоматизация процессов",
            "n8n",
            "zapier",
            "make.com",
            "без кода",
        ],
    },
    {
        "id": "ai-content",
        "label": "AI-контент и UX",
        "short": "AI-контент",
        "color": "#f472b6",
        "queries": [
            "AI Content Designer",
            "UX Writer",
            "Conversation Designer",
            "Conversational Designer",
            "Content Designer",
        ],
        "keywords": [
            "ux writing",
            "микротекст",
            "conversation design",
            "dialogue design",
            "контент для ai",
            "tone of voice",
        ],
    },
    {
        "id": "docs",
        "label": "Техническая документация",
        "short": "Документация",
        "color": "#fbbf24",
        "queries": [
            "Technical Writer",
            "AI Documentation Specialist",
            "Documentation Engineer",
            "API Writer",
        ],
        "keywords": [
            "technical documentation",
            "docs as code",
            "developer documentation",
            "api reference",
            "техническая документация",
            "руководство пользователя",
        ],
    },
    {
        "id": "training",
        "label": "Обучение и оценка AI",
        "short": "Обучение AI",
        "color": "#34d399",
        "queries": [
            "AI Trainer",
            "AI Response Evaluator",
            "AI Data Specialist",
            "Data Annotation Specialist",
            "RLHF Trainer",
            "Model Evaluator",
        ],
        "keywords": [
            "rlhf",
            "human feedback",
            "annotation",
            "аннотац",
            "разметка данных",
            "training data",
            "оценка ответов",
        ],
    },
    {
        "id": "ai-ops",
        "label": "Смежные перспективные профессии",
        "short": "AI-операции",
        "color": "#60a5fa",
        "queries": [
            "AI Operations",
            "AI Product Specialist",
            "AI Product Manager",
            "AI Strategy",
            "Head of AI",
            "AI Solutions Architect",
        ],
        "keywords": [
            "ai operations",
            "ai adoption",
            "ai governance",
            "внедрение ai",
            "ai стратегия",
            "genai platform",
        ],
    },
]

# Значение для вакансий, которые не подошли ни под одно направление.
OTHER_DIRECTION = {
    "id": "other",
    "label": "Другое",
    "short": "Другое",
    "color": "#94a3b8",
    "queries": [],
    "keywords": [],
}

# ---------------------------------------------------------------------------
# Справочники полей вакансии. Идентификаторы (id) используются в фильтрах,
# подписи (label) — в интерфейсе.
# ---------------------------------------------------------------------------

LEVELS = [
    {"id": "Junior", "label": "Junior"},
    {"id": "Middle", "label": "Middle"},
    {"id": "Senior", "label": "Senior"},
    {"id": "Lead", "label": "Lead / Head"},
    {"id": "none", "label": "Уровень не указан"},
]

WORK_FORMATS = [
    {"id": "remote", "label": "Удалённо"},
    {"id": "hybrid", "label": "Гибрид"},
    {"id": "office", "label": "Офис"},
    {"id": "none", "label": "Формат не указан"},
]

EMPLOYMENT_TYPES = [
    {"id": "full-time", "label": "Полная занятость"},
    {"id": "part-time", "label": "Частичная занятость"},
    {"id": "contract", "label": "Контракт / фриланс"},
    {"id": "project", "label": "Проектная работа"},
    {"id": "none", "label": "Занятость не указана"},
]

# ---------------------------------------------------------------------------
# Словарь навыков. Используется, чтобы достать навыки из текста вакансии,
# полученной из внешнего источника (в демо-данных навыки заданы явно).
# aliases — как навык может быть записан «по-разному» в разных компаниях.
# ---------------------------------------------------------------------------

SKILL_VOCABULARY = [
    {"name": "Prompt engineering", "aliases": ["prompt engineering", "prompt engineer", "промпт", "prompt design"]},
    {"name": "LLM", "aliases": ["llm", "больших языковых модел", "языковых модел"]},
    {"name": "Generative AI", "aliases": ["generative ai", "genai", "генеративн"]},
    {"name": "RAG", "aliases": ["rag", "retrieval-augmented", "поисково-генеративн"]},
    {"name": "AI-агенты", "aliases": ["ai agent", "ai-агент", "agentic", "llm agent"]},
    {"name": "Python", "aliases": ["python"]},
    {"name": "JavaScript / TypeScript", "aliases": ["javascript", "typescript"]},
    {"name": "React / Next.js", "aliases": ["react", "next.js", "nextjs"]},
    {"name": "FastAPI / Flask", "aliases": ["fastapi", "flask"]},
    {"name": "OpenAI API", "aliases": ["openai", "gpt-4", "gpt-4o", "chatgpt"]},
    {"name": "Claude / Anthropic", "aliases": ["claude", "anthropic"]},
    {"name": "No-code / Low-code", "aliases": ["no-code", "low-code"]},
    {"name": "n8n", "aliases": ["n8n"]},
    {"name": "Zapier / Make", "aliases": ["zapier", "make.com", "integromat"]},
    {"name": "SQL", "aliases": ["sql"]},
    {"name": "Data analysis", "aliases": ["data analysis", "анализ данных", "аналитик данных"]},
    {"name": "Machine learning", "aliases": ["machine learning", "машинное обучение"]},
    {"name": "NLP", "aliases": ["nlp", "обработки естественного языка"]},
    {"name": "Figma", "aliases": ["figma"]},
    {"name": "UX writing", "aliases": ["ux writing", "ux writer", "микротекст"]},
    {"name": "Conversation design", "aliases": ["conversation design", "conversation designer", "диалогов"]},
    {"name": "Техническая документация", "aliases": ["technical writing", "technical writer", "docs as code", "документац"]},
    {"name": "Оценка качества AI", "aliases": ["llm evaluator", "rlhf", "human feedback", "оценка качества", "разметка данных"]},
    {"name": "Docker / CI-CD", "aliases": ["docker", "ci/cd", "контейнеризац"]},
    {"name": "Векторные базы", "aliases": ["vector database", "vector store", "векторн"]},
    {"name": "Мультимодальность", "aliases": ["multimodal", "мультимодальн"]},
    {"name": "HTML / CSS", "aliases": ["html", "css"]},
]


def get_direction(direction_id):
    """Возвращает описание направления по его идентификатору.

    Для неизвестных идентификаторов возвращается общее направление «Другое».
    """
    for direction in DIRECTIONS:
        if direction["id"] == direction_id:
            return direction
    return OTHER_DIRECTION


def detect_direction(text):
    """Определяет направление вакансии по названию и описанию.

    Название должности весит вдвое больше, чем слова из описания.
    Если совпадений нет — возвращается направление «Другое».
    """
    text_low = (text or "").casefold()
    best_direction, best_weight = None, 0

    for direction in DIRECTIONS:
        weight = 0
        for query in direction["queries"]:
            if query.casefold() in text_low:
                weight += 2
        for keyword in direction["keywords"]:
            if keyword.casefold() in text_low:
                weight += 1
        if weight > best_weight:
            best_direction, best_weight = direction, weight

    if best_direction is None:
        return OTHER_DIRECTION["id"]
    return best_direction["id"]


def extract_skills(text, limit=8):
    """Возвращает список известных навыков, упомянутых в тексте вакансии."""
    text_low = (text or "").casefold()
    found = []

    for skill in SKILL_VOCABULARY:
        if any(alias.casefold() in text_low for alias in skill["aliases"]):
            found.append(skill["name"])
        if len(found) >= limit:
            break

    return found
