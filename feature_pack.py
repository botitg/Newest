"""
feature_pack.py - расширенный игровой контент и новые механики
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Optional, Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import db

router = Router()

INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")

EDU_TEST_COOLDOWN_MINUTES = 45
EDU_QUIZ_QUESTIONS_PER_RUN = 5
EDU_QUIZ_RECENT_MEMORY = 18
EDU_STUDY_SESSION_COOLDOWN_MINUTES = 360

EDU_QUESTION_BANK = [
    {"q": "Что означает инфляция в макроэкономике?", "options": ["Рост общего уровня цен", "Падение безработицы", "Рост экспорта", "Снижение ключевой ставки"], "correct": 0, "difficulty": 1, "explain": "Инфляция — устойчивый рост общего уровня цен."},
    {"q": "Дефляция обычно опасна тем, что...", "options": ["Стимулирует инвестиции", "Ускоряет рост зарплат", "Снижает спрос и тормозит экономику", "Повышает налоговые поступления"], "correct": 2, "difficulty": 2, "explain": "При дефляции потребители откладывают покупки, а бизнес режет инвестиции."},
    {"q": "Дефицит бюджета — это ситуация, когда...", "options": ["Доходы равны расходам", "Доходы больше расходов", "Расходы больше доходов", "Нет налогов"], "correct": 2, "difficulty": 1, "explain": "Дефицит — превышение расходов над доходами."},
    {"q": "Ключевая ставка ЦБ в первую очередь влияет на...", "options": ["Курс школьной успеваемости", "Стоимость кредитов в экономике", "Количество государственных символов", "Размер минимальной пенсии напрямую"], "correct": 1, "difficulty": 2, "explain": "Через ставку ЦБ задается стоимость денег в банковской системе."},
    {"q": "НДС — это налог, который...", "options": ["Платит только президент", "Взимается на добавленную стоимость", "Платится только за импорт", "Взимается только с наличных"], "correct": 1, "difficulty": 1, "explain": "НДС начисляется на добавленную стоимость на этапах цепочки поставок."},
    {"q": "Диверсификация портфеля нужна, чтобы...", "options": ["Увеличить риск в одном активе", "Снизить зависимость от одного актива", "Убрать комиссии банка", "Повысить налоги"], "correct": 1, "difficulty": 2, "explain": "Разные активы снижают общий риск портфеля."},
    {"q": "Сложный процент означает, что...", "options": ["Процент начисляется только один раз", "Процент начисляется и на прошлые проценты", "Процент зависит только от погоды", "Процент не влияет на итоговую сумму"], "correct": 1, "difficulty": 2, "explain": "При сложном проценте база начисления растет со временем."},
    {"q": "Ликвидный актив — это актив, который...", "options": ["Нельзя продать", "Быстро превращается в деньги с малой потерей стоимости", "Обязательно приносит дивиденды", "Используется только государством"], "correct": 1, "difficulty": 2, "explain": "Ликвидность — скорость и легкость продажи актива."},
    {"q": "KPI в организации — это...", "options": ["Случайные показатели", "Ключевые метрики эффективности", "Название налоговой формы", "Тип банковского вклада"], "correct": 1, "difficulty": 2, "explain": "KPI помогают измерять результативность команды/процесса."},
    {"q": "Маржинальность бизнеса растет, если...", "options": ["Себестоимость растет быстрее выручки", "Выручка растет, а себестоимость контролируется", "Налоги отменены", "Нет учета расходов"], "correct": 1, "difficulty": 3, "explain": "Маржа укрепляется при контроле затрат и росте выручки."},
    {"q": "Точка безубыточности — это...", "options": ["Максимальная прибыль", "Уровень, где доходы = расходам", "Размер налоговой скидки", "Количество сотрудников"], "correct": 1, "difficulty": 2, "explain": "На точке безубыточности компания не в прибыли и не в убытке."},
    {"q": "Амортизация в учете нужна для...", "options": ["Случайного штрафа", "Распределения стоимости актива по сроку службы", "Списания всех налогов сразу", "Увеличения инфляции"], "correct": 1, "difficulty": 3, "explain": "Амортизация отражает износ актива во времени."},
    {"q": "Финансовый рычаг (leverage) означает...", "options": ["Работу только с наличными", "Использование заемных средств для усиления результата", "Снижение прозрачности отчетности", "Отказ от инвестиций"], "correct": 1, "difficulty": 3, "explain": "Заемные средства увеличивают потенциал и риск."},
    {"q": "Какой принцип важен для антикоррупционного контроля?", "options": ["Закрыть все отчеты", "Разделение полномочий и прозрачность", "Назначение без проверок", "Устные договоренности"], "correct": 1, "difficulty": 3, "explain": "Прозрачность и контрольные контуры снижают коррупционные риски."},
    {"q": "Верховенство закона означает, что...", "options": ["Закон обязателен для всех, включая власть", "Закон не нужен при кризисе", "Только суды подчиняются закону", "Только бизнес обязан исполнять закон"], "correct": 0, "difficulty": 2, "explain": "Принцип действует для всех субъектов без исключений."},
    {"q": "Какая ветвь власти обычно принимает законы?", "options": ["Исполнительная", "Законодательная", "Судебная", "Банковская"], "correct": 1, "difficulty": 1, "explain": "Законы принимаются законодательной ветвью."},
    {"q": "Если доходность актива высокая, то обычно...", "options": ["Риск тоже выше", "Риск всегда ниже", "Риск отсутствует", "Нельзя оценить связь"], "correct": 0, "difficulty": 2, "explain": "Риск и ожидаемая доходность часто связаны положительно."},
    {"q": "Что лучше описывает cash-flow?", "options": ["Только прибыль в отчете", "Движение реальных денежных потоков", "Список активов без операций", "Размер уставного капитала"], "correct": 1, "difficulty": 2, "explain": "Cash-flow показывает поступления и выбытия денег."},
    {"q": "Корреляция активов в портфеле важна потому, что...", "options": ["Показывает цвет логотипа", "Влияет на общий риск портфеля", "Определяет налоговую ставку", "Заменяет аудит"], "correct": 1, "difficulty": 4, "explain": "Слабая корреляция помогает снижать риск портфеля."},
    {"q": "Что такое VaR в риск-менеджменте?", "options": ["Гарантированная прибыль", "Оценка возможного убытка при заданной вероятности", "Размер дивидендов", "Ставка по депозиту"], "correct": 1, "difficulty": 5, "explain": "VaR оценивает предел потерь в вероятностном сценарии."},
    {"q": "При шоке предложения обычно происходит...", "options": ["Рост выпуска и падение цен", "Падение выпуска и рост цен", "Снижение налогов автоматически", "Нулевая инфляция"], "correct": 1, "difficulty": 4, "explain": "Негативный шок предложения толкает цены вверх и выпуск вниз."},
    {"q": "Госзакупки прозрачнее всего проводить через...", "options": ["Закрытые устные договоренности", "Публичный конкурс с критериями", "Назначение подрядчика без тендера", "Случайный выбор"], "correct": 1, "difficulty": 3, "explain": "Публичный конкурс снижает коррупционные риски и повышает эффективность."},
    {"q": "Эластичность спроса показывает...", "options": ["Скорость печати денег", "Чувствительность спроса к изменению цены", "Размер госдолга", "Количество чиновников"], "correct": 1, "difficulty": 3, "explain": "Это мера реакции спроса на изменение цены."},
    {"q": "В кризис ликвидности первоочередная задача менеджера...", "options": ["Игнорировать платежный календарь", "Контролировать денежные разрывы и обязательства", "Увеличить дивиденды любой ценой", "Отменить учет"], "correct": 1, "difficulty": 4, "explain": "В кризис важно сохранить платежеспособность."},
    {"q": "Что сильнее всего увеличивает вероятность дефолта по кредиту?", "options": ["Снижение долговой нагрузки", "Рост просрочек и падение доходов", "Стабильный cash-flow", "Повышение рейтинга"], "correct": 1, "difficulty": 3, "explain": "Просрочки и падение доходов — прямые факторы риска дефолта."},
    {"q": "Для устойчивого роста организации важнее всего...", "options": ["Только разовые акции", "Система процессов и контроль качества", "Случайные решения лидера", "Постоянное наращивание штрафов"], "correct": 1, "difficulty": 2, "explain": "Системность процессов дает стабильный долгосрочный рост."},
    {"q": "Какой подход лучше при высокой рыночной волатильности?", "options": ["Максимальная концентрация в одном активе", "План управления риском и лимиты позиции", "Полный отказ от учета", "Наращивание плеча без ограничений"], "correct": 1, "difficulty": 4, "explain": "Лимиты и дисциплина защищают капитал в турбулентности."},
    {"q": "Если индекс рынка сильно вырос за короткий срок, разумно...", "options": ["Игнорировать риск коррекции", "Частично фиксировать прибыль и ребалансировать", "Увеличить ставку в один актив", "Отменить stop-loss"], "correct": 1, "difficulty": 4, "explain": "Фиксация части прибыли снижает риск внезапной коррекции."},
    {"q": "Что из этого улучшает качество управленческого решения?", "options": ["Данные + сценарный анализ + проверка рисков", "Интуиция без данных", "Секретные договоренности", "Полное отсутствие KPI"], "correct": 0, "difficulty": 3, "explain": "Сценарии и риск-анализ делают решение более устойчивым."},
    {"q": "Как правильно оценивать инвестиционный проект?", "options": ["Только по эмоциям", "По NPV/денежным потокам/рискам", "По количеству лайков", "По случайному выбору"], "correct": 1, "difficulty": 5, "explain": "Финансовые метрики и риск-профиль — база оценки проекта."},
]


class FeatureStates(StatesGroup):
    business_name = State()
    private_org_name = State()
    private_org_application_text = State()
    private_casino_name = State()
    hustle_guess = State()
    job_application_text = State()
    business_fund_amount = State()
    private_org_fund_amount = State()
    gang_name = State()
    cartel_name = State()
    law_create = State()
    law_edit = State()
    flag_text = State()
    flag_photo = State()
    tax_holiday_reason = State()
    contract_title = State()
    contract_description = State()
    contract_reward = State()
    bank_deposit_amount = State()
    bank_withdraw_amount = State()


def _display_user(user: dict | None) -> str:
    user = user or {}
    for field in ("nickname", "full_name"):
        value = str(user.get(field) or "")
        for token in INVISIBLE_NAME_CHARS:
            value = value.replace(token, "")
        value = " ".join(value.split()).strip()
        if value:
            return value
    username = str(user.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    return f"Игрок #{user.get('user_id')}"


def _md(text: str) -> str:
    escaped = str(text or "")
    for token in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        escaped = escaped.replace(token, f"\\{token}")
    return escaped


def _back(callback_data: str = "back_to_main", text: str = "🔙 Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)]])


def _edit_or_answer(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        async def _sender(*args, **kwargs):
            try:
                await event.message.edit_text(*args, **kwargs)
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
                raise
        return _sender

    async def _sender(*args, **kwargs):
        await event.answer(*args, **kwargs)

    return _sender


def _time_left_label(ready_date: str | None) -> str:
    raw = str(ready_date or "").strip()
    if not raw:
        return "время неизвестно"
    try:
        ready_dt = datetime.fromisoformat(raw)
    except Exception:
        return raw[:16]
    delta = ready_dt - datetime.now()
    if delta.total_seconds() <= 0:
        return "готово"
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours <= 0:
        return f"{minutes} мин"
    return f"{hours} ч {minutes} мин"


def _edu_minutes_since(iso_dt: str | None) -> Optional[int]:
    raw = str(iso_dt or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    return int((datetime.now() - dt).total_seconds() // 60)


def _edu_quick_test_cooldown_remaining(last_test_at: str | None) -> int:
    passed = _edu_minutes_since(last_test_at)
    if passed is None:
        return 0
    remain = EDU_TEST_COOLDOWN_MINUTES - passed
    return max(0, remain)


def _edu_study_cooldown_remaining(last_study_at: str | None) -> int:
    passed = _edu_minutes_since(last_study_at)
    if passed is None:
        return 0
    remain = EDU_STUDY_SESSION_COOLDOWN_MINUTES - passed
    return max(0, remain)


def _edu_difficulty_cap(level: int) -> int:
    safe_level = max(1, int(level or 1))
    if safe_level <= 2:
        return 2
    if safe_level <= 5:
        return 3
    if safe_level <= 8:
        return 4
    return 5


def _edu_question_by_index(idx: int) -> Optional[dict]:
    if 0 <= idx < len(EDU_QUESTION_BANK):
        return EDU_QUESTION_BANK[idx]
    return None


def _edu_format_question_lines(question: dict, number: int, total: int) -> list[str]:
    return [
        "📝 ТЕСТ ОБРАЗОВАНИЯ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Вопрос {int(number)}/{int(total)} | Сложность: {int(question.get('difficulty') or 1)}/5",
        "",
        str(question.get("q") or ""),
        "",
        "Выберите один вариант ответа:",
    ]


def _edu_keyboard_for_question(q_idx: int) -> InlineKeyboardMarkup:
    question = _edu_question_by_index(q_idx) or {}
    options = list(question.get("options") or [])
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for idx, option in enumerate(options[:4]):
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"{idx + 1}. {str(option)}", callback_data=f"fp_edu_test_pick_{idx}")]
        )
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="edu_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def _edu_load_recent_question_ids(user_id: int) -> list[int]:
    key = f"edu_q_hist_{int(user_id)}"
    raw = str(await db.get_system_state(key) or "").strip()
    if not raw:
        return []
    today = datetime.now().date().isoformat()
    parts = raw.split("|", 1)
    if len(parts) != 2 or parts[0] != today:
        return []
    used_ids: list[int] = []
    for token in parts[1].split(","):
        token = token.strip()
        if token.isdigit():
            val = int(token)
            if 0 <= val < len(EDU_QUESTION_BANK) and val not in used_ids:
                used_ids.append(val)
    return used_ids


async def _edu_save_recent_question_ids(user_id: int, ids: list[int]) -> None:
    today = datetime.now().date().isoformat()
    normalized: list[int] = []
    for token in ids:
        try:
            val = int(token)
        except Exception:
            continue
        if 0 <= val < len(EDU_QUESTION_BANK) and val not in normalized:
            normalized.append(val)
    normalized = normalized[-EDU_QUIZ_RECENT_MEMORY:]
    payload = ",".join(str(v) for v in normalized)
    await db.set_system_state(f"edu_q_hist_{int(user_id)}", f"{today}|{payload}")


async def _edu_pick_question_indexes(user_id: int, level: int, total: int = EDU_QUIZ_QUESTIONS_PER_RUN) -> list[int]:
    total_needed = max(3, min(int(total or EDU_QUIZ_QUESTIONS_PER_RUN), 8))
    cap = _edu_difficulty_cap(level)
    preferred = [idx for idx, q in enumerate(EDU_QUESTION_BANK) if int(q.get("difficulty") or 1) <= cap]
    if len(preferred) < total_needed:
        preferred = list(range(len(EDU_QUESTION_BANK)))

    recent_ids = await _edu_load_recent_question_ids(user_id)
    recent_set = set(recent_ids)
    candidate = [idx for idx in preferred if idx not in recent_set]
    if len(candidate) < total_needed:
        extra = [idx for idx in preferred if idx not in candidate]
        random.shuffle(extra)
        candidate.extend(extra)
    if len(candidate) < total_needed:
        fallback = [idx for idx in range(len(EDU_QUESTION_BANK)) if idx not in candidate]
        random.shuffle(fallback)
        candidate.extend(fallback)
    random.shuffle(candidate)
    picked = candidate[:total_needed]
    if len(picked) < total_needed:
        full = list(range(len(EDU_QUESTION_BANK)))
        random.shuffle(full)
        for idx in full:
            if idx not in picked:
                picked.append(idx)
            if len(picked) >= total_needed:
                break
    return picked[:total_needed]


def _edu_required_correct(level: int, total_questions: int) -> int:
    total = max(1, int(total_questions or 1))
    lvl = max(1, int(level or 1))
    if lvl <= 3:
        return max(2, min(total, 3))
    if lvl <= 7:
        return max(3, min(total, 4))
    return max(4, min(total, 5))


def _edu_grade(score: int, total: int) -> str:
    total_safe = max(1, int(total or 1))
    ratio = float(score or 0) / total_safe
    if ratio >= 0.95:
        return "A+"
    if ratio >= 0.85:
        return "A"
    if ratio >= 0.7:
        return "B"
    if ratio >= 0.55:
        return "C"
    return "D"


async def _bot_username(event: Message | CallbackQuery) -> str:
    try:
        me = await event.bot.get_me()
        return str(me.username or "").strip()
    except Exception:
        return ""


FUN_ACTIVITY_CONFIG = [
    {
        "code": "street_show",
        "title": "🎤 Уличный концерт",
        "button": "🎤 Концерт",
        "hint": "Соберите толпу и чаевые.",
        "cooldown": 12,
    },
    {
        "code": "treasure_hunt",
        "title": "🧭 Охота за кладом",
        "button": "🧭 Клад",
        "hint": "Карта может привести к джекпоту или к пустышке.",
        "cooldown": 18,
    },
    {
        "code": "rumor_trade",
        "title": "📈 Торговля на слухах",
        "button": "📈 Слухи",
        "hint": "Риск-сделка с высокой волатильностью.",
        "cooldown": 14,
    },
    {
        "code": "cyber_hack",
        "title": "💻 Кибервзлом",
        "button": "💻 Взлом",
        "hint": "Подпольный доход, но репутация страдает.",
        "cooldown": 22,
    },
    {
        "code": "charity_drive",
        "title": "🤝 Благотворительная акция",
        "button": "🤝 Благотвор.",
        "hint": "Пожертвуйте деньги и поднимите репутацию.",
        "cooldown": 16,
    },
    {
        "code": "street_race",
        "title": "🏁 Ночная гонка",
        "button": "🏁 Гонка",
        "hint": "Ставка на адреналин: шанс на крупный приз.",
        "cooldown": 15,
    },
    {
        "code": "mystery_box",
        "title": "🎁 Загадочный ящик",
        "button": "🎁 Ящик",
        "hint": "Случайный эффект: от бонуса до ловушки.",
        "cooldown": 20,
    },
    {
        "code": "courier_rush",
        "title": "🚴 Экспресс-доставка",
        "button": "🚴 Доставка",
        "hint": "Быстрый заработок, зависит от подготовки.",
        "cooldown": 11,
    },
    {
        "code": "photo_hunt",
        "title": "📸 Фотоохота",
        "button": "📸 Фотоохота",
        "hint": "Поймайте редкий кадр и продайте СМИ.",
        "cooldown": 17,
    },
    {
        "code": "city_festival",
        "title": "🎪 Городской фестиваль",
        "button": "🎪 Фестиваль",
        "hint": "Большое событие с шансом на славу.",
        "cooldown": 24,
    },
]
FUN_ACTIVITY_MAP = {str(item["code"]): item for item in FUN_ACTIVITY_CONFIG}

FUN_STRATEGY_CONFIG = {
    "safe": {
        "label": "🛡 Осторожная",
        "description": "Меньше рисков, стабильнее результат.",
        "gain_mult": 0.85,
        "loss_mult": 0.7,
        "rep_shift": 0.12,
        "xp_mult": 1.05,
        "xp_flat": 2,
        "bonus_min": 500,
        "bonus_max": 1400,
    },
    "balanced": {
        "label": "⚖️ Сбалансированная",
        "description": "Ровный профиль наград и рисков.",
        "gain_mult": 1.0,
        "loss_mult": 1.0,
        "rep_shift": 0.0,
        "xp_mult": 1.0,
        "xp_flat": 0,
        "bonus_min": 700,
        "bonus_max": 2100,
    },
    "risky": {
        "label": "🔥 Агрессивная",
        "description": "Большой куш или заметные потери.",
        "gain_mult": 1.32,
        "loss_mult": 1.35,
        "rep_shift": -0.1,
        "xp_mult": 1.18,
        "xp_flat": 4,
        "bonus_min": 1000,
        "bonus_max": 3200,
    },
}

FUN_ACTIVITY_STORY = {
    "street_show": {
        "setup": "Вы выходите на городскую площадь. Нужно выбрать формат выступления.",
        "decision": "Куда смещаете главный акцент концерта?",
        "options": ["Сильный вокал", "Шоу и перформанс", "Интерактив с толпой"],
        "success": "Толпа поддержала ваш ход: буст по чаевым и популярности.",
        "fail": "Публика не зацепилась, часть аудитории разошлась.",
    },
    "treasure_hunt": {
        "setup": "Карта указывает на три подозрительные зоны.",
        "decision": "Какой сектор раскапываете первым?",
        "options": ["Старый док", "Северный парк", "Подземный тоннель"],
        "success": "Вы угадали направление и нашли скрытый тайник.",
        "fail": "Пустой сектор. Потрачено время и ресурсы.",
    },
    "rumor_trade": {
        "setup": "В городе гуляют противоречивые экономические слухи.",
        "decision": "На какой сигнал ставите основной капитал?",
        "options": ["Рост импорта", "Снижение налогов", "Дефицит топлива"],
        "success": "Сигнал сработал точно, сделка усилилась.",
        "fail": "Слух оказался ложным, позиция ухудшилась.",
    },
    "cyber_hack": {
        "setup": "Операция требует точного выбора канала атаки.",
        "decision": "Какой вектор используете в решающий момент?",
        "options": ["Фишинг-цепочка", "Сетевой туннель", "Инсайдерский ключ"],
        "success": "Канал сработал идеально: добыча выросла.",
        "fail": "Защита среагировала, часть операции сорвалась.",
    },
    "charity_drive": {
        "setup": "Благотворительная акция стартует в трех районах.",
        "decision": "Куда направить основную волну волонтеров?",
        "options": ["Медцентр", "Школьный фонд", "Социальная кухня"],
        "success": "Решение дало сильный отклик общества и спонсоров.",
        "fail": "Сбор прошел средне, эффект ниже ожиданий.",
    },
    "street_race": {
        "setup": "Перед стартом нужно выбрать ключевую тактику трассы.",
        "decision": "На каком участке делаете решающий рывок?",
        "options": ["Первый поворот", "Средний отрезок", "Финишная прямая"],
        "success": "Точный рывок дал преимущество и прирост приза.",
        "fail": "Маневр не удался, темп был потерян.",
    },
    "mystery_box": {
        "setup": "Ящик содержит несколько отсеков с неизвестными эффектами.",
        "decision": "Какой отсек вскрываете главным?",
        "options": ["Левый", "Центральный", "Правый"],
        "success": "Вы вскрыли самый ценный отсек.",
        "fail": "В отсеке оказалась ловушка и бесполезный хлам.",
    },
    "courier_rush": {
        "setup": "У вас три возможных маршрута на экспресс-доставку.",
        "decision": "Какой маршрут берете как приоритетный?",
        "options": ["Через центр", "Через объезд", "Комбинированный"],
        "success": "Маршрут оказался быстрым и прибыльным.",
        "fail": "Возникла пробка/сбой, часть рейса сорвалась.",
    },
    "photo_hunt": {
        "setup": "Редакция ждет кадр дня, но локаций слишком много.",
        "decision": "Где охотитесь за главным снимком?",
        "options": ["Биржа", "Ночной рынок", "Городская набережная"],
        "success": "Вы поймали кадр в нужной точке и усилили гонорар.",
        "fail": "Локация не дала редкий материал.",
    },
    "city_festival": {
        "setup": "На фестивале конкурируют десятки участников.",
        "decision": "Какой блок программы продвигаете первым?",
        "options": ["Музыкальный", "Гастрономический", "Культурный"],
        "success": "Блок выстрелил и поднял итоговый сбор.",
        "fail": "Блок не дал вовлечения, доход ниже возможного.",
    },
}


def _fun_daily_focus_code(user_id: int) -> str:
    day_seed = int(datetime.now().strftime("%Y%m%d")) + int(user_id) * 17
    return str(FUN_ACTIVITY_CONFIG[day_seed % len(FUN_ACTIVITY_CONFIG)]["code"])


def _scale_fun_delta(value: float, gain_mult: float, loss_mult: float) -> float:
    numeric = float(value or 0)
    if numeric >= 0:
        return round(numeric * float(gain_mult), 2)
    return round(numeric * float(loss_mult), 2)


def _resolve_fun_activity_advanced(
    user: dict,
    code: str,
    strategy_key: str,
    choice: int,
    secret: int,
) -> dict:
    base = _resolve_fun_activity(user, code)
    strategy = FUN_STRATEGY_CONFIG.get(strategy_key, FUN_STRATEGY_CONFIG["balanced"])
    story = FUN_ACTIVITY_STORY.get(code, {})

    bal_delta = _scale_fun_delta(base.get("balance_delta", 0), strategy["gain_mult"], strategy["loss_mult"])
    shadow_delta = _scale_fun_delta(base.get("shadow_delta", 0), strategy["gain_mult"], strategy["loss_mult"])
    rep_delta = round(float(base.get("rep_delta") or 0) + float(strategy.get("rep_shift") or 0), 2)

    raw_xp = int(base.get("xp_delta") or 0)
    xp_delta = int(round(raw_xp * float(strategy.get("xp_mult") or 1.0))) + int(strategy.get("xp_flat") or 0)
    xp_delta = max(1, xp_delta)

    challenge_success = int(choice) == int(secret)
    if challenge_success:
        precision_bonus = random.randint(int(strategy["bonus_min"]), int(strategy["bonus_max"]))
        if code == "cyber_hack":
            shadow_delta = round(shadow_delta + precision_bonus, 2)
        else:
            bal_delta = round(bal_delta + precision_bonus, 2)
        rep_delta = round(rep_delta + (0.18 if strategy_key != "risky" else 0.08), 2)
        xp_delta += random.randint(4, 9)
        challenge_line = str(story.get("success") or "Решающий этап пройден успешно.")
    else:
        precision_penalty = random.randint(250, 900)
        bal_delta = round(bal_delta - precision_penalty, 2)
        rep_delta = round(rep_delta - (0.12 if strategy_key != "risky" else 0.18), 2)
        xp_delta += 1
        challenge_line = str(story.get("fail") or "Ключевой ход оказался неудачным.")

    text_lines = [
        str(base.get("text") or "Активность завершена."),
        f"Тактика: {strategy['label']} ({strategy['description']})",
        challenge_line,
    ]

    news_title = str(base.get("news_title") or "")
    news_body = str(base.get("news_body") or "")
    news_severity = str(base.get("news_severity") or "normal")
    if challenge_success and strategy_key == "risky" and random.random() < 0.25 and not news_title:
        pretty_name = str(FUN_ACTIVITY_MAP.get(code, {}).get("title") or code)
        news_title = f"Резонансная тактика: {pretty_name}"
        news_body = "Игрок применил агрессивную стратегию и резко усилил результат активности."
        news_severity = "hot"

    return {
        "balance_delta": round(bal_delta, 2),
        "shadow_delta": round(shadow_delta, 2),
        "rep_delta": round(rep_delta, 2),
        "xp_delta": int(xp_delta),
        "text": "\n".join(text_lines),
        "challenge_success": challenge_success,
        "strategy_label": strategy["label"],
        "news_title": news_title,
        "news_body": news_body,
        "news_severity": news_severity,
    }


def _format_money_delta(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(float(value or 0)):,.2f}"


def _format_rep_delta(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(float(value or 0)):.2f}"


def _format_xp_delta(value: int) -> str:
    sign = "+" if int(value or 0) >= 0 else "-"
    return f"{sign}{abs(int(value or 0))}"


def _fun_precheck(user: dict, code: str) -> tuple[bool, str]:
    balance = float(user.get("balance") or 0)
    if code == "rumor_trade" and balance < 800:
        return False, "❌ Нужно минимум $800 для риск-сделки."
    if code == "charity_drive" and balance < 500:
        return False, "❌ Нужно минимум $500 для пожертвования."
    if code == "street_race" and balance < 700:
        return False, "❌ Нужно минимум $700 на вход в гонку."
    return True, ""


def _resolve_fun_activity(user: dict, code: str) -> dict:
    reputation = float(user.get("reputation") or 50)
    education = int(user.get("education") or 1)
    payload = {
        "balance_delta": 0.0,
        "shadow_delta": 0.0,
        "rep_delta": 0.0,
        "xp_delta": 0,
        "text": "Событие прошло спокойно.",
        "news_title": "",
        "news_body": "",
        "news_severity": "normal",
    }

    if code == "street_show":
        crowd_mult = random.uniform(0.9, 1.7)
        payout = int(random.randint(500, 1400) * crowd_mult + reputation * 2.5)
        payload["balance_delta"] = float(payout)
        payload["rep_delta"] = 0.22
        payload["xp_delta"] = random.randint(8, 14)
        payload["text"] = f"Толпа оценила выступление. Чаевые: ${payout:,.0f}."
        return payload

    if code == "treasure_hunt":
        roll = random.random()
        if roll < 0.12:
            reward = random.randint(6500, 14500)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.45
            payload["xp_delta"] = random.randint(16, 28)
            payload["text"] = f"Вы нашли редкий тайник! Добыча: ${reward:,.0f}."
            payload["news_title"] = "Громкая находка клада в Мирнастане"
            payload["news_body"] = f"Игрок обнаружил редкий тайник и получил ${reward:,.0f}."
            payload["news_severity"] = "hot"
        elif roll < 0.72:
            reward = random.randint(1200, 3600)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.12
            payload["xp_delta"] = random.randint(10, 18)
            payload["text"] = f"Обычная находка, но прибыльная: +${reward:,.0f}."
        else:
            loss = random.randint(300, 1200)
            payload["balance_delta"] = -float(loss)
            payload["rep_delta"] = -0.18
            payload["xp_delta"] = 6
            payload["text"] = f"Ложный след. Потрачено на снаряжение: ${loss:,.0f}."
        return payload

    if code == "rumor_trade":
        outcomes = [(-680, -0.22), (-320, -0.08), (260, 0.05), (720, 0.12), (1300, 0.2)]
        money_delta, rep_delta = random.choice(outcomes)
        payload["balance_delta"] = float(money_delta)
        payload["rep_delta"] = float(rep_delta)
        payload["xp_delta"] = random.randint(7, 13)
        if money_delta >= 0:
            payload["text"] = f"Сделка на слухах удалась: +${money_delta:,.0f}."
        else:
            payload["text"] = f"Рынок развернулся против вас: -${abs(money_delta):,.0f}."
        return payload

    if code == "cyber_hack":
        roll = random.random()
        if roll < 0.22:
            fine = random.randint(500, 1300)
            payload["balance_delta"] = -float(fine)
            payload["rep_delta"] = -0.55
            payload["xp_delta"] = random.randint(8, 14)
            payload["text"] = f"Операция провалилась. Потери и штрафы: ${fine:,.0f}."
        elif roll < 0.85:
            shadow_gain = random.randint(1200, 3600)
            payload["shadow_delta"] = float(shadow_gain)
            payload["rep_delta"] = -0.28
            payload["xp_delta"] = random.randint(10, 18)
            payload["text"] = f"Подпольная сделка прошла успешно: +${shadow_gain:,.0f} в теневой баланс."
        else:
            shadow_gain = random.randint(5000, 9800)
            payload["shadow_delta"] = float(shadow_gain)
            payload["rep_delta"] = -0.62
            payload["xp_delta"] = random.randint(16, 26)
            payload["text"] = f"Крупный взлом! Теневой доход: +${shadow_gain:,.0f}."
            payload["news_title"] = "СМИ обсуждают цифровой скандал"
            payload["news_body"] = "В городе зафиксирован крупный подпольный цифровой инцидент."
            payload["news_severity"] = "high"
        return payload

    if code == "charity_drive":
        sponsor_back = random.randint(0, 2) == 2
        cashback = random.randint(200, 900) if sponsor_back else 0
        payload["balance_delta"] = -500 + cashback
        payload["rep_delta"] = 1.35
        payload["xp_delta"] = random.randint(12, 20)
        payload["text"] = (
            f"Вы пожертвовали $500 и получили рост репутации."
            + (f" Спонсор компенсировал ${cashback:,.0f}." if cashback > 0 else "")
        )
        if sponsor_back:
            payload["news_title"] = "Благотворительная акция набирает обороты"
            payload["news_body"] = "Игрок поддержал городской фонд и получил поддержку спонсоров."
            payload["news_severity"] = "normal"
        return payload

    if code == "street_race":
        roll = random.random()
        if roll < 0.46:
            payload["balance_delta"] = -700.0
            payload["rep_delta"] = -0.2
            payload["xp_delta"] = 7
            payload["text"] = "Гонка не задалась. Стартовый взнос потерян."
        elif roll < 0.9:
            win = random.randint(900, 2300)
            payload["balance_delta"] = float(win)
            payload["rep_delta"] = 0.16
            payload["xp_delta"] = random.randint(10, 17)
            payload["text"] = f"Вы финишировали в топе! Приз: ${win:,.0f}."
        else:
            win = random.randint(3500, 7000)
            payload["balance_delta"] = float(win)
            payload["rep_delta"] = 0.28
            payload["xp_delta"] = random.randint(18, 28)
            payload["text"] = f"Легендарный заезд! Суперприз: ${win:,.0f}."
            payload["news_title"] = "Ночная гонка завершилась сенсацией"
            payload["news_body"] = f"Игрок вырвал победу в уличной гонке и забрал ${win:,.0f}."
            payload["news_severity"] = "hot"
        return payload

    if code == "mystery_box":
        roll = random.random()
        if roll < 0.2:
            penalty = random.randint(300, 1100)
            payload["balance_delta"] = -float(penalty)
            payload["rep_delta"] = -0.12
            payload["xp_delta"] = random.randint(4, 10)
            payload["text"] = f"Ловушка в ящике. Потеряно: ${penalty:,.0f}."
        elif roll < 0.7:
            reward = random.randint(700, 2200)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.1
            payload["xp_delta"] = random.randint(8, 14)
            payload["text"] = f"Неплохой набор ресурсов. Доход: +${reward:,.0f}."
        else:
            reward = random.randint(3000, 8800)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.24
            payload["xp_delta"] = random.randint(14, 24)
            payload["text"] = f"Редкий дроп! Вы получили ${reward:,.0f}."
        return payload

    if code == "courier_rush":
        success_chance = min(0.9, 0.45 + education * 0.07)
        if random.random() <= success_chance:
            reward = random.randint(900, 2500)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.14
            payload["xp_delta"] = random.randint(10, 18)
            payload["text"] = f"Все доставки в срок. Оплата: +${reward:,.0f}."
        else:
            penalty = random.randint(280, 900)
            payload["balance_delta"] = -float(penalty)
            payload["rep_delta"] = -0.1
            payload["xp_delta"] = 6
            payload["text"] = f"Срыв маршрута и штраф: ${penalty:,.0f}."
        return payload

    if code == "photo_hunt":
        roll = random.random()
        if roll < 0.18:
            reward = random.randint(3800, 9200)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.36
            payload["xp_delta"] = random.randint(16, 26)
            payload["text"] = f"Вы поймали вирусный кадр! СМИ заплатили ${reward:,.0f}."
            payload["news_title"] = "Вирусный кадр игрока обсуждает весь город"
            payload["news_body"] = f"Редкий снимок принес автору ${reward:,.0f} и всплеск популярности."
            payload["news_severity"] = "hot"
        else:
            reward = random.randint(650, 2100)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.11
            payload["xp_delta"] = random.randint(8, 14)
            payload["text"] = f"Хорошая фотосерия продана редакции за ${reward:,.0f}."
        return payload

    if code == "city_festival":
        roll = random.random()
        if roll < 0.15:
            reward = random.randint(4500, 10500)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.52
            payload["xp_delta"] = random.randint(18, 30)
            payload["text"] = f"Вы стали хедлайнером фестиваля: +${reward:,.0f}."
            payload["news_title"] = "Фестиваль Мирнастана: новая звезда"
            payload["news_body"] = f"На городском фестивале игрок получил признание и доход ${reward:,.0f}."
            payload["news_severity"] = "hot"
        else:
            reward = random.randint(1000, 2800)
            payload["balance_delta"] = float(reward)
            payload["rep_delta"] = 0.2
            payload["xp_delta"] = random.randint(10, 18)
            payload["text"] = f"Фестиваль принес стабильный доход: +${reward:,.0f}."
        return payload

    return payload


async def _render_fun_hub(event: Message | CallbackQuery):
    user_id = int(event.from_user.id)
    user = await db.get_user(user_id) or {}
    focus_code = _fun_daily_focus_code(user_id)
    focus_cfg = FUN_ACTIVITY_MAP.get(focus_code, {})
    focus_cooldown = await db.get_user_cooldown_remaining(
        user_id,
        f"fun_lab_{focus_code}",
        int(focus_cfg.get("cooldown") or 1),
    )
    focus_state = "доступно" if focus_cooldown <= 0 else f"через {focus_cooldown} мин."
    lines = [
        "🎪 СЮЖЕТНОЕ СОБЫТИЕ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Баланс: ${float(user.get('balance') or 0):,.2f}",
        f"Репутация: {float(user.get('reputation') or 50):.2f}/100",
        f"Опыт: {int(user.get('experience') or 0)}",
        "",
        "Единый режим приключений с реальными решениями.",
        "Каждый запуск состоит из 2 этапов: тактика + ключевой выбор.",
        "",
        f"🎯 Событие дня: {focus_cfg.get('title', 'не определено')}",
        f"Статус события дня: {focus_state}",
        "",
    ]

    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🚀 Запустить событие дня", callback_data="fp_fun_start_daily")],
        [InlineKeyboardButton(text="🎲 Случайное событие", callback_data="fp_fun_start_random")],
        [
            InlineKeyboardButton(text="🧠 Как это работает", callback_data="fp_fun_guide"),
            InlineKeyboardButton(text="🎯 Цель дня", callback_data="fp_fun_daily"),
        ],
        [
            InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu"),
            InlineKeyboardButton(text="📰 СМИ", callback_data="media_news_menu"),
        ],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="fp_fun_hub")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.message(Command("fun"))
@router.callback_query(F.data == "fp_fun_hub")
async def feature_fun_hub_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.clear()
    await _render_fun_hub(event)


async def _start_fun_activity_session(callback: CallbackQuery, state: FSMContext, code: str) -> None:
    cfg = FUN_ACTIVITY_MAP.get(code)
    if not cfg:
        await callback.answer("❌ Неизвестное событие.", show_alert=True)
        return

    user_id = int(callback.from_user.id)
    user = await db.get_user(user_id) or {}
    if not user:
        await callback.answer("❌ Профиль не найден.", show_alert=True)
        return

    ok, fail_text = _fun_precheck(user, code)
    if not ok:
        await callback.answer(fail_text, show_alert=True)
        return

    story = FUN_ACTIVITY_STORY.get(code, {})
    secret = random.randint(1, 3)
    await state.update_data(
        fun_session={
            "code": code,
            "secret": secret,
            "strategy": "",
            "created_at": datetime.now().isoformat(),
        }
    )

    lines = [
        f"{cfg['title']}: этап 1/2",
        "━━━━━━━━━━━━━━━━━━━━",
        str(story.get("setup") or "Подготовка операции."),
        "",
        "Выберите тактику прохождения:",
    ]
    for strategy_key in ("safe", "balanced", "risky"):
        strategy = FUN_STRATEGY_CONFIG[strategy_key]
        lines.append(f"• {strategy['label']} — {strategy['description']}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛡 Осторожная", callback_data=f"fp_fun_strategy_{code}_safe"),
                InlineKeyboardButton(text="⚖️ Баланс", callback_data=f"fp_fun_strategy_{code}_balanced"),
            ],
            [InlineKeyboardButton(text="🔥 Агрессивная", callback_data=f"fp_fun_strategy_{code}_risky")],
            [InlineKeyboardButton(text="🎪 Назад к событиям", callback_data="fp_fun_hub")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "fp_fun_start_daily")
async def feature_fun_hub_start_daily(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    code = _fun_daily_focus_code(int(callback.from_user.id))
    await _start_fun_activity_session(callback, state, code)


@router.callback_query(F.data == "fp_fun_start_random")
async def feature_fun_hub_start_random(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    codes = [str(item.get("code") or "") for item in FUN_ACTIVITY_CONFIG if str(item.get("code") or "").strip()]
    if not codes:
        await callback.answer("❌ Список событий пуст.", show_alert=True)
        return
    code = random.choice(codes)
    await _start_fun_activity_session(callback, state, code)


@router.callback_query(F.data.startswith("fp_fun_act_"))
async def feature_fun_hub_action(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    code = (callback.data or "").replace("fp_fun_act_", "").strip().lower()
    await _start_fun_activity_session(callback, state, code)


@router.callback_query(F.data == "fp_fun_guide")
async def feature_fun_hub_guide(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lines = [
        "🧠 ТАКТИКИ ПРОХОЖДЕНИЯ",
        "━━━━━━━━━━━━━━━━━━━━",
        "Каждая активность теперь состоит из 2 этапов:",
        "1) Выбор тактики.",
        "2) Ключевое решение по сценарию.",
        "",
        "Профили тактик:",
        f"{FUN_STRATEGY_CONFIG['safe']['label']} — ниже риск, мягче штрафы.",
        f"{FUN_STRATEGY_CONFIG['balanced']['label']} — стандартные шансы.",
        f"{FUN_STRATEGY_CONFIG['risky']['label']} — высокий риск, высокий потенциал.",
        "",
        "Если на этапе 2 угадаете правильный ход, получите усиленный бонус.",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎪 К активностям", callback_data="fp_fun_hub")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "fp_fun_daily")
async def feature_fun_hub_daily_focus(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.from_user.id)
    code = _fun_daily_focus_code(user_id)
    cfg = FUN_ACTIVITY_MAP.get(code, {})
    today_key = datetime.now().strftime("%Y%m%d")
    remain = await db.get_user_cooldown_remaining(user_id, f"fun_focus_bonus_{today_key}", 24 * 60)
    focus_status = "доступен" if remain <= 0 else f"получен (повтор через {remain} мин.)"

    lines = [
        "🎯 ЦЕЛЬ ДНЯ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Сегодняшняя активность: {cfg.get('title', code)}",
        "Условие: пройдите ее и угадайте ключевое решение на этапе 2.",
        "Награда: дополнительный денежный бонус + опыт + репутация.",
        f"Статус бонуса: {focus_status}",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎪 К активностям", callback_data="fp_fun_hub")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_fun_strategy_"))
async def feature_fun_hub_pick_strategy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("fp_fun_strategy_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных тактики.", show_alert=True)
        return
    code, strategy_key = payload.rsplit("_", 1)
    if strategy_key not in FUN_STRATEGY_CONFIG:
        await callback.answer("❌ Неизвестная тактика.", show_alert=True)
        return
    if code not in FUN_ACTIVITY_MAP:
        await callback.answer("❌ Активность не найдена.", show_alert=True)
        return

    data = await state.get_data()
    session = data.get("fun_session") if isinstance(data, dict) else None
    if not isinstance(session, dict) or str(session.get("code")) != code:
        await callback.answer("⚠️ Сценарий устарел, запустите активность заново.", show_alert=True)
        await _render_fun_hub(callback)
        return

    session["strategy"] = strategy_key
    session["stage"] = "choice"
    await state.update_data(fun_session=session)

    story = FUN_ACTIVITY_STORY.get(code, {})
    options = list(story.get("options") or ["Вариант 1", "Вариант 2", "Вариант 3"])
    while len(options) < 3:
        options.append(f"Вариант {len(options) + 1}")

    lines = [
        f"{FUN_ACTIVITY_MAP[code]['title']}: этап 2/2",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Тактика: {FUN_STRATEGY_CONFIG[strategy_key]['label']}",
        "",
        str(story.get("decision") or "Выберите ключевой ход операции."),
    ]
    for idx, option in enumerate(options[:3], start=1):
        lines.append(f"{idx}) {option}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"1️⃣ {options[0]}", callback_data=f"fp_fun_choice_{code}_1")],
            [InlineKeyboardButton(text=f"2️⃣ {options[1]}", callback_data=f"fp_fun_choice_{code}_2")],
            [InlineKeyboardButton(text=f"3️⃣ {options[2]}", callback_data=f"fp_fun_choice_{code}_3")],
            [InlineKeyboardButton(text="↩️ Сменить тактику", callback_data=f"fp_fun_act_{code}")],
            [InlineKeyboardButton(text="🎪 К активностям", callback_data="fp_fun_hub")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_fun_choice_"))
async def feature_fun_hub_finish(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("fp_fun_choice_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка выбора.", show_alert=True)
        return
    code, choice_raw = payload.rsplit("_", 1)
    try:
        choice = int(choice_raw)
    except (TypeError, ValueError):
        await callback.answer("❌ Неверный выбор.", show_alert=True)
        return
    if choice not in {1, 2, 3}:
        await callback.answer("❌ Неверный выбор.", show_alert=True)
        return

    data = await state.get_data()
    session = data.get("fun_session") if isinstance(data, dict) else None
    if not isinstance(session, dict) or str(session.get("code")) != code:
        await callback.answer("⚠️ Сценарий устарел, запустите активность заново.", show_alert=True)
        await _render_fun_hub(callback)
        return

    strategy_key = str(session.get("strategy") or "")
    if strategy_key not in FUN_STRATEGY_CONFIG:
        await callback.answer("⚠️ Сначала выберите тактику.", show_alert=True)
        return
    secret = int(session.get("secret") or random.randint(1, 3))

    user_id = int(callback.from_user.id)
    user = await db.get_user(user_id) or {}
    if not user:
        await callback.answer("❌ Профиль не найден.", show_alert=True)
        return

    ok, fail_text = _fun_precheck(user, code)
    if not ok:
        await callback.answer(fail_text, show_alert=True)
        return

    cooldown_key = f"fun_lab_{code}"
    cfg = FUN_ACTIVITY_MAP.get(code, {})
    allowed, remain = await db.check_and_set_user_cooldown(user_id, cooldown_key, int(cfg.get("cooldown") or 1))
    if not allowed:
        await callback.answer(f"⏳ Доступно через {remain} мин.", show_alert=True)
        return

    outcome = _resolve_fun_activity_advanced(
        user=user,
        code=code,
        strategy_key=strategy_key,
        choice=choice,
        secret=secret,
    )

    focus_bonus = 0.0
    focus_code = _fun_daily_focus_code(user_id)
    if code == focus_code and bool(outcome.get("challenge_success")):
        focus_key = f"fun_focus_bonus_{datetime.now().strftime('%Y%m%d')}"
        allowed_focus, _ = await db.check_and_set_user_cooldown(user_id, focus_key, 24 * 60)
        if allowed_focus:
            focus_bonus = float(random.randint(900, 2600))
            outcome["balance_delta"] = round(float(outcome.get("balance_delta") or 0) + focus_bonus, 2)
            outcome["rep_delta"] = round(float(outcome.get("rep_delta") or 0) + 0.2, 2)
            outcome["xp_delta"] = int(outcome.get("xp_delta") or 0) + 8

    bal_before = float(user.get("balance") or 0)
    shadow_before = float(user.get("shadow_balance") or 0)
    rep_before = float(user.get("reputation") or 50)
    xp_before = int(user.get("experience") or 0)

    bal_delta = float(outcome.get("balance_delta") or 0)
    shadow_delta = float(outcome.get("shadow_delta") or 0)
    rep_delta = float(outcome.get("rep_delta") or 0)
    xp_delta = int(outcome.get("xp_delta") or 0)

    bal_after = round(max(0.0, bal_before + bal_delta), 2)
    shadow_after = round(max(0.0, shadow_before + shadow_delta), 2)
    rep_after = round(max(0.0, min(100.0, rep_before + rep_delta)), 2)
    xp_after = max(0, xp_before + xp_delta)

    await db.update_user(
        user_id,
        balance=bal_after,
        reputation=rep_after,
        experience=xp_after,
        shadow_balance=shadow_after,
    )
    await db.log_player_activity(
        user_id=user_id,
        activity_type=f"fun_{code}",
        details=(
            f"{str(outcome.get('text') or 'Активность выполнена.')} "
            f"[strategy={strategy_key}; choice={choice}; target={secret}]"
        ),
        value=round(bal_delta + shadow_delta, 2),
    )

    news_title = str(outcome.get("news_title") or "").strip()
    news_body = str(outcome.get("news_body") or "").strip()
    news_severity = str(outcome.get("news_severity") or "normal").strip().lower()
    if news_title and news_body:
        await db.create_media_news(
            title=news_title,
            body=news_body,
            source_user_id=user_id,
            severity=news_severity,
        )

    options = list(FUN_ACTIVITY_STORY.get(code, {}).get("options") or ["1", "2", "3"])
    picked = options[choice - 1] if choice - 1 < len(options) else str(choice)

    lines = [
        f"{cfg.get('title', code)}: результат",
        "━━━━━━━━━━━━━━━━━━━━",
        str(outcome.get("text") or "Готово."),
        "",
        f"Ваш выбор: {picked}",
        f"Точность решения: {'✅ Успех' if outcome.get('challenge_success') else '❌ Промах'}",
        "",
        f"Баланс: {_format_money_delta(bal_delta)}",
    ]
    if abs(shadow_delta) > 0:
        lines.append(f"Теневой баланс: {_format_money_delta(shadow_delta)}")
    lines.extend(
        [
            f"Репутация: {_format_rep_delta(rep_delta)}",
            f"Опыт: {_format_xp_delta(xp_delta)}",
        ]
    )
    if focus_bonus > 0:
        lines.append(f"🎯 Бонус цели дня: +${focus_bonus:,.2f}")
    lines.extend(
        [
            "",
            f"Личный кулдаун: {int(cfg.get('cooldown') or 1)} мин.",
            f"Текущий баланс: ${bal_after:,.2f}",
        ]
    )

    await state.update_data(fun_session={})

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎪 К событиям", callback_data="fp_fun_hub")],
            [
                InlineKeyboardButton(text="📰 СМИ", callback_data="media_news_menu"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main"),
            ],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


def _is_police_user(user: dict | None) -> bool:
    role = str((user or {}).get("role") or "").lower()
    org = str((user or {}).get("organization") or "").lower()
    return ("полиц" in role) or ("police" in role) or ("полиц" in org) or ("police" in org)


def _is_judge_user(user: dict | None) -> bool:
    role = str((user or {}).get("role") or "").lower()
    org = str((user or {}).get("organization") or "").lower()
    return ("суд" in role) or ("judge" in role) or ("court" in role) or ("суд" in org) or ("court" in org)


async def _can_use_police_tools(user_id: int, user: dict | None = None) -> bool:
    info = user or await db.get_user(user_id) or {}
    if _is_police_user(info):
        return True
    if await db.is_user_in_org_type(user_id, "police"):
        return True
    if await db.is_fbi_agent(user_id):
        return True
    return False


async def _can_use_fbi_tools(user_id: int, user: dict | None = None) -> bool:
    info = user or await db.get_user(user_id) or {}
    role = str(info.get("role") or "").lower()
    org = str(info.get("organization") or "").lower()
    if "fbi" in role or "фбр" in role or "fbi" in org or "фбр" in org:
        return True
    if await db.is_fbi_agent(user_id):
        return True
    if await db.is_user_in_org_type(user_id, "fbi"):
        return True
    authority = await db.get_government_authority(user_id)
    return authority in {"president", "vice_president", "minister"}


async def _is_judge_actor(user_id: int, user: dict | None = None) -> bool:
    info = user or await db.get_user(user_id) or {}
    if _is_judge_user(info):
        return True
    return await db.is_user_in_org_type(user_id, "court")


async def _can_manage_hr(user_id: int) -> bool:
    authority = await db.get_government_authority(user_id)
    return authority in {"president", "vice_president", "finance_minister", "minister"}


async def _render_business_menu(event: Message | CallbackQuery):
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    businesses = await db.list_user_businesses(user_id)
    text_lines = [
        "🏢 **БИЗНЕС И КАПИТАЛ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Баланс: ${float(user.get('balance') or 0):,.2f}",
        f"Ваших бизнесов: {len(businesses)}",
        "",
    ]
    if businesses:
        for idx, biz in enumerate(businesses[:5], start=1):
            text_lines.append(
                f"{idx}. {biz.get('name')} ({biz.get('type')}) — доход ${float(biz.get('income_daily') or 0):,.0f}/день"
            )
    else:
        text_lines.append("У вас пока нет бизнеса. Купите недвижимость и оформите объект под предприятие.")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆕 Открыть из недвижимости", callback_data="fp_business_create_start")],
            [InlineKeyboardButton(text="📊 Мои бизнесы", callback_data="fp_business_my")],
            [InlineKeyboardButton(text="🧩 Панель активов", callback_data="fp_assets_panel")],
            [InlineKeyboardButton(text="🧾 Налоговые отчеты", callback_data="fp_business_tax_reports")],
            [InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(text_lines), reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("biz"))
@router.callback_query(F.data == "biz_menu")
@router.callback_query(F.data == "create_business")
@router.callback_query(F.data == "my_businesses")
async def feature_business_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await state.clear()
    await _render_business_menu(event)


@router.message(Command("assets"))
@router.callback_query(F.data == "fp_assets_panel")
async def feature_assets_panel(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await state.clear()
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    businesses = await db.list_user_businesses(user_id)
    private_orgs = await db.list_private_orgs(limit=150)
    led_orgs = [org for org in private_orgs if int(org.get("leader_id") or 0) == int(user_id)]
    my_membership = await db.get_user_private_org_membership(user_id)

    total_biz_budget = sum(float(b.get("budget") or 0) for b in businesses)
    total_biz_income = sum(float(b.get("income_daily") or 0) for b in businesses)

    lines = [
        "🧩 **ПАНЕЛЬ АКТИВОВ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Игрок: {_md(_display_user(user))}",
        f"Личный баланс: ${float(user.get('balance') or 0):,.2f}",
        "",
        f"Бизнесов: {len(businesses)}",
        f"Суммарный бюджет бизнесов: ${total_biz_budget:,.2f}",
        f"Суммарный доход/день: ${total_biz_income:,.2f}",
        f"Организаций под вашим управлением: {len(led_orgs)}",
    ]
    if my_membership:
        lines.append(f"Ваше участие: {_md(str(my_membership.get('name') or 'частная организация'))}")

    keyboard_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📊 Мои бизнесы", callback_data="fp_business_my"),
            InlineKeyboardButton(text="🏢 Частные орг.", callback_data="private_org_list"),
        ],
        [InlineKeyboardButton(text="💼 Работа и доход", callback_data="work_menu")],
    ]
    for biz in businesses[:8]:
        biz_id = int(biz.get("id") or 0)
        if biz_id <= 0:
            continue
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"⚙️ Бизнес #{biz_id}: {str(biz.get('name') or 'без названия')[:22]}", callback_data=f"fp_business_open_{biz_id}")]
        )
    for org in led_orgs[:6]:
        org_id = int(org.get("id") or 0)
        if org_id <= 0:
            continue
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"🏢 Орг #{org_id}: {str(org.get('name') or 'без названия')[:24]}", callback_data=f"fp_private_org_open_{org_id}")]
        )
    if my_membership:
        member_org_id = int(my_membership.get("id") or 0)
        if member_org_id > 0 and member_org_id not in {int(o.get("id") or 0) for o in led_orgs}:
            keyboard_rows.append([InlineKeyboardButton(text="👥 Моя организация", callback_data=f"fp_private_org_open_{member_org_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "fp_business_my")
async def feature_business_my(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    businesses = await db.list_user_businesses(callback.from_user.id)
    if not businesses:
        await callback.message.edit_text(
            "📊 **МОИ БИЗНЕСЫ**\n━━━━━━━━━━━━━━━━━━━━\n\nСписок пуст.",
            reply_markup=_back("biz_menu"),
            parse_mode="Markdown",
        )
        return
    lines = ["📊 **МОИ БИЗНЕСЫ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for biz in businesses:
        biz_id = int(biz.get("id") or 0)
        lines.append(
            f"• **{_md(str(biz.get('name') or 'Без названия'))}** — {biz.get('type')}\n"
            f"  Доход/день: ${float(biz.get('income_daily') or 0):,.0f} | Расход/день: ${float(biz.get('expense_daily') or 0):,.0f}"
        )
        if biz_id > 0:
            keyboard_rows.append([InlineKeyboardButton(text=f"⚙️ Управлять #{biz_id}", callback_data=f"fp_business_open_{biz_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="biz_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_business_open_"))
async def feature_business_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_business_open_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректный бизнес.", show_alert=True)
        return
    business_id = int(raw_id)
    await _render_business_panel(callback.message, callback.from_user.id, business_id)


async def _render_business_panel(message: Message, owner_id: int, business_id: int) -> None:
    biz = await db.get_business_by_id(business_id)
    if not biz:
        await message.edit_text("❌ Бизнес не найден.", reply_markup=_back("fp_business_my"), parse_mode=None)
        return
    if int(biz.get("owner_id") or 0) != int(owner_id):
        await message.edit_text("❌ Только владелец может управлять бизнесом.", reply_markup=_back("fp_business_my"), parse_mode=None)
        return
    res = await db.get_business_resources(business_id)
    text = (
        f"🏢 Панель бизнеса: {biz.get('name')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Тип: {biz.get('type')}\n"
        f"Бюджет: ${float(biz.get('budget') or 0):,.2f}\n"
        f"Доход/день: ${float(biz.get('income_daily') or 0):,.2f}\n"
        f"Расход/день: ${float(biz.get('expense_daily') or 0):,.2f}\n"
        f"Оборудование: ур. {int(biz.get('equipment_level') or 1)}\n"
        f"Сырье: {float(res.get('raw_materials') or 0):,.1f} ед."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏗 Заказать сырье 100", callback_data=f"fp_business_raw_{business_id}_100")],
            [InlineKeyboardButton(text="🏗 Заказать сырье 500", callback_data=f"fp_business_raw_{business_id}_500")],
            [
                InlineKeyboardButton(text="⚙️ Производство", callback_data=f"fp_business_op_{business_id}_production"),
                InlineKeyboardButton(text="📣 Маркетинг", callback_data=f"fp_business_op_{business_id}_marketing"),
            ],
            [InlineKeyboardButton(text="📄 Контракт", callback_data=f"fp_business_op_{business_id}_contract")],
            [
                InlineKeyboardButton(text="💸 Вложить в бизнес", callback_data=f"fp_business_fund_in_{business_id}"),
                InlineKeyboardButton(text="💵 Вывести себе", callback_data=f"fp_business_fund_out_{business_id}"),
            ],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_business_open_{business_id}")],
            [InlineKeyboardButton(text="🔙 К списку", callback_data="fp_business_my")],
        ]
    )
    await message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_business_raw_"))
async def feature_business_order_raw(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 5 or not parts[3].isdigit() or not parts[4].isdigit():
        await callback.answer("Некорректный заказ сырья.", show_alert=True)
        return
    business_id = int(parts[3])
    amount = float(parts[4])
    ok, msg, payload = await db.order_business_raw_materials(
        owner_id=callback.from_user.id,
        business_id=business_id,
        amount=amount,
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    if ok and payload:
        await callback.message.answer(
            f"Объем: {float(payload.get('amount') or 0):,.1f} ед.\n"
            f"Сумма: ${float(payload.get('total_cost') or 0):,.2f}",
            parse_mode=None,
        )
    await _render_business_panel(callback.message, callback.from_user.id, business_id)


@router.callback_query(F.data.startswith("fp_business_op_"))
async def feature_business_operation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 5 or not parts[3].isdigit():
        await callback.answer("Некорректная операция.", show_alert=True)
        return
    business_id = int(parts[3])
    operation = parts[4]
    ok, msg, payload = await db.run_business_operation(
        owner_id=callback.from_user.id,
        business_id=business_id,
        operation=operation,
    )
    if not ok:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    else:
        payload = payload or {}
        await callback.message.answer(
            "✅ Операция бизнеса выполнена\n"
            f"Тип: {payload.get('operation')}\n"
            f"Δ Бюджет: ${float(payload.get('delta_budget') or 0):,.2f}\n"
            f"Новый бюджет: ${float(payload.get('new_budget') or 0):,.2f}\n"
            f"Сырья израсходовано: {float(payload.get('raw_consumed') or 0):,.1f}",
            parse_mode=None,
        )
    await _render_business_panel(callback.message, callback.from_user.id, business_id)


@router.callback_query(F.data.startswith("fp_business_fund_in_"))
async def feature_business_fund_in_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_business_fund_in_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректный бизнес.", show_alert=True)
        return
    business_id = int(raw_id)
    await state.set_state(FeatureStates.business_fund_amount)
    await state.update_data(business_fund_business_id=business_id, business_fund_direction="to_business")
    await callback.message.answer(
        "Введите сумму для перевода в бюджет бизнеса:",
        reply_markup=_back(f"fp_business_open_{business_id}", "🔙 Отмена"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_business_fund_out_"))
async def feature_business_fund_out_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_business_fund_out_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректный бизнес.", show_alert=True)
        return
    business_id = int(raw_id)
    await state.set_state(FeatureStates.business_fund_amount)
    await state.update_data(business_fund_business_id=business_id, business_fund_direction="to_owner")
    await callback.message.answer(
        "Введите сумму для вывода на личный счет:",
        reply_markup=_back(f"fp_business_open_{business_id}", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.business_fund_amount, F.text, ~F.text.startswith("/"))
async def feature_business_fund_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    business_id = int(data.get("business_fund_business_id") or 0)
    direction = str(data.get("business_fund_direction") or "")
    try:
        amount = float(str(message.text or "").replace("$", "").replace(" ", "").replace(",", "."))
    except ValueError:
        await message.answer("❌ Некорректная сумма.", reply_markup=_back(f"fp_business_open_{business_id}"))
        return
    await state.clear()
    ok, msg, payload = await db.transfer_business_funds(
        owner_id=message.from_user.id,
        business_id=business_id,
        amount=amount,
        direction=direction,
    )
    if not ok:
        await message.answer(f"❌ {msg}", reply_markup=_back(f"fp_business_open_{business_id}"))
        return
    payload = payload or {}
    await message.answer(
        "✅ Перевод выполнен\n"
        f"Сумма: ${float(payload.get('amount') or 0):,.2f}\n"
        f"Личный баланс: ${float(payload.get('owner_balance') or 0):,.2f}\n"
        f"Бюджет бизнеса: ${float(payload.get('business_budget') or 0):,.2f}",
        reply_markup=_back(f"fp_business_open_{business_id}"),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_business_create_start")
async def feature_business_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    props = await db.get_user_properties(callback.from_user.id)
    free_props = [p for p in props if int(p.get("has_business") or 0) == 0 and int(p.get("has_private_org") or 0) == 0]
    if not free_props:
        await callback.message.edit_text(
            "❌ Для открытия бизнеса нужен свободный объект недвижимости.\n"
            "Купите здание в разделе недвижимости.",
            reply_markup=_back("prop_menu", "🏠 К недвижимости"),
            parse_mode=None,
        )
        return
    keyboard = [
        [InlineKeyboardButton(text=f"🏗️ {p.get('name')} (${float(p.get('price') or 0):,.0f})", callback_data=f"fp_business_pickprop_{int(p['id'])}")]
        for p in free_props[:12]
    ]
    keyboard.append([InlineKeyboardButton(text="🔙 К бизнесу", callback_data="biz_menu")])
    await callback.message.edit_text(
        "🆕 Выберите объект недвижимости для запуска бизнеса:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_business_pickprop_"))
async def feature_business_pick_property(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    property_id_raw = callback.data.replace("fp_business_pickprop_", "")
    if not property_id_raw.isdigit():
        await callback.answer("Некорректный объект.", show_alert=True)
        return
    property_id = int(property_id_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍔 Ресторан", callback_data=f"fp_business_type_{property_id}_restaurant")],
            [InlineKeyboardButton(text="🛒 Магазин", callback_data=f"fp_business_type_{property_id}_shop")],
            [InlineKeyboardButton(text="🏭 Производство", callback_data=f"fp_business_type_{property_id}_factory")],
            [InlineKeyboardButton(text="🏨 Отель", callback_data=f"fp_business_type_{property_id}_hotel")],
            [InlineKeyboardButton(text="📡 Медиа", callback_data=f"fp_business_type_{property_id}_media")],
            [InlineKeyboardButton(text="💻 IT", callback_data=f"fp_business_type_{property_id}_it")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fp_business_create_start")],
        ]
    )
    await callback.message.edit_text("Выберите профиль бизнеса:", reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_business_type_"))
async def feature_business_select_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("Некорректный тип бизнеса.", show_alert=True)
        return
    property_id = parts[3]
    business_type = parts[4]
    if not property_id.isdigit():
        await callback.answer("Некорректный объект.", show_alert=True)
        return
    await state.set_state(FeatureStates.business_name)
    await state.update_data(fp_business_property_id=int(property_id), fp_business_type=business_type)
    await callback.message.answer(
        f"Введите название бизнеса ({business_type}):",
        reply_markup=_back("biz_menu", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.business_name, F.text, ~F.text.startswith("/"))
async def feature_business_name_input(message: Message, state: FSMContext):
    data = await state.get_data()
    property_id = int(data.get("fp_business_property_id") or 0)
    business_type = str(data.get("fp_business_type") or "service")
    if property_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия создания бизнеса устарела.", reply_markup=_back("biz_menu"))
        return
    success, msg, payload = await db.create_business_from_property(
        owner_id=message.from_user.id,
        property_id=property_id,
        name=message.text or "",
        business_type=business_type,
    )
    await state.clear()
    if not success:
        await message.answer(f"❌ {msg}", reply_markup=_back("biz_menu"))
        return
    await message.answer(
        "✅ Бизнес открыт!\n"
        f"ID: {payload.get('business_id')}\n"
        f"Регистрация: ${float(payload.get('registration_fee') or 0):,.2f}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📊 Мои бизнесы", callback_data="fp_business_my")],
                [InlineKeyboardButton(text="🔙 К бизнесу", callback_data="biz_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_business_tax_reports")
async def feature_business_tax_reports(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    is_tax_officer = await db.is_user_in_org_type(callback.from_user.id, "tax")
    reports = await db.get_latest_business_tax_reports(
        limit=20,
        owner_id=None if is_tax_officer else callback.from_user.id,
        unpaid_only=False,
    )
    lines = ["🧾 **НАЛОГОВЫЕ ОТЧЕТЫ БИЗНЕСОВ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not reports:
        lines.append("Отчетов пока нет.")
    else:
        for row in reports[:15]:
            created = str(row.get("created_at") or "")[:16]
            status = str(row.get("status") or "").upper()
            lines.append(
                f"[{created}] **{_md(str(row.get('business_name') or 'Бизнес'))}** "
                f"| {status} | налог ${float(row.get('tax_due') or 0):,.2f} "
                f"| оплачено ${float(row.get('tax_paid') or 0):,.2f}"
            )
            if row.get("note"):
                lines.append(f"↳ {_md(str(row.get('note')))}")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("biz_menu"),
        parse_mode="Markdown",
    )


async def _render_property_menu(event: Message | CallbackQuery):
    props = await db.get_user_properties(event.from_user.id)
    sender = _edit_or_answer(event)
    text = (
        "🏠 **НЕДВИЖИМОСТЬ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ваших объектов: {len(props)}\n"
        "Покупайте здания и оформляйте их под бизнесы или частные организации."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Каталог объектов", callback_data="property_catalog")],
            [InlineKeyboardButton(text="🏠 Мое имущество", callback_data="my_property")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    await sender(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("prop"))
@router.callback_query(F.data == "prop_menu")
async def feature_property_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await state.clear()
    await _render_property_menu(event)


@router.callback_query(F.data == "property_catalog")
async def feature_property_catalog(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    props = await db.list_properties(available_only=True, limit=14)
    if not props:
        await callback.message.edit_text(
            "🏠 **КАТАЛОГ НЕДВИЖИМОСТИ**\n━━━━━━━━━━━━━━━━━━━━\n\nСвободных объектов нет.",
            reply_markup=_back("prop_menu"),
            parse_mode="Markdown",
        )
        return
    lines = ["🏠 **КАТАЛОГ НЕДВИЖИМОСТИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    for prop in props:
        lines.append(
            f"• **{_md(str(prop.get('name')))}** — ${float(prop.get('price') or 0):,.0f}\n"
            f"  Локация: {_md(str(prop.get('location') or 'Неизвестно'))}"
        )
        keyboard_rows.append([InlineKeyboardButton(text=f"Купить #{int(prop['id'])}", callback_data=f"fp_buy_property_{int(prop['id'])}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="prop_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_buy_property_"))
async def feature_buy_property(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    property_id_raw = callback.data.replace("fp_buy_property_", "")
    if not property_id_raw.isdigit():
        await callback.answer("Некорректный объект.", show_alert=True)
        return
    success, msg, _ = await db.buy_property(callback.from_user.id, int(property_id_raw))
    await callback.message.answer(("✅ " if success else "❌ ") + msg, parse_mode=None)
    await feature_property_catalog(callback, state)


@router.callback_query(F.data == "my_property")
async def feature_my_property(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    props = await db.get_user_properties(callback.from_user.id)
    if not props:
        await callback.message.edit_text(
            "🏠 **МОЕ ИМУЩЕСТВО**\n━━━━━━━━━━━━━━━━━━━━\n\nУ вас пока нет недвижимости.",
            reply_markup=_back("prop_menu"),
            parse_mode="Markdown",
        )
        return

    lines = ["🏠 **МОЕ ИМУЩЕСТВО**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    for prop in props[:12]:
        lines.append(
            f"• **{_md(str(prop.get('name')))}** — ${float(prop.get('price') or 0):,.0f}\n"
            f"  Статус: {'занят' if int(prop.get('has_business') or 0) or int(prop.get('has_private_org') or 0) else 'свободен'}"
        )
        if int(prop.get("has_business") or 0) == 0 and int(prop.get("has_private_org") or 0) == 0:
            prop_id = int(prop["id"])
            keyboard_rows.append([InlineKeyboardButton(text=f"🏢 В частную орг #{prop_id}", callback_data=f"fp_convert_private_{prop_id}")])
            keyboard_rows.append([InlineKeyboardButton(text=f"🏪 В бизнес #{prop_id}", callback_data=f"fp_convert_business_{prop_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="prop_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_convert_business_"))
async def feature_convert_business(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    prop_id_raw = callback.data.replace("fp_convert_business_", "")
    if not prop_id_raw.isdigit():
        await callback.answer("Некорректный объект.", show_alert=True)
        return
    prop_id = int(prop_id_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍔 Ресторан", callback_data=f"fp_business_type_{prop_id}_restaurant")],
            [InlineKeyboardButton(text="🛒 Магазин", callback_data=f"fp_business_type_{prop_id}_shop")],
            [InlineKeyboardButton(text="🏭 Производство", callback_data=f"fp_business_type_{prop_id}_factory")],
            [InlineKeyboardButton(text="🏨 Отель", callback_data=f"fp_business_type_{prop_id}_hotel")],
            [InlineKeyboardButton(text="📡 Медиа", callback_data=f"fp_business_type_{prop_id}_media")],
            [InlineKeyboardButton(text="💻 IT", callback_data=f"fp_business_type_{prop_id}_it")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="my_property")],
        ]
    )
    await callback.message.edit_text("Выберите профиль бизнеса для объекта:", reply_markup=keyboard, parse_mode=None)


@router.message(Command("priv"))
@router.callback_query(F.data == "private_org_list")
async def feature_private_org_list(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    orgs = await db.list_private_orgs(limit=12)
    my_org = await db.get_user_private_org_membership(event.from_user.id)
    lines = ["🏢 **ЧАСТНЫЕ ОРГАНИЗАЦИИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if my_org:
        lines.append(
            f"Ваша организация: **{_md(str(my_org.get('name') or ''))}** "
            f"(роль: {_md(str(my_org.get('member_role') or 'Участник'))})"
        )
        lines.append("")
        keyboard_rows.append(
            [InlineKeyboardButton(text="🏢 Моя организация", callback_data=f"fp_private_org_open_{int(my_org['id'])}")]
        )

    if not orgs:
        lines.append("Пока нет частных организаций.")
    else:
        for org in orgs[:10]:
            lines.append(
                f"• **{_md(str(org.get('name')))}** | Лидер: {_md(str(org.get('leader_name') or 'Неизвестно'))}\n"
                f"  Бюджет: ${float(org.get('budget') or 0):,.0f}"
            )
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"Открыть #{int(org['id'])}", callback_data=f"fp_private_org_open_{int(org['id'])}")]
            )
    keyboard_rows.extend(
        [
            [InlineKeyboardButton(text="🆕 Создать частную организацию", callback_data="fp_private_org_create_start")],
            [InlineKeyboardButton(text="🧩 Панель активов", callback_data="fp_assets_panel")],
            [InlineKeyboardButton(text="🏠 Моя недвижимость", callback_data="my_property")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "fp_private_org_create_start")
async def feature_private_org_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    props = await db.get_user_properties(callback.from_user.id)
    free_props = [p for p in props if int(p.get("has_business") or 0) == 0 and int(p.get("has_private_org") or 0) == 0]
    if not free_props:
        await callback.message.edit_text(
            "❌ Нужен свободный объект недвижимости.\nКупите объект в разделе недвижимости.",
            reply_markup=_back("prop_menu", "🏠 К недвижимости"),
            parse_mode=None,
        )
        return
    keyboard = [
        [InlineKeyboardButton(text=f"🏢 {p.get('name')} (${float(p.get('price') or 0):,.0f})", callback_data=f"fp_private_org_pickprop_{int(p['id'])}")]
        for p in free_props[:12]
    ]
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="private_org_list")])
    await callback.message.edit_text(
        "Выберите объект для регистрации частной организации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_private_org_pickprop_"))
@router.callback_query(F.data.startswith("fp_convert_private_"))
async def feature_private_org_pick_property(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    prefix = "fp_private_org_pickprop_" if callback.data.startswith("fp_private_org_pickprop_") else "fp_convert_private_"
    prop_raw = callback.data.replace(prefix, "")
    if not prop_raw.isdigit():
        await callback.answer("Некорректный объект.", show_alert=True)
        return
    prop_id = int(prop_raw)
    await state.set_state(FeatureStates.private_org_name)
    await state.update_data(fp_private_org_property_id=prop_id)
    await callback.message.answer(
        "Введите название новой частной организации:",
        reply_markup=_back("private_org_list", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.private_org_name, F.text, ~F.text.startswith("/"))
async def feature_private_org_name_input(message: Message, state: FSMContext):
    data = await state.get_data()
    prop_id = int(data.get("fp_private_org_property_id") or 0)
    if prop_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия создания организации устарела.", reply_markup=_back("private_org_list"))
        return
    success, msg, payload = await db.create_private_org_from_property(
        leader_id=message.from_user.id,
        property_id=prop_id,
        name=message.text or "",
    )
    await state.clear()
    if not success:
        await message.answer(f"❌ {msg}", reply_markup=_back("private_org_list"))
        return
    await message.answer(
        "✅ Частная организация зарегистрирована.\n"
        f"ID: {payload.get('org_id')}\n"
        f"Регистрация: ${float(payload.get('registration_fee') or 0):,.2f}",
        reply_markup=_back("private_org_list"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_private_org_open_"))
async def feature_private_org_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_open_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    await _render_private_org_panel(callback.message, callback.from_user.id, org_id)


async def _render_private_org_panel(message: Message, user_id: int, org_id: int) -> None:
    org = await db.get_private_org_by_id(org_id)
    if not org:
        await message.edit_text("❌ Организация не найдена.", reply_markup=_back("private_org_list"), parse_mode=None)
        return

    membership = await db.get_user_private_org_membership(user_id)
    is_member = membership and int(membership.get("id") or 0) == org_id
    is_leader = int(org.get("leader_id") or 0) == int(user_id)
    members = await db.get_private_org_members(org_id, limit=200)
    resources = await db.get_private_org_resources(org_id)

    lines = [
        f"🏢 **{_md(str(org.get('name') or 'ЧАСТНАЯ ОРГАНИЗАЦИЯ'))}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Лидер: {_md(str(org.get('leader_name') or 'Неизвестно'))}",
        f"Участников: {len(members)}",
        f"Бюджет: ${float(org.get('budget') or 0):,.2f}",
        f"Объект: {_md(str(org.get('property_name') or 'не назначен'))}",
        f"Сырье на складе: {float(resources.get('raw_materials') or 0):,.1f} ед.",
    ]
    if is_member:
        lines.append(f"Ваша роль: {_md(str(membership.get('member_role') or 'Участник'))}")
    elif is_leader:
        lines.append("Вы лидер этой организации.")
    else:
        lines.append("Вы пока не состоите в организации.")

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if is_leader:
        keyboard_rows.append([InlineKeyboardButton(text="📨 Заявки", callback_data=f"fp_private_org_apps_{org_id}")])
        keyboard_rows.append([InlineKeyboardButton(text="👥 Участники", callback_data=f"fp_private_org_members_{org_id}")])
        keyboard_rows.append([InlineKeyboardButton(text="🏗 Заказать сырье", callback_data=f"fp_private_org_raw_menu_{org_id}")])
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="⚙️ Производство", callback_data=f"fp_private_org_op_{org_id}_production"),
                InlineKeyboardButton(text="📣 Кампания", callback_data=f"fp_private_org_op_{org_id}_campaign"),
            ]
        )
        keyboard_rows.append([InlineKeyboardButton(text="🛡 Аудит безопасности", callback_data=f"fp_private_org_op_{org_id}_security")])
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="💸 Внести в бюджет", callback_data=f"fp_private_org_fund_in_{org_id}"),
                InlineKeyboardButton(text="💵 Вывести себе", callback_data=f"fp_private_org_fund_out_{org_id}"),
            ]
        )
    elif is_member:
        keyboard_rows.append([InlineKeyboardButton(text="👥 Участники", callback_data=f"fp_private_org_members_{org_id}")])
    else:
        keyboard_rows.append([InlineKeyboardButton(text="📝 Подать заявление", callback_data=f"fp_private_org_apply_{org_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 К списку", callback_data="private_org_list")])
    await message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_private_org_members_"))
async def feature_private_org_members(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_members_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    org = await db.get_private_org_by_id(org_id)
    if not org:
        await callback.answer("Организация не найдена.", show_alert=True)
        return
    members = await db.get_private_org_members(org_id, limit=80)
    lines = [
        f"👥 **УЧАСТНИКИ: {_md(str(org.get('name') or ''))}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Всего: {len(members)}",
        "",
    ]
    if not members:
        lines.append("Участников пока нет.")
    else:
        for m in members[:40]:
            lines.append(
                f"• {_md(str(m.get('display_name') or m.get('user_id')))} — {_md(str(m.get('role') or 'Участник'))}"
            )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back(f"fp_private_org_open_{org_id}", "🔙 К организации"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_private_org_apply_"))
async def feature_private_org_apply_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_apply_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    org = await db.get_private_org_by_id(org_id)
    if not org:
        await callback.answer("Организация не найдена.", show_alert=True)
        return
    await state.set_state(FeatureStates.private_org_application_text)
    await state.update_data(private_org_apply_id=org_id)
    await callback.message.answer(
        f"📝 Заявление в **{_md(str(org.get('name') or 'организацию'))}**.\n"
        "Напишите коротко, почему вас должны принять:",
        reply_markup=_back(f"fp_private_org_open_{org_id}", "🔙 Отмена"),
        parse_mode="Markdown",
    )


@router.message(FeatureStates.private_org_application_text, F.text, ~F.text.startswith("/"))
async def feature_private_org_apply_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    org_id = int(data.get("private_org_apply_id") or 0)
    if org_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия заявления устарела.", reply_markup=_back("private_org_list"))
        return
    ok, msg, app_id = await db.apply_to_private_org(message.from_user.id, org_id, message.text or "")
    await state.clear()
    if not ok:
        await message.answer(f"❌ {msg}", reply_markup=_back(f"fp_private_org_open_{org_id}"))
        return
    await message.answer(
        f"✅ {msg}\nНомер заявления: #{int(app_id or 0)}",
        reply_markup=_back(f"fp_private_org_open_{org_id}"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_private_org_apps_"))
async def feature_private_org_apps(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_apps_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    org = await db.get_private_org_by_id(org_id)
    if not org:
        await callback.answer("Организация не найдена.", show_alert=True)
        return
    if int(org.get("leader_id") or 0) != callback.from_user.id:
        await callback.answer("Только лидер может смотреть заявления.", show_alert=True)
        return
    apps = await db.get_private_org_applications(org_id, status="pending", limit=30)
    lines = [
        f"📨 **ЗАЯВЛЕНИЯ: {_md(str(org.get('name') or ''))}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not apps:
        lines.append("Новых заявлений нет.")
    else:
        for app in apps[:12]:
            app_id = int(app.get("id") or 0)
            text = str(app.get("application_text") or "")
            if len(text) > 110:
                text = text[:107] + "..."
            lines.append(f"#{app_id} {_md(str(app.get('applicant_name') or app.get('user_id')))}")
            lines.append(_md(text) if text else "без текста")
            lines.append("")
            keyboard_rows.append(
                [
                    InlineKeyboardButton(text=f"✅ Принять #{app_id}", callback_data=f"fp_private_org_app_accept_{app_id}_{org_id}"),
                    InlineKeyboardButton(text=f"❌ Отклонить #{app_id}", callback_data=f"fp_private_org_app_reject_{app_id}_{org_id}"),
                ]
            )
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_private_org_apps_{org_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_private_org_open_{org_id}")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_private_org_app_accept_"))
@router.callback_query(F.data.startswith("fp_private_org_app_reject_"))
async def feature_private_org_app_decision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 7 or not parts[5].isdigit() or not parts[6].isdigit():
        await callback.answer("Некорректные данные заявления.", show_alert=True)
        return
    approve = parts[4] == "accept"
    app_id = int(parts[5])
    org_id = int(parts[6])
    ok, msg = await db.review_private_org_application(
        reviewer_id=callback.from_user.id,
        application_id=app_id,
        approve=approve,
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    org = await db.get_private_org_by_id(org_id)
    apps = await db.get_private_org_applications(org_id, status="pending", limit=30)
    lines = [
        f"📨 **ЗАЯВЛЕНИЯ: {_md(str((org or {}).get('name') or ''))}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not apps:
        lines.append("Новых заявлений нет.")
    else:
        for app in apps[:12]:
            aid = int(app.get("id") or 0)
            text = str(app.get("application_text") or "")
            if len(text) > 110:
                text = text[:107] + "..."
            lines.append(f"#{aid} {_md(str(app.get('applicant_name') or app.get('user_id')))}")
            lines.append(_md(text) if text else "без текста")
            lines.append("")
            keyboard_rows.append(
                [
                    InlineKeyboardButton(text=f"✅ Принять #{aid}", callback_data=f"fp_private_org_app_accept_{aid}_{org_id}"),
                    InlineKeyboardButton(text=f"❌ Отклонить #{aid}", callback_data=f"fp_private_org_app_reject_{aid}_{org_id}"),
                ]
            )
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_private_org_apps_{org_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_private_org_open_{org_id}")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_private_org_raw_menu_"))
async def feature_private_org_raw_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_raw_menu_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    org = await db.get_private_org_by_id(org_id)
    if not org:
        await callback.answer("Организация не найдена.", show_alert=True)
        return
    if int(org.get("leader_id") or 0) != callback.from_user.id:
        await callback.answer("Только лидер может закупать сырье.", show_alert=True)
        return
    resources = await db.get_private_org_resources(org_id)
    text = (
        f"🏗 Закупка сырья для {org.get('name')}\n"
        f"Текущий запас: {float(resources.get('raw_materials') or 0):,.1f} ед.\n"
        f"Бюджет организации: ${float(org.get('budget') or 0):,.2f}\n\n"
        "Цена: $115 за единицу."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить 100 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_100")],
            [InlineKeyboardButton(text="Купить 500 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_500")],
            [InlineKeyboardButton(text="Купить 1000 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_1000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_private_org_open_{org_id}")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_private_org_raw_buy_"))
async def feature_private_org_raw_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 7 or not parts[5].isdigit() or not parts[6].isdigit():
        await callback.answer("Некорректный заказ.", show_alert=True)
        return
    org_id = int(parts[5])
    amount = float(parts[6])
    ok, msg, payload = await db.order_private_org_raw_materials(
        leader_id=callback.from_user.id,
        org_id=org_id,
        amount=amount,
    )
    if not ok:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    else:
        payload = payload or {}
        await callback.message.answer(
            "✅ Сырье закуплено.\n"
            f"Объем: {float(payload.get('amount') or 0):,.1f} ед.\n"
            f"Сумма: ${float(payload.get('total_cost') or 0):,.2f}",
            parse_mode=None,
        )
    org = await db.get_private_org_by_id(org_id)
    resources = await db.get_private_org_resources(org_id)
    text = (
        f"🏗 Закупка сырья для {((org or {}).get('name') or 'организации')}\n"
        f"Текущий запас: {float(resources.get('raw_materials') or 0):,.1f} ед.\n"
        f"Бюджет организации: ${float((org or {}).get('budget') or 0):,.2f}\n\n"
        "Цена: $115 за единицу."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить 100 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_100")],
            [InlineKeyboardButton(text="Купить 500 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_500")],
            [InlineKeyboardButton(text="Купить 1000 ед.", callback_data=f"fp_private_org_raw_buy_{org_id}_1000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_private_org_open_{org_id}")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_private_org_op_"))
async def feature_private_org_operation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 6 or not parts[4].isdigit():
        await callback.answer("Некорректная операция.", show_alert=True)
        return
    org_id = int(parts[4])
    operation = parts[5]
    ok, msg, payload = await db.run_private_org_operation(
        leader_id=callback.from_user.id,
        org_id=org_id,
        operation=operation,
    )
    if not ok:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    else:
        payload = payload or {}
        await callback.message.answer(
            "✅ Операция выполнена\n"
            f"Тип: {payload.get('operation')}\n"
            f"Δ Бюджет: ${float(payload.get('delta_budget') or 0):,.2f}\n"
            f"Новый бюджет: ${float(payload.get('new_budget') or 0):,.2f}\n"
            f"Сырья израсходовано: {float(payload.get('raw_consumed') or 0):,.1f}",
            parse_mode=None,
        )
    await _render_private_org_panel(callback.message, callback.from_user.id, org_id)


@router.callback_query(F.data.startswith("fp_private_org_fund_in_"))
async def feature_private_org_fund_in_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_fund_in_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    await state.set_state(FeatureStates.private_org_fund_amount)
    await state.update_data(private_org_fund_org_id=org_id, private_org_fund_direction="to_org")
    await callback.message.answer(
        "Введите сумму для перевода в бюджет организации:",
        reply_markup=_back(f"fp_private_org_open_{org_id}", "🔙 Отмена"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_private_org_fund_out_"))
async def feature_private_org_fund_out_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw_id = callback.data.replace("fp_private_org_fund_out_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная организация.", show_alert=True)
        return
    org_id = int(raw_id)
    await state.set_state(FeatureStates.private_org_fund_amount)
    await state.update_data(private_org_fund_org_id=org_id, private_org_fund_direction="to_user")
    await callback.message.answer(
        "Введите сумму для вывода на личный счет лидера:",
        reply_markup=_back(f"fp_private_org_open_{org_id}", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.private_org_fund_amount, F.text, ~F.text.startswith("/"))
async def feature_private_org_fund_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    org_id = int(data.get("private_org_fund_org_id") or 0)
    direction = str(data.get("private_org_fund_direction") or "")
    try:
        amount = float(str(message.text or "").replace("$", "").replace(" ", "").replace(",", "."))
    except ValueError:
        await message.answer("❌ Некорректная сумма.", reply_markup=_back(f"fp_private_org_open_{org_id}"))
        return
    await state.clear()
    ok, msg, payload = await db.transfer_private_org_funds(
        leader_id=message.from_user.id,
        org_id=org_id,
        amount=amount,
        direction=direction,
    )
    if not ok:
        await message.answer(f"❌ {msg}", reply_markup=_back(f"fp_private_org_open_{org_id}"))
        return
    payload = payload or {}
    await message.answer(
        "✅ Перевод выполнен\n"
        f"Сумма: ${float(payload.get('amount') or 0):,.2f}\n"
        f"Личный баланс: ${float(payload.get('user_balance') or 0):,.2f}\n"
        f"Бюджет организации: ${float(payload.get('org_budget') or 0):,.2f}",
        reply_markup=_back(f"fp_private_org_open_{org_id}"),
        parse_mode=None,
    )


@router.message(Command("edu"))
@router.callback_query(F.data == "edu_menu")
async def feature_education_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await state.update_data(edu_quiz={})
    await db.ensure_education_program_catalog()
    status = await db.get_user_education_status(event.from_user.id)
    user = status.get("user") or {}
    active = status.get("active_enrollment")
    quick_test_remain = _edu_quick_test_cooldown_remaining(str(user.get("last_education_test_at") or ""))
    lines = [
        "🎓 ОБРАЗОВАНИЕ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Текущий уровень: {int(user.get('education') or 1)}",
        f"Завершенных программ: {int(status.get('completed_count') or 0)}",
        f"Быстрый тест: {'доступен' if quick_test_remain <= 0 else f'через {quick_test_remain} мин.'}",
        "",
        "Как пройти обучение:",
        "1) Сдать быстрый тест.",
        "2) Выбрать программу и поступить.",
        "3) Проходить сессии до завершения курса.",
        "",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if active:
        study_remain = _edu_study_cooldown_remaining(str(active.get("last_study_date") or ""))
        lines.extend(
            [
                f"Активная программа: {str(active.get('program_name') or '')}",
                f"Прогресс: {int(active.get('progress_days') or 0)}/{int(active.get('duration_days') or 1)} дней",
                f"Следующая сессия: {'доступна' if study_remain <= 0 else f'через {study_remain} мин.'}",
            ]
        )
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="📘 Теория-сессия", callback_data="fp_study_theory"),
                InlineKeyboardButton(text="🧪 Практикум", callback_data="fp_study_practice"),
            ]
        )
        keyboard_rows.append([InlineKeyboardButton(text="📝 Быстрый тест", callback_data="fp_edu_quick_test")])
        keyboard_rows.append([InlineKeyboardButton(text="📚 Программы", callback_data="view_education_programs")])
        keyboard_rows.append([InlineKeyboardButton(text="📈 Мой прогресс", callback_data="education_progress")])
    else:
        lines.append("Активной программы нет. Пройдите тест и поступайте на курс.")
        keyboard_rows.append([InlineKeyboardButton(text="📝 Быстрый тест", callback_data="fp_edu_quick_test")])
        keyboard_rows.append([InlineKeyboardButton(text="📚 Программы", callback_data="view_education_programs")])
        keyboard_rows.append([InlineKeyboardButton(text="📈 Мой прогресс", callback_data="education_progress")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])

    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows), parse_mode=None)


@router.callback_query(F.data == "view_education_programs")
async def feature_view_programs(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await db.ensure_education_program_catalog()
    status = await db.get_user_education_status(callback.from_user.id)
    active = status.get("active_enrollment") or {}
    active_program_id = int(active.get("program_id") or 0)
    programs = await db.list_education_programs(active_only=True, limit=15)
    lines = ["📚 ПРОГРАММЫ ОБУЧЕНИЯ", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for program in programs:
        pid = int(program.get("id") or 0)
        duration_days = int(program.get("duration_days") or 0)
        min_edu = int(program.get("min_education") or 1)
        min_rep = float(program.get("min_reputation") or 0)
        fee = float(program.get("tuition_fee") or 0)
        difficulty = min(5, max(1, 1 + duration_days // 3 + min_edu // 3))
        marker = " (АКТИВНА)" if active_program_id and pid == active_program_id else ""
        lines.append(
            f"• {str(program.get('name') or '')}{marker}\n"
            f"  Сложность: {difficulty}/5 | Длительность: {duration_days} дн.\n"
            f"  Цена: ${fee:,.0f} | Мин.уровень: {min_edu} | Мин.репутация: {min_rep:.1f}"
        )
        if not marker:
            keyboard_rows.append([InlineKeyboardButton(text=f"Поступить #{pid}", callback_data=f"fp_edu_enroll_{pid}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="edu_menu")])
    sender = _edit_or_answer(callback)
    await sender(
        "\n".join(lines) if programs else "Нет активных программ.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_edu_enroll_"))
async def feature_enroll_program(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    program_raw = callback.data.replace("fp_edu_enroll_", "")
    if not program_raw.isdigit():
        await callback.answer("Некорректная программа.", show_alert=True)
        return
    success, msg = await db.enroll_education_program(callback.from_user.id, int(program_raw), study_choice="theory")
    await callback.message.answer(("✅ " if success else "❌ ") + msg, parse_mode=None)
    await feature_education_menu(callback, state)


@router.callback_query(F.data == "education_progress")
async def feature_education_progress(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    status = await db.get_user_education_status(callback.from_user.id)
    active = status.get("active_enrollment")
    user = status.get("user") or {}
    lines = ["📈 МОЙ ПРОГРЕСС ОБУЧЕНИЯ", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not active:
        lines.append("Активного обучения нет.")
    else:
        study_remain = _edu_study_cooldown_remaining(str(active.get("last_study_date") or ""))
        lines.extend(
            [
                f"Программа: {str(active.get('program_name') or '')}",
                f"Дни прогресса: {int(active.get('progress_days') or 0)} / {int(active.get('duration_days') or 1)}",
                f"Последняя учеба: {str(active.get('last_study_date') or 'еще не было')[:16]}",
                f"Следующая сессия: {'доступна' if study_remain <= 0 else f'через {study_remain} мин.'}",
            ]
        )
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="📘 Теория-сессия", callback_data="fp_study_theory"),
                InlineKeyboardButton(text="🧪 Практикум", callback_data="fp_study_practice"),
            ]
        )
    lines.append("")
    quick_test_remain = _edu_quick_test_cooldown_remaining(str(user.get("last_education_test_at") or ""))
    lines.append(
        f"Быстрый тест: {'доступен' if quick_test_remain <= 0 else f'через {quick_test_remain} мин.'}"
    )
    keyboard_rows.append([InlineKeyboardButton(text="📝 Быстрый тест", callback_data="fp_edu_quick_test")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="edu_menu")])
    sender = _edit_or_answer(callback)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_edu_quick_test")
async def feature_education_quick_test(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    remain = _edu_quick_test_cooldown_remaining(str(user.get("last_education_test_at") or ""))
    if remain > 0:
        await callback.answer(f"⏳ Следующий тест через {remain} мин.", show_alert=True)
        return

    level = int(user.get("education") or 1)
    quiz_total = 5 if level <= 3 else (6 if level <= 7 else 7)
    question_indexes = await _edu_pick_question_indexes(
        user_id=callback.from_user.id,
        level=level,
        total=quiz_total,
    )
    if not question_indexes:
        await callback.answer("❌ Банк вопросов временно недоступен.", show_alert=True)
        return
    total = len(question_indexes)
    required = _edu_required_correct(level, total)
    avg_difficulty = round(
        sum(float((_edu_question_by_index(idx) or {}).get("difficulty") or 1) for idx in question_indexes) / total,
        2,
    )
    quiz_payload = {
        "questions": question_indexes,
        "cursor": 0,
        "score": 0,
        "required": required,
        "total": total,
        "avg_difficulty": avg_difficulty,
        "started_at": datetime.now().isoformat(),
    }
    await state.update_data(edu_quiz=quiz_payload)

    first_question = _edu_question_by_index(question_indexes[0]) or {}
    lines = _edu_format_question_lines(first_question, 1, total)
    lines.insert(3, f"Для зачета нужно: {required}/{total} правильных ответов")
    lines.insert(5, f"Ваш текущий уровень: {level}")
    sender = _edit_or_answer(callback)
    await sender(
        "\n".join(lines),
        reply_markup=_edu_keyboard_for_question(question_indexes[0]),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_edu_test_pick_"))
async def feature_education_quick_test_answer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    choice_raw = (callback.data or "").replace("fp_edu_test_pick_", "", 1)
    if not choice_raw.isdigit():
        await callback.answer("Некорректный ответ.", show_alert=True)
        return
    choice = int(choice_raw)

    data = await state.get_data()
    quiz = data.get("edu_quiz") if isinstance(data, dict) else None
    if not isinstance(quiz, dict):
        await callback.answer("Тест устарел. Запустите заново.", show_alert=True)
        return

    questions = list(quiz.get("questions") or [])
    cursor = int(quiz.get("cursor") or 0)
    score = int(quiz.get("score") or 0)
    required = int(quiz.get("required") or 3)
    total = int(quiz.get("total") or len(questions) or EDU_QUIZ_QUESTIONS_PER_RUN)
    avg_difficulty = float(quiz.get("avg_difficulty") or 1.0)

    if cursor < 0 or cursor >= len(questions):
        await state.update_data(edu_quiz={})
        await callback.answer("Сессия теста завершена. Запустите заново.", show_alert=True)
        return

    q_idx = int(questions[cursor])
    question = _edu_question_by_index(q_idx)
    if not question:
        await state.update_data(edu_quiz={})
        await callback.answer("Вопрос недоступен. Запустите тест заново.", show_alert=True)
        return

    options = list(question.get("options") or [])
    if choice < 0 or choice >= len(options):
        await callback.answer("Некорректный номер варианта.", show_alert=True)
        return

    correct_idx = int(question.get("correct") or 0)
    is_correct = choice == correct_idx
    if is_correct:
        score += 1

    next_cursor = cursor + 1
    if next_cursor < total:
        quiz["cursor"] = next_cursor
        quiz["score"] = score
        await state.update_data(edu_quiz=quiz)

        next_q_idx = int(questions[next_cursor])
        next_question = _edu_question_by_index(next_q_idx) or {}
        feedback = "✅ Верно." if is_correct else f"❌ Неверно. {str(question.get('explain') or '')}"
        lines = _edu_format_question_lines(next_question, next_cursor + 1, total)
        lines.insert(3, feedback)
        lines.insert(5, f"Счет: {score}/{next_cursor}. Для зачета нужно {required}/{total}")
        sender = _edit_or_answer(callback)
        await sender(
            "\n".join(lines),
            reply_markup=_edu_keyboard_for_question(next_q_idx),
            parse_mode=None,
        )
        return

    passed = score >= required
    ok, msg, payload = await db.complete_quick_education_test(
        callback.from_user.id,
        passed=passed,
        score=score,
        total_questions=total,
        difficulty=avg_difficulty,
    )
    used = await _edu_load_recent_question_ids(callback.from_user.id)
    combined = used + questions
    await _edu_save_recent_question_ids(callback.from_user.id, combined)
    await state.update_data(edu_quiz={})

    if not ok:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
        return
    payload = payload or {}
    grade = _edu_grade(score, total)
    summary_lines = [
        "🧾 РЕЗУЛЬТАТ ТЕСТА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Статус: {'✅ зачет' if passed else '❌ незачет'}",
        f"Оценка: {grade}",
        f"Баллы: {score}/{total}",
        f"Требовалось: {required}/{total}",
        f"Новый уровень: {payload.get('new_education')}",
        f"Награда: ${float(payload.get('reward') or 0):,.2f}",
        f"Сложность теста: {float(payload.get('difficulty') or avg_difficulty):.2f}/5",
        f"Следующий тест через {int(payload.get('cooldown_minutes') or EDU_TEST_COOLDOWN_MINUTES)} мин.",
    ]
    sender = _edit_or_answer(callback)
    await sender(
        "\n".join(summary_lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎓 К обучению", callback_data="edu_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data.in_({"fp_study_theory", "fp_study_practice"}))
async def feature_study_session(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mode = "practice" if callback.data.endswith("practice") else "theory"
    success, msg, payload = await db.study_education_session(callback.from_user.id, mode=mode)
    if not success:
        cooldown_min = int((payload or {}).get("cooldown_minutes") or 0)
        suffix = f"\nОсталось ждать: {cooldown_min} мин." if cooldown_min > 0 else ""
        await callback.message.answer(f"❌ {msg}{suffix}", parse_mode=None)
        return
    payload = payload or {}
    mode_label = "Практикум" if mode == "practice" else "Теория"
    await callback.message.answer(
        f"✅ {msg}\n"
        f"Режим: {mode_label}\n"
        f"Программа: {payload.get('program_name')}\n"
        f"Прогресс: {payload.get('progress_days')}/{payload.get('duration_days')}\n"
        f"Завершено: {'Да' if payload.get('completed') else 'Нет'}\n"
        f"Новый уровень: {payload.get('new_education')}",
        parse_mode=None,
    )
    await feature_education_menu(callback, state)


@router.message(Command("work"))
@router.callback_query(F.data == "work_menu")
async def feature_work_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await state.clear()
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    pending = await db.get_user_pending_job_application(user_id)
    task_status = await db.get_user_job_task_status(user_id)
    active_task = task_status.get("active_task")
    lines = [
        "💼 **РАБОТА И ПОДРАБОТКИ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Текущая работа: {_md(str(user.get('citizen_job') or 'нет'))}",
        f"Зарплата: ${float(user.get('citizen_salary') or 0):,.0f}/день",
        "",
        "Трудоустройство идет через HR-заявление.",
    ]
    if pending:
        lines.append(
            f"📨 Активная HR-заявка: #{int(pending.get('id') or 0)} ({pending.get('job_title')})"
        )
    if active_task:
        lines.append(
            f"🎯 Цель работы: {int(active_task.get('progress') or 0)}/{int(active_task.get('goal') or 1)} смен"
        )
    lines.append("")
    lines.append("Подработки доступны отдельно и с личным кулдауном для каждого игрока.")

    keyboard_rows = [
        [InlineKeyboardButton(text="📋 Вакансии", callback_data="view_citizen_jobs")],
        [InlineKeyboardButton(text="🛠 Отработать смену", callback_data="work_shift")],
        [InlineKeyboardButton(text="💼 Мой статус", callback_data="citizen_work_status")],
        [InlineKeyboardButton(text="⚡ Микроподработки", callback_data="fp_microjob_menu")],
        [InlineKeyboardButton(text="🎯 Подработки", callback_data="side_hustle_menu")],
    ]
    if pending:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="⏱ Авто-решение HR", callback_data="fp_job_auto_review"),
                InlineKeyboardButton(text="🗑 Отозвать заявку", callback_data="fp_job_cancel_pending"),
            ]
        )
    if await _can_manage_hr(user_id):
        keyboard_rows.append([InlineKeyboardButton(text="🧾 Отдел кадров", callback_data="work_hr")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=keyboard_rows
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "view_citizen_jobs")
async def feature_view_citizen_jobs(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    pending = await db.get_user_pending_job_application(callback.from_user.id)
    jobs = db.list_citizen_jobs()
    lines = ["📋 **АКТУАЛЬНЫЕ ВАКАНСИИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    can_apply = (not user.get("citizen_job")) and (pending is None)
    for job in jobs:
        lines.append(
            f"• **{_md(str(job['title']))}** — ${float(job['salary']):,.0f}/день\n"
            f"  Требования: 🎓 {int(job['edu_required'])}+ | ⭐ {float(job['rep_required']):.1f}+"
        )
        lines.append(f"  {_md(str(job['description']))}")
        lines.append("")
        if can_apply:
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"📝 Заявление: {job['title']}", callback_data=f"fp_job_apply_{job['code']}")]
            )

    if user.get("citizen_job"):
        lines.append(f"⚠️ Вы уже работаете: {user.get('citizen_job')}. Сначала увольнение/перевод через HR.")
    elif pending:
        lines.append(f"📨 У вас уже есть активная заявка #{int(pending.get('id') or 0)}.")
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="⏱ Авто-решение HR", callback_data="fp_job_auto_review"),
                InlineKeyboardButton(text="🗑 Отозвать", callback_data="fp_job_cancel_pending"),
            ]
        )
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_job_apply_"))
async def feature_job_apply_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    job_code = callback.data.replace("fp_job_apply_", "")
    job = db.get_citizen_job(job_code)
    if not job:
        await callback.answer("Вакансия не найдена.", show_alert=True)
        return
    user = await db.get_user(callback.from_user.id) or {}
    if user.get("citizen_job"):
        await callback.answer("Вы уже трудоустроены.", show_alert=True)
        return
    pending = await db.get_user_pending_job_application(callback.from_user.id)
    if pending:
        await callback.answer("У вас уже есть активная HR-заявка.", show_alert=True)
        return
    await state.set_state(FeatureStates.job_application_text)
    await state.update_data(work_apply_job_code=job_code)
    await callback.message.answer(
        f"📝 HR-заявление на должность **{_md(str(job['title']))}**.\n"
        "Опишите ваш опыт и почему вас стоит нанять:",
        reply_markup=_back("view_citizen_jobs", "🔙 Отмена"),
        parse_mode="Markdown",
    )


@router.message(FeatureStates.job_application_text, F.text, ~F.text.startswith("/"))
async def feature_job_apply_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    job_code = str(data.get("work_apply_job_code") or "")
    if not job_code:
        await state.clear()
        await message.answer("❌ Сессия заявления устарела.", reply_markup=_back("work_menu"))
        return
    ok, msg, app_id = await db.apply_for_citizen_job(
        user_id=message.from_user.id,
        job_code=job_code,
        application_text=message.text or "",
    )
    await state.clear()
    if not ok:
        await message.answer(f"❌ {msg}", reply_markup=_back("view_citizen_jobs"))
        return
    await message.answer(
        f"✅ {msg}\nНомер заявки: #{int(app_id or 0)}",
        reply_markup=_back("work_menu", "🔙 К работе"),
        parse_mode=None,
    )


@router.callback_query(F.data == "citizen_work_status")
async def feature_citizen_work_status(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    pending = await db.get_user_pending_job_application(callback.from_user.id)
    task_info = await db.get_user_job_task_status(callback.from_user.id)
    active_task = task_info.get("active_task")
    lines = [
        "💼 **МОЙ РАБОЧИЙ СТАТУС**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Должность: {_md(str(user.get('citizen_job') or 'нет'))}",
        f"Оклад: ${float(user.get('citizen_salary') or 0):,.2f}/день",
        f"Последняя смена: {str(user.get('last_job_shift') or '—')[:16]}",
    ]
    if pending:
        lines.append(f"HR-заявка: #{int(pending.get('id') or 0)} ({pending.get('job_title')})")
    if active_task:
        lines.append(
            f"🎯 Цель: {int(active_task.get('progress') or 0)}/{int(active_task.get('goal') or 1)} смен"
        )
        lines.append(f"Премия цели: ${float(active_task.get('reward') or 0):,.0f}")
    keyboard_rows = [
        [InlineKeyboardButton(text="🛠 Отработать смену", callback_data="work_shift")],
        [InlineKeyboardButton(text="⚡ Микроподработки", callback_data="fp_microjob_menu")],
    ]
    if pending:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="⏱ Авто-решение HR", callback_data="fp_job_auto_review"),
                InlineKeyboardButton(text="🗑 Отозвать", callback_data="fp_job_cancel_pending"),
            ]
        )
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "fp_job_cancel_pending")
async def feature_job_cancel_pending(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ok, msg = await db.cancel_user_pending_job_application(callback.from_user.id)
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await feature_work_menu(callback, state)


@router.callback_query(F.data == "fp_job_auto_review")
async def feature_job_auto_review(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ok, msg, payload = await db.auto_review_user_job_application(
        user_id=callback.from_user.id,
        min_wait_minutes=0,
    )
    payload = payload or {}
    if ok:
        if payload.get("approved"):
            await callback.message.answer(
                f"✅ {msg}\nВас приняли на должность: {payload.get('job_title')}",
                parse_mode=None,
            )
        else:
            await callback.message.answer(("✅ " if msg else "") + msg, parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await feature_work_menu(callback, state)


@router.callback_query(F.data == "work_shift")
async def feature_work_shift(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ok, msg, payload = await db.work_citizen_shift(callback.from_user.id)
    if not ok:
        await callback.message.edit_text(
            f"❌ {msg}",
            reply_markup=_back("work_menu"),
            parse_mode=None,
        )
        return
    payload = payload or {}
    lines = [
        "✅ СМЕНА ЗАВЕРШЕНА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Должность: {payload.get('job_title')}",
        f"Выплата за смену: ${float(payload.get('payout') or 0):,.2f}",
        f"Премия за цель: ${float(payload.get('bonus_reward') or 0):,.2f}",
        f"Текущий баланс: ${float(payload.get('new_balance') or 0):,.2f}",
        f"Цель: {int(payload.get('task_progress') or 0)}/{int(payload.get('task_goal') or 1)} смен",
        f"Личный кулдаун: {int(payload.get('cooldown_minutes') or 0)} мин.",
    ]
    if payload.get("next_task_goal"):
        lines.append(f"🎯 Новая цель открыта: {int(payload.get('next_task_goal') or 0)} смен.")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💼 Мой статус", callback_data="citizen_work_status")],
                [InlineKeyboardButton(text="🔙 К работе", callback_data="work_menu")],
            ]
        ),
        parse_mode=None,
    )


async def _render_hr_panel(message: Message, reviewer_id: int) -> None:
    apps = await db.get_pending_job_applications(limit=20)
    lines = ["🧾 **ОТДЕЛ КАДРОВ: ЗАЯВКИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not apps:
        lines.append("Новых заявок нет.")
    else:
        for app in apps[:12]:
            app_id = int(app.get("id") or 0)
            text = str(app.get("application_text") or "")
            if len(text) > 110:
                text = text[:107] + "..."
            lines.append(
                f"#{app_id} {_md(str(app.get('applicant_name') or app.get('user_id')))}\n"
                f"Вакансия: {_md(str(app.get('job_title') or '—'))}\n"
                f"🎓 {int(app.get('education') or 1)} | ⭐ {float(app.get('reputation') or 0):.1f}"
            )
            lines.append(_md(text) if text else "без текста")
            lines.append("")
            keyboard_rows.append(
                [
                    InlineKeyboardButton(text=f"✅ Одобрить #{app_id}", callback_data=f"fp_job_hr_accept_{app_id}"),
                    InlineKeyboardButton(text=f"❌ Отклонить #{app_id}", callback_data=f"fp_job_hr_reject_{app_id}"),
                ]
            )
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="work_hr")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 К работе", callback_data="work_menu")])
    await message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "work_hr")
async def feature_work_hr(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not await _can_manage_hr(callback.from_user.id):
        await callback.answer("Доступ только для правительства.", show_alert=True)
        return
    await _render_hr_panel(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("fp_job_hr_accept_"))
@router.callback_query(F.data.startswith("fp_job_hr_reject_"))
async def feature_work_hr_decision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not await _can_manage_hr(callback.from_user.id):
        await callback.answer("Доступ только для правительства.", show_alert=True)
        return
    approve = callback.data.startswith("fp_job_hr_accept_")
    raw_id = callback.data.replace("fp_job_hr_accept_", "").replace("fp_job_hr_reject_", "")
    if not raw_id.isdigit():
        await callback.answer("Некорректная заявка.", show_alert=True)
        return
    ok, msg, target_user_id = await db.process_job_application(
        application_id=int(raw_id),
        reviewer_id=callback.from_user.id,
        approve=approve,
        note="Решение отдела кадров",
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    if ok and target_user_id:
        try:
            await callback.bot.send_message(
                int(target_user_id),
                (
                    "📨 Решение по HR-заявке:\n"
                    f"{'✅ Одобрено' if approve else '❌ Отклонено'}\n"
                    f"{msg}"
                ),
                parse_mode=None,
            )
        except Exception:
            pass
    await _render_hr_panel(callback.message, callback.from_user.id)


@router.callback_query(F.data == "side_hustle_menu")
async def feature_side_hustle_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    text = (
        "🎯 **ПОДРАБОТКИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Легальные и нелегальные способы дохода.\n"
        "Перед началом выбери направление."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Микроподработки", callback_data="fp_microjob_menu")],
            [InlineKeyboardButton(text="✅ Легальная подработка", callback_data="fp_hustle_start_legal")],
            [InlineKeyboardButton(text="🕶️ Нелегальная подработка", callback_data="fp_hustle_start_illegal")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.in_({"fp_hustle_start_legal", "fp_hustle_start_illegal"}))
async def feature_hustle_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    hustle_type = "legal" if callback.data == "fp_hustle_start_legal" else "illegal"
    legal_variants = ["courier", "freelance", "auction"]
    illegal_variants = ["night_drop", "ghost_trade", "crypto_launder"]
    variant = random.choice(legal_variants if hustle_type == "legal" else illegal_variants)
    secret = random.randint(1, 3)

    await state.set_state(FeatureStates.hustle_guess)
    await state.update_data(hustle_type=hustle_type, hustle_variant=variant, hustle_secret=secret)
    text = (
        "🎮 **МИНИ-ИГРА ПОДРАБОТКИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выбери один из трех кейсов. Один кейс дает лучший результат."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧰 Кейс 1", callback_data="fp_hustle_guess_1"),
                InlineKeyboardButton(text="🧰 Кейс 2", callback_data="fp_hustle_guess_2"),
                InlineKeyboardButton(text="🧰 Кейс 3", callback_data="fp_hustle_guess_3"),
            ],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="side_hustle_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "fp_microjob_menu")
async def feature_microjob_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    text = (
        "⚡ **МИКРОПОДРАБОТКИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Быстрые задания с отдельными кулдаунами на каждый тип.\n"
        "Кулдауны персональные: один игрок не блокирует другого."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Курьер", callback_data="fp_microjob_courier"),
                InlineKeyboardButton(text="🚕 Такси", callback_data="fp_microjob_taxi"),
            ],
            [
                InlineKeyboardButton(text="🔧 Ремонт", callback_data="fp_microjob_repair"),
                InlineKeyboardButton(text="💻 Фриланс", callback_data="fp_microjob_freelance"),
            ],
            [
                InlineKeyboardButton(text="🛍 Уличная торговля", callback_data="fp_microjob_street_trade"),
                InlineKeyboardButton(text="⚡ Экспресс-доставка", callback_data="fp_microjob_delivery_plus"),
            ],
            [
                InlineKeyboardButton(text="📦 Склад", callback_data="fp_microjob_warehouse"),
                InlineKeyboardButton(text="🎥 Стрим", callback_data="fp_microjob_stream"),
            ],
            [InlineKeyboardButton(text="🧑‍💼 Ассистент", callback_data="fp_microjob_assistant")],
            [InlineKeyboardButton(text="🎯 К большим подработкам", callback_data="side_hustle_menu")],
            [InlineKeyboardButton(text="🔙 К работе", callback_data="work_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("fp_microjob_"))
async def feature_microjob_run(callback: CallbackQuery, state: FSMContext):
    job_key = callback.data.replace("fp_microjob_", "")
    if job_key == "menu":
        await callback.answer("Откройте список микроподработок кнопкой меню.", show_alert=True)
        return
    await callback.answer()

    ok, msg, payload = await db.run_microjob(callback.from_user.id, job_key)
    if not ok:
        await callback.message.edit_text(
            f"❌ {msg}",
            reply_markup=_back("fp_microjob_menu", "🔙 К микроподработкам"),
            parse_mode=None,
        )
        return

    payload = payload or {}
    await callback.message.edit_text(
        "✅ Микроподработка выполнена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Задача: {payload.get('job_title')}\n"
        f"Выплата: ${float(payload.get('payout') or 0):,.2f}\n"
        f"Критический успех: {'Да' if payload.get('critical') else 'Нет'}\n"
        f"Баланс: ${float(payload.get('new_balance') or 0):,.2f}\n"
        f"Кулдаун этого задания: {int(payload.get('cooldown_minutes') or 0)} мин.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚡ Еще микроподработка", callback_data="fp_microjob_menu")],
                [InlineKeyboardButton(text="🎯 Подработки", callback_data="side_hustle_menu")],
                [InlineKeyboardButton(text="🔙 К работе", callback_data="work_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_hustle_guess_"))
async def feature_hustle_guess(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    guess_raw = callback.data.replace("fp_hustle_guess_", "")
    if not guess_raw.isdigit():
        await callback.answer("Некорректный выбор.", show_alert=True)
        return
    data = await state.get_data()
    hustle_type = str(data.get("hustle_type") or "")
    variant = str(data.get("hustle_variant") or "")
    secret = int(data.get("hustle_secret") or 0)
    guess = int(guess_raw)
    if hustle_type not in {"legal", "illegal"}:
        await state.clear()
        await callback.answer("Сессия устарела.", show_alert=True)
        return
    success, msg, payload = await db.run_side_hustle(
        user_id=callback.from_user.id,
        hustle_type=hustle_type,
        variant=variant,
        mini_success=(guess == secret),
    )
    await state.clear()
    if not success:
        await callback.message.edit_text(
            f"❌ {msg}",
            reply_markup=_back("side_hustle_menu"),
            parse_mode=None,
        )
        return
    payload = payload or {}
    text = (
        "✅ Подработка завершена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Тип: {'Легальная' if payload.get('hustle_type') == 'legal' else 'Нелегальная'}\n"
        f"Сценарий: {payload.get('variant')}\n"
        f"Результат: {payload.get('result')}\n"
        f"Выплата: ${float(payload.get('payout') or 0):,.2f}\n"
        f"Риск: {int(payload.get('risk') or 0)}/100\n"
        f"Новый баланс: ${float(payload.get('new_balance') or 0):,.2f}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Еще подработка", callback_data="side_hustle_menu")],
                [InlineKeyboardButton(text="🔙 В работу", callback_data="work_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.message(Command("casino"))
@router.callback_query(F.data == "casino_menu")
async def feature_casino_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    casinos = await db.list_casinos(limit=12)
    lines = ["🎰 **КАЗИНО**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not casinos:
        lines.append("Казино пока не зарегистрированы.")
    else:
        for c in casinos:
            lines.append(
                f"• **{_md(str(c.get('name')))}** ({c.get('casino_type')})\n"
                f"  Лимиты: ${float(c.get('min_bet') or 0):,.0f} - ${float(c.get('max_bet') or 0):,.0f}"
            )
    keyboard_rows = [
        [InlineKeyboardButton(text=f"Открыть #{int(c['id'])}", callback_data=f"fp_casino_open_{int(c['id'])}")]
        for c in casinos[:10]
    ]
    keyboard_rows.append([InlineKeyboardButton(text="🆕 Открыть частное казино", callback_data="fp_casino_create")])
    keyboard_rows.append([InlineKeyboardButton(text="📜 Моя история игр", callback_data="fp_casino_history")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "fp_casino_create")
async def feature_casino_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FeatureStates.private_casino_name)
    await callback.message.answer(
        "Введите название частного казино:",
        reply_markup=_back("casino_menu", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.private_casino_name, F.text, ~F.text.startswith("/"))
async def feature_casino_name_input(message: Message, state: FSMContext):
    success, msg, payload = await db.create_private_casino(
        owner_id=message.from_user.id,
        name=message.text or "",
    )
    await state.clear()
    if not success:
        await message.answer(f"❌ {msg}", reply_markup=_back("casino_menu"))
        return
    await message.answer(
        "✅ Частное казино открыто.\n"
        f"ID: {payload.get('casino_id')}\n"
        f"Регистрация: ${float(payload.get('registration_fee') or 0):,.2f}",
        reply_markup=_back("casino_menu"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_casino_open_"))
async def feature_casino_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    casino_raw = callback.data.replace("fp_casino_open_", "")
    if not casino_raw.isdigit():
        await callback.answer("Некорректное казино.", show_alert=True)
        return
    casino_id = int(casino_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪙 Монетка", callback_data=f"fp_casino_coin_{casino_id}")],
            [InlineKeyboardButton(text="🎲 Кубик", callback_data=f"fp_casino_dice_{casino_id}")],
            [InlineKeyboardButton(text="🎰 Слоты $5k", callback_data=f"fp_casino_play_{casino_id}_slots_none_5000")],
            [InlineKeyboardButton(text="🎰 Слоты $20k", callback_data=f"fp_casino_play_{casino_id}_slots_none_20000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="casino_menu")],
        ]
    )
    await callback.message.edit_text("Выберите игру и ставку:", reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_casino_coin_"))
async def feature_casino_coin_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cid_raw = callback.data.replace("fp_casino_coin_", "")
    if not cid_raw.isdigit():
        await callback.answer("Некорректное казино.", show_alert=True)
        return
    cid = int(cid_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Орел $5k", callback_data=f"fp_casino_play_{cid}_coin_heads_5000")],
            [InlineKeyboardButton(text="Решка $5k", callback_data=f"fp_casino_play_{cid}_coin_tails_5000")],
            [InlineKeyboardButton(text="Орел $20k", callback_data=f"fp_casino_play_{cid}_coin_heads_20000")],
            [InlineKeyboardButton(text="Решка $20k", callback_data=f"fp_casino_play_{cid}_coin_tails_20000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_casino_open_{cid}")],
        ]
    )
    await callback.message.edit_text("Монетка: выберите исход и ставку.", reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_casino_dice_"))
async def feature_casino_dice_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    cid_raw = callback.data.replace("fp_casino_dice_", "")
    if not cid_raw.isdigit():
        await callback.answer("Некорректное казино.", show_alert=True)
        return
    cid = int(cid_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="High (4-6) $5k", callback_data=f"fp_casino_play_{cid}_dice_high_5000")],
            [InlineKeyboardButton(text="Low (1-3) $5k", callback_data=f"fp_casino_play_{cid}_dice_low_5000")],
            [InlineKeyboardButton(text="High (4-6) $20k", callback_data=f"fp_casino_play_{cid}_dice_high_20000")],
            [InlineKeyboardButton(text="Low (1-3) $20k", callback_data=f"fp_casino_play_{cid}_dice_low_20000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_casino_open_{cid}")],
        ]
    )
    await callback.message.edit_text("Кубик: выберите исход и ставку.", reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_casino_play_"))
async def feature_casino_play(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) < 7:
        await callback.answer("Некорректная ставка.", show_alert=True)
        return
    cid_raw, game, prediction, bet_raw = parts[3], parts[4], parts[5], parts[6]
    if not cid_raw.isdigit() or not bet_raw.isdigit():
        await callback.answer("Некорректные параметры ставки.", show_alert=True)
        return
    success, msg, payload = await db.play_casino_game(
        user_id=callback.from_user.id,
        casino_id=int(cid_raw),
        game_type=game,
        prediction=prediction,
        bet_amount=float(bet_raw),
    )
    if not success:
        await callback.message.edit_text(f"❌ {msg}", reply_markup=_back(f"fp_casino_open_{cid_raw}"), parse_mode=None)
        return
    payload = payload or {}
    await callback.message.edit_text(
        "🎰 Игра завершена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Результат: {payload.get('result')}\n"
        f"Бросок/ролл: {payload.get('roll_value')}\n"
        f"Ставка: ${float(payload.get('bet') or 0):,.2f}\n"
        f"Выплата: ${float(payload.get('payout') or 0):,.2f}\n"
        f"Профит: ${float(payload.get('profit') or 0):,.2f}\n"
        f"Новый баланс: ${float(payload.get('new_balance') or 0):,.2f}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎰 Еще сыграть", callback_data=f"fp_casino_open_{cid_raw}")],
                [InlineKeyboardButton(text="📜 История", callback_data="fp_casino_history")],
                [InlineKeyboardButton(text="🔙 В казино", callback_data="casino_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_casino_history")
async def feature_casino_history(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_user_recent_casino_games(callback.from_user.id, limit=20)
    lines = ["📜 **ИСТОРИЯ ИГР**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("История пустая.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            lines.append(
                f"[{created}] {row.get('casino_name')} | {row.get('game_type')} | "
                f"ставка ${float(row.get('bet_amount') or 0):,.0f} | "
                f"выплата ${float(row.get('payout') or 0):,.0f} | {row.get('result')}"
            )
    await callback.message.edit_text("\n".join(lines), reply_markup=_back("casino_menu"), parse_mode="Markdown")


def _news_filter_label(code: str) -> str:
    mapping = {
        "all": "Все",
        "normal": "Обычные",
        "hot": "Горячие",
        "high": "Важные",
        "critical": "Критические",
    }
    return mapping.get(code, "Все")


def _news_badge(severity: str) -> str:
    sev = str(severity or "normal").strip().lower()
    if sev == "critical":
        return "🚨 Критично"
    if sev == "high":
        return "⚠️ Важно"
    if sev == "hot":
        return "🔥 Горячее"
    return "🆕 Новость"


async def _render_media_news_feed(
    event: Message | CallbackQuery,
    severity_filter: str = "all",
):
    safe_filter = str(severity_filter or "all").strip().lower()
    if safe_filter not in {"all", "normal", "high", "critical", "hot"}:
        safe_filter = "all"

    rows = await db.get_latest_media_news(
        limit=18,
        severity=None if safe_filter == "all" else safe_filter,
    )
    digest = await db.get_media_news_digest(hours=24)

    lines = [
        "📰 **ЛЕНТА СМИ MIRNASTAN**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Фильтр: {_md(_news_filter_label(safe_filter))}",
        (
            f"За 24ч: всего {int(digest.get('total') or 0)} | "
            f"🆕 {int(digest.get('normal') or 0)} | "
            f"🔥 {int(digest.get('hot') or 0)} | "
            f"⚠️ {int(digest.get('high') or 0)} | "
            f"🚨 {int(digest.get('critical') or 0)}"
        ),
        "",
    ]

    if not rows:
        lines.append("Новостей по выбранному фильтру пока нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            title = _md(str(row.get("title") or "Новость"))
            body = _md(str(row.get("body") or ""))
            source = _md(str(row.get("source_name") or "Система"))
            badge = _news_badge(str(row.get("severity") or "normal"))
            lines.append(f"[{created}] {badge} **{title}**")
            lines.append(f"Источник: {source}")
            lines.append(body)
            lines.append("")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Все", callback_data="media_news_menu"),
                InlineKeyboardButton(text="🔥 Горячие", callback_data="media_news_sev_hot"),
                InlineKeyboardButton(text="🚨 Критичные", callback_data="media_news_sev_critical"),
            ],
            [
                InlineKeyboardButton(text="⚠️ Важные", callback_data="media_news_sev_high"),
                InlineKeyboardButton(text="📌 Обычные", callback_data="media_news_sev_normal"),
            ],
            [
                InlineKeyboardButton(text="📈 Дайджест 24ч", callback_data="media_news_digest"),
                InlineKeyboardButton(text="🔄 Обновить", callback_data="media_news_menu"),
            ],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("news"))
@router.callback_query(F.data == "media_news_menu")
async def feature_media_news(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    await _render_media_news_feed(event, severity_filter="all")


@router.callback_query(F.data.startswith("media_news_sev_"))
async def feature_media_news_with_filter(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    severity = str(callback.data or "").replace("media_news_sev_", "").strip().lower()
    await _render_media_news_feed(callback, severity_filter=severity)


@router.callback_query(F.data == "media_news_digest")
async def feature_media_news_digest(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    digest = await db.get_media_news_digest(hours=24)
    top_sources = digest.get("top_sources") or []

    lines = [
        "📈 **СМИ: ДАЙДЖЕСТ ЗА 24 ЧАСА**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Всего публикаций: {int(digest.get('total') or 0)}",
        f"🆕 Обычные: {int(digest.get('normal') or 0)}",
        f"🔥 Горячие: {int(digest.get('hot') or 0)}",
        f"⚠️ Важные: {int(digest.get('high') or 0)}",
        f"🚨 Критические: {int(digest.get('critical') or 0)}",
        "",
        "Топ источников:",
    ]
    if not top_sources:
        lines.append("• Пока нет данных.")
    else:
        for row in top_sources[:5]:
            lines.append(
                f"• {_md(str(row.get('source_name') or 'Система'))}: {int(row.get('count') or 0)} публикаций"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 Открыть ленту", callback_data="media_news_menu")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


def _stock_change_label(change_pct: float) -> str:
    value = float(change_pct or 0.0)
    if value > 0.001:
        return f"🟢 +{value:.2f}%"
    if value < -0.001:
        return f"🔴 {value:.2f}%"
    return f"⚪ {value:.2f}%"


def _find_stock_asset(snapshot: dict, symbol: str) -> Optional[dict]:
    safe_symbol = str(symbol or "").strip().upper()
    for asset in snapshot.get("assets") or []:
        if str(asset.get("symbol") or "").strip().upper() == safe_symbol:
            return asset
    return None


def _find_stock_holding(snapshot: dict, symbol: str) -> Optional[dict]:
    safe_symbol = str(symbol or "").strip().upper()
    for row in snapshot.get("holdings") or []:
        if str(row.get("symbol") or "").strip().upper() == safe_symbol:
            return row
    return None


def _stock_market_metrics(snapshot: dict) -> dict:
    assets = snapshot.get("assets") or []
    if not assets:
        return {
            "index_value": 0.0,
            "index_change_pct": 0.0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "regime": "neutral",
            "regime_label": "⚪ Нейтральный рынок",
            "breadth_pct": 0.0,
        }

    sum_price = 0.0
    sum_prev = 0.0
    up = 0
    down = 0
    flat = 0
    for asset in assets:
        price = max(0.0, float(asset.get("price") or 0.0))
        prev = max(0.01, float(asset.get("prev_close") or price or 0.01))
        sum_price += price
        sum_prev += prev
        change_pct = float(asset.get("change_pct") or 0.0)
        if change_pct > 0.001:
            up += 1
        elif change_pct < -0.001:
            down += 1
        else:
            flat += 1

    index_value = round((sum_price / len(assets)) * 10.0, 2)
    prev_index = round((sum_prev / len(assets)) * 10.0, 2)
    index_change = ((index_value - prev_index) / prev_index * 100.0) if prev_index > 0 else 0.0
    breadth = ((up - down) / len(assets)) * 100.0

    regime = "neutral"
    regime_label = "⚪ Нейтральный рынок"
    if index_change >= 1.2 and breadth > 10:
        regime = "bull"
        regime_label = "🟢 Бычий рынок"
    elif index_change <= -1.2 and breadth < -10:
        regime = "bear"
        regime_label = "🔴 Медвежий рынок"

    return {
        "index_value": index_value,
        "index_change_pct": round(index_change, 3),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "regime": regime,
        "regime_label": regime_label,
        "breadth_pct": round(breadth, 2),
    }


def _stock_portfolio_concentration(snapshot: dict) -> dict:
    holdings = snapshot.get("holdings") or []
    if not holdings:
        return {"symbol": "", "share_pct": 0.0}

    total = max(0.0, float(snapshot.get("portfolio_value") or 0.0))
    if total <= 0:
        return {"symbol": "", "share_pct": 0.0}

    top = max(holdings, key=lambda row: float(row.get("current_value") or 0.0))
    top_symbol = str(top.get("symbol") or "")
    top_value = max(0.0, float(top.get("current_value") or 0.0))
    share = (top_value / total * 100.0) if total > 0 else 0.0
    return {"symbol": top_symbol, "share_pct": round(share, 2)}


async def _render_stock_exchange_menu(
    event: Message | CallbackQuery,
    *,
    refresh_prices: bool = True,
    notice: str = "",
):
    user_id = int(event.from_user.id)
    tick_info = await db.update_stock_exchange_market(force=False, interval_minutes=10) if refresh_prices else {
        "updated": False
    }
    snapshot = await db.get_stock_exchange_snapshot(user_id=user_id, refresh=False)
    assets = snapshot.get("assets") or []
    holdings = snapshot.get("holdings") or []
    balance = float(snapshot.get("balance") or 0.0)
    portfolio_value = float(snapshot.get("portfolio_value") or 0.0)
    portfolio_pnl = float(snapshot.get("portfolio_pnl") or 0.0)
    market_change = float(snapshot.get("market_change_avg_pct") or 0.0)
    open_orders = int(snapshot.get("open_orders") or 0)
    dividend_status = snapshot.get("dividend_status") or {}
    metrics = _stock_market_metrics(snapshot)
    concentration = _stock_portfolio_concentration(snapshot)
    top_symbol = str(concentration.get("symbol") or "")
    top_share_pct = float(concentration.get("share_pct") or 0.0)

    lines = [
        "📈 БИРЖА АКЦИЙ MIRNASTAN",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Индекс MIRX: {float(metrics.get('index_value') or 0):,.2f} ({_stock_change_label(float(metrics.get('index_change_pct') or 0))})",
        f"Режим: {metrics.get('regime_label')}",
        f"Рынок (среднее): {_stock_change_label(market_change)} | Breadth: {float(metrics.get('breadth_pct') or 0):+.1f}%",
        f"Ваш баланс: ${balance:,.2f}",
        f"Портфель: ${portfolio_value:,.2f} | PnL: {_format_money_delta(portfolio_pnl)}",
        f"Позиции: {len(holdings)} | Открытых ордеров: {open_orders}",
    ]
    if top_symbol and top_share_pct > 0:
        lines.append(f"Концентрация портфеля: {top_symbol} ({top_share_pct:.1f}%)")
    if bool(dividend_status.get("can_claim", True)):
        lines.append("💸 Дивиденды: доступны к получению")
    else:
        lines.append(f"💸 Дивиденды: через {int(dividend_status.get('minutes_to_next') or 0)} мин.")
    if tick_info.get("updated"):
        lines.append("🔄 Котировки обновлены автоматически.")
        if int(tick_info.get("orders_executed") or 0) > 0:
            lines.append(
                f"⚙️ Исполнено авто-ордеров: {int(tick_info.get('orders_executed') or 0)}"
            )
    elif int(tick_info.get("minutes_to_next") or 0) > 0:
        lines.append(f"⏱ Обновление цен через {int(tick_info.get('minutes_to_next'))} мин.")

    movers = sorted(assets, key=lambda x: abs(float(x.get("change_pct") or 0)), reverse=True)[:3]
    if movers:
        lines.append("")
        lines.append("Топ движения:")
        for row in movers:
            lines.append(
                f"• {str(row.get('symbol') or '')}: ${float(row.get('price') or 0):,.2f} ({_stock_change_label(float(row.get('change_pct') or 0))})"
            )
    if notice:
        lines.extend(["", str(notice)])

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for asset in assets:
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        change_pct = float(asset.get("change_pct") or 0.0)
        icon = "🟢" if change_pct > 0.001 else ("🔴" if change_pct < -0.001 else "⚪")
        price = float(asset.get("price") or 0.0)
        pair.append(
            InlineKeyboardButton(
                text=f"{icon} {symbol} ${price:,.0f}",
                callback_data=f"stock_asset_{symbol}",
            )
        )
        if len(pair) == 2:
            keyboard_rows.append(pair)
            pair = []
    if pair:
        keyboard_rows.append(pair)

    keyboard_rows.extend(
        [
            [
                InlineKeyboardButton(text="📦 Портфель", callback_data="stock_portfolio_menu"),
                InlineKeyboardButton(text="🕒 Сделки", callback_data="stock_history_menu"),
            ],
            [
                InlineKeyboardButton(text="📊 Аналитика", callback_data="stock_analytics_menu"),
                InlineKeyboardButton(text="🧾 Ордера", callback_data="stock_orders_menu"),
            ],
            [InlineKeyboardButton(text="💸 Получить дивиденды", callback_data="stock_dividend_claim")],
            [InlineKeyboardButton(text="🔄 Обновить цены", callback_data="stock_exchange_refresh")],
            [
                InlineKeyboardButton(text="🏙️ Городская площадь", callback_data="market_menu"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main"),
            ],
        ]
    )

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


async def _render_stock_asset_card(event: Message | CallbackQuery, symbol: str, notice: str = ""):
    safe_symbol = str(symbol or "").strip().upper()[:12]
    snapshot = await db.get_stock_exchange_snapshot(user_id=int(event.from_user.id), refresh=False)
    asset = _find_stock_asset(snapshot, safe_symbol)
    if not asset:
        await _render_stock_exchange_menu(event, refresh_prices=False, notice="❌ Тикер не найден.")
        return

    holding = _find_stock_holding(snapshot, safe_symbol) or {}
    qty = float(holding.get("quantity") or 0.0)
    avg_price = float(holding.get("avg_price") or 0.0)
    current_value = float(holding.get("current_value") or 0.0)
    pnl = float(holding.get("pnl") or 0.0)
    balance = float(snapshot.get("balance") or 0.0)

    lines = [
        f"📊 {safe_symbol} — {str(asset.get('name') or safe_symbol)}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Цена: ${float(asset.get('price') or 0):,.2f}",
        f"Изменение: {_stock_change_label(float(asset.get('change_pct') or 0))}",
        f"Волатильность: {float(asset.get('volatility') or 0) * 100:.2f}%",
        "",
        f"Ваш баланс: ${balance:,.2f}",
    ]

    if qty > 0:
        lines.extend(
            [
                f"В портфеле: {qty:.4f} шт",
                f"Средняя цена: ${avg_price:,.2f}",
                f"Текущая стоимость: ${current_value:,.2f}",
                f"PnL позиции: {_format_money_delta(pnl)}",
            ]
        )
    else:
        lines.append("В портфеле: нет позиции по этой акции.")

    current_price = max(1.0, float(asset.get("price") or 1.0))
    buy_trigger = round(current_price * 0.95, 2)
    take_trigger = round(current_price * 1.08, 2)
    stop_trigger = round(current_price * 0.94, 2)
    lines.extend(
        [
            "",
            "Авто-уровни (можно ставить ордера):",
            f"• Buy Limit: ${buy_trigger:,.2f}",
            f"• Take Profit: ${take_trigger:,.2f}",
            f"• Stop Loss: ${stop_trigger:,.2f}",
        ]
    )

    if notice:
        lines.extend(["", str(notice)])

    buy_presets = (300, 1000, 2500, 7000)
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    buy_pair: list[InlineKeyboardButton] = []
    for amount in buy_presets:
        buy_pair.append(
            InlineKeyboardButton(text=f"🟢 Купить ${int(amount)}", callback_data=f"stock_buy_{safe_symbol}_{int(amount)}")
        )
        if len(buy_pair) == 2:
            keyboard_rows.append(buy_pair)
            buy_pair = []
    if buy_pair:
        keyboard_rows.append(buy_pair)

    if qty > 0:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="🔴 Продать 25%", callback_data=f"stock_sell_{safe_symbol}_25"),
                InlineKeyboardButton(text="🔴 Продать 50%", callback_data=f"stock_sell_{safe_symbol}_50"),
            ]
        )
        keyboard_rows.append(
            [InlineKeyboardButton(text="🔴 Продать 100%", callback_data=f"stock_sell_{safe_symbol}_100")]
        )

    buy_cents = int(round(buy_trigger * 100))
    take_cents = int(round(take_trigger * 100))
    stop_cents = int(round(stop_trigger * 100))
    keyboard_rows.append(
        [InlineKeyboardButton(text="🎯 Buy limit (-5%, $1000)", callback_data=f"stock_order_buy_{safe_symbol}_{buy_cents}")]
    )
    if qty > 0:
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="✅ Take profit (+8%, 50%)", callback_data=f"stock_order_take_{safe_symbol}_{take_cents}"),
            ]
        )
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="🛑 Stop loss (-6%, 50%)", callback_data=f"stock_order_stop_{safe_symbol}_{stop_cents}"),
            ]
        )

    keyboard_rows.extend(
        [
            [
                InlineKeyboardButton(text="📦 Портфель", callback_data="stock_portfolio_menu"),
                InlineKeyboardButton(text="🧾 Ордера", callback_data="stock_orders_menu"),
            ],
            [InlineKeyboardButton(text="📈 К списку акций", callback_data="stock_exchange_menu")],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.message(Command("stocks"))
@router.callback_query(F.data == "stock_exchange_menu")
async def feature_stock_exchange_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        await event.answer()
    await _render_stock_exchange_menu(event, refresh_prices=True)


@router.callback_query(F.data == "stock_exchange_refresh")
async def feature_stock_exchange_refresh(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _render_stock_exchange_menu(callback, refresh_prices=True)


@router.callback_query(F.data == "stock_portfolio_menu")
async def feature_stock_portfolio_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    snapshot = await db.get_stock_exchange_snapshot(user_id=int(callback.from_user.id), refresh=False)
    holdings = sorted(
        snapshot.get("holdings") or [],
        key=lambda x: float(x.get("current_value") or 0.0),
        reverse=True,
    )

    lines = [
        "📦 ВАШ ПОРТФЕЛЬ АКЦИЙ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Общая стоимость: ${float(snapshot.get('portfolio_value') or 0):,.2f}",
        f"Общий результат: {_format_money_delta(float(snapshot.get('portfolio_pnl') or 0))}",
        f"Свободные деньги: ${float(snapshot.get('balance') or 0):,.2f}",
        "",
    ]
    if not holdings:
        lines.append("Пока нет открытых позиций.")
    else:
        for row in holdings[:12]:
            lines.append(
                f"• {str(row.get('symbol') or '')}: {float(row.get('quantity') or 0):.4f} шт | "
                f"${float(row.get('current_value') or 0):,.2f} | PnL {_format_money_delta(float(row.get('pnl') or 0))}"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🕒 Сделки", callback_data="stock_history_menu"),
                InlineKeyboardButton(text="📈 Биржа", callback_data="stock_exchange_menu"),
            ],
            [
                InlineKeyboardButton(text="📊 Аналитика", callback_data="stock_analytics_menu"),
                InlineKeyboardButton(text="🧾 Ордера", callback_data="stock_orders_menu"),
            ],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "stock_history_menu")
async def feature_stock_history_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    trades = await db.get_stock_exchange_recent_trades(int(callback.from_user.id), limit=15)
    lines = [
        "🕒 ИСТОРИЯ БИРЖЕВЫХ СДЕЛОК",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not trades:
        lines.append("Сделок пока нет.")
    else:
        for row in trades:
            side = str(row.get("side") or "").lower()
            side_label = "🟢 BUY" if side == "buy" else "🔴 SELL"
            created = str(row.get("created_at") or "")[:16]
            lines.append(
                f"• {created} | {side_label} {str(row.get('symbol') or '')} "
                f"{float(row.get('quantity') or 0):.4f} @ ${float(row.get('price') or 0):,.2f} "
                f"(сумма ${float(row.get('total') or 0):,.2f})"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Портфель", callback_data="stock_portfolio_menu"),
                InlineKeyboardButton(text="📈 Биржа", callback_data="stock_exchange_menu"),
            ],
            [
                InlineKeyboardButton(text="📊 Аналитика", callback_data="stock_analytics_menu"),
                InlineKeyboardButton(text="🧾 Ордера", callback_data="stock_orders_menu"),
            ],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "stock_analytics_menu")
async def feature_stock_analytics_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    snapshot = await db.get_stock_exchange_snapshot(user_id=int(callback.from_user.id), refresh=False)
    assets = snapshot.get("assets") or []
    metrics = _stock_market_metrics(snapshot)
    concentration = _stock_portfolio_concentration(snapshot)
    top_symbol = str(concentration.get("symbol") or "")
    top_share = float(concentration.get("share_pct") or 0.0)

    gainers = sorted(assets, key=lambda row: float(row.get("change_pct") or 0.0), reverse=True)[:3]
    losers = sorted(assets, key=lambda row: float(row.get("change_pct") or 0.0))[:3]

    risk_score = 40.0
    if top_share > 0:
        risk_score += min(45.0, top_share * 0.55)
    risk_score += min(15.0, abs(float(metrics.get("index_change_pct") or 0.0)) * 1.5)
    risk_score = max(0.0, min(100.0, risk_score))
    if risk_score < 35:
        risk_label = "🟢 Низкий"
    elif risk_score < 65:
        risk_label = "🟠 Средний"
    else:
        risk_label = "🔴 Высокий"

    lines = [
        "📊 АНАЛИТИКА БИРЖИ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Индекс MIRX: {float(metrics.get('index_value') or 0):,.2f}",
        f"Дневное изменение индекса: {_stock_change_label(float(metrics.get('index_change_pct') or 0))}",
        f"Режим рынка: {metrics.get('regime_label')}",
        f"Ширина рынка: {int(metrics.get('up_count') or 0)}↑ / {int(metrics.get('down_count') or 0)}↓ / {int(metrics.get('flat_count') or 0)}→",
        f"Риск портфеля: {risk_label} ({risk_score:.1f}/100)",
    ]
    if top_symbol:
        lines.append(f"Топ-концентрация: {top_symbol} ({top_share:.1f}%)")

    lines.extend(["", "Лидеры роста:"])
    if gainers:
        for row in gainers:
            lines.append(
                f"• {str(row.get('symbol') or '')}: {_stock_change_label(float(row.get('change_pct') or 0))} | ${float(row.get('price') or 0):,.2f}"
            )
    else:
        lines.append("• Нет данных.")

    lines.extend(["", "Лидеры падения:"])
    if losers:
        for row in losers:
            lines.append(
                f"• {str(row.get('symbol') or '')}: {_stock_change_label(float(row.get('change_pct') or 0))} | ${float(row.get('price') or 0):,.2f}"
            )
    else:
        lines.append("• Нет данных.")

    advice = "Диверсифицируйте портфель по 3+ тикерам."
    if top_share >= 60:
        advice = "Снизьте концентрацию в одном тикере: риск выше нормы."
    elif float(metrics.get("index_change_pct") or 0.0) <= -2.5:
        advice = "Высокая волатильность: рассмотрите защитные stop-loss ордера."
    elif float(metrics.get("index_change_pct") or 0.0) >= 2.5:
        advice = "Рынок разогрет: фиксируйте часть прибыли тейк-профитом."
    lines.extend(["", f"Совет системы: {advice}"])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Биржа", callback_data="stock_exchange_menu"),
                InlineKeyboardButton(text="🧾 Ордера", callback_data="stock_orders_menu"),
            ],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


def _stock_order_type_label(order_type: str) -> str:
    safe = str(order_type or "").strip().lower()
    if safe == "buy_limit":
        return "🟢 Buy Limit"
    if safe == "sell_take":
        return "✅ Take Profit"
    if safe == "sell_stop":
        return "🛑 Stop Loss"
    return safe or "order"


@router.callback_query(F.data == "stock_orders_menu")
async def feature_stock_orders_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_stock_limit_orders(int(callback.from_user.id), status="all", limit=25)
    open_count = sum(1 for row in rows if str(row.get("status") or "") == "open")

    lines = [
        "🧾 ЛИМИТНЫЕ ОРДЕРА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Всего в ленте: {len(rows)} | Открыто: {open_count}",
        "",
    ]
    if not rows:
        lines.append("Ордеров пока нет.")
    else:
        for row in rows[:12]:
            oid = int(row.get("id") or 0)
            symbol = str(row.get("symbol") or "")
            status = str(row.get("status") or "")
            target = float(row.get("target_price") or 0.0)
            order_type = _stock_order_type_label(str(row.get("order_type") or ""))
            current = float(row.get("current_price") or 0.0)
            if str(row.get("order_type") or "") == "buy_limit":
                detail = f"${float(row.get('amount') or 0):,.0f}"
            else:
                detail = f"{int(row.get('percent') or 0)}%"
            lines.append(
                f"#{oid} {order_type} {symbol} | target ${target:,.2f} | now ${current:,.2f} | {detail} | {status}"
            )

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if str(row.get("status") or "") != "open":
            continue
        oid = int(row.get("id") or 0)
        if oid <= 0:
            continue
        keyboard_rows.append([InlineKeyboardButton(text=f"❌ Отменить ордер #{oid}", callback_data=f"stock_order_cancel_{oid}")])
        if len(keyboard_rows) >= 6:
            break

    keyboard_rows.extend(
        [
            [
                InlineKeyboardButton(text="📈 Биржа", callback_data="stock_exchange_menu"),
                InlineKeyboardButton(text="📊 Аналитика", callback_data="stock_analytics_menu"),
            ],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("stock_order_cancel_"))
async def feature_stock_order_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = (callback.data or "").replace("stock_order_cancel_", "", 1)
    try:
        order_id = int(raw)
    except (TypeError, ValueError):
        await callback.answer("❌ Некорректный ордер.", show_alert=True)
        return
    ok, msg = await db.cancel_stock_limit_order(int(callback.from_user.id), order_id)
    if not ok:
        await callback.answer(msg, show_alert=True)
    await feature_stock_orders_menu(callback, state)


@router.callback_query(F.data == "stock_dividend_claim")
async def feature_stock_dividend_claim(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    ok, msg, payload = await db.claim_stock_dividends(int(callback.from_user.id))
    if not ok:
        await _render_stock_exchange_menu(callback, refresh_prices=False, notice=f"❌ {msg}")
        return

    lines = [
        "💸 ДИВИДЕНДЫ ЗАЧИСЛЕНЫ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Сумма: ${float(payload.get('payout') or 0):,.2f}",
        f"Средняя доходность: {float(payload.get('avg_yield_pct') or 0):.3f}%",
        f"Новый баланс: ${float(payload.get('new_balance') or 0):,.2f}",
        "",
        "Топ начислений:",
    ]
    details = payload.get("details") or []
    if not details:
        lines.append("• Детализация недоступна.")
    else:
        for row in sorted(details, key=lambda x: float(x.get("amount") or 0), reverse=True)[:5]:
            lines.append(
                f"• {str(row.get('symbol') or '')}: ${float(row.get('amount') or 0):,.2f} "
                f"({float(row.get('rate') or 0)*100:.3f}%)"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Биржа", callback_data="stock_exchange_menu")],
            [InlineKeyboardButton(text="🏙️ К площади", callback_data="market_menu")],
        ]
    )
    sender = _edit_or_answer(callback)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("stock_order_buy_"))
async def feature_stock_order_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("stock_order_buy_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных ордера.", show_alert=True)
        return
    symbol, cents_raw = payload.rsplit("_", 1)
    try:
        target_price = int(cents_raw) / 100.0
    except (TypeError, ValueError):
        await callback.answer("❌ Неверная цена ордера.", show_alert=True)
        return

    ok, msg, order = await db.place_stock_limit_order(
        user_id=int(callback.from_user.id),
        symbol=symbol,
        order_type="buy_limit",
        target_price=target_price,
        amount=1000.0,
    )
    notice = f"{'✅' if ok else '❌'} {msg}"
    if ok and order:
        notice += (
            f"\nСоздан ордер #{int(order.get('order_id') or 0)}: buy {str(order.get('symbol') or '')} "
            f"при цене <= ${float(order.get('target_price') or 0):,.2f} на ${float(order.get('amount') or 0):,.2f}"
        )
    await _render_stock_asset_card(callback, symbol, notice=notice)


@router.callback_query(F.data.startswith("stock_order_take_"))
async def feature_stock_order_take(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("stock_order_take_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных ордера.", show_alert=True)
        return
    symbol, cents_raw = payload.rsplit("_", 1)
    try:
        target_price = int(cents_raw) / 100.0
    except (TypeError, ValueError):
        await callback.answer("❌ Неверная цена ордера.", show_alert=True)
        return

    ok, msg, order = await db.place_stock_limit_order(
        user_id=int(callback.from_user.id),
        symbol=symbol,
        order_type="sell_take",
        target_price=target_price,
        percent=50,
    )
    notice = f"{'✅' if ok else '❌'} {msg}"
    if ok and order:
        notice += (
            f"\nСоздан ордер #{int(order.get('order_id') or 0)}: sell 50% {str(order.get('symbol') or '')} "
            f"при цене >= ${float(order.get('target_price') or 0):,.2f}"
        )
    await _render_stock_asset_card(callback, symbol, notice=notice)


@router.callback_query(F.data.startswith("stock_order_stop_"))
async def feature_stock_order_stop(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("stock_order_stop_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных ордера.", show_alert=True)
        return
    symbol, cents_raw = payload.rsplit("_", 1)
    try:
        target_price = int(cents_raw) / 100.0
    except (TypeError, ValueError):
        await callback.answer("❌ Неверная цена ордера.", show_alert=True)
        return

    ok, msg, order = await db.place_stock_limit_order(
        user_id=int(callback.from_user.id),
        symbol=symbol,
        order_type="sell_stop",
        target_price=target_price,
        percent=50,
    )
    notice = f"{'✅' if ok else '❌'} {msg}"
    if ok and order:
        notice += (
            f"\nСоздан ордер #{int(order.get('order_id') or 0)}: sell 50% {str(order.get('symbol') or '')} "
            f"при цене <= ${float(order.get('target_price') or 0):,.2f}"
        )
    await _render_stock_asset_card(callback, symbol, notice=notice)


@router.callback_query(F.data.startswith("stock_asset_"))
async def feature_stock_asset_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    symbol = (callback.data or "").replace("stock_asset_", "", 1).strip().upper()
    await _render_stock_asset_card(callback, symbol)


@router.callback_query(F.data.startswith("stock_buy_"))
async def feature_stock_buy(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("stock_buy_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных сделки.", show_alert=True)
        return
    symbol, amount_raw = payload.rsplit("_", 1)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        await callback.answer("❌ Неверная сумма.", show_alert=True)
        return

    ok, msg, trade = await db.stock_exchange_buy(int(callback.from_user.id), symbol=symbol, amount=amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        await _render_stock_asset_card(callback, symbol)
        return

    note = (
        f"✅ {msg}\n"
        f"Куплено: {float(trade.get('quantity') or 0):.4f} шт по ${float(trade.get('price') or 0):,.2f}\n"
        f"Сумма: ${float(trade.get('total') or 0):,.2f}\n"
        f"Новый баланс: ${float(trade.get('new_balance') or 0):,.2f}"
    )
    await _render_stock_asset_card(callback, symbol, notice=note)


@router.callback_query(F.data.startswith("stock_sell_"))
async def feature_stock_sell(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    payload = (callback.data or "").replace("stock_sell_", "", 1)
    if "_" not in payload:
        await callback.answer("❌ Ошибка данных продажи.", show_alert=True)
        return
    symbol, percent_raw = payload.rsplit("_", 1)
    try:
        percent = int(percent_raw)
    except (TypeError, ValueError):
        await callback.answer("❌ Неверный процент продажи.", show_alert=True)
        return

    ok, msg, trade = await db.stock_exchange_sell_percent(int(callback.from_user.id), symbol=symbol, percent=percent)
    if not ok:
        await callback.answer(msg, show_alert=True)
        await _render_stock_asset_card(callback, symbol)
        return

    note = (
        f"✅ {msg}\n"
        f"Продано: {float(trade.get('sold_qty') or 0):.4f} шт по ${float(trade.get('price') or 0):,.2f}\n"
        f"Получено: ${float(trade.get('proceeds') or 0):,.2f}\n"
        f"Результат сделки: {_format_money_delta(float(trade.get('pnl') or 0))}\n"
        f"Новый баланс: ${float(trade.get('new_balance') or 0):,.2f}"
    )
    await _render_stock_asset_card(callback, symbol, notice=note)


@router.message(Command("market"))
@router.callback_query(F.data == "market_menu")
async def feature_market_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    inflation = await db.get_inflation_snapshot()
    text = (
        "📣 **ГОРОДСКАЯ ПЛОЩАДКА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ключевые рыночные инструменты: СМИ, биржа, казино, контракты, маркетинг и застройка.\n"
        f"Текущая инфляция в сутки: {float(inflation.get('inflation_daily_rate') or 0) * 100:.2f}%"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📰 Новости СМИ", callback_data="media_news_menu")],
            [InlineKeyboardButton(text="📈 Акции / Биржа", callback_data="stock_exchange_menu")],
            [InlineKeyboardButton(text="🎪 Сюжетное событие", callback_data="fp_fun_hub")],
            [InlineKeyboardButton(text="📋 Контракты", callback_data="view_contracts")],
            [InlineKeyboardButton(text="✍️ Создать контракт", callback_data="create_contract")],
            [InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu")],
            [InlineKeyboardButton(text="👥 Рефералы и маркетинг", callback_data="referral_menu")],
            [InlineKeyboardButton(text="🏗️ Панель застройщика", callback_data="developer_menu")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("ref"))
@router.callback_query(F.data == "referral_menu")
async def feature_referral_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass

    user_id = event.from_user.id
    stats = await db.get_referral_stats(user_id)
    inflation = await db.get_inflation_snapshot()
    username = await _bot_username(event)
    ref_code = str(stats.get("referral_code") or f"REF{user_id}")
    ref_link = f"https://t.me/{username}?start=ref_{ref_code}" if username else f"/start ref_{ref_code}"
    referrals_count = int(stats.get("referrals_count") or 0)
    marketing_level = int(stats.get("marketing_level") or 0)
    earnings = float(stats.get("referral_earnings") or 0)
    gift_claimed = int(stats.get("referral_gift_claimed") or 0) == 1
    gift_remaining = int(stats.get("gift_remaining") or 0)

    lines = [
        "👥 **РЕФЕРАЛЬНАЯ СИСТЕМА И МАРКЕТИНГ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Ваш код: `{ref_code}`",
        f"Реферальная ссылка: `{ref_link}`",
        "",
        f"Приглашено друзей: {referrals_count}/50",
        f"Доход с рефералов: ${earnings:,.2f}",
        f"Уровень маркетинга: {marketing_level}",
        f"Инфляция в сутки: {float(inflation.get('inflation_daily_rate') or 0) * 100:.2f}%",
        "",
    ]
    if gift_claimed:
        lines.append("🎁 Подарок за 50 друзей: уже получен.")
    elif referrals_count >= 50:
        lines.append("🎁 Подарок за 50 друзей: доступен к получению.")
    else:
        lines.append(f"🎁 До подарка за 50 друзей осталось: {gift_remaining}.")

    recent = stats.get("recent_referrals") or []
    if recent:
        lines.append("")
        lines.append("Последние приглашенные:")
        for row in recent[:5]:
            lines.append(
                f"• {_md(str(row.get('referred_name') or row.get('referred_id')))} "
                f"(+${float(row.get('reward_amount') or 0):,.0f})"
            )

    keyboard_rows = [
        [InlineKeyboardButton(text="🚀 Маркетинг $250", callback_data="ref_marketing_250")],
        [InlineKeyboardButton(text="📣 Маркетинг $1000", callback_data="ref_marketing_1000")],
        [InlineKeyboardButton(text="🌐 Маркетинг $2500", callback_data="ref_marketing_2500")],
    ]
    if not gift_claimed:
        keyboard_rows.append([InlineKeyboardButton(text="🎁 Забрать подарок 50 друзей", callback_data="ref_claim_gift")])
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="referral_menu")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 К рынку", callback_data="market_menu")])

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("ref_marketing_"))
async def feature_referral_marketing(callback: CallbackQuery, state: FSMContext):
    raw_amount = callback.data.replace("ref_marketing_", "")
    if not raw_amount.isdigit():
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    amount = float(int(raw_amount))
    success, msg, _ = await db.run_marketing_campaign(callback.from_user.id, amount)
    await callback.answer(("✅ " if success else "❌ ") + msg[:180], show_alert=not success)
    await feature_referral_menu(callback, state)


@router.callback_query(F.data == "ref_claim_gift")
async def feature_referral_claim_gift(callback: CallbackQuery, state: FSMContext):
    success, msg, _ = await db.claim_referral_gift(callback.from_user.id)
    await callback.answer(("✅ " if success else "❌ ") + msg[:180], show_alert=not success)
    await feature_referral_menu(callback, state)


@router.message(Command("builder"))
@router.callback_query(F.data == "developer_menu")
async def feature_developer_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass

    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    projects = await db.get_developer_projects(user_id, limit=20)
    inflation = await db.get_inflation_snapshot()

    lines = [
        "🏗️ **ПАНЕЛЬ ЗАСТРОЙЩИКА**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Баланс: ${float(user.get('balance') or 0):,.2f}",
        f"Активных стройпроектов: {len([p for p in projects if str(p.get('status') or '') != 'claimed'])}",
        f"Индекс инфляции: {float(inflation.get('inflation_index') or 1):.4f}",
        "",
        "Тарифы:",
        "• Малый ЖК: вложение $280, срок ~25 мин",
        "• Квартал: вложение $950, срок ~90 мин",
        "• Сити-проект: вложение $2600, срок ~240 мин",
        "",
    ]

    if not projects:
        lines.append("У вас пока нет проектов.")
    else:
        lines.append("Ваши проекты:")
        for row in projects[:8]:
            status = str(row.get("status") or "building")
            if status != "claimed" and _time_left_label(str(row.get("ready_date") or "")) == "готово":
                status_label = "ready"
            else:
                status_label = status
            lines.append(
                f"• #{int(row.get('id') or 0)} {_md(str(row.get('project_name') or 'Проект'))}\n"
                f"  Статус: {status_label} | Выплата: ${float(row.get('expected_payout') or 0):,.2f} | "
                f"До готовности: {_time_left_label(str(row.get('ready_date') or ''))}"
            )

    keyboard_rows = [
        [InlineKeyboardButton(text="🧱 Старт: Малый ЖК", callback_data="dev_start_small")],
        [InlineKeyboardButton(text="🏘️ Старт: Квартал", callback_data="dev_start_district")],
        [InlineKeyboardButton(text="🏙️ Старт: Сити-проект", callback_data="dev_start_mega")],
    ]
    ready_rows = []
    for row in projects:
        pid = int(row.get("id") or 0)
        if pid <= 0:
            continue
        status = str(row.get("status") or "building")
        if status == "claimed":
            continue
        if _time_left_label(str(row.get("ready_date") or "")) == "готово":
            ready_rows.append([InlineKeyboardButton(text=f"💰 Забрать выплату #{pid}", callback_data=f"dev_claim_{pid}")])
    keyboard_rows.extend(ready_rows[:6])
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="developer_menu")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 К рынку", callback_data="market_menu")])

    sender = _edit_or_answer(event)
    await sender(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("dev_start_"))
async def feature_developer_start(callback: CallbackQuery, state: FSMContext):
    tier = callback.data.replace("dev_start_", "").strip().lower()
    success, msg, _ = await db.start_developer_project(callback.from_user.id, tier)
    await callback.answer(("✅ " if success else "❌ ") + msg[:180], show_alert=not success)
    await feature_developer_menu(callback, state)


@router.callback_query(F.data.startswith("dev_claim_"))
async def feature_developer_claim(callback: CallbackQuery, state: FSMContext):
    raw = callback.data.replace("dev_claim_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный проект.", show_alert=True)
        return
    success, msg, _ = await db.claim_developer_project(callback.from_user.id, int(raw))
    await callback.answer(("✅ " if success else "❌ ") + msg[:180], show_alert=not success)
    await feature_developer_menu(callback, state)


@router.callback_query(F.data == "fp_easter_egg")
async def feature_easter_egg(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    secret_lines = [
        "В подвале старого БЦ нашли сейф с купонами.",
        "На крыше отеля заметили тайник с редкими фишками.",
        "В архиве мэрии обнаружили забытую облигацию.",
        "В подземном переходе найден кэш старых контрактов.",
    ]
    bonus = random.randint(400, 1800)
    user = await db.get_user(callback.from_user.id) or {}
    new_balance = round(float(user.get("balance") or 0) + bonus, 2)
    await db.update_user(callback.from_user.id, balance=new_balance)
    await db.log_player_activity(callback.from_user.id, "easter_egg", "Найдена пасхалка дня", bonus)
    await callback.message.edit_text(
        f"🥚 Пасхалка!\n\n{random.choice(secret_lines)}\n\n"
        f"Награда: +${bonus:,.0f}\n"
        f"Новый баланс: ${new_balance:,.2f}",
        reply_markup=_back("market_menu"),
        parse_mode=None,
    )


@router.message(Command("gang"))
async def feature_gang_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🕶️ Открыть раздел банд:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🕶️ Банды", callback_data="gang_list")]]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "gang_list")
async def feature_gang_menu(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    user_gang = await db.get_user_gang(callback.from_user.id)
    if not user_gang:
        gangs = await db.list_gangs(limit=12)
        lines = ["🕶️ **БАНДЫ ГОРОДА**", "━━━━━━━━━━━━━━━━━━━━", ""]
        if not gangs:
            lines.append("Банды пока не созданы.")
        else:
            for gang in gangs:
                lines.append(
                    f"• **{_md(str(gang.get('name')))}** | лидер: {_md(str(gang.get('leader_name') or 'Неизвестно'))}\n"
                    f"  Репутация: {int(gang.get('reputation') or 0)} | участников: {int(gang.get('members_count') or 0)}"
                )
        keyboard_rows = [
            [InlineKeyboardButton(text=f"Вступить в #{int(g['id'])}", callback_data=f"fp_gang_join_{int(g['id'])}")]
            for g in gangs[:10]
        ]
        keyboard_rows.append([InlineKeyboardButton(text="🆕 Создать банду", callback_data="fp_gang_create")])
        keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
            parse_mode="Markdown",
        )
        return

    cartel = await db.get_gang_cartel(int(user_gang["id"]))
    lines = [
        f"🕶️ **БАНДА: {_md(str(user_gang.get('name') or ''))}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Роль: {_md(str(user_gang.get('member_role') or 'Участник'))}",
        f"Территория: {_md(str(user_gang.get('territory') or 'не указана'))}",
        f"Репутация: {int(user_gang.get('reputation') or 0)}",
        "",
    ]
    keyboard_rows = []
    if not cartel and int(user_gang.get("leader_id") or 0) == callback.from_user.id:
        lines.append("Наркокартель не создан.")
        keyboard_rows.append([InlineKeyboardButton(text="☠️ Создать картель", callback_data=f"fp_cartel_create_{int(user_gang['id'])}")])
    elif cartel:
        lines.extend(
            [
                f"Картель: {_md(str(cartel.get('name') or ''))}",
                f"Склад: {float(cartel.get('stock') or 0):,.1f}",
                f"Чистота: {float(cartel.get('purity') or 0):.1f}%",
                f"Отмывание: {int(cartel.get('laundering_level') or 1)} ур.",
            ]
        )
        keyboard_rows.extend(
            [
                [InlineKeyboardButton(text="🧪 Производство", callback_data="fp_cartel_op_produce")],
                [InlineKeyboardButton(text="🚚 Сбыт", callback_data="fp_cartel_op_smuggle")],
                [InlineKeyboardButton(text="🧼 Отмывание", callback_data="fp_cartel_op_launder")],
            ]
        )
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="gang_list")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "fp_gang_create")
async def feature_gang_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FeatureStates.gang_name)
    await callback.message.answer(
        "Введите название новой банды:",
        reply_markup=_back("gang_list", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.gang_name, F.text, ~F.text.startswith("/"))
async def feature_gang_create_name(message: Message, state: FSMContext):
    success, msg, gang_id = await db.create_gang(message.from_user.id, message.text or "")
    await state.clear()
    if not success:
        await message.answer(f"❌ {msg}", reply_markup=_back("gang_list"))
        return
    await message.answer(
        f"✅ Банда создана. ID: {gang_id}",
        reply_markup=_back("gang_list"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_gang_join_"))
async def feature_gang_join(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    gang_raw = callback.data.replace("fp_gang_join_", "")
    if not gang_raw.isdigit():
        await callback.answer("Некорректная банда.", show_alert=True)
        return
    success, msg = await db.join_gang(callback.from_user.id, int(gang_raw))
    await callback.message.answer(("✅ " if success else "❌ ") + msg, parse_mode=None)
    await feature_gang_menu(callback, state)


@router.callback_query(F.data.startswith("fp_cartel_create_"))
async def feature_cartel_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    gid_raw = callback.data.replace("fp_cartel_create_", "")
    if not gid_raw.isdigit():
        await callback.answer("Некорректная банда.", show_alert=True)
        return
    await state.set_state(FeatureStates.cartel_name)
    await state.update_data(cartel_gang_id=int(gid_raw))
    await callback.message.answer(
        "Введите название картеля:",
        reply_markup=_back("gang_list", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.cartel_name, F.text, ~F.text.startswith("/"))
async def feature_cartel_create_name(message: Message, state: FSMContext):
    data = await state.get_data()
    gid = int(data.get("cartel_gang_id") or 0)
    if gid <= 0:
        await state.clear()
        await message.answer("❌ Сессия устарела.", reply_markup=_back("gang_list"))
        return
    success, msg = await db.create_drug_cartel(message.from_user.id, gid, message.text or "")
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("gang_list"), parse_mode=None)


@router.callback_query(F.data.in_({"fp_cartel_op_produce", "fp_cartel_op_smuggle", "fp_cartel_op_launder"}))
async def feature_cartel_operation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    op = callback.data.replace("fp_cartel_op_", "")
    success, msg, payload = await db.run_cartel_operation(callback.from_user.id, op)
    if not success:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    else:
        payload = payload or {}
        await callback.message.answer(
            "✅ Операция выполнена\n"
            f"Тип: {payload.get('operation')}\n"
            f"Результат: {payload.get('result')}\n"
            f"Риск: {payload.get('risk')}\n"
            f"Δ Баланс: ${float(payload.get('delta_balance') or 0):,.2f}\n"
            f"Δ Тень: ${float(payload.get('delta_shadow') or 0):,.2f}\n"
            f"Новый баланс: ${float(payload.get('new_balance') or 0):,.2f}",
            parse_mode=None,
        )
    await feature_gang_menu(callback, state)


async def _ensure_president(callback: CallbackQuery) -> bool:
    authority = await db.get_government_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("Доступ только президенту.", show_alert=True)
        return False
    return True


async def _ensure_president_message(message: Message, state: FSMContext, back_cb: str) -> bool:
    authority = await db.get_government_authority(message.from_user.id)
    if authority == "president":
        return True
    await state.clear()
    await message.answer("Доступ только президенту.", reply_markup=_back(back_cb), parse_mode=None)
    return False

@router.callback_query(F.data == "pres_laws")
async def feature_pres_laws(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    try:
        await callback.answer()
    except Exception:
        pass
    rules = await db.list_government_rules(include_archived=True, limit=18)
    lines = ["📜 **ЗАКОНЫ ГОСУДАРСТВА**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    if not rules:
        lines.append("Законов пока нет.")
    else:
        for rule in rules[:12]:
            lines.append(
                f"#{int(rule.get('id') or 0)} {rule.get('rule_number')} | {rule.get('status')} | "
                f"штраф ${float(rule.get('violation_penalty') or 0):,.0f}"
            )
            lines.append(_md(str(rule.get("rule_text") or "")))
            keyboard_rows.append([InlineKeyboardButton(text=f"✏️ Ред. #{int(rule['id'])}", callback_data=f"pres_law_edit_{int(rule['id'])}")])
            keyboard_rows.append([InlineKeyboardButton(text=f"🔁 Статус #{int(rule['id'])}", callback_data=f"pres_law_toggle_{int(rule['id'])}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ Новый закон", callback_data="pres_law_add")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "pres_law_add")
async def feature_pres_law_add_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    await state.set_state(FeatureStates.law_create)
    await callback.message.answer(
        "Введите закон в формате:\nТекст закона | штраф\n\nПример:\nВсе бизнесы обязаны платить налог вовремя | 15000",
        reply_markup=_back("pres_laws", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.law_create, F.text, ~F.text.startswith("/"))
async def feature_pres_law_add_input(message: Message, state: FSMContext):
    if not await _ensure_president_message(message, state, "pres_laws"):
        return
    raw = (message.text or "").strip()
    if "|" in raw:
        text, penalty_raw = [x.strip() for x in raw.split("|", 1)]
    else:
        text, penalty_raw = raw, "1000"
    try:
        penalty = float(penalty_raw.replace(" ", "").replace(",", "."))
    except ValueError:
        penalty = 1000.0
    success, msg, _ = await db.create_government_rule(message.from_user.id, text, penalty)
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("pres_laws"), parse_mode=None)


@router.callback_query(F.data.startswith("pres_law_edit_"))
async def feature_pres_law_edit_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    rid_raw = callback.data.replace("pres_law_edit_", "")
    if not rid_raw.isdigit():
        await callback.answer("Некорректный закон.", show_alert=True)
        return
    await state.set_state(FeatureStates.law_edit)
    await state.update_data(edit_rule_id=int(rid_raw))
    await callback.message.answer(
        "Введите обновление в формате:\nНовый текст | штраф | статус(active/suspended/archived)\n"
        "Можно указать только текст.",
        reply_markup=_back("pres_laws", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.law_edit, F.text, ~F.text.startswith("/"))
async def feature_pres_law_edit_input(message: Message, state: FSMContext):
    if not await _ensure_president_message(message, state, "pres_laws"):
        return
    data = await state.get_data()
    rid = int(data.get("edit_rule_id") or 0)
    if rid <= 0:
        await state.clear()
        await message.answer("❌ Сессия редактирования устарела.", reply_markup=_back("pres_laws"))
        return
    chunks = [x.strip() for x in (message.text or "").split("|")]
    text = chunks[0] if chunks else None
    penalty: Optional[float] = None
    status: Optional[str] = None
    if len(chunks) > 1 and chunks[1]:
        try:
            penalty = float(chunks[1].replace(" ", "").replace(",", "."))
        except ValueError:
            penalty = None
    if len(chunks) > 2 and chunks[2]:
        status = chunks[2].lower()
    success, msg = await db.edit_government_rule(message.from_user.id, rid, rule_text=text, penalty=penalty, status=status)
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("pres_laws"), parse_mode=None)


@router.callback_query(F.data.startswith("pres_law_toggle_"))
async def feature_pres_law_toggle(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    rid_raw = callback.data.replace("pres_law_toggle_", "")
    if not rid_raw.isdigit():
        await callback.answer("Некорректный закон.", show_alert=True)
        return
    rid = int(rid_raw)
    rules = await db.list_government_rules(include_archived=True, limit=500)
    current = next((r for r in rules if int(r.get("id") or 0) == rid), None)
    if not current:
        await callback.answer("Закон не найден.", show_alert=True)
        return
    current_status = str(current.get("status") or "active").lower()
    new_status = "suspended" if current_status == "active" else "active"
    success, msg = await db.edit_government_rule(callback.from_user.id, rid, status=new_status)
    await callback.message.answer(("✅ " if success else "❌ ") + msg, parse_mode=None)
    await feature_pres_laws(callback, state)


@router.callback_query(F.data == "pres_flag_menu")
async def feature_pres_flag_menu(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    flag = await db.get_state_flag()
    text = (
        "🏳️ Управление государственным флагом\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Текст флага: {flag.get('state_flag_text') or 'не задан'}\n"
        f"Фото флага: {'загружено' if flag.get('state_flag_file_id') else 'не загружено'}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Установить текст", callback_data="pres_flag_set_text")],
            [InlineKeyboardButton(text="🖼️ Загрузить фото", callback_data="pres_flag_set_photo")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "pres_flag_set_text")
async def feature_pres_flag_set_text(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    await state.set_state(FeatureStates.flag_text)
    await callback.message.answer("Введите текст флага (эмодзи/девиз):", reply_markup=_back("pres_flag_menu", "🔙 Отмена"), parse_mode=None)


@router.message(FeatureStates.flag_text, F.text, ~F.text.startswith("/"))
async def feature_pres_flag_text_input(message: Message, state: FSMContext):
    if not await _ensure_president_message(message, state, "pres_flag_menu"):
        return
    success, msg = await db.set_state_flag(message.from_user.id, flag_text=message.text or "")
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("pres_flag_menu"), parse_mode=None)


@router.callback_query(F.data == "pres_flag_set_photo")
async def feature_pres_flag_set_photo(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    await state.set_state(FeatureStates.flag_photo)
    await callback.message.answer("Отправьте изображение флага одним фото.", reply_markup=_back("pres_flag_menu", "🔙 Отмена"), parse_mode=None)


@router.message(FeatureStates.flag_photo, F.photo)
async def feature_pres_flag_photo_input(message: Message, state: FSMContext):
    if not await _ensure_president_message(message, state, "pres_flag_menu"):
        return
    file_id = message.photo[-1].file_id if message.photo else ""
    success, msg = await db.set_state_flag(message.from_user.id, flag_file_id=file_id)
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("pres_flag_menu"), parse_mode=None)


@router.callback_query(F.data == "pres_tax_holiday_menu")
async def feature_pres_tax_holiday_menu(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    businesses = await db.list_all_businesses(limit=18)
    lines = ["🧾 Выберите бизнес для налоговых каникул (1 день):", ""]
    keyboard_rows = []
    for biz in businesses[:14]:
        lines.append(f"• #{int(biz['id'])} {biz.get('name')} | владелец: {biz.get('owner_name')}")
        keyboard_rows.append([InlineKeyboardButton(text=f"Каникулы #{int(biz['id'])}", callback_data=f"pres_tax_holiday_pick_{int(biz['id'])}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")])
    await callback.message.edit_text(
        "\n".join(lines) if businesses else "Нет бизнесов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("pres_tax_holiday_pick_"))
async def feature_pres_tax_holiday_pick(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_president(callback):
        return
    await callback.answer()
    bid_raw = callback.data.replace("pres_tax_holiday_pick_", "")
    if not bid_raw.isdigit():
        await callback.answer("Некорректный бизнес.", show_alert=True)
        return
    await state.set_state(FeatureStates.tax_holiday_reason)
    await state.update_data(tax_holiday_business_id=int(bid_raw))
    await callback.message.answer(
        "Введите причину налоговых каникул на 1 день:",
        reply_markup=_back("pres_tax_holiday_menu", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.tax_holiday_reason, F.text, ~F.text.startswith("/"))
async def feature_pres_tax_holiday_reason(message: Message, state: FSMContext):
    if not await _ensure_president_message(message, state, "pres_tax_holiday_menu"):
        return
    data = await state.get_data()
    bid = int(data.get("tax_holiday_business_id") or 0)
    if bid <= 0:
        await state.clear()
        await message.answer("❌ Сессия устарела.", reply_markup=_back("pres_tax_holiday_menu"))
        return
    success, msg = await db.grant_business_tax_holiday(
        actor_id=message.from_user.id,
        business_id=bid,
        reason=message.text or "",
        days=1,
    )
    await state.clear()
    await message.answer(("✅ " if success else "❌ ") + msg, reply_markup=_back("pres_tax_holiday_menu"), parse_mode=None)


@router.message(FeatureStates.law_create)
async def feature_pres_law_add_invalid(message: Message):
    await message.answer("❌ Введите текст закона в формате: Текст | штраф", reply_markup=_back("pres_laws"), parse_mode=None)


@router.message(FeatureStates.law_edit)
async def feature_pres_law_edit_invalid(message: Message):
    await message.answer("❌ Введите обновление в формате: Текст | штраф | статус", reply_markup=_back("pres_laws"), parse_mode=None)


@router.message(FeatureStates.flag_text)
async def feature_pres_flag_text_invalid(message: Message):
    await message.answer("❌ Нужен текст флага. Отправьте обычное сообщение.", reply_markup=_back("pres_flag_menu"), parse_mode=None)


@router.message(FeatureStates.flag_photo)
async def feature_pres_flag_photo_invalid(message: Message):
    await message.answer("❌ Нужна фотография. Отправьте одно фото флага.", reply_markup=_back("pres_flag_menu"), parse_mode=None)


@router.message(FeatureStates.tax_holiday_reason)
async def feature_pres_tax_holiday_invalid(message: Message):
    await message.answer("❌ Введите причину налоговых каникул текстом.", reply_markup=_back("pres_tax_holiday_menu"), parse_mode=None)


def _parse_amount(raw_text: str) -> Optional[float]:
    raw = str(raw_text or "").strip().replace("$", "").replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return round(value, 2)


# ---------------------------------------------------------------------------
# Contracts handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "view_contracts")
async def feature_contracts_view(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.list_market_contracts(viewer_id=callback.from_user.id, include_closed=False, limit=20)
    lines = ["📋 **КОНТРАКТЫ БИРЖИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    actions_added = 0

    if not rows:
        lines.append("Пока нет активных контрактов.")
    else:
        for row in rows:
            cid = int(row.get("id") or 0)
            creator_id = int(row.get("creator_id") or 0)
            assignee_id = int(row.get("assignee_id") or 0) if row.get("assignee_id") is not None else 0
            status = str(row.get("status") or "")
            reward = float(row.get("reward") or 0)
            lines.append(
                f"#{cid} | {status.upper()} | {_md(str(row.get('title') or 'Без названия'))}\n"
                f"Награда: ${reward:,.0f} | Заказчик: {_md(str(row.get('creator_name') or creator_id))}"
            )
            if status == "open" and creator_id != callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(text=f"✅ Взять #{cid}", callback_data=f"fp_contract_claim_{cid}")])
                actions_added += 1
            if status == "open" and creator_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(text=f"🛑 Отменить #{cid}", callback_data=f"fp_contract_cancel_{cid}")])
                actions_added += 1
            if status == "claimed" and assignee_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(text=f"🏁 Сдать #{cid}", callback_data=f"fp_contract_complete_{cid}")])
                actions_added += 1
            if status == "claimed" and creator_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(text=f"✔️ Подтвердить #{cid}", callback_data=f"fp_contract_complete_{cid}")])
                actions_added += 1
            lines.append("")

    keyboard_rows.append([InlineKeyboardButton(text="✍️ Создать контракт", callback_data="create_contract")])
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="view_contracts")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 К рынку", callback_data="market_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "create_contract")
async def feature_contracts_create_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FeatureStates.contract_title)
    await callback.message.answer(
        "Введите название контракта:",
        reply_markup=_back("view_contracts", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.contract_title, F.text, ~F.text.startswith("/"))
async def feature_contracts_title_input(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 4:
        await message.answer("❌ Название слишком короткое. Минимум 4 символа.", parse_mode=None)
        return
    await state.update_data(contract_title=title)
    await state.set_state(FeatureStates.contract_description)
    await message.answer("Опишите задачу контракта:", parse_mode=None)


@router.message(FeatureStates.contract_description, F.text, ~F.text.startswith("/"))
async def feature_contracts_description_input(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    if len(desc) < 8:
        await message.answer("❌ Описание слишком короткое. Минимум 8 символов.", parse_mode=None)
        return
    await state.update_data(contract_description=desc)
    await state.set_state(FeatureStates.contract_reward)
    await message.answer("Введите награду в долларах (например: 15000):", parse_mode=None)


@router.message(FeatureStates.contract_reward, F.text, ~F.text.startswith("/"))
async def feature_contracts_reward_input(message: Message, state: FSMContext):
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите корректную сумму.", parse_mode=None)
        return
    data = await state.get_data()
    title = str(data.get("contract_title") or "").strip()
    desc = str(data.get("contract_description") or "").strip()
    await state.clear()
    ok, msg, payload = await db.create_market_contract(
        creator_id=message.from_user.id,
        title=title,
        description=desc,
        reward=amount,
    )
    if not ok:
        await message.answer(f"❌ {msg}", reply_markup=_back("view_contracts"), parse_mode=None)
        return
    payload = payload or {}
    await message.answer(
        "✅ Контракт создан.\n"
        f"ID: {payload.get('contract_id')}\n"
        f"Награда: ${float(payload.get('reward') or 0):,.2f}",
        reply_markup=_back("view_contracts"),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_contract_claim_"))
async def feature_contracts_claim(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_contract_claim_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный контракт.", show_alert=True)
        return
    ok, msg = await db.claim_market_contract(callback.from_user.id, int(raw))
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await feature_contracts_view(callback, state)


@router.callback_query(F.data.startswith("fp_contract_complete_"))
async def feature_contracts_complete(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_contract_complete_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный контракт.", show_alert=True)
        return
    ok, msg, payload = await db.complete_market_contract(callback.from_user.id, int(raw))
    if ok:
        payout = float((payload or {}).get("payout") or 0)
        await callback.message.answer(f"✅ {msg}\nВыплата: ${payout:,.2f}", parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await feature_contracts_view(callback, state)


@router.callback_query(F.data.startswith("fp_contract_cancel_"))
async def feature_contracts_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_contract_cancel_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный контракт.", show_alert=True)
        return
    ok, msg, payload = await db.cancel_market_contract(callback.from_user.id, int(raw))
    if ok:
        refund = float((payload or {}).get("refund") or 0)
        await callback.message.answer(f"✅ {msg}\nВозврат: ${refund:,.2f}", parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await feature_contracts_view(callback, state)


@router.message(FeatureStates.contract_title)
async def feature_contracts_title_invalid(message: Message):
    await message.answer("❌ Введите название контракта обычным текстом.", parse_mode=None)


@router.message(FeatureStates.contract_description)
async def feature_contracts_desc_invalid(message: Message):
    await message.answer("❌ Введите описание контракта обычным текстом.", parse_mode=None)


@router.message(FeatureStates.contract_reward)
async def feature_contracts_reward_invalid(message: Message):
    await message.answer("❌ Введите сумму награды числом.", parse_mode=None)


# ---------------------------------------------------------------------------
# Bank handlers (deposit/history)
# ---------------------------------------------------------------------------

async def _render_bank_ops(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id) or {}
    balance = float(user.get("balance") or 0)
    bank = float(user.get("bank") or 0)
    text = (
        "💳 **БАНКОВЫЕ ОПЕРАЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Наличные: ${balance:,.2f}\n"
        f"Счет в банке: ${bank:,.2f}\n\n"
        "Быстрые действия:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️ +10%", callback_data="fp_bank_dep_10"),
                InlineKeyboardButton(text="⬆️ +25%", callback_data="fp_bank_dep_25"),
                InlineKeyboardButton(text="⬆️ +50%", callback_data="fp_bank_dep_50"),
                InlineKeyboardButton(text="⬆️ Всё", callback_data="fp_bank_dep_100"),
            ],
            [
                InlineKeyboardButton(text="⬇️ -10%", callback_data="fp_bank_wd_10"),
                InlineKeyboardButton(text="⬇️ -25%", callback_data="fp_bank_wd_25"),
                InlineKeyboardButton(text="⬇️ -50%", callback_data="fp_bank_wd_50"),
                InlineKeyboardButton(text="⬇️ Всё", callback_data="fp_bank_wd_100"),
            ],
            [InlineKeyboardButton(text="✍️ Внести сумму вручную", callback_data="fp_bank_dep_manual")],
            [InlineKeyboardButton(text="✍️ Снять сумму вручную", callback_data="fp_bank_wd_manual")],
            [InlineKeyboardButton(text="📊 История", callback_data="bank_history")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="bank_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "bank_deposit")
async def feature_bank_deposit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await _render_bank_ops(callback)


@router.callback_query(F.data.startswith("fp_bank_dep_"))
async def feature_bank_dep_percent(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    pct_raw = callback.data.replace("fp_bank_dep_", "")
    if pct_raw == "manual":
        await feature_bank_dep_manual_start(callback, state)
        return
    if not pct_raw.isdigit():
        await callback.answer("Некорректный процент.", show_alert=True)
        return
    user = await db.get_user(callback.from_user.id) or {}
    balance = float(user.get("balance") or 0)
    pct = int(pct_raw)
    amount = round(balance * pct / 100.0, 2)
    if amount <= 0:
        await callback.message.answer("❌ Недостаточно наличных для депозита.", parse_mode=None)
        return
    ok, msg, _ = await db.deposit_to_bank(callback.from_user.id, amount, note=f"quick_{pct}%")
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await _render_bank_ops(callback)


@router.callback_query(F.data.startswith("fp_bank_wd_"))
async def feature_bank_withdraw_percent(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    pct_raw = callback.data.replace("fp_bank_wd_", "")
    if pct_raw == "manual":
        await feature_bank_wd_manual_start(callback, state)
        return
    if not pct_raw.isdigit():
        await callback.answer("Некорректный процент.", show_alert=True)
        return
    user = await db.get_user(callback.from_user.id) or {}
    bank = float(user.get("bank") or 0)
    pct = int(pct_raw)
    amount = round(bank * pct / 100.0, 2)
    if amount <= 0:
        await callback.message.answer("❌ Недостаточно средств на счете.", parse_mode=None)
        return
    ok, msg, _ = await db.withdraw_from_bank(callback.from_user.id, amount, note=f"quick_{pct}%")
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await _render_bank_ops(callback)


@router.callback_query(F.data == "fp_bank_dep_manual")
async def feature_bank_dep_manual_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FeatureStates.bank_deposit_amount)
    await callback.message.answer(
        "Введите сумму для пополнения банка:",
        reply_markup=_back("bank_deposit", "🔙 Отмена"),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_bank_wd_manual")
async def feature_bank_wd_manual_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FeatureStates.bank_withdraw_amount)
    await callback.message.answer(
        "Введите сумму для снятия со счета:",
        reply_markup=_back("bank_deposit", "🔙 Отмена"),
        parse_mode=None,
    )


@router.message(FeatureStates.bank_deposit_amount, F.text, ~F.text.startswith("/"))
async def feature_bank_dep_manual_input(message: Message, state: FSMContext):
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите корректную сумму.", parse_mode=None)
        return
    await state.clear()
    ok, msg, _ = await db.deposit_to_bank(message.from_user.id, amount, note="manual")
    await message.answer(("✅ " if ok else "❌ ") + msg, reply_markup=_back("bank_deposit"), parse_mode=None)


@router.message(FeatureStates.bank_withdraw_amount, F.text, ~F.text.startswith("/"))
async def feature_bank_wd_manual_input(message: Message, state: FSMContext):
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите корректную сумму.", parse_mode=None)
        return
    await state.clear()
    ok, msg, _ = await db.withdraw_from_bank(message.from_user.id, amount, note="manual")
    await message.answer(("✅ " if ok else "❌ ") + msg, reply_markup=_back("bank_deposit"), parse_mode=None)


@router.callback_query(F.data == "bank_history")
async def feature_bank_history(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_user_bank_transactions(callback.from_user.id, limit=20)
    lines = ["📊 **ИСТОРИЯ БАНКА**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Операций пока нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            tx_type = "Депозит" if row.get("tx_type") == "deposit" else "Вывод"
            lines.append(
                f"[{created}] {tx_type} ${float(row.get('amount') or 0):,.2f}\n"
                f"Наличные: ${float(row.get('balance_before') or 0):,.2f} → ${float(row.get('balance_after') or 0):,.2f}\n"
                f"Банк: ${float(row.get('bank_before') or 0):,.2f} → ${float(row.get('bank_after') or 0):,.2f}"
            )
            lines.append("")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("bank_deposit"),
        parse_mode="Markdown",
    )


@router.message(FeatureStates.bank_deposit_amount)
async def feature_bank_dep_invalid(message: Message):
    await message.answer("❌ Введите сумму числом.", parse_mode=None)


@router.message(FeatureStates.bank_withdraw_amount)
async def feature_bank_wd_invalid(message: Message):
    await message.answer("❌ Введите сумму числом.", parse_mode=None)


# ---------------------------------------------------------------------------
# Police handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "police_search_suspects")
async def feature_police_search_suspects(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    if not await _can_use_police_tools(callback.from_user.id, user):
        await callback.answer("Доступ только для полиции/ФБР.", show_alert=True)
        return

    await _render_police_arrest_picker(callback, page=0)


async def _render_police_arrest_picker(callback: CallbackQuery, page: int = 0):
    page_size = 8
    total = await db.count_players(exclude_user_id=callback.from_user.id)
    max_page = (total - 1) // page_size if total > 0 else 0
    safe_page = max(0, min(int(page or 0), max_page))
    offset = safe_page * page_size

    players = await db.get_players_page(
        limit=page_size,
        offset=offset,
        exclude_user_id=callback.from_user.id,
    )

    lines = ["🔍 **РОЗЫСК ПОДОЗРЕВАЕМЫХ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    lines.append(f"Страница: {safe_page + 1}/{max_page + 1} | Всего игроков: {total}")
    lines.append("")
    keyboard_rows = []
    if not players:
        lines.append("Подозреваемые не найдены.")
    else:
        for row in players:
            sid = int(row.get("user_id") or 0)
            risk = float(row.get("crimes_committed") or 0) * 2 + float(row.get("tax_debt") or 0) / 1000
            name = _display_user(row)
            lines.append(
                f"#{sid} {_md(name)}\n"
                f"Риск: {risk:.1f} | Преступления: {int(row.get('crimes_committed') or 0)} | "
                f"Налоговый долг: ${float(row.get('tax_debt') or 0):,.0f}"
            )
            lines.append("")
            keyboard_rows.append([InlineKeyboardButton(text=f"⛓️ Арест #{sid}", callback_data=f"fp_police_arrest_pick_{sid}_{safe_page}")])

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"fp_police_arrest_page_{safe_page - 1}"))
    if safe_page < max_page:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"fp_police_arrest_page_{safe_page + 1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_police_arrest_page_{safe_page}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="police_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_police_arrest_page_"))
async def feature_police_arrest_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_police_arrest_page_", "")
    if not raw.lstrip("-").isdigit():
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await _render_police_arrest_picker(callback, page=int(raw))


@router.callback_query(F.data.startswith("fp_police_arrest_pick_"))
async def feature_police_arrest_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_police_arrest_pick_", "")
    parts = tail.split("_")
    sid_raw = parts[0] if parts else ""
    page_raw = parts[1] if len(parts) > 1 else "0"
    if not sid_raw.isdigit():
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    sid = int(sid_raw)
    page = int(page_raw) if page_raw.lstrip("-").isdigit() else 0
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Уклонение от налогов", callback_data=f"fp_police_arrest_do_{sid}_tax_{page}")],
            [InlineKeyboardButton(text="🧾 Финансовое мошенничество", callback_data=f"fp_police_arrest_do_{sid}_fraud_{page}")],
            [InlineKeyboardButton(text="🕵️ Коррупционная деятельность", callback_data=f"fp_police_arrest_do_{sid}_corrupt_{page}")],
            [InlineKeyboardButton(text="⚠️ Нарушение порядка", callback_data=f"fp_police_arrest_do_{sid}_order_{page}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_police_arrest_page_{page}")],
        ]
    )
    await callback.message.edit_text(
        f"Выберите основание для ареста игрока #{sid}:",
        reply_markup=keyboard,
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fp_police_arrest_do_"))
async def feature_police_arrest_do(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_police_arrest_do_", "")
    parts = tail.split("_")
    if len(parts) < 2 or not parts[0].isdigit():
        await callback.answer("Некорректные параметры ареста.", show_alert=True)
        return
    suspect_id = int(parts[0])
    code = parts[1]
    page = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0
    templates = {
        "tax": ("Уклонение от налогов", 4500, 180),
        "fraud": ("Финансовое мошенничество", 7000, 240),
        "corrupt": ("Коррупционная деятельность", 9500, 300),
        "order": ("Нарушение общественного порядка", 1800, 120),
    }
    reason, fine, minutes = templates.get(code, templates["order"])
    ok, msg, payload = await db.register_police_arrest(
        officer_id=callback.from_user.id,
        suspect_id=suspect_id,
        reason=reason,
        fine_amount=float(fine),
        jail_minutes=int(minutes),
    )
    if ok:
        case_id = int((payload or {}).get("case_id") or 0)
        await callback.message.answer(f"✅ {msg}\nСудебное дело: #{case_id}", parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await _render_police_arrest_picker(callback, page=page)


@router.callback_query(F.data == "police_my_arrests")
async def feature_police_my_arrests(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_police_arrests(officer_id=callback.from_user.id, limit=20)
    lines = ["⛓️ **МОИ АРЕСТЫ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("У вас пока нет арестов.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            lines.append(
                f"[{created}] #{int(row.get('id') or 0)} | {row.get('status')}\n"
                f"Подозреваемый: {row.get('suspect_name')} | Дело: #{int(row.get('case_id') or 0)}\n"
                f"Основание: {row.get('reason')}"
            )
            lines.append("")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("police_menu"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "police_investigations")
async def feature_police_investigations(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_active_investigations(officer_id=callback.from_user.id, limit=20)
    lines = ["📋 **РАССЛЕДОВАНИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Активных расследований нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            lines.append(
                f"[{created}] Арест #{int(row.get('arrest_id') or 0)} | "
                f"Подозреваемый: {row.get('suspect_name')}\n"
                f"Дело #{int(row.get('case_id') or 0)} | статус: {row.get('case_status') or 'open'}\n"
                f"Основание: {row.get('reason')}"
            )
            lines.append("")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("police_menu"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "police_penalty_menu")
async def feature_police_penalty_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    if not await _can_use_police_tools(callback.from_user.id, user):
        await callback.answer("Доступ только для полиции/ФБР.", show_alert=True)
        return

    await _render_police_penalty_menu(callback, page=0)


async def _render_police_penalty_menu(callback: CallbackQuery, page: int = 0):
    page_size = 8
    total = await db.count_players(exclude_user_id=callback.from_user.id)
    max_page = (total - 1) // page_size if total > 0 else 0
    safe_page = max(0, min(int(page or 0), max_page))
    offset = safe_page * page_size

    players = await db.get_players_page(
        limit=page_size,
        offset=offset,
        exclude_user_id=callback.from_user.id,
    )

    lines = ["⚖️ **ПОЛИЦИЯ: НАКАЗАНИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    lines.append(f"Страница: {safe_page + 1}/{max_page + 1} | Всего игроков: {total}")
    lines.append("")
    keyboard_rows = []
    if not players:
        lines.append("Кандидатов для санкций пока нет.")
    else:
        for row in players:
            sid = int(row.get("user_id") or 0)
            if sid <= 0:
                continue
            lines.append(
                f"#{sid} {_md(_display_user(row))} | "
                f"Реп: {float(row.get('reputation') or 0):.1f} | "
                f"Долг: ${float(row.get('tax_debt') or 0):,.0f}"
            )
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"⚖️ Наказать #{sid}", callback_data=f"fp_police_penalty_pick_{sid}_{safe_page}")]
            )

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"fp_police_penalty_page_{safe_page - 1}"))
    if safe_page < max_page:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"fp_police_penalty_page_{safe_page + 1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_police_penalty_page_{safe_page}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="police_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_police_penalty_page_"))
async def feature_police_penalty_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_police_penalty_page_", "")
    if not raw.lstrip("-").isdigit():
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await _render_police_penalty_menu(callback, page=int(raw))


@router.callback_query(F.data.startswith("fp_police_penalty_pick_"))
async def feature_police_penalty_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_police_penalty_pick_", "")
    parts = tail.split("_")
    sid_raw = parts[0] if parts else ""
    page_raw = parts[1] if len(parts) > 1 else "0"
    if not sid_raw.isdigit():
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    sid = int(sid_raw)
    page = int(page_raw) if page_raw.lstrip("-").isdigit() else 0
    text = (
        f"⚖️ Наказания полиции для игрока #{sid}\n"
        "Выберите формат санкции:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟨 Предупреждение", callback_data=f"fp_police_penalty_do_{sid}_warn_{page}")],
            [InlineKeyboardButton(text="💸 Штраф", callback_data=f"fp_police_penalty_do_{sid}_fine_{page}")],
            [InlineKeyboardButton(text="⛔ Ограничение 30м", callback_data=f"fp_police_penalty_do_{sid}_restrict_{page}")],
            [InlineKeyboardButton(text="📢 Публичное постановление", callback_data=f"fp_police_penalty_do_{sid}_public_{page}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_police_penalty_page_{page}")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_police_penalty_do_"))
async def feature_police_penalty_do(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_police_penalty_do_", "")
    parts = tail.split("_")
    if len(parts) < 2 or not parts[0].isdigit():
        await callback.answer("Некорректные параметры санкции.", show_alert=True)
        return
    target_id = int(parts[0])
    code = parts[1].strip().lower()
    page = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0

    templates = {
        "warn": {
            "reason": "Письменное предупреждение полиции",
            "fine": 0.0,
            "ban": 0,
            "rep": -3.0,
            "tax": 0.0,
            "corr": 0,
            "seize": 0.0,
            "public": False,
        },
        "fine": {
            "reason": "Административный штраф полиции",
            "fine": 140.0,
            "ban": 0,
            "rep": -4.0,
            "tax": 0.0,
            "corr": 0,
            "seize": 0.0,
            "public": False,
        },
        "restrict": {
            "reason": "Ограничение действий по постановлению полиции",
            "fine": 80.0,
            "ban": 30,
            "rep": -6.0,
            "tax": 20.0,
            "corr": 1,
            "seize": 0.0,
            "public": False,
        },
        "public": {
            "reason": "Публичное постановление полиции",
            "fine": 90.0,
            "ban": 45,
            "rep": -7.0,
            "tax": 35.0,
            "corr": 1,
            "seize": 0.0,
            "public": True,
        },
    }
    cfg = templates.get(code)
    if not cfg:
        await callback.answer("Неизвестный тип санкции.", show_alert=True)
        return

    ok, msg, payload = await db.issue_security_penalty(
        actor_id=callback.from_user.id,
        target_id=target_id,
        agency="police",
        reason=str(cfg["reason"]),
        fine_amount=float(cfg["fine"]),
        ban_minutes=int(cfg["ban"]),
        reputation_delta=float(cfg["rep"]),
        tax_debt_delta=float(cfg["tax"]),
        corruption_delta=int(cfg["corr"]),
        seize_percent=float(cfg["seize"]),
        public_notice=bool(cfg["public"]),
    )
    if ok:
        p = payload or {}
        await callback.message.answer(
            "✅ Наказание применено.\n"
            f"Штраф: ${float(p.get('fine_paid') or 0):,.2f}\n"
            f"Изъято: ${float(p.get('seized_amount') or 0):,.2f}\n"
            f"Блокировка до: {str(p.get('ban_until') or 'нет')[:16]}",
            parse_mode=None,
        )
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await _render_police_penalty_menu(callback, page=page)


@router.callback_query(F.data == "fbi_penalty_menu")
async def feature_fbi_penalty_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    if not await _can_use_fbi_tools(callback.from_user.id, user):
        await callback.answer("Доступ только для ФБР/руководства.", show_alert=True)
        return

    await _render_fbi_penalty_menu(callback, page=0)


async def _render_fbi_penalty_menu(callback: CallbackQuery, page: int = 0):
    page_size = 8
    total = await db.count_players(exclude_user_id=callback.from_user.id)
    max_page = (total - 1) // page_size if total > 0 else 0
    safe_page = max(0, min(int(page or 0), max_page))
    offset = safe_page * page_size

    players = await db.get_players_page(
        limit=page_size,
        offset=offset,
        search="",
        exclude_user_id=callback.from_user.id,
    )

    lines = ["🛡 **ФБР: САНКЦИИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    lines.append(f"Страница: {safe_page + 1}/{max_page + 1} | Всего игроков: {total}")
    lines.append("")
    keyboard_rows = []
    if not players:
        lines.append("Игроки не найдены.")
    else:
        for row in players:
            pid = int(row.get("user_id") or 0)
            if pid <= 0:
                continue
            lines.append(
                f"#{pid} {_md(_display_user(row))} | "
                f"Баланс: ${float(row.get('balance') or 0):,.0f} | "
                f"Тень: ${float(row.get('shadow_balance') or 0):,.0f}"
            )
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"🛡 Санкции #{pid}", callback_data=f"fp_fbi_penalty_pick_{pid}_{safe_page}")]
            )

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"fp_fbi_penalty_page_{safe_page - 1}"))
    if safe_page < max_page:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"fp_fbi_penalty_page_{safe_page + 1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fp_fbi_penalty_page_{safe_page}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_fbi_penalty_page_"))
async def feature_fbi_penalty_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_fbi_penalty_page_", "")
    if not raw.lstrip("-").isdigit():
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await _render_fbi_penalty_menu(callback, page=int(raw))


@router.callback_query(F.data.startswith("fp_fbi_penalty_pick_"))
async def feature_fbi_penalty_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_fbi_penalty_pick_", "")
    parts = tail.split("_")
    sid_raw = parts[0] if parts else ""
    page_raw = parts[1] if len(parts) > 1 else "0"
    if not sid_raw.isdigit():
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    sid = int(sid_raw)
    page = int(page_raw) if page_raw.lstrip("-").isdigit() else 0
    text = (
        f"🛡 Санкции ФБР для игрока #{sid}\n"
        "Выберите формат санкции:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Временная заморозка", callback_data=f"fp_fbi_penalty_do_{sid}_freeze_{page}")],
            [InlineKeyboardButton(text="⚖️ Финансовые санкции", callback_data=f"fp_fbi_penalty_do_{sid}_sanction_{page}")],
            [InlineKeyboardButton(text="🤐 Шантаж + блокировка", callback_data=f"fp_fbi_penalty_do_{sid}_blackmail_{page}")],
            [InlineKeyboardButton(text="📢 Публичное разоблачение", callback_data=f"fp_fbi_penalty_do_{sid}_public_{page}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fp_fbi_penalty_page_{page}")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("fp_fbi_penalty_do_"))
async def feature_fbi_penalty_do(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tail = callback.data.replace("fp_fbi_penalty_do_", "")
    parts = tail.split("_")
    if len(parts) < 2 or not parts[0].isdigit():
        await callback.answer("Некорректные параметры санкции.", show_alert=True)
        return
    target_id = int(parts[0])
    code = parts[1].strip().lower()
    page = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0

    templates = {
        "freeze": {
            "reason": "Временная заморозка активов по линии ФБР",
            "fine": 70.0,
            "ban": 60,
            "rep": -8.0,
            "tax": 40.0,
            "corr": 2,
            "seize": 0.18,
            "public": False,
        },
        "sanction": {
            "reason": "Финансовые санкции ФБР",
            "fine": 180.0,
            "ban": 120,
            "rep": -12.0,
            "tax": 80.0,
            "corr": 3,
            "seize": 0.0,
            "public": False,
        },
        "blackmail": {
            "reason": "Оперативное давление и шантаж ФБР",
            "fine": 220.0,
            "ban": 180,
            "rep": -14.0,
            "tax": 100.0,
            "corr": 4,
            "seize": 0.12,
            "public": False,
        },
        "public": {
            "reason": "Публичное разоблачение ФБР",
            "fine": 120.0,
            "ban": 90,
            "rep": -16.0,
            "tax": 120.0,
            "corr": 3,
            "seize": 0.05,
            "public": True,
        },
    }
    cfg = templates.get(code)
    if not cfg:
        await callback.answer("Неизвестный тип санкции.", show_alert=True)
        return

    ok, msg, payload = await db.issue_security_penalty(
        actor_id=callback.from_user.id,
        target_id=target_id,
        agency="fbi",
        reason=str(cfg["reason"]),
        fine_amount=float(cfg["fine"]),
        ban_minutes=int(cfg["ban"]),
        reputation_delta=float(cfg["rep"]),
        tax_debt_delta=float(cfg["tax"]),
        corruption_delta=int(cfg["corr"]),
        seize_percent=float(cfg["seize"]),
        public_notice=bool(cfg["public"]),
    )
    if ok:
        p = payload or {}
        await callback.message.answer(
            "✅ Санкция ФБР применена.\n"
            f"Штраф: ${float(p.get('fine_paid') or 0):,.2f}\n"
            f"Изъято: ${float(p.get('seized_amount') or 0):,.2f}\n"
            f"Блокировка до: {str(p.get('ban_until') or 'нет')[:16]}",
            parse_mode=None,
        )
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await _render_fbi_penalty_menu(callback, page=page)


# ---------------------------------------------------------------------------
# Court handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "court_cases")
async def feature_court_cases(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    is_judge = await _is_judge_actor(callback.from_user.id, user)
    rows = await db.get_court_cases(limit=25) if is_judge else await db.get_court_cases(defendant_id=callback.from_user.id, limit=25)

    lines = ["⚖️ **ДЕЛА В СУДЕ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    if not rows:
        lines.append("Дел не найдено.")
    else:
        for row in rows[:16]:
            case_id = int(row.get("id") or 0)
            lines.append(
                f"#{case_id} | {str(row.get('status') or '').upper()} | "
                f"Ответчик: {_md(str(row.get('defendant_name') or row.get('defendant_id')))}\n"
                f"Иск: ${float(row.get('requested_penalty') or 0):,.0f} | "
                f"Штраф: ${float(row.get('imposed_penalty') or 0):,.0f}\n"
                f"{_md(str(row.get('title') or 'Без названия'))}"
            )
            lines.append("")
            if is_judge and str(row.get("status") or "") in {"open", "hearing"} and len(keyboard_rows) < 10:
                keyboard_rows.append([InlineKeyboardButton(text=f"🕒 Слушание #{case_id}", callback_data=f"fp_court_hearing_{case_id}")])
                keyboard_rows.append([InlineKeyboardButton(text=f"✅ Закрыть #{case_id}", callback_data=f"fp_court_close_{case_id}")])
                keyboard_rows.append([InlineKeyboardButton(text=f"🛑 Отклонить #{case_id}", callback_data=f"fp_court_dismiss_{case_id}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="court_cases")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="court_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_court_hearing_"))
async def feature_court_set_hearing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_court_hearing_", "")
    if not raw.isdigit():
        await callback.answer("Некорректное дело.", show_alert=True)
        return
    ok, msg, _ = await db.update_court_case_status(
        actor_id=callback.from_user.id,
        case_id=int(raw),
        status="hearing",
        verdict_text="Назначено судебное слушание.",
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await feature_court_cases(callback, state)


@router.callback_query(F.data.startswith("fp_court_close_"))
async def feature_court_close(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_court_close_", "")
    if not raw.isdigit():
        await callback.answer("Некорректное дело.", show_alert=True)
        return
    ok, msg, payload = await db.update_court_case_status(
        actor_id=callback.from_user.id,
        case_id=int(raw),
        status="closed",
        verdict_text="Дело закрыто, назначен штраф.",
    )
    if ok:
        fine = float((payload or {}).get("collected_penalty") or 0)
        await callback.message.answer(f"✅ {msg}\nВзыскано: ${fine:,.2f}", parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await feature_court_cases(callback, state)


@router.callback_query(F.data.startswith("fp_court_dismiss_"))
async def feature_court_dismiss(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = callback.data.replace("fp_court_dismiss_", "")
    if not raw.isdigit():
        await callback.answer("Некорректное дело.", show_alert=True)
        return
    ok, msg, _ = await db.update_court_case_status(
        actor_id=callback.from_user.id,
        case_id=int(raw),
        status="dismissed",
        verdict_text="Дело отклонено.",
        imposed_penalty=0,
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await feature_court_cases(callback, state)


@router.callback_query(F.data == "court_defendants")
async def feature_court_defendants(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    rows = await db.get_court_defendants(limit=20)
    lines = ["👥 **ОБВИНЯЕМЫЕ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Список пуст.")
    else:
        for row in rows:
            lines.append(
                f"#{int(row.get('defendant_id') or 0)} {row.get('defendant_name')}\n"
                f"Активных дел: {int(row.get('active_cases') or 0)} | "
                f"Приговоров: {int(row.get('convictions') or 0)} | "
                f"Отклонено: {int(row.get('dismissals') or 0)}"
            )
            lines.append("")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("court_menu"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "court_history")
async def feature_court_history(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    is_judge = await _is_judge_actor(callback.from_user.id, user)
    lines = ["📜 **ИСТОРИЯ ДЕЛ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if is_judge:
        closed = await db.get_court_cases(status="closed", limit=12)
        dismissed = await db.get_court_cases(status="dismissed", limit=12)
        rows = (closed + dismissed)[:18]
        if not rows:
            lines.append("История пока пустая.")
        else:
            for row in rows:
                lines.append(
                    f"#{int(row.get('id') or 0)} | {row.get('status')} | "
                    f"{row.get('defendant_name')} | "
                    f"штраф ${float(row.get('imposed_penalty') or 0):,.0f}"
                )
    else:
        status = await db.get_user_court_status(callback.from_user.id)
        recent = status.get("recent") or []
        if not recent:
            lines.append("История пока пустая.")
        else:
            for row in recent:
                lines.append(
                    f"#{int(row.get('id') or 0)} | {row.get('status')} | "
                    f"{row.get('title')} | штраф ${float(row.get('imposed_penalty') or 0):,.0f}"
                )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("court_menu"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "court_status")
async def feature_court_status(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    status = await db.get_user_court_status(callback.from_user.id)
    lines = [
        "📋 **ВАШ СУДЕБНЫЙ СТАТУС**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Открытых дел: {int(status.get('open_cases') or 0)}",
        f"На слушании: {int(status.get('hearing_cases') or 0)}",
        f"Закрытых дел: {int(status.get('closed_cases') or 0)}",
        f"Отклоненных дел: {int(status.get('dismissed_cases') or 0)}",
        "",
    ]
    recent = status.get("recent") or []
    if recent:
        lines.append("Последние дела:")
        for row in recent[:6]:
            lines.append(
                f"#{int(row.get('id') or 0)} | {row.get('status')} | "
                f"штраф ${float(row.get('imposed_penalty') or 0):,.0f}"
            )
    else:
        lines.append("У вас нет судебных записей.")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("court_menu"),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Organization management handlers
# ---------------------------------------------------------------------------

async def _get_managed_org_for_user(user_id: int, preferred_org_id: Optional[int] = None) -> Optional[dict]:
    async def _can_manage(org: dict | None) -> bool:
        if not org:
            return False
        oid = int(org.get("id") or 0)
        if oid <= 0:
            return False
        return await db.can_manage_organization(user_id, oid)

    if preferred_org_id:
        org = await db.get_organization_by_id(int(preferred_org_id))
        if await _can_manage(org):
            return org

    orgs_short = await db.list_organizations()
    for short in orgs_short:
        oid = int(short.get("id") or 0)
        if oid <= 0:
            continue
        org = await db.get_organization_by_id(oid)
        if await _can_manage(org):
            return org
    return None


@router.callback_query(F.data == "review_applications")
async def feature_review_applications(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    preferred_org_id = int(data.get("managed_org_id") or 0)
    org = await _get_managed_org_for_user(callback.from_user.id, preferred_org_id if preferred_org_id > 0 else None)
    if not org:
        await callback.answer("Доступно только руководству организации.", show_alert=True)
        return

    apps = await db.get_organization_applications(int(org["id"]), status="pending", limit=20)
    lines = [
        f"📋 **ЗАЯВКИ В { _md(str(org.get('name') or 'ОРГАНИЗАЦИЮ')) }**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard_rows = []
    if not apps:
        lines.append("Новых заявок нет.")
    else:
        for app in apps[:12]:
            aid = int(app.get("id") or 0)
            text = str(app.get("application_text") or "")
            if len(text) > 100:
                text = text[:97] + "..."
            lines.append(
                f"#{aid} { _md(str(app.get('applicant_name') or app.get('user_id'))) }\n"
                f"Текст: {_md(text) if text else 'без комментария'}"
            )
            lines.append("")
            keyboard_rows.append(
                [
                    InlineKeyboardButton(text=f"✅ Принять #{aid}", callback_data=f"fp_org_app_accept_{aid}"),
                    InlineKeyboardButton(text=f"❌ Отклонить #{aid}", callback_data=f"fp_org_app_reject_{aid}"),
                ]
            )
    active_org_id = int(org.get("id") or 0)
    back_cb = f"manage_organization_{active_org_id}" if active_org_id > 0 else "manage_organization"
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="review_applications")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_org_app_accept_"))
@router.callback_query(F.data.startswith("fp_org_app_reject_"))
async def feature_review_applications_decision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    approve = callback.data.startswith("fp_org_app_accept_")
    raw = callback.data.replace("fp_org_app_accept_", "").replace("fp_org_app_reject_", "")
    if not raw.isdigit():
        await callback.answer("Некорректная заявка.", show_alert=True)
        return
    ok, msg = await db.review_organization_application(
        reviewer_id=callback.from_user.id,
        application_id=int(raw),
        approve=approve,
        note="Рассмотрено руководством",
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + msg, parse_mode=None)
    await feature_review_applications(callback, state)


@router.callback_query(F.data == "manage_members")
async def feature_manage_members(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    preferred_org_id = int(data.get("managed_org_id") or 0)
    org = await _get_managed_org_for_user(callback.from_user.id, preferred_org_id if preferred_org_id > 0 else None)
    if not org:
        await callback.answer("Доступно только руководству организации.", show_alert=True)
        return
    members = await db.get_organization_members(int(org["id"]), limit=60)
    lines = [
        f"👥 **СОТРУДНИКИ { _md(str(org.get('name') or 'ОРГАНИЗАЦИИ')) }**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Всего: {len(members)}",
        "",
    ]
    if not members:
        lines.append("Сотрудников пока нет.")
    else:
        for row in members[:25]:
            member_name = _display_user(row)
            lines.append(
                f"• {_md(member_name)}\n"
                f"  Роль: {_md(str(row.get('role') or 'Сотрудник'))} | "
                f"Зарплата: ${float(row.get('salary') or 0):,.0f}"
            )
    active_org_id = int(org.get("id") or 0)
    back_cb = f"manage_organization_{active_org_id}" if active_org_id > 0 else "manage_organization"
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back(back_cb),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "org_finances")
async def feature_org_finances(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    preferred_org_id = int(data.get("managed_org_id") or 0)
    org = await _get_managed_org_for_user(callback.from_user.id, preferred_org_id if preferred_org_id > 0 else None)
    if not org:
        await callback.answer("Доступно только руководству организации.", show_alert=True)
        return
    members = await db.get_organization_members(int(org["id"]), limit=200)
    payroll = round(sum(float(m.get("salary") or 0) for m in members), 2)
    avg_salary = round((payroll / len(members)), 2) if members else 0.0
    lines = [
        f"💰 **ФИНАНСЫ { _md(str(org.get('name') or 'ОРГАНИЗАЦИИ')) }**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Бюджет: ${float(org.get('budget') or 0):,.2f}",
        f"Сотрудников: {len(members)}",
        f"ФОТ (день): ${payroll:,.2f}",
        f"Средняя зарплата: ${avg_salary:,.2f}",
        "",
        "Налоговые параметры:",
        f"• income_tax: {float(org.get('income_tax') or 0):.3f}",
        f"• property_tax: {float(org.get('property_tax') or 0):.3f}",
        f"• business_tax: {float(org.get('business_tax') or 0):.3f}",
    ]
    active_org_id = int(org.get("id") or 0)
    back_cb = f"manage_organization_{active_org_id}" if active_org_id > 0 else "manage_organization"
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back(back_cb),
        parse_mode="Markdown",
    )

