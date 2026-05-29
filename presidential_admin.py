"""
presidential_admin.py - Админ-панель президента и расширенные финансовые полномочия
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db

logger = logging.getLogger(__name__)
router = Router()
INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")


class PresidentStates(StatesGroup):
    admin_panel = State()
    appointing_position = State()
    transfer_amount = State()
    transfer_reason = State()
    nation_broadcast_text = State()
    org_fund_amount = State()
    org_fund_reason = State()
    money_print_amount = State()
    money_destroy_amount = State()


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


GOVERNMENT_PROFILES: dict[str, dict[str, object]] = {
    "democracy": {
        "label": "Демократия",
        "summary": "Сильная отчетность и самостоятельность госорганов.",
        "org_model": "Независимые ведомства + публичный контроль расходов.",
        "delta": {"stability": 4, "corruption": -8, "satisfaction": 10},
    },
    "monarchy": {
        "label": "Монархия",
        "summary": "Единая вертикаль и высокий контроль дисциплины.",
        "org_model": "Жесткая иерархия, ключевые решения через правительство.",
        "delta": {"stability": 10, "corruption": 3, "satisfaction": -2},
    },
    "dictatorship": {
        "label": "Диктатура",
        "summary": "Максимальная централизация, быстрые силовые решения.",
        "org_model": "Силовые структуры приоритетны, контроль над бизнесом выше.",
        "delta": {"stability": 7, "corruption": 9, "satisfaction": -11},
    },
}


def _clamp_stat(value: float, min_value: int = 0, max_value: int = 100) -> int:
    return max(min_value, min(max_value, int(round(value))))


def _delta_text(delta: int) -> str:
    return f"+{delta}" if delta >= 0 else str(delta)


def _org_health_emoji(org: dict | None) -> str:
    info = org or {}
    score = 0
    if int(info.get("leader_id") or 0) > 0:
        score += 1
    if int(info.get("members") or 0) >= 2:
        score += 1
    if float(info.get("budget") or 0) > 0:
        score += 1
    if score == 3:
        return "🟢"
    if score == 2:
        return "🟡"
    return "🔴"


async def _collect_player_ids() -> list[int]:
    total = await db.count_players()
    if total <= 0:
        return []
    page_size = 50
    seen: set[int] = set()
    for offset in range(0, total, page_size):
        players = await db.get_players_page(limit=page_size, offset=offset)
        for player in players:
            player_id = int(player.get("user_id") or 0)
            if player_id > 0:
                seen.add(player_id)
    return sorted(seen)


def _player_display(player: dict) -> str:
    nickname = str(player.get("nickname") or "")
    full_name = str(player.get("full_name") or "")
    username = str(player.get("username") or "")
    for token in INVISIBLE_NAME_CHARS:
        nickname = nickname.replace(token, "")
        full_name = full_name.replace(token, "")
        username = username.replace(token, "")
    nickname = " ".join(nickname.split()).strip()
    full_name = " ".join(full_name.split()).strip()
    username = " ".join(username.split()).strip().lstrip("@")
    user_id = int(player.get("user_id") or 0)
    display = nickname or full_name or (f"@{username}" if username else f"ID {user_id}")
    if len(display) > 32:
        return display[:29] + "..."
    return display


async def _get_authority(user_id: int) -> str | None:
    return await db.get_government_authority(user_id)


def _org_role_templates(org: dict | None) -> list[tuple[str, str]]:
    info = org or {}
    org_type = str(info.get("type") or "").strip().lower()
    name = str(info.get("name") or "").strip().lower()

    templates: dict[str, list[tuple[str, str]]] = {
        "government": [
            ("👑 Президент", "president"),
            ("🛡️ Вице-президент", "vicepresident"),
            ("🧾 Министр", "minister"),
            ("💰 Министр финансов", "financeminister"),
            ("📢 Пресс-секретарь", "presssecretary"),
            ("👤 Сотрудник", "member"),
        ],
        "police": [
            ("👮 Начальник полиции", "policechief"),
            ("🛡️ Зам. начальника", "deputy"),
            ("🔎 Следователь", "investigator"),
            ("🚔 Оперуполномоченный", "operative"),
            ("👤 Сотрудник", "member"),
        ],
        "fbi": [
            ("🕵️ Директор ФБР", "fbidirector"),
            ("🛡️ Зам. директора", "deputy"),
            ("📡 Аналитик", "analyst"),
            ("💻 Киберагент", "cyberagent"),
            ("🕵️ Агент", "agent"),
        ],
        "hospital": [
            ("🏥 Главврач", "chiefdoctor"),
            ("🩺 Зам. главврача", "deputy"),
            ("🔬 Хирург", "surgeon"),
            ("🧪 Терапевт", "therapist"),
            ("👤 Медперсонал", "member"),
        ],
        "court": [
            ("⚖️ Председатель суда", "chiefjudge"),
            ("🧑‍⚖️ Зам. председателя", "deputy"),
            ("⚖️ Судья", "judge"),
            ("📚 Секретарь суда", "courtclerk"),
            ("👤 Сотрудник", "member"),
        ],
        "bank": [
            ("🏦 Председатель банка", "bankchairman"),
            ("🧮 Зам. председателя", "deputy"),
            ("📊 Риск-менеджер", "riskmanager"),
            ("📑 Аудитор", "auditor"),
            ("👤 Сотрудник", "member"),
        ],
        "education": [
            ("🎓 Ректор", "rector"),
            ("📘 Проректор", "deputy"),
            ("👨‍🏫 Профессор", "professor"),
            ("🧠 Преподаватель", "teacher"),
            ("👤 Сотрудник", "member"),
        ],
        "tax": [
            ("🧾 Глава налоговой", "taxchief"),
            ("🧮 Зам. главы", "deputy"),
            ("📑 Налоговый аудитор", "taxauditor"),
            ("🔍 Инспектор", "taxinspector"),
            ("👤 Сотрудник", "member"),
        ],
    }

    if org_type in templates:
        return templates[org_type]
    if "правитель" in name:
        return templates["government"]
    if "полиц" in name:
        return templates["police"]
    if "фбр" in name:
        return templates["fbi"]
    if "больниц" in name:
        return templates["hospital"]
    if "суд" in name:
        return templates["court"]
    if "банк" in name:
        return templates["bank"]
    if "универс" in name or "образов" in name:
        return templates["education"]
    if "налог" in name:
        return templates["tax"]
    return [("👑 Лидер", "leader"), ("🛡️ Заместитель", "deputy"), ("👤 Сотрудник", "member")]


def _org_role_name_by_code(org: dict | None, role_code: str) -> str:
    code = str(role_code or "").strip().lower()
    for title, candidate_code in _org_role_templates(org):
        if candidate_code == code:
            # удаляем emoji из названия роли
            return " ".join(str(title).split()[1:]) if len(str(title).split()) > 1 else str(title)
    return "Сотрудник"


async def _render_admin_panel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    authority = await _get_authority(user_id)
    if authority is None:
        await callback.answer("❌ Доступ только для руководства государства.", show_alert=True)
        return

    gov = _normalize_government(await db.get_government_system())
    gov_code = str(gov.get("government_type", "democracy")).lower()
    gov_type = _gov_type_label(gov_code)
    gov_profile = GOVERNMENT_PROFILES.get(gov_code, GOVERNMENT_PROFILES["democracy"])
    has_full_admin = authority == "president"

    text_lines = [
        "👑 АДМИН-ПАНЕЛЬ ГОСУДАРСТВА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Доступ: {_authority_label(authority)}",
        f"Форма правления: {gov_type}",
        f"Доктрина: {gov_profile.get('org_model')}",
        f"Стабильность: {gov.get('stability', 50)}/100",
        f"Коррупция: {gov.get('corruption', 0)}/100",
        f"Удовлетворение населения: {gov.get('satisfaction', 60)}/100",
        "",
        "Управляйте назначениями и финансами государства.",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []
    if has_full_admin:
        keyboard.append([InlineKeyboardButton(text="👤 Назначение должностей", callback_data="pres_appoint")])
        keyboard.append([InlineKeyboardButton(text="🏛️ Форма правления", callback_data="pres_change_government")])
        keyboard.append([
            InlineKeyboardButton(text="📜 Законы", callback_data="pres_laws"),
            InlineKeyboardButton(text="🏳️ Флаг", callback_data="pres_flag_menu"),
        ])
        keyboard.append([InlineKeyboardButton(text="🎟️ Промокоды", callback_data="pres_promo_menu")])
        keyboard.append([
            InlineKeyboardButton(text="🏢 Обзор организаций", callback_data="pres_org_overview"),
            InlineKeyboardButton(text="📣 Обращение к нации", callback_data="pres_broadcast_start"),
        ])
        keyboard.append([InlineKeyboardButton(text="🧾 Налог. каникулы", callback_data="pres_tax_holiday_menu")])
        keyboard.append([
            InlineKeyboardButton(text="🏛️ Пополнить организацию", callback_data="pres_org_fund_start"),
            InlineKeyboardButton(text="🖨️ Печать денег", callback_data="pres_money_print_menu"),
        ])
        keyboard.append([
            InlineKeyboardButton(text="📊 Экономика", callback_data="pres_economy_stats"),
            InlineKeyboardButton(text="🔥 Удалить деньги", callback_data="pres_destroy_money_menu"),
        ])

    keyboard.append([InlineKeyboardButton(text="💸 Гос. перевод", callback_data="pres_transfer_start")])
    keyboard.append([
        InlineKeyboardButton(text="📜 Логи переводов", callback_data="pres_transfer_logs"),
        InlineKeyboardButton(text="🕶️ Коррупция", callback_data="pres_corruption_logs"),
    ])
    keyboard.append([InlineKeyboardButton(text="🆘 Помощь", callback_data="pres_help")])
    keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])

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


async def _render_org_overview(callback: CallbackQuery, page: int = 0):
    organizations = await db.list_organizations()
    organizations = [org for org in organizations if int(org.get("id") or 0) > 0]
    total = len(organizations)
    page_size = 6
    max_page = (total - 1) // page_size if total > 0 else 0
    page = max(0, min(page, max_page))
    chunk = organizations[page * page_size:(page + 1) * page_size]

    gov = _normalize_government(await db.get_government_system())
    gov_code = str(gov.get("government_type") or "democracy").lower()
    gov_profile = GOVERNMENT_PROFILES.get(gov_code, GOVERNMENT_PROFILES["democracy"])

    text_lines = [
        "🏢 ОРГАНИЗАЦИОННЫЙ ШТАБ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Форма правления: {_gov_type_label(gov_code)}",
        f"Модель управления: {gov_profile.get('org_model')}",
        f"Страница: {page + 1}/{max_page + 1}",
        "",
        "Легенда: 🟢 стабильно | 🟡 требует внимания | 🔴 критично",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []
    if not chunk:
        text_lines.append("")
        text_lines.append("Организации пока не зарегистрированы.")
    else:
        for short_org in chunk:
            org_id = int(short_org.get("id") or 0)
            org = await db.get_organization_by_id(org_id) or short_org
            status = _org_health_emoji(org)
            members_count = int(org.get("members") or 0)
            pending = len(await db.get_organization_applications(org_id, status="pending", limit=200))
            org_name = str(org.get("name") or org_id)
            text_lines.append(f"{status} {org_name}: {members_count} сотрудников, заявок {pending}")
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status} {org_name}",
                    callback_data=f"pres_org_detail_{org_id}_{page}",
                )
            ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"pres_org_overview_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"pres_org_overview_{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")])

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_org_overview")
async def pres_org_overview(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Только президент может управлять орг. штабом.", show_alert=True)
        return
    await _render_org_overview(callback, page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_org_overview_"))
async def pres_org_overview_page(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Только президент может управлять орг. штабом.", show_alert=True)
        return
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return
    try:
        page = int(parts[3])
    except ValueError:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return
    await _render_org_overview(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_org_detail_"))
async def pres_org_detail(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Только президент может открывать орг. карточки.", show_alert=True)
        return
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Некорректная карточка организации.", show_alert=True)
        return
    try:
        org_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer("❌ Некорректная карточка организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    leader_id = int(org.get("leader_id") or 0)
    deputy_id = int(org.get("deputy_id") or 0)
    leader = await db.get_user(leader_id) if leader_id > 0 else None
    deputy = await db.get_user(deputy_id) if deputy_id > 0 else None
    members = await db.get_organization_members(org_id, limit=400)
    pending_apps = await db.get_organization_applications(org_id, status="pending", limit=400)

    issues: list[str] = []
    if leader_id <= 0:
        issues.append("нет лидера")
    if deputy_id <= 0:
        issues.append("нет заместителя")
    if len(members) == 0:
        issues.append("нет активного состава")
    if float(org.get("budget") or 0) < 0:
        issues.append("дефицитный бюджет")
    if not issues:
        issues.append("критичных рисков не найдено")

    text = (
        "🏢 КАРТОЧКА ОРГАНИЗАЦИИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Название: {org.get('name')}\n"
        f"Тип: {org.get('type')}\n"
        f"Статус: {_org_health_emoji(org)}\n"
        f"Лидер: {_player_display(leader or {'user_id': leader_id}) if leader_id > 0 else 'не назначен'}\n"
        f"Заместитель: {_player_display(deputy or {'user_id': deputy_id}) if deputy_id > 0 else 'не назначен'}\n"
        f"Сотрудников: {len(members)}\n"
        f"Заявок ожидает: {len(pending_apps)}\n"
        f"Бюджет: ${float(org.get('budget') or 0):,.2f}\n"
        f"Репутация: {int(org.get('reputation') or 50)}/100\n"
        f"Риски: {', '.join(issues)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Назначить кадры", callback_data=f"pres_appoint_org_{org_id}_0")],
        [InlineKeyboardButton(text="🏛️ Открыть организацию", callback_data=f"view_org_{org_id}")],
        [InlineKeyboardButton(text="🔙 К обзору", callback_data=f"pres_org_overview_{page}")],
        [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "pres_broadcast_start")
async def pres_broadcast_start(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Рассылка всем игрокам доступна только президенту.", show_alert=True)
        return
    await state.set_state(PresidentStates.nation_broadcast_text)
    await callback.message.edit_text(
        "📣 Обращение ко всем игрокам Мирнастана\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Отправьте текст обращения одним сообщением.\n"
        "Сообщение уйдет всем зарегистрированным игрокам бота.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


@router.message(PresidentStates.nation_broadcast_text, F.text, ~F.text.startswith("/"))
async def pres_broadcast_text_input(message: Message, state: FSMContext):
    authority = await _get_authority(message.from_user.id)
    if authority != "president":
        await state.clear()
        await message.answer("❌ Рассылка всем игрокам доступна только президенту.", parse_mode=None)
        return

    text_raw = " ".join(str(message.text or "").split()).strip()
    if len(text_raw) < 8:
        await message.answer("❌ Сообщение слишком короткое (минимум 8 символов).", parse_mode=None)
        return
    if len(text_raw) > 1800:
        await message.answer("❌ Сообщение слишком длинное (максимум 1800 символов).", parse_mode=None)
        return

    recipients = await _collect_player_ids()
    if not recipients:
        await state.set_state(PresidentStates.admin_panel)
        await message.answer(
            "❌ Не найдено получателей в базе.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
            ]),
            parse_mode=None,
        )
        return

    actor = await db.get_user(message.from_user.id) or {}
    actor_name = _player_display(actor)
    payload = (
        "📣 ОБРАЩЕНИЕ ПРЕЗИДЕНТА МИРНАСТАНА САМСА\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Президент: {actor_name}\n"
        f"Дата: САМСА {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"{text_raw}"
    )

    sent = 0
    failed = 0
    failed_ids: list[str] = []
    for idx, recipient_id in enumerate(recipients, start=1):
        try:
            await message.bot.send_message(recipient_id, payload, parse_mode=None)
            sent += 1
        except Exception as exc:
            failed += 1
            if len(failed_ids) < 8:
                failed_ids.append(str(recipient_id))
            logger.debug("Ошибка рассылки игроку %s: %s", recipient_id, exc)
        if idx % 20 == 0:
            await asyncio.sleep(0.05)

    await state.set_state(PresidentStates.admin_panel)
    summary_lines = [
        "✅ Президентская рассылка завершена",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Отправлено: {sent}",
        f"Ошибок: {failed}",
    ]
    if failed_ids:
        summary_lines.append(f"Недоступные ID (пример): {', '.join(failed_ids)}")

    await message.answer(
        "\n".join(summary_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )


@router.message(PresidentStates.nation_broadcast_text)
async def pres_broadcast_invalid(message: Message):
    await message.answer(
        "❌ Отправьте текст обращения обычным сообщением.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )


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
        keyboard.append([InlineKeyboardButton(text=str(org.get("name") or org_id), callback_data=f"pres_appoint_org_{org_id}_0")])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="president_admin_panel")])

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

    page_size = 12
    total = await db.count_players()
    max_page = (total - 1) // page_size if total > 0 else 0
    page = max(0, min(page, max_page))
    offset = page * page_size
    players = await db.get_players_page(limit=page_size, offset=offset)

    text_lines = [
        "👤 НАЗНАЧЕНИЕ СОТРУДНИКА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Организация: {org.get('name')}",
        f"Всего игроков: {total}",
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
                text=f"👤 {_player_display(player)}",
                callback_data=f"pres_set_position_{org_id}_{player_id}_{page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"pres_appoint_org_{org_id}_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"pres_appoint_org_{org_id}_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(text="🔙 К организациям", callback_data="pres_appoint")])

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

    role_buttons = _org_role_templates(org)

    keyboard = [[
        InlineKeyboardButton(
            text=title,
            callback_data=f"pres_confirm_position_{org_id}_{player_id}_{role_code}_{page}",
        )
    ] for title, role_code in role_buttons]
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"pres_appoint_org_{org_id}_{page}")])

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

    org = await db.get_organization_by_id(org_id) or {}
    role_name = _org_role_name_by_code(org, role_code)

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
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"pres_appoint_org_{org_id}_{page}")]
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
        [InlineKeyboardButton(text="👥 Продолжить назначения", callback_data=f"pres_appoint_org_{org_id}_{page}")],
        [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
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
    current_code = str(gov.get("government_type", "democracy")).lower()
    current = _gov_type_label(current_code)

    text = (
        "🏛️ Смена формы правления\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Текущая форма: {current}\n\n"
        "Выберите новую форму:\n\n"
        f"🗳️ Демократия: {GOVERNMENT_PROFILES['democracy']['summary']}\n"
        f"Эффект: стабильность {_delta_text(int(GOVERNMENT_PROFILES['democracy']['delta']['stability']))}, "
        f"коррупция {_delta_text(int(GOVERNMENT_PROFILES['democracy']['delta']['corruption']))}, "
        f"удовлетворение {_delta_text(int(GOVERNMENT_PROFILES['democracy']['delta']['satisfaction']))}\n\n"
        f"👑 Монархия: {GOVERNMENT_PROFILES['monarchy']['summary']}\n"
        f"Эффект: стабильность {_delta_text(int(GOVERNMENT_PROFILES['monarchy']['delta']['stability']))}, "
        f"коррупция {_delta_text(int(GOVERNMENT_PROFILES['monarchy']['delta']['corruption']))}, "
        f"удовлетворение {_delta_text(int(GOVERNMENT_PROFILES['monarchy']['delta']['satisfaction']))}\n\n"
        f"⚡ Диктатура: {GOVERNMENT_PROFILES['dictatorship']['summary']}\n"
        f"Эффект: стабильность {_delta_text(int(GOVERNMENT_PROFILES['dictatorship']['delta']['stability']))}, "
        f"коррупция {_delta_text(int(GOVERNMENT_PROFILES['dictatorship']['delta']['corruption']))}, "
        f"удовлетворение {_delta_text(int(GOVERNMENT_PROFILES['dictatorship']['delta']['satisfaction']))}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳️ Демократия", callback_data="pres_gov_democracy")],
        [InlineKeyboardButton(text="👑 Монархия", callback_data="pres_gov_monarchy")],
        [InlineKeyboardButton(text="⚡ Диктатура", callback_data="pres_gov_dictatorship")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="president_admin_panel")],
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

    gov_now = _normalize_government(await db.get_government_system())
    old_code = str(gov_now.get("government_type") or "democracy").lower()
    if gov_code == old_code:
        await callback.answer("ℹ️ Эта форма правления уже активна.", show_alert=True)
        return

    profile = GOVERNMENT_PROFILES.get(gov_code, GOVERNMENT_PROFILES["democracy"])
    delta = profile.get("delta", {})
    new_stability = _clamp_stat(gov_now.get("stability", 50) + int(delta.get("stability", 0)))
    new_corruption = _clamp_stat(gov_now.get("corruption", 0) + int(delta.get("corruption", 0)))
    new_satisfaction = _clamp_stat(gov_now.get("satisfaction", 60) + int(delta.get("satisfaction", 0)))

    await db.update_government_system(
        current_type=gov_code,
        stability=new_stability,
        corruption=new_corruption,
        public_satisfaction=new_satisfaction,
        last_changed=datetime.now().isoformat(),
    )
    await db.log_player_activity(
        user_id=callback.from_user.id,
        activity_type="government_reform",
        details=f"Президент изменил форму правления на {_gov_type_label(gov_code)}.",
        value=25_000,
    )

    text = (
        "✅ Форма правления обновлена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Было: {_gov_type_label(old_code)}\n"
        f"Стало: {_gov_type_label(gov_code)}\n"
        f"Доктрина: {profile.get('org_model')}\n\n"
        f"Стабильность: {gov_now.get('stability', 50)} → {new_stability}\n"
        f"Коррупция: {gov_now.get('corruption', 0)} → {new_corruption}\n"
        f"Удовлетворение: {gov_now.get('satisfaction', 60)} → {new_satisfaction}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
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
        [InlineKeyboardButton(text="👥 Выдать игроку", callback_data="pres_transfer_mode_public")],
        [InlineKeyboardButton(text="🕶️ Подпольная схема", callback_data="pres_transfer_mode_shadow")],
        [InlineKeyboardButton(text="💼 Взять себе", callback_data="pres_transfer_mode_self")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="president_admin_panel")],
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
                text=f"👤 {_player_display(player)}",
                callback_data=f"pres_transfer_select_{mode}_{player_id}_{page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"pres_transfer_page_{mode}_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"pres_transfer_page_{mode}_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="pres_transfer_start")])

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
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="pres_transfer_start")]
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
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="pres_transfer_start")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


@router.message(PresidentStates.transfer_amount, F.text, ~F.text.startswith("/"))
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


@router.message(PresidentStates.transfer_reason, F.text, ~F.text.startswith("/"))
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
                [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
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
            [InlineKeyboardButton(text="💸 Новый перевод", callback_data="pres_transfer_start")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
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
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
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
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )
    await callback.answer()


async def _render_org_funding_picker(callback: CallbackQuery, page: int = 0):
    organizations = await db.list_organizations()
    gov_org = await db.get_government_organization()
    gov_org_id = int((gov_org or {}).get("id") or 0)
    gov_budget = round(float((gov_org or {}).get("budget") or 0), 2)

    targets = []
    for item in organizations:
        org_id = int(item.get("id") or 0)
        if org_id <= 0:
            continue
        if org_id == gov_org_id:
            continue
        targets.append(item)

    page_size = 8
    total = len(targets)
    max_page = (total - 1) // page_size if total > 0 else 0
    page = max(0, min(page, max_page))
    chunk = targets[page * page_size:(page + 1) * page_size]

    lines = [
        "🏛️ ПОПОЛНЕНИЕ ОРГАНИЗАЦИЙ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Госбюджет: ${gov_budget:,.2f}",
        f"Страница: {page + 1}/{max_page + 1}",
        "",
        "Выберите организацию для пополнения:",
    ]
    keyboard: list[list[InlineKeyboardButton]] = []
    if not chunk:
        lines.append("Нет доступных организаций.")
    else:
        for item in chunk:
            org_id = int(item.get("id") or 0)
            org = await db.get_organization_by_id(org_id) or item
            org_name = str(org.get("name") or f"Орг #{org_id}")
            org_budget = round(float(org.get("budget") or 0), 2)
            lines.append(f"• {org_name}: ${org_budget:,.2f}")
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🏢 {org_name}",
                    callback_data=f"pres_org_fund_pick_{org_id}_{page}",
                )
            ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"pres_org_fund_page_{page - 1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"pres_org_fund_page_{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_org_fund_start")
async def pres_org_fund_start(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Пополнение организаций доступно только президенту.", show_alert=True)
        return
    await _render_org_funding_picker(callback, page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_org_fund_page_"))
async def pres_org_fund_page(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Пополнение организаций доступно только президенту.", show_alert=True)
        return
    try:
        page = int((callback.data or "").replace("pres_org_fund_page_", ""))
    except ValueError:
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return
    await _render_org_funding_picker(callback, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("pres_org_fund_pick_"))
async def pres_org_fund_pick(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Пополнение организаций доступно только президенту.", show_alert=True)
        return

    parts = (callback.data or "").split("_")
    if len(parts) < 6:
        await callback.answer("❌ Некорректный выбор организации.", show_alert=True)
        return
    try:
        org_id = int(parts[4])
        page = int(parts[5])
    except ValueError:
        await callback.answer("❌ Некорректный ID организации.", show_alert=True)
        return

    org = await db.get_organization_by_id(org_id)
    if not org:
        await callback.answer("❌ Организация не найдена.", show_alert=True)
        return

    await state.update_data(org_fund_target_id=org_id, org_fund_page=page)
    await state.set_state(PresidentStates.org_fund_amount)
    await callback.message.answer(
        f"💵 Введите сумму пополнения для '{org.get('name')}' (числом):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="pres_org_fund_start")]]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.message(PresidentStates.org_fund_amount, F.text, ~F.text.startswith("/"))
async def pres_org_fund_amount_input(message: Message, state: FSMContext):
    authority = await _get_authority(message.from_user.id)
    if authority != "president":
        await state.clear()
        await message.answer("❌ Сессия истекла: действие доступно только президенту.", parse_mode=None)
        return

    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("❌ Введите сумму числом, например: 250000")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return
    if amount > 10_000_000_000:
        await message.answer("❌ Слишком большая сумма.")
        return

    await state.update_data(org_fund_amount=amount)
    await state.set_state(PresidentStates.org_fund_reason)
    await message.answer("📝 Укажите причину пополнения:", parse_mode=None)


@router.message(PresidentStates.org_fund_reason, F.text, ~F.text.startswith("/"))
async def pres_org_fund_reason_input(message: Message, state: FSMContext):
    authority = await _get_authority(message.from_user.id)
    if authority != "president":
        await state.clear()
        await message.answer("❌ Сессия истекла: действие доступно только президенту.", parse_mode=None)
        return

    data = await state.get_data()
    org_id = int(data.get("org_fund_target_id") or 0)
    amount = float(data.get("org_fund_amount") or 0)
    reason = (message.text or "").strip()
    await state.clear()

    if org_id <= 0 or amount <= 0:
        await message.answer("❌ Сессия пополнения устарела.", parse_mode=None)
        return

    ok, msg, details = await db.transfer_state_budget_to_organization(
        actor_id=message.from_user.id,
        target_org_id=org_id,
        amount=amount,
        reason=reason,
    )
    if not ok:
        await message.answer(
            f"❌ {msg}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]]
            ),
            parse_mode=None,
        )
        return

    text = (
        "✅ Пополнение выполнено\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Организация: {details.get('target_org_name')}\n"
        f"Сумма: ${float(details.get('amount') or 0):,.2f}\n"
        f"Бюджет организации: ${float(details.get('target_budget_after') or 0):,.2f}\n"
        f"Госбюджет после операции: ${float(details.get('government_budget_after') or 0):,.2f}\n"
        f"ID операции: {details.get('transfer_id')}"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏛️ Новое пополнение", callback_data="pres_org_fund_start")],
                [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
            ]
        ),
        parse_mode=None,
    )


async def _render_money_print_menu(callback: CallbackQuery, flash: str = ""):
    authority = await _get_authority(callback.from_user.id)
    if authority not in {"president", "finance_minister"}:
        await callback.answer("❌ Раздел доступен президенту и министру финансов.", show_alert=True)
        return False

    claim = await db.claim_ready_state_money_print_jobs(
        actor_id=callback.from_user.id,
        enforce_authority=True,
    )
    gov_org = await db.get_government_organization() or {}
    gov_budget = round(float(gov_org.get("budget") or 0), 2)
    jobs = await db.get_recent_state_money_print_jobs(limit=8)

    lines = [
        "🖨️ ГОСУДАРСТВЕННАЯ ПЕЧАТЬ ДЕНЕГ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Текущий госбюджет: ${gov_budget:,.2f}",
        "",
    ]
    if flash:
        lines.append(flash)
        lines.append("")

    claimed_jobs = int(claim.get("claimed_jobs") or 0)
    minted_total = round(float(claim.get("minted_total") or 0), 2)
    if claimed_jobs > 0:
        lines.append(f"✅ Завершено запусков: {claimed_jobs}, зачислено: ${minted_total:,.2f}")
        lines.append("")

    active_jobs = [row for row in jobs if str(row.get("status") or "").lower() == "printing"]
    lines.append(f"Активных запусков: {len(active_jobs)}")
    lines.append("")
    lines.append("Последние операции:")
    if not jobs:
        lines.append("• Операций пока нет.")
    else:
        for row in jobs[:6]:
            status = str(row.get("status") or "printing")
            marker = "🟡" if status == "printing" else "✅"
            amount = round(float(row.get("amount") or 0), 2)
            cost = round(float(row.get("production_cost") or 0), 2)
            ready_at = str(row.get("ready_at") or "")[:16]
            lines.append(f"{marker} ${amount:,.0f} | себест. ${cost:,.0f} | готово: {ready_at}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ 50k", callback_data="pres_money_print_quick_50000"),
                InlineKeyboardButton(text="⚡ 200k", callback_data="pres_money_print_quick_200000"),
            ],
            [
                InlineKeyboardButton(text="⚡ 1M", callback_data="pres_money_print_quick_1000000"),
                InlineKeyboardButton(text="⚡ 5M", callback_data="pres_money_print_quick_5000000"),
            ],
            [InlineKeyboardButton(text="📝 Своя сумма", callback_data="pres_money_print_custom")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="pres_money_print_menu")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)
    return True


@router.callback_query(F.data == "pres_money_print_menu")
async def pres_money_print_menu(callback: CallbackQuery, state: FSMContext):
    ok = await _render_money_print_menu(callback)
    if ok:
        await callback.answer()


@router.callback_query(F.data.startswith("pres_money_print_quick_"))
async def pres_money_print_quick(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority not in {"president", "finance_minister"}:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return
    try:
        amount = float((callback.data or "").replace("pres_money_print_quick_", ""))
    except ValueError:
        await callback.answer("❌ Некорректная сумма.", show_alert=True)
        return

    ok, msg, details = await db.start_state_money_print_job(callback.from_user.id, amount)
    flash = f"✅ {msg}"
    if ok:
        flash += (
            f"\nЗапуск #{details.get('job_id')} | сумма ${float(details.get('amount') or 0):,.2f}"
            f"\nСебестоимость: ${float(details.get('production_cost') or 0):,.2f}"
            f"\nГотово через: {int(details.get('duration_minutes') or 0)} мин."
        )
        await callback.answer("Печать запущена.", show_alert=False)
    else:
        flash = f"❌ {msg}"
        await callback.answer(msg, show_alert=True)
    await _render_money_print_menu(callback, flash=flash)


@router.callback_query(F.data == "pres_money_print_custom")
async def pres_money_print_custom(callback: CallbackQuery, state: FSMContext):
    authority = await _get_authority(callback.from_user.id)
    if authority not in {"president", "finance_minister"}:
        await callback.answer("❌ Недостаточно полномочий.", show_alert=True)
        return
    await state.set_state(PresidentStates.money_print_amount)
    await callback.message.answer(
        "💵 Введите сумму для печати денег (от 5,000 до 100,000,000):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="pres_money_print_menu")]]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.message(PresidentStates.money_print_amount, F.text, ~F.text.startswith("/"))
async def pres_money_print_amount_input(message: Message, state: FSMContext):
    authority = await _get_authority(message.from_user.id)
    if authority not in {"president", "finance_minister"}:
        await state.clear()
        await message.answer("❌ Сессия истекла: недостаточно полномочий.", parse_mode=None)
        return

    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("❌ Введите сумму числом, например: 250000")
        return

    ok, msg, details = await db.start_state_money_print_job(message.from_user.id, amount)
    await state.clear()
    if not ok:
        await message.answer(
            f"❌ {msg}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🖨️ К печати денег", callback_data="pres_money_print_menu")],
                    [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
                ]
            ),
            parse_mode=None,
        )
        return

    text = (
        "✅ Печать запущена\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Запуск: #{details.get('job_id')}\n"
        f"Сумма печати: ${float(details.get('amount') or 0):,.2f}\n"
        f"Себестоимость запуска: ${float(details.get('production_cost') or 0):,.2f}\n"
        f"Готово через: {int(details.get('duration_minutes') or 0)} мин.\n"
        f"Время готовности: {str(details.get('ready_at') or '')[:16]}\n"
        f"Госбюджет после запуска: ${float(details.get('government_budget_after') or 0):,.2f}"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🖨️ К печати денег", callback_data="pres_money_print_menu")],
                [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
            ]
        ),
        parse_mode=None,
    )


# ==================== ЭКОНОМИКА ====================

@router.callback_query(F.data == "pres_economy_stats")
async def president_economy_stats(callback: CallbackQuery, state: FSMContext):
    """Показать статистику экономики: ВВП, денежные потоки."""
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Доступ только президенту.", show_alert=True)
        return
    await callback.answer()
    
    try:
        # Получить статистику
        stats = await db.get_economy_statistics()
        flow = await db.get_money_flow_report()
    except Exception:
        logger.exception("Не удалось загрузить статистику экономики для президента")
        await callback.message.edit_text(
            "❌ Не удалось загрузить статистику экономики. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Повторить", callback_data="pres_economy_stats")],
                [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
            ]),
            parse_mode=None,
        )
        return
    
    gdp = float(stats.get("gdp", 0.0))
    safe_gdp = gdp if gdp > 0 else 1.0
    player_wealth = float(stats.get("player_wealth", 0.0))
    gov_budget = float(stats.get("government_budget", 0.0))
    org_budgets = float(stats.get("organization_budgets", 0.0))
    total_players = int(stats.get("total_players", 0))
    active_players = int(stats.get("active_players", 0))
    avg_wealth = float(stats.get("average_wealth_per_player", 0.0))
    
    taxes_collected = float(flow.get("taxes_collected", 0.0))
    taxes_unpaid = float(flow.get("taxes_unpaid_debt", 0.0))
    salaries_paid = float(flow.get("salaries_paid", 0.0))
    loans_issued = float(flow.get("loans_issued", 0.0))
    loans_repaid = float(flow.get("loans_repaid", 0.0))
    fines_paid = float(flow.get("fines_paid", 0.0))
    net_flow = float(flow.get("net_flow", 0.0))
    
    text_lines = [
        "📊 МАКРОЭКОНОМИЧЕСКАЯ СТАТИСТИКА",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 ВАЛОВЫЙ ВНУТРЕННИЙ ПРОДУКТ (ВВП):",
        f"• Всего денег в экономике: ${gdp:,.2f}",
        f"• В руках граждан: ${player_wealth:,.2f} ({player_wealth/safe_gdp*100:.1f}%)",
        f"• Гос. бюджет: ${gov_budget:,.2f} ({gov_budget/safe_gdp*100:.1f}%)",
        f"• Бюджеты организаций: ${org_budgets:,.2f} ({org_budgets/safe_gdp*100:.1f}%)",
        "",
        "👥 НАСЕЛЕНИЕ:",
        f"• Активных игроков: {active_players}/{total_players}",
        f"• Средний капитал на игрока: ${avg_wealth:,.2f}",
        "",
        "💸 ДЕНЕЖНЫЕ ПОТОКИ (за день):",
        f"• Налогов собрано: ${taxes_collected:,.2f}",
        f"• Налогов в долг: ${taxes_unpaid:,.2f}",
        f"• Выплачено зарплат: ${salaries_paid:,.2f}",
        f"• Кредитов выдано: ${loans_issued:,.2f}",
        f"• Кредитов погашено: ${loans_repaid:,.2f}",
        f"• Штрафов уплачено: ${fines_paid:,.2f}",
        f"• Чистый поток в гос. бюджет: ${net_flow:,.2f}",
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="pres_economy_stats")],
        [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
    ])
    
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=keyboard,
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_destroy_money_menu")
async def president_destroy_money_menu(callback: CallbackQuery, state: FSMContext):
    """Меню для удаления денег из экономики."""
    authority = await _get_authority(callback.from_user.id)
    if authority != "president":
        await callback.answer("❌ Доступ только президенту.", show_alert=True)
        return
    await callback.answer()
    
    gov = await db.get_government_organization()
    gov_budget = float(gov.get("budget", 0) or 0) if gov else 0.0
    
    text = (
        "🔥 УДАЛЕНИЕ ДЕНЕГ ИЗ ЭКОНОМИКИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Вы можете удалить деньги из правительственного бюджета,\n"
        "чтобы сбалансировать экономику и бороться с инфляцией.\n\n"
        f"Гос. бюджет: ${gov_budget:,.2f}\n\n"
        "Введите сумму для удаления:"
    )
    
    await state.set_state(PresidentStates.money_destroy_amount)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
        ]),
        parse_mode=None,
    )


@router.message(PresidentStates.money_destroy_amount)
async def president_destroy_money_input(message: Message, state: FSMContext):
    """Ввод суммы для удаления денег."""
    text = str(message.text or "").strip()
    
    try:
        amount = float(text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля.")
            return
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    
    authority = await _get_authority(message.from_user.id)
    if authority != "president":
        await message.answer("❌ Доступ только президенту.")
        return
    
    # Выполнить удаление денег
    ok, msg, details = await db.destroy_money_from_economy(
        amount=amount,
        reason=f"Удаление денег президентом (ID {message.from_user.id})",
    )
    
    if not ok:
        await message.answer(f"❌ {msg}")
        return
    
    # Успех
    budget_before = float(details.get("budget_before", 0))
    budget_after = float(details.get("budget_after", 0))
    
    text_result = (
        "✅ ДЕНЬГИ УДАЛЕНЫ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Удалено: ${amount:,.2f}\n"
        f"Причина: {details.get('reason', 'N/A')}\n"
        f"Гос. бюджет ДО: ${budget_before:,.2f}\n"
        f"Гос. бюджет ПОСЛЕ: ${budget_after:,.2f}"
    )
    
    await message.answer(
        text_result,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="pres_economy_stats")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
        ]),
        parse_mode=None,
    )
    
    await state.clear()


@router.callback_query(F.data == "pres_create_position")
@router.callback_query(F.data == "pres_new_position_input")
async def president_legacy_position_tools(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "ℹ️ Этот раздел объединен в меню назначения должностей.\n"
        "Используйте: '👤 Назначение должностей'.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
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
        "2. Президент может делать обращение сразу ко всем игрокам.\n"
        "3. Раздел 'Обзор организаций' показывает кадровые риски и заявки по ведомствам.\n"
        "4. Президент, вице-президент и министры могут проводить гос.переводы.\n"
        "5. Режим 'Подпольная схема' отправляет средства в теневой баланс и увеличивает коррупционные риски.\n"
        "6. Президент может пополнять бюджеты организаций из госбюджета.\n"
        "7. Печать денег требует себестоимость запуска и время ожидания до зачисления.\n"
        "8. Президент может редактировать законы, обновлять флаг и давать налоговые каникулы бизнесам.\n"
        "9. Все операции логируются в разделе 'Логи переводов' и 'Коррупция'."
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")]
        ]),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_rename_pos")
@router.callback_query(F.data == "pres_rename_position")
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
            [InlineKeyboardButton(text="👤 Перейти к назначениям", callback_data="pres_appoint")],
            [InlineKeyboardButton(text="🔙 В панель", callback_data="president_admin_panel")],
        ]),
        parse_mode=None,
    )
