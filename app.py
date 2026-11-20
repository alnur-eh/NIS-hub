from __future__ import annotations

import html
import inspect
import math
import re
from collections import Counter
from datetime import datetime

import streamlit as st

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(
    page_title="NIS HUB | NIS Turkistan",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- АВТО-СОВМЕСТИМОСТЬ С ВЕРСИЯМИ STREAMLIT ---
BTN_STRETCH = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.button).parameters
    else {"use_container_width": True}
)
DL_STRETCH = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.download_button).parameters
    else {"use_container_width": True}
)

DAYS_ORDER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEK_DAYS_UI = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ РАСПИСАНИЯ И РЕЙТИНГА ---
def extract_days(schedule: str) -> list[str]:
    return [d for d in DAYS_ORDER if re.search(rf"(?<!\w){d}(?!\w)", schedule, re.IGNORECASE)]


def parse_time_range(schedule: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})", schedule)
    if not m:
        return None
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    return (start, end)


def extract_time_label(schedule: str) -> str:
    if "•" in schedule:
        return schedule.split("•", 1)[1].strip()
    m = re.search(r"\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}", schedule)
    return m.group(0) if m else schedule


def find_schedule_conflicts(target_club: dict, enrolled_clubs: list[dict]) -> list[str]:
    target_days = set(extract_days(target_club["schedule"]))
    if not target_days:
        return []
    t_range = parse_time_range(target_club["schedule"])
    conflicts = []
    for ec in enrolled_clubs:
        if ec["id"] == target_club["id"]:
            continue
        overlap_days = [d for d in DAYS_ORDER if d in target_days and d in set(extract_days(ec["schedule"]))]
        if not overlap_days:
            continue
        e_range = parse_time_range(ec["schedule"])
        if t_range and e_range:
            if max(t_range[0], e_range[0]) < min(t_range[1], e_range[1]):
                conflicts.append(f"{', '.join(overlap_days)} (пересечение по времени) — «{ec['name']}»")
        else:
            conflicts.append(f"{', '.join(overlap_days)} — «{ec['name']}»")
    return conflicts


def compute_live_rating(club: dict) -> int:
    occupancy = club["spots_taken"] / max(club["spots_total"], 1)
    return min(100, int(round(club["rating"] * 0.7 + occupancy * 30)))


# --- ЛЁГКИЙ РЕНДЕР СВЕТЛЫХ ТАБЛИЦ И ГРАФИКОВ (БЕЗ ЧЁРНЫХ БЛОКОВ И ТОРМОЗОВ) ---
def render_light_table(headers: list[str], rows: list[list[str]]) -> str:
    th_html = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    tr_html = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row)
        tr_html.append(f"<tr>{tds}</tr>")
    return f"""
    <div class="clean-table-wrap">
        <table class="clean-table">
            <thead><tr>{th_html}</tr></thead>
            <tbody>{"".join(tr_html)}</tbody>
        </table>
    </div>
    """


def render_rating_bars(clubs: list[dict]) -> str:
    sorted_clubs = sorted(clubs, key=compute_live_rating, reverse=True)
    items_html = []
    for idx, c in enumerate(sorted_clubs, start=1):
        score = compute_live_rating(c)
        name = html.escape(c["name"])
        cat = html.escape(c["category"])
        taken = c["spots_taken"]
        total = c["spots_total"]
        items_html.append(f"""
        <div class="bar-row">
            <div class="bar-meta">
                <span class="bar-title"><b>#{idx}</b> {name} <span class="bar-cat">• {cat}</span></span>
                <span class="bar-val">{score}/100 <span class="bar-sub">({taken}/{total} уч.)</span></span>
            </div>
            <div class="bar-track">
                <div class="bar-fill" style="width: {score}%;"></div>
            </div>
        </div>
        """)
    return f"<div class='bars-card'>{''.join(items_html)}</div>"


# --- ЛЁГКИЙ NLP-ДВИЖОК (TF-IDF + COSINE SIMILARITY + СТЕММИНГ) ---
SYNONYM_EXPANSION = {
    "код": "программирование python c++ алгоритмы it разработка",
    "сайт": "программирование дизайн figma интерфейсы веб it",
    "приложен": "программирование python дизайн интерфейсы стартапы",
    "игр": "программирование c++ дизайн шахматы баскетбол",
    "деньг": "экономика финансы бизнес стартапы",
    "бизнес": "экономика финансы стартапы предпринимательство питч",
    "робот": "робототехника инженерия пайка c++ механика",
    "матем": "математика логика олимпиады геометрия комбинаторика",
    "рисов": "дизайн иллюстрация творчество арт figma",
    "музык": "домбыра кюй сцена творчество культура",
    "говор": "дебаты речь английский аргументация лидерство",
    "английск": "дебаты речь коммуникация лидерство",
    "спорт": "баскетбол выносливость турниры команда здоровье",
    "помог": "волонтерство экология социальные инициативы",
    "природ": "экология волонтерство сортировка",
    "космос": "астрофизика физика моделирование наука python",
    "шахмат": "стратегия логика турниры интеллект",
}

RU_SUFFIXES = (
    "иями", "ями", "ами", "ость", "ение", "ание", "ться", "ать", "ять", "ить",
    "еть", "овать", "ева", "ого", "его", "ому", "ему", "ыми", "ими", "ая",
    "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ов", "ев", "ам", "ям",
    "ом", "ем", "ах", "ях", "ую", "юю", "у", "ю", "а", "я", "ы", "и", "е", "о"
)

RU_STOPWORDS = {
    "для", "или", "без", "что", "чтобы", "как", "где", "при", "про", "под",
    "над", "это", "этот", "все", "всё", "мне", "меня", "свой", "свои", "свою",
    "хочу", "хотел", "можно", "было", "быть", "есть", "очень", "нужно", "надо",
    "желательно", "который", "которые", "чтоб", "если", "тоже", "уже", "еще"
}


def stem_token(word: str) -> str:
    w = word.lower().replace("ё", "е")
    if len(w) <= 3:
        return w
    for suf in RU_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w[:6] if len(w) > 6 else w


def tokenize_with_map(text: str, expand_synonyms: bool = False) -> tuple[list[str], dict[str, str]]:
    raw_words = re.findall(r"[a-zа-яё0-9+]+", text.lower().replace("ё", "е"))
    tokens = []
    stem_to_word: dict[str, str] = {}

    for w in raw_words:
        if (len(w) > 2 or w in ("ai", "it", "c++")) and w not in RU_STOPWORDS:
            st_w = stem_token(w)
            tokens.append(st_w)
            stem_to_word.setdefault(st_w, w)

    if expand_synonyms:
        joined = " ".join(raw_words)
        for key, expansion in SYNONYM_EXPANSION.items():
            if key in joined:
                for ew in expansion.split():
                    st_ew = stem_token(ew)
                    tokens.append(st_ew)
                    stem_to_word.setdefault(st_ew, ew)

    return tokens, stem_to_word


def compute_tfidf_cosine(query_text: str, clubs: list[dict]) -> dict[int, tuple[float, list[str]]]:
    query_tokens, query_stem_map = tokenize_with_map(query_text, expand_synonyms=True)
    if not query_tokens:
        return {c["id"]: (0.0, []) for c in clubs}

    raw_query_tokens, raw_query_map = tokenize_with_map(query_text, expand_synonyms=False)
    raw_query_stems = set(raw_query_tokens)

    docs_tokens = {}
    docs_stem_maps = {}
    for c in clubs:
        corpus = f"{' '.join(c['tags'])} {c['name']} {c['category']} {c['description']} {c['level']} {c['mode']}"
        d_toks, d_map = tokenize_with_map(corpus, expand_synonyms=False)
        docs_tokens[c["id"]] = d_toks
        docs_stem_maps[c["id"]] = d_map

    all_docs = list(docs_tokens.values()) + [query_tokens]
    num_docs = len(all_docs)
    df = Counter()
    for doc in all_docs:
        for term in set(doc):
            df[term] += 1

    idf = {term: math.log((num_docs + 1) / (freq + 1)) + 1.0 for term, freq in df.items()}

    def to_vec(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        total = max(len(tokens), 1)
        return {t: (cnt / total) * idf.get(t, 1.0) for t, cnt in tf.items()}

    q_vec = to_vec(query_tokens)
    q_norm = math.sqrt(sum(v * v for v in q_vec.values()))

    results = {}
    for c in clubs:
        d_tokens = docs_tokens[c["id"]]
        d_vec = to_vec(d_tokens)
        d_norm = math.sqrt(sum(v * v for v in d_vec.values()))

        if q_norm == 0 or d_norm == 0:
            sim = 0.0
        else:
            dot = sum(q_vec[t] * d_vec.get(t, 0.0) for t in q_vec)
            sim = dot / (q_norm * d_norm)

        matched_stems = sorted(list(set(query_tokens) & set(d_tokens)))
        direct_stems = [m for m in matched_stems if m in raw_query_stems]
        ordered_stems = direct_stems + [m for m in matched_stems if m not in direct_stems]

        readable_hits = []
        for m in ordered_stems:
            word = raw_query_map.get(m) or docs_stem_maps[c["id"]].get(m) or query_stem_map.get(m) or m
            if word not in readable_hits:
                readable_hits.append(word)
            if len(readable_hits) >= 4:
                break

        results[c["id"]] = (sim, readable_hits)

    return results


def build_portfolio_text(
    enrolled_clubs: list[dict],
    reg_events: list[dict],
    achievements: list[dict],
    total_events: int,
    hours: int
) -> str:
    lines = [
        "====================================================",
        "  NIS HUB — ЦИФРОВОЕ ПОРТФОЛИО УЧЕНИКА NIS TURKISTAN",
        "====================================================",
        "Ученик: Алнур Ш. (9 класс, Шанырак «Түркістан»)",
        "ID профиля: #NIS-2026-09K",
        f"Дата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        "--- СВОДКА АКТИВНОСТИ ---",
        f"• Активных клубов: {len(enrolled_clubs)}",
        f"• Мероприятий за учебный год: {total_events}",
        f"• Часов внеурочной активности за семестр: {hours} ч.",
        f"• Подтверждённых достижений: {len(achievements)}",
        "",
        "--- ТЕКУЩИЕ КРУЖКИ И СЕКЦИИ ---",
    ]
    if enrolled_clubs:
        for c in enrolled_clubs:
            lines.append(f"• {c['name']} ({c['category']}) | {c['schedule']} | Наставник: {c['mentor']}")
    else:
        lines.append("• Нет активных записей")

    lines.append("")
    lines.append("--- ЗАРЕГИСТРИРОВАННЫЕ МЕРОПРИЯТИЯ ---")
    if reg_events:
        for e in reg_events:
            lines.append(f"• {e['title']} ({e['date']}) — {e['organizer']}")
    else:
        lines.append("• Нет активных регистраций")

    lines.append("")
    lines.append("--- ПОДТВЕРЖДЁННЫЕ ДОСТИЖЕНИЯ ---")
    for a in achievements:
        lines.append(f"• [{a['Дата']}] {a['Событие / Клуб']}: {a['Результат']}")

    lines.append("")
    lines.append("Сформировано автоматически на платформе NIS HUB (NIS Turkistan).")
    return "\n".join(lines)


# --- ИНИЦИАЛИЗАЦИЯ ДАННЫХ (SESSION STATE) ---
def init_state():
    if "active_page" not in st.session_state:
        st.session_state.active_page = "home"

    if "pending_toast" not in st.session_state:
        st.session_state.pending_toast = None

    if "ai_results" not in st.session_state:
        st.session_state.ai_results = None

    if "clubs" not in st.session_state:
        st.session_state.clubs = [
            {
                "id": 1,
                "name": "NIS AI & Data Lab",
                "category": "IT и Программирование",
                "mentor": "Ахметов Б.К. (учитель информатики)",
                "schedule": "Вт, Чт • 16:30–18:00",
                "room": "Каб. 304 (IT-лаборатория)",
                "spots_total": 20,
                "spots_taken": 15,
                "rating": 98,
                "format": "Командная работа",
                "goal": "Олимпиады и проекты",
                "level": "Средний уровень",
                "mode": "Гибрид (Онлайн + Офлайн)",
                "tags": ["python", "ai", "аналитика", "программирование", "хакатоны", "данные"],
                "description": "Разработка ML-моделей, анализ данных и подготовка проектов к научным конкурсам (РНКП) и хакатонам."
            },
            {
                "id": 2,
                "name": "Robotics & Engineering (FTC / WRO)",
                "category": "Робототехника и Инженерия",
                "mentor": "Сериков Д.Н. (инженер-наставник)",
                "schedule": "Пн, Ср, Пт • 16:30–18:30",
                "room": "Мастерская робототехники",
                "spots_total": 16,
                "spots_taken": 14,
                "rating": 96,
                "format": "Командная работа",
                "goal": "Олимпиады и проекты",
                "level": "Для новичков (без опыта)",
                "mode": "Офлайн",
                "tags": ["роботы", "инженерия", "c++", "пайка", "соревнования", "механика"],
                "description": "Сборка и программирование автономных роботов для соревнований. Есть вводный трек для новичков."
            },
            {
                "id": 3,
                "name": "Олимпиадный математический клуб «Эйлер»",
                "category": "Наука и Олимпиады",
                "mentor": "Нурланова А.С. (учитель математики)",
                "schedule": "Пн, Пт • 16:00–17:30",
                "room": "Каб. 212",
                "spots_total": 25,
                "spots_taken": 19,
                "rating": 95,
                "format": "Индивидуально и в парах",
                "goal": "Олимпиады и проекты",
                "level": "Продвинутый уровень",
                "mode": "Гибрид (Онлайн + Офлайн)",
                "tags": ["математика", "логика", "комбинаторика", "геометрия", "олимпиады"],
                "description": "Разбор нестандартных олимпиадных задач по планиметрии, теории чисел и комбинаторике."
            },
            {
                "id": 4,
                "name": "NIS Startup & Economics Incubator",
                "category": "Предпринимательство",
                "mentor": "Ким Е.В. (учитель экономики)",
                "schedule": "Ср • 16:30–18:00",
                "room": "Коворкинг-зона",
                "spots_total": 22,
                "spots_taken": 12,
                "rating": 91,
                "format": "Командная работа",
                "goal": "Карьера и навыки",
                "level": "Для новичков (без опыта)",
                "mode": "Гибрид (Онлайн + Офлайн)",
                "tags": ["бизнес", "экономика", "стартапы", "финансы", "питч", "маркетинг"],
                "description": "От идеи до MVP: финансовое моделирование, исследование рынка и защита школьных стартапов с нуля."
            },
            {
                "id": 5,
                "name": "Дебатный клуб «Тұран» (KZ / RU / EN)",
                "category": "Лидерство и Дебаты",
                "mentor": "Омарова Г.Т. (педагог-организатор)",
                "schedule": "Чт • 16:30–18:00",
                "room": "Актовый малый зал",
                "spots_total": 30,
                "spots_taken": 23,
                "rating": 93,
                "format": "Командная работа",
                "goal": "Коммуникация и лидерство",
                "level": "Для новичков (без опыта)",
                "mode": "Офлайн",
                "tags": ["дебаты", "речь", "английский", "аргументация", "лидерство"],
                "description": "Британский парламентский формат, критическое мышление и уверенные выступления на трёх языках."
            },
            {
                "id": 6,
                "name": "Баскетбольная секция NIS Turkistan",
                "category": "Спорт",
                "mentor": "Жумабаев Р.А. (тренер физкультуры)",
                "schedule": "Пн, Чт • 17:00–18:30",
                "room": "Большой спортзал",
                "spots_total": 24,
                "spots_taken": 20,
                "rating": 94,
                "format": "Командная работа",
                "goal": "Здоровье и хобби",
                "level": "Средний уровень",
                "mode": "Офлайн",
                "tags": ["баскетбол", "спорт", "команда", "выносливость", "турниры"],
                "description": "Тактическая и физическая подготовка сборной школы к спартакиадам НИШ."
            },
            {
                "id": 7,
                "name": "Домбыра & Этно-ансамбль «Мұра»",
                "category": "Музыка и Искусство",
                "mentor": "Сейтжанов М.К. (руководитель студии)",
                "schedule": "Вт, Сб • 15:00–16:20",
                "room": "Музыкальная студия",
                "spots_total": 18,
                "spots_taken": 11,
                "rating": 92,
                "format": "Командная работа",
                "goal": "Здоровье и хобби",
                "level": "Для новичков (без опыта)",
                "mode": "Офлайн",
                "tags": ["музыка", "домбыра", "творчество", "сцена", "культура"],
                "description": "Обучение с нуля, исполнение классических кюев и современных аранжировок для школьных концертов."
            },
            {
                "id": 8,
                "name": "Эко-волонтёрский штаб «Green Turkistan»",
                "category": "Волонтёрство",
                "mentor": "Байтурсынова Л.М. (учитель биологии)",
                "schedule": "Сб • 11:00–13:00",
                "room": "Каб. 115",
                "spots_total": 35,
                "spots_taken": 21,
                "rating": 89,
                "format": "Командная работа",
                "goal": "Коммуникация и лидерство",
                "level": "Для новичков (без опыта)",
                "mode": "Офлайн",
                "tags": ["волонтёрство", "экология", "социальные проекты", "помощь"],
                "description": "Эко-акции, сортировка отходов в школе, благотворительные ярмарки и социальные инициативы."
            },
            {
                "id": 9,
                "name": "Цифровая иллюстрация и UX/UI дизайн",
                "category": "Музыка и Искусство",
                "mentor": "Алиева Д.Р. (учитель искусства)",
                "schedule": "Ср, Пт • 16:00–17:30",
                "room": "Арт-студия 208 / Онлайн",
                "spots_total": 16,
                "spots_taken": 13,
                "rating": 90,
                "format": "Индивидуально и в парах",
                "goal": "Карьера и навыки",
                "level": "Для новичков (без опыта)",
                "mode": "Онлайн",
                "tags": ["дизайн", "figma", "рисование", "интерфейсы", "творчество"],
                "description": "Проектирование интерфейсов в Figma, графический дизайн и визуальное оформление школьных медиа."
            },
            {
                "id": 10,
                "name": "Шахматный клуб «Стратегия»",
                "category": "Спорт",
                "mentor": "Искаков Т.Б. (педагог доп. образования)",
                "schedule": "Пн, Ср • 16:00–17:30",
                "room": "Библиотека (зона тихих игр)",
                "spots_total": 20,
                "spots_taken": 14,
                "rating": 91,
                "format": "Индивидуально и в парах",
                "goal": "Олимпиады и проекты",
                "level": "Для новичков (без опыта)",
                "mode": "Гибрид (Онлайн + Офлайн)",
                "tags": ["шахматы", "стратегия", "логика", "турниры"],
                "description": "Анализ дебютов и миттельшпиля, подготовка к командным и личным турнирам."
            }
        ]

    if "enrolled_ids" not in st.session_state:
        st.session_state.enrolled_ids = [1, 3]

    if "pending_clubs" not in st.session_state:
        st.session_state.pending_clubs = [
            {
                "temp_id": 101,
                "name": "Астрофизика и космическое моделирование",
                "category": "Наука и Олимпиады",
                "author": "Ученик 9 класса (ID #4092)",
                "mentor": "Садыков Е.М. (учитель физики — предварительно согласен)",
                "schedule": "Сб • 14:00–15:30",
                "format": "Командная работа",
                "goal": "Олимпиады и проекты",
                "level": "Для новичков (без опыта)",
                "mode": "Гибрид (Онлайн + Офлайн)",
                "tags": ["космос", "физика", "python", "моделирование", "наука"],
                "description": "Симуляция орбитальной механики на Python и подготовка проектов по астрофизике.",
                "submitted_at": "Сегодня, 09:40"
            }
        ]

    if "events" not in st.session_state:
        st.session_state.events = [
            {
                "id": 1,
                "title": "Хакатон «NIS TURKISTAN — 5 YEARS»",
                "date": "22 ноября • 10:00",
                "organizer": "NIS AI & Data Lab",
                "spots_left": 2,
                "registered": True
            },
            {
                "id": 2,
                "title": "Межшкольный турнир по дебатам Turkistan Cup",
                "date": "28 ноября • 14:30",
                "organizer": "Дебатный клуб «Тұран»",
                "spots_left": 6,
                "registered": False
            },
            {
                "id": 3,
                "title": "Питч-сессия школьных стартапов Demo Day",
                "date": "5 декабря • 16:00",
                "organizer": "NIS Startup Incubator",
                "spots_left": 12,
                "registered": False
            },
            {
                "id": 4,
                "title": "Эко-сбор и благотворительная ярмарка",
                "date": "12 декабря • 11:00",
                "organizer": "Green Turkistan",
                "spots_left": None,
                "registered": False
            }
        ]

    if "community_posts" not in st.session_state:
        st.session_state.community_posts = [
            {
                "id": 1,
                "post_type": "Поиск команды",
                "role": "Ученик 9 класса • Шанырак «Алаш»",
                "need": "Ищу фронтенд-разработчика и дизайнера в команду для школьного хакатона",
                "skills": ["Python", "Аналитика", "Математика"],
                "responded": False,
                "reply_text": "",
                "is_mine": False
            },
            {
                "id": 2,
                "post_type": "Поиск команды",
                "role": "Ученица 10 класса • Шанырак «Бәйтерек»",
                "need": "Собираю команду на региональный турнир по дебатам (английская лига)",
                "skills": ["English C1", "Публичные выступления"],
                "responded": False,
                "reply_text": "",
                "is_mine": False
            },
            {
                "id": 3,
                "post_type": "Учитель-наставник",
                "role": "Учитель физики • Садыков Е.М.",
                "need": "Готов стать научным руководителем для 2 проектов по физике и астрономии",
                "skills": ["Наставничество", "РНКП", "Физика"],
                "responded": False,
                "reply_text": "",
                "is_mine": False
            }
        ]

    if "notifications" not in st.session_state:
        st.session_state.notifications = [
            "Занятие «NIS AI & Data Lab» перенесено из каб. 302 в каб. 304 (IT-лаборатория).",
            "Открыта регистрация на «Питч-сессию школьных стартапов Demo Day» (5 декабря).",
            "Доступен новый AI-подбор с анализом текстовых целей ученика!"
        ]


init_state()


def go_to(page_key: str):
    st.session_state.active_page = page_key
    st.rerun()


# --- ОТЛОЖЕННОЕ ОТОБРАЖЕНИЕ TOAST ---
if st.session_state.pending_toast:
    toast_msg, toast_icon = st.session_state.pending_toast
    st.toast(toast_msg, icon=toast_icon)
    st.session_state.pending_toast = None

# --- ДИНАМИЧЕСКИЙ РАСЧЁТ ПОКАЗАТЕЛЕЙ ---
enrolled_clubs = [c for c in st.session_state.clubs if c["id"] in st.session_state.enrolled_ids]
registered_events = [e for e in st.session_state.events if e["registered"]]
active_events_count = 4 + len(registered_events)
semester_hours = 20 + len(st.session_state.enrolled_ids) * 4 + len(registered_events) * 2

ACHIEVEMENTS_DATA = [
    {"Дата": "Ноябрь 2026", "Событие / Клуб": "КБО по математике", "Результат": "Участник 2-х туров (олимпиадное направление)"},
    {"Дата": "Октябрь 2026", "Событие / Клуб": "Цифровой проект «Тайқазан»", "Результат": "Разработка интерактивного веб-музея"},
    {"Дата": "Сентябрь 2026", "Событие / Клуб": "Школьный отбор по экономике", "Результат": "1 место в школьном этапе"},
    {"Дата": "Август 2026", "Событие / Клуб": "SASMO Mathematics Olympiad", "Результат": "Золотая медаль"}
]

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.subheader("👤 Профиль ученика")
    st.markdown("**Алнур Ш.** • 9 класс (Шанырак «Түркістан»)")
    st.caption("ID: #NIS-2026-09K • Личные контакты скрыты")

    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Мои клубы", len(st.session_state.enrolled_ids))
    col_s2.metric("Часов", semester_hours)

    st.divider()
    st.subheader("🔔 Уведомления")
    for note in st.session_state.notifications[:4]:
        st.info(note)

    st.divider()
    st.caption("NIS Turkistan • 5 Years Hackathon")
    if st.button("🔄 Сбросить демо", help="Вернуть исходное состояние", **BTN_STRETCH):
        st.session_state.clear()
        st.rerun()

# --- СОВРЕМЕННЫЙ СВЕТЛЫЙ SAAS-ДИЗАЙН (БЫСТРЫЙ, БЕЗ ВНЕШНИХ ШРИФТОВ И ЧЁРНЫХ ЭЛЕМЕНТОВ) ---
st.markdown("""
<style>
    :root {
        color-scheme: light !important;
    }

    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif !important;
        color: #0F172A;
    }

    /* Светлый фон с мягким синим свечением справа */
    .stApp {
        background: radial-gradient(circle at 82% 25%, rgba(219, 234, 254, 0.78) 0%, rgba(248, 250, 252, 0.92) 45%, #ffffff 100%) !important;
        color: #0F172A !important;
    }
    [data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }

    /* Принудительно светлые поля ввода и селекты даже при тёмной теме macOS */
    input, textarea, [data-baseweb="input"] > div, [data-baseweb="textarea"] > div, [data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border-color: #CBD5E1 !important;
        border-radius: 10px !important;
    }
    label, .stRadio label, .stCheckbox label, .stMarkdown p, .stMarkdown li, [data-testid="stCaptionContainer"] {
        color: #1E293B !important;
    }
    [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 14px !important;
    }

    .block-container {
        padding-top: 1.3rem !important;
        padding-bottom: 3rem !important;
        max-width: 1240px !important;
    }
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Кнопки */
    div.stButton > button, div.stDownloadButton > button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.15s ease !important;
    }
    div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563EB 0%, #3B82F6 100%) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 6px 18px rgba(37, 99, 235, 0.24) !important;
    }
    div.stButton > button[kind="primary"]:hover, div.stDownloadButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%) !important;
        transform: translateY(-1px) !important;
    }
    div.stButton > button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #1E293B !important;
        border: 1px solid #E2E8F0 !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: #93C5FD !important;
        color: #2563EB !important;
        background-color: #F8FAFC !important;
    }

    /* Карточки */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: rgba(255, 255, 255, 0.95) !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 18px !important;
        box-shadow: 0 6px 22px rgba(15, 23, 42, 0.04) !important;
        padding: 0.35rem !important;
    }

    /* Логотип */
    .brand-box {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 2px 0;
    }
    .brand-icon {
        width: 38px;
        height: 38px;
        border-radius: 11px;
        background: #EFF6FF;
        border: 1px solid #DBEAFE;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
    }
    .brand-title {
        font-weight: 800;
        font-size: 1.15rem;
        line-height: 1.05;
        color: #0F172A;
    }
    .brand-title span { color: #2563EB; }
    .brand-sub {
        font-size: 0.64rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        color: #64748B;
        margin-top: 2px;
    }

    /* Hero */
    .hero-pill {
        display: inline-block;
        background: #EFF6FF;
        color: #2563EB;
        border: 1px solid #DBEAFE;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        padding: 0.4rem 0.9rem;
        border-radius: 999px;
        margin-bottom: 1.1rem;
    }
    .hero-h1 {
        font-size: clamp(2.35rem, 4.3vw, 3.6rem);
        font-weight: 800;
        line-height: 1.08;
        letter-spacing: -0.03em;
        color: #0F172A;
        margin: 0 0 1.1rem 0;
    }
    .hero-h1 .accent {
        background: linear-gradient(135deg, #2563EB 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-desc {
        font-size: 1.04rem;
        line-height: 1.62;
        color: #475569;
        max-width: 540px;
        margin-bottom: 1.5rem;
    }
    .hero-stats {
        display: flex;
        gap: 2.8rem;
        margin-top: 2rem;
        padding-top: 1.1rem;
        border-top: 1px solid #E2E8F0;
        max-width: 480px;
    }
    .stat-num { font-size: 1.75rem; font-weight: 800; color: #0F172A; line-height: 1.1; }
    .stat-label { font-size: 0.78rem; color: #64748B; margin-top: 4px; }

    .hero-visual-wrap {
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 2rem 1rem 2.3rem 1rem;
    }
    .hero-blue-card {
        width: 340px;
        min-height: 390px;
        border-radius: 28px;
        background: linear-gradient(145deg, #3B82F6 0%, #2563EB 52%, #1D4ED8 100%);
        color: #ffffff;
        padding: 2.1rem 2rem;
        box-shadow: 0 28px 60px rgba(37, 99, 235, 0.30);
        transform: rotate(-2.5deg);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .card-kicker { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; opacity: 0.85; }
    .card-rocket { font-size: 2.7rem; margin: 1rem 0 0.6rem 0; }
    .card-headline { font-size: 2.1rem; font-weight: 800; line-height: 1.08; margin: 0 0 0.7rem 0; }
    .card-sub { font-size: 0.92rem; opacity: 0.9; margin-bottom: 1.5rem; }
    .glass-pills { display: flex; gap: 0.45rem; flex-wrap: wrap; }
    .glass-pill {
        background: rgba(255, 255, 255, 0.18);
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 0.32rem 0.75rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
        color: #ffffff;
    }
    .float-badge {
        position: absolute;
        background: #ffffff;
        color: #0F172A;
        font-size: 0.85rem;
        font-weight: 700;
        padding: 0.65rem 1.1rem;
        border-radius: 14px;
        box-shadow: 0 14px 28px rgba(15, 23, 42, 0.12);
        border: 1px solid #F1F5F9;
        z-index: 5;
    }
    .float-top-right { top: 50px; right: 12px; }
    .float-bottom-left { bottom: 58px; left: 10px; }

    /* Бейджи */
    .badge {
        display: inline-block;
        padding: 0.24rem 0.7rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: #EFF6FF;
        color: #1D4ED8;
        margin-right: 0.35rem;
        margin-bottom: 0.35rem;
    }
    .badge-level { background-color: #F1F5F9; color: #334155; }
    .badge-mode { background-color: #ECFDF5; color: #047857; }
    .badge-mine { background-color: #DBEAFE; color: #1E40AF; }

    .privacy-note {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #2563EB;
        padding: 0.85rem 1.1rem;
        border-radius: 12px;
        font-size: 0.9rem;
        color: #334155;
        margin-bottom: 1.2rem;
    }
    .page-title { font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; color: #0F172A; margin-bottom: 0.25rem; }
    .page-sub { color: #64748B; font-size: 0.95rem; margin-bottom: 1.35rem; }

    /* Светлые HTML-таблицы (вместо чёрных st.dataframe) */
    .clean-table-wrap {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
        margin-bottom: 1.4rem;
    }
    .clean-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.92rem;
        color: #0F172A;
    }
    .clean-table thead th {
        background: #F8FAFC;
        color: #475569;
        font-weight: 700;
        text-align: left;
        padding: 0.85rem 1.1rem;
        border-bottom: 1px solid #E2E8F0;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .clean-table tbody td {
        padding: 0.85rem 1.1rem;
        border-bottom: 1px solid #F1F5F9;
        color: #1E293B;
    }
    .clean-table tbody tr:last-child td { border-bottom: none; }
    .clean-table tbody tr:hover td { background-color: #F8FAFC; }

    /* Светлый график рейтинга клубов (вместо чёрного st.bar_chart) */
    .bars-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 1.3rem 1.5rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    }
    .bar-row { margin-bottom: 0.95rem; }
    .bar-row:last-child { margin-bottom: 0; }
    .bar-meta {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin-bottom: 0.32rem;
        font-size: 0.9rem;
        color: #0F172A;
    }
    .bar-cat { color: #64748B; font-size: 0.82rem; font-weight: 500; }
    .bar-val { font-weight: 700; color: #2563EB; }
    .bar-sub { color: #64748B; font-weight: 500; font-size: 0.8rem; }
    .bar-track {
        width: 100%;
        height: 11px;
        background: #EFF6FF;
        border-radius: 999px;
        overflow: hidden;
    }
    .bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%);
        border-radius: 999px;
    }

    /* Метрики с переносом строк */
    [data-testid="stMetricValue"] {
        font-size: 1.65rem !important;
        line-height: 1.2 !important;
        color: #0F172A !important;
    }
    [data-testid="stMetricValue"] > div {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
    }
</style>
""", unsafe_allow_html=True)

# --- ВЕРХНЯЯ ПАНЕЛЬ НАВИГАЦИИ ---
nav_cols = st.columns([2.1, 0.95, 0.95, 1.1, 1.05, 1.25, 1.0, 1.15, 0.95])
with nav_cols[0]:
    st.markdown("""
    <div class="brand-box">
        <div class="brand-icon">🎓</div>
        <div>
            <div class="brand-title">NIS <span>HUB</span></div>
            <div class="brand-sub">TURKISTAN</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

NAV_ITEMS = [
    ("home", "Главная"),
    ("clubs", "Кружки"),
    ("ai", "AI-подбор"),
    ("events", "События"),
    ("community", "Сообщество"),
    ("create", "+ Клуб"),
    ("portfolio", "Портфолио"),
    ("admin", "Админ"),
]

for idx, (page_key, label) in enumerate(NAV_ITEMS, start=1):
    with nav_cols[idx]:
        btn_type = "primary" if st.session_state.active_page == page_key else "secondary"
        if st.button(label, key=f"nav_{page_key}", type=btn_type, **BTN_STRETCH):
            go_to(page_key)

st.markdown("<hr style='margin: 0.7rem 0 1.5rem 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)


# ==========================================
# СТРАНИЦА 0: ГЛАВНАЯ
# ==========================================
if st.session_state.active_page == "home":
    hero_left, hero_right = st.columns([1.25, 1.0], gap="large")

    with hero_left:
        st.markdown("""
        <div style="padding-top: 1rem;">
            <div class="hero-pill">ТВОИ ВОЗМОЖНОСТИ НАЧИНАЮТСЯ ЗДЕСЬ</div>
            <h1 class="hero-h1">
                Открой свой талант.<br>
                <span class="accent">Создай своё<br>будущее.</span>
            </h1>
            <p class="hero-desc">
                <b>NIS HUB</b> — единое цифровое пространство NIS Turkistan для кружков,
                талантов, ученических инициатив, наставников и новых знакомств.
                Найди своё увлечение и стань частью школьного сообщества!
            </p>
        </div>
        """, unsafe_allow_html=True)

        cta1, cta2, _ = st.columns([1.35, 1.15, 0.8])
        with cta1:
            if st.button("Найти свой кружок →", key="hero_go_clubs", type="primary", **BTN_STRETCH):
                go_to("clubs")
        with cta2:
            if st.button("✨ AI-помощник", key="hero_go_ai", type="secondary", **BTN_STRETCH):
                go_to("ai")

        st.markdown(f"""
        <div class="hero-stats">
            <div>
                <div class="stat-num">{len(st.session_state.clubs)}+</div>
                <div class="stat-label">Кружков и секций</div>
            </div>
            <div>
                <div class="stat-num">7</div>
                <div class="stat-label">Модулей платформы</div>
            </div>
            <div>
                <div class="stat-num">∞</div>
                <div class="stat-label">Возможностей</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with hero_right:
        st.markdown("""
        <div class="hero-visual-wrap">
            <div class="float-badge float-top-right">👥 Найди команду</div>
            <div class="hero-blue-card">
                <div class="card-kicker">YOUR POTENTIAL</div>
                <div>
                    <div class="card-rocket">🚀</div>
                    <div class="card-headline">Dream big.<br>Start here.</div>
                    <div class="card-sub">Твоя идея может изменить мир.</div>
                </div>
                <div class="glass-pills">
                    <span class="glass-pill">Technology</span>
                    <span class="glass-pill">Science</span>
                    <span class="glass-pill">Creativity</span>
                </div>
            </div>
            <div class="float-badge float-bottom-left">💡 Создай идею</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.6rem;'></div>", unsafe_allow_html=True)
    st.markdown("### 🔥 Популярные направления NIS Turkistan")
    top_clubs = sorted(st.session_state.clubs, key=compute_live_rating, reverse=True)[:3]
    p_cols = st.columns(3)
    for col, c in zip(p_cols, top_clubs):
        with col:
            with st.container(border=True):
                st.markdown(
                    f"<span class='badge'>{html.escape(c['category'])}</span>"
                    f"<span class='badge badge-mode'>{html.escape(c['mode'])}</span>",
                    unsafe_allow_html=True
                )
                st.markdown(f"#### {c['name']}")
                st.caption(c["description"])
                st.markdown(f"🗓️ **{c['schedule']}** • Индекс: **{compute_live_rating(c)}/100**")
                if st.button("Перейти в каталог →", key=f"home_c_{c['id']}", **BTN_STRETCH):
                    go_to("clubs")


# ==========================================
# СТРАНИЦА 1: КАТАЛОГ КРУЖКОВ
# ==========================================
elif st.session_state.active_page == "clubs":
    st.markdown("<div class='page-title'>📚 Каталог кружков и секций</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Выбирайте направления по интересам, уровню подготовки и формату (Онлайн / Офлайн / Гибрид) — система сама проверит накладки расписания.</div>", unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1.3, 1.3, 1.3])
    with col_f1:
        search_query = st.text_input("🔍 Поиск по названию или навыку", placeholder="Например: Python, баскетбол, дебаты...")
    with col_f2:
        categories = ["Все направления"] + sorted(list({c["category"] for c in st.session_state.clubs}))
        selected_cat = st.selectbox("Направление", categories)
    with col_f3:
        levels = ["Любой уровень", "Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"]
        selected_level = st.selectbox("Уровень подготовки", levels)
    with col_f4:
        mode_options = ["Любой формат", "Офлайн", "Гибрид (Онлайн + Офлайн)", "Онлайн"]
        selected_mode = st.selectbox("Формат занятий", mode_options)

    only_available = st.checkbox("Показать только клубы со свободными местами", value=False)

    filtered_clubs = []
    for club in st.session_state.clubs:
        if selected_cat != "Все направления" and club["category"] != selected_cat:
            continue
        if selected_level != "Любой уровень" and club["level"] != selected_level:
            continue
        if selected_mode != "Любой формат" and club["mode"] != selected_mode:
            continue
        if only_available and club["spots_taken"] >= club["spots_total"]:
            continue
        if search_query:
            q = search_query.lower()
            if not (
                q in club["name"].lower()
                or q in club["description"].lower()
                or any(q in t.lower() for t in club["tags"])
            ):
                continue
        filtered_clubs.append(club)

    st.caption(f"Найдено кружков и секций: **{len(filtered_clubs)}**")

    cols = st.columns(2)
    for idx, club in enumerate(filtered_clubs):
        with cols[idx % 2]:
            with st.container(border=True):
                free_spots = club["spots_total"] - club["spots_taken"]
                live_rating = compute_live_rating(club)
                st.markdown(
                    f"<span class='badge'>{html.escape(club['category'])}</span>"
                    f"<span class='badge badge-level'>{html.escape(club['level'])}</span>"
                    f"<span class='badge badge-mode'>{html.escape(club['mode'])}</span>",
                    unsafe_allow_html=True
                )
                st.markdown(f"### {club['name']}")
                st.write(club["description"])
                st.markdown(
                    f"**Наставник:** {club['mentor']}  \n"
                    f"**Расписание:** {club['schedule']} • {club['room']}  \n"
                    f"**Индекс активности клуба:** {live_rating}/100"
                )

                is_enrolled = club["id"] in st.session_state.enrolled_ids
                if not is_enrolled:
                    conflicts = find_schedule_conflicts(club, enrolled_clubs)
                    if conflicts:
                        st.warning(f"⚠️ Накладка расписания: {'; '.join(conflicts)}")

                progress_val = min(club["spots_taken"] / club["spots_total"], 1.0)
                st.progress(progress_val, text=f"Заполнено мест: {club['spots_taken']} из {club['spots_total']} (свободно: {free_spots})")

                if is_enrolled:
                    if st.button("✅ Вы записаны (Отменить запись)", key=f"leave_{club['id']}", **BTN_STRETCH):
                        st.session_state.enrolled_ids.remove(club["id"])
                        club["spots_taken"] = max(0, club["spots_taken"] - 1)
                        st.session_state.pending_toast = (f"Запись в «{club['name']}» отменена.", "ℹ️")
                        st.rerun()
                else:
                    if free_spots > 0:
                        if st.button("📝 Записаться в один клик", key=f"join_{club['id']}", type="primary", **BTN_STRETCH):
                            st.session_state.enrolled_ids.append(club["id"])
                            club["spots_taken"] += 1
                            st.session_state.pending_toast = (f"Вы успешно записались в «{club['name']}»!", "🎉")
                            st.rerun()
                    else:
                        st.button("Мест нет", key=f"full_{club['id']}", disabled=True, **BTN_STRETCH)


# ==========================================
# СТРАНИЦА 2: AI-ПОДБОР (FIND YOUR PASSION)
# ==========================================
elif st.session_state.active_page == "ai":
    st.markdown("<div class='page-title'>✨ AI-навигатор «Find Your Passion»</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Опишите своими словами, чем вам хочется заниматься — гибридная NLP-модель (TF-IDF + косинусное сходство) подберёт топ-3 кружка с объяснением.</div>", unsafe_allow_html=True)

    with st.expander("⚙️ Архитектура AI-модуля (для экспертного жюри)"):
        st.markdown("""
        * **NLP-анализ текста:** фильтрация стоп-слов + морфологический стемминг + словарь синонимов + построение векторов **TF-IDF** и расчёт **Cosine Similarity**.
        * **Гибридный скоринг:** итоговый `AI Match Score` объединяет смысловую близость текста (до 45%) и параметры ученика — цель, уровень, онлайн/офлайн формат и расписание (до 55%).
        * **Приватность:** работает локально без передачи персональных данных учеников во внешние облачные LLM.
        """)

    with st.form("ai_recommender_form"):
        user_prompt = st.text_area(
            "✍️ Опишите своими словами, что вам нравится или какую цель ставите:",
            placeholder="Например: Хочу научиться делать сайты или свой стартап с нуля, без опыта, желательно онлайн..."
        )

        col_ai1, col_ai2 = st.columns(2)
        with col_ai1:
            selected_interests = st.multiselect(
                "Дополнительные теги интересов (опционально):",
                ["Программирование и AI", "Математика и логика", "Роботы и инженерия", "Бизнес и экономика", "Публичные выступления и дебаты", "Спорт и активные игры", "Музыка и дизайн", "Волонтёрство и экология"],
                default=[]
            )
            preferred_goal = st.selectbox(
                "Главная цель на этот учебный год:",
                ["Олимпиады и проекты", "Карьера и навыки", "Коммуникация и лидерство", "Здоровье и хобби"]
            )
        with col_ai2:
            preferred_level = st.selectbox(
                "Ваш текущий уровень:",
                ["Любой уровень", "Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"]
            )
            preferred_mode = st.selectbox(
                "Предпочтительный формат:",
                ["Любой формат", "Офлайн", "Гибрид (Онлайн + Офлайн)", "Онлайн"]
            )
            free_day = st.selectbox(
                "Удобный день недели:",
                ["Любой день", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
            )
        submitted_ai = st.form_submit_button("✨ Запустить AI-подбор", type="primary")

    if submitted_ai:
        interest_tag_map = {
            "Программирование и AI": ["python", "ai", "аналитика", "программирование", "хакатоны", "данные"],
            "Математика и логика": ["математика", "логика", "комбинаторика", "геометрия", "олимпиады", "шахматы"],
            "Роботы и инженерия": ["роботы", "инженерия", "c++", "пайка", "механика"],
            "Бизнес и экономика": ["бизнес", "экономика", "стартапы", "финансы", "маркетинг"],
            "Публичные выступления и дебаты": ["дебаты", "речь", "английский", "аргументация", "лидерство"],
            "Спорт и активные игры": ["баскетбол", "спорт", "выносливость", "шахматы"],
            "Музыка и дизайн": ["музыка", "домбыра", "дизайн", "figma", "творчество"],
            "Волонтёрство и экология": ["волонтёрство", "экология", "социальные проекты"]
        }

        target_tags = set()
        for item in selected_interests:
            target_tags.update(interest_tag_map.get(item, []))

        nlp_scores = compute_tfidf_cosine(user_prompt, st.session_state.clubs)
        max_sim = max((val[0] for val in nlp_scores.values()), default=0.0)

        scored_clubs = []
        for club in st.session_state.clubs:
            reasons = []
            raw_sim, matched_words = nlp_scores[club["id"]]
            nlp_pct = int(round((raw_sim / max_sim) * 100)) if max_sim > 0 else 0
            nlp_points = (raw_sim / max_sim) * 42 if max_sim > 0 else 0

            if matched_words and user_prompt.strip():
                reasons.append(f"NLP-анализ (стемминг + TF-IDF) выявил смысловое совпадение по темам: {', '.join(matched_words)}")

            profile_points = 30
            matched_tags = target_tags.intersection(set(club["tags"]))
            if matched_tags:
                profile_points += min(24, len(matched_tags) * 10)
                reasons.append(f"совпадение по интересам ({', '.join(sorted(matched_tags))})")

            if club["goal"] == preferred_goal:
                profile_points += 14
                reasons.append(f"подходит под цель «{preferred_goal}»")

            if preferred_level != "Любой уровень":
                if club["level"] == preferred_level:
                    profile_points += 12
                    reasons.append(f"подходящий уровень ({club['level'].lower()})")
                elif preferred_level == "Для новичков (без опыта)" and club["level"] == "Продвинутый уровень":
                    profile_points -= 12

            if preferred_mode != "Любой формат" and club["mode"] == preferred_mode:
                profile_points += 10
                reasons.append(f"формат «{club['mode']}»")

            if free_day != "Любой день" and free_day in extract_days(club["schedule"]):
                profile_points += 8
                reasons.append(f"удобное расписание ({free_day})")

            prompt_low = user_prompt.lower()
            if ("онлайн" in prompt_low or "удален" in prompt_low) and "Онлайн" in club["mode"]:
                profile_points += 10
                reasons.append("доступен онлайн-формат")
            if ("без опыта" in prompt_low or "нович" in prompt_low or "с нуля" in prompt_low) and "новичков" in club["level"]:
                profile_points += 10
                reasons.append("комфортный вход с нуля")

            if user_prompt.strip():
                total_score = int(round(min(99, max(35, nlp_points + profile_points * 0.62))))
            else:
                total_score = int(round(min(99, max(35, profile_points + 8))))

            scored_clubs.append((total_score, nlp_pct, club["id"], reasons))

        scored_clubs.sort(key=lambda x: x[0], reverse=True)
        st.session_state.ai_results = {
            "prompt": user_prompt.strip(),
            "items": scored_clubs[:3],
        }

    if st.session_state.ai_results:
        st.markdown("### 🎯 Топ-3 персональные рекомендации")
        clubs_by_id = {c["id"]: c for c in st.session_state.clubs}

        for rank, (score, nlp_pct, club_id, reasons) in enumerate(st.session_state.ai_results["items"], start=1):
            club = clubs_by_id.get(club_id)
            if not club:
                continue
            free_spots = club["spots_total"] - club["spots_taken"]
            with st.container(border=True):
                c1, c2 = st.columns([3.8, 1.2])
                with c1:
                    st.markdown(
                        f"<span class='badge'>{html.escape(club['category'])}</span>"
                        f"<span class='badge badge-level'>{html.escape(club['level'])}</span>"
                        f"<span class='badge badge-mode'>{html.escape(club['mode'])}</span>",
                        unsafe_allow_html=True
                    )
                    st.markdown(f"#### #{rank}. {club['name']}")
                    st.write(club["description"])
                    st.caption(f"Расписание: {club['schedule']} • {club['room']} • Свободно мест: {free_spots}")

                    if club["id"] not in st.session_state.enrolled_ids:
                        conflicts = find_schedule_conflicts(club, enrolled_clubs)
                        if conflicts:
                            st.warning(f"⚠️ Накладка расписания: {'; '.join(conflicts)}")

                    reason_text = "; ".join(reasons) if reasons else "высокий индекс вовлечённости учеников и универсальный формат"
                    st.success(f"**Объяснение AI:** {reason_text.capitalize()}.")
                with c2:
                    st.metric("AI Match Score", f"{score}%")
                    if st.session_state.ai_results["prompt"]:
                        st.caption(f"NLP-близость текста: **{nlp_pct}%**")

                    if club["id"] in st.session_state.enrolled_ids:
                        st.info("Вы уже в клубе")
                    elif free_spots > 0:
                        if st.button("Записаться", key=f"ai_join_{club['id']}", type="primary", **BTN_STRETCH):
                            st.session_state.enrolled_ids.append(club["id"])
                            club["spots_taken"] += 1
                            st.session_state.pending_toast = (f"Вы записаны в «{club['name']}»!", "✅")
                            st.rerun()
                    else:
                        st.button("Мест нет", key=f"ai_full_{club['id']}", disabled=True, **BTN_STRETCH)


# ==========================================
# СТРАНИЦА 3: СОБЫТИЯ И ЧЕЛЛЕНДЖИ
# ==========================================
elif st.session_state.active_page == "events":
    st.markdown("<div class='page-title'>📅 События и челленджи</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Регистрация автоматически обновляет остаток мест, часы внеурочной активности и личное портфолио.</div>", unsafe_allow_html=True)

    for ev in st.session_state.events:
        spots_left = ev["spots_left"]
        if spots_left is None:
            spots_text = "Без ограничений"
        elif spots_left == 0:
            spots_text = "Свободных мест нет"
        else:
            spots_text = f"Осталось мест: {spots_left}"

        with st.container(border=True):
            ec1, ec2, ec3 = st.columns([3, 2, 1.5])
            with ec1:
                st.markdown(f"**{ev['title']}**")
                st.caption(f"Организатор: {ev['organizer']}")
            with ec2:
                st.markdown(f"🗓️ {ev['date']}")
                st.caption(f"Статус мест: **{spots_text}**")
            with ec3:
                if ev["registered"]:
                    if st.button("✅ Вы участвуете (Отменить)", key=f"ev_cancel_{ev['id']}", **BTN_STRETCH):
                        ev["registered"] = False
                        if ev["spots_left"] is not None:
                            ev["spots_left"] += 1
                        st.session_state.pending_toast = (f"Регистрация на «{ev['title']}» отменена.", "ℹ️")
                        st.rerun()
                elif spots_left is None or spots_left > 0:
                    if st.button("Участвовать (+2 ч.)", key=f"ev_reg_{ev['id']}", type="primary", **BTN_STRETCH):
                        ev["registered"] = True
                        if ev["spots_left"] is not None:
                            ev["spots_left"] = max(0, ev["spots_left"] - 1)
                        st.session_state.pending_toast = (f"Регистрация на «{ev['title']}» подтверждена! (+2 ч.)", "📅")
                        st.rerun()
                else:
                    st.button("Мест нет", key=f"ev_full_{ev['id']}", disabled=True, **BTN_STRETCH)


# ==========================================
# СТРАНИЦА 4: СООБЩЕСТВО И НАСТАВНИКИ (ИНТЕРАКТИВНОЕ)
# ==========================================
elif st.session_state.active_page == "community":
    st.markdown("<div class='page-title'>🤝 Сообщество и наставники</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Находите единомышленников в команду и учителей-наставников для проектов без публикации личных контактов.</div>", unsafe_allow_html=True)

    sent_count = sum(1 for p in st.session_state.community_posts if p["responded"])
    my_posts_count = sum(1 for p in st.session_state.community_posts if p.get("is_mine"))

    cm1, cm2, cm3 = st.columns(3)
    cm1.metric("Активных запросов", len(st.session_state.community_posts))
    cm2.metric("Ваши объявления", my_posts_count)
    cm3.metric("Отправлено откликов", sent_count)

    st.markdown("""
    <div class="privacy-note">
        <b>Защита персональных данных:</b> личные номера телефонов, мессенджеры и почта учеников скрыты. Связь происходит только через безопасный внутренний отклик на платформе.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("➕ Опубликовать свой запрос на поиск команды или наставника", expanded=False):
        with st.form("new_community_post", clear_on_submit=True):
            post_type = st.selectbox("Тип запроса", ["Поиск команды", "Ищу учителя-наставника", "Идея проекта"])
            post_need = st.text_input("Кого и для чего вы ищете? *", placeholder="Например: Ищу дизайнера в команду на хакатон...")
            post_skills = st.text_input("Ваши навыки / тема (через запятую)", placeholder="Python, Аналитика, Питчинг")
            if st.form_submit_button("Опубликовать запрос", type="primary"):
                if post_need.strip():
                    st.session_state.community_posts.insert(0, {
                        "id": int(datetime.now().timestamp() * 1000),
                        "post_type": post_type,
                        "role": "Алнур Ш. • 9 класс • Шанырак «Түркістан»",
                        "need": post_need.strip(),
                        "skills": [s.strip() for s in post_skills.split(",") if s.strip()] or ["Инициатива"],
                        "responded": False,
                        "reply_text": "",
                        "is_mine": True
                    })
                    st.session_state.pending_toast = ("Ваш запрос опубликован в ленте сообщества!", "📣")
                    st.rerun()
                else:
                    st.error("Опишите, кого вы ищете.")

    comm_filter = st.radio(
        "Фильтр ленты:",
        ["Все объявления", "Поиск команды", "Учитель-наставник", "Ищу учителя-наставника", "Идея проекта"],
        horizontal=True
    )

    visible_posts = [
        p for p in st.session_state.community_posts
        if comm_filter == "Все объявления" or p["post_type"] == comm_filter
    ]

    if not visible_posts:
        st.info("В этой категории пока нет объявлений — станьте первым!")

    for post in visible_posts:
        with st.container(border=True):
            p1, p2 = st.columns([3.7, 1.5])
            with p1:
                mine_badge = "<span class='badge badge-mine'>Ваш запрос</span>" if post.get("is_mine") else ""
                st.markdown(
                    f"<span class='badge'>{html.escape(post['post_type'])}</span>{mine_badge} "
                    f"<b>{html.escape(post['role'])}</b>",
                    unsafe_allow_html=True
                )
                st.write(post["need"])
                tags_html = " ".join(
                    f"<span class='badge badge-level'>{html.escape(s)}</span>"
                    for s in post["skills"]
                )
                st.markdown(tags_html, unsafe_allow_html=True)

                if post["responded"]:
                    msg_info = f" Сообщение: «{post['reply_text']}»" if post.get("reply_text") else ""
                    st.success(f"✅ Внутренний отклик отправлен.{msg_info} Ожидайте подтверждения в чате NIS HUB.")

            with p2:
                if post.get("is_mine"):
                    if st.button("🗑️ Удалить", key=f"post_del_{post['id']}", **BTN_STRETCH):
                        st.session_state.community_posts = [
                            p for p in st.session_state.community_posts if p["id"] != post["id"]
                        ]
                        st.session_state.pending_toast = ("Ваш запрос удалён из ленты.", "🗑️")
                        st.rerun()
                elif post["responded"]:
                    if st.button("Отозвать отклик", key=f"post_undo_{post['id']}", **BTN_STRETCH):
                        post["responded"] = False
                        post["reply_text"] = ""
                        st.session_state.pending_toast = ("Отклик отозван.", "ℹ️")
                        st.rerun()
                else:
                    if st.button("🤝 Откликнуться", key=f"post_resp_{post['id']}", type="primary", **BTN_STRETCH):
                        post["responded"] = True
                        post["reply_text"] = "Готов(а) присоединиться и обсудить детали!"
                        st.session_state.notifications.insert(
                            0,
                            f"🤝 Вы откликнулись на запрос «{post['role']}». Внутренний диалог открыт."
                        )
                        st.session_state.pending_toast = ("Отклик отправлен через безопасный внутренний чат!", "🤝")
                        st.rerun()


# ==========================================
# СТРАНИЦА 5: СОЗДАТЬ СВОЙ КЛУБ
# ==========================================
elif st.session_state.active_page == "create":
    st.markdown("<div class='page-title'>💡 Создать свой клуб</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Предложите идею собственного ученического клуба — после подтверждения администрацией он появится в каталоге.</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="privacy-note">
        <b>Регламент безопасности NIS HUB:</b> каждая заявка на открытие нового клуба проверяется ответственным педагогом или администрацией перед публикацией.
    </div>
    """, unsafe_allow_html=True)

    with st.form("create_club_form", clear_on_submit=True):
        new_name = st.text_input("Название нового клуба *", placeholder="Например: Клуб спортивного программирования NIS")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            new_cat = st.selectbox("Направление *", ["IT и Программирование", "Наука и Олимпиады", "Робототехника и Инженерия", "Предпринимательство", "Лидерство и Дебаты", "Спорт", "Музыка и Искусство", "Волонтёрство"])
            new_mentor = st.text_input("Предполагаемый учитель-наставник *", placeholder="ФИО педагога")
            new_level = st.selectbox("Уровень подготовки *", ["Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"])
        with c_col2:
            new_schedule = st.text_input("Желаемое расписание *", placeholder="Например: Пт • 16:30–18:00")
            new_goal = st.selectbox("Основной фокус клуба", ["Олимпиады и проекты", "Карьера и навыки", "Коммуникация и лидерство", "Здоровье и хобби"])
            new_mode = st.selectbox("Формат занятий *", ["Офлайн", "Гибрид (Онлайн + Офлайн)", "Онлайн"])
        new_tags = st.text_input("Ключевые теги (через запятую)", placeholder="алгоритмы, c++, олимпиады, задачи")
        new_desc = st.text_area("Описание идеи, целей и формата встреч *")

        submit_club = st.form_submit_button("📤 Отправить заявку на модерацию", type="primary")
        if submit_club:
            if new_name.strip() and new_mentor.strip() and new_schedule.strip() and new_desc.strip():
                st.session_state.pending_clubs.append({
                    "temp_id": int(datetime.now().timestamp() * 1000),
                    "name": new_name.strip(),
                    "category": new_cat,
                    "author": "Алнур Ш. (9 класс)",
                    "mentor": new_mentor.strip(),
                    "schedule": new_schedule.strip(),
                    "format": "Командная работа",
                    "goal": new_goal,
                    "level": new_level,
                    "mode": new_mode,
                    "tags": [t.strip().lower() for t in new_tags.split(",") if t.strip()] or ["инициатива"],
                    "description": new_desc.strip(),
                    "submitted_at": datetime.now().strftime("%H:%M")
                })
                st.success("Заявка отправлена! Откройте раздел «Админ» в верхнем меню, чтобы увидеть её одобрение.")
            else:
                st.error("Пожалуйста, заполните все обязательные поля (*).")


# ==========================================
# СТРАНИЦА 6: МОЁ ПОРТФОЛИО И ЖИВОЙ РЕЙТИНГ (СВЕТЛЫЕ ТАБЛИЦЫ И ГРАФИК)
# ==========================================
elif st.session_state.active_page == "portfolio":
    col_head, col_dl = st.columns([3.5, 1.5])
    with col_head:
        st.markdown("<div class='page-title'>🏆 Моё портфолио и достижения</div>", unsafe_allow_html=True)
        st.markdown("<div class='page-sub'>Алнур Ш. • 9 класс • Шанырак «Түркістан» • ID #NIS-2026-09K</div>", unsafe_allow_html=True)
    with col_dl:
        st.markdown("<div style='height: 0.6rem;'></div>", unsafe_allow_html=True)
        portfolio_txt = build_portfolio_text(
            enrolled_clubs=enrolled_clubs,
            reg_events=registered_events,
            achievements=ACHIEVEMENTS_DATA,
            total_events=active_events_count,
            hours=semester_hours
        )
        st.download_button(
            label="📥 Скачать портфолио (.txt)",
            data=portfolio_txt.encode("utf-8"),
            file_name="NIS_HUB_Portfolio_Alnur.txt",
            mime="text/plain",
            type="primary",
            **DL_STRETCH
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Активных клубов", len(st.session_state.enrolled_ids), help="Текущие записи в кружки и секции")
    m2.metric("Мероприятий за год", active_events_count, help="4 завершённых + текущие регистрации")
    m3.metric("Часов за семестр", semester_hours, help="20 базовых + 4 ч. за клуб + 2 ч. за мероприятие")
    m4.metric("Достижений", len(ACHIEVEMENTS_DATA), help="Верифицированные школой результаты")

    st.markdown("#### 🗓️ Моя сетка внеурочной нагрузки (Пн–Сб)")
    week_rows = []
    for day in WEEK_DAYS_UI:
        day_clubs = [c for c in enrolled_clubs if day in extract_days(c["schedule"])]
        day_clubs.sort(key=lambda c: (parse_time_range(c["schedule"]) or (9999, 9999))[0])
        if not day_clubs:
            week_rows.append([day, "🟢 Свободное окно", "Нет запланированных занятий", "—"])
        else:
            club_lines = " | ".join(f"{extract_time_label(c['schedule'])} • {c['name']}" for c in day_clubs)
            room_lines = " | ".join(c["room"] for c in day_clubs)
            status = "🔴 Плотный день (2+)" if len(day_clubs) >= 2 else "📘 Занятие"
            week_rows.append([day, status, club_lines, room_lines])

    st.markdown(
        render_light_table(["День", "Статус", "Кружки и время", "Локация"], week_rows),
        unsafe_allow_html=True
    )

    st.markdown("#### Мои ближайшие мероприятия")
    if registered_events:
        ev_cols = st.columns(2)
        for idx, rev in enumerate(registered_events):
            with ev_cols[idx % 2]:
                st.info(f"🗓️ **{rev['title']}** — {rev['date']} ({rev['organizer']})")
    else:
        st.caption("Вы пока не зарегистрированы на предстоящие события.")

    st.markdown("#### Личные достижения (для портфолио выпускника)")
    ach_rows = [[a["Дата"], a["Событие / Клуб"], a["Результат"]] for a in ACHIEVEMENTS_DATA]
    st.markdown(
        render_light_table(["Дата", "Событие / Клуб", "Результат"], ach_rows),
        unsafe_allow_html=True
    )

    st.markdown("#### 📊 Живой рейтинг активности клубов NIS Turkistan (без публичного ранжирования учеников)")
    st.caption("Рассчитывается динамически на основе достижений клуба (70%) и текущей вовлечённости участников (30%) — обновляется сразу после записи.")
    st.markdown(render_rating_bars(st.session_state.clubs), unsafe_allow_html=True)


# ==========================================
# СТРАНИЦА 7: АДМИН-ПАНЕЛЬ И МОДЕРАЦИЯ
# ==========================================
elif st.session_state.active_page == "admin":
    st.markdown("<div class='page-title'>🛡️ Кабинет ответственного педагога / администрации</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Оперативная аналитика загруженности кружков и модерация новых ученических инициатив.</div>", unsafe_allow_html=True)

    total_taken = sum(c["spots_taken"] for c in st.session_state.clubs)
    total_spots = sum(c["spots_total"] for c in st.session_state.clubs)
    school_occupancy = round((total_taken / max(total_spots, 1)) * 100)

    cat_stats: dict[str, list[int]] = {}
    for c in st.session_state.clubs:
        pair = cat_stats.setdefault(c["category"], [0, 0])
        pair[0] += c["spots_taken"]
        pair[1] += c["spots_total"]

    top_cat, (top_taken, top_total) = max(
        cat_stats.items(),
        key=lambda item: item[1][0] / max(item[1][1], 1)
    )
    top_cat_pct = round((top_taken / max(top_total, 1)) * 100)

    near_full_clubs = [
        c for c in st.session_state.clubs
        if (c["spots_taken"] / max(c["spots_total"], 1)) >= 0.85
    ]

    adm1, adm2, adm3 = st.columns([1.0, 1.65, 1.15])
    adm1.metric(
        "Общая заполняемость по школе",
        f"{school_occupancy}%",
        help=f"Занято {total_taken} из {total_spots} доступных мест"
    )
    adm2.metric(
        "Самое востребованное направление",
        top_cat,
        delta=f"{top_cat_pct}% мест занято"
    )
    adm3.metric(
        "Клубы на грани переполнения (≥85%)",
        len(near_full_clubs),
        help="Сигнал администрации открыть вторую группу"
    )

    if near_full_clubs:
        alerts = [
            f"«{c['name']}» ({round(c['spots_taken'] / max(c['spots_total'], 1) * 100)}% — {c['spots_taken']}/{c['spots_total']})"
            for c in near_full_clubs
        ]
        st.warning(
            f"**Сигнал администрации:** высокая нагрузка в клубах {', '.join(alerts)}. "
            "Рекомендуется запланировать вторую группу или расширение квоты."
        )

    st.divider()
    st.markdown("#### 📋 Заявки на открытие новых ученических клубов")

    if not st.session_state.pending_clubs:
        st.info("Новых заявок на рассмотрении нет.")
    else:
        for idx, p_club in enumerate(st.session_state.pending_clubs):
            with st.container(border=True):
                st.markdown(
                    f"<span class='badge'>{html.escape(p_club['category'])}</span>"
                    f"<span class='badge badge-level'>{html.escape(p_club['level'])}</span>"
                    f"<span class='badge badge-mode'>{html.escape(p_club['mode'])}</span>",
                    unsafe_allow_html=True
                )
                st.markdown(f"### Заявка: {p_club['name']}")
                st.markdown(f"**Инициатор:** {p_club['author']} • **Время подачи:** {p_club['submitted_at']}")
                st.markdown(f"**Наставник:** {p_club['mentor']} • **Расписание:** {p_club['schedule']}")
                st.write(p_club["description"])

                b_col1, b_col2, _ = st.columns([1.5, 1.2, 3])
                with b_col1:
                    if st.button("✅ Одобрить и опубликовать", key=f"app_{p_club['temp_id']}", type="primary"):
                        new_id = max(c["id"] for c in st.session_state.clubs) + 1
                        st.session_state.clubs.append({
                            "id": new_id,
                            "name": p_club["name"],
                            "category": p_club["category"],
                            "mentor": p_club["mentor"],
                            "schedule": p_club["schedule"],
                            "room": "Аудитория назначается после одобрения",
                            "spots_total": 20,
                            "spots_taken": 1,
                            "rating": 85,
                            "format": p_club["format"],
                            "goal": p_club["goal"],
                            "level": p_club["level"],
                            "mode": p_club["mode"],
                            "tags": p_club["tags"],
                            "description": p_club["description"]
                        })
                        st.session_state.notifications.insert(
                            0,
                            f"🎉 Новый клуб «{p_club['name']}» одобрен администрацией и открыт для записи!"
                        )
                        st.session_state.pending_clubs.pop(idx)
                        st.session_state.pending_toast = (f"Клуб «{p_club['name']}» опубликован в каталоге!", "🚀")
                        st.rerun()
                with b_col2:
                    if st.button("❌ Отклонить", key=f"rej_{p_club['temp_id']}"):
                        declined_name = p_club["name"]
                        st.session_state.pending_clubs.pop(idx)
                        st.session_state.pending_toast = (f"Заявка «{declined_name}» отклонена.", "ℹ️")
                        st.rerun()
