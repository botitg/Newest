"""
handlers_part2.py - Обработчики организаций, бизнеса и работы
Асинхронные handlers для aiogram 3.x
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import db
from states import (
    OrganizationStates, BusinessStates, CitizenStates
)
from keyboards import (
    get_back_button, get_organization_list_keyboard, OrgCallback
)

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# ОРГАНИЗАЦИИ - ОСНОВНОЕ МЕНЮ И ПРОСМОТР
# ============================================================================

@router.message(Command("orgs"))
@router.callback_query(F.data == "orgs_main")
async def organizations_menu(event, state: FSMContext):
    """Главное меню организаций"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🏛️ **ГОСУДАРСТВЕННЫЕ ОРГАНИЗАЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if user.get('organization'):
        text += f"**Ваша должность:** {user.get('role', 'Нет')}\n"
        text += f"**Зарплата:** ${user.get('salary', 0):.2f}/день\n\n"
    
    text += "Выберите организацию для просмотра или присоединения:"
    
    reply_markup = get_organization_list_keyboard()
    
    await state.set_state(OrganizationStates.org_menu)
    if isinstance(event, CallbackQuery):
        await message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await message.answer(text, reply_markup=reply_markup, parse_mode='Markdown')


@router.callback_query(OrgCallback.filter(F.action == "view_org"))
@router.callback_query(OrgCallback.filter(F.action == "view"))
async def view_organization(callback: CallbackQuery, state: FSMContext, callback_data: OrgCallback):
    """Просмотр информации об организации"""
    org_id = int(callback_data.org_id or -1)

    org = None
    if org_id > 0:
        org = await db.get_organization_by_id(org_id)
    if not org and callback_data.org_name and callback_data.org_name != "none":
        org = await db.get_organization(callback_data.org_name)
        if org:
            org_id = int(org.get('id') or -1)

    if not org:
        await callback.answer("❌ Организация не найдена", show_alert=True)
        return
    
    text = f"🏛️ **{org.get('name', 'Неизвестно')}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📖 **Описание:** {org.get('description', 'Нет')}\n"
    text += f"👥 **Членов:** {org.get('members', 0)}\n"
    text += f"💰 **Бюджет:** ${org.get('budget', 0):.2f}\n"
    text += f"⭐ **Репутация:** {org.get('reputation', 50)}/100\n\n"
    
    if org.get('leader_id'):
        leader = await db.get_user(org.get('leader_id'))
        text += f"👑 **Лидер:** {leader.get('full_name', 'Неизвестно')}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("👥 Члены", callback_data=f"org_members_{org_id}")],
        [InlineKeyboardButton("💬 Чат организации", callback_data=f"org_chat_{org_id}")],
        [InlineKeyboardButton("📝 Подать заявку", callback_data=f"apply_org_{org_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")]
    ]
    
    await state.set_state(OrganizationStates.viewing_org)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    await callback.answer()


@router.callback_query(F.data.startswith("view_org_"))
async def legacy_view_organization(callback: CallbackQuery, state: FSMContext):
    """Совместимость со старым callback_data вида view_org_{id}."""
    try:
        org_id = int(callback.data.replace("view_org_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации", show_alert=True)
        return
    cb_data = OrgCallback(action="view_org", org_id=org_id, org_name="none")
    await view_organization(callback, state, cb_data)


@router.callback_query(F.data.startswith("org_members_"))
async def view_organization_members(callback: CallbackQuery, state: FSMContext):
    """Список членов организации."""
    try:
        org_id = int(callback.data.replace("org_members_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    members = await db.get_organization_members(org_id)
    text = f"👥 **Члены {org.get('name', 'Организации')}**\n━━━━━━━━━━━━━━━━━━━━\n\n"

    if not members:
        text += "Нет членов"
    else:
        for member in members[:15]:
            text += f"• **{member.get('full_name')}** - {member.get('role', 'Участник')}\n"
        if len(members) > 15:
            text += f"\n... и ещё {len(members) - 15} человек"

    keyboard = [[
        InlineKeyboardButton("🔙 Назад", callback_data=OrgCallback(action="view_org", org_id=org_id, org_name="none").pack())
    ]]

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    await callback.answer()


# ============================================================================
# ОРГАНИЗАЦИИ - ЧАТЫ
# ============================================================================

@router.callback_query(F.data.startswith("org_chat_send_hidden_"))
async def org_chat_send_hidden_start(callback: CallbackQuery, state: FSMContext):
    """Начать отправку скрытого сообщения в чат организации."""
    await callback.answer()
    try:
        org_id = int(callback.data.replace("org_chat_send_hidden_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    user = await db.get_user(callback.from_user.id) or {}
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if user.get("organization") != org.get("name"):
        await callback.answer("❌ Только члены организации могут писать в чат.", show_alert=True)
        return

    await state.set_state(OrganizationStates.org_chat_message)
    await state.update_data(org_chat_org_id=org_id, org_chat_hidden=True)
    await callback.message.answer(
        "🕶️ Введите скрытое сообщение для чата организации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"org_chat_{org_id}")
        ]]),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("org_chat_send_"))
async def org_chat_send_start(callback: CallbackQuery, state: FSMContext):
    """Начать отправку обычного сообщения в чат организации."""
    await callback.answer()
    try:
        org_id = int(callback.data.replace("org_chat_send_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    user = await db.get_user(callback.from_user.id) or {}
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if user.get("organization") != org.get("name"):
        await callback.answer("❌ Только члены организации могут писать в чат.", show_alert=True)
        return

    await state.set_state(OrganizationStates.org_chat_message)
    await state.update_data(org_chat_org_id=org_id, org_chat_hidden=False)
    await callback.message.answer(
        "💬 Введите сообщение для чата организации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"org_chat_{org_id}")
        ]]),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("org_chat_"))
async def org_chat_view(callback: CallbackQuery, state: FSMContext):
    """Просмотр чата организации."""
    await callback.answer()
    try:
        org_id = int(callback.data.replace("org_chat_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    user = await db.get_user(callback.from_user.id) or {}
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    is_fbi = await db.is_fbi_agent(callback.from_user.id)
    is_member = user.get("organization") == org.get("name")
    if not is_member and not is_fbi:
        await callback.answer("❌ Чат доступен только сотрудникам организации или ФБР.", show_alert=True)
        return

    messages = await db.get_organization_chat_messages(
        org_id=org_id,
        limit=18,
        include_hidden=is_fbi,
    )
    text_lines = [
        f"💬 ЧАТ: {org.get('name')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if is_fbi and not is_member:
        text_lines.append("Режим наблюдения ФБР: включен.")

    if not messages:
        text_lines.append("")
        text_lines.append("Пока нет сообщений.")
    else:
        text_lines.append("")
        for msg in messages:
            author = (msg.get("full_name") or "").strip() or (f"@{msg.get('username')}" if msg.get("username") else f"ID {msg.get('user_id')}")
            created = str(msg.get("created_date") or "")[11:16]
            marker = "🕶️ " if int(msg.get("is_hidden") or 0) == 1 else ""
            content = str(msg.get("content") or "")
            if len(content) > 140:
                content = content[:137] + "..."
            text_lines.append(f"[{created}] {marker}{author}: {content}")

    keyboard: list[list[InlineKeyboardButton]] = []
    if is_member:
        keyboard.append([
            InlineKeyboardButton("✍️ Написать", callback_data=f"org_chat_send_{org_id}"),
            InlineKeyboardButton("🕶️ Подпольно", callback_data=f"org_chat_send_hidden_{org_id}"),
        ])
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"org_chat_{org_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=OrgCallback(action="view_org", org_id=org_id, org_name="none").pack())])

    await state.set_state(OrganizationStates.viewing_org)
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.message(OrganizationStates.org_chat_message, F.text)
async def org_chat_send_finish(message: Message, state: FSMContext):
    """Сохранить сообщение в чат организации."""
    data = await state.get_data()
    org_id = int(data.get("org_chat_org_id") or -1)
    is_hidden = bool(data.get("org_chat_hidden"))
    if org_id <= 0:
        await state.clear()
        await message.answer("❌ Сессия чата устарела.")
        return

    success, db_msg = await db.send_organization_chat_message(
        org_id=org_id,
        user_id=message.from_user.id,
        content=message.text,
        is_hidden=is_hidden,
    )
    if not success:
        await message.answer(
            f"❌ {db_msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton("🔙 К чату", callback_data=f"org_chat_{org_id}")
            ]]),
        )
        return

    await state.set_state(OrganizationStates.viewing_org)
    await message.answer(
        "✅ Сообщение отправлено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton("💬 Открыть чат", callback_data=f"org_chat_{org_id}")
        ]]),
    )


# ============================================================================
# ОРГАНИЗАЦИИ - ПРИМЕНЕНИЕ
# ============================================================================

@router.callback_query(F.data.startswith("apply_org_"))
async def start_apply_to_organization(callback: CallbackQuery, state: FSMContext):
    """Начало процесса применения в организацию."""
    try:
        org_id = int(callback.data.replace("apply_org_", ""))
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    if user.get('organization'):
        await callback.answer("❌ Вы уже в организации", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    text = f"📝 **Применение в {org.get('name')}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Напишите сообщение с причиной присоединения (до 500 символов):"

    await state.set_state(OrganizationStates.application_text)
    await state.update_data(org_id=org_id, org_name=org.get('name'))

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_back_button(callback="orgs_main"), parse_mode='Markdown')


@router.message(OrganizationStates.application_text, F.text)
async def receive_application_text(message: Message, state: FSMContext):
    """Получение текста заявки"""
    data = await state.get_data()
    org_id = data.get('org_id')
    user_id = message.from_user.id
    
    application_text = message.text[:500]
    
    # Записываем заявку в БД
    success, db_message = await db.apply_to_organization(user_id, org_id, application_text)
    if success:
        text = "✅ **Заявка отправлена!**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "Администраторы организации рассмотрят вашу заявку в ближайшее время.\n"
        text += "Вы получите уведомление, когда придёт решение."
    else:
        text = f"❌ **Заявка не отправлена**\n━━━━━━━━━━━━━━━━━━━━\n\n{db_message}"
    
    await state.set_state(OrganizationStates.org_menu)
    await message.answer(text, reply_markup=get_back_button(callback="orgs_main"), parse_mode='Markdown')


# ============================================================================
# ОРГАНИЗАЦИИ - УПРАВЛЕНИЕ (для лидеров)
# ============================================================================

@router.callback_query(F.data == "manage_organization")
async def manage_organization_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления организацией (для лидера)"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    org = await db.get_organization(user.get('organization'))
    if not org or org.get('leader_id') != user_id:
        await callback.answer("❌ Вы не лидер организации", show_alert=True)
        return
    
    text = f"⚙️ **Управление {org.get('name')}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"💰 **Бюджет:** ${org.get('budget', 0):.2f}\n"
    text += f"👥 **Членов:** {org.get('members', 0)}\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 Заявки", callback_data="review_applications")],
        [InlineKeyboardButton("👥 Члены", callback_data="manage_members")],
        [InlineKeyboardButton("💬 Чат организации", callback_data=f"org_chat_{org.get('id')}")],
        [InlineKeyboardButton("💰 Финансы", callback_data="org_finances")],
        [InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")]
    ]
    
    await state.set_state(OrganizationStates.managing_org)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "review_applications")
async def review_applications(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран заявок организации."""
    from feature_pack import feature_review_applications
    await feature_review_applications(callback, state)


@router.callback_query(F.data == "manage_members")
async def manage_members(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран сотрудников организации."""
    from feature_pack import feature_manage_members
    await feature_manage_members(callback, state)


@router.callback_query(F.data == "org_finances")
async def org_finances(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран финансов организации."""
    from feature_pack import feature_org_finances
    await feature_org_finances(callback, state)


# ============================================================================
# БИЗНЕСЫ
# ============================================================================

@router.message(Command("biz"))
@router.callback_query(F.data == "biz_menu")
async def business_menu(event, state: FSMContext):
    """Прокси на единое рабочее меню бизнеса."""
    from feature_pack import feature_business_menu
    await feature_business_menu(event, state)


@router.callback_query(F.data == "create_business")
async def start_create_business(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий сценарий открытия бизнеса через недвижимость."""
    from feature_pack import feature_business_create_start
    await feature_business_create_start(callback, state)


@router.callback_query(F.data.startswith("biz_type_"))
async def select_business_type(callback: CallbackQuery, state: FSMContext):
    """Совместимость со старыми кнопками выбора типа бизнеса."""
    await callback.answer("Сценарий обновлен. Откройте бизнес через новый мастер.", show_alert=True)
    from feature_pack import feature_business_create_start
    await feature_business_create_start(callback, state)


@router.callback_query(F.data == "my_businesses")
async def my_businesses(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий список бизнесов пользователя."""
    from feature_pack import feature_business_my
    await feature_business_my(callback, state)


# ============================================================================
# ГРАЖДАНСКАЯ РАБОТА
# ============================================================================

@router.message(Command("work"))
@router.callback_query(F.data == "work_menu")
async def citizen_work_menu(event, state: FSMContext):
    """Меню гражданской работы"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "💼 **ГРАЖДАНСКАЯ РАБОТА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Работайте на благо государства и зарабатывайте деньги.\n\n"
    )
    
    if user.get('citizen_job'):
        text += f"**Ваша должность:** {user.get('citizen_job')}\n"
        text += f"**Зарплата:** ${user.get('citizen_salary', 0):.2f}/день\n\n"
    else:
        text += "Вы не имеете должности.\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 Вакансии", callback_data="view_citizen_jobs")],
        [InlineKeyboardButton("💼 Мой статус", callback_data="citizen_work_status")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(CitizenStates.job_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "view_citizen_jobs")
async def view_citizen_jobs(callback: CallbackQuery, state: FSMContext):
    """Просмотр вакансий"""
    text = (
        "📋 **ВАКАНСИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Доступные должности:\n\n"
        "🚓 **Полицейский** - $500/день\n"
        "🏥 **Врач** - $600/день\n"
        "👨‍⚖️ **Судья** - $800/день\n"
        "🧑‍💼 **Чиновник** - $450/день\n"
        "🧽 **Уборщик** - $200/день\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="work_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "citizen_work_status")
async def citizen_work_status(callback: CallbackQuery, state: FSMContext):
    """Статус работы"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = "💼 **ВАШ СТАТУС РАБОТЫ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if user.get('citizen_job'):
        text += f"**Должность:** {user.get('citizen_job')}\n"
        text += f"**Зарплата:** ${user.get('citizen_salary', 0):.2f}/день\n"
        text += "**Статус:** Трудоустроены ✅\n"
    else:
        text += "**Статус:** Без работы ❌\n"
        text += "Вы можете применить на вакансию"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="work_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# ОБРАЗОВАНИЕ
# ============================================================================

@router.message(Command("edu"))
@router.callback_query(F.data == "edu_menu")
async def education_menu(event, state: FSMContext):
    """Меню образования"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🎓 **ОБРАЗОВАНИЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Повышайте свой образовательный уровень\n"
        "и получайте новые возможности в игре.\n\n"
    )
    
    text += f"**Ваш уровень:** {user.get('education', 1)}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("📚 Программы", callback_data="view_education_programs")],
        [InlineKeyboardButton("🎓 Мой прогресс", callback_data="education_progress")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "view_education_programs")
async def view_education_programs(callback: CallbackQuery, state: FSMContext):
    """Просмотр университетских программ"""
    text = (
        "📚 **ПРОГРАММЫ ОБРАЗОВАНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Доступные программы:\n\n"
        "1️⃣ **Начальное** - уровень 1\n"
        "   Основные знания (бесплатно)\n\n"
        "2️⃣ **Среднее** - уровень 2\n"
        "   Специальные навыки ($5,000)\n\n"
        "3️⃣ **Высшее** - уровень 3\n"
        "   Профессиональное обучение ($15,000)\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data == "education_progress")
async def education_progress(callback: CallbackQuery, state: FSMContext):
    """Прогресс обучения"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🎓 **ВАШ ПРОГРЕСС**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Уровень образования:** {user.get('education', 1)}\n"
        "**Статус:** Активен\n"
        "**Прогресс:** 0%\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# НЕДВИЖИМОСТЬ
# ============================================================================

@router.message(Command("prop"))
@router.callback_query(F.data == "prop_menu")
async def property_menu(event, state: FSMContext):
    """Меню недвижимости"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    text = (
        "🏠 **НЕДВИЖИМОСТЬ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Покупайте и продавайте недвижимость,\n"
        "открывайте бизнес и зарабатывайте.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Каталог", callback_data="property_catalog")],
        [InlineKeyboardButton("🏠 Мое имущество", callback_data="my_property")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "property_catalog")
async def property_catalog(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий каталог недвижимости."""
    from feature_pack import feature_property_catalog
    await feature_property_catalog(callback, state)


@router.callback_query(F.data == "my_property")
async def my_property(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий список собственности пользователя."""
    from feature_pack import feature_my_property
    await feature_my_property(callback, state)


# ============================================================================
# КОНТРАКТЫ И РЫНОК
# ============================================================================

@router.message(Command("market"))
@router.callback_query(F.data == "market_menu")
async def market_menu(event, state: FSMContext):
    """Меню рынка контрактов"""
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()
    
    text = (
        "📣 **КОНТРАКТНАЯ БИРЖА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Покупайте и продавайте услуги.\n"
        "Создавайте контракты на выполнение заказов.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Контракты", callback_data="view_contracts")],
        [InlineKeyboardButton("✍️ Создать", callback_data="create_contract")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(keyboard))


@router.callback_query(F.data == "view_contracts")
async def view_contracts(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий список контрактов."""
    from feature_pack import feature_contracts_view
    await feature_contracts_view(callback, state)


@router.callback_query(F.data == "create_contract")
async def create_contract(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочее создание контракта."""
    from feature_pack import feature_contracts_create_start
    await feature_contracts_create_start(callback, state)

