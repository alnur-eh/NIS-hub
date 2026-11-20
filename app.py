from __future__ import annotations

import html
import inspect
import math
import re
from collections import Counter
from datetime import datetime

import pandas as pd
import streamlit as st

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(
    page_title="NIS HUB | NIS Turkistan",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- АВТО-СОВМЕСТИМОСТЬ С ВЕРСИЯМИ STREAMLIT (БЕЗ DEPRECATION WARNING) ---
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
DF_STRETCH = (
    {"width": "stretch"}
    if "width" in inspect.signature(st.dataframe).parameters
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
            # Проверка пересечения интервалов [start, end)
            if max(t_range[0], e_range[0]) < min(t_range[1], e_range[1]):
                conflicts.append(f"{', '.join(overlap_days)} (пересечение по времени) — «{ec['name']}»")
        else:
            conflicts.append(f"{', '.join(overlap_days)} — «{ec['name']}»")
    return conflicts


def compute_live_rating(club: dict) -> int:
    """Живой индекс активности клуба: 70% достижения + 30% текущая вовлечённость (заполняемость)."""
    occupancy = club["spots_taken"] / max(club["spots_total"], 1)
    return min(100, int(round(club["rating"] * 0.7 + occupancy * 30)))


def build_weekly_schedule_df(enrolled_clubs: list[dict]) -> pd.DataFrame:
    rows = []
    for day in WEEK_DAYS_UI:
        day_clubs = [c for c in enrolled_clubs if day in extract_days(c["schedule"])]
        day_clubs.sort(key=lambda c: (parse_time_range(c["schedule"]) or (9999, 9999))[0])

        if not day_clubs:
            rows.append({
                "День": day,
                "Статус": "🟢 Свободное окно",
                "Кружки и время": "Нет запланированных занятий",
                "Локация": "—"
            })
        else:
            club_lines = [f"{extract_time_label(c['schedule'])} • {c['name']}" for c in day_clubs]
            room_lines = [c["room"] for c in day_clubs]
            status = "🔴 Плотный день (2+)" if len(day_clubs) >= 2 else "📘 Занятие"
            rows.append({
                "День": day,
                "Статус": status,
                "Кружки и время": " | ".join(club_lines),
                "Локация": " | ".join(room_lines)
            })
    return pd.DataFrame(rows)


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
    """Возвращает {club_id: (cosine_similarity 0..1, список читаемых совпавших слов)}."""
    query_tokens, query_stem_map = tokenize_with_map(query_text, expand_synonyms=True)
    if not query_tokens:
        return {c["id"]: (0.0, []) for c in clubs}

    raw_query_tokens, raw_query_map = tokenize_with_map(query_text, expand_synonyms=False)
    raw_query_stems = set(raw_query_tokens)

    docs_tokens = {}
    docs_stem_maps = {}
    for c in clubs:
        corpus = f"{' '.join(c['tags'])} {c['name']} {c['category']} {c['description']} {c['level']} {c['accessibility']}"
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
                "accessibility": "Гибрид / Онлайн-доступ",
                "tags": ["python", "ai", "аналитика", "программирование", "хакатоны", "данные"],
                "description": "Разработка ML-моделей, анализ данных и подготовка проектов к научным конкурсам (РНКП) и хакатонам."
            },
            {
                "id": 2,
                "name": "Robotics & Engineering (FTC / WRO)",
                "category": "Робототехника и Инженерия",
                "mentor": "Сериков Д.Н. (инженер-наставник)",
                "schedule": "Пн, Ср, Пт • 16:30–18:30",
                "room": "Мастерская робототехники (1 этаж)",
                "spots_total": 16,
                "spots_taken": 14,
                "rating": 96,
                "format": "Командная работа",
                "goal": "Олимпиады и проекты",
                "level": "Для новичков (без опыта)",
                "accessibility": "Без барьеров (1 этаж)",
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
                "accessibility": "Гибрид / Онлайн-доступ",
                "tags": ["математика", "логика", "комбинаторика", "геометрия", "олимпиады"],
                "description": "Разбор нестандартных олимпиадных задач по планиметрии, теории чисел и комбинаторике."
            },
            {
                "id": 4,
                "name": "NIS Startup & Economics Incubator",
                "category": "Предпринимательство",
                "mentor": "Ким Е.В. (учитель экономики)",
                "schedule": "Ср • 16:30–18:00",
                "room": "Коворкинг-зона (2 этаж)",
                "spots_total": 22,
                "spots_taken": 12,
                "rating": 91,
                "format": "Командная работа",
                "goal": "Карьера и навыки",
                "level": "Для новичков (без опыта)",
                "accessibility": "Гибрид / Онлайн-доступ",
                "tags": ["бизнес", "экономика", "стартапы", "финансы", "питч", "маркетинг"],
                "description": "От идеи до MVP: финансовое моделирование, исследование рынка и защита школьных стартапов с нуля."
            },
            {
                "id": 5,
                "name": "Дебатный клуб «Тұран» (KZ / RU / EN)",
                "category": "Лидерство и Дебаты",
                "mentor": "Омарова Г.Т. (педагог-организатор)",
                "schedule": "Чт • 16:30–18:00",
                "room": "Актовый малый зал (1 этаж)",
                "spots_total": 30,
                "spots_taken": 23,
                "rating": 93,
                "format": "Командная работа",
                "goal": "Коммуникация и лидерство",
                "level": "Для новичков (без опыта)",
                "accessibility": "Без барьеров (1 этаж)",
                "tags": ["дебаты", "речь", "английский", "аргументация", "лидерство"],
                "description": "Британский парламентский формат, критическое мышление и уверенные выступления на трёх языках."
            },
            {
                "id": 6,
                "name": "Баскетбольная секция NIS Turkistan",
                "category": "Спорт",
                "mentor": "Жумабаев Р.А. (тренер физкультуры)",
                "schedule": "Пн, Чт • 17:00–18:30",
                "room": "Большой спортзал (1 этаж)",
                "spots_total": 24,
                "spots_taken": 20,
                "rating": 94,
                "format": "Командная работа",
                "goal": "Здоровье и хобби",
                "level": "Средний уровень",
                "accessibility": "Офлайн • адаптивные нагрузки",
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
                "accessibility": "Тихая среда / малая группа",
                "tags": ["музыка", "домбыра", "творчество", "сцена", "культура"],
                "description": "Обучение с нуля, исполнение классических кюев и современных аранжировок для школьных концертов."
            },
            {
                "id": 8,
                "name": "Эко-волонтёрский штаб «Green Turkistan»",
                "category": "Волонтёрство",
                "mentor": "Байтурсынова Л.М. (учитель биологии)",
                "schedule": "Сб • 11:00–13:00",
                "room": "Каб. 115 (1 этаж)",
                "spots_total": 35,
                "spots_taken": 21,
                "rating": 89,
                "format": "Командная работа",
                "goal": "Коммуникация и лидерство",
                "level": "Для новичков (без опыта)",
                "accessibility": "Без барьеров (1 этаж)",
                "tags": ["волонтёрство", "экология", "социальные проекты", "помощь"],
                "description": "Эко-акции, сортировка отходов в школе, благотворительные ярмарки и социальные инициативы."
            },
            {
                "id": 9,
                "name": "Цифровая иллюстрация и UX/UI дизайн",
                "category": "Музыка и Искусство",
                "mentor": "Алиева Д.Р. (учитель искусства)",
                "schedule": "Ср, Пт • 16:00–17:30",
                "room": "Арт-студия 208",
                "spots_total": 16,
                "spots_taken": 13,
                "rating": 90,
                "format": "Индивидуально и в парах",
                "goal": "Карьера и навыки",
                "level": "Для новичков (без опыта)",
                "accessibility": "Гибрид / Онлайн-доступ",
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
                "accessibility": "Тихая среда / малая группа",
                "tags": ["шахматы", "стратегия", "логика", "турниры"],
                "description": "Анализ дебютов и миттельшпиля, комфортная тихая среда для учеников любого уровня подготовки."
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
                "accessibility": "Гибрид / Онлайн-доступ",
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
                "is_mine": False
            },
            {
                "id": 2,
                "post_type": "Поиск команды",
                "role": "Ученица 10 класса • Шанырак «Бәйтерек»",
                "need": "Собираю команду на региональный турнир по дебатам (английская лига)",
                "skills": ["English C1", "Публичные выступления"],
                "responded": False,
                "is_mine": False
            },
            {
                "id": 3,
                "post_type": "Учитель-наставник",
                "role": "Учитель физики • Садыков Е.М.",
                "need": "Готов стать научным руководителем для 2 проектов по физике и астрономии",
                "skills": ["Наставничество", "РНКП", "Физика"],
                "responded": False,
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

# --- ОТЛОЖЕННОЕ ОТОБРАЖЕНИЕ TOAST (НЕ ПРОПАДАЕТ ПОСЛЕ RERUN) ---
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

# --- БОКОВАЯ ПАНЕЛЬ (ПРОФИЛЬ, ДОСТУПНОСТЬ, УВЕДОМЛЕНИЯ, СБРОС ДЕМО) ---
with st.sidebar:
    st.subheader("👤 Профиль ученика")
    st.markdown("**Алнур Ш.** • 9 класс (Шанырак «Түркістан»)")
    st.caption("ID: #NIS-2026-09K • Личные контакты скрыты")

    col_s1, col_s2 = st.columns(2)
    col_s1.metric(
        "Мои клубы",
        len(st.session_state.enrolled_ids),
        help="Текущее количество активных записей в кружки и секции"
    )
    col_s2.metric(
        "Часов за семестр",
        semester_hours,
        help="20 базовых часов за семестр + 4 ч. за каждый активный клуб + 2 ч. за каждое мероприятие"
    )

    st.divider()
    st.subheader("♿ Доступность интерфейса")
    a11y_mode = st.toggle("Повышенная читаемость (крупный шрифт)", value=False)

    st.divider()
    st.subheader("🔔 Уведомления")
    for note in st.session_state.notifications[:4]:
        st.info(note)

    st.divider()
    st.caption("NIS Turkistan • 5 Years Hackathon Prototype")
    if st.button(
        "🔄 Сбросить демо",
        help="Вернуть все данные к исходному состоянию перед выступлением",
        **BTN_STRETCH
    ):
        st.session_state.clear()
        st.rerun()

# --- СТИЛИЗАЦИЯ UI (С ПОДДЕРЖКОЙ РЕЖИМА ДОСТУПНОСТИ И ПЕРЕНОСА МЕТРИК) ---
a11y_css = """
    html, body, [class*="css"] { font-size: 18px !important; }
    .stMarkdown p, .stMarkdown li, label, .stCaption { font-size: 1.15rem !important; line-height: 1.55 !important; }
    .badge { border: 1.5px solid #0f4c3a !important; font-size: 0.92rem !important; }
    .privacy-note { border-left-width: 6px !important; font-size: 1.05rem !important; }
""" if a11y_mode else ""

st.markdown(f"""
<style>
    .main-header {{
        background: linear-gradient(135deg, #0f4c3a 0%, #1b7a5e 100%);
        padding: 1.5rem 2rem;
        border-radius: 14px;
        color: white;
        margin-bottom: 1.5rem;
    }}
    .main-header h1 {{
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }}
    .main-header p {{
        margin: 0.4rem 0 0 0;
        opacity: 0.92;
        font-size: 1rem;
    }}
    .badge {{
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        background-color: #e6f4ef;
        color: #0f4c3a;
        margin-right: 0.35rem;
        margin-bottom: 0.3rem;
    }}
    .badge-level {{
        background-color: #eef2ff;
        color: #3730a3;
    }}
    .badge-a11y {{
        background-color: #fef3c7;
        color: #92400e;
    }}
    .badge-mine {{
        background-color: #dcfce7;
        color: #166534;
    }}
    .privacy-note {{
        background-color: #f8fafc;
        border-left: 4px solid #1b7a5e;
        padding: 0.75rem 1rem;
        border-radius: 6px;
        font-size: 0.88rem;
        color: #334155;
        margin-bottom: 1rem;
    }}
    [data-testid="stMetricValue"] {{
        font-size: 1.75rem !important;
        line-height: 1.2 !important;
    }}
    [data-testid="stMetricValue"] > div {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
    }}
    {a11y_css}
</style>
""", unsafe_allow_html=True)

# --- ШАПКА ПРИЛОЖЕНИЯ ---
st.markdown("""
<div class="main-header">
    <h1>🚀 NIS HUB — Территория талантов и возможностей</h1>
    <p>Единая цифровая экосистема кружков, клубов, наставников и событий NIS Turkistan</p>
</div>
""", unsafe_allow_html=True)

# --- ОСНОВНАЯ НАВИГАЦИЯ ПО МОДУЛЯМ ---
tabs = st.tabs([
    "📚 Каталог кружков",
    "🤖 AI-подбор (Find Your Passion)",
    "📅 События и челленджи",
    "➕ Создать свой клуб",
    "🤝 Сообщество и наставники",
    "🏆 Моё портфолио",
    "🛡️ Модерация (Админ/Педагог)"
])

# ==========================================
# ВКЛАДКА 1: CLUB DIRECTORY & ONLINE REGISTRATION
# ==========================================
with tabs[0]:
    st.subheader("Каталог кружков, секций и клубов NIS Turkistan")

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1.3, 1.3, 1.3])
    with col_f1:
        search_query = st.text_input("🔍 Поиск по названию или навыку", placeholder="Например: Python, баскетбол, дебаты...")
    with col_f2:
        categories = ["Все направления"] + sorted(list({c["category"] for c in st.session_state.clubs}))
        selected_cat = st.selectbox("Направление", categories)
    with col_f3:
        levels = ["Любой уровень", "Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"]
        selected_level = st.selectbox("Порог входа", levels)
    with col_f4:
        a11y_options = ["Любой формат"] + sorted(list({c["accessibility"] for c in st.session_state.clubs}))
        selected_a11y = st.selectbox("Доступность / среда", a11y_options)

    only_available = st.checkbox("Показать только клубы со свободными местами", value=False)

    filtered_clubs = []
    for club in st.session_state.clubs:
        if selected_cat != "Все направления" and club["category"] != selected_cat:
            continue
        if selected_level != "Любой уровень" and club["level"] != selected_level:
            continue
        if selected_a11y != "Любой формат" and club["accessibility"] != selected_a11y:
            continue
        if only_available and club["spots_taken"] >= club["spots_total"]:
            continue
        if search_query:
            q = search_query.lower()
            in_name = q in club["name"].lower()
            in_desc = q in club["description"].lower()
            in_tags = any(q in t.lower() for t in club["tags"])
            if not (in_name or in_desc or in_tags):
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
                    f"<span class='badge badge-a11y'>{html.escape(club['accessibility'])}</span>",
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
# ВКЛАДКА 2: FIND YOUR PASSION (NLP + AI-РЕКОМЕНДАЦИИ)
# ==========================================
with tabs[1]:
    st.subheader("🤖 AI-навигатор «Find Your Passion» (NLP TF-IDF + Профильный матчинг)")
    st.write("Опишите своими словами, чем вам хочется заниматься, и выберите параметры — гибридный алгоритм проанализирует смысл вашего запроса через векторную модель TF-IDF и подберёт топ-3 клуба с объяснением.")

    with st.expander("⚙️ Архитектура AI-модуля (информация для жюри)"):
        st.markdown("""
        * **NLP-анализ свободного текста:** фильтрация стоп-слов + стемминг русских и английских слов (приведение к морфологическим основам) + семантическое расширение синонимов + построение векторов **TF-IDF** и расчёт **косинусного сходства (Cosine Similarity)**.
        * **Гибридный скоринг:** итоговый `Match Score` объединяет семантическую близость текста (до 45%) и структурированные параметры ученика — цель, порог входа, формат и расписание (до 55%).
        * **Приватность и надёжность:** движок работает локально без передачи персональных данных учеников во внешние облачные LLM (с готовностью к подключению внешнего LLM API через фолбэк).
        """)

    with st.form("ai_recommender_form"):
        user_prompt = st.text_area(
            "✍️ Опишите своими словами, что вам нравится, какую цель ставите или какие есть пожелания:",
            placeholder="Например: Хочу научиться делать сайты или свой стартап с нуля, без опыта, желательно чтобы можно было подключаться онлайн..."
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
                "Ваш текущий уровень / порог входа:",
                ["Любой уровень", "Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"]
            )
            preferred_format = st.radio(
                "Комфортный формат работы:",
                ["Не имеет значения", "Командная работа", "Индивидуально и в парах"],
                horizontal=True
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

            # 1. NLP-компонента (TF-IDF + Cosine Similarity)
            raw_sim, matched_words = nlp_scores[club["id"]]
            nlp_pct = int(round((raw_sim / max_sim) * 100)) if max_sim > 0 else 0
            nlp_points = (raw_sim / max_sim) * 42 if max_sim > 0 else 0

            if matched_words and user_prompt.strip():
                reasons.append(f"NLP-анализ (стемминг + TF-IDF) выявил смысловое совпадение по темам: {', '.join(matched_words)}")

            # 2. Профильная компонента
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
                    reasons.append(f"подходящий порог входа ({club['level'].lower()})")
                elif preferred_level == "Для новичков (без опыта)" and club["level"] == "Продвинутый уровень":
                    profile_points -= 12

            if preferred_format == "Не имеет значения" or club["format"] == preferred_format:
                profile_points += 6

            if free_day != "Любой день" and free_day in extract_days(club["schedule"]):
                profile_points += 8
                reasons.append(f"удобное расписание ({free_day})")

            prompt_low = user_prompt.lower()
            if ("онлайн" in prompt_low or "удален" in prompt_low) and "Онлайн" in club["accessibility"]:
                profile_points += 10
                reasons.append("доступен гибридный / онлайн-формат")
            if ("без опыта" in prompt_low or "нович" in prompt_low or "с нуля" in prompt_low) and "новичков" in club["level"]:
                profile_points += 10
                reasons.append("комфортный вход с нуля без опыта")

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

    # Рендеринг результатов ВНЕ блока submitted_ai — кнопки записи работают стабильно
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
                        f"<span class='badge badge-a11y'>{html.escape(club['accessibility'])}</span>",
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
# ВКЛАДКА 3: EVENTS & CHALLENGES (РЕАКТИВНЫЕ МЕСТА)
# ==========================================
with tabs[2]:
    st.subheader("📅 Календарь школьных событий, олимпиад и челленджей")
    st.caption("Регистрация на события автоматически обновляет количество оставшихся мест, часы активности и счётчик мероприятий в портфолио.")
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
                        st.session_state.pending_toast = (f"Регистрация на «{ev['title']}» подтверждена! (+2 ч. в портфолио)", "📅")
                        st.rerun()
                else:
                    st.button("Мест нет", key=f"ev_full_{ev['id']}", disabled=True, **BTN_STRETCH)

# ==========================================
# ВКЛАДКА 4: CREATE YOUR CLUB
# ==========================================
with tabs[3]:
    st.subheader("➕ Инициатива ученика: создать собственный клуб")
    st.markdown("""
    <div class="privacy-note">
        <b>Правило безопасности и качества NIS HUB:</b> согласно регламенту школы, заявка на открытие нового клуба проходит проверку ответственным педагогом или администрацией перед публикацией в общем каталоге.
    </div>
    """, unsafe_allow_html=True)

    with st.form("create_club_form", clear_on_submit=True):
        new_name = st.text_input("Название нового клуба *", placeholder="Например: Клуб спортивного программирования NIS")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            new_cat = st.selectbox("Направление *", ["IT и Программирование", "Наука и Олимпиады", "Робототехника и Инженерия", "Предпринимательство", "Лидерство и Дебаты", "Спорт", "Музыка и Искусство", "Волонтёрство"])
            new_mentor = st.text_input("Предполагаемый учитель-наставник *", placeholder="ФИО педагога (если уже обсудили)")
            new_level = st.selectbox("Порог входа *", ["Для новичков (без опыта)", "Средний уровень", "Продвинутый уровень"])
        with c_col2:
            new_schedule = st.text_input("Желаемое расписание *", placeholder="Например: Пт • 16:30–18:00")
            new_goal = st.selectbox("Основной фокус клуба", ["Олимпиады и проекты", "Карьера и навыки", "Коммуникация и лидерство", "Здоровье и хобби"])
            new_a11y = st.selectbox("Формат доступности *", ["Без барьеров (1 этаж)", "Гибрид / Онлайн-доступ", "Тихая среда / малая группа", "Офлайн • адаптивные нагрузки"])
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
                    "accessibility": new_a11y,
                    "tags": [t.strip().lower() for t in new_tags.split(",") if t.strip()] or ["инициатива"],
                    "description": new_desc.strip(),
                    "submitted_at": datetime.now().strftime("%H:%M")
                })
                st.success("Заявка отправлена! Перейдите во вкладку «🛡️ Модерация», чтобы увидеть, как администратор одобряет её.")
            else:
                st.error("Пожалуйста, заполните все обязательные поля (*).")

# ==========================================
# ВКЛАДКА 5: COMMUNITY & MENTORS (ДВУСТОРОННЯЯ + ПРИВАТНОСТЬ)
# ==========================================
with tabs[4]:
    st.subheader("🤝 Поиск единомышленников и учителей-наставников")
    st.markdown("""
    <div class="privacy-note">
        <b>Защита персональных данных:</b> личные номера телефонов, мессенджеры и почта учеников не публикуются в открытом доступе. Связь происходит только через безопасный внутренний отклик на платформе.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("➕ Опубликовать свой запрос на поиск команды или наставника"):
        with st.form("new_community_post", clear_on_submit=True):
            post_type = st.selectbox("Тип запроса", ["Поиск команды", "Ищу учителя-наставника", "Идея проекта"])
            post_need = st.text_input("Кого и для чего вы ищете? *", placeholder="Например: Ищу дизайнера в команду на хакатон по кейсу NIS HUB...")
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
                        "is_mine": True
                    })
                    st.session_state.pending_toast = ("Ваш запрос опубликован в ленте сообщества!", "📣")
                    st.rerun()
                else:
                    st.error("Опишите, кого вы ищете.")

    comm_filter = st.radio(
        "Показать:",
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
            p1, p2 = st.columns([4, 1.3])
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
            with p2:
                if post.get("is_mine"):
                    if st.button("🗑️ Удалить", key=f"post_del_{post['id']}", **BTN_STRETCH):
                        st.session_state.community_posts = [
                            p for p in st.session_state.community_posts if p["id"] != post["id"]
                        ]
                        st.session_state.pending_toast = ("Ваш запрос удалён из ленты.", "🗑️")
                        st.rerun()
                elif post["responded"]:
                    st.button("📨 Отклик отправлен", key=f"post_sent_{post['id']}", disabled=True, **BTN_STRETCH)
                else:
                    if st.button("Откликнуться", key=f"post_resp_{post['id']}", type="primary", **BTN_STRETCH):
                        post["responded"] = True
                        st.session_state.pending_toast = ("Запрос отправлен через безопасный внутренний чат NIS HUB!", "🤝")
                        st.rerun()

# ==========================================
# ВКЛАДКА 6: MY ACHIEVEMENTS, СЕТКА РАСПИСАНИЯ И ЖИВОЙ РЕЙТИНГ
# ==========================================
with tabs[5]:
    col_head, col_dl = st.columns([3.5, 1.5])
    with col_head:
        st.subheader("🏆 Моё портфолио и рейтинг активности клубов")
    with col_dl:
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
    m1.metric(
        "Активных клубов",
        len(st.session_state.enrolled_ids),
        help="Кружки и секции, на которые вы записаны в текущем семестре"
    )
    m2.metric(
        "Мероприятий за год",
        active_events_count,
        help="4 завершённых мероприятия за учебный год + текущие регистрации во вкладке «События»"
    )
    m3.metric(
        "Часов за семестр",
        semester_hours,
        help="20 базовых часов за семестр + 4 ч. за каждый активный клуб + 2 ч. за каждое мероприятие"
    )
    m4.metric(
        "Подтверждённых достижений",
        len(ACHIEVEMENTS_DATA),
        help="Верифицированные школой результаты олимпиад и проектов"
    )

    st.markdown("#### 🗓️ Моя сетка внеурочной нагрузки (Пн–Сб)")
    st.caption("Помогает сбалансировать неделю и сразу видеть свободные дни для новых секций или подготовки к проектам.")
    weekly_df = build_weekly_schedule_df(enrolled_clubs)
    st.dataframe(weekly_df, hide_index=True, **DF_STRETCH)

    st.markdown("#### Мои ближайшие мероприятия")
    if registered_events:
        ev_cols = st.columns(2)
        for idx, rev in enumerate(registered_events):
            with ev_cols[idx % 2]:
                st.info(f"🗓️ **{rev['title']}** — {rev['date']} ({rev['organizer']})")
    else:
        st.caption("Вы пока не зарегистрированы на предстоящие события.")

    st.markdown("#### Личные достижения (для портфолио выпускника)")
    achievements_df = pd.DataFrame(ACHIEVEMENTS_DATA)
    st.dataframe(achievements_df, hide_index=True, **DF_STRETCH)

    st.divider()
    st.markdown("#### 📊 Живой рейтинг активности клубов NIS Turkistan (без публичного ранжирования учеников)")
    st.caption("Рассчитывается динамически на основе достижений клуба (70%) и текущей вовлечённости участников (30%) — обновляется сразу после записи.")
    rating_rows = [
        {
            "Клуб": c["name"],
            "Направление": c["category"],
            "Индекс активности": compute_live_rating(c),
            "Участников": c["spots_taken"]
        }
        for c in st.session_state.clubs
    ]
    rating_df = pd.DataFrame(rating_rows).sort_values(by="Индекс активности", ascending=False)
    st.bar_chart(rating_df.set_index("Клуб")["Индекс активности"], color="#1b7a5e")

# ==========================================
# ВКЛАДКА 7: МОДЕРАЦИЯ + МИНИ-ДАШБОРД ДЛЯ АДМИНИСТРАЦИИ
# ==========================================
with tabs[6]:
    st.subheader("🛡️ Кабинет ответственного педагога / администрации")

    # --- МИНИ-ДАШБОРД УПРАВЛЕНЧЕСКОЙ АНАЛИТИКИ ---
    st.markdown("#### 📈 Оперативная аналитика внеурочной деятельности NIS Turkistan")
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
        help=f"Занято {total_taken} из {total_spots} доступных мест во всех {len(st.session_state.clubs)} клубах"
    )
    adm2.metric(
        "Самое востребованное направление",
        top_cat,
        delta=f"{top_cat_pct}% мест занято",
        help="Направление с наивысшим процентом заполняемости групп"
    )
    adm3.metric(
        "Клубы на грани переполнения (≥85%)",
        len(near_full_clubs),
        help="Сигнал администрации: рассмотреть открытие второй группы или выделение дополнительной аудитории"
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
    st.caption("Модуль подтверждения заявок перед их публикацией в общем каталоге школы.")

    if not st.session_state.pending_clubs:
        st.info("Новых заявок на рассмотрении нет.")
    else:
        for idx, p_club in enumerate(st.session_state.pending_clubs):
            with st.container(border=True):
                st.markdown(
                    f"<span class='badge'>{html.escape(p_club['category'])}</span>"
                    f"<span class='badge badge-level'>{html.escape(p_club['level'])}</span>"
                    f"<span class='badge badge-a11y'>{html.escape(p_club['accessibility'])}</span>",
                    unsafe_allow_html=True
                )
                st.markdown(f"### Заявка: {p_club['name']}")
                st.markdown(f"**Инициатор:** {p_club['author']} • **Время подачи:** {p_club['submitted_at']}")
                st.markdown(f"**Наставник:** {p_club['mentor']} • **Расписание:** {p_club['schedule']}")
                st.write(p_club["description"])

                b_col1, b_col2, _ = st.columns([1.4, 1.2, 3])
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
                            "accessibility": p_club["accessibility"],
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
