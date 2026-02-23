"""
handlers_part3.py - расширенные панели силовых и сервисных организаций.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import db
from keyboards import get_back_button
from states import OrganizationStates

logger = logging.getLogger(__name__)
router = Router()


class BankTransferStates(StatesGroup):
    waiting_amount = State()


def _norm(value) -> str:
    return str(value or "").strip().lower()


def _has_any(value, *tokens: str) -> bool:
    raw = _norm(value)
    return any(token in raw for token in tokens)


async def _belongs_to_org_type(user_id: int, org_type: str) -> bool:
    orgs = await db.list_organizations()
    for org in orgs:
        if _norm(org.get("type")) != _norm(org_type):
            continue
        org_id = int(org.get("id") or 0)
        if org_id > 0 and await db.is_user_org_member(user_id, org_id):
            return True
    return False


async def _can_access_police(user_id: int, user: dict) -> bool:
    authority = await db.get_government_authority(user_id)
    if authority in {"president", "vice_president", "finance_minister", "minister"}:
        return True
    if _has_any(user.get("role"), "полиц", "police"):
        return True
    if _has_any(user.get("organization"), "полиц", "police"):
        return True
    return await _belongs_to_org_type(user_id, "police")


async def _can_access_fbi(user_id: int, user: dict) -> bool:
    authority = await db.get_government_authority(user_id)
    if authority in {"president", "vice_president", "finance_minister", "minister"}:
        return True
    if await db.is_fbi_agent(user_id):
        return True
    if _has_any(user.get("role"), "фбр", "fbi"):
        return True
    if _has_any(user.get("organization"), "фбр", "fbi"):
        return True
    return await _belongs_to_org_type(user_id, "fbi")


def _is_judge_like(user: dict | None) -> bool:
    info = user or {}
    return _has_any(info.get("role"), "суд", "judge", "court") or _has_any(info.get("organization"), "суд", "court")


# ============================================================================
# ПОЛИЦИЯ
# ============================================================================


@router.callback_query(F.data == "police_menu")
async def police_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    if not await _can_access_police(user_id, user):
        await callback.answer("Доступ только для полиции.", show_alert=True)
        await callback.message.edit_text(
            "❌ Доступ только для сотрудников полиции и руководства государства.",
            reply_markup=get_back_button(),
            parse_mode=None,
        )
        return

    text = (
        "🚓 **ПОЛИЦИЯ: ОПЕРАТИВНЫЙ ЦЕНТР**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Розыск, аресты и оперативные расследования.\n"
        "Выберите нужный раздел:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
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
                InlineKeyboardButton(text="🕵️ ФБР", callback_data="fbi_menu"),
            ],
            [
                InlineKeyboardButton(text="📋 Судебный статус", callback_data="court_status"),
                InlineKeyboardButton(text="📻 Гос-рация", callback_data="gov_radio_menu"),
            ],
            [
                InlineKeyboardButton(text="🏦 Банк", callback_data="bank_menu"),
                InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu"),
            ],
            [InlineKeyboardButton(text="🧭 Панель организаций", callback_data="manage_organization")],
            [
                InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main"),
            ],
        ]
    )
    await state.set_state(OrganizationStates.org_menu)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "police_search_suspects")
async def police_search_suspects(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_police_search_suspects

    await feature_police_search_suspects(callback, state)


@router.callback_query(F.data == "police_my_arrests")
async def police_my_arrests(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_police_my_arrests

    await feature_police_my_arrests(callback, state)


@router.callback_query(F.data == "police_investigations")
async def police_investigations(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_police_investigations

    await feature_police_investigations(callback, state)


@router.callback_query(F.data == "police_penalty_menu")
async def police_penalty_menu(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_police_penalty_menu

    await feature_police_penalty_menu(callback, state)


# ============================================================================
# ФБР
# ============================================================================


@router.callback_query(F.data == "fbi_menu")
async def fbi_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    if not await _can_access_fbi(user_id, user):
        await callback.answer("Доступ только для ФБР.", show_alert=True)
        await callback.message.edit_text(
            "❌ Доступ только для сотрудников ФБР и руководства государства.",
            reply_markup=get_back_button(),
            parse_mode=None,
        )
        return

    text = (
        "🕵️ **ФБР: АНАЛИТИЧЕСКИЙ ЦЕНТР**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Перехват сообщений, мониторинг игроков и специальные операции."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📡 Перехват", callback_data="fbi_intercept_messages"),
                InlineKeyboardButton(text="🎯 Слежка", callback_data="fbi_track_player"),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="fbi_statistics"),
                InlineKeyboardButton(text="⚔️ Операции", callback_data="fbi_operations"),
            ],
            [
                InlineKeyboardButton(text="🛡 Санкции", callback_data="fbi_penalty_menu"),
                InlineKeyboardButton(text="🚓 Полиция", callback_data="police_search_suspects"),
            ],
            [
                InlineKeyboardButton(text="⚖️ Суд", callback_data="court_cases"),
                InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu"),
            ],
            [
                InlineKeyboardButton(text="📻 Гос-рация", callback_data="gov_radio_menu"),
                InlineKeyboardButton(text="🏦 Банк", callback_data="bank_menu"),
            ],
            [InlineKeyboardButton(text="🧭 Панель организаций", callback_data="manage_organization")],
            [
                InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main"),
            ],
        ]
    )
    await state.set_state(OrganizationStates.org_menu)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "fbi_intercept_messages")
async def fbi_intercept_messages(callback: CallbackQuery, state: FSMContext):
    # Роутер fbi_intercept подключен раньше, но оставляем fallback-переход.
    from fbi_intercept import fbi_intercept_messages as fbi_intercept_screen

    await fbi_intercept_screen(callback, state)


@router.callback_query(F.data == "fbi_statistics")
async def fbi_statistics(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    if not await _can_access_fbi(user_id, user):
        await callback.answer("Доступ только для ФБР.", show_alert=True)
        return

    feed = await db.get_fbi_global_feed(limit=120)
    by_source: dict[str, int] = {}
    for row in feed:
        src = str(row.get("source") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    lines = [
        "📊 ФБР: статистика наблюдения",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Записей в глобальной ленте: {len(feed)}",
        "",
        "Источники:",
    ]
    if not by_source:
        lines.append("• данных пока нет")
    else:
        for src, cnt in sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:8]:
            lines.append(f"• {src}: {cnt}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="fbi_statistics")],
            [InlineKeyboardButton(text="🎯 К мониторингу", callback_data="fbi_track_player")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_menu")],
        ]
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "fbi_operations")
async def fbi_operations(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_user(user_id) or {}
    if not await _can_access_fbi(user_id, user):
        await callback.answer("Доступ только для ФБР.", show_alert=True)
        return

    text = (
        "⚔️ ФБР: спецоперации\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Для запуска операции сначала выберите цель через мониторинг игрока.\n"
        "После выбора цели доступны действия: expose/scandal/arrest/freeze/blackmail."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Выбрать цель", callback_data="fbi_track_player")],
            [InlineKeyboardButton(text="📡 Лента перехвата", callback_data="fbi_intercept_messages")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="fbi_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "fbi_penalty_menu")
async def fbi_penalty_menu(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_fbi_penalty_menu

    await feature_fbi_penalty_menu(callback, state)


# ============================================================================
# СУД
# ============================================================================


@router.callback_query(F.data == "court_menu")
async def court_menu(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id) or {}
    judge = _is_judge_like(user)
    text = (
        "⚖️ СУДЕБНАЯ СИСТЕМА\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Рассмотрение дел, статистика по подсудимым и история процессов."
    )
    if judge:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📂 Дела", callback_data="court_cases"),
                    InlineKeyboardButton(text="👤 Подсудимые", callback_data="court_defendants"),
                ],
                [InlineKeyboardButton(text="📚 История", callback_data="court_history")],
                [InlineKeyboardButton(text="🧭 Панель организаций", callback_data="manage_organization")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        )
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📂 Дела в суде", callback_data="court_cases")],
                [InlineKeyboardButton(text="📋 Мой статус", callback_data="court_status")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        )
    await state.set_state(OrganizationStates.org_menu)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "court_cases")
async def court_cases(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_court_cases

    await feature_court_cases(callback, state)


@router.callback_query(F.data == "court_defendants")
async def court_defendants(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_court_defendants

    await feature_court_defendants(callback, state)


@router.callback_query(F.data == "court_history")
async def court_history(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_court_history

    await feature_court_history(callback, state)


@router.callback_query(F.data == "court_status")
async def court_status(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_court_status

    await feature_court_status(callback, state)


# ============================================================================
# БАНК И КРЕДИТЫ
# ============================================================================


@router.message(Command("loan"))
@router.callback_query(F.data == "bank_menu")
async def bank_menu(event, state: FSMContext):
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()

    user = await db.get_user(event.from_user.id) or {}
    text = (
        "🏦 **БАНКОВСКИЙ ЦЕНТР**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Наличные: ${float(user.get('balance') or 0):,.2f}\n"
        f"На счете: ${float(user.get('bank') or 0):,.2f}\n"
        f"Налоговый долг: ${float(user.get('tax_debt') or 0):,.2f}\n\n"
        "Выберите действие:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Заявка на кредит", callback_data="loan_request"),
                InlineKeyboardButton(text="💸 Операции счета", callback_data="bank_deposit"),
            ],
            [
                InlineKeyboardButton(text="📊 История банка", callback_data="bank_history"),
                InlineKeyboardButton(text="� История переводов", callback_data="transfer_history_menu"),
            ],
            [
                InlineKeyboardButton(text="📄 Мои кредиты", callback_data="loan_my_status"),
                InlineKeyboardButton(text="💸 Перевод игроку", callback_data="bank_transfer_start"),
            ],
            [
                InlineKeyboardButton(text="🏪 Бизнесы", callback_data="biz_menu"),
                InlineKeyboardButton(text="📣 Рынок", callback_data="market_menu"),
            ],
            [
                InlineKeyboardButton(text="💰 Финансы", callback_data="profile_finance"),
                InlineKeyboardButton(text="📰 Новости", callback_data="media_news_menu"),
            ],
            [InlineKeyboardButton(text="🧭 Панель организаций", callback_data="manage_organization")],
            [
                InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main"),
            ],
        ]
    )
    await state.set_state(OrganizationStates.org_menu)
    if isinstance(event, CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data == "loan_request")
async def loan_request_menu(callback: CallbackQuery, state: FSMContext):
    text = (
        "💳 ЗАЯВКА НА КРЕДИТ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Быстрые тарифы (авто-скоринг):\n"
        "• 5,000\n"
        "• 10,000\n"
        "• 20,000\n"
        "• 35,000\n\n"
        "Ставка зависит от вашего кредитного рейтинга."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$5k", callback_data="loan_apply_5000"),
                InlineKeyboardButton(text="$10k", callback_data="loan_apply_10000"),
            ],
            [
                InlineKeyboardButton(text="$20k", callback_data="loan_apply_20000"),
                InlineKeyboardButton(text="$35k", callback_data="loan_apply_35000"),
            ],
            [InlineKeyboardButton(text="📄 Мои заявки", callback_data="loan_my_status")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="bank_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data.startswith("loan_apply_"))
async def loan_apply(callback: CallbackQuery, state: FSMContext):
    raw = (callback.data or "").replace("loan_apply_", "")
    if not raw.isdigit():
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    amount = float(int(raw))
    if amount < 1_000 or amount > 50_000:
        await callback.answer("Сумма вне допустимого диапазона.", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id) or {}
    tax_debt = float(user.get("tax_debt") or 0)
    reputation = float(user.get("reputation") or 50)
    education = int(user.get("education") or 1)
    credit_score = int(max(300, min(850, 460 + reputation * 2.8 + education * 18 - min(180, tax_debt / 1200))))

    now = datetime.now()
    now_iso = now.isoformat()
    term_months = 6 if amount <= 10_000 else 9 if amount <= 20_000 else 12
    interest_rate = 0.10 if credit_score >= 700 else 0.14 if credit_score >= 620 else 0.18
    total_due = round(amount * (1 + interest_rate), 2)
    monthly_payment = round(total_due / term_months, 2)
    due_date = (now + timedelta(days=30 * term_months)).isoformat()
    approved = credit_score >= 560 and tax_debt <= 180_000
    status = "approved" if approved else "pending"

    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute(
            """
            SELECT id FROM loans
            WHERE applicant_id = ?
              AND status IN ('pending', 'approved')
            LIMIT 1
            """,
            (int(callback.from_user.id),),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            await conn.rollback()
            await callback.answer("У вас уже есть активная кредитная заявка/кредит.", show_alert=True)
            return

        await conn.execute(
            """
            INSERT INTO loans
            (applicant_id, bank_officer_id, amount, interest_rate, term_months, monthly_payment,
             purpose, status, application_date, approval_date, due_date, remaining_balance, collateral, credit_score, daily_payment, last_payment_date)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                int(callback.from_user.id),
                amount,
                interest_rate,
                term_months,
                monthly_payment,
                "Авто-кредит",
                status,
                now_iso,
                now_iso if approved else None,
                due_date,
                total_due,
                "none",
                credit_score,
                round(monthly_payment / 30.0, 2),
            ),
        )
        if approved:
            new_balance = round(float(user.get("balance") or 0) + amount, 2)
            await conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, int(callback.from_user.id)))
        await conn.commit()

    if approved:
        text = (
            "✅ Кредит одобрен.\n\n"
            f"Сумма: ${amount:,.2f}\n"
            f"Ставка: {interest_rate * 100:.1f}%\n"
            f"Срок: {term_months} мес.\n"
            f"К выплате: ${total_due:,.2f}\n"
            f"Платеж/мес: ${monthly_payment:,.2f}\n"
            f"Кредитный скор: {credit_score}"
        )
    else:
        text = (
            "🕒 Заявка отправлена на ручную проверку банка.\n\n"
            f"Сумма: ${amount:,.2f}\n"
            f"Предварительный скор: {credit_score}\n"
            "Повышайте репутацию и снижайте налоговый долг."
        )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📄 Мои заявки", callback_data="loan_my_status")],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "loan_my_status")
async def loan_my_status(callback: CallbackQuery, state: FSMContext):
    rows: list[dict] = []
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """
            SELECT *
            FROM loans
            WHERE applicant_id = ?
            ORDER BY application_date DESC
            LIMIT 10
            """,
            (int(callback.from_user.id),),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    lines = ["📄 МОИ КРЕДИТНЫЕ ЗАЯВКИ", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Заявок пока нет.")
    else:
        for row in rows:
            created = str(row.get("application_date") or "")[:16]
            status = str(row.get("status") or "pending")
            lines.append(
                f"[{created}] {status.upper()} | "
                f"${float(row.get('amount') or 0):,.0f} | "
                f"скор {int(row.get('credit_score') or 0)}"
            )
            lines.append(f"Остаток: ${float(row.get('remaining_balance') or 0):,.2f}")
            lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Новая заявка", callback_data="loan_request")],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "bank_deposit")
async def bank_deposit(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_bank_deposit

    await feature_bank_deposit(callback, state)


@router.callback_query(F.data == "bank_history")
async def bank_history(callback: CallbackQuery, state: FSMContext):
    from feature_pack import feature_bank_history

    await feature_bank_history(callback, state)


@router.callback_query(F.data == "transfer_history_menu")
async def transfer_history_menu(callback: CallbackQuery, state: FSMContext):
    """Показать историю переводов между игроками."""
    user_id = callback.from_user.id
    history = await db.get_player_transfer_history(user_id=user_id, limit=20)
    
    lines = [
        "📈 ИСТОРИЯ ПЕРЕВОДОВ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    
    if not history:
        lines.append("История переводов пуста.")
    else:
        for tx in history:
            tx_type = str(tx.get("tx_type") or "").lower()
            amount = float(tx.get("amount") or 0)
            created = str(tx.get("created_date") or "")[:16]
            note = str(tx.get("note") or "")
            
            if "transfer_out" in tx_type:
                emoji = "📤"
                direction = "Отправлено"
            elif "transfer_in" in tx_type:
                emoji = "📥"
                direction = "Получено"
            else:
                emoji = "📊"
                direction = "Операция"
            
            lines.append(f"{emoji} [{created}] {direction}: ${amount:,.2f}")
            if note:
                note_short = note[:60]
                if len(note) > 60:
                    note_short += "..."
                lines.append(f"   └─ {note_short}")
            lines.append("")
    
    # Добавляем статистику
    sent_total = sum(float(tx.get("amount") or 0) for tx in history if "transfer_out" in str(tx.get("tx_type") or ""))
    received_total = sum(float(tx.get("amount") or 0) for tx in history if "transfer_in" in str(tx.get("tx_type") or ""))
    
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        f"📤 Отправлено: ${sent_total:,.2f}",
        f"📥 Получено: ${received_total:,.2f}",
        f"📊 Баланс: ${received_total - sent_total:,.2f}",
    ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📤 Исходящие", callback_data="transfer_history_sent"),
                    InlineKeyboardButton(text="📥 Входящие", callback_data="transfer_history_received"),
                ],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "transfer_history_sent")
async def transfer_history_sent(callback: CallbackQuery, state: FSMContext):
    """Показать только исходящие переводы."""
    user_id = callback.from_user.id
    history = await db.get_player_transfer_history(user_id=user_id, limit=25, include_direction="sent")
    
    lines = [
        "📤 ИСХОДЯЩИЕ ПЕРЕВОДЫ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    
    if not history:
        lines.append("Исходящих переводов нет.")
    else:
        total_sent = 0.0
        for tx in history:
            amount = float(tx.get("amount") or 0)
            created = str(tx.get("created_date") or "")[:16]
            note = str(tx.get("note") or "")
            
            total_sent += amount
            
            # Извлекаем ID получателя из note если возможно
            recipient_info = ""
            if "Кому:" in note or "Кому:" in note:
                parts = note.split("Кому:")
                if len(parts) > 1:
                    recipient_info = parts[1].split(".")[0].strip()
            
            lines.append(f"💸 [{created}] ${amount:,.2f}")
            if note:
                note_clean = note.replace("Кому: ", "").replace("Получатель: ", "")
                note_short = note_clean[:55]
                if len(note_clean) > 55:
                    note_short += "..."
                lines.append(f"   └─ {note_short}")
            lines.append("")
        
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"Всего отправлено: ${total_sent:,.2f}",
        ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📥 Входящие", callback_data="transfer_history_received"),
                    InlineKeyboardButton(text="📊 Все", callback_data="transfer_history_menu"),
                ],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "transfer_history_received")
async def transfer_history_received(callback: CallbackQuery, state: FSMContext):
    """Показать только входящие переводы."""
    user_id = callback.from_user.id
    history = await db.get_player_transfer_history(user_id=user_id, limit=25, include_direction="received")
    
    lines = [
        "📥 ВХОДЯЩИЕ ПЕРЕВОДЫ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    
    if not history:
        lines.append("Входящих переводов нет.")
    else:
        total_received = 0.0
        for tx in history:
            amount = float(tx.get("amount") or 0)
            created = str(tx.get("created_date") or "")[:16]
            note = str(tx.get("note") or "")
            
            total_received += amount
            
            lines.append(f"💵 [{created}] ${amount:,.2f}")
            if note:
                note_clean = note.replace("От:", "").replace("Отправитель:", "")
                note_short = note_clean[:55]
                if len(note_clean) > 55:
                    note_short += "..."
                lines.append(f"   └─ {note_short}")
            lines.append("")
        
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"Всего получено: ${total_received:,.2f}",
        ])
    
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📤 Исходящие", callback_data="transfer_history_sent"),
                    InlineKeyboardButton(text="📊 Все", callback_data="transfer_history_menu"),
                ],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


async def _render_bank_transfer_picker(callback: CallbackQuery, offset: int = 0):
    page_size = 8
    safe_offset = max(0, int(offset or 0))
    total = await db.count_players(exclude_user_id=callback.from_user.id)
    if total <= 0:
        total = 0
    max_offset = max(0, ((total - 1) // page_size) * page_size) if total > 0 else 0
    if safe_offset > max_offset:
        safe_offset = max_offset

    players = await db.get_players_page(
        limit=page_size,
        offset=safe_offset,
        exclude_user_id=callback.from_user.id,
    )

    page = (safe_offset // page_size) + 1 if total > 0 else 1
    pages = ((total - 1) // page_size) + 1 if total > 0 else 1

    text_lines = [
        "💸 ПЕРЕВОД ИГРОКУ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Страница: {page}/{pages}",
        "",
        "Выберите получателя:",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if not players:
        text_lines.append("Игроков для перевода пока нет.")
    else:
        for player in players:
            player_id = int(player.get("user_id") or 0)
            if player_id <= 0:
                continue
            label = await db.get_user_public_name_by_id(player_id)
            if len(label) > 28:
                label = label[:25] + "..."
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"👤 {label}", callback_data=f"bank_transfer_pick_{player_id}_{safe_offset}")]
            )

    nav_row: list[InlineKeyboardButton] = []
    if safe_offset > 0:
        prev_offset = max(0, safe_offset - page_size)
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"bank_transfer_page_{prev_offset}"))
    if safe_offset + page_size < total:
        next_offset = safe_offset + page_size
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"bank_transfer_page_{next_offset}"))
    if nav_row:
        keyboard_rows.append(nav_row)
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")])

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode=None,
    )


@router.callback_query(F.data == "bank_transfer_start")
async def bank_transfer_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_bank_transfer_picker(callback, offset=0)
    await callback.answer()


@router.callback_query(F.data.startswith("bank_transfer_page_"))
async def bank_transfer_page(callback: CallbackQuery, state: FSMContext):
    raw = (callback.data or "").replace("bank_transfer_page_", "")
    if not raw.isdigit():
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await _render_bank_transfer_picker(callback, offset=int(raw))
    await callback.answer()


@router.callback_query(F.data.startswith("bank_transfer_pick_"))
async def bank_transfer_pick(callback: CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split("_")
    if len(parts) < 5:
        await callback.answer("Некорректный выбор игрока.", show_alert=True)
        return
    try:
        target_id = int(parts[3])
    except ValueError:
        await callback.answer("Некорректный ID игрока.", show_alert=True)
        return

    target = await db.get_user(target_id)
    if not target:
        await callback.answer("Игрок не найден.", show_alert=True)
        return

    target_name = await db.get_user_public_name_by_id(target_id)
    await state.update_data(bank_transfer_target_id=target_id, bank_transfer_target_name=target_name)
    await state.set_state(BankTransferStates.waiting_amount)
    await callback.message.answer(
        f"💵 Введите сумму перевода для {target_name}:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="bank_transfer_start")]]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.message(BankTransferStates.waiting_amount, F.text, ~F.text.startswith("/"))
async def bank_transfer_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = int(data.get("bank_transfer_target_id") or 0)
    target_name = str(data.get("bank_transfer_target_name") or f"Игрок #{target_id}")
    if target_id <= 0:
        await state.clear()
        await message.answer("Сессия перевода устарела.", parse_mode=None)
        return

    raw = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("Введите сумму числом, например: 1250")
        return

    ok, msg, details = await db.transfer_between_players(
        sender_id=message.from_user.id,
        recipient_id=target_id,
        amount=amount,
        note="Банковский перевод",
    )
    await state.clear()
    if not ok or not details:
        await message.answer(
            f"❌ {msg}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💸 Перевод игроку", callback_data="bank_transfer_start")],
                    [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
                ]
            ),
            parse_mode=None,
        )
        return

    amount_value = float(details.get("amount") or 0)
    commission_value = float(details.get("commission") or 0)
    total_debit = float(details.get("total_debit") or amount_value)
    new_balance = float(details.get("sender_balance") or 0)
    
    # Расчет баланса после операции
    final_balance = round(new_balance - total_debit, 2)
    
    confirmation_lines = [
        "✅ Перевод выполнен",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Получатель: {target_name}",
        f"Сумма перевода: ${amount_value:,.2f}",
    ]
    
    if commission_value > 0:
        confirmation_lines.append(f"Комиссия банка (2%): ${commission_value:,.2f}")
        confirmation_lines.append(f"Итого списано: ${total_debit:,.2f}")
    
    confirmation_lines.extend([
        "",
        f"Ваш новый баланс: ${final_balance:,.2f}",
    ])
    
    await message.answer(
        "\n".join(confirmation_lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💸 Новый перевод", callback_data="bank_transfer_start")],
                [InlineKeyboardButton(text="📈 История переводов", callback_data="transfer_history_menu")],
                [InlineKeyboardButton(text="🔙 В банк", callback_data="bank_menu")],
            ]
        ),
        parse_mode=None,
    )

    try:
        sender_name = await db.get_user_public_name_by_id(message.from_user.id)
        await message.bot.send_message(
            int(target_id),
            "💸 Вам поступил перевод\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"От: {sender_name}\n"
            f"Сумма: ${amount_value:,.2f}",
            parse_mode=None,
        )
    except Exception:
        pass


@router.message(BankTransferStates.waiting_amount)
async def bank_transfer_amount_invalid(message: Message):
    await message.answer("Введите сумму перевода обычным текстом.", parse_mode=None)


# ============================================================================
# БОЛЬНИЦА
# ============================================================================


@router.message(Command("med"))
@router.callback_query(F.data == "hospital_menu")
async def hospital_menu(event, state: FSMContext):
    if isinstance(event, Message):
        message = event
    else:
        message = event.message
        await event.answer()

    user = await db.get_user(event.from_user.id) or {}
    text = (
        "🏥 БОЛЬНИЦА\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Прием врача восстанавливает состояние персонажа.\n\n"
        f"Баланс: ${float(user.get('balance') or 0):,.2f}\n"
        f"Травма: {str(user.get('injury_severity') or 'нет')}\n"
        f"Состояние: {str(user.get('life_state') or 'alive')}\n\n"
        "Стоимость приема: $500"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🩺 Записаться", callback_data="hospital_appointment"),
                InlineKeyboardButton(text="📋 История", callback_data="hospital_history"),
            ],
            [InlineKeyboardButton(text="🧭 Панель организаций", callback_data="manage_organization")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    await state.set_state(OrganizationStates.org_menu)
    if isinstance(event, CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "hospital_appointment")
async def hospital_appointment(callback: CallbackQuery, state: FSMContext):
    text = (
        "🩺 ПОДТВЕРЖДЕНИЕ ПРИЕМА\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "После приема:\n"
        "• снимаются травмы\n"
        "• состояние возвращается к стабильному\n"
        "• списывается $500"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="hospital_confirm_appointment")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="hospital_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    await callback.answer()


@router.callback_query(F.data == "hospital_confirm_appointment")
async def hospital_confirm_appointment(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id) or {}
    balance = float(user.get("balance") or 0)
    price = 500.0
    if balance < price:
        await callback.answer("Недостаточно средств.", show_alert=True)
        await callback.message.edit_text(
            "❌ Недостаточно средств для приема врача.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="hospital_menu")]]
            ),
            parse_mode=None,
        )
        return

    updates = {
        "balance": round(balance - price, 2),
        "injury_severity": None,
        "in_hospital": 0,
        "hospital_until": None,
        "life_state": "alive",
    }
    await db.update_user(callback.from_user.id, **updates)
    await db.log_player_activity(
        user_id=callback.from_user.id,
        activity_type="hospital_visit",
        details="Плановый прием в больнице",
        value=-price,
    )

    await callback.message.edit_text(
        "✅ Прием завершен. Состояние восстановлено.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📋 История лечения", callback_data="hospital_history")],
                [InlineKeyboardButton(text="🔙 В больницу", callback_data="hospital_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()


@router.callback_query(F.data == "hospital_history")
async def hospital_history(callback: CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """
            SELECT activity_type, details, value, created_date
            FROM player_activity_log
            WHERE user_id = ?
              AND activity_type LIKE 'hospital%'
            ORDER BY created_date DESC
            LIMIT 12
            """,
            (int(callback.from_user.id),),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    lines = ["📋 ИСТОРИЯ ЛЕЧЕНИЯ", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Записей пока нет.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            details = str(row.get("details") or "медицинская операция")
            value = float(row.get("value") or 0)
            lines.append(f"[{created}] {details} ({value:,.2f}$)")
            lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🩺 Новый прием", callback_data="hospital_appointment")],
                [InlineKeyboardButton(text="🔙 В больницу", callback_data="hospital_menu")],
            ]
        ),
        parse_mode=None,
    )
    await callback.answer()

