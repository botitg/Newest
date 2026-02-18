"""
feature_pack.py - расширенный игровой контент и новые механики
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import db

router = Router()


class FeatureStates(StatesGroup):
    business_name = State()
    private_org_name = State()
    private_casino_name = State()
    hustle_guess = State()
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
    return (
        (user.get("full_name") or "").strip()
        or (f"@{user.get('username')}" if user.get("username") else f"ID {user.get('user_id')}")
    )


def _md(text: str) -> str:
    escaped = str(text or "")
    for token in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        escaped = escaped.replace(token, f"\\{token}")
    return escaped


def _back(callback_data: str = "back_to_main", text: str = "🔙 Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)]])


def _edit_or_answer(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        return event.message.edit_text
    return event.answer


def _is_police_user(user: dict | None) -> bool:
    role = str((user or {}).get("role") or "").lower()
    org = str((user or {}).get("organization") or "").lower()
    return ("полиц" in role) or ("police" in role) or ("полиц" in org) or ("police" in org)


def _is_judge_user(user: dict | None) -> bool:
    role = str((user or {}).get("role") or "").lower()
    org = str((user or {}).get("organization") or "").lower()
    return ("суд" in role) or ("judge" in role) or ("court" in role) or ("суд" in org) or ("court" in org)


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
            [InlineKeyboardButton("🆕 Открыть из недвижимости", callback_data="fp_business_create_start")],
            [InlineKeyboardButton("📊 Мои бизнесы", callback_data="fp_business_my")],
            [InlineKeyboardButton("🧾 Налоговые отчеты", callback_data="fp_business_tax_reports")],
            [InlineKeyboardButton("🎰 Казино", callback_data="casino_menu")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
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
    for biz in businesses:
        lines.append(
            f"• **{_md(str(biz.get('name') or 'Без названия'))}** — {biz.get('type')}\n"
            f"  Доход/день: ${float(biz.get('income_daily') or 0):,.0f} | Расход/день: ${float(biz.get('expense_daily') or 0):,.0f}"
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=_back("biz_menu"), parse_mode="Markdown")


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
        [InlineKeyboardButton(f"🏗️ {p.get('name')} (${float(p.get('price') or 0):,.0f})", callback_data=f"fp_business_pickprop_{int(p['id'])}")]
        for p in free_props[:12]
    ]
    keyboard.append([InlineKeyboardButton("🔙 К бизнесу", callback_data="biz_menu")])
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
            [InlineKeyboardButton("🍔 Ресторан", callback_data=f"fp_business_type_{property_id}_restaurant")],
            [InlineKeyboardButton("🛒 Магазин", callback_data=f"fp_business_type_{property_id}_shop")],
            [InlineKeyboardButton("🏭 Производство", callback_data=f"fp_business_type_{property_id}_factory")],
            [InlineKeyboardButton("🏨 Отель", callback_data=f"fp_business_type_{property_id}_hotel")],
            [InlineKeyboardButton("📡 Медиа", callback_data=f"fp_business_type_{property_id}_media")],
            [InlineKeyboardButton("💻 IT", callback_data=f"fp_business_type_{property_id}_it")],
            [InlineKeyboardButton("🔙 Назад", callback_data="fp_business_create_start")],
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


@router.message(FeatureStates.business_name, F.text)
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
                [InlineKeyboardButton("📊 Мои бизнесы", callback_data="fp_business_my")],
                [InlineKeyboardButton("🔙 К бизнесу", callback_data="biz_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "fp_business_tax_reports")
async def feature_business_tax_reports(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    is_tax_officer = (user.get("organization") or "") == "Налоговая служба"
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
            [InlineKeyboardButton("🔎 Каталог объектов", callback_data="property_catalog")],
            [InlineKeyboardButton("🏠 Мое имущество", callback_data="my_property")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
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
        keyboard_rows.append([InlineKeyboardButton(f"Купить #{int(prop['id'])}", callback_data=f"fp_buy_property_{int(prop['id'])}")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="prop_menu")])
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
            keyboard_rows.append([InlineKeyboardButton(f"🏢 В частную орг #{prop_id}", callback_data=f"fp_convert_private_{prop_id}")])
            keyboard_rows.append([InlineKeyboardButton(f"🏪 В бизнес #{prop_id}", callback_data=f"fp_convert_business_{prop_id}")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="prop_menu")])
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
            [InlineKeyboardButton("🍔 Ресторан", callback_data=f"fp_business_type_{prop_id}_restaurant")],
            [InlineKeyboardButton("🛒 Магазин", callback_data=f"fp_business_type_{prop_id}_shop")],
            [InlineKeyboardButton("🏭 Производство", callback_data=f"fp_business_type_{prop_id}_factory")],
            [InlineKeyboardButton("🏨 Отель", callback_data=f"fp_business_type_{prop_id}_hotel")],
            [InlineKeyboardButton("📡 Медиа", callback_data=f"fp_business_type_{prop_id}_media")],
            [InlineKeyboardButton("💻 IT", callback_data=f"fp_business_type_{prop_id}_it")],
            [InlineKeyboardButton("🔙 Назад", callback_data="my_property")],
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
    lines = ["🏢 **ЧАСТНЫЕ ОРГАНИЗАЦИИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not orgs:
        lines.append("Пока нет частных организаций.")
    else:
        for org in orgs:
            lines.append(
                f"• **{_md(str(org.get('name')))}** | Лидер: {_md(str(org.get('leader_name') or 'Неизвестно'))}\n"
                f"  Бюджет: ${float(org.get('budget') or 0):,.0f}"
            )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("🆕 Создать частную организацию", callback_data="fp_private_org_create_start")],
            [InlineKeyboardButton("🏠 Моя недвижимость", callback_data="my_property")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
        ]
    )
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
        [InlineKeyboardButton(f"🏢 {p.get('name')} (${float(p.get('price') or 0):,.0f})", callback_data=f"fp_private_org_pickprop_{int(p['id'])}")]
        for p in free_props[:12]
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="private_org_list")])
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


@router.message(FeatureStates.private_org_name, F.text)
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


@router.message(Command("edu"))
@router.callback_query(F.data == "edu_menu")
async def feature_education_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    status = await db.get_user_education_status(event.from_user.id)
    user = status.get("user") or {}
    active = status.get("active_enrollment")
    lines = [
        "🎓 **ОБРАЗОВАНИЕ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Текущий уровень: {int(user.get('education') or 1)}",
        f"Завершенных программ: {int(status.get('completed_count') or 0)}",
        "",
    ]
    if active:
        lines.extend(
            [
                f"Активная программа: **{_md(str(active.get('program_name')))}**",
                f"Прогресс: {int(active.get('progress_days') or 0)}/{int(active.get('duration_days') or 1)} дней",
            ]
        )
    else:
        lines.append("Активной программы нет.")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("📚 Программы", callback_data="view_education_programs")],
            [InlineKeyboardButton("🧠 Учиться (теория)", callback_data="fp_study_theory")],
            [InlineKeyboardButton("🧪 Учиться (практика)", callback_data="fp_study_practice")],
            [InlineKeyboardButton("📈 Мой прогресс", callback_data="education_progress")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "view_education_programs")
async def feature_view_programs(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    programs = await db.list_education_programs(active_only=True, limit=15)
    lines = ["📚 **ПРОГРАММЫ ОБУЧЕНИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    for program in programs:
        lines.append(
            f"• **{_md(str(program.get('name')))}**\n"
            f"  Длительность: {int(program.get('duration_days') or 0)} дн. | "
            f"Цена: ${float(program.get('tuition_fee') or 0):,.0f} | "
            f"Мин.уровень: {int(program.get('min_education') or 1)}"
        )
        keyboard_rows.append([InlineKeyboardButton(f"Поступить #{int(program['id'])}", callback_data=f"fp_edu_enroll_{int(program['id'])}")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")])
    await callback.message.edit_text(
        "\n".join(lines) if programs else "Нет активных программ.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown" if programs else None,
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
    lines = ["📈 **МОЙ ПРОГРЕСС ОБУЧЕНИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not active:
        lines.append("Активного обучения нет.")
    else:
        lines.extend(
            [
                f"Программа: **{_md(str(active.get('program_name')))}**",
                f"Дни прогресса: {int(active.get('progress_days') or 0)} / {int(active.get('duration_days') or 1)}",
                f"Последняя учеба: {str(active.get('last_study_date') or 'еще не было')[:16]}",
            ]
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=_back("edu_menu"), parse_mode="Markdown")


@router.callback_query(F.data.in_({"fp_study_theory", "fp_study_practice"}))
async def feature_study_session(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mode = "practice" if callback.data.endswith("practice") else "theory"
    success, msg, payload = await db.study_education_session(callback.from_user.id, mode=mode)
    if not success:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
        return
    payload = payload or {}
    await callback.message.answer(
        f"✅ {msg}\n"
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
    user = await db.get_user(event.from_user.id) or {}
    lines = [
        "💼 **РАБОТА И ПОДРАБОТКИ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Текущая работа: {user.get('citizen_job') or 'нет'}",
        f"Зарплата: ${float(user.get('citizen_salary') or 0):,.0f}/день",
        "",
        "Можно зарабатывать без профессии через мини-игры: легально и нелегально.",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("🎯 Подработки", callback_data="side_hustle_menu")],
            [InlineKeyboardButton("📋 Вакансии", callback_data="view_citizen_jobs")],
            [InlineKeyboardButton("💼 Мой статус", callback_data="citizen_work_status")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


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
            [InlineKeyboardButton("✅ Легальная подработка", callback_data="fp_hustle_start_legal")],
            [InlineKeyboardButton("🕶️ Нелегальная подработка", callback_data="fp_hustle_start_illegal")],
            [InlineKeyboardButton("🔙 Назад", callback_data="work_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.in_({"fp_hustle_start_legal", "fp_hustle_start_illegal"}))
async def feature_hustle_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    hustle_type = "legal" if callback.data.endswith("legal") else "illegal"
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
                InlineKeyboardButton("🧰 Кейс 1", callback_data="fp_hustle_guess_1"),
                InlineKeyboardButton("🧰 Кейс 2", callback_data="fp_hustle_guess_2"),
                InlineKeyboardButton("🧰 Кейс 3", callback_data="fp_hustle_guess_3"),
            ],
            [InlineKeyboardButton("🔙 Отмена", callback_data="side_hustle_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


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
                [InlineKeyboardButton("🎯 Еще подработка", callback_data="side_hustle_menu")],
                [InlineKeyboardButton("🔙 В работу", callback_data="work_menu")],
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
        [InlineKeyboardButton(f"Открыть #{int(c['id'])}", callback_data=f"fp_casino_open_{int(c['id'])}")]
        for c in casinos[:10]
    ]
    keyboard_rows.append([InlineKeyboardButton("🆕 Открыть частное казино", callback_data="fp_casino_create")])
    keyboard_rows.append([InlineKeyboardButton("📜 Моя история игр", callback_data="fp_casino_history")])
    keyboard_rows.append([InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")])
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


@router.message(FeatureStates.private_casino_name, F.text)
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
            [InlineKeyboardButton("🪙 Монетка", callback_data=f"fp_casino_coin_{casino_id}")],
            [InlineKeyboardButton("🎲 Кубик", callback_data=f"fp_casino_dice_{casino_id}")],
            [InlineKeyboardButton("🎰 Слоты $5k", callback_data=f"fp_casino_play_{casino_id}_slots_none_5000")],
            [InlineKeyboardButton("🎰 Слоты $20k", callback_data=f"fp_casino_play_{casino_id}_slots_none_20000")],
            [InlineKeyboardButton("🔙 Назад", callback_data="casino_menu")],
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
            [InlineKeyboardButton("Орел $5k", callback_data=f"fp_casino_play_{cid}_coin_heads_5000")],
            [InlineKeyboardButton("Решка $5k", callback_data=f"fp_casino_play_{cid}_coin_tails_5000")],
            [InlineKeyboardButton("Орел $20k", callback_data=f"fp_casino_play_{cid}_coin_heads_20000")],
            [InlineKeyboardButton("Решка $20k", callback_data=f"fp_casino_play_{cid}_coin_tails_20000")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"fp_casino_open_{cid}")],
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
            [InlineKeyboardButton("High (4-6) $5k", callback_data=f"fp_casino_play_{cid}_dice_high_5000")],
            [InlineKeyboardButton("Low (1-3) $5k", callback_data=f"fp_casino_play_{cid}_dice_low_5000")],
            [InlineKeyboardButton("High (4-6) $20k", callback_data=f"fp_casino_play_{cid}_dice_high_20000")],
            [InlineKeyboardButton("Low (1-3) $20k", callback_data=f"fp_casino_play_{cid}_dice_low_20000")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"fp_casino_open_{cid}")],
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
                [InlineKeyboardButton("🎰 Еще сыграть", callback_data=f"fp_casino_open_{cid_raw}")],
                [InlineKeyboardButton("📜 История", callback_data="fp_casino_history")],
                [InlineKeyboardButton("🔙 В казино", callback_data="casino_menu")],
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


@router.message(Command("news"))
@router.callback_query(F.data == "media_news_menu")
async def feature_media_news(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    rows = await db.get_latest_media_news(limit=18)
    lines = ["📰 **ЛЕНТА СМИ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Новостей пока нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            lines.append(f"[{created}] **{_md(str(row.get('title') or 'Новость'))}**")
            lines.append(_md(str(row.get("body") or "")))
            lines.append("")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("🔄 Обновить", callback_data="media_news_menu")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("market"))
@router.callback_query(F.data == "market_menu")
async def feature_market_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
    text = (
        "📣 **ГОРОДСКАЯ ПЛОЩАДКА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Новости, казино, подработки и небольшие пасхалки."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("📰 Новости СМИ", callback_data="media_news_menu")],
            [InlineKeyboardButton("📋 Контракты", callback_data="view_contracts")],
            [InlineKeyboardButton("✍️ Создать контракт", callback_data="create_contract")],
            [InlineKeyboardButton("🎰 Казино", callback_data="casino_menu")],
            [InlineKeyboardButton("🎯 Подработки", callback_data="side_hustle_menu")],
            [InlineKeyboardButton("🥚 Пасхалка дня", callback_data="fp_easter_egg")],
            [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
        ]
    )
    sender = _edit_or_answer(event)
    await sender(text, reply_markup=keyboard, parse_mode="Markdown")


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
            inline_keyboard=[[InlineKeyboardButton("🕶️ Банды", callback_data="gang_list")]]
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
            [InlineKeyboardButton(f"Вступить в #{int(g['id'])}", callback_data=f"fp_gang_join_{int(g['id'])}")]
            for g in gangs[:10]
        ]
        keyboard_rows.append([InlineKeyboardButton("🆕 Создать банду", callback_data="fp_gang_create")])
        keyboard_rows.append([InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")])
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
        keyboard_rows.append([InlineKeyboardButton("☠️ Создать картель", callback_data=f"fp_cartel_create_{int(user_gang['id'])}")])
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
                [InlineKeyboardButton("🧪 Производство", callback_data="fp_cartel_op_produce")],
                [InlineKeyboardButton("🚚 Сбыт", callback_data="fp_cartel_op_smuggle")],
                [InlineKeyboardButton("🧼 Отмывание", callback_data="fp_cartel_op_launder")],
            ]
        )
    keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="gang_list")])
    keyboard_rows.append([InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")])
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


@router.message(FeatureStates.gang_name, F.text)
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


@router.message(FeatureStates.cartel_name, F.text)
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
            keyboard_rows.append([InlineKeyboardButton(f"✏️ Ред. #{int(rule['id'])}", callback_data=f"pres_law_edit_{int(rule['id'])}")])
            keyboard_rows.append([InlineKeyboardButton(f"🔁 Статус #{int(rule['id'])}", callback_data=f"pres_law_toggle_{int(rule['id'])}")])
    keyboard_rows.append([InlineKeyboardButton("➕ Новый закон", callback_data="pres_law_add")])
    keyboard_rows.append([InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")])
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


@router.message(FeatureStates.law_create, F.text)
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


@router.message(FeatureStates.law_edit, F.text)
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
            [InlineKeyboardButton("✏️ Установить текст", callback_data="pres_flag_set_text")],
            [InlineKeyboardButton("🖼️ Загрузить фото", callback_data="pres_flag_set_photo")],
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")],
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


@router.message(FeatureStates.flag_text, F.text)
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
        keyboard_rows.append([InlineKeyboardButton(f"Каникулы #{int(biz['id'])}", callback_data=f"pres_tax_holiday_pick_{int(biz['id'])}")])
    keyboard_rows.append([InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")])
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


@router.message(FeatureStates.tax_holiday_reason, F.text)
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
                keyboard_rows.append([InlineKeyboardButton(f"✅ Взять #{cid}", callback_data=f"fp_contract_claim_{cid}")])
                actions_added += 1
            if status == "open" and creator_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(f"🛑 Отменить #{cid}", callback_data=f"fp_contract_cancel_{cid}")])
                actions_added += 1
            if status == "claimed" and assignee_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(f"🏁 Сдать #{cid}", callback_data=f"fp_contract_complete_{cid}")])
                actions_added += 1
            if status == "claimed" and creator_id == callback.from_user.id and actions_added < 10:
                keyboard_rows.append([InlineKeyboardButton(f"✔️ Подтвердить #{cid}", callback_data=f"fp_contract_complete_{cid}")])
                actions_added += 1
            lines.append("")

    keyboard_rows.append([InlineKeyboardButton("✍️ Создать контракт", callback_data="create_contract")])
    keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="view_contracts")])
    keyboard_rows.append([InlineKeyboardButton("🔙 К рынку", callback_data="market_menu")])
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


@router.message(FeatureStates.contract_title, F.text)
async def feature_contracts_title_input(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 4:
        await message.answer("❌ Название слишком короткое. Минимум 4 символа.", parse_mode=None)
        return
    await state.update_data(contract_title=title)
    await state.set_state(FeatureStates.contract_description)
    await message.answer("Опишите задачу контракта:", parse_mode=None)


@router.message(FeatureStates.contract_description, F.text)
async def feature_contracts_description_input(message: Message, state: FSMContext):
    desc = (message.text or "").strip()
    if len(desc) < 8:
        await message.answer("❌ Описание слишком короткое. Минимум 8 символов.", parse_mode=None)
        return
    await state.update_data(contract_description=desc)
    await state.set_state(FeatureStates.contract_reward)
    await message.answer("Введите награду в долларах (например: 15000):", parse_mode=None)


@router.message(FeatureStates.contract_reward, F.text)
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
                InlineKeyboardButton("⬆️ +10%", callback_data="fp_bank_dep_10"),
                InlineKeyboardButton("⬆️ +25%", callback_data="fp_bank_dep_25"),
                InlineKeyboardButton("⬆️ +50%", callback_data="fp_bank_dep_50"),
                InlineKeyboardButton("⬆️ Всё", callback_data="fp_bank_dep_100"),
            ],
            [
                InlineKeyboardButton("⬇️ -10%", callback_data="fp_bank_wd_10"),
                InlineKeyboardButton("⬇️ -25%", callback_data="fp_bank_wd_25"),
                InlineKeyboardButton("⬇️ -50%", callback_data="fp_bank_wd_50"),
                InlineKeyboardButton("⬇️ Всё", callback_data="fp_bank_wd_100"),
            ],
            [InlineKeyboardButton("✍️ Внести сумму вручную", callback_data="fp_bank_dep_manual")],
            [InlineKeyboardButton("✍️ Снять сумму вручную", callback_data="fp_bank_wd_manual")],
            [InlineKeyboardButton("📊 История", callback_data="bank_history")],
            [InlineKeyboardButton("🔙 Назад", callback_data="bank_menu")],
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


@router.message(FeatureStates.bank_deposit_amount, F.text)
async def feature_bank_dep_manual_input(message: Message, state: FSMContext):
    amount = _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите корректную сумму.", parse_mode=None)
        return
    await state.clear()
    ok, msg, _ = await db.deposit_to_bank(message.from_user.id, amount, note="manual")
    await message.answer(("✅ " if ok else "❌ ") + msg, reply_markup=_back("bank_deposit"), parse_mode=None)


@router.message(FeatureStates.bank_withdraw_amount, F.text)
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
    if not (_is_police_user(user) or await db.is_fbi_agent(callback.from_user.id)):
        await callback.answer("Доступ только для полиции/ФБР.", show_alert=True)
        return

    suspects = await db.get_police_suspects(limit=14, exclude_user_id=callback.from_user.id)
    lines = ["🔍 **РОЗЫСК ПОДОЗРЕВАЕМЫХ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    keyboard_rows = []
    if not suspects:
        lines.append("Подозреваемые не найдены.")
    else:
        for row in suspects[:10]:
            sid = int(row.get("user_id") or 0)
            risk = float(row.get("risk_score") or 0)
            lines.append(
                f"#{sid} {_md(str(row.get('full_name') or row.get('username') or sid))}\n"
                f"Риск: {risk:.1f} | Преступления: {int(row.get('crimes_committed') or 0)} | "
                f"Налоговый долг: ${float(row.get('tax_debt') or 0):,.0f}"
            )
            lines.append("")
            keyboard_rows.append([InlineKeyboardButton(f"⛓️ Арест #{sid}", callback_data=f"fp_police_arrest_pick_{sid}")])
    keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="police_search_suspects")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="police_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("fp_police_arrest_pick_"))
async def feature_police_arrest_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sid_raw = callback.data.replace("fp_police_arrest_pick_", "")
    if not sid_raw.isdigit():
        await callback.answer("Некорректный игрок.", show_alert=True)
        return
    sid = int(sid_raw)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("💰 Уклонение от налогов", callback_data=f"fp_police_arrest_do_{sid}_tax")],
            [InlineKeyboardButton("🧾 Финансовое мошенничество", callback_data=f"fp_police_arrest_do_{sid}_fraud")],
            [InlineKeyboardButton("🕵️ Коррупционная деятельность", callback_data=f"fp_police_arrest_do_{sid}_corrupt")],
            [InlineKeyboardButton("⚠️ Нарушение порядка", callback_data=f"fp_police_arrest_do_{sid}_order")],
            [InlineKeyboardButton("🔙 Назад", callback_data="police_search_suspects")],
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
    if len(parts) != 2 or not parts[0].isdigit():
        await callback.answer("Некорректные параметры ареста.", show_alert=True)
        return
    suspect_id = int(parts[0])
    code = parts[1]
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
    await feature_police_search_suspects(callback, state)


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


# ---------------------------------------------------------------------------
# Court handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "court_cases")
async def feature_court_cases(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await db.get_user(callback.from_user.id) or {}
    is_judge = _is_judge_user(user)
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
                keyboard_rows.append([InlineKeyboardButton(f"🕒 Слушание #{case_id}", callback_data=f"fp_court_hearing_{case_id}")])
                keyboard_rows.append([InlineKeyboardButton(f"✅ Закрыть #{case_id}", callback_data=f"fp_court_close_{case_id}")])
                keyboard_rows.append([InlineKeyboardButton(f"🛑 Отклонить #{case_id}", callback_data=f"fp_court_dismiss_{case_id}")])
    keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="court_cases")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="court_menu")])
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
    is_judge = _is_judge_user(user)
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

async def _get_managed_org_for_user(user_id: int) -> Optional[dict]:
    user = await db.get_user(user_id) or {}
    org_name = str(user.get("organization") or "").strip()
    if not org_name:
        return None
    org = await db.get_organization(org_name)
    if not org:
        return None
    if int(org.get("leader_id") or 0) == int(user_id) or int(org.get("deputy_id") or 0) == int(user_id):
        return org
    return None


@router.callback_query(F.data == "review_applications")
async def feature_review_applications(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    org = await _get_managed_org_for_user(callback.from_user.id)
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
                    InlineKeyboardButton(f"✅ Принять #{aid}", callback_data=f"fp_org_app_accept_{aid}"),
                    InlineKeyboardButton(f"❌ Отклонить #{aid}", callback_data=f"fp_org_app_reject_{aid}"),
                ]
            )
    keyboard_rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="review_applications")])
    keyboard_rows.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_organization")])
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
    org = await _get_managed_org_for_user(callback.from_user.id)
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
            lines.append(
                f"• {_md(str(row.get('full_name') or row.get('username') or row.get('user_id')))}\n"
                f"  Роль: {_md(str(row.get('role') or 'Сотрудник'))} | "
                f"Зарплата: ${float(row.get('salary') or 0):,.0f}"
            )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("manage_organization"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "org_finances")
async def feature_org_finances(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    org = await _get_managed_org_for_user(callback.from_user.id)
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
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_back("manage_organization"),
        parse_mode="Markdown",
    )
