"""
handlers_part3.py - Обработчики полиции, ФБР, суда и банка
Асинхронные handlers для aiogram 3.x
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import get_back_button, MenuCallback
from states import OrganizationStates

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# ПОЛИЦИЯ
# ============================================================================

@router.callback_query(F.data == "police_menu")
async def police_menu(callback: CallbackQuery, state: FSMContext):
    """Меню полиции"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    # Проверка, работает ли в полиции
    if user.get('role') != 'Полицейский' and user.get('organization') != 'Полиция':
        text = "❌ Вы не работаете в полиции"
        await callback.message.edit_text(text, reply_markup=get_back_button())
        await callback.answer("Только полицейские имеют доступ", show_alert=True)
        return
    
    text = (
        "🚓 **ПОЛИЦИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Поддерживайте порядок в государстве.\n"
        "Арестовывайте преступников и проводите расследования.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Для поиска", callback_data="police_search_suspects")],
        [InlineKeyboardButton("⛓️ Мои аресты", callback_data="police_my_arrests")],
        [InlineKeyboardButton("📋 Расследования", callback_data="police_investigations")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "police_search_suspects")
async def police_search_suspects(callback: CallbackQuery, state: FSMContext):
    """Поиск подозреваемых"""
    text = (
        "🔍 **РОЗЫСК ПОДОЗРЕВАЕМЫХ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Список активных подозреваемых:\n\n"
        "1. Не найдено подозреваемых\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="police_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "police_my_arrests")
async def police_my_arrests(callback: CallbackQuery, state: FSMContext):
    """Список моих арестов"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        f"🚨 **МОИ АРЕСТЫ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Всего арестов:** {user.get('arrests_made', 0)}\n"
        f"**Активные случаи:** 0\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="police_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "police_investigations")
async def police_investigations(callback: CallbackQuery, state: FSMContext):
    """Расследования"""
    text = (
        "📋 **РАССЛЕДОВАНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Активные расследования отсутствуют.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="police_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# ФБР - ПЕРЕХВАТ И НАБЛЮДЕНИЕ
# ============================================================================

@router.callback_query(F.data == "fbi_menu")
async def fbi_menu(callback: CallbackQuery, state: FSMContext):
    """Меню ФБР"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    # Проверка, работает ли в ФБР
    if user.get('role') != 'Агент ФБР' and user.get('organization') != 'ФБР':
        text = "❌ Вы не работаете в ФБР"
        await callback.message.edit_text(text, reply_markup=get_back_button())
        await callback.answer("Только агенты ФБР имеют доступ", show_alert=True)
        return
    
    text = (
        "🕵️ **ФЕДЕРАЛЬНОЕ БЮРО РАССЛЕДОВАНИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Проводите разведку и тотальный надзор.\n"
        "Перехватывайте сообщения и контролируйте население.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("📡 Перехват", callback_data="fbi_intercept_messages")],
        [InlineKeyboardButton("📊 Статистика", callback_data="fbi_statistics")],
        [InlineKeyboardButton("⚔️ Операции", callback_data="fbi_operations")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "fbi_intercept_messages")
async def fbi_intercept_messages(callback: CallbackQuery, state: FSMContext):
    """Перехват сообщений"""
    text = (
        "📡 **ПЕРЕХВАТ СООБЩЕНИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔒 **ВЫСОКОСЕКРЕТНАЯ ИНФОРМАЦИЯ**\n\n"
        "Последние перехваченные сообщения:\n\n"
        "Нет активных сообщений для перехвата.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="fbi_intercept_messages")],
        [InlineKeyboardButton("🔙 Назад", callback_data="fbi_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "fbi_statistics")
async def fbi_statistics(callback: CallbackQuery, state: FSMContext):
    """Статистика ФБР"""
    text = (
        "📊 **СТАТИСТИКА НАБЛЮДЕНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📱 **Перехвачено сообщений:** 0\n"
        "📞 **Мониторится игроков:** 0\n"
        "🚨 **Подозрительных действий:** 0\n"
        "⚠️ **Угроз безопасности:** 0\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="fbi_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "fbi_operations")
async def fbi_operations(callback: CallbackQuery, state: FSMContext):
    """Операции ФБР"""
    text = (
        "⚔️ **СПЕЦОПЕРАЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Активные операции:\n\n"
        "Нет активных операций.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🆕 Начать", callback_data="fbi_track_player")],
        [InlineKeyboardButton("🔙 Назад", callback_data="fbi_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# СУД
# ============================================================================

@router.callback_query(F.data == "court_menu")
async def court_menu(callback: CallbackQuery, state: FSMContext):
    """Меню суда"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "⚖️ **СУДЕБНАЯ СИСТЕМА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Рассматривайте дела и выносите приговоры.\n"
    )
    
    if user.get('role') == 'Судья':
        keyboard = [
            [InlineKeyboardButton("📋 Дела", callback_data="court_cases")],
            [InlineKeyboardButton("👥 Обвиняемые", callback_data="court_defendants")],
            [InlineKeyboardButton("📜 История", callback_data="court_history")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Дела в суде", callback_data="court_cases")],
            [InlineKeyboardButton("📜 Мой статус", callback_data="court_status")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
        ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "court_cases")
async def court_cases(callback: CallbackQuery, state: FSMContext):
    """Список дел суда"""
    text = (
        "📋 **ДЕЛА В СУДЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Активные дела:\n\n"
        "Дел не найдено.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="court_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "court_defendants")
async def court_defendants(callback: CallbackQuery, state: FSMContext):
    """Обвиняемые в суде"""
    text = (
        "👥 **ОБВИНЯЕМЫЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Активные обвинения:\n\n"
        "Нет обвиняемых.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="court_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "court_history")
async def court_history(callback: CallbackQuery, state: FSMContext):
    """История судебных дел"""
    user_id = callback.from_user.id
    
    text = (
        "📜 **ИСТОРИЯ ДЕЛА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Закрытые дела:\n\n"
        "История пуста.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="court_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "court_status")
async def court_status(callback: CallbackQuery, state: FSMContext):
    """Статус в судебной системе"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "📋 **ВАШ СУДЕБНЫЙ СТАТУС**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Обвинений:** 0\n"
        f"**Приговоров:** 0\n"
        f"**Судимостей:** 0\n"
        "**Статус:** Чист ✅\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="court_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# БАНК И КРЕДИТЫ
# ============================================================================

@router.message(Command("loan"))
@router.callback_query(F.data == "bank_menu")
async def bank_menu(event, state: FSMContext):
    """Меню банка"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🏦 **ЦЕНТРАЛЬНЫЙ БАНК**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Берите кредиты для развития.\n"
        "Управляйте своими финансами.\n\n"
    )
    
    text += f"💰 **Ваш баланс:** ${user.get('balance', 0):.2f}\n"
    text += f"💳 **В банке:** ${user.get('bank', 0):.2f}\n"
    
    if user.get('tax_debt', 0) > 0:
        text += f"⚠️ **Налоговый долг:** ${user.get('tax_debt', 0):.2f}\n"
    
    keyboard = [
        [InlineKeyboardButton("📝 Кредит", callback_data="loan_request")],
        [InlineKeyboardButton("💸 Депозит", callback_data="bank_deposit")],
        [InlineKeyboardButton("📊 История", callback_data="bank_history")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "loan_request")
async def loan_request_menu(callback: CallbackQuery, state: FSMContext):
    """Заявка на кредит"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "📝 **ЗАЯВКА НА КРЕДИТ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Процентная ставка:** 15% в месяц\n"
        "**Максимальная сумма:** $50,000\n"
        "**Минимум:** $1,000\n\n"
        "Укажите сумму кредита (в ответе на это сообщение):\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="bank_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "bank_deposit")
async def bank_deposit(callback: CallbackQuery, state: FSMContext):
    """Депозит в банке"""
    text = (
        "💸 **БАНКОВСКИЙ ДЕПОЗИТ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Процент:** 2% в месяц на ваш вклад\n"
        "**Минимум:** $100\n\n"
        "Укажите сумму для пополнения:\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="bank_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "bank_history")
async def bank_history(callback: CallbackQuery, state: FSMContext):
    """История операций банка"""
    text = (
        "📊 **ИСТОРИЯ ОПЕРАЦИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Последние операции:\n\n"
        "История отсутствует.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="bank_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# БОЛЬНИЦА И ЛЕЧЕНИЕ
# ============================================================================

@router.message(Command("med"))
@router.callback_query(F.data == "hospital_menu")
async def hospital_menu(event, state: FSMContext):
    """Меню больницы"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🏥 **БОЛЬНИЦА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Лечение и медицинское обслуживание.\n\n"
    )
    
    if user.get('in_hospital'):
        text += f"⚠️ **Вы находитесь на лечении**\n"
        text += f"**Выписка:** {user.get('hospital_until', 'Неизвестно')}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🩺 Прием", callback_data="hospital_appointment")],
        [InlineKeyboardButton("📋 История", callback_data="hospital_history")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "hospital_appointment")
async def hospital_appointment(callback: CallbackQuery, state: FSMContext):
    """Прием врача"""
    text = (
        "🩺 **ПРИЕМ ВРАЧА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Стоимость приема:** $500\n"
        "**Время ожидания:** 1 час\n\n"
        "Запишитесь на прием?\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Записаться", callback_data="hospital_confirm_appointment")],
        [InlineKeyboardButton("❌ Отмена", callback_data="hospital_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "hospital_confirm_appointment")
async def hospital_confirm_appointment(callback: CallbackQuery, state: FSMContext):
    """Подтверждение приема"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    if user.get('balance', 0) < 500:
        text = "❌ **Недостаточно денег**\nТребуется $500"
        await callback.message.edit_text(text, reply_markup=get_back_button("hospital_menu"))
        await callback.answer("Нет денег", show_alert=True)
        return
    
    text = (
        "✅ **ПРИЕМ ЗАВЕРШЁН**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Вы здоровы! Лечение восстановило ваше здоровье на 100%.\n"
    )
    
    await callback.message.edit_text(text, reply_markup=get_back_button("hospital_menu"))
    await callback.answer()


@router.callback_query(F.data == "hospital_history")
async def hospital_history(callback: CallbackQuery, state: FSMContext):
    """История посещений больницы"""
    text = (
        "📋 **ИСТОРИЯ ЛЕЧЕНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ваши посещения:\n\n"
        "История пуста.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="hospital_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()
