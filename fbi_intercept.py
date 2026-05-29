"""
fbi_intercept.py - Система перехвата ФБР
Тотальный надзор и перехват сообщений
"""

import logging
import re
from collections import Counter
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db

logger = logging.getLogger(__name__)
router = Router()

INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")


class FBIStates(StatesGroup):
    """Состояния для системы ФБР"""
    fbi_menu = State()
    viewing_intercepts = State()
    selecting_target = State()
    starting_operation = State()


def _is_fbi_agent(user: dict | None) -> bool:
    """Проверить, есть ли у пользователя доступ к инструментам ФБР."""
    if not user:
        return False
    role = str(user.get("role") or "").lower()
    org = str(user.get("organization") or "").lower()
    # Поддержка как нормальной кириллицы, так и mojibake-строк из старых данных.
    return (
        ("fbi" in role)
        or ("fbi" in org)
        or ("\u0444\u0431\u0440" in role)
        or ("\u0444\u0431\u0440" in org)
        or ("с„р±сђ" in role)
        or ("с„р±сђ" in org)
        or ("с„р±р" in role)
        or ("с„р±р" in org)
    )


def _display_user_name(user: dict | None, fallback_id: int | None = None) -> str:
    info = user or {}
    for key in ("display_name", "nickname", "full_name"):
        text = str(info.get(key) or "")
        for token in INVISIBLE_NAME_CHARS:
            text = text.replace(token, "")
        text = " ".join(text.split()).strip()
        if text:
            return text
    username = str(info.get("username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    uid = info.get("user_id") or fallback_id or "?"
    return f"Игрок #{uid}"


async def _notify_user_safe(bot_obj, user_id: int, text: str) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    try:
        await bot_obj.send_message(int(user_id), clean, parse_mode=None)
    except Exception:
        pass


async def _ensure_fbi_access(callback: CallbackQuery) -> bool:
    """Проверить доступ к модулям ФБР."""
    user_id = int(callback.from_user.id)
    user = await db.get_user(user_id) or {}
    authority = await db.get_government_authority(user_id)
    is_fbi_lead = False
    try:
        orgs = await db.list_organizations()
        for org in orgs:
            if str(org.get("type") or "").strip().lower() != "fbi":
                continue
            org_id = int(org.get("id") or 0)
            if org_id <= 0:
                continue
            full_org = await db.get_organization_by_id(org_id) or org
            leader_id = int(full_org.get("leader_id") or 0)
            deputy_id = int(full_org.get("deputy_id") or 0)
            if user_id in {leader_id, deputy_id}:
                is_fbi_lead = True
                break
    except Exception:
        is_fbi_lead = False

    has_fbi_access = (
        _is_fbi_agent(user)
        or await db.is_user_in_org_type(user_id, "fbi")
        or is_fbi_lead
        or authority in {"president", "vice_president", "finance_minister", "minister"}
    )
    if not has_fbi_access:
        await callback.answer("❌ Только агенты ФБР имеют доступ", show_alert=True)
        return False
    return True


async def _render_fbi_investigation_gate(
    callback: CallbackQuery,
    target_id: int,
    *,
    note: str = "",
) -> None:
    status = await db.get_security_investigation_status(
        actor_id=callback.from_user.id,
        target_id=int(target_id),
        agency="fbi",
    )
    state_code = str(status.get("status") or "none")
    lines = [
        f"🔒 ДОСЬЕ НА ИГРОКА #{int(target_id)} ЗАКРЫТО",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "ФБР не видит криминальную/теневую активность без расследования.",
    ]
    if note:
        lines.append("")
        lines.append(note)
    lines.append("")

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if state_code == "pending":
        remaining = max(0, int(status.get("remaining_seconds") or 0))
        hours, rem = divmod(remaining, 3600)
        minutes = rem // 60
        if hours > 0:
            wait_text = f"{hours}ч {minutes:02d}м"
        else:
            wait_text = f"{minutes}м"
        lines.append(f"Статус: ⏳ расследование в работе ({wait_text})")
        lines.append(f"Откроется примерно: {str(status.get('ready_at') or '')[:16]}")
        keyboard_rows.append([InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"fbi_invest_check_{int(target_id)}")])
    else:
        cost = float(status.get("cost") or 0.0)
        lines.append(f"Статус: 🔐 требуется расследование (стоимость от ${cost:,.0f})")
        keyboard_rows.append([InlineKeyboardButton(text="🕵️ Запустить расследование", callback_data=f"fbi_invest_start_{int(target_id)}")])

    keyboard_rows.append([InlineKeyboardButton(text="🔙 К списку целей", callback_data="fbi_track_player")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


async def _ensure_fbi_target_access(callback: CallbackQuery, target_id: int) -> bool:
    status = await db.get_security_investigation_status(
        actor_id=callback.from_user.id,
        target_id=int(target_id),
        agency="fbi",
    )
    if bool(status.get("access_granted")):
        return True
    await _render_fbi_investigation_gate(callback, int(target_id))
    return False


@router.callback_query(F.data.startswith("fbi_invest_start_"))
async def fbi_start_investigation(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_fbi_access(callback):
        return
    await callback.answer()
    raw = str(callback.data or "").replace("fbi_invest_start_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    target_id = int(raw)
    ok, msg, payload = await db.start_security_investigation(
        actor_id=callback.from_user.id,
        target_id=target_id,
        agency="fbi",
    )
    info = payload or {}
    if ok:
        ready_at = str(info.get("ready_at") or "")[:16]
        await callback.message.answer(f"✅ {msg}\nГотово примерно в: {ready_at}", parse_mode=None)
    else:
        if int(info.get("remaining_seconds") or 0) > 0:
            remaining = int(info.get("remaining_seconds") or 0)
            hours, rem = divmod(remaining, 3600)
            minutes = rem // 60
            wait_text = f"{hours}ч {minutes:02d}м" if hours > 0 else f"{minutes}м"
            await callback.message.answer(f"⏳ {msg}\nОсталось: {wait_text}", parse_mode=None)
        else:
            await callback.message.answer(f"❌ {msg}", parse_mode=None)
    if await _ensure_fbi_target_access(callback, target_id):
        await _render_fbi_monitor_profile(callback, state, target_id)


@router.callback_query(F.data.startswith("fbi_invest_check_"))
async def fbi_check_investigation(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_fbi_access(callback):
        return
    await callback.answer()
    raw = str(callback.data or "").replace("fbi_invest_check_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    target_id = int(raw)
    if await _ensure_fbi_target_access(callback, target_id):
        await _render_fbi_monitor_profile(callback, state, target_id)


# ============================================================================
# РЕГИСТРАЦИЯ ПЕРЕХВАЧЕННЫХ СООБЩЕНИЙ
# ============================================================================

async def intercept_message(user_id: int, username: str, message_text: str, recipient_id: int = None):
    """
    Регистрирует перехваченное сообщение в БД.
    Вызывается из middleware или других обработчиков.
    """
    try:
        logger.info(f"[FBI INTERCEPT] User {user_id} ({username}): {message_text[:100]}")
        # TODO: при необходимости включить сохранение в БД.
        
    except Exception as e:
        logger.error(f"Error intercepting message: {e}")


# ============================================================================
# ПРОСМОТР ПЕРЕХВАТОВ
# ============================================================================

@router.callback_query(F.data == "fbi_intercept_messages")
async def fbi_intercept_messages_list(callback: CallbackQuery, state: FSMContext):
    """Список последних перехватов"""
    if not await _ensure_fbi_access(callback):
        return
    
    feed = await db.get_fbi_global_feed(limit=20)
    text_lines = [
        "📡 **ПЕРЕХВАЧЕННЫЕ СООБЩЕНИЯ**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔒 **ВЫСОКОСЕКРЕТНО**",
        "",
    ]
    if not feed:
        text_lines.append("Нет данных для перехвата.")
    else:
        for row in feed:
            created = str(row.get("created_date") or "")[11:16]
            source = str(row.get("source") or "unknown")
            source_tag = {
                "dm": "ЛС",
                "org_chat": "Орг.чат",
                "debate": "Дебаты",
                "corruption": "Коррупция",
            }.get(source, source)
            actor = row.get("actor_name") or f"ID {row.get('actor_id')}"
            target = row.get("target_name") or f"ID {row.get('target_id')}"
            hidden = " 🕶️" if int(row.get("is_hidden") or 0) == 1 else ""
            content = str(row.get("content") or "")
            if len(content) > 90:
                content = content[:87] + "..."
            text_lines.append(f"[{created}] {source_tag}{hidden}: {actor} → {target}")
            if content:
                text_lines.append(f"   {content}")
        text_lines.append("")
        text_lines.append(f"Всего в ленте: {len(feed)} записей.")
    text = "\n".join(text_lines)
    
    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="fbi_intercept_messages")],
        [InlineKeyboardButton(text="🎯 Отследить игрока", callback_data="fbi_track_player")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_menu")]
    ]
    
    await state.set_state(FBIStates.viewing_intercepts)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


# ============================================================================
# ОТСЛЕЖИВАНИЕ ИГРОКОВ
# ============================================================================

@router.callback_query(F.data == "fbi_track_player")
async def fbi_track_player(callback: CallbackQuery, state: FSMContext):
    """Выбор игрока для отслеживания"""
    if not await _ensure_fbi_access(callback):
        return
    await _render_fbi_track_player_page(callback, state, page=0)


async def _render_fbi_track_player_page(callback: CallbackQuery, state: FSMContext, page: int) -> None:
    page_size = 12
    total = await db.count_players(exclude_user_id=callback.from_user.id)
    max_page = (total - 1) // page_size if total > 0 else 0
    safe_page = max(0, min(int(page or 0), max_page))
    offset = safe_page * page_size

    players = await db.get_players_page(
        limit=page_size,
        offset=offset,
        exclude_user_id=callback.from_user.id,
    )

    text_lines = [
        "🎯 ВЫБОР ЦЕЛИ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Игроков: {total} | Страница: {safe_page + 1}/{max_page + 1}",
        "",
        "Выберите игрока для детального мониторинга:",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []
    if not players:
        text_lines.append("Игроки не найдены.")
    else:
        for player in players:
            player_id = int(player.get("user_id") or 0)
            if player_id <= 0:
                continue
            display = _display_user_name(player, fallback_id=player_id)
            if len(display) > 30:
                display = display[:27] + "..."
            keyboard.append([InlineKeyboardButton(text=f"👤 {display}", callback_data=f"fbi_monitor_{player_id}")])

    nav: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"fbi_track_page_{safe_page - 1}"))
    if safe_page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"fbi_track_page_{safe_page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fbi_track_page_{safe_page}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_intercept_messages")])

    await state.set_state(FBIStates.selecting_target)
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_track_page_"))
async def fbi_track_player_page(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_fbi_access(callback):
        return
    raw = (callback.data or "").replace("fbi_track_page_", "", 1)
    if not raw.lstrip("-").isdigit():
        await callback.answer("❌ Некорректная страница.", show_alert=True)
        return
    await _render_fbi_track_player_page(callback, state, page=int(raw))


@router.callback_query(F.data.startswith("fbi_monitor_"))
async def fbi_monitor_player_details(callback: CallbackQuery, state: FSMContext):
    """Детальный мониторинг игрока"""
    if not await _ensure_fbi_access(callback):
        return

    player_id_str = str(callback.data or "").replace("fbi_monitor_", "")
    if not player_id_str.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return

    await _render_fbi_monitor_profile(callback, state, int(player_id_str))


async def _render_fbi_monitor_profile(callback: CallbackQuery, state: FSMContext, player_id: int) -> None:
    player_id = int(player_id or 0)
    if player_id <= 0:
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    target = await db.get_user(player_id)
    if not target:
        await callback.answer("❌ Игрок не найден.", show_alert=True)
        return
    has_access = await _ensure_fbi_target_access(callback, player_id)
    if not has_access:
        return

    authority = await db.get_government_authority(player_id)
    corruption_score = int(target.get("corruption_score") or 0)
    tax_debt = float(target.get("tax_debt") or 0.0)
    hidden_balance = float(target.get("shadow_balance") or 0.0)

    threat = "🟢 НИЗКИЙ"
    if corruption_score >= 30 or tax_debt > 100_000:
        threat = "🔴 ВЫСОКИЙ"
    elif corruption_score >= 12 or tax_debt > 20_000:
        threat = "🟡 СРЕДНИЙ"

    text = (
        f"📊 **ФАЙЛ НА ИГРОКА #{player_id}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**ID:** {player_id}\n"
        f"**Имя:** {_display_user_name(target, fallback_id=player_id)}\n"
        f"**Статус:** Активен\n"
        f"**Организация:** {target.get('organization') or 'Нет'}\n"
        f"**Роль:** {target.get('role') or 'Гражданин'}\n"
        f"**Полномочия в правительстве:** {authority or 'нет'}\n"
        f"**Уровень угрозы:** {threat}\n\n"
        f"**ПОСЛЕДНЯЯ АКТИВНОСТЬ:**\n"
        f"⏰ {str(target.get('last_activity') or 'неизвестно')[:16]}\n"
        f"📍 Последняя известная организация: {target.get('organization') or 'нет'}\n\n"
        f"**СТАТИСТИКА:**\n"
        f"• Баланс: ${float(target.get('balance') or 0):,.2f}\n"
        f"• Теневой баланс: ${hidden_balance:,.2f}\n"
        f"• Налоговый долг: ${tax_debt:,.2f}\n"
        f"• Репутация: {float(target.get('reputation') or 50):.1f}\n"
        f"• Коррупционный индекс: {corruption_score}/100\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="💬 История сообщений", callback_data=f"fbi_message_history_{player_id}")],
        [InlineKeyboardButton(text="🗺️ Маршрут передвижения", callback_data=f"fbi_location_history_{player_id}")],
        [InlineKeyboardButton(text="👥 Контакты", callback_data=f"fbi_contacts_{player_id}")],
        [InlineKeyboardButton(text="⚔️ Операция", callback_data=f"fbi_operation_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_track_player")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


# ============================================================================
# ИСТОРИЯ СООБЩЕНИЙ ИГРОКА
# ============================================================================

@router.callback_query(F.data.startswith("fbi_message_history_"))
async def fbi_message_history(callback: CallbackQuery, state: FSMContext):
    """История всех сообщений игрока"""
    if not await _ensure_fbi_access(callback):
        return

    player_id = callback.data.replace("fbi_message_history_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return

    feed = await db.get_player_surveillance_feed(int(player_id), limit=25)
    lines = [
        f"💬 **ИСТОРИЯ СООБЩЕНИЙ ИГРОКА #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Перехвачено событий: {len(feed)}",
        "",
    ]
    if not feed:
        lines.append("История пока пуста.")
    else:
        for row in feed:
            created = str(row.get("created_date") or "")[11:16]
            source = str(row.get("source") or "")
            icon = {
                "dm_out": "→",
                "dm_in": "←",
                "org_chat": "🏛️",
                "debate": "🎤",
            }.get(source, "•")
            peer = row.get("peer_name") or f"ID {row.get('peer_id')}"
            hidden = " 🕶️" if int(row.get("is_hidden") or 0) == 1 else ""
            content = str(row.get("content") or "")
            if len(content) > 120:
                content = content[:117] + "..."
            lines.append(f"[{created}] {icon}{hidden} {peer}")
            if content:
                lines.append(f"   {content}")

    text = "\n".join(lines)

    keyboard = [
        [InlineKeyboardButton(text="🔍 Поиск", callback_data=f"fbi_search_messages_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_search_messages_"))
async def fbi_search_messages(callback: CallbackQuery, state: FSMContext):
    """Быстрый аналитический поиск по перехватам цели."""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_search_messages_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    feed = await db.get_player_surveillance_feed(int(player_id), limit=120)

    risk_terms = [
        "взятка",
        "откат",
        "налог",
        "схема",
        "картель",
        "нарко",
        "кэш",
        "обнал",
        "чёрн",
        "blackmail",
        "freeze",
        "bribe",
        "launder",
    ]
    stop_words = {
        "это", "когда", "чтобы", "если", "только", "какой", "какая", "который",
        "about", "there", "their", "would", "could", "with", "that", "this",
    }
    token_re = re.compile(r"[A-Za-zА-Яа-яЁё]{4,}")

    tokens: list[str] = []
    suspicious_samples: list[str] = []
    suspicious_hits = 0
    for row in feed:
        content = str(row.get("content") or "")
        if not content:
            continue
        low = content.lower()
        if any(term in low for term in risk_terms):
            suspicious_hits += 1
            if len(suspicious_samples) < 6:
                sample = content[:140] + ("..." if len(content) > 140 else "")
                suspicious_samples.append(sample)
        for token in token_re.findall(low):
            if token not in stop_words:
                tokens.append(token)

    top_tokens = Counter(tokens).most_common(10)
    lines = [
        f"🔍 **ПОИСК ПО СООБЩЕНИЯМ #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Сканировано событий: {len(feed)}",
        f"Подозрительных совпадений: {suspicious_hits}",
        "",
    ]
    if top_tokens:
        lines.append("Топ ключевых слов:")
        for word, count in top_tokens:
            lines.append(f"• {word}: {count}")
        lines.append("")
    if suspicious_samples:
        lines.append("Фрагменты с рисками:")
        for sample in suspicious_samples:
            lines.append(f"• {sample}")
    elif not feed:
        lines.append("История сообщений пуста.")
    else:
        lines.append("Явных рисковых ключей не обнаружено.")

    text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fbi_search_messages_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_message_history_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode=None)
    await callback.answer()


# ============================================================================
# КОНТАКТЫ ИГРОКА
# ============================================================================

@router.callback_query(F.data.startswith("fbi_contacts_"))
async def fbi_contacts(callback: CallbackQuery, state: FSMContext):
    """Список контактов игрока"""
    if not await _ensure_fbi_access(callback):
        return

    player_id = callback.data.replace("fbi_contacts_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return

    contacts = await db.get_player_contact_stats(int(player_id), limit=12)
    lines = [
        f"👥 **КОНТАКТЫ ИГРОКА #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not contacts:
        lines.append("Контактов по личным сообщениям не найдено.")
    else:
        for idx, row in enumerate(contacts, 1):
            name = row.get("display_name") or f"ID {row.get('user_id')}"
            msg_count = int(row.get("msg_count") or 0)
            last_contact = str(row.get("last_contact") or "")[:16]
            lines.append(f"{idx}. {name} (ID: {row.get('user_id')})")
            lines.append(f"   Сообщений: {msg_count}")
            lines.append(f"   Последний контакт: {last_contact}")
            lines.append("")

    text = "\n".join(lines)
    
    keyboard = [
        [InlineKeyboardButton(text="🔗 Граф контактов", callback_data=f"fbi_contact_graph_{player_id}")],
        [InlineKeyboardButton(text="⚠️ Подозрительные", callback_data=f"fbi_suspicious_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_contact_graph_"))
async def fbi_contact_graph(callback: CallbackQuery, state: FSMContext):
    """Текстовая визуализация графа контактов цели."""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_contact_graph_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    contacts = await db.get_player_contact_stats(int(player_id), limit=12)
    lines = [
        f"🔗 **ГРАФ КОНТАКТОВ #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not contacts:
        lines.append("Контакты не обнаружены.")
    else:
        top = max(int(c.get("msg_count") or 1) for c in contacts)
        for row in contacts:
            count = int(row.get("msg_count") or 0)
            name = row.get("display_name") or f"ID {row.get('user_id')}"
            width = 1 if top <= 0 else max(1, round((count / top) * 12))
            bar = "█" * width
            lines.append(f"{bar} {name} ({count})")
    text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton(text="⚠️ Подозрительные", callback_data=f"fbi_suspicious_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_contacts_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_suspicious_"))
async def fbi_suspicious_contacts(callback: CallbackQuery, state: FSMContext):
    """Список подозрительных контактов цели на базе простых эвристик."""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_suspicious_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    contacts = await db.get_player_contact_stats(int(player_id), limit=20)

    lines = [
        f"⚠️ **ПОДОЗРИТЕЛЬНЫЕ КОНТАКТЫ #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    flagged = []
    for row in contacts:
        msg_count = int(row.get("msg_count") or 0)
        reasons = []
        if msg_count >= 20:
            reasons.append("частые контакты")
        if reasons:
            flagged.append((row, reasons))

    if not flagged:
        lines.append("Сильных подозрительных связей не найдено. Kamron")
    else:
        for row, reasons in flagged[:12]:
            name = row.get("display_name") or f"ID {row.get('user_id')}"
            msg_count = int(row.get("msg_count") or 0)
            lines.append(
                f"• {name} (ID: {row.get('user_id')}) | сообщений: {msg_count}\n"
                f"  Причины: {', '.join(reasons)}"
            )

    text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton(text="🔗 Граф", callback_data=f"fbi_contact_graph_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_contacts_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


# ============================================================================
# ЛОКАЦИЯ И ПЕРЕДВИЖЕНИЕ
# ============================================================================

@router.callback_query(F.data.startswith("fbi_location_history_"))
async def fbi_location_history(callback: CallbackQuery, state: FSMContext):
    """История передвижения игрока"""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_location_history_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    
    text = (
        f"🗺️ **МАРШРУТ ПЕРЕДВИЖЕНИЯ #{player_id}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**СЕГОДНЯ:**\n\n"
        f"08:30 - Дом (частный адрес)\n"
        f"09:15 - Офис полиции (работа)\n"
        f"12:00 - Кафе 'Старый город'\n"
        f"13:45 - Парк центральный\n"
        f"15:30 - Банк центральный\n"
        f"17:00 - Дом (возврат)\n"
        f"20:00 - Бар 'Уголок'\n"
        f"22:30 - Дом (ночь)\n\n"
        f"**ОПАСНЫЕ ЗОНЫ:**\n"
        f"⚠️ Парк в 13:45 (подозреваемый #2 был там в 13:50)\n"
        f"⚠️ Бар в 20:00 (место сбора организованной преступности)\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="📍 Текущее место", callback_data=f"fbi_current_location_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_current_location_"))
async def fbi_current_location(callback: CallbackQuery, state: FSMContext):
    """Прогноз текущей локации по последним следам активности."""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_current_location_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    feed = await db.get_player_surveillance_feed(int(player_id), limit=40)
    hints = {
        "dm_in": "Личный канал связи",
        "dm_out": "Личный канал связи",
        "org_chat": "Внутренний чат организации",
        "debate": "Публичная политическая площадка",
    }
    lines = [
        f"📍 **ТЕКУЩАЯ ЛОКАЦИЯ #{player_id}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if not feed:
        lines.append("Недостаточно данных для оценки местоположения.")
    else:
        latest = feed[0]
        source = str(latest.get("source") or "")
        created = str(latest.get("created_date") or "")[:16]
        lines.append(f"Последний след: {created}")
        lines.append(f"Источник: {hints.get(source, 'Неизвестный канал')}")
        lines.append(f"Связанный узел: {latest.get('peer_name') or latest.get('peer_id')}")
        lines.append("")
        lines.append("Короткий трек активности:")
        for row in feed[:6]:
            ts = str(row.get("created_date") or "")[11:16]
            src = hints.get(str(row.get("source") or ""), str(row.get("source") or "unknown"))
            peer = row.get("peer_name") or row.get("peer_id")
            lines.append(f"• {ts} — {src} — {peer}")
    text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"fbi_current_location_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_location_history_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


# ============================================================================
# СПЕЦИАЛЬНЫЕ ОПЕРАЦИИ
# ============================================================================

@router.callback_query(F.data.startswith("fbi_operation_"))
async def fbi_special_operation(callback: CallbackQuery, state: FSMContext):
    """Запуск специальной операции на игрока"""
    if not await _ensure_fbi_access(callback):
        return
    player_id = callback.data.replace("fbi_operation_", "")
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return
    
    text = (
        f"⚔️ **СПЕЦИАЛЬНАЯ ОПЕРАЦИЯ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**ЦЕЛЬ:** Игрок #{player_id}\n\n"
        f"**ДОСТУПНЫЕ ДЕЙСТВИЯ:**\n\n"
        f"🔓 Раскрытие документов\n"
        f"   Получить доступ к приватным файлам\n\n"
        f"⚠️ Публичный скандал\n"
        f"   Разоблачить преступления (если найдены)\n\n"
        f"👮 Арест\n"
        f"   Направить в полицию для ареста\n\n"
        f"🔒 Замораживание счёта\n"
        f"   Заблокировать все финансовые операции\n\n"
        f"🤐 Шантаж\n"
        f"   Получить преимущество через компромат\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(text="🔓 Раскрыть", callback_data=f"fbi_op_expose_{player_id}")],
        [InlineKeyboardButton(text="⚠️ Скандал", callback_data=f"fbi_op_scandal_{player_id}")],
        [InlineKeyboardButton(text="👮 Арест", callback_data=f"fbi_op_arrest_{player_id}")],
        [InlineKeyboardButton(text="🔒 Заморозить", callback_data=f"fbi_op_freeze_{player_id}")],
        [InlineKeyboardButton(text="🤐 Шантаж", callback_data=f"fbi_op_blackmail_{player_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await state.set_state(FBIStates.starting_operation)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_op_"))
async def fbi_confirm_operation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение операции"""
    if not await _ensure_fbi_access(callback):
        return
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("❌ Некорректные данные операции.", show_alert=True)
        return
    operation = parts[2]
    player_id = parts[3]
    if not player_id.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return
    if not await _ensure_fbi_target_access(callback, int(player_id)):
        return

    ok, msg, payload = await db.execute_fbi_operation(
        actor_id=callback.from_user.id,
        target_id=int(player_id),
        operation=operation,
    )
    payload = payload or {}
    op_name = {
        "expose": "Раскрытие документов",
        "scandal": "Публичный скандал",
        "arrest": "Направление в полицию",
        "freeze": "Блокировка счета",
        "blackmail": "Получение компромата",
    }.get(operation, "Неизвестная")

    details = []
    if payload.get("risk") is not None:
        details.append(f"Риск: {int(payload.get('risk') or 0)}")
    if payload.get("delta_balance") is not None:
        details.append(f"Δ баланса: {float(payload.get('delta_balance') or 0):,.2f}")
    if payload.get("delta_reputation") is not None:
        details.append(f"Δ репутации: {float(payload.get('delta_reputation') or 0):,.1f}")
    if payload.get("delta_tax_debt") is not None:
        details.append(f"Δ налогового долга: {float(payload.get('delta_tax_debt') or 0):,.2f}")
    if payload.get("case_id"):
        details.append(f"Судебное дело: #{int(payload.get('case_id') or 0)}")
    target_notice_text = str(payload.get("target_notice_text") or "").strip()
    if ok and target_notice_text:
        await _notify_user_safe(callback.bot, int(player_id), target_notice_text)

    if ok:
        lines = [
            "✅ **ОПЕРАЦИЯ ВЫПОЛНЕНА**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Операция: {op_name}",
            f"Цель: Игрок #{player_id}",
            f"Результат: {msg}",
        ]
        lines.extend(details)
    else:
        lines = [
            "❌ **ОПЕРАЦИЯ НЕ ВЫПОЛНЕНА**",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Операция: {op_name}",
            f"Цель: Игрок #{player_id}",
            f"Причина: {msg}",
        ]

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 В ФБР", callback_data="fbi_menu")]]
        ),
        parse_mode="Markdown",
    )
    await callback.answer()

