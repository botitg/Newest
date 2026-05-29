"""
revolutions.py - Система революций и свержения правительства
Смена власти через народное волеизъявление
"""

import logging
from datetime import datetime
import random
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import get_back_button

logger = logging.getLogger(__name__)
router = Router()
INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")


def _clean_name(value, max_len: int = 32) -> str:
    text = str(value or "")
    for token in INVISIBLE_NAME_CHARS:
        text = text.replace(token, "")
    text = " ".join(text.split()).strip()
    return text[:max_len] if max_len > 0 else text


def _display_name_from_row(row: dict | None, fallback_id: int | None = None) -> str:
    data = row or {}
    for key in ("supporter_name", "organizer_name", "nickname", "full_name"):
        text = _clean_name(data.get(key), 32)
        if text:
            return text
    username = _clean_name(data.get("supporter_username") or data.get("username"), 32).lstrip("@")
    if username:
        return f"@{username}"
    uid = data.get("supporter_id") or data.get("user_id") or fallback_id
    return f"ID {uid}" if uid else "Неизвестный"


class RevolutionStates(StatesGroup):
    """Состояния для системы революций"""
    revolution_menu = State()
    selecting_new_leader = State()
    sponsoring_revolution = State()
    joining_revolution = State()
    creating_manifesto = State()


async def _resolve_revolution_for_user(user_id: int, state: FSMContext) -> dict | None:
    data = await state.get_data()
    selected_id = int(data.get("selected_revolution_id") or 0)
    if selected_id > 0:
        rev = await db.get_revolution_by_id(selected_id)
        if rev and str(rev.get("status") or "") == "active":
            return rev

    revolutions = await db.get_active_revolutions(limit=50)
    organizer_rev = next((r for r in revolutions if int(r.get("organizer_id") or 0) == int(user_id)), None)
    if organizer_rev:
        await state.update_data(selected_revolution_id=int(organizer_rev.get("id") or 0))
        return organizer_rev
    if revolutions:
        first = revolutions[0]
        await state.update_data(selected_revolution_id=int(first.get("id") or 0))
        return first
    return None


# ============================================================================
# ГЛАВНОЕ МЕНЮ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "revolution_menu")
async def revolution_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню революций"""
    # Проверяем активные революции
    gov = await db.get_government_system() or {}
    gov_type = gov.get('government_type') or gov.get('current_type') or 'Демократия'
    leader_id = gov.get('current_leader_id')
    stability = gov.get('stability', 50)
    corruption = gov.get('corruption', 30)
    
    text = (
        "🔴 **РЕВОЛЮЦИИ И ПЕРЕВОРОТЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Текущее правление:** {gov_type}\n"
        f"**Лидер:** ID {leader_id if leader_id else 'не назначен'}\n"
        f"**Стабильность:** {stability}/100\n"
        f"**Коррупция:** {corruption}/100\n\n"
        "Организуйте революцию и смените власть!\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="⚡ Запустить революцию", callback_data="start_revolution")],
        [InlineKeyboardButton(text="👥 Активные революции", callback_data="view_active_revolutions")],
        [InlineKeyboardButton(text="📋 История", callback_data="revolution_history")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(RevolutionStates.revolution_menu)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


# ============================================================================
# ЗАПУСК РЕВОЛЮЦИИ
# ============================================================================

@router.callback_query(F.data == "start_revolution")
async def start_revolution_setup(callback: CallbackQuery, state: FSMContext):
    """Начало революции - выбор целей"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {} or {}
    
    text = (
        "⚡ **ЗАПУСК РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**ТРЕБОВАНИЯ:**\n\n"
        "💰 **Спонсирование:** $100,000\n"
        "   (Вы финансируете революцию)\n\n"
        "👥 **Поддержка:** 50+ сторонников\n"
        "   (Нужно собрать из других игроков)\n\n"
        "📋 **Манифест:** Описание целей революции\n"
        "   (Обоснование смены власти)\n\n"
    )
    
    if user.get('balance', 0) < 100000:
        text += "❌ У вас недостаточно денег!\n"
        text += "Требуется: $100,000\n"
        text += f"У вас: ${user.get('balance', 0):.2f}\n"
        
        keyboard = [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_menu")]
        ]
    else:
        text += "Вы готовы спонсировать революцию?"
        
        keyboard = [
            [InlineKeyboardButton(text="✅ Да, начать!", callback_data="confirm_sponsor_revolution")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="revolution_menu")]
        ]
    
    await state.set_state(RevolutionStates.sponsoring_revolution)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "confirm_sponsor_revolution")
async def confirm_revolution_sponsorship(callback: CallbackQuery, state: FSMContext):
    """Подтверждение спонсирования революции"""
    user_id = callback.from_user.id
    
    text = (
        "📝 **МАНИФЕСТ РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Напишите манифест вашей революции.\n"
        "Объясните, почему нужно свергнуть текущее правительство.\n\n"
        "Манифест будет видна всем игрокам для агитации.\n"
        "(Максимум 500 символов)\n"
    )
    
    await state.set_state(RevolutionStates.creating_manifesto)
    await state.update_data(user_id=user_id)
    
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_back_button(callback="revolution_menu"), parse_mode='Markdown')


@router.message(RevolutionStates.creating_manifesto, F.text, ~F.text.startswith("/"))
async def process_revolution_manifesto(message: Message, state: FSMContext):
    """Обработка манифеста революции"""
    data = await state.get_data()
    user_id = data.get('user_id')
    manifesto = (message.text or "").strip()[:500]
    if len(manifesto) < 20:
        await message.answer("❌ Манифест слишком короткий. Минимум 20 символов.")
        return

    user = await db.get_user(user_id) or {}
    ok, msg, payload = await db.create_revolution(
        organizer_id=int(user_id),
        manifesto=manifesto,
        supporters_needed=50,
        budget_spent=100000,
    )
    if not ok:
        await state.set_state(RevolutionStates.revolution_menu)
        await message.answer(f"❌ {msg}", reply_markup=get_back_button(callback="revolution_menu"))
        return

    payload = payload or {}
    rev_id = int(payload.get("revolution_id") or 0)
    await state.update_data(selected_revolution_id=rev_id)
    text = (
        "🔴 **РЕВОЛЮЦИЯ ОБЪЯВЛЕНА!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Организатор: {_display_name_from_row(user, fallback_id=user_id)}\n"
        f"ID революции: #{rev_id}\n"
        f"Нужно сторонников: {int(payload.get('supporters_needed') or 50)}\n"
        f"Текущий счет: {int(payload.get('supporters_count') or 1)}\n"
        f"Бюджет запуска: ${float(payload.get('budget_spent') or 0):,.2f}\n\n"
        f"Манифест:\n{manifesto}"
    )

    keyboard = [
        [InlineKeyboardButton(text="📣 Агитация", callback_data="revolution_campaign")],
        [InlineKeyboardButton(text="👥 Сторонники", callback_data="revolution_supporters")],
        [InlineKeyboardButton(text="🔍 Активные революции", callback_data="view_active_revolutions")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="revolution_menu")]
    ]

    await state.set_state(RevolutionStates.joining_revolution)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# ============================================================================
# ПРОСМОТР АКТИВНЫХ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "view_active_revolutions")
async def view_active_revolutions(callback: CallbackQuery, state: FSMContext):
    """Просмотр активных революций"""
    revolutions = await db.get_active_revolutions(limit=20)
    lines = [
        "🔴 **АКТИВНЫЕ РЕВОЛЮЦИИ**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard = []

    if not revolutions:
        lines.append("Активные революции отсутствуют.")
        lines.append("Запустите новую революцию, чтобы начать движение.")
    else:
        for idx, rev in enumerate(revolutions[:10], start=1):
            rid = int(rev.get("id") or 0)
            supporters = int(rev.get("supporters_count") or 0)
            needed = max(1, int(rev.get("supporters_needed") or 50))
            progress = min(100, round((supporters / needed) * 100))
            started = str(rev.get("started_date") or "")[:16]
            lines.append(
                f"{idx}. Революция #{rid}\n"
                f"Организатор: {_display_name_from_row(rev, fallback_id=int(rev.get('organizer_id') or 0))}\n"
                f"Сторонники: {supporters}/{needed} ({progress}%)\n"
                f"Старт: {started}"
            )
            lines.append("")
            keyboard.append([
                InlineKeyboardButton(text=f"✅ Вступить #{rid}", callback_data=f"confirm_join_revolution_{rid}"),
                InlineKeyboardButton(text=f"📖 Манифест #{rid}", callback_data=f"view_manifesto_{rid}"),
            ])

        await state.update_data(selected_revolution_id=int(revolutions[0].get("id") or 0))

    keyboard.append([InlineKeyboardButton(text="⚡ Новая революция", callback_data="start_revolution")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_menu")])

    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    await callback.answer()


# ============================================================================
# ПРИСОЕДИНЕНИЕ К РЕВОЛЮЦИИ
# ============================================================================

@router.callback_query(F.data == "join_revolution")
async def join_revolution(callback: CallbackQuery, state: FSMContext):
    """Присоединение к революции"""
    revolutions = await db.get_active_revolutions(limit=15)
    lines = [
        "👥 **ПРИСОЕДИНЕНИЕ К РЕВОЛЮЦИИ**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard = []
    if not revolutions:
        lines.append("Сейчас нет активных революций.")
    else:
        for rev in revolutions[:8]:
            rid = int(rev.get("id") or 0)
            supporters = int(rev.get("supporters_count") or 0)
            needed = max(1, int(rev.get("supporters_needed") or 50))
            lines.append(
                f"#{rid} | {_display_name_from_row(rev, fallback_id=int(rev.get('organizer_id') or 0))}\n"
                f"Сторонники: {supporters}/{needed}"
            )
            lines.append("")
            keyboard.append([
                InlineKeyboardButton(text=f"✅ Вступить #{rid}", callback_data=f"confirm_join_revolution_{rid}"),
                InlineKeyboardButton(text=f"📖 Манифест #{rid}", callback_data=f"view_manifesto_{rid}"),
            ])
        await state.update_data(selected_revolution_id=int(revolutions[0].get("id") or 0))

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_menu")])
    await state.set_state(RevolutionStates.joining_revolution)
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_join_revolution_"))
async def confirm_join_revolution(callback: CallbackQuery, state: FSMContext):
    """Подтверждение присоединения к революции"""
    revolution_id = callback.data.replace("confirm_join_revolution_", "")
    user_id = callback.from_user.id
    if not revolution_id.isdigit():
        await callback.answer("Некорректная революция.", show_alert=True)
        return

    ok, msg = await db.add_revolution_supporter(user_id, int(revolution_id))
    rev = await db.get_revolution_by_id(int(revolution_id))
    supporters = int((rev or {}).get("supporters_count") or 0)
    needed = int((rev or {}).get("supporters_needed") or 50)
    status = str((rev or {}).get("status") or "active")

    text = (
        f"{'✅' if ok else '❌'} **ПОДДЕРЖКА РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{msg}\n\n"
        f"Революция #{revolution_id}\n"
        f"Сторонники: {supporters}/{needed}\n"
        f"Статус: {status}"
    )
    await state.update_data(selected_revolution_id=int(revolution_id))
    keyboard = [
        [InlineKeyboardButton(text="📣 Агитация", callback_data="revolution_campaign")],
        [InlineKeyboardButton(text="👥 Сторонники", callback_data="revolution_supporters")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="revolution_menu")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    await callback.answer()


@router.callback_query(F.data.startswith("view_manifesto_"))
async def view_manifesto(callback: CallbackQuery, state: FSMContext):
    """Просмотр манифеста выбранной революции."""
    revolution_id = callback.data.replace("view_manifesto_", "")
    if not revolution_id.isdigit():
        await callback.answer("Некорректная революция.", show_alert=True)
        return
    rev = await db.get_revolution_by_id(int(revolution_id))
    if not rev:
        await callback.answer("Революция не найдена.", show_alert=True)
        return
    supporters = int(rev.get("supporters_count") or 0)
    needed = int(rev.get("supporters_needed") or 50)
    await state.update_data(selected_revolution_id=int(revolution_id))
    text = (
        f"📖 **МАНИФЕСТ РЕВОЛЮЦИИ #{revolution_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Организатор: {_display_name_from_row(rev, fallback_id=int(rev.get('organizer_id') or 0))}\n"
        f"Старт: {str(rev.get('started_date') or '')[:16]}\n"
        f"Сторонники: {supporters}/{needed}\n"
        f"Статус: {rev.get('status')}\n\n"
        f"{rev.get('reason') or 'Манифест отсутствует.'}"
    )
    keyboard = [
        [InlineKeyboardButton(text="✅ Поддержать", callback_data=f"confirm_join_revolution_{int(revolution_id)}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="join_revolution")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="revolution_menu")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    await callback.answer()


# ============================================================================
# АГИТАЦИЯ И СБОР ГОЛОСОВ
# ============================================================================

@router.callback_query(F.data == "revolution_campaign")
async def revolution_campaign(callback: CallbackQuery, state: FSMContext):
    """Агитация для революции"""
    text = (
        "📣 **АГИТАЦИОННАЯ КАМПАНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Используйте эти материалы для агитации:\n\n"
        "Примеры слоганов:\n"
        "• 'Пора менять власть!'\n"
        "• 'Долой коррупцию!'\n"
        "• 'Смена правления близка!'\n"
        "• 'Власть народу!'\n"
        "• 'Вперед к переменам!'\n\n"
        "**КАЖДЫЙ ПРИЗЫВ:**\n"
        "✅ +1 сторонник\n"
        "⏰ Раз в 30 минут максимум\n"
        "🎯 Лучше всего в групповых чатах\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="📢 Сделать призыв", callback_data="make_propaganda_call")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="revolution_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "make_propaganda_call")
async def make_propaganda_call(callback: CallbackQuery, state: FSMContext):
    """Создание пропагандистского раза"""
    text = (
        "📢 **СОЗДАНИЕ ПРИЗЫВА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите тип призыва:\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="⚡ Эмоциональный", callback_data="propaganda_emotional")],
        [InlineKeyboardButton(text="📊 Аналитический", callback_data="propaganda_analytical")],
        [InlineKeyboardButton(text="🎯 Целевой", callback_data="propaganda_targeted")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("propaganda_"))
async def send_propaganda(callback: CallbackQuery, state: FSMContext):
    """Отправка пропагандистского материала"""
    propaganda_type = callback.data.replace("propaganda_", "")

    rev = await _resolve_revolution_for_user(callback.from_user.id, state)
    if not rev:
        await callback.answer("Нет активной революции для агитации.", show_alert=True)
        return

    messages = {
        "emotional": "Друзья! Пора менять власть! Вместе мы сильнее! ⚡",
        "analytical": "Данные показывают рост коррупции. Нужны системные изменения.",
        "targeted": "Если вам надоела текущая система, присоединяйтесь к революции!"
    }
    delta_map = {"emotional": (1, 2), "analytical": (1, 3), "targeted": (1, 2)}
    low, high = delta_map.get(propaganda_type, (1, 2))
    gained = random.randint(low, high)
    ok, msg, payload = await db.boost_revolution_support(int(rev["id"]), gained)
    payload = payload or {}

    supporters = int(payload.get("supporters_count") or rev.get("supporters_count") or 0)
    needed = int(payload.get("supporters_needed") or rev.get("supporters_needed") or 50)
    progress = min(100, round((supporters / max(1, needed)) * 100))

    text = (
        "✅ **ПРИЗЫВ ОТПРАВЛЕН**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Сообщение:\n\"{messages.get(propaganda_type, 'Голосуйте за перемены!')}\"\n\n"
        f"{msg}\n"
        f"Прирост поддержки: +{gained if ok else 0}\n"
        f"Текущие сторонники: {supporters}/{needed}\n"
        f"Прогресс: {progress}%"
    )

    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


# ============================================================================
# СТАТИСТИКА И ИСТОРИЯ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "revolution_stats")
async def revolution_stats(callback: CallbackQuery, state: FSMContext):
    """Статистика по выбранной/активной революции."""
    rev = await _resolve_revolution_for_user(callback.from_user.id, state)
    if not rev:
        text = (
            "📊 СТАТИСТИКА РЕВОЛЮЦИИ\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Сейчас нет активной революции.\n"
            "Запустите новую кампанию или поддержите существующую."
        )
        keyboard = [
            [InlineKeyboardButton(text="⚡ Новая революция", callback_data="start_revolution")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        return

    supporters = int(rev.get("supporters_count") or 0)
    needed = max(1, int(rev.get("supporters_needed") or 50))
    progress = min(100, round((supporters / needed) * 100))

    started_raw = str(rev.get("started_date") or "")
    started_date = started_raw[:16].replace("T", " ") if started_raw else "неизвестно"
    days_active = 1
    try:
        started_dt = datetime.fromisoformat(started_raw)
        diff = datetime.now() - started_dt
        days_active = max(1, diff.days + 1)
    except Exception:
        days_active = 1

    avg_per_day = round(supporters / max(1, days_active), 2)
    missing = max(0, needed - supporters)
    eta_days = int((missing + max(1, int(avg_per_day)) - 1) / max(1, int(avg_per_day))) if missing > 0 else 0
    trend = "растет" if avg_per_day >= 1 else "медленно"

    top_supporters = await db.get_revolution_supporters(int(rev.get("id") or 0), limit=3)
    top_lines = []
    for idx, s in enumerate(top_supporters, start=1):
        name = _display_name_from_row(s, fallback_id=int(s.get("supporter_id") or 0))
        role = s.get("role") or "Сторонник"
        top_lines.append(f"{idx}. {name} ({role})")
    if not top_lines:
        top_lines.append("Пока нет данных.")

    text = (
        f"📊 СТАТИСТИКА РЕВОЛЮЦИИ #{int(rev.get('id') or 0)}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Организатор: {_display_name_from_row(rev, fallback_id=int(rev.get('organizer_id') or 0))}\n"
        f"Старт: {started_date}\n"
        f"Статус: {rev.get('status')}\n\n"
        f"Сторонников: {supporters}/{needed} ({progress}%)\n"
        f"В кампании: {days_active} дн.\n"
        f"Средний прирост: {avg_per_day} в день\n"
        f"Тренд: {trend}\n"
        f"До цели: {missing} (оценка {eta_days} дн.)\n\n"
        "Ядро движения:\n"
        + "\n".join(top_lines)
    )

    keyboard = [
        [InlineKeyboardButton(text="👥 Сторонники", callback_data="revolution_supporters")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")],
    ]

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "revolution_supporters")
async def revolution_supporters(callback: CallbackQuery, state: FSMContext):
    """Список сторонников выбранной/активной революции."""
    rev = await _resolve_revolution_for_user(callback.from_user.id, state)
    if not rev:
        text = (
            "👥 СТОРОННИКИ РЕВОЛЮЦИИ\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Нет активной революции для просмотра."
        )
        keyboard = [
            [InlineKeyboardButton(text="⚡ Новая революция", callback_data="start_revolution")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")],
        ]
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await callback.answer()
        return

    rev_id = int(rev.get("id") or 0)
    supporters = await db.get_revolution_supporters(rev_id, limit=25)
    total = int(rev.get("supporters_count") or len(supporters))

    lines = [
        f"👥 СТОРОННИКИ РЕВОЛЮЦИИ #{rev_id}",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Всего: {total}",
        "",
    ]

    if not supporters:
        lines.append("Пока никто не присоединился.")
    else:
        for idx, s in enumerate(supporters, start=1):
            name = _display_name_from_row(s, fallback_id=int(s.get("supporter_id") or 0))
            role = s.get("role") or "Сторонник"
            joined = str(s.get("joined_date") or "")[:16].replace("T", " ")
            if joined:
                lines.append(f"{idx}. {name} - {role} ({joined})")
            else:
                lines.append(f"{idx}. {name} - {role}")

        hidden_count = max(0, total - len(supporters))
        if hidden_count > 0:
            lines.append("")
            lines.append(f"... и еще {hidden_count} чел.")

    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="revolution_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_campaign")],
    ]

    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data == "revolution_history")
async def revolution_history(callback: CallbackQuery, state: FSMContext):
    """История завершенных революций из БД."""
    history = await db.get_revolution_history(limit=15)
    lines = [
        "📋 ИСТОРИЯ РЕВОЛЮЦИЙ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard = []

    if not history:
        lines.append("Завершенных революций пока нет.")
    else:
        icon_map = {
            "success": "✅",
            "failed": "❌",
            "cancelled": "⛔",
        }
        for rev in history:
            rev_id = int(rev.get("id") or 0)
            status = str(rev.get("status") or "unknown")
            icon = icon_map.get(status, "•")
            ended = str(rev.get("ended_date") or rev.get("started_date") or "")[:16].replace("T", " ")
            supporters = int(rev.get("supporters_count") or 0)
            needed = int(rev.get("supporters_needed") or 0)
            result = str(rev.get("result") or "—")
            lines.append(
                f"{icon} #{rev_id} | {ended}\n"
                f"Организатор: {_display_name_from_row(rev, fallback_id=int(rev.get('organizer_id') or 0))}\n"
                f"Статус: {status} ({result})\n"
                f"Поддержка: {supporters}/{needed}"
            )
            lines.append("")
            keyboard.append([
                InlineKeyboardButton(text=f"📖 Манифест #{rev_id}", callback_data=f"view_manifesto_{rev_id}")
            ])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="revolution_menu")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

