"""
revolutions.py - Система революций и свержения правительства
Смена власти через народное волеизъявление
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import get_back_button

logger = logging.getLogger(__name__)
router = Router()


class RevolutionStates(StatesGroup):
    """Состояния для системы революций"""
    revolution_menu = State()
    selecting_new_leader = State()
    sponsoring_revolution = State()
    joining_revolution = State()
    creating_manifesto = State()


# ============================================================================
# ГЛАВНОЕ МЕНЮ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "revolution_menu")
async def revolution_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню революций"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
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
        [InlineKeyboardButton("⚡ Запустить революцию", callback_data="start_revolution")],
        [InlineKeyboardButton("👥 Активные революции", callback_data="view_active_revolutions")],
        [InlineKeyboardButton("📋 История", callback_data="revolution_history")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(RevolutionStates.revolution_menu)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
        text += f"❌ У вас недостаточно денег!\n"
        text += f"Требуется: $100,000\n"
        text += f"У вас: ${user.get('balance', 0):.2f}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="revolution_menu")]
        ]
    else:
        text += "Вы готовы спонсировать революцию?"
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, начать!", callback_data="confirm_sponsor_revolution")],
            [InlineKeyboardButton("❌ Отмена", callback_data="revolution_menu")]
        ]
    
    await state.set_state(RevolutionStates.sponsoring_revolution)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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


@router.message(RevolutionStates.creating_manifesto, F.text)
async def process_revolution_manifesto(message: Message, state: FSMContext):
    """Обработка манифеста революции"""
    data = await state.get_data()
    user_id = data.get('user_id')
    manifesto = message.text[:500]
    
    user = await db.get_user(user_id) or {} or {}
    
    # Создаём революцию в БД
    # await db.create_revolution(
    #     organizer_id=user_id,
    #     manifesto=manifesto,
    #     supporters_needed=50,
    #     budget_spent=100000
    # )
    
    # Списываем средства
    # await db.update_user(user_id, balance=user.get('balance', 0) - 100000)
    
    text = (
        "🔴 **РЕВОЛЮЦИЯ ОБЪЯВЛЕНА!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Организатор:** {user.get('full_name')}\n"
        f"**Затраты:** $100,000\n"
        f"**Манифест:**\n"
        f"\"{manifesto}\"\n\n"
        f"**Статус:** Ожидание поддержки\n"
        f"**Нужно сторонников:** 50\n"
        f"**Текущей:** 1 (организатор)\n\n"
        "Игроки могут присоединиться к революции и голосовать за изменения!"
    )
    
    keyboard = [
        [InlineKeyboardButton("📣 Агитация", callback_data="revolution_campaign")],
        [InlineKeyboardButton("👥 Сторонники", callback_data="revolution_supporters")],
        [InlineKeyboardButton("🔙 В меню", callback_data="revolution_menu")]
    ]
    
    await state.set_state(RevolutionStates.joining_revolution)
    await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ============================================================================
# ПРОСМОТР АКТИВНЫХ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "view_active_revolutions")
async def view_active_revolutions(callback: CallbackQuery, state: FSMContext):
    """Просмотр активных революций"""
    text = (
        "🔴 **АКТИВНЫЕ РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Получаем активные революции из БД
    # revolutions = await db.get_active_revolutions()
    
    revolutions = []  # Заглушка
    
    if not revolutions:
        text += "Активные революции отсутствуют.\n"
        text += "\nНачните революцию, чтобы изменить власть!"
    else:
        for i, rev in enumerate(revolutions[:10]):
            text += (
                f"\n{i+1}. **Революция #{rev.get('id')}**\n"
                f"   Организатор: {rev.get('organizer_name')}\n"
                f"   Сторонников: {rev.get('supporters_count', 0)}/50\n"
                f"   Прогресс: {rev.get('supporters_count', 0) * 2}%\n"
            )
    
    keyboard = [
        [InlineKeyboardButton("⚡ Новая революция", callback_data="start_revolution")],
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# ПРИСОЕДИНЕНИЕ К РЕВОЛЮЦИИ
# ============================================================================

@router.callback_query(F.data == "join_revolution")
async def join_revolution(callback: CallbackQuery, state: FSMContext):
    """Присоединение к революции"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "👥 **ПРИСОЕДИНИСЬ К РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите, к какой революции присоединиться:\n\n"
        "1. 🔴 Революция против коррупции\n"
        "   Сторонников: 23/50\n"
        "   Прогресс: 46%\n\n"
        "Нажмите кнопку ниже для присоединения:\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Присоединиться", callback_data="confirm_join_revolution_1")],
        [InlineKeyboardButton("📖 Манифест", callback_data="view_manifesto_1")],
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_menu")]
    ]
    
    await state.set_state(RevolutionStates.joining_revolution)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_join_revolution_"))
async def confirm_join_revolution(callback: CallbackQuery, state: FSMContext):
    """Подтверждение присоединения к революции"""
    revolution_id = callback.data.replace("confirm_join_revolution_", "")
    user_id = callback.from_user.id
    
    # await db.add_revolution_supporter(user_id, int(revolution_id))
    
    text = (
        "✅ **ВЫ ПРИСОЕДИНИЛИСЬ!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Поздравляем! Вы- официальный сторонник революции.\n\n"
        "**ВАША РОЛЬ:**\n"
        "🗣️ Вы можете агитировать других игроков\n"
        "📢 Публиковать революционные материалы\n"
        "👥 Собирать подписи в поддержку\n"
        "🎯 Участвовать в голосовании при завершении\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data="revolution_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("view_manifesto_"))
async def view_manifesto(callback: CallbackQuery, state: FSMContext):
    """Просмотр манифеста выбранной революции."""
    revolution_id = callback.data.replace("view_manifesto_", "")
    text = (
        f"📖 **МАНИФЕСТ РЕВОЛЮЦИИ #{revolution_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Раздел манифестов находится в разработке."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="join_revolution")],
        [InlineKeyboardButton("🏠 В меню", callback_data="revolution_menu")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
        [InlineKeyboardButton("📢 Сделать призыв", callback_data="make_propaganda_call")],
        [InlineKeyboardButton("📊 Статистика", callback_data="revolution_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
        [InlineKeyboardButton("⚡ Эмоциональный", callback_data="propaganda_emotional")],
        [InlineKeyboardButton("📊 Аналитический", callback_data="propaganda_analytical")],
        [InlineKeyboardButton("🎯 Целевой", callback_data="propaganda_targeted")],
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("propaganda_"))
async def send_propaganda(callback: CallbackQuery, state: FSMContext):
    """Отправка пропагандистского материала"""
    propaganda_type = callback.data.replace("propaganda_", "")
    
    messages = {
        "emotional": "Друзья! Пора менять власть! Вместе мы сильнее! ⚡",
        "analytical": "Данные показывают рост коррупции на 30%. Нужны изменения.",
        "targeted": "Если вам надоела текущая система, присоединяйтесь к революции!"
    }
    
    text = (
        f"✅ **ПРИЗЫВ ОТПРАВЛЕН**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Сообщение:**\n"
        f"\"{messages.get(propaganda_type, 'Голосуйте за перемены!')}\"\n\n"
        f"**Результат:**\n"
        f"+1 сторонник\n"
        f"Текущей: 24/50\n"
        f"Прогресс: 48%\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# СТАТИСТИКА И ИСТОРИЯ РЕВОЛЮЦИЙ
# ============================================================================

@router.callback_query(F.data == "revolution_stats")
async def revolution_stats(callback: CallbackQuery, state: FSMContext):
    """Статистика революции"""
    text = (
        "📊 **СТАТИСТИКА РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Сторонников:** 24/50 (48%)\n"
        "**Дней осталось:** 7\n"
        "**Среднее в день:** 3.4 сторонника\n"
        "**Тренд:** ↗️ Растет\n\n"
        "**ТОП АГИТАТОРОВ:**\n"
        "1. Вы - 4 призыва\n"
        "2. @username2 - 2 призыва\n"
        "3. @username3 - 1 призыв\n\n"
        "При достижении 50 сторонников произойдёт голосование!\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "revolution_supporters")
async def revolution_supporters(callback: CallbackQuery, state: FSMContext):
    """Список сторонников революции"""
    text = (
        "👥 **СТОРОННИКИ РЕВОЛЮЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Всего: 24 сторонника\n\n"
    )
    
    supporters = [
        ("username1", "Организатор"),
        ("username2", "Активист"),
        ("username3", "Участник"),
        ("username4", "Участник"),
        ("username5", "Участник"),
    ]
    
    for i, (username, role) in enumerate(supporters[:10]):
        text += f"{i+1}. @{username} - **{role}**\n"
    
    text += "\n... и ещё 19 человек"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_campaign")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "revolution_history")
async def revolution_history(callback: CallbackQuery, state: FSMContext):
    """История революций"""
    text = (
        "📋 **ИСТОРИЯ РЕВОЛЮЦИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**УСПЕШНЫЕ РЕВОЛЮЦИИ:**\n\n"
        "✅ 2026-01-15: Смержение демократии\n"
        "   Что: Монархия установлена\n"
        "   Организатор: @kingmaker\n"
        "   Сторонников: 87/100\n\n"
        "✅ 2025-12-20: Восстання против монархии\n"
        "   Что: Вернулась демократия\n"
        "   Организатор: @freedomfighter\n"
        "   Сторонников: 92/100\n\n"
        "**НЕУДАЧНЫЕ:**\n\n"
        "❌ 2025-11-10: Переворот\n"
        "   Не набрали поддержку: 23/100\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="revolution_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()
