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
    OrganizationStates
)
from keyboards import (
    get_back_button, get_organization_list_keyboard, OrgCallback
)
from ui_media import send_section_screen

logger = logging.getLogger(__name__)
router = Router()

INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")


def _safe_text(value, default: str = "—") -> str:
    """Безопасно преобразовать значение в отображаемую строку."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _clean_name(value) -> str:
    text = str(value or "")
    for token in INVISIBLE_NAME_CHARS:
        text = text.replace(token, "")
    return " ".join(text.split()).strip()


def _display_name_from_row(row: dict | None, fallback_id: int | None = None) -> str:
    row = row or {}
    for key in ("display_name", "nickname", "full_name"):
        val = _clean_name(row.get(key))
        if val:
            return val
    username = _clean_name(row.get("username")).lstrip("@")
    if username:
        return f"@{username}"
    uid = row.get("user_id") or fallback_id or "?"
    return f"Игрок #{uid}"


def _normalized(value: str | None) -> str:
    return str(value or "").strip().lower()


def _org_kind(org: dict | None) -> str:
    info = org or {}
    org_type = _normalized(info.get("type"))
    name = _normalized(info.get("name"))
    if org_type:
        if org_type in {"government", "police", "hospital", "court", "bank", "education", "fbi", "tax"}:
            return org_type
    if "правитель" in name:
        return "government"
    if "полиц" in name:
        return "police"
    if "больниц" in name or "госпитал" in name:
        return "hospital"
    if "суд" in name:
        return "court"
    if "банк" in name:
        return "bank"
    if "универс" in name or "образов" in name:
        return "education"
    if "фбр" in name:
        return "fbi"
    if "налог" in name:
        return "tax"
    return org_type or "unknown"


async def _can_manage_org(
    user_id: int,
    org: dict | None,
) -> bool:
    info = org or {}
    org_id = int(info.get("id") or 0)
    if org_id <= 0:
        return False

    return await db.can_manage_organization(user_id, org_id)


async def _can_broadcast_org_news_to_groups(
    user_id: int,
    org: dict | None,
) -> bool:
    info = org or {}
    safe_user = int(user_id or 0)
    if safe_user <= 0:
        return False
    if safe_user == int(info.get("leader_id") or 0):
        return True
    authority = await db.get_government_authority(safe_user)
    return authority == "president"


async def _get_manageable_orgs(user_id: int) -> list[dict]:
    orgs_short = await db.list_organizations()
    manageable: list[dict] = []

    for short in orgs_short:
        org_id = int(short.get("id") or 0)
        if org_id <= 0:
            continue
        org = await db.get_organization_by_id(org_id)
        if not org:
            continue
        if await _can_manage_org(user_id, org):
            manageable.append(org)

    manageable.sort(key=lambda x: _normalized(x.get("name")))
    return manageable


async def _broadcast_government_news_to_groups(
    bot,
    org: dict,
    title: str,
    body: str,
    news_id: int,
) -> tuple[int, int]:
    """Отправить новость правительства во все активные группы бота."""
    chats = await db.get_active_group_chats()
    if not chats:
        return 0, 0

    org_name = _safe_text(org.get("name"), "Правительство")
    clean_title = " ".join(str(title or "").split()).strip()
    clean_body = " ".join(str(body or "").split()).strip()
    if len(clean_body) > 900:
        clean_body = clean_body[:900].rstrip() + "..."
    text = (
        "📣 ОФИЦИАЛЬНОЕ СООБЩЕНИЕ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Источник: {org_name}\n"
        f"Заголовок: {clean_title}\n\n"
        f"{clean_body}\n\n"
        f"ID новости: {int(news_id or 0)}"
    )

    sent = 0
    failed = 0
    for chat in chats:
        chat_id = int(chat.get("chat_id") or 0)
        if chat_id == 0:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


def _leader_panel_keyboard(org: dict, can_fire_leader: bool = False) -> list[list[InlineKeyboardButton]]:
    org_id = int(org.get("id") or 0)
    kind = _org_kind(org)
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📋 Заявки", callback_data=f"review_applications_{org_id}"),
            InlineKeyboardButton(text="👥 Сотрудники", callback_data=f"manage_members_{org_id}"),
        ],
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data=f"org_finances_{org_id}"),
            InlineKeyboardButton(text="💬 Чат", callback_data=f"org_chat_{org_id}"),
        ],
        [
            InlineKeyboardButton(text="💸 Выплата игроку", callback_data=f"org_pay_start_{org_id}_0"),
        ],
        [
            InlineKeyboardButton(text="📢 Пресс-центр", callback_data=f"org_news_start_{org_id}"),
            InlineKeyboardButton(text="📊 Активность", callback_data=f"org_activity_{org_id}"),
        ],
    ]

    if kind == "fbi":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="📡 Перехват", callback_data="fbi_intercept_messages"),
                    InlineKeyboardButton(text="🎯 Слежка", callback_data="fbi_track_player"),
                ],
                [
                    InlineKeyboardButton(text="🛡 Санкции", callback_data="fbi_penalty_menu"),
                    InlineKeyboardButton(text="🧠 Операции", callback_data="fbi_operations"),
                ],
                [
                    InlineKeyboardButton(text="📊 Аналитика", callback_data="fbi_statistics"),
                    InlineKeyboardButton(text="🚓 Полиция", callback_data="police_menu"),
                ],
                [
                    InlineKeyboardButton(text="⚖️ Суд", callback_data="court_menu"),
                    InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu"),
                ],
                [
                    InlineKeyboardButton(text="📻 Гос-рация", callback_data="gov_radio_menu"),
                    InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                ],
            ]
        )
    elif kind == "police":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="🔍 Розыск", callback_data="police_search_suspects"),
                    InlineKeyboardButton(text="🚨 Аресты", callback_data="police_my_arrests"),
                ],
                [
                    InlineKeyboardButton(text="⚖️ Наказания", callback_data="police_penalty_menu"),
                    InlineKeyboardButton(text="🗂 Расследования", callback_data="police_investigations"),
                ],
                [
                    InlineKeyboardButton(text="⚖️ Суд", callback_data="court_cases"),
                    InlineKeyboardButton(text="📋 Судебный статус", callback_data="court_status"),
                ],
                [
                    InlineKeyboardButton(text="🕵️ ФБР", callback_data="fbi_menu"),
                    InlineKeyboardButton(text="📻 Гос-рация", callback_data="gov_radio_menu"),
                ],
                [
                    InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu"),
                    InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                ],
            ]
        )
    elif kind == "court":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="📂 Дела", callback_data="court_cases"),
                    InlineKeyboardButton(text="👤 Подсудимые", callback_data="court_defendants"),
                ],
                [InlineKeyboardButton(text="📚 История суда", callback_data="court_history")],
            ]
        )
    elif kind == "bank":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="🏦 Банк-панель", callback_data="bank_menu"),
                    InlineKeyboardButton(text="📊 Операции", callback_data="bank_history"),
                ],
                [
                    InlineKeyboardButton(text="💳 Кредитный центр", callback_data="loan_request"),
                    InlineKeyboardButton(text="📄 Мои кредиты", callback_data="loan_my_status"),
                ],
                [
                    InlineKeyboardButton(text="🏪 Бизнесы", callback_data="biz_menu"),
                    InlineKeyboardButton(text="📣 Рынок", callback_data="market_menu"),
                ],
                [InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu")],
            ]
        )
    elif kind == "hospital":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="🩺 Приемы", callback_data="hospital_appointment"),
                    InlineKeyboardButton(text="📋 История", callback_data="hospital_history"),
                ]
            ]
        )
    elif kind == "education":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="🎓 Программы", callback_data="view_education_programs"),
                    InlineKeyboardButton(text="📈 Прогресс", callback_data="education_progress"),
                ]
            ]
        )
    elif kind == "tax":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="🧾 Налог. отчеты", callback_data=f"org_tax_reports_{org_id}"),
                    InlineKeyboardButton(text="📦 Отчеты бизнеса", callback_data=f"org_business_tax_cycle_{org_id}"),
                ],
                [InlineKeyboardButton(text="⚙️ Налог. цикл (ручной)", callback_data=f"org_tax_cycle_{org_id}")],
            ]
        )
    elif kind == "government":
        keyboard.extend(
            [
                [
                    InlineKeyboardButton(text="👑 Гос. панель", callback_data="president_admin_panel"),
                    InlineKeyboardButton(text="📻 Гос-рация", callback_data="gov_radio_menu"),
                ],
                [
                    InlineKeyboardButton(text="📜 Законы", callback_data="pres_laws"),
                    InlineKeyboardButton(text="🧾 Налог. каникулы", callback_data="pres_tax_holiday_menu"),
                ],
            ]
        )

    if can_fire_leader and int(org.get("leader_id") or 0) > 0:
        keyboard.append(
            [
                InlineKeyboardButton(text="🤫 Снять лидера (тихо)", callback_data=f"org_fire_leader_silent_{org_id}"),
                InlineKeyboardButton(text="📢 Снять лидера (публично)", callback_data=f"org_fire_leader_public_{org_id}"),
            ]
        )

    keyboard.append([InlineKeyboardButton(text="🚀 Инициатива руководства", callback_data=f"org_initiative_{org_id}")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить панель", callback_data=f"manage_organization_{org_id}")])
    keyboard.append(
        [
            InlineKeyboardButton(text="🔙 К организации", callback_data=f"view_org_{org_id}"),
            InlineKeyboardButton(text="🏛️ К списку", callback_data="orgs_main"),
        ]
    )
    return keyboard


async def _render_leader_panel(callback: CallbackQuery, state: FSMContext, org: dict):
    org_id = int(org.get("id") or 0)
    members = await db.get_organization_members(org_id, limit=250)
    pending_apps = await db.get_organization_applications(org_id, status="pending", limit=300)
    authority = await db.get_government_authority(callback.from_user.id)
    current_leader_id = int(org.get("leader_id") or 0)
    can_fire_leader = current_leader_id > 0 and (
        callback.from_user.id == current_leader_id or authority in {"president", "vice_president"}
    )
    await state.update_data(managed_org_id=org_id)

    text = (
        f"🧭 ПАНЕЛЬ РУКОВОДСТВА: {_safe_text(org.get('name'), 'Организация')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Тип: {_org_kind(org)}\n"
        f"Бюджет: ${float(org.get('budget') or 0):,.2f}\n"
        f"Сотрудников: {len(members)}\n"
        f"Заявок в ожидании: {len(pending_apps)}\n"
        f"Политика: {_safe_text(org.get('policy'), 'neutral')}\n\n"
        "Выберите раздел управления:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=_leader_panel_keyboard(org, can_fire_leader=can_fire_leader))
    await state.set_state(OrganizationStates.managing_org)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


async def _render_org_payout_player_picker(
    callback: CallbackQuery,
    org: dict,
    page: int = 0,
    notice: str = "",
):
    if callback.message is None:
        return
    org_id = int(org.get("id") or 0)
    if org_id <= 0:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    safe_page = max(0, int(page or 0))
    page_size = 8
    total_players = max(0, int(await db.count_players() or 0))
    max_page = max(0, (total_players - 1) // page_size) if total_players > 0 else 0
    if safe_page > max_page:
        safe_page = max_page
    offset = safe_page * page_size
    players = await db.get_players_page(limit=page_size, offset=offset)

    lines = [
        f"💸 ВЫПЛАТА ИЗ БЮДЖЕТА: {_safe_text(org.get('name'), 'Организация')}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Бюджет: {float(org.get('budget') or 0):,.2f} люмов",
        f"Страница: {safe_page + 1}/{max_page + 1}",
        "",
    ]
    if notice:
        lines.append(_safe_text(notice))
        lines.append("")
    lines.append("Выберите игрока для выплаты:")

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not players:
        lines.append("• Список игроков пуст.")
    else:
        for player in players:
            user_id = int(player.get("user_id") or 0)
            if user_id <= 0:
                continue
            display_name = _display_name_from_row(player, fallback_id=user_id)
            short_name = display_name if len(display_name) <= 28 else display_name[:25] + "..."
            lines.append(f"• {display_name} (ID {user_id})")
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"👤 {short_name}",
                        callback_data=f"org_pay_pick_{org_id}_{user_id}_{safe_page}",
                    )
                ]
            )

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"org_pay_start_{org_id}_{safe_page - 1}")
        )
    if safe_page < max_page:
        nav_row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"org_pay_start_{org_id}_{safe_page + 1}")
        )
    if nav_row:
        keyboard_rows.append(nav_row)
    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"org_pay_start_{org_id}_{safe_page}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


# ============================================================================
# ОРГАНИЗАЦИИ - ОСНОВНОЕ МЕНЮ И ПРОСМОТР
# ============================================================================

@router.message(Command("orgs"))
@router.callback_query(F.data == "orgs_main")
async def organizations_menu(event, state: FSMContext):
    """Главное меню организаций"""
    if not isinstance(event, Message):
        await event.answer()
    
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    
    text = (
        "🏛️ ГОСУДАРСТВЕННЫЕ ОРГАНИЗАЦИИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if user.get('organization'):
        text += f"Ваша должность: {_safe_text(user.get('role'), 'Нет')}\n"
        text += f"Зарплата: {float(user.get('salary', 0) or 0):,.2f} люмов/час\n\n"
    
    text += "Выберите организацию для просмотра или присоединения:"
    
    organizations = await db.list_organizations()
    reply_markup = get_organization_list_keyboard(organizations)
    manageable_orgs = await _get_manageable_orgs(user_id)
    if manageable_orgs:
        reply_markup.inline_keyboard.insert(
            0,
            [InlineKeyboardButton(text="🧭 Панель руководства", callback_data="manage_organization")],
        )
    
    await state.set_state(OrganizationStates.org_menu)
    await send_section_screen(
        event,
        text=text,
        reply_markup=reply_markup,
        parse_mode=None,
        section_key="org",
    )


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
    
    text = f"🏛️ {_safe_text(org.get('name'), 'Неизвестно')}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📖 Описание: {_safe_text(org.get('description'), 'Нет')}\n"
    text += f"👥 Членов: {int(org.get('members', 0) or 0)}\n"
    text += f"💰 Бюджет: {float(org.get('budget', 0) or 0):,.2f} люмов\n"
    text += f"⭐ Репутация: {_safe_text(org.get('reputation', 50), '50')}/100\n\n"
    
    if org.get('leader_id'):
        leader = await db.get_user(org.get('leader_id'))
        leader_name = _display_name_from_row(leader or {}, fallback_id=int(org.get('leader_id') or 0))
        text += f"👑 Лидер: {leader_name}\n\n"

    is_member = await db.is_user_org_member(callback.from_user.id, org_id)
    if not is_member:
        user_org_name = _normalized((await db.get_user(callback.from_user.id) or {}).get("organization"))
        is_member = user_org_name == _normalized(org.get("name"))

    keyboard = [
        [InlineKeyboardButton(text="👥 Члены", callback_data=f"org_members_{org_id}")],
        [InlineKeyboardButton(text="💬 Чат организации", callback_data=f"org_chat_{org_id}")],
    ]
    if is_member:
        keyboard.append([InlineKeyboardButton(text="🚪 Покинуть организацию", callback_data=f"leave_org_{org_id}")])
    else:
        keyboard.append([InlineKeyboardButton(text="📝 Подать заявку", callback_data=f"apply_org_{org_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="orgs_main")])

    kind = _org_kind(org)
    service_map: dict[str, tuple[str, str]] = {
        "government": ("👑 Панель правительства", "president_admin_panel"),
        "police": ("🚓 Панель полиции", "police_menu"),
        "fbi": ("🕵️ Панель ФБР", "fbi_menu"),
        "court": ("⚖️ Панель суда", "court_menu"),
        "bank": ("🏦 Панель банка", "bank_menu"),
        "hospital": ("🏥 Панель больницы", "hospital_menu"),
        "education": ("🎓 Панель образования", "edu_menu"),
    }
    service_entry = service_map.get(kind)
    if service_entry:
        keyboard.insert(0, [InlineKeyboardButton(text=service_entry[0], callback_data=service_entry[1])])

    can_manage = await _can_manage_org(callback.from_user.id, org)
    if can_manage:
        keyboard.insert(0, [InlineKeyboardButton(text="🧭 Панель руководства", callback_data=f"manage_organization_{org_id}")])
    
    await state.set_state(OrganizationStates.viewing_org)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("leave_org_"))
async def leave_organization_action(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = (callback.data or "").replace("leave_org_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org_id = int(raw)
    ok, msg, payload = await db.leave_organization(callback.from_user.id, org_id=org_id)
    if ok:
        org_name = str((payload or {}).get("org_name") or "организацию")
        await callback.message.answer(f"✅ {msg}\nВы вышли из: {org_name}", parse_mode=None)
    else:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
    await organizations_menu(callback, state)


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
    text = f"👥 Члены {_safe_text(org.get('name'), 'Организации')}\n━━━━━━━━━━━━━━━━━━━━\n\n"

    if not members:
        text += "Нет членов"
    else:
        for member in members[:15]:
            member_name = _display_name_from_row(member, fallback_id=int(member.get("user_id") or 0))
            member_role = _safe_text(member.get('role'), 'Участник')
            text += f"• {member_name} - {member_role}\n"
        if len(members) > 15:
            text += f"\n... и ещё {len(members) - 15} человек"

    keyboard = [[
        InlineKeyboardButton(text="🔙 Назад", callback_data=OrgCallback(action="view_org", org_id=org_id, org_name="none").pack())
    ]]

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
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
    is_member = await db.is_user_org_member(callback.from_user.id, org_id)
    if not is_member and _normalized(user.get("organization")) != _normalized(org.get("name")):
        await callback.answer("❌ Только члены организации могут писать в чат.", show_alert=True)
        return

    await state.set_state(OrganizationStates.org_chat_message)
    await state.update_data(org_chat_org_id=org_id, org_chat_hidden=True)
    await callback.message.answer(
        "🕶️ Введите скрытое сообщение для чата организации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"org_chat_{org_id}")
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
    is_member = await db.is_user_org_member(callback.from_user.id, org_id)
    if not is_member and _normalized(user.get("organization")) != _normalized(org.get("name")):
        await callback.answer("❌ Только члены организации могут писать в чат.", show_alert=True)
        return

    await state.set_state(OrganizationStates.org_chat_message)
    await state.update_data(org_chat_org_id=org_id, org_chat_hidden=False)
    await callback.message.answer(
        "💬 Введите сообщение для чата организации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"org_chat_{org_id}")
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
    is_member = await db.is_user_org_member(callback.from_user.id, org_id)
    if not is_member:
        is_member = _normalized(user.get("organization")) == _normalized(org.get("name"))
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
            author = _display_name_from_row(msg, fallback_id=int(msg.get("user_id") or 0))
            created = str(msg.get("created_date") or "")[11:16]
            marker = "🕶️ " if int(msg.get("is_hidden") or 0) == 1 else ""
            content = str(msg.get("content") or "")
            if len(content) > 140:
                content = content[:137] + "..."
            text_lines.append(f"[{created}] {marker}{author}: {content}")

    keyboard: list[list[InlineKeyboardButton]] = []
    if is_member:
        keyboard.append([
            InlineKeyboardButton(text="✍️ Написать", callback_data=f"org_chat_send_{org_id}"),
            InlineKeyboardButton(text="🕶️ Подпольно", callback_data=f"org_chat_send_hidden_{org_id}"),
        ])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"org_chat_{org_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=OrgCallback(action="view_org", org_id=org_id, org_name="none").pack())])

    await state.set_state(OrganizationStates.viewing_org)
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.message(OrganizationStates.org_chat_message, F.text, ~F.text.startswith("/"))
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
                InlineKeyboardButton(text="🔙 К чату", callback_data=f"org_chat_{org_id}")
            ]]),
        )
        return

    await state.set_state(OrganizationStates.viewing_org)
    await message.answer(
        "✅ Сообщение отправлено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Открыть чат", callback_data=f"org_chat_{org_id}")
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

    text = f"📝 Применение в {_safe_text(org.get('name'))}\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Напишите сообщение с причиной присоединения (до 500 символов):"

    await state.set_state(OrganizationStates.application_text)
    await state.update_data(org_id=org_id, org_name=org.get('name'))

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_back_button(callback="orgs_main"), parse_mode=None)


@router.message(OrganizationStates.application_text, F.text, ~F.text.startswith("/"))
async def receive_application_text(message: Message, state: FSMContext):
    """Получение текста заявки"""
    data = await state.get_data()
    org_id = data.get('org_id')
    user_id = message.from_user.id
    
    application_text = message.text[:500]
    
    # Записываем заявку в БД
    success, db_message = await db.apply_to_organization(user_id, org_id, application_text)
    if success:
        text = "✅ Статус заявки\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += _safe_text(db_message)
        if "автоматически" not in str(db_message).lower():
            text += "\n\nАдминистраторы организации рассмотрят вашу заявку в ближайшее время."
            text += "\nВы получите уведомление, когда придёт решение."
    else:
        text = f"❌ Заявка не отправлена\n━━━━━━━━━━━━━━━━━━━━\n\n{_safe_text(db_message)}"
    
    await state.set_state(OrganizationStates.org_menu)
    await message.answer(text, reply_markup=get_back_button(callback="orgs_main"), parse_mode=None)


# ============================================================================
# ОРГАНИЗАЦИИ - УПРАВЛЕНИЕ (для лидеров)
# ============================================================================

@router.callback_query(F.data == "manage_organization")
async def manage_organization_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора управляемой организации."""
    await callback.answer()
    manageable = await _get_manageable_orgs(callback.from_user.id)
    if not manageable:
        await callback.answer("❌ У вас нет прав руководства организациями.", show_alert=True)
        return

    if len(manageable) == 1:
        await _render_leader_panel(callback, state, manageable[0])
        return

    lines = [
        "🧭 ПАНЕЛЬ РУКОВОДСТВА",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Выберите организацию для управления:",
        "",
    ]
    keyboard: list[list[InlineKeyboardButton]] = []
    for org in manageable:
        org_id = int(org.get("id") or 0)
        lines.append(f"• #{org_id} {_safe_text(org.get('name'), 'Организация')} ({_org_kind(org)})")
        keyboard.append([InlineKeyboardButton(text=f"Открыть: {_safe_text(org.get('name'), 'Организация')}", callback_data=f"manage_organization_{org_id}")])

    keyboard.append([InlineKeyboardButton(text="🔙 К организациям", callback_data="orgs_main")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)


@router.callback_query(F.data.startswith("manage_organization_"))
async def manage_organization_open(callback: CallbackQuery, state: FSMContext):
    """Открыть панель руководства конкретной организации."""
    await callback.answer()
    raw = (callback.data or "").replace("manage_organization_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректная организация.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на управление этой организацией.", show_alert=True)
        return

    await _render_leader_panel(callback, state, org)


@router.callback_query(F.data.startswith("org_fire_leader_"))
async def org_fire_leader(callback: CallbackQuery, state: FSMContext):
    """Снятие лидера организации (тихо/публично)."""
    await callback.answer()
    raw = str(callback.data or "").replace("org_fire_leader_", "")
    parts = raw.split("_")
    if len(parts) < 2:
        await callback.answer("❌ Некорректные данные.", show_alert=True)
        return

    mode = parts[0].strip().lower()
    org_raw = parts[-1].strip()
    if mode not in {"silent", "public"} or not org_raw.isdigit():
        await callback.answer("❌ Некорректные параметры.", show_alert=True)
        return
    org_id = int(org_raw)

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    ok, msg, payload = await db.dismiss_organization_leader(
        actor_id=callback.from_user.id,
        org_id=org_id,
        mode=mode,
        reason="Снятие через панель руководства",
    )
    await callback.message.answer(("✅ " if ok else "❌ ") + _safe_text(msg), parse_mode=None)

    updated_org = await db.get_organization_by_id(org_id)
    if updated_org and await _can_manage_org(callback.from_user.id, updated_org):
        await _render_leader_panel(callback, state, updated_org)
        return

    await callback.message.edit_text(
        "🧭 Панель руководства недоступна для выбранной организации.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 К организациям", callback_data="orgs_main")]]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "review_applications")
async def review_applications(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран заявок организации."""
    from feature_pack import feature_review_applications
    await feature_review_applications(callback, state)


@router.callback_query(F.data.startswith("review_applications_"))
async def review_applications_for_org(callback: CallbackQuery, state: FSMContext):
    """Прокси на экран заявок с выбранной организацией."""
    await callback.answer()
    raw = (callback.data or "").replace("review_applications_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на управление заявками.", show_alert=True)
        return
    await state.update_data(managed_org_id=org_id)
    from feature_pack import feature_review_applications
    await feature_review_applications(callback, state)


@router.callback_query(F.data.startswith("org_initiative_"))
async def org_initiative(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    raw = (callback.data or "").replace("org_initiative_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректная организация.", show_alert=True)
        return
    org_id = int(raw)
    ok, msg, payload = await db.run_org_initiative(callback.from_user.id, org_id)
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    updated_org = await db.get_organization_by_id(org_id)
    if updated_org and await _can_manage_org(callback.from_user.id, updated_org):
        await _render_leader_panel(callback, state, updated_org)
        return
    if callback.message:
        await callback.message.edit_text(
            ("✅ " if ok else "❌ ") + msg,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 К организациям", callback_data="orgs_main")]]
            ),
            parse_mode=None,
        )


@router.callback_query(F.data == "manage_members")
async def manage_members(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран сотрудников организации."""
    from feature_pack import feature_manage_members
    await feature_manage_members(callback, state)


@router.callback_query(F.data.startswith("manage_members_"))
async def manage_members_for_org(callback: CallbackQuery, state: FSMContext):
    """Прокси на экран сотрудников с выбранной организацией."""
    await callback.answer()
    raw = (callback.data or "").replace("manage_members_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на управление сотрудниками.", show_alert=True)
        return
    await state.update_data(managed_org_id=org_id)
    from feature_pack import feature_manage_members
    await feature_manage_members(callback, state)


@router.callback_query(F.data.startswith("org_pay_start_"))
async def org_pay_start(callback: CallbackQuery, state: FSMContext):
    """Выбор игрока для выплаты из бюджета организации."""
    await callback.answer()
    tail = (callback.data or "").replace("org_pay_start_", "")
    parts = tail.split("_")
    if len(parts) < 1 or not parts[0].isdigit():
        await callback.answer("❌ Некорректный формат запроса.", show_alert=True)
        return
    org_id = int(parts[0])
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на выплаты из бюджета.", show_alert=True)
        return

    await state.update_data(managed_org_id=org_id)
    await _render_org_payout_player_picker(callback, org, page=page)


@router.callback_query(F.data.startswith("org_pay_pick_"))
async def org_pay_pick(callback: CallbackQuery, state: FSMContext):
    """Выбор суммы выплаты для конкретного игрока."""
    await callback.answer()
    tail = (callback.data or "").replace("org_pay_pick_", "")
    parts = tail.split("_")
    if len(parts) < 3 or not all(part.isdigit() for part in parts[:3]):
        await callback.answer("❌ Некорректные параметры выплаты.", show_alert=True)
        return
    org_id = int(parts[0])
    target_user_id = int(parts[1])
    page = int(parts[2])

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на выплаты из бюджета.", show_alert=True)
        return

    target = await db.get_user(target_user_id)
    if not target:
        await callback.answer("❌ Игрок не найден.", show_alert=True)
        return

    budget = round(float(org.get("budget") or 0), 2)
    target_name = _display_name_from_row(target, fallback_id=target_user_id)
    target_balance = round(float(target.get("balance") or 0), 2)
    lines = [
        f"💸 ВЫПЛАТА ИГРОКУ: {_safe_text(org.get('name'), 'Организация')}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Игрок: {target_name} (ID {target_user_id})",
        f"Баланс игрока: {target_balance:,.2f} люмов",
        f"Бюджет организации: {budget:,.2f} люмов",
        "",
        "Выберите сумму выплаты:",
    ]

    preset_amounts = [500, 1000, 2500, 5000, 10_000, 25_000, 50_000, 100_000]
    dynamic = [int(max(1, round(budget * 0.01))), int(max(1, round(budget * 0.05)))]
    candidates = sorted(set(preset_amounts + dynamic))
    amounts = [amt for amt in candidates if 0 < amt <= max(0.0, budget)]
    if not amounts and budget > 0:
        amounts = [int(max(1, round(min(budget, 1000.0))))]

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not amounts:
        lines.append("❌ В бюджете недостаточно средств даже для минимальной выплаты.")
    else:
        row: list[InlineKeyboardButton] = []
        for amount in amounts[:8]:
            row.append(
                InlineKeyboardButton(
                    text=f"{amount:,.0f} лм",
                    callback_data=f"org_pay_do_{org_id}_{target_user_id}_{int(amount)}_{page}",
                )
            )
            if len(row) == 2:
                keyboard_rows.append(row)
                row = []
        if row:
            keyboard_rows.append(row)

    keyboard_rows.append([InlineKeyboardButton(text="👥 Сменить игрока", callback_data=f"org_pay_start_{org_id}_{page}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")])
    if callback.message is not None:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
            parse_mode=None,
        )


@router.callback_query(F.data.startswith("org_pay_do_"))
async def org_pay_do(callback: CallbackQuery, state: FSMContext):
    """Подтвердить и провести выплату из бюджета организации."""
    await callback.answer()
    tail = (callback.data or "").replace("org_pay_do_", "")
    parts = tail.split("_")
    if len(parts) < 4 or not all(part.isdigit() for part in parts[:4]):
        await callback.answer("❌ Некорректные параметры выплаты.", show_alert=True)
        return
    org_id = int(parts[0])
    target_user_id = int(parts[1])
    amount = float(parts[2])
    page = int(parts[3])

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на выплаты из бюджета.", show_alert=True)
        return

    ok, msg, payload = await db.pay_organization_bonus(
        actor_id=callback.from_user.id,
        org_id=org_id,
        target_user_id=target_user_id,
        amount=amount,
        reason=f"Распоряжение руководства ({_safe_text(org.get('name'), 'Организация')})",
    )
    if not ok:
        await callback.answer(msg, show_alert=True)
        await _render_org_payout_player_picker(
            callback,
            org,
            page=page,
            notice=f"❌ {msg}",
        )
        return

    updated_org = await db.get_organization_by_id(org_id) or org
    target = await db.get_user(target_user_id) or {}
    target_name = _display_name_from_row(target, fallback_id=target_user_id)
    notice = (
        f"✅ {msg}\n"
        f"Игрок: {target_name}\n"
        f"Сумма: {float(payload.get('amount') or amount):,.2f} люмов\n"
        f"Новый бюджет: {float(payload.get('budget_after') or updated_org.get('budget') or 0):,.2f} люмов"
    )
    await _render_org_payout_player_picker(callback, updated_org, page=page, notice=notice)


@router.callback_query(F.data == "org_finances")
async def org_finances(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран финансов организации."""
    from feature_pack import feature_org_finances
    await feature_org_finances(callback, state)


@router.callback_query(F.data.startswith("org_finances_"))
async def org_finances_for_org(callback: CallbackQuery, state: FSMContext):
    """Прокси на экран финансов с выбранной организацией."""
    await callback.answer()
    raw = (callback.data or "").replace("org_finances_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на управление финансами.", show_alert=True)
        return
    await state.update_data(managed_org_id=org_id)
    from feature_pack import feature_org_finances
    await feature_org_finances(callback, state)


@router.callback_query(F.data.startswith("org_activity_"))
async def org_activity_dashboard(callback: CallbackQuery, state: FSMContext):
    """Сводка активности организации за последние сутки."""
    await callback.answer()
    raw = (callback.data or "").replace("org_activity_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на просмотр аналитики.", show_alert=True)
        return

    snapshot = await db.get_organization_activity_snapshot(org_id=org_id, hours=24)
    if not snapshot:
        await callback.answer("❌ Не удалось получить аналитику.", show_alert=True)
        return

    lines = [
        f"📊 АКТИВНОСТЬ: {_safe_text(snapshot.get('org_name'), 'Организация')}",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Тип: {_safe_text(snapshot.get('org_type'), 'unknown')}",
        f"Политика: {_safe_text(snapshot.get('policy'), 'neutral')}",
        f"Бюджет: ${float(snapshot.get('budget') or 0):,.2f}",
        "",
        f"Сотрудников: {int(snapshot.get('members') or 0)}",
        f"Фонд зарплат (час): ${float(snapshot.get('payroll_daily') or 0):,.2f}",
        f"Заявок в ожидании: {int(snapshot.get('pending_apps') or 0)}",
        "",
        f"Чат за {int(snapshot.get('hours') or 24)}ч: {int(snapshot.get('chat_messages') or 0)}",
        f"Скрытых сообщений: {int(snapshot.get('hidden_messages') or 0)}",
        f"Событий сотрудников: {int(snapshot.get('activity_events') or 0)}",
        "",
        "Топ по чату:",
    ]
    leaders = snapshot.get("top_chat_members") or []
    if not leaders:
        lines.append("• Нет данных за период.")
    else:
        for row in leaders[:5]:
            lines.append(
                f"• {_safe_text(row.get('member_name'), '#?')}: {int(row.get('messages') or 0)} сообщений"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"org_activity_{org_id}"),
                InlineKeyboardButton(text="📢 Пресс-центр", callback_data=f"org_news_start_{org_id}"),
            ],
            [InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("org_news_start_"))
async def org_news_start(callback: CallbackQuery, state: FSMContext):
    """Запуск черновика новости организации."""
    await callback.answer()
    raw = (callback.data or "").replace("org_news_start_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на публикацию.", show_alert=True)
        return

    await state.update_data(org_news_org_id=org_id, managed_org_id=org_id)
    await state.set_state(OrganizationStates.org_news_draft)
    text = (
        f"📢 ПРЕСС-ЦЕНТР: {_safe_text(org.get('name'), 'Организация')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте текст новости одним сообщением.\n"
        "Формат:\n"
        "1) Первая строка - заголовок.\n"
        "2) Со второй строки - текст новости.\n\n"
        "Если отправите одну строку, она станет текстом, а заголовок будет создан автоматически."
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"manage_organization_{org_id}")],
            ]
        ),
        parse_mode=None,
    )


@router.message(OrganizationStates.org_news_draft, F.text, ~F.text.startswith("/"))
async def org_news_submit(message: Message, state: FSMContext):
    """Публикация новости организации в СМИ."""
    data = await state.get_data()
    org_id = int(data.get("org_news_org_id") or 0)
    if org_id <= 0:
        await state.set_state(OrganizationStates.org_menu)
        await message.answer("❌ Сессия пресс-центра устарела.", reply_markup=get_back_button(callback="orgs_main"), parse_mode=None)
        return

    org = await db.get_organization_by_id(org_id)
    if not org:
        await state.set_state(OrganizationStates.org_menu)
        await message.answer("❌ Организация не найдена.", reply_markup=get_back_button(callback="orgs_main"), parse_mode=None)
        return
    if not await _can_manage_org(message.from_user.id, org):
        await state.set_state(OrganizationStates.org_menu)
        await message.answer("❌ Нет прав на публикацию от этой организации.", reply_markup=get_back_button(callback="orgs_main"), parse_mode=None)
        return

    raw_text = (message.text or "").strip()
    if len(raw_text) < 8:
        await message.answer("❌ Текст слишком короткий. Добавьте больше деталей.")
        return

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) >= 2:
        title = lines[0]
        body = "\n".join(lines[1:])
    else:
        title = f"Официальное сообщение ({_safe_text(org.get('name'), 'Организация')})"
        body = raw_text

    ok, result_msg, news_id = await db.publish_organization_news(
        actor_id=message.from_user.id,
        org_id=org_id,
        title=title,
        body=body,
        severity="hot",
    )

    sent_groups = 0
    failed_groups = 0
    can_group_broadcast = await _can_broadcast_org_news_to_groups(message.from_user.id, org)
    if ok and news_id > 0 and _org_kind(org) == "government" and can_group_broadcast:
        sent_groups, failed_groups = await _broadcast_government_news_to_groups(
            bot=message.bot,
            org=org,
            title=title,
            body=body,
            news_id=news_id,
        )

    await state.update_data(managed_org_id=org_id)
    await state.set_state(OrganizationStates.managing_org)
    text = ("✅ " if ok else "❌ ") + _safe_text(result_msg)
    if ok and news_id > 0:
        text += f"\n\nID новости: {news_id}"
    if ok and _org_kind(org) == "government":
        if can_group_broadcast:
            text += f"\n📡 Рассылка в группы: отправлено {sent_groups}, ошибок {failed_groups}."
        else:
            text += "\n📡 Рассылка в группы не выполнена: доступ есть только у лидера организации или президента."

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📰 Открыть ленту СМИ", callback_data="media_news_menu"),
                    InlineKeyboardButton(text="📊 Аналитика", callback_data=f"org_activity_{org_id}"),
                ],
                [InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")],
            ]
        ),
        parse_mode=None,
    )


@router.message(OrganizationStates.org_news_draft)
async def org_news_invalid(message: Message):
    await message.answer("Отправьте текст новости обычным сообщением.", parse_mode=None)


@router.callback_query(F.data.startswith("org_tax_reports_"))
async def org_tax_reports(callback: CallbackQuery, state: FSMContext):
    """Панель налоговой аналитики по бизнес-отчетам."""
    await callback.answer()
    raw = (callback.data or "").replace("org_tax_reports_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав на просмотр налоговых отчетов.", show_alert=True)
        return

    reports = await db.get_latest_business_tax_reports(limit=18)
    lines = [
        f"🧾 НАЛОГОВЫЕ ОТЧЕТЫ: {_safe_text(org.get('name'), 'Организация')}",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not reports:
        lines.append("Отчеты пока не сформированы.")
    else:
        for row in reports[:12]:
            created = str(row.get("created_at") or "")[:16]
            status = _safe_text(row.get("status"), "unknown")
            business = _safe_text(row.get("business_name"), "Бизнес")
            owner = _safe_text(row.get("owner_name"), f"#{int(row.get('owner_id') or 0)}")
            tax_due = float(row.get("tax_due") or 0)
            tax_paid = float(row.get("tax_paid") or 0)
            lines.append(f"[{created}] {business} | {status}")
            lines.append(f"Владелец: {owner} | Начислено: ${tax_due:,.2f} | Оплачено: ${tax_paid:,.2f}")
            note = _safe_text(row.get("note"), "")
            if note and note != "—":
                lines.append(f"Примечание: {note}")
            lines.append("")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Пересчитать бизнес-отчеты", callback_data=f"org_business_tax_cycle_{org_id}"),
                InlineKeyboardButton(text="⚙️ Налоговый цикл", callback_data=f"org_tax_cycle_{org_id}"),
            ],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"org_tax_reports_{org_id}")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("org_business_tax_cycle_"))
async def org_business_tax_cycle(callback: CallbackQuery, state: FSMContext):
    """Ручной запуск бизнес-налоговых отчетов (для руководства налоговой/гос-органов)."""
    await callback.answer()
    raw = (callback.data or "").replace("org_business_tax_cycle_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    kind = _org_kind(org)
    if kind not in {"tax", "government"}:
        await callback.answer("❌ Доступно только налоговой и правительству.", show_alert=True)
        return

    ok, remain = await db.check_and_set_user_cooldown(callback.from_user.id, f"manual_business_tax_cycle_{org_id}", 10)
    if not ok:
        await callback.answer(f"⏳ Подождите {remain} мин.", show_alert=True)
        return

    result = await db.generate_business_tax_reports()
    text = (
        "✅ Бизнес-налоговые отчеты пересчитаны.\n\n"
        f"Цикл: {_safe_text(result.get('cycle_date'))}\n"
        f"Создано отчетов: {int(result.get('reports_created') or 0)}\n"
        f"Оплачено налогов: ${float(result.get('total_tax_paid') or 0):,.2f}\n"
        f"Просрочек: {int(result.get('unpaid_count') or 0)}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧾 К отчетам", callback_data=f"org_tax_reports_{org_id}")],
                [InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("org_tax_cycle_"))
async def org_tax_cycle(callback: CallbackQuery, state: FSMContext):
    """Ручной запуск расширенного налогового цикла."""
    await callback.answer()
    raw = (callback.data or "").replace("org_tax_cycle_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return
    org_id = int(raw)
    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return
    if not await _can_manage_org(callback.from_user.id, org):
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    kind = _org_kind(org)
    if kind not in {"tax", "government"}:
        await callback.answer("❌ Доступно только налоговой и правительству.", show_alert=True)
        return

    ok, remain = await db.check_and_set_user_cooldown(callback.from_user.id, f"manual_tax_cycle_{org_id}", 20)
    if not ok:
        await callback.answer(f"⏳ Подождите {remain} мин.", show_alert=True)
        return

    result = await db.run_advanced_tax_cycle()
    text = (
        "✅ Расширенный налоговый цикл выполнен.\n\n"
        f"Дата цикла: {_safe_text(result.get('cycle_date'))}\n"
        f"Обработано пользователей: {int(result.get('processed_users') or 0)}\n"
        f"Должников: {int(result.get('debtors') or 0)}\n"
        f"Собрано: ${float(result.get('total_collected') or 0):,.2f}\n"
        f"Новый долг: ${float(result.get('total_new_debt') or 0):,.2f}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧾 К отчетам", callback_data=f"org_tax_reports_{org_id}")],
                [InlineKeyboardButton(text="🔙 В панель", callback_data=f"manage_organization_{org_id}")],
            ]
        ),
        parse_mode=None,
    )


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
    """Прокси на расширенное меню работы."""
    from feature_pack import feature_work_menu
    await feature_work_menu(event, state)


@router.callback_query(F.data == "view_citizen_jobs")
async def view_citizen_jobs(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий список вакансий."""
    from feature_pack import feature_view_citizen_jobs
    await feature_view_citizen_jobs(callback, state)


@router.callback_query(F.data == "citizen_work_status")
async def citizen_work_status(callback: CallbackQuery, state: FSMContext):
    """Прокси на расширенный статус работы."""
    from feature_pack import feature_citizen_work_status
    await feature_citizen_work_status(callback, state)


# ============================================================================
# ОБРАЗОВАНИЕ
# ============================================================================

@router.message(Command("edu"))
@router.callback_query(F.data == "edu_menu")
async def education_menu(event, state: FSMContext):
    """Прокси на расширенное меню образования."""
    from feature_pack import feature_education_menu
    await feature_education_menu(event, state)


@router.callback_query(F.data == "view_education_programs")
async def view_education_programs(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий список программ."""
    from feature_pack import feature_view_programs
    await feature_view_programs(callback, state)


@router.callback_query(F.data == "education_progress")
async def education_progress(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий экран прогресса."""
    from feature_pack import feature_education_progress
    await feature_education_progress(callback, state)


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
        [InlineKeyboardButton(text="🔍 Каталог", callback_data="property_catalog")],
        [InlineKeyboardButton(text="🏠 Мое имущество", callback_data="my_property")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


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
        [InlineKeyboardButton(text="📋 Контракты", callback_data="view_contracts")],
        [InlineKeyboardButton(text="✍️ Создать", callback_data="create_contract")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ]
    
    await state.set_state(OrganizationStates.org_menu)
    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)) if isinstance(event, CallbackQuery) else await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


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

