"""
presidential_admin.py - Админ-панель президента и расширенные финансовые полномочия
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db

logger = logging.getLogger(__name__)
router = Router()


class PresidentStates(StatesGroup):
    admin_panel = State()
    appointing_position = State()
    transfer_amount = State()
    transfer_reason = State()


def _normalize_government(gov: dict | None) -> dict:
    gov = gov or {}
    return {
        "current_leader_id": gov.get("current_leader_id"),
        "government_type": gov.get("government_type") or gov.get("current_type") or "democracy",
        "stability": int(gov.get("stability", 50) or 50),
        "corruption": int(gov.get("corruption", 0) or 0),
        "satisfaction": int(gov.get("public_satisfaction", gov.get("satisfaction", 60)) or 60),
    }


def _authority_label(authority: str | None) -> str:
    mapping = {
        "president": "Президент",
        "vice_president": "Вице-президент",
        "finance_minister": "Министр финансов",
        "minister": "Министр",
    }
    return mapping.get(authority or "", "Нет полномочий")


def _gov_type_label(code: str) -> str:
    mapping = {
        "democracy": "Демократия",
        "monarchy": "Монархия",
        "dictatorship": "Диктатура",
    }
    return mapping.get((code or "").lower(), code or "Демократия")


def _player_display(player: dict) -> str:
    full_name = (player.get("full_name") or "").strip()
    username = (player.get("username") or "").strip()
    user_id = int(player.get("user_id") or 0)
    display = full_name or (f"@{username}" if username else f"ID {user_id}")
    if len(display) > 32:
        return display[:29] + "..."
    return display


async def _get_authority(user_id: int) -> str | None:
    return await db.get_government_authority(user_id)


async def _render_admin_panel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    authority = await _get_authority(user_id)
    if authority is None:
        await callback.answer("❌ Доступ только для руководства государства.", show_alert=True)
        return

    gov = _normalize_government(await db.get_government_system())
    gov_type = _gov_type_label(gov.get("government_type", "democracy"))
    has_full_admin = authority == "president"

    text_lines = [
        "👑 АДМИН-ПАНЕЛЬ ГОСУДАРСТВА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Доступ: {_authority_label(authority)}",
        f"Форма правления: {gov_type}",
        f"Стабильность: {gov.get('stability', 50)}/100",
        f"Коррупция: {gov.get('corruption', 0)}/100",
        f"Удовлетворение населения: {gov.get('satisfaction', 60)}/100",
        "",
        "Управляйте назначениями и финансами государства.",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []
    if has_full_admin:
        keyboard.append([InlineKeyboardButton("👤 Назначение должностей", callback_data="pres_appoint")])
        keyboard.append([InlineKeyboardButton("🏛️ Форма правления", callback_data="pres_change_government")])
        keyboard.append([
            InlineKeyboardButton("📜 Законы", callback_data="pres_laws"),
            InlineKeyboardButton("🏳️ Флаг", callback_data="pres_flag_menu"),
        ])
        keyboard.append([InlineKeyboardButton("🧾 Налог. каникулы", callback_data="pres_tax_holiday_menu")])

    keyboard.append([InlineKeyboardButton("💸 Гос. перевод", callback_data="pres_transfer_start")])
    keyboard.append([
        InlineKeyboardButton("📜 Логи переводов", callback_data="pres_transfer_logs"),
        InlineKeyboardButton("🕶️ Коррупция", callback_data="pres_corruption_logs"),
    ])
    keyboard.append([InlineKeyboardButton("🆘 Помощь", callback_data="pres_help")])
    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")])

    await state.set_state(PresidentStates.admin_panel)
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data == "president_admin_panel")
async def president_admin_panel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _render_admin_panel(callback, state)


@router.callback_query(F.data == "pres_appoint")
async def president_appoint_select_org(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Назначения доступны только президенту.", show_alert=True)
        return

    organizations = await db.list_organizations()
    keyboard: list[list[InlineKeyboardButton]] = []
    for org in organizations:
        org_id = int(org.get("id") or 0)
        if org_id <= 0:
            continue
        keyboard.append([InlineKeyboardButton(str(org.get("name") or org_id), callback_data=f"pres_appoint_org_{org_id}_0")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="president_admin_panel")])

    await state.set_state(PresidentStates.appointing_position)
    await callback.message.edit_text(
        "🏛️ Выберите организацию для назначения сотрудника:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )
    await callback.answer()


async def _render_org_player_picker(callback: CallbackQuery, org_id: int, page: int = 0):
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    page_size = 8
    total = await db.count_players()
    max_page = (total - 1) // page_size if total > 0 else 0
    page = max(0, min(page, max_page))
    offset = page * page_size
    players = await db.get_players_page(limit=page_size, offset=offset)

    text_lines = [
        "👤 НАЗНАЧЕНИЕ СОТРУДНИКА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Организация: {org.get('name')}",
        f"Страница: {page + 1}/{max_page + 1}",
        "",
        "Выберите игрока:",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []
    for player in players:
        player_id = int(player.get("user_id") or 0)
        if player_id <= 0:
            continue
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {_player_display(player)}",
                callback_data=f"pres_set_position_{org_id}_{player_id}_{page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"pres_appoint_org_{org_id}_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"pres_appoint_org_{org_id}_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 К организациям", callback_data="pres_appoint")])

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("pres_appoint_org_"))
async def president_select_player_for_position(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Назначения доступны только президенту.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Некорректные данные организации.", show_alert=True)
        return

    try:
        org_id = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 0
    except ValueError:
        await callback.answer("❌ Некорректные параметры.", show_alert=True)
        return

    await _render_org_player_picker(callback, org_id, page)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_set_position_"))
async def president_set_position(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Назначения доступны только президенту.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 6:
        await callback.answer("❌ Некорректные параметры назначения.", show_alert=True)
        return

    try:
        org_id = int(parts[3])
        player_id = int(parts[4])
        page = int(parts[5])
    except ValueError:
        await callback.answer("❌ Некорректные параметры назначения.", show_alert=True)
        return

    player = await db.get_user(player_id)
    org = await db.get_organization_by_id(org_id)
    if not player or not org:
        await callback.answer("❌ Игрок или организация не найдены.", show_alert=True)
        return

    role_buttons = [
        ("👑 Лидер", "leader"),
        ("🏆 Заместитель", "deputy"),
        ("🧾 Министр", "minister"),
        ("💰 Министр финансов", "finance"),
        ("🛡️ Вице-президент", "vicepres"),
        ("👤 Сотрудник", "member"),
    ]

    keyboard = [[
        InlineKeyboardButton(
            title,
            callback_data=f"pres_confirm_position_{org_id}_{player_id}_{role_code}_{page}",
        )
    ] for title, role_code in role_buttons]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"pres_appoint_org_{org_id}_{page}")])

    text = (
        "📌 Назначение должности\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Организация: {org.get('name')}\n"
        f"Игрок: {_player_display(player)}\n\n"
        "Выберите роль:"
    )

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_confirm_position_"))
async def president_confirm_position(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Назначения доступны только президенту.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 7:
        await callback.answer("❌ Некорректные данные подтверждения.", show_alert=True)
        return

    try:
        org_id = int(parts[3])
        player_id = int(parts[4])
        role_code = parts[5]
        page = int(parts[6])
    except ValueError:
        await callback.answer("❌ Некорректные параметры подтверждения.", show_alert=True)
        return

    role_map = {
        "leader": "Лидер",
        "deputy": "Заместитель",
        "minister": "Министр",
        "finance": "Министр финансов",
        "vicepres": "Вице-президент",
        "member": "Сотрудник",
    }
    role_name = role_map.get(role_code, "Сотрудник")

    success, msg = await db.appoint_user_to_organization(
        target_user_id=player_id,
        org_id=org_id,
        role=role_name,
        appointed_by_id=callback.from_user.id,
    )

    if not success:
        await callback.message.edit_text(
            f"❌ {msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("🔙 Назад", callback_data=f"pres_appoint_org_{org_id}_{page}")]
            ]),
            parse_mode=None,
        )
        await callback.answer()
        return

    player = await db.get_user(player_id) or {}
    org = await db.get_organization_by_id(org_id) or {}
    text = (
        "✅ Назначение выполнено\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Игрок: {_player_display(player)}\n"
        f"Организация: {org.get('name', org_id)}\n"
        f"Роль: {role_name}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("👥 Продолжить назначения", callback_data=f"pres_appoint_org_{org_id}_{page}")],
        [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "pres_change_government")
async def president_change_government(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Только президент может менять форму правления.", show_alert=True)
        return

    gov = _normalize_government(await db.get_government_system())
    current = _gov_type_label(gov.get("government_type", "democracy"))

    text = (
        "🏛️ Смена формы правления\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Текущая форма: {current}\n\n"
        "Выберите новую форму:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🗳️ Демократия", callback_data="pres_gov_democracy")],
        [InlineKeyboardButton("👑 Монархия", callback_data="pres_gov_monarchy")],
        [InlineKeyboardButton("⚡ Диктатура", callback_data="pres_gov_dictatorship")],
        [InlineKeyboardButton("🔙 Назад", callback_data="president_admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_gov_"))
async def president_confirm_government_change(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Только президент может менять форму правления.", show_alert=True)
        return

    gov_code = callback.data.replace("pres_gov_", "").strip().lower()
    if gov_code not in {"democracy", "monarchy", "dictatorship"}:
        await callback.answer("❌ Неизвестная форма правления.", show_alert=True)
        return

    await db.update_government_system(current_type=gov_code, last_changed=datetime.now().isoformat())

    text = (
        "✅ Форма правления обновлена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Новая форма: {_gov_type_label(gov_code)}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "pres_transfer_start")
async def pres_transfer_start(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority is None:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return

    text = (
        "💸 Государственные переводы\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите режим перевода:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("👥 Выдать игроку", callback_data="pres_transfer_mode_public")],
        [InlineKeyboardButton("🕶️ Подпольная схема", callback_data="pres_transfer_mode_shadow")],
        [InlineKeyboardButton("💼 Взять себе", callback_data="pres_transfer_mode_self")],
        [InlineKeyboardButton("🔙 Назад", callback_data="president_admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


async def _render_transfer_target_picker(callback: CallbackQuery, mode: str, page: int = 0):
    page_size = 8
    total = await db.count_players()
    max_page = (total - 1) // page_size if total > 0 else 0
    page = max(0, min(page, max_page))
    offset = page * page_size
    players = await db.get_players_page(limit=page_size, offset=offset)

    text = (
        "👥 Выбор получателя\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Режим: {'Подпольно' if mode == 'shadow' else 'Открыто'}\n"
        f"Страница: {page + 1}/{max_page + 1}"
    )

    keyboard: list[list[InlineKeyboardButton]] = []
    for player in players:
        player_id = int(player.get("user_id") or 0)
        if player_id <= 0:
            continue
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {_player_display(player)}",
                callback_data=f"pres_transfer_select_{mode}_{player_id}_{page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"pres_transfer_page_{mode}_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"pres_transfer_page_{mode}_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="pres_transfer_start")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("pres_transfer_mode_"))
async def pres_transfer_mode(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority is None:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return

    mode = callback.data.replace("pres_transfer_mode_", "").strip().lower()
    if mode not in {"public", "shadow", "self"}:
        await callback.answer("❌ Некорректный режим перевода.", show_alert=True)
        return

    if mode == "self":
        await state.update_data(transfer_mode=mode, transfer_target_id=callback.from_user.id)
        await state.set_state(PresidentStates.transfer_amount)
        await callback.message.answer(
            "💵 Введите сумму, которую хотите вывести из бюджета:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("🔙 Отмена", callback_data="pres_transfer_start")]
            ]),
            parse_mode=None,
        )
        await callback.answer()
        return

    await _render_transfer_target_picker(callback, mode, page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_transfer_page_"))
async def pres_transfer_page(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return

    mode = parts[3]
    try:
        page = int(parts[4])
    except ValueError:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return

    await _render_transfer_target_picker(callback, mode, page)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_transfer_select_"))
async def pres_transfer_select(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    if len(parts) < 6:
        await callback.answer("❌ Некорректный выбор игрока.", show_alert=True)
        return

    mode = parts[3]
    try:
        target_id = int(parts[4])
    except ValueError:
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return

    target = await db.get_user(target_id)
    if not target:
        await callback.answer("❌ Игрок не найден.", show_alert=True)
        return

    await state.update_data(transfer_mode=mode, transfer_target_id=target_id)
    await state.set_state(PresidentStates.transfer_amount)
    await callback.message.answer(
        f"💵 Введите сумму для перевода игроку {_player_display(target)}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 Отмена", callback_data="pres_transfer_start")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


@router.message(PresidentStates.transfer_amount, F.text)
async def pres_transfer_amount_input(message: Message, state: FSMContext):
    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("❌ Введите корректную сумму числом, например: 150000")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return
    if amount > 10_000_000_000:
        await message.answer("❌ Слишком большая сумма.")
        return

    await state.update_data(transfer_amount=amount)
    await state.set_state(PresidentStates.transfer_reason)
    await message.answer("📝 Укажите комментарий/причину перевода:", parse_mode=None)


@router.message(PresidentStates.transfer_reason, F.text)
async def pres_transfer_reason_input(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = str(data.get("transfer_mode") or "public")
    target_id = int(data.get("transfer_target_id") or 0)
    amount = float(data.get("transfer_amount") or 0)
    reason = (message.text or "").strip()

    if target_id <= 0 or amount <= 0:
        await state.clear()
        await message.answer("❌ Сессия перевода устарела.")
        return

    success, msg, details = await db.issue_state_funds(
        actor_id=message.from_user.id,
        target_id=target_id,
        amount=amount,
        reason=reason,
        is_shadow=(mode == "shadow"),
    )

    await state.clear()

    if not success:
        await message.answer(
            f"❌ {msg}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
            ]),
            parse_mode=None,
        )
        return

    text = (
        "✅ Перевод выполнен\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"ID операции: {details.get('transfer_id')}\n"
        f"Тип: {'Подпольный' if details.get('is_shadow') else 'Открытый'}\n"
        f"Сумма: ${details.get('amount', 0):,.2f}\n"
        f"Новый бюджет правительства: ${details.get('new_budget', 0):,.2f}\n"
        f"Полномочие: {_authority_label(details.get('authority'))}\n"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("💸 Новый перевод", callback_data="pres_transfer_start")],
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")],
        ]),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_transfer_logs")
async def pres_transfer_logs(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority is None:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return

    rows = await db.get_recent_privileged_transfers(limit=15)
    lines = [
        "📜 ЛОГИ ГОСУДАРСТВЕННЫХ ПЕРЕВОДОВ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not rows:
        lines.append("Логов пока нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            actor = row.get("actor_name") or f"ID {row.get('actor_id')}"
            target = row.get("target_name") or f"ID {row.get('target_id')}"
            amount = float(row.get("amount") or 0)
            shadow = "🕶️" if int(row.get("is_shadow") or 0) == 1 else ""
            lines.append(f"[{created}] {shadow} {actor} → {target}: ${amount:,.2f}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "pres_corruption_logs")
async def pres_corruption_logs(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority is None:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return

    rows = await db.get_recent_corruption_ops(limit=15)
    lines = [
        "🕶️ КОРРУПЦИОННЫЕ СХЕМЫ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not rows:
        lines.append("Схем не зафиксировано.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            actor = row.get("actor_name") or f"ID {row.get('actor_id')}"
            target = row.get("target_name") or "—"
            op_type = row.get("op_type") or "operation"
            amount = float(row.get("amount") or 0)
            risk = int(row.get("risk") or 0)
            lines.append(f"[{created}] {op_type}: {actor} -> {target} | ${amount:,.2f} | риск {risk}/100")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


# Совместимость со старыми кнопками (переименование/создание должностей)
@router.callback_query(F.data == "pres_rename_position")
@router.callback_query(F.data.startswith("pres_rename_"))
@router.callback_query(F.data == "pres_create_position")
@router.callback_query(F.data == "pres_new_position_input")
async def president_legacy_position_tools(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "ℹ️ Этот раздел объединен в меню назначения должностей.\n"
        "Используйте: '👤 Назначение должностей'.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_help")
async def president_help(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = (
        "🆘 ПОМОЩЬ ПО ГОСПАНЕЛИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. Президент может назначать любых игроков в любые организации.\n"
        "2. Президент, вице-президент и министры могут проводить гос.переводы.\n"
        "3. Режим 'Подпольная схема' отправляет средства в теневой баланс и увеличивает коррупционные риски.\n"
        "4. Президент может редактировать законы, обновлять флаг и давать налоговые каникулы бизнесам.\n"
        "5. Все операции логируются в разделе 'Логи переводов' и 'Коррупция'."
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_rename_pos")
async def legacy_pres_rename_pos(callback: CallbackQuery, state: FSMContext):
    """Совместимость со старой кнопкой."""
    await president_legacy_position_tools(callback, state)


@router.callback_query(F.data == "pres_appoint_president")
async def legacy_pres_appoint_president(callback: CallbackQuery, state: FSMContext):
    """Совместимость со старой кнопкой назначения президента."""
    await callback.answer()
    await callback.message.edit_text(
        "ℹ️ Назначение президента выполняется через обычное меню назначений в организацию 'Правительство'.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("👤 Перейти к назначениям", callback_data="pres_appoint")],
            [InlineKeyboardButton("🔙 В панель", callback_data="president_admin_panel")],
        ]),
        parse_mode=None,
    )
