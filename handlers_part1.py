"""
handlers.py - Часть 1/3: Основные обработчики (главное меню, команды)
aiogram 3.x асинхронные обработчики
"""

import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import db
from states import MainStates, ElectionStates
from keyboards import (
    get_main_menu_keyboard,
    get_back_button,
    get_election_menu_keyboard,
    ElectionCallback,
    PartyCallback,
)

# Создаем роутер для основных обработчиков
router = Router()


async def _dispatch_menu_action(callback: CallbackQuery, state: FSMContext, action: str):
    """Совместимость со старым callback_data формата menu:<action>."""
    action_aliases = {
        "org_list": "orgs_main",
        "government_menu": "president_admin_panel",
        "business_list": "biz_menu",
        "education_menu": "edu_menu",
        "property_menu": "prop_menu",
        "contracts_menu": "market_menu",
        "protest_menu": "revolution_menu",
        "finance_menu": "bank_menu",
        "loan_menu": "bank_menu",
        "treatment_menu": "hospital_menu",
        "tutorial": "tutorial_menu",
    }
    target = action_aliases.get(action, action)

    if target == "orgs_main":
        from handlers_part2 import organizations_menu
        await organizations_menu(callback, state)
        return

    if target == "biz_menu":
        from handlers_part2 import business_menu
        await business_menu(callback, state)
        return

    if target == "work_menu":
        from handlers_part2 import citizen_work_menu
        await citizen_work_menu(callback, state)
        return

    if target == "edu_menu":
        from handlers_part2 import education_menu
        await education_menu(callback, state)
        return

    if target == "prop_menu":
        from handlers_part2 import property_menu
        await property_menu(callback, state)
        return

    if target == "market_menu":
        from handlers_part2 import market_menu
        await market_menu(callback, state)
        return

    if target == "court_menu":
        from handlers_part3 import court_menu
        await court_menu(callback, state)
        return

    if target == "bank_menu":
        from handlers_part3 import bank_menu
        await bank_menu(callback, state)
        return

    if target == "hospital_menu":
        from handlers_part3 import hospital_menu
        await hospital_menu(callback, state)
        return

    if target == "revolution_menu":
        from revolutions import revolution_menu
        await revolution_menu(callback, state)
        return

    if target == "president_admin_panel":
        from presidential_admin import president_admin_panel
        await president_admin_panel(callback, state)
        return

    if target == "profile_menu":
        await profile_menu(callback, state)
        return

    if target == "daily_bonus":
        await daily_bonus(callback, state)
        return

    if target == "help_menu":
        await help_menu(callback)
        return

    if target == "tutorial_menu":
        await tutorial_menu(callback)
        return

    if target == "private_org_list":
        await private_org_placeholder(callback)
        return

    if target == "gang_list":
        await gang_placeholder(callback)
        return

    await callback.answer("❌ Раздел пока недоступен.", show_alert=True)


@router.callback_query(F.data.startswith("menu:"))
async def legacy_menu_router(callback: CallbackQuery, state: FSMContext):
    """Маршрутизация старых callback кнопок menu:<action>."""
    action = (callback.data or "").split(":", 1)[1] if ":" in (callback.data or "") else ""
    await _dispatch_menu_action(callback, state, action)


@router.callback_query(F.data == "tutorial_menu")
async def tutorial_menu(callback: CallbackQuery):
    """Кнопка обучения (временный экран)."""
    await callback.answer()
    text = (
        "🎓 **ОБУЧЕНИЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Пошаговый интерактивный туториал сейчас обновляется.\n"
        "Пока можно начать с команд:\n"
        "• /start\n"
        "• /help\n"
        "• /work\n"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_back_button(),
        parse_mode='Markdown',
    )


@router.callback_query(F.data == "private_org_list")
async def private_org_placeholder(callback: CallbackQuery):
    """Временная заглушка для раздела частных организаций."""
    await callback.answer()
    await callback.message.edit_text(
        "🏢 **ЧАСТНЫЕ ОРГАНИЗАЦИИ**\n━━━━━━━━━━━━━━━━━━━━\n\nРаздел в разработке.",
        reply_markup=get_back_button(),
        parse_mode='Markdown',
    )


@router.callback_query(F.data == "gang_list")
async def gang_placeholder(callback: CallbackQuery):
    """Временная заглушка для раздела банд."""
    await callback.answer()
    await callback.message.edit_text(
        "🕶️ **БАНДЫ**\n━━━━━━━━━━━━━━━━━━━━\n\nРаздел в разработке.",
        reply_markup=get_back_button(),
        parse_mode='Markdown',
    )


# ==================== BACK_TO_MAIN - ПРИОРИТЕТНЫЙ ОБРАБОТЧИК ====================

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    try:
        await callback.answer()
        
        # Получаем данные пользователя
        user = await db.get_user(callback.from_user.id)
        is_new = not user.get('tutorial_completed') if user else False
        
        # Проверяем, есть ли активные выборы
        has_president = await db.check_has_president()
        gov = await db.get_organization("Правительство")
        has_elections = False
        election_id = -1
        
        if gov and not has_president:
            await db.ensure_presidential_election(duration_hours=30)
            active_pres = await db.get_active_presidential_election()
            has_elections = active_pres is not None
            if active_pres:
                election_id = active_pres['id']
        
        # Если пользователь находится в состоянии выборов — вернем в меню выборов
        current_state = await state.get_state()
        if current_state and current_state.startswith("ElectionStates"):
            await state.set_state(ElectionStates.global_lock)
            try:
                await callback.edit_message_text(
                    "🗳️ **ПЕРЕХОД В МЕНЮ ВЫБОРОВ**",
                    reply_markup=get_election_menu_keyboard(election_id) if has_elections else get_back_button(),
                    parse_mode='Markdown'
                )
                return
            except Exception:
                # если не получилось отредактировать, отправляем новое сообщение
                await callback.message.answer(
                    "🗳️ **Меню выборов**",
                    reply_markup=get_election_menu_keyboard(election_id) if has_elections else get_back_button()
                )
                return

        await state.set_state(MainStates.main_menu)

        text = (
            "🏛️ **Государство Онлайн**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Добро пожаловать! Выберите раздел для работы:\n"
        )
        
        await callback.edit_message_text(
            text,
            reply_markup=get_main_menu_keyboard(is_new, has_elections, election_id),
            parse_mode='Markdown'
        )
    except Exception:
        # Если edit_text не сработал, отправляем новое сообщение
        try:
            await callback.message.answer(
                "🏛️ **Государство Онлайн**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Добро пожаловать! Выберите раздел для работы:",
                reply_markup=get_main_menu_keyboard(False, False, -1),
                parse_mode='Markdown'
            )
        except Exception:
            pass


# ==================== КОМАНДА /START ====================

@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    """Обработка команды /start"""
    
    # Создаем/обновляем пользователя
    user = await db.create_or_update_user(
        message.from_user.id,
        message.from_user.username or "",
        f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
    )
    
    # Проверяем, прошел ли пользователь обучение
    is_new = not user.get('tutorial_completed')
    
    # Проверяем, есть ли активные выборы и нет ли президента
    has_president = await db.check_has_president()
    gov = await db.get_organization("Правительство")
    has_elections = False
    
    if gov and not has_president:
        await db.ensure_presidential_election(duration_hours=30)
        active_pres = await db.get_active_presidential_election()
        has_elections = active_pres is not None
    
    # Если выборы активны, показываем режим глобальной блокировки
    if has_elections:
        await state.set_state(ElectionStates.global_lock)
        
        await message.answer(
            "🗳️ **ПРЕЗИДЕНТСКИЕ ВЫБОРЫ**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ **ВНИМАНИЕ!**\n\n"
            "В настоящий момент идут выборы президента государства!\n"
            "Объедините друзей в партию и победите на выборах!\n\n"
            "Выберите действие:",
            reply_markup=get_election_menu_keyboard(active_pres['id']) if active_pres else get_back_button()
        )
    else:
        # Нормальное начало
        await state.set_state(MainStates.main_menu)
        
        greeting = (
            "🏛️ **Государство Онлайн**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        if is_new:
            greeting = (
                "👋 **Добро пожаловать, новичок!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Чтобы быстро разобраться в игре, рекомендуем пройти обучение.\n"
                "Вы получите начальный капитал и поймете, как всё работает.\n\n"
            ) + greeting
        
        greeting += (
            "В этой игре вы можете:\n"
            "• Работать на государстве или в бизнесе\n"
            "• Участвовать в выборах и политике\n"
            "• Создавать свои организации и бизнесы\n"
            "• Взаимодействовать с другими игроками\n"
            "• Участвовать в революциях и восстаниях\n\n"
            "Выберите раздел:"
        )
        
        await message.answer(
            greeting,
            reply_markup=get_main_menu_keyboard(is_new, has_elections, -1)
        )


# ==================== КОМАНДА /HELP ====================

@router.message(Command("help"))
async def help_command(message: Message):
    """Справка по командам"""
    
    help_text = (
        "ℹ️ **СПРАВКА И КОМАНДЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "📋 **ОСНОВНЫЕ КОМАНДЫ:**\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/profile — ваш профиль\n"
        "/menu — главное меню (быстрый доступ)\n\n"
        
        "🏛️ **ОРГАНИЗАЦИИ:**\n"
        "/orgs — все государственные организации\n"
        "/myorg — моя организация (если состою)\n"
        "/tasks — задания организаций\n\n"
        
        "💼 **РАБОТА И БИЗНЕС:**\n"
        "/work — гражданская работа\n"
        "/biz — список бизнесов\n"
        "/priv — частные организации\n\n"
        
        "📚 **ОБРАЗОВАНИЕ:**\n"
        "/edu — учебные программы\n"
        "/tutorial — пройти обучение заново\n\n"
        
        "💰 **ФИНАНСЫ:**\n"
        "/loan — заявка на кредит\n"
        "/bank — меню банка\n"
        "/daily — бонус дня\n\n"
        
        "⚖️ **ПРАВОСУДИЕ:**\n"
        "/court — суд и судебные дела\n"
        "/police — меню полиции\n\n"
        
        "🏥 **ЗДОРОВЬЕ:**\n"
        "/med — лечение в больнице\n\n"
        
        "🏠 **ИМУЩЕСТВО:**\n"
        "/prop — недвижимость\n"
        "/gang — банды и криминал\n\n"
        
        "📣 **ПОЛИТИКА:**\n"
        "/government — система правления\n"
        "/protest — митинги и восстания\n"
        "/revolution — революции\n\n"
        
        "📝 **ДРУГОЕ:**\n"
        "/market — контрактная биржа\n"
        "/id — узнать ID игрока (reply на сообщение)\n\n"
        
        "ℹ️ **ИНФОРМАЦИЯ:**\n"
        "В группах бот отвечает только на команды.\n"
        "Для полного доступа напишите в личные сообщения боту.\n"
    )
    
    await message.answer(help_text, reply_markup=get_back_button())


# ==================== МЕНЮ ПОМОЩИ ====================

@router.callback_query(F.data == "help_menu")
async def help_menu(callback: CallbackQuery):
    """Меню справки"""
    await callback.answer()
    
    help_text = (
        "ℹ️ **СПРАВКА И ПОМОЩЬ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "🎮 **ЭТО ПОЛИТИЧЕСКАЯ СИМУЛЯЦИЯ**\n\n"
        
        "В этой игре вы можете:\n\n"
        
        "👨‍💼 **КАРЬЕРА:**\n"
        "• Работать в госорганизациях (Полиция, Больница, Суд и т.д.)\n"
        "• Получать зарплату и повышения\n"
        "• Подниматься на руководящие должности\n\n"
        
        "💼 **БИЗНЕС:**\n"
        "• Создавать свои бизнесы\n"
        "• Нанимать сотрудников\n"
        "• Получать прибыль и платить налоги\n\n"
        
        "🗳️ **ПОЛИТИКА:**\n"
        "• Участвовать в выборах\n"
        "• Голосовать за кандидатов\n"
        "• Становиться президентом (максимальная власть!)\n\n"
        
        "💣 **РЕВОЛЮЦИЯ:**\n"
        "• Организовывать восстания\n"
        "• Менять форму правления\n"
        "• Свергать неугодных лидеров\n\n"
        
        "💰 **ЭКОНОМИКА:**\n"
        "• Брать кредиты в банке\n"
        "• Платить налоги государству\n"
        "• Инвестировать в недвижимость\n"
        "• Торговать на контрактной бирже\n\n"
        
        "📚 **РАЗВИТИЕ:**\n"
        "• Учиться в университете\n"
        "• Повышать свой уровень образования\n"
        "• Становиться преподавателем\n\n"
        
        "⚖️ **ПРАВОСУДИЕ:**\n"
        "• Арестовывать преступников (если полицейский)\n"
        "• Судить дела (если судья)\n"
        "• Защищаться в суде\n\n"
        
        "🕵️ **РАССЛЕДОВАНИЯ:**\n"
        "• ФБР может перехватывать письма\n"
        "• Вести расследования\n"
        "• Раскрывать преступления\n\n"
        
        "⚠️ **ВАЖНО:**\n"
        "• Все ваши действия влияют на репутацию\n"
        "• Налоги и долги отслеживаются автоматически\n"
        "• Президент имеет полную власть над системой\n\n"
        
        "💡 **СОВЕТ:**\n"
        "Начните с малого - устройтесь на работу в государстве "
        "или в бизнес, получайте опыт и развивайте свой персонаж!"
    )
    
    await callback.edit_message_text(
        help_text,
        reply_markup=get_back_button(),
        parse_mode='Markdown'
    )



# ==================== ID КОМАНДА ====================

@router.message(Command("id"))
async def id_command(message: Message):
    """Узнать ID пользователя"""
    
    # Если ответ на сообщение - показываем ID цели
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        await message.answer(
            f"👤 **{target.first_name or target.username or 'User'}**\n"
            f"ID: `{target.id}`",
            parse_mode='Markdown'
        )
    else:
        # Показываем свой ID
        user = await db.get_user(message.from_user.id)
        await message.answer(
            f"👤 **{user.get('full_name', 'Вы')}**\n"
            f"Ваш ID: `{message.from_user.id}`",
            parse_mode='Markdown'
        )


# ==================== ПРОФИЛЬ ====================

@router.callback_query(F.data == "profile_menu")
@router.message(Command("profile"))
async def profile_menu(update, state: FSMContext):
    """Профиль пользователя"""
    
    if isinstance(update, Message):
        message = update
        user = await db.get_user(message.from_user.id)
        await state.set_state(MainStates.main_menu)
    else:
        callback = update
        await callback.answer()
        user = await db.get_user(callback.from_user.id)
        message = callback
    
    if not user:
        await message.answer("❌ Профиль не найден")
        return
    
    # Получаем дополнительную информацию
    org = await db.get_organization(user.get('organization')) if user.get('organization') else None
    
    profile_text = (
        f"👤 **{user.get('full_name', 'Неизвестно')}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"🆔 **ID:** {user['user_id']}\n"
        f"📱 **Username:** @{user.get('username', 'not_set')}\n\n"
        
        f"💰 **ФИНАНСЫ:**\n"
        f"• Баланс: ${user.get('balance', 0):,.0f}\n"
        f"• Налоговый долг: ${user.get('tax_debt', 0):,.0f}\n"
        f"• Всего налогов уплачено: ${user.get('total_tax_paid', 0):,.0f}\n\n"
        
        f"📊 **СТАТИСТИКА:**\n"
        f"• Уровень: {user.get('level', 1)}\n"
        f"• Образование: {user.get('education', 1)}\n"
        f"• Опыт: {user.get('experience', 0)}\n"
        f"• Репутация: {user.get('reputation', 50):.1f}/100\n\n"
        
        f"💼 **ЗАНЯТОСТЬ:**\n"
    )
    
    if org:
        profile_text += (
            f"• Организация: {org['name']}\n"
            f"• Должность: {user.get('role', 'Неизвестно')}\n"
            f"• Зарплата: ${user.get('salary', 0)}/месяц\n\n"
        )
    else:
        profile_text += "• Не состоит в организации\n\n"
    
    if user.get('citizen_job'):
        profile_text += (
            f"👨‍💼 **ГРАЖДАНСКАЯ РАБОТА:**\n"
            f"• Должность: {user.get('citizen_job')}\n"
            f"• Зарплата: ${user.get('citizen_salary', 0)}/месяц\n\n"
        )
    
    profile_text += (
        f"🏥 **ЗДОРОВЬЕ:**\n"
        f"• Состояние: {user.get('life_state', 'alive')}\n"
        f"• Травма: {user.get('injury_severity', 'нет')}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Финансы", callback_data="profile_finance")],
        [InlineKeyboardButton("📊 Статистика", callback_data="profile_stats")],
        [InlineKeyboardButton("💌 Письма", callback_data="profile_messages")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
    ]
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    if isinstance(update, Message):
        await update.answer(profile_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')


@router.callback_query(F.data == "profile_finance")
async def profile_finance(callback: CallbackQuery):
    """Детализация финансов пользователя."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ Профиль не найден.", reply_markup=get_back_button(callback="back_to_main"))
        return

    text = (
        "💰 **ФИНАНСОВЫЙ ОТЧЕТ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Баланс: ${user.get('balance', 0):,.2f}\n"
        f"• Налоговый долг: ${user.get('tax_debt', 0):,.2f}\n"
        f"• Всего уплачено налогов: ${user.get('total_tax_paid', 0):,.2f}\n"
        f"• Штрафы оплачены: ${user.get('fines_paid', 0):,.2f}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')


@router.callback_query(F.data == "profile_stats")
async def profile_stats(callback: CallbackQuery):
    """Детализация игровой статистики пользователя."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ Профиль не найден.", reply_markup=get_back_button(callback="back_to_main"))
        return

    text = (
        "📊 **СТАТИСТИКА ИГРОКА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Уровень: {user.get('level', 1)}\n"
        f"• Опыт: {user.get('experience', 0)}\n"
        f"• Образование: {user.get('education', 1)}\n"
        f"• Репутация: {user.get('reputation', 50):.1f}/100\n"
        f"• Арестов совершено: {user.get('arrests_made', 0)}\n"
        f"• Преступлений: {user.get('crimes_committed', 0)}\n"
        f"• Вылечено пациентов: {user.get('patients_treated', 0)}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')


@router.callback_query(F.data == "profile_messages")
async def profile_messages(callback: CallbackQuery):
    """Раздел писем (пока базовая заглушка)."""
    await callback.answer()
    text = (
        "💌 **ЛИЧНЫЕ СООБЩЕНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Функция центра сообщений находится в разработке."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_main")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')


# ==================== ЕЖЕДНЕВНЫЙ БОНУС ====================

@router.callback_query(F.data == "daily_bonus")
@router.message(Command("daily"))
async def daily_bonus(update, state: FSMContext):
    """Получить ежедневный бонус"""
    
    if isinstance(update, Message):
        user_id = update.from_user.id
        msg = update
    else:
        user_id = update.from_user.id
        await update.answer()
        msg = update
    
    user = await db.get_user(user_id)
    if not user:
        await msg.answer("❌ История не найдена")
        return
    
    today = datetime.now().date().isoformat()
    
    # Проверяем, а уже ли получал бонус сегодня
    if user.get('last_daily_bonus', '').startswith(today):
        await msg.answer(
            "⏳ **Вы уже получали бонус сегодня!**\n"
            "Приходите завтра для нового раунда.",
            reply_markup=get_back_button()
        )
        return
    
    # Выдаем бонус (случайное значение от 500 до 2000)
    import random
    bonus = random.randint(500, 2000)
    
    new_balance = user.get('balance', 0) + bonus
    await db.update_user(user_id, balance=new_balance, last_daily_bonus=datetime.now().isoformat())
    
    bonus_text = (
        f"✅ **БОНУС ПОЛУЧЕН!**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 **+${bonus:,}**\n\n"
        f"Ваш новый баланс: ${new_balance:,.0f}\n\n"
        f"⏰ Следующий бонус доступен через 24 часа."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
    ]
    
    if isinstance(update, Message):
        await msg.answer(bonus_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    else:
        await msg.edit_message_text(bonus_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
# ==================== ВЫБОРЫ - ОБРАБОТЧИКИ ====================


def _election_back_markup(election_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔙 В меню выборов",
                callback_data=ElectionCallback(action="view_party", election_id=election_id).pack()
            )
        ]]
    )


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup):
    """Надежно отредактировать сообщение, а если нельзя — отправить новое."""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=None)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=None)


async def _resolve_active_election_id(raw_election_id: int) -> int:
    """Получить валидный ID активных президентских выборов."""
    if isinstance(raw_election_id, int) and raw_election_id > 0:
        election = await db.get_election(raw_election_id)
        if election and election.get('status') == 'active':
            return raw_election_id

    active = await db.get_active_presidential_election()
    if active:
        return int(active['id'])

    created = await db.ensure_presidential_election(duration_hours=30)
    if created:
        return int(created)

    return -1


def _format_time_left(end_date_raw: str) -> str:
    try:
        end_date = datetime.fromisoformat(end_date_raw)
        delta = end_date - datetime.now()
        seconds = int(delta.total_seconds())
        if seconds <= 0:
            return "меньше минуты"
        hours, rem = divmod(seconds, 3600)
        minutes, _ = divmod(rem, 60)
        if hours > 0:
            return f"{hours}ч {minutes}м"
        return f"{minutes}м"
    except Exception:
        return "неизвестно"


def _election_stage_label(stage_raw: str | None) -> str:
    stage = (stage_raw or "").strip().lower()
    mapping = {
        "nomination": "Регистрация",
        "registration": "Регистрация",
        "campaign": "Агитация",
        "debates": "Дебаты",
        "voting": "Голосование",
        "finished": "Завершены",
    }
    return mapping.get(stage, "Регистрация")


async def _can_manage_election_stage(user_id: int, election_id: int) -> bool:
    gov = await db.get_government_system()
    leader_id = int((gov or {}).get("current_leader_id") or 0)
    if leader_id == user_id:
        return True

    if leader_id == 0:
        party = await db.get_user_party_for_election(user_id, election_id)
        if party and int(party.get("leader_id") or 0) == user_id:
            return True

    return False


PARTY_INVITE_PAGE_SIZE = 8


def _party_invite_page_cb(party_id: int, election_id: int, page: int) -> str:
    return f"pinvpg:{party_id}:{election_id}:{page}"


def _party_invite_select_cb(party_id: int, election_id: int, user_id: int, page: int) -> str:
    return f"pinvsel:{party_id}:{election_id}:{user_id}:{page}"


def _parse_party_invite_cb(data: str, expected_prefix: str, expected_len: int) -> tuple[int, ...] | None:
    parts = (data or "").split(":")
    if len(parts) != expected_len or parts[0] != expected_prefix:
        return None
    try:
        return tuple(int(x) for x in parts[1:])
    except ValueError:
        return None


async def _render_party_invite_picker(
    callback: CallbackQuery,
    party: dict,
    election_id: int,
    page: int = 0,
    notice: str | None = None,
):
    """Отрисовать список игроков для приглашения в партию."""
    leader_id = callback.from_user.id
    party_id = int(party.get("id") or -1)
    party_name = party.get("name") or "Без названия"

    total = await db.count_invitable_players_for_party(election_id, party_id, leader_id)
    max_page = (total - 1) // PARTY_INVITE_PAGE_SIZE if total > 0 else 0
    page = max(0, min(page, max_page))
    offset = page * PARTY_INVITE_PAGE_SIZE

    players = await db.get_invitable_players_for_party(
        election_id=election_id,
        party_id=party_id,
        leader_id=leader_id,
        limit=PARTY_INVITE_PAGE_SIZE,
        offset=offset,
    )

    lines = [
        "👥 ПРИГЛАШЕНИЕ В ПАРТИЮ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Партия: {party_name}",
    ]
    if notice:
        lines.extend(["", notice])

    if total <= 0:
        lines.extend(["", "Сейчас нет доступных игроков для приглашения."])
    else:
        lines.extend(["", f"Выберите игрока ({offset + 1}-{offset + len(players)} из {total}):"])

    buttons = []
    for player in players:
        target_id = int(player.get("user_id") or 0)
        if target_id <= 0:
            continue
        full_name = (player.get("full_name") or "").strip()
        username = (player.get("username") or "").strip()
        display = full_name or (f"@{username}" if username else f"ID {target_id}")
        if len(display) > 28:
            display = display[:25] + "..."
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {display}",
                callback_data=_party_invite_select_cb(party_id, election_id, target_id, page),
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=_party_invite_page_cb(party_id, election_id, page - 1)))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=_party_invite_page_cb(party_id, election_id, page + 1)))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(
            text="🔙 К моей партии",
            callback_data=PartyCallback(action="view_members", party_id=party_id, election_id=election_id).pack(),
        )
    ])

    await _safe_edit(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons))


async def _send_party_invitation(
    bot,
    party: dict,
    election_id: int,
    leader_id: int,
    invited_user_id: int,
) -> str:
    """Создать приглашение в БД и попытаться отправить уведомление игроку."""
    party_id = int(party.get("id") or -1)
    now = datetime.now().isoformat()
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            '''INSERT INTO party_invitations (party_id, invited_user_id, invited_by_id, created_date, status)
               VALUES (?, ?, ?, ?, 'pending')
               ON CONFLICT(party_id, invited_user_id)
               DO UPDATE SET invited_by_id = excluded.invited_by_id,
                             created_date = excluded.created_date,
                             status = 'pending' ''',
            (party_id, invited_user_id, leader_id, now)
        )
        await conn.commit()

    accept_cb = PartyCallback(
        action="answer_invite",
        party_id=party_id,
        election_id=election_id,
        decision=1,
    ).pack()
    reject_cb = PartyCallback(
        action="answer_invite",
        party_id=party_id,
        election_id=election_id,
        decision=0,
    ).pack()

    try:
        await bot.send_message(
            invited_user_id,
            f"📩 Вас пригласили в партию '{party.get('name')}'.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Принять", callback_data=accept_cb),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=reject_cb),
            ]]),
            parse_mode=None,
        )
        return "Приглашение доставлено игроку."
    except Exception:
        return "Приглашение сохранено, но не удалось отправить личное уведомление игроку."


@router.callback_query(ElectionCallback.filter(F.action == "view"))
async def election_view_brief(callback: CallbackQuery, callback_data: ElectionCallback):
    """Совместимость со старой кнопкой view."""
    await election_view_party(callback, callback_data)


@router.callback_query(ElectionCallback.filter(F.action == "view_party"))
async def election_view_party(callback: CallbackQuery, callback_data: ElectionCallback):
    """Главное меню выборов."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    election = await db.get_election(election_id)
    if not election:
        await _safe_edit(
            callback,
            "❌ Выборы не найдены.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    user_party = await db.get_user_party_for_election(user_id, election_id)
    candidates = await db.get_election_candidates(election_id)
    has_voted = await db.has_user_voted(election_id, user_id)
    can_manage_stage = await _can_manage_election_stage(user_id, election_id)
    stage_label = _election_stage_label(election.get("stage"))

    text_lines = [
        "🗳️ ПРЕЗИДЕНТСКИЕ ВЫБОРЫ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"ID выборов: {election_id}",
        f"Этап: {stage_label}",
        f"До завершения: {_format_time_left(election.get('end_date', ''))}",
        f"Кандидатов: {len(candidates)}",
        f"Проголосовали: {election.get('total_voters', 0)}",
        "",
    ]

    if user_party:
        text_lines.append(
            f"Ваша партия: {user_party.get('name', 'Без названия')} "
            f"({user_party.get('members_count', 1)} чел.)"
        )
    else:
        text_lines.append("Вы пока не состоите в партии.")

    text_lines.append("Вы уже проголосовали." if has_voted else "Вы еще не голосовали.")

    buttons = []
    if not user_party:
        buttons.append([
            InlineKeyboardButton(
                text="🟢 Создать партию",
                callback_data=ElectionCallback(action="create_party", election_id=election_id).pack(),
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="📜 Список партий",
                callback_data=ElectionCallback(action="list_parties", election_id=election_id).pack(),
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="📋 Моя партия",
                callback_data=PartyCallback(action="view_members", party_id=user_party['id'], election_id=election_id).pack(),
            )
        ])
        if int(user_party.get('leader_id') or 0) == user_id:
            buttons.append([
                InlineKeyboardButton(
                    text="👥 Пригласить в партию",
                    callback_data=PartyCallback(action="invite", party_id=user_party['id'], election_id=election_id).pack(),
                )
            ])

    buttons.extend([
        [InlineKeyboardButton(text="📝 Выдвинуться", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🎤 Дебаты", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="✍️ Написать в дебаты", callback_data=ElectionCallback(action="debate_post", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🗳️ Голосовать", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📋 Кандидаты", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
    ])

    if can_manage_stage:
        buttons.insert(
            0,
            [InlineKeyboardButton(text="⏭️ Следующий этап выборов", callback_data=ElectionCallback(action="stage_next", election_id=election_id).pack())],
        )

    await _safe_edit(callback, "\n".join(text_lines), InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(ElectionCallback.filter(F.action == "stage_next"))
async def election_stage_next(callback: CallbackQuery, callback_data: ElectionCallback):
    """Перевод выборов на следующий этап (для уполномоченных)."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]]),
        )
        return

    if not await _can_manage_election_stage(user_id, election_id):
        await callback.answer("❌ У вас нет прав менять этапы выборов.", show_alert=True)
        return

    success, msg, new_stage = await db.cycle_election_stage(election_id)
    stage_label = _election_stage_label(new_stage)
    if not success:
        await _safe_edit(callback, f"❌ {msg}", _election_back_markup(election_id))
        return

    text = (
        "✅ Этап выборов обновлен.\n"
        f"Новый этап: {stage_label}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎤 Открыть дебаты", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
    ])
    await _safe_edit(callback, text, keyboard)


@router.callback_query(ElectionCallback.filter(F.action == "debates"))
async def election_debates_view(callback: CallbackQuery, callback_data: ElectionCallback, state: FSMContext):
    """Лента дебатов текущих выборов."""
    await callback.answer()
    await state.set_state(ElectionStates.global_lock)

    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]]),
        )
        return

    election = await db.get_election(election_id)
    stage_label = _election_stage_label((election or {}).get("stage"))
    posts = await db.get_election_debate_posts(election_id=election_id, limit=15)

    lines = [
        "🎤 ДЕБАТЫ КАНДИДАТОВ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Этап выборов: {stage_label}",
        "",
    ]

    if not posts:
        lines.append("Пока нет сообщений в дебатах.")
    else:
        for row in posts:
            author = (row.get("full_name") or "").strip() or (f"@{row.get('username')}" if row.get("username") else f"ID {row.get('user_id')}")
            party = row.get("party_name")
            party_chunk = f" | {party}" if party else ""
            created = str(row.get("created_date") or "")[11:16]
            message = str(row.get("message") or "")
            if len(message) > 180:
                message = message[:177] + "..."
            lines.append(f"[{created}] {author}{party_chunk}")
            lines.append(message)
            lines.append("")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать в дебаты", callback_data=ElectionCallback(action="debate_post", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
    ])
    await _safe_edit(callback, "\n".join(lines), keyboard)


@router.callback_query(ElectionCallback.filter(F.action == "debate_post"))
async def election_debate_post_start(callback: CallbackQuery, callback_data: ElectionCallback, state: FSMContext):
    """Начать ввод сообщения для дебатов."""
    await callback.answer()

    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]]),
        )
        return

    await state.set_state(ElectionStates.debate_message)
    await state.update_data(election_id=election_id)
    await callback.message.answer(
        "✍️ Напишите тезис для дебатов (5-700 символов):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())
        ]]),
        parse_mode=None,
    )


@router.message(ElectionStates.debate_message, F.text)
async def election_debate_post_finish(message: Message, state: FSMContext):
    """Сохранить сообщение дебатов."""
    data = await state.get_data()
    election_id = int(data.get("election_id") or -1)

    if election_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия дебатов устарела.", parse_mode=None)
        return

    success, result = await db.add_election_debate_post(
        election_id=election_id,
        user_id=message.from_user.id,
        message=message.text,
    )
    if not success:
        await message.answer(
            f"❌ {result}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 К дебатам", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())
            ]]),
            parse_mode=None,
        )
        return

    await state.set_state(ElectionStates.global_lock)
    await message.answer(
        "✅ Ваш тезис опубликован в дебатах.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎤 Открыть дебаты", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())],
            [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
        ]),
        parse_mode=None,
    )


@router.callback_query(ElectionCallback.filter(F.action == "create_party"))
async def election_create_party(callback: CallbackQuery, callback_data: ElectionCallback, state: FSMContext):
    """Запрос названия новой партии."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Нет активных выборов для создания партии.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    existing_party = await db.get_user_party_for_election(user_id, election_id)
    if existing_party:
        await _safe_edit(
            callback,
            f"❌ Вы уже состоите в партии '{existing_party.get('name')}'.",
            _election_back_markup(election_id),
        )
        return

    election = await db.get_election(election_id)
    stage = str((election or {}).get("stage") or "").lower()
    if stage in {"voting", "finished"}:
        await _safe_edit(
            callback,
            f"❌ На этапе '{_election_stage_label(stage)}' создание партий закрыто.",
            _election_back_markup(election_id),
        )
        return

    await state.set_state(ElectionStates.party_name_input)
    await state.update_data(election_id=election_id)

    await callback.message.answer(
        "🟢 Введите название партии (2-32 символа).\n"
        "Разрешены буквы, цифры, пробел и дефис.",
        reply_markup=_election_back_markup(election_id),
        parse_mode=None,
    )


@router.message(ElectionStates.party_name_input, F.text)
async def election_party_name_input(message: Message, state: FSMContext):
    """Создать партию по введенному названию."""
    party_name = " ".join(message.text.strip().split())
    data = await state.get_data()
    election_id = int(data.get('election_id') or -1)

    if election_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия создания партии устарела.", parse_mode=None)
        return

    if len(party_name) < 2 or len(party_name) > 32:
        await message.answer("❌ Название должно быть от 2 до 32 символов.", reply_markup=_election_back_markup(election_id), parse_mode=None)
        return

    if not all(ch.isalnum() or ch in " -" for ch in party_name):
        await message.answer("❌ Разрешены только буквы, цифры, пробел и дефис.", reply_markup=_election_back_markup(election_id), parse_mode=None)
        return

    success, result_text, party_id = await db.create_party(party_name, message.from_user.id, election_id)
    if not success:
        await message.answer(result_text, reply_markup=_election_back_markup(election_id), parse_mode=None)
        return

    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Моя партия", callback_data=PartyCallback(action="view_members", party_id=party_id, election_id=election_id).pack())],
        [InlineKeyboardButton(text="👥 Пригласить игрока", callback_data=PartyCallback(action="invite", party_id=party_id, election_id=election_id).pack())],
        [InlineKeyboardButton(text="📝 Выдвинуться", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
    ])

    await message.answer(
        f"✅ Партия '{party_name}' зарегистрирована.\n"
        "Теперь можно пригласить участников и выдвинуться кандидатом.",
        reply_markup=keyboard,
        parse_mode=None,
    )

@router.callback_query(ElectionCallback.filter(F.action == "nominate"))
async def election_nominate(callback: CallbackQuery, callback_data: ElectionCallback):
    """Регистрация кандидата."""
    await callback.answer()

    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    election = await db.get_election(election_id)
    stage = str((election or {}).get("stage") or "").lower()
    if stage in {"voting", "finished"}:
        await _safe_edit(
            callback,
            f"❌ На этапе '{_election_stage_label(stage)}' регистрация кандидатов закрыта.",
            _election_back_markup(election_id),
        )
        return

    success, msg = await db.register_candidate(election_id, callback.from_user.id)
    if success:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗳️ К голосованию", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📋 Кандидаты", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
            [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
        ])
        await _safe_edit(callback, "✅ Вы зарегистрированы кандидатом.", keyboard)
    else:
        await _safe_edit(callback, msg, _election_back_markup(election_id))


@router.callback_query(ElectionCallback.filter(F.action == "vote_menu"))
async def election_vote_menu(callback: CallbackQuery, callback_data: ElectionCallback):
    """Показать меню голосования."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    candidates = await db.get_election_candidates(election_id)
    if not candidates:
        await _safe_edit(
            callback,
            "❌ На этих выборах пока нет кандидатов.",
            _election_back_markup(election_id),
        )
        return

    election = await db.get_election(election_id)
    stage = str((election or {}).get("stage") or "").lower()
    if stage not in {"voting", "finished"}:
        await _safe_edit(
            callback,
            f"❌ Голосование пока закрыто. Текущий этап: {_election_stage_label(stage)}.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎤 Дебаты", callback_data=ElectionCallback(action="debates", election_id=election_id).pack())],
                [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
            ]),
        )
        return

    already_voted = await db.has_user_voted(election_id, user_id)

    text = "🗳️ ГОЛОСОВАНИЕ\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Вы уже проголосовали. Повторный голос невозможен.\n\n" if already_voted else "Выберите кандидата:\n\n"

    for idx, cand in enumerate(candidates, 1):
        cand_name = cand.get('full_name') or f"ID {cand.get('candidate_id')}"
        party_name = cand.get('party_name')
        party_chunk = f" | Партия: {party_name}" if party_name else ""
        text += f"{idx}. {cand_name}{party_chunk} — {cand.get('votes', 0)} голосов\n"

    buttons = []
    if not already_voted:
        for cand in candidates:
            cand_name = cand.get('full_name') or f"ID {cand.get('candidate_id')}"
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗳️ {cand_name}",
                    callback_data=ElectionCallback(
                        action="vote",
                        election_id=election_id,
                        candidate_id=cand['candidate_id']
                    ).pack()
                )
            ])

    buttons.append([
        InlineKeyboardButton(
            text="🔙 В меню выборов",
            callback_data=ElectionCallback(action="view_party", election_id=election_id).pack()
        )
    ])

    await _safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(ElectionCallback.filter(F.action == "vote"))
async def election_vote(callback: CallbackQuery, callback_data: ElectionCallback):
    """Проголосовать за кандидата."""
    await callback.answer()

    election_id = await _resolve_active_election_id(callback_data.election_id)
    candidate_id = int(callback_data.candidate_id or -1)

    if election_id <= 0 or candidate_id <= 0:
        await _safe_edit(
            callback,
            "❌ Некорректные данные голосования.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    election = await db.get_election(election_id)
    stage = str((election or {}).get("stage") or "").lower()
    if stage not in {"voting"}:
        await _safe_edit(
            callback,
            f"❌ Сейчас нельзя голосовать. Этап: {_election_stage_label(stage)}.",
            _election_back_markup(election_id),
        )
        return

    success, msg = await db.cast_vote(election_id, callback.from_user.id, candidate_id)
    if not success:
        await _safe_edit(callback, msg, _election_back_markup(election_id))
        return

    candidate = await db.get_user(candidate_id)
    candidate_name = candidate.get('full_name') if candidate else f"ID {candidate_id}"

    await _safe_edit(
        callback,
        f"✅ Ваш голос принят.\nКандидат: {candidate_name}",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Кандидаты", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
            [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
        ]),
    )


@router.callback_query(ElectionCallback.filter(F.action == "view_candidates"))
async def election_view_candidates(callback: CallbackQuery, callback_data: ElectionCallback):
    """Показать список кандидатов и рейтинг."""
    await callback.answer()

    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    candidates = await db.get_election_candidates(election_id)
    if not candidates:
        await _safe_edit(callback, "❌ На этих выборах пока нет кандидатов.", _election_back_markup(election_id))
        return

    total_votes = sum(int(c.get('votes', 0) or 0) for c in candidates)

    text = "📋 КАНДИДАТЫ\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for idx, cand in enumerate(candidates, 1):
        votes = int(cand.get('votes', 0) or 0)
        percent = (votes / total_votes * 100) if total_votes > 0 else 0
        cand_name = cand.get('full_name') or f"ID {cand.get('candidate_id')}"
        party_name = cand.get('party_name')
        party_chunk = f" | Партия: {party_name}" if party_name else ""
        text += f"{idx}. {cand_name}{party_chunk}\n   Голосов: {votes} ({percent:.1f}%)\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳️ Голосовать", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
    ])

    await _safe_edit(callback, text, keyboard)

@router.callback_query(ElectionCallback.filter(F.action == "list_parties"))
async def election_list_parties(callback: CallbackQuery, callback_data: ElectionCallback):
    """Список партий на выборах."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    parties = await db.get_election_parties(election_id)
    user_party = await db.get_user_party_for_election(user_id, election_id)

    if not parties:
        await _safe_edit(callback, "❌ На выборах пока нет партий.", _election_back_markup(election_id))
        return

    text = "📜 СПИСОК ПАРТИЙ\n━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for p in parties:
        pname = p.get('name', 'Без названия')
        leader_name = p.get('leader_name') or f"ID {p.get('leader_id')}"
        members_count = int(p.get('members_count', 0) or 0)
        votes_total = int(p.get('votes_total', 0) or 0)

        text += f"• {pname}\n  Лидер: {leader_name}\n  Участников: {members_count} | Голосов: {votes_total}\n\n"

        if not user_party and int(p.get('leader_id') or 0) != user_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"➕ Вступить: {pname}",
                    callback_data=PartyCallback(action="request_join", party_id=p['id'], election_id=election_id).pack(),
                )
            ])

    if user_party:
        text += f"Вы уже состоите в партии: {user_party.get('name')}\n"

    buttons.append([
        InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())
    ])

    await _safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(PartyCallback.filter(F.action == "request_join"))
async def party_request_join(callback: CallbackQuery, callback_data: PartyCallback):
    """Запрос на вступление в партию (к лидеру)."""
    await callback.answer()

    user_id = callback.from_user.id
    party_id = int(callback_data.party_id or -1)
    election_id = await _resolve_active_election_id(callback_data.election_id)

    if party_id <= 0 or election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Некорректный запрос на вступление.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    party = await db.get_party(party_id)
    if not party or int(party.get('election_id') or -1) != election_id:
        await _safe_edit(callback, "❌ Партия не найдена.", _election_back_markup(election_id))
        return

    current_party = await db.get_user_party_for_election(user_id, election_id)
    if current_party:
        await _safe_edit(callback, "❌ Вы уже состоите в партии на этих выборах.", _election_back_markup(election_id))
        return

    now = datetime.now().isoformat()
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            '''INSERT INTO party_invitations (party_id, invited_user_id, invited_by_id, created_date, status)
               VALUES (?, ?, ?, ?, 'request')
               ON CONFLICT(party_id, invited_user_id)
               DO UPDATE SET invited_by_id = excluded.invited_by_id,
                             created_date = excluded.created_date,
                             status = 'request' ''',
            (party_id, user_id, user_id, now)
        )
        await conn.commit()

    leader_id = int(party.get('leader_id') or 0)
    if leader_id > 0:
        try:
            accept_cb = PartyCallback(
                action="handle_request",
                party_id=party_id,
                election_id=election_id,
                invited_user_id=user_id,
                decision=1,
            ).pack()
            reject_cb = PartyCallback(
                action="handle_request",
                party_id=party_id,
                election_id=election_id,
                invited_user_id=user_id,
                decision=0,
            ).pack()
            display_name = callback.from_user.full_name or callback.from_user.username or str(user_id)
            await callback.bot.send_message(
                leader_id,
                f"📩 Игрок {display_name} просит вступить в партию '{party.get('name')}'.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Принять", callback_data=accept_cb),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=reject_cb),
                ]]),
                parse_mode=None,
            )
        except Exception:
            pass

    await _safe_edit(callback, "✅ Запрос отправлен лидеру партии.", _election_back_markup(election_id))


@router.callback_query(PartyCallback.filter(F.action == "handle_request"))
async def party_handle_request(callback: CallbackQuery, callback_data: PartyCallback):
    """Лидер принимает или отклоняет запрос на вступление."""
    await callback.answer()

    leader_id = callback.from_user.id
    party_id = int(callback_data.party_id or -1)
    invited_user_id = int(callback_data.invited_user_id or -1)
    decision = int(callback_data.decision or 0)
    election_id = await _resolve_active_election_id(callback_data.election_id)

    if party_id <= 0 or invited_user_id <= 0 or election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Некорректные данные запроса.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    party = await db.get_party(party_id)
    if not party:
        await _safe_edit(callback, "❌ Партия не найдена.", _election_back_markup(election_id))
        return

    if int(party.get('leader_id') or 0) != leader_id:
        await callback.answer("❌ Только лидер партии может обрабатывать заявки.", show_alert=True)
        return

    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT status FROM party_invitations WHERE party_id = ? AND invited_user_id = ?",
            (party_id, invited_user_id),
        )
        req = await cur.fetchone()

    if not req or req['status'] != 'request':
        await _safe_edit(callback, "❌ Заявка уже обработана или не найдена.", _election_back_markup(election_id))
        return

    new_status = 'accepted' if decision == 1 else 'rejected'
    now = datetime.now().isoformat()

    if decision == 1:
        success, msg = await db.add_party_member(party_id, invited_user_id)
        if not success:
            await _safe_edit(callback, f"❌ Не удалось принять в партию: {msg}", _election_back_markup(election_id))
            return

        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "UPDATE party_invitations SET status = ?, created_date = ? WHERE party_id = ? AND invited_user_id = ?",
                (new_status, now, party_id, invited_user_id),
            )
            await conn.commit()

        try:
            await callback.bot.send_message(
                invited_user_id,
                f"✅ Ваша заявка в партию '{party.get('name')}' одобрена.",
                parse_mode=None,
            )
        except Exception:
            pass

        await _safe_edit(callback, "✅ Игрок принят в партию.", _election_back_markup(election_id))
    else:
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "UPDATE party_invitations SET status = ?, created_date = ? WHERE party_id = ? AND invited_user_id = ?",
                (new_status, now, party_id, invited_user_id),
            )
            await conn.commit()

        try:
            await callback.bot.send_message(
                invited_user_id,
                f"❌ Ваша заявка в партию '{party.get('name')}' отклонена.",
                parse_mode=None,
            )
        except Exception:
            pass

        await _safe_edit(callback, "❌ Заявка отклонена.", _election_back_markup(election_id))

@router.callback_query(PartyCallback.filter(F.action == "view_members"))
async def party_view_members(callback: CallbackQuery, callback_data: PartyCallback):
    """Показать членов партии пользователя."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    user_party = await db.get_user_party_for_election(user_id, election_id)
    if not user_party:
        await _safe_edit(callback, "❌ Вы не состоите ни в одной партии.", _election_back_markup(election_id))
        return

    requested_party_id = int(callback_data.party_id or user_party['id'])
    if requested_party_id != int(user_party['id']):
        await _safe_edit(callback, "❌ Можно просматривать только свою партию.", _election_back_markup(election_id))
        return

    members = await db.get_party_members(requested_party_id)

    text = f"👥 ПАРТИЯ: {user_party.get('name')}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"Участников: {len(members)}\n\n"

    for idx, member in enumerate(members, 1):
        role = "Лидер" if member.get('role') == 'leader' else "Участник"
        text += f"{idx}. {member.get('full_name', 'Игрок')} ({role})\n"

    buttons = []
    if int(user_party.get('leader_id') or 0) == user_id:
        buttons.append([
            InlineKeyboardButton(
                text="👥 Пригласить",
                callback_data=PartyCallback(action="invite", party_id=requested_party_id, election_id=election_id).pack(),
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🔙 В меню выборов",
            callback_data=ElectionCallback(action="view_party", election_id=election_id).pack(),
        )
    ])

    await _safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(PartyCallback.filter(F.action == "invite"))
async def party_invite(callback: CallbackQuery, callback_data: PartyCallback):
    """Начать приглашение игрока в партию."""
    await callback.answer()

    user_id = callback.from_user.id
    election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Сейчас нет активных выборов.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    party = await db.get_party_by_leader(user_id, election_id)
    if not party:
        await _safe_edit(callback, "❌ Только лидер партии может отправлять приглашения.", _election_back_markup(election_id))
        return

    await _render_party_invite_picker(callback, party, election_id, page=0)


@router.callback_query(F.data.startswith("pinvpg:"))
async def party_invite_page(callback: CallbackQuery):
    """Перелистывание списка игроков для приглашения."""
    await callback.answer()

    parsed = _parse_party_invite_cb(callback.data, "pinvpg", 4)
    if not parsed:
        await callback.answer("❌ Некорректные данные страницы.", show_alert=True)
        return

    party_id, election_id, page = parsed
    party = await db.get_party(party_id)
    if not party or int(party.get("leader_id") or 0) != callback.from_user.id:
        await callback.answer("❌ Только лидер партии может приглашать игроков.", show_alert=True)
        return

    if int(party.get("election_id") or -1) != election_id:
        await callback.answer("❌ Партия не относится к этим выборам.", show_alert=True)
        return

    await _render_party_invite_picker(callback, party, election_id, page=page)


@router.callback_query(F.data.startswith("pinvsel:"))
async def party_invite_select(callback: CallbackQuery):
    """Выбор игрока из списка для приглашения в партию."""
    await callback.answer()

    parsed = _parse_party_invite_cb(callback.data, "pinvsel", 5)
    if not parsed:
        await callback.answer("❌ Некорректные данные выбора.", show_alert=True)
        return

    party_id, election_id, invited_user_id, page = parsed
    leader_id = callback.from_user.id
    party = await db.get_party(party_id)

    if not party or int(party.get("leader_id") or 0) != leader_id:
        await callback.answer("❌ Только лидер партии может приглашать игроков.", show_alert=True)
        return

    if int(party.get("election_id") or -1) != election_id:
        await callback.answer("❌ Партия не относится к этим выборам.", show_alert=True)
        return

    if invited_user_id == leader_id:
        await _render_party_invite_picker(callback, party, election_id, page=page, notice="❌ Нельзя пригласить самого себя.")
        return

    invited_user = await db.get_user(invited_user_id)
    if not invited_user:
        await _render_party_invite_picker(callback, party, election_id, page=page, notice="❌ Игрок не найден.")
        return

    invited_user_party = await db.get_user_party_for_election(invited_user_id, election_id)
    if invited_user_party:
        await _render_party_invite_picker(
            callback,
            party,
            election_id,
            page=page,
            notice="❌ Этот игрок уже состоит в партии на этих выборах.",
        )
        return

    delivery = await _send_party_invitation(
        bot=callback.bot,
        party=party,
        election_id=election_id,
        leader_id=leader_id,
        invited_user_id=invited_user_id,
    )

    invited_name = (invited_user.get("full_name") or "").strip() or f"ID {invited_user_id}"
    await _render_party_invite_picker(
        callback,
        party,
        election_id,
        page=page,
        notice=f"✅ Приглашение отправлено игроку {invited_name}. {delivery}",
    )


@router.callback_query(PartyCallback.filter(F.action == "answer_invite"))
async def party_answer_invite(callback: CallbackQuery, callback_data: PartyCallback):
    """Ответ приглашенного пользователя на приглашение в партию."""
    await callback.answer()

    user_id = callback.from_user.id
    party_id = int(callback_data.party_id or -1)
    decision = int(callback_data.decision or 0)
    election_id = await _resolve_active_election_id(callback_data.election_id)

    if party_id <= 0 or election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Некорректные данные приглашения.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    party = await db.get_party(party_id)
    if not party:
        await _safe_edit(callback, "❌ Партия не найдена.", _election_back_markup(election_id))
        return

    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT status FROM party_invitations WHERE party_id = ? AND invited_user_id = ?",
            (party_id, user_id),
        )
        invite = await cur.fetchone()

    if not invite or invite['status'] != 'pending':
        await _safe_edit(callback, "❌ Приглашение не найдено или уже обработано.", _election_back_markup(election_id))
        return

    now = datetime.now().isoformat()
    leader_id = int(party.get('leader_id') or 0)

    if decision == 1:
        success, msg = await db.add_party_member(party_id, user_id)
        if not success:
            await _safe_edit(callback, f"❌ Не удалось вступить в партию: {msg}", _election_back_markup(election_id))
            return

        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "UPDATE party_invitations SET status = ?, created_date = ? WHERE party_id = ? AND invited_user_id = ?",
                ('accepted', now, party_id, user_id),
            )
            await conn.commit()

        if leader_id > 0:
            try:
                await callback.bot.send_message(leader_id, f"✅ Игрок ID {user_id} принял приглашение в партию '{party.get('name')}'.", parse_mode=None)
            except Exception:
                pass

        await _safe_edit(callback, f"✅ Вы вступили в партию '{party.get('name')}'.", _election_back_markup(election_id))
    else:
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "UPDATE party_invitations SET status = ?, created_date = ? WHERE party_id = ? AND invited_user_id = ?",
                ('rejected', now, party_id, user_id),
            )
            await conn.commit()

        if leader_id > 0:
            try:
                await callback.bot.send_message(leader_id, f"❌ Игрок ID {user_id} отклонил приглашение в партию '{party.get('name')}'.", parse_mode=None)
            except Exception:
                pass

        await _safe_edit(callback, "❌ Вы отклонили приглашение.", _election_back_markup(election_id))
