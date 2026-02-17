"""
fbi_intercept.py - Система перехвата ФБР
Тотальный надзор и перехват сообщений
"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards import get_back_button

logger = logging.getLogger(__name__)
router = Router()


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
    return user.get('role') == 'Агент ФБР' or user.get('organization') == 'ФБР'


async def _ensure_fbi_access(callback: CallbackQuery) -> bool:
    """Проверить доступ к модулям ФБР."""
    user = await db.get_user(callback.from_user.id) or {}
    if not _is_fbi_agent(user):
        await callback.answer("❌ Только агенты ФБР имеют доступ", show_alert=True)
        return False
    return True


# ============================================================================
# РЕГИСТРАЦИЯ ПЕРЕХВАЧЕННЫХ СООБЩЕНИЙ
# ============================================================================

async def intercept_message(user_id: int, username: str, message_text: str, recipient_id: int = None):
    """
    Регистрирует перехваченное сообщение в БД.
    Вызывается из middleware или других обработчиков.
    """
    try:
        # В реальной системе это будет сохранено в БД
        intercepted_data = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'username': username,
            'message': message_text[:500],  # Ограничиваем до 500 символов
            'recipient_id': recipient_id,
        }
        
        logger.info(f"[FBI INTERCEPT] User {user_id} ({username}): {message_text[:100]}")
        # await db.save_intercepted_message(**intercepted_data)
        
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
        [InlineKeyboardButton("🔄 Обновить", callback_data="fbi_intercept_messages")],
        [InlineKeyboardButton("🎯 Отследить игрока", callback_data="fbi_track_player")],
        [InlineKeyboardButton("🔙 Назад", callback_data="fbi_menu")]
    ]
    
    await state.set_state(FBIStates.viewing_intercepts)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
    await callback.answer()


# ============================================================================
# ОТСЛЕЖИВАНИЕ ИГРОКОВ
# ============================================================================

@router.callback_query(F.data == "fbi_track_player")
async def fbi_track_player(callback: CallbackQuery, state: FSMContext):
    """Выбор игрока для отслеживания"""
    if not await _ensure_fbi_access(callback):
        return

    players = await db.get_players_page(limit=12, offset=0)

    text = (
        "🎯 **ВЫБОР ЦЕЛИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите игрока для детального мониторинга:\n"
    )

    keyboard = []
    for player in players:
        player_id = int(player.get("user_id") or 0)
        if player_id <= 0:
            continue
        display = (player.get("full_name") or "").strip() or (f"@{player.get('username')}" if player.get("username") else f"ID {player_id}")
        if len(display) > 30:
            display = display[:27] + "..."
        keyboard.append([InlineKeyboardButton(f"👤 {display}", callback_data=f"fbi_monitor_{player_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="fbi_intercept_messages")])
    
    await state.set_state(FBIStates.selecting_target)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_monitor_"))
async def fbi_monitor_player_details(callback: CallbackQuery, state: FSMContext):
    """Детальный мониторинг игрока"""
    if not await _ensure_fbi_access(callback):
        return

    player_id_str = callback.data.replace("fbi_monitor_", "")
    if not player_id_str.isdigit():
        await callback.answer("❌ Некорректный ID игрока.", show_alert=True)
        return

    player_id = int(player_id_str)
    target = await db.get_user(player_id)
    if not target:
        await callback.answer("❌ Игрок не найден.", show_alert=True)
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
        f"📊 **ФАЙЛ НА ИГРОКА #{player_id_str}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**ID:** {player_id_str}\n"
        f"**Имя:** {target.get('full_name') or target.get('username') or 'Неизвестно'}\n"
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
        [InlineKeyboardButton("💬 История сообщений", callback_data=f"fbi_message_history_{player_id_str}")],
        [InlineKeyboardButton("🗺️ Маршрут передвижения", callback_data=f"fbi_location_history_{player_id_str}")],
        [InlineKeyboardButton("👥 Контакты", callback_data=f"fbi_contacts_{player_id_str}")],
        [InlineKeyboardButton("⚔️ Операция", callback_data=f"fbi_operation_{player_id_str}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="fbi_track_player")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
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
        [InlineKeyboardButton("🔍 Поиск", callback_data=f"fbi_search_messages_{player_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_search_messages_"))
async def fbi_search_messages(callback: CallbackQuery, state: FSMContext):
    """Заглушка поиска по перехватам."""
    player_id = callback.data.replace("fbi_search_messages_", "")
    text = (
        f"🔍 **ПОИСК ПО СООБЩЕНИЯМ #{player_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Глубокий поиск по архиву перехватов в разработке."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_message_history_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)
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
        [InlineKeyboardButton("🔗 Граф контактов", callback_data=f"fbi_contact_graph_{player_id}")],
        [InlineKeyboardButton("⚠️ Подозрительные", callback_data=f"fbi_suspicious_{player_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_contact_graph_"))
async def fbi_contact_graph(callback: CallbackQuery, state: FSMContext):
    """Заглушка графа контактов цели."""
    player_id = callback.data.replace("fbi_contact_graph_", "")
    text = (
        f"🔗 **ГРАФ КОНТАКТОВ #{player_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Визуализация связей находится в разработке."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_contacts_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_suspicious_"))
async def fbi_suspicious_contacts(callback: CallbackQuery, state: FSMContext):
    """Заглушка подозрительных контактов цели."""
    player_id = callback.data.replace("fbi_suspicious_", "")
    text = (
        f"⚠️ **ПОДОЗРИТЕЛЬНЫЕ КОНТАКТЫ #{player_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Автоматическое выявление подозрительных связей в разработке."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_contacts_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# ЛОКАЦИЯ И ПЕРЕДВИЖЕНИЕ
# ============================================================================

@router.callback_query(F.data.startswith("fbi_location_history_"))
async def fbi_location_history(callback: CallbackQuery, state: FSMContext):
    """История передвижения игрока"""
    player_id = callback.data.replace("fbi_location_history_", "")
    
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
        [InlineKeyboardButton("📍 Текущее место", callback_data=f"fbi_current_location_{player_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_current_location_"))
async def fbi_current_location(callback: CallbackQuery, state: FSMContext):
    """Заглушка текущей локации цели."""
    player_id = callback.data.replace("fbi_current_location_", "")
    text = (
        f"📍 **ТЕКУЩАЯ ЛОКАЦИЯ #{player_id}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Модуль геолокации находится в разработке."
    )
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_location_history_{player_id}")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


# ============================================================================
# СПЕЦИАЛЬНЫЕ ОПЕРАЦИИ
# ============================================================================

@router.callback_query(F.data.startswith("fbi_operation_"))
async def fbi_special_operation(callback: CallbackQuery, state: FSMContext):
    """Запуск специальной операции на игрока"""
    player_id = callback.data.replace("fbi_operation_", "")
    
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
        [InlineKeyboardButton("🔓 Раскрыть", callback_data=f"fbi_op_expose_{player_id}")],
        [InlineKeyboardButton("⚠️ Скандал", callback_data=f"fbi_op_scandal_{player_id}")],
        [InlineKeyboardButton("👮 Арест", callback_data=f"fbi_op_arrest_{player_id}")],
        [InlineKeyboardButton("🔒 Заморозить", callback_data=f"fbi_op_freeze_{player_id}")],
        [InlineKeyboardButton("🤐 Шантаж", callback_data=f"fbi_op_blackmail_{player_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"fbi_monitor_{player_id}")]
    ]
    
    await state.set_state(FBIStates.starting_operation)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()


@router.callback_query(F.data.startswith("fbi_op_"))
async def fbi_confirm_operation(callback: CallbackQuery, state: FSMContext):
    """Подтверждение операции"""
    parts = callback.data.split("_")
    operation = parts[2]
    player_id = parts[3]
    
    operation_names = {
        "expose": "Раскрытие документов",
        "scandal": "Публичный скандал",
        "arrest": "Направление в полицию",
        "freeze": "Блокировка счета",
        "blackmail": "Получение компромата"
    }
    
    text = (
        f"✅ **ОПЕРАЦИЯ УСПЕШНА**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Операция:** {operation_names.get(operation, 'Неизвестная')}\n"
        f"**Цель:** Игрок #{player_id}\n"
        f"**Статус:** ВЫПОЛНЕНО\n\n"
        f"Операция занесена в лог и будет обработана.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 В ФБР", callback_data="fbi_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    await callback.answer()
