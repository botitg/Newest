"""
handlers.py - Часть 1/3: Основные обработчики (главное меню, команды)
aiogram 3.x асинхронные обработчики
"""

import aiosqlite
import logging
import random
import re
from aiogram import Router, F
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import db
from states import MainStates, ElectionStates, MessageStates
from keyboards import (
    get_main_menu_keyboard,
    get_back_button,
    get_election_menu_keyboard,
    ElectionCallback,
    PartyCallback,
)
from ui_media import send_section_screen

# Создаем роутер для основных обработчиков
router = Router()
logger = logging.getLogger(__name__)
INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")
MESSAGE_PICK_PAGE_SIZE = 10


def _escape_markdown(text: str) -> str:
    value = str(text or "")
    for token in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        value = value.replace(token, f"\\{token}")
    return value


def _clean_name(value, max_len: int = 32) -> str:
    text = str(value or "")
    for token in INVISIBLE_NAME_CHARS:
        text = text.replace(token, "")
    text = " ".join(text.split()).strip()
    return text[:max_len] if max_len > 0 else text


def _display_user_name(user: dict | None, fallback_id: int | None = None) -> str:
    info = user or {}
    for key in ("nickname", "full_name"):
        text = _clean_name(info.get(key), 32)
        if text:
            return text
    username = _clean_name(info.get("username"), 32).lstrip("@")
    if username:
        return f"@{username}"
    uid = info.get("user_id") or fallback_id
    return f"Игрок #{uid}" if uid else "Неизвестный игрок"


def _gov_authority_label(authority: str | None) -> str:
    mapping = {
        "president": "Президент",
        "vice_president": "Вице-президент",
        "finance_minister": "Министр финансов",
        "minister": "Министр",
    }
    return mapping.get(str(authority or "").strip().lower(), "Нет")


def _lum(amount: float) -> str:
    return f"{float(amount or 0):,.2f} люмов"


def _parse_money_amount(raw_text: str) -> float | None:
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


def _normalize_reply_token(text: str) -> str:
    token = (text or "").strip().split(" ", 1)[0].lower()
    if token.startswith("/"):
        token = token.lstrip("/")
    if "@" in token:
        token = token.split("@", 1)[0]
    return token.strip(".,!?;:()[]{}<>\"'`«»")


def _extract_start_arg(raw_text: str | None) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _is_referral_arg(arg: str) -> bool:
    value = str(arg or "").strip().lower()
    if not value:
        return False
    if value.startswith("ref") or value.startswith("invite"):
        return True
    compact = "".join(ch for ch in value if ch.isalnum())
    return compact.isdigit()


async def _main_flag_block() -> str:
    flag = await db.get_state_flag()
    flag_text = (flag.get("state_flag_text") or "").strip()
    has_image = bool(flag.get("state_flag_file_id"))
    if flag_text:
        return f"🏳️ **Госфлаг:** {_escape_markdown(flag_text)}\n\n"
    if has_image:
        return "🏳️ **Госфлаг:** загружен президентом.\n\n"
    return ""


def _main_menu_with_flag_button(
    is_new_player: bool,
    has_elections: bool,
    election_id: int,
) -> InlineKeyboardMarkup:
    return get_main_menu_keyboard(is_new_player, has_elections, election_id)


async def _main_info_block(user_id: int) -> str:
    user = await db.get_user(user_id) or {}
    display_name = _display_user_name(user, fallback_id=user_id)
    level = int(user.get("level") or 1)
    rep = float(user.get("reputation") or 50)
    balance = float(user.get("balance") or 0)
    job = _clean_name(user.get("citizen_job"), 30) or "нет"

    news_title = ""
    news_rows = await db.get_latest_media_news(limit=1)
    if news_rows:
        news_title = _clean_name((news_rows[0] or {}).get("title"), 72)

    lines = [
        f"👤 Игрок: {_escape_markdown(display_name)}",
        f"📈 Уровень: {level} | Репутация: {rep:.1f}",
        f"💰 Баланс: ${balance:,.0f} | Работа: {_escape_markdown(job)}",
    ]
    if news_title:
        lines.append(f"📰 Последняя новость: {_escape_markdown(news_title)}")
    lines.append("")
    return "\n".join(lines)


def _nickname_required_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Установить ник", callback_data="set_nick_start")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")],
        ]
    )


def _nickname_required_text(referral_notice: str = "") -> str:
    notice = str(referral_notice or "").strip()
    prefix = f"{notice}\n\n" if notice else ""
    return (
        f"{prefix}"
        "✏️ НИК ОБЯЗАТЕЛЕН\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Без ника играть нельзя.\n"
        "Введите ник длиной 3-28 символов.\n"
        "После этого откроются все разделы игры."
    )


async def _get_tutorial_progress(user_id: int) -> dict:
    user = await db.get_user(user_id) or {}
    org_id = await db.get_user_organization_id(user_id)
    pending_job = await db.get_user_pending_job_application(user_id)
    recent_casino = await db.get_user_recent_casino_games(user_id, limit=1)

    has_pvp_or_casino_activity = bool(recent_casino)
    if not has_pvp_or_casino_activity:
        try:
            async with db._connect() as conn:
                async with conn.execute(
                    """
                    SELECT 1
                    FROM player_activity_log
                    WHERE user_id = ?
                      AND activity_type IN ('pvp_casino_win', 'pvp_casino_lose', 'casino_win')
                    ORDER BY created_date DESC
                    LIMIT 1
                    """,
                    (int(user_id),),
                ) as cursor:
                    has_pvp_or_casino_activity = await cursor.fetchone() is not None
        except Exception:
            has_pvp_or_casino_activity = bool(recent_casino)

    steps = [
        {
            "title": "Установить ник",
            "hint": "Ник обязателен. Используйте /nick или кнопку «Установить ник».",
            "done": bool(_clean_name(user.get("nickname"), 28)),
        },
        {
            "title": "Пройти быстрый тест по образованию",
            "hint": "Откройте «Обучение» -> «Быстрый тест».",
            "done": bool(str(user.get("last_education_test_at") or "").strip()),
        },
        {
            "title": "Подать заявление на работу",
            "hint": "Откройте раздел «Работа» и отправьте заявку.",
            "done": bool(pending_job) or bool(_clean_name(user.get("citizen_job"), 40)),
        },
        {
            "title": "Получить первую работу",
            "hint": "Дождитесь одобрения заявки или авто-решения HR.",
            "done": bool(_clean_name(user.get("citizen_job"), 40)),
        },
        {
            "title": "Отработать 1 смену",
            "hint": "После трудоустройства выполните первую смену.",
            "done": bool(str(user.get("last_job_shift") or "").strip()),
        },
        {
            "title": "Забрать ежедневный бонус",
            "hint": "Откройте кнопку «Ежедневный бонус» в экономике.",
            "done": bool(str(user.get("last_daily_bonus") or "").strip()),
        },
        {
            "title": "Пополнить счет в банке",
            "hint": "Зайдите в «Банк» и переведите деньги на банковский счет.",
            "done": float(user.get("bank") or 0) > 0,
        },
        {
            "title": "Вступить в организацию",
            "hint": "Откройте «Организации» и подайте заявку в любой отдел.",
            "done": bool(int(org_id or 0)),
        },
        {
            "title": "Сыграть 1 игру в казино или дуэль",
            "hint": "Попробуйте «Казино» или групповую дуэль в чате.",
            "done": bool(has_pvp_or_casino_activity),
        },
    ]

    done_count = sum(1 for step in steps if step["done"])
    total = len(steps)
    percent = int(round((done_count / total) * 100)) if total > 0 else 0
    return {
        "user": user,
        "steps": steps,
        "done_count": done_count,
        "total": total,
        "percent": percent,
    }


def _build_tutorial_text(progress: dict) -> str:
    user = progress.get("user") or {}
    done = bool(user.get("tutorial_completed"))
    done_count = int(progress.get("done_count") or 0)
    total = int(progress.get("total") or 0)
    percent = int(progress.get("percent") or 0)
    steps = progress.get("steps") or []

    lines = [
        "🎓 ОБУЧЕНИЕ И СТАРТ",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Прогресс: {done_count}/{total} ({percent}%)",
        f"Статус: {'✅ пройдено' if done else '🕒 в процессе'}",
        "",
        "Пошаговый чек-лист:",
    ]
    for idx, step in enumerate(steps, start=1):
        marker = "✅" if step.get("done") else "▫️"
        title = str(step.get("title") or "").strip()
        hint = str(step.get("hint") or "").strip()
        lines.append(f"{idx}. {marker} {title}")
        if not step.get("done") and hint:
            lines.append(f"   Подсказка: {hint}")

    next_step = next((step for step in steps if not step.get("done")), None)
    if next_step:
        lines.extend(["", f"Следующий шаг: {next_step.get('title')}"])

    lines.extend(["", "Команда для повторного открытия: /tutorial"])
    return "\n".join(lines)


def _build_tutorial_keyboard(progress: dict) -> InlineKeyboardMarkup:
    done_count = int(progress.get("done_count") or 0)
    total = int(progress.get("total") or 0)
    completed = done_count >= total and total > 0
    finish_text = "✅ Завершить обучение" if completed else f"✅ Завершить ({done_count}/{total})"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Ник", callback_data="set_nick_start")],
            [InlineKeyboardButton(text="💼 Работа", callback_data="work_menu")],
            [InlineKeyboardButton(text="🎓 Обучение", callback_data="edu_menu")],
            [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus")],
            [InlineKeyboardButton(text="🏦 Банк", callback_data="bank_menu")],
            [InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main")],
            [InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu")],
            [InlineKeyboardButton(text="🔄 Обновить прогресс", callback_data="tutorial_menu")],
            [InlineKeyboardButton(text=finish_text, callback_data="tutorial_complete")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )


SECTION_MENUS: dict[str, dict[str, object]] = {
    "state": {
        "title": "🏛️ ГОСУДАРСТВО",
        "items": [
            ("🏛️ Госорганизации", "orgs_main"),
            ("👑 Управление страной", "president_admin_panel"),
            ("📻 Гос-рация", "gov_radio_menu"),
            ("⚖️ Суд", "court_menu"),
        ],
    },
    "career": {
        "title": "💼 КАРЬЕРА",
        "items": [
            ("💼 Работа", "work_menu"),
            ("🎓 Обучение", "edu_menu"),
            ("🏢 Частные организации", "private_org_list"),
            ("🕶️ Банды", "gang_list"),
            ("👨‍👩‍👧 Семья", "family_menu"),
        ],
    },
    "economy": {
        "title": "💰 ЭКОНОМИКА",
        "items": [
            ("🏦 Банк", "bank_menu"),
            ("🏢 Компании", "biz_menu"),
            ("📈 Биржа", "stock_exchange_menu"),
            ("🏠 Недвижимость", "prop_menu"),
            ("🎟️ Промокоды", "promo_menu"),
            ("🧾 Налоги", "daily_tax_status"),
            ("🤝 Charity", "charity_menu"),
            ("📣 Городская площадка", "market_menu"),
            ("👥 Рефералы", "referral_menu"),
            ("🏗️ Застройщик", "developer_menu"),
        ],
    },
    "fun": {
        "title": "🎮 РАЗВЛЕЧЕНИЯ",
        "items": [
            ("🎪 Сюжетное событие", "fun_hub"),
            ("🎰 Казино", "casino_menu"),
            ("📰 Новости СМИ", "media_news_menu"),
            ("🤖 AI-помощник", "ai_menu"),
        ],
    },
}


GROUP_CASINO_ALIASES = {
    "кости": "dice",
    "кость": "dice",
    "кубик": "dice",
    "dice": "dice",
    "автомат": "slots3",
    "автомат3": "slots3",
    "слот": "slots3",
    "слоты": "slots3",
    "slot": "slots3",
    "slots": "slots3",
    "slot3": "slots3",
    "slots3": "slots3",
    "баскет": "basketball",
    "баскетбол": "basketball",
    "basket": "basketball",
    "basketball": "basketball",
    "рулетка": "roulette",
    "roulette": "roulette",
    "redblack": "roulette",
    "rb": "roulette",
    "red": "roulette_red",
    "black": "roulette_black",
    "красное": "roulette_red",
    "черное": "roulette_black",
    "чёрное": "roulette_black",
}

GROUP_CASINO_CFG = {
    "dice": {"title": "Кости", "emoji": "🎲", "min": 1, "max": 6},
    "slots": {"title": "Автомат x3", "emoji": "🎰", "min": 0, "max": 0},
    "slots3": {"title": "Автомат x3", "emoji": "🎰", "min": 0, "max": 0},
    "basketball": {"title": "Баскетбол", "emoji": "🏀", "min": 1, "max": 5},
    "roulette": {"title": "Red / Black", "emoji": "🎯", "min": 1, "max": 2},
}


def _parse_group_casino_command(text: str) -> tuple[str, int, float] | None:
    clean = " ".join((text or "").strip().split())
    if not clean:
        return None
    if clean.startswith("/"):
        # Поддержка команд в группах при включенном privacy mode:
        # /duel кости 6 1000
        first_parts = clean.split(" ", 1)
        command_part = first_parts[0].lstrip("/")
        if "@" in command_part:
            command_part = command_part.split("@", 1)[0]
        command = command_part.lower().strip()
        tail = first_parts[1] if len(first_parts) > 1 else ""
        if command in {"duel", "casino_duel", "pvp"}:
            clean = " ".join(tail.split()).strip()
        else:
            # Поддержка /кости 6 1000, /автомат 40 5000 и т.д.
            clean = f"{command} {tail}".strip()
            clean = " ".join(clean.split())
        if not clean:
            return None

    parts = clean.split(" ")
    if len(parts) < 2:
        return None

    first_token = parts[0].lower()
    game_alias = GROUP_CASINO_ALIASES.get(first_token)
    if not game_alias:
        return None

    game = game_alias
    target = 0
    bet_part = ""

    if game_alias == "dice":
        # Поддержка двух форм:
        #   кости [ставка]
        #   кости [число] [ставка]  (число для совместимости)
        if len(parts) >= 3:
            try:
                target = int(parts[1])
            except ValueError:
                target = 0
            bet_part = parts[2]
        else:
            bet_part = parts[1]
    elif game_alias in {"slots", "slots3"}:
        game = "slots3"
        if len(parts) >= 3:
            bet_part = parts[2]
        else:
            bet_part = parts[1]
        target = 0
    elif game_alias in {"roulette_red", "roulette_black"}:
        game = "roulette"
        target = 1 if game_alias == "roulette_red" else 2
        bet_part = parts[1] if len(parts) >= 2 else ""
    elif game_alias == "roulette":
        game = "roulette"
        if len(parts) < 3:
            return None
        color_alias = GROUP_CASINO_ALIASES.get(parts[1].lower(), "")
        if color_alias == "roulette_red":
            target = 1
        elif color_alias == "roulette_black":
            target = 2
        else:
            return None
        bet_part = parts[2]
    else:
        if len(parts) < 3:
            return None
        try:
            target = int(parts[1])
        except ValueError:
            return None
        bet_part = parts[2]

    bet_raw = re.sub(r"[^0-9.,]", "", bet_part)
    try:
        bet = float(bet_raw.replace(",", "."))
    except ValueError:
        return None
    if bet <= 0:
        return None
    return game, target, round(bet, 2)


def _tax_cycle_to_token(cycle_date: str | None) -> str:
    raw = str(cycle_date or "").strip()
    if len(raw) >= 10:
        raw = raw[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        compact = raw.replace("-", "")
        if compact.isdigit():
            return compact
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def _tax_token_to_cycle(token: str | None) -> str:
    digits = "".join(ch for ch in str(token or "") if ch.isdigit())
    if len(digits) < 8:
        return ""
    y = digits[0:4]
    m = digits[4:6]
    d = digits[6:8]
    return f"{y}-{m}-{d}"


async def _render_section_menu(callback: CallbackQuery, section: str):
    if callback.message is None:
        return
    cfg = SECTION_MENUS.get(section)
    if not cfg:
        await callback.answer("❌ Раздел не найден.", show_alert=True)
        return
    title = str(cfg.get("title") or "Раздел")
    items = list(cfg.get("items") or [])
    text_lines = [
        f"**{title}**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Выберите нужный подраздел:",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for label, target in items:
        text_lines.append(f"• {label}")
        keyboard_rows.append([InlineKeyboardButton(text=label, callback_data=f"menu:{target}")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")])
    await send_section_screen(
        callback,
        text="\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
        section_key=None,
        add_back_to_menu=False,
    )


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

    if target.startswith("menu_section_"):
        section = target.replace("menu_section_", "").strip().lower()
        await _render_section_menu(callback, section)
        return

    if target == "orgs_main":
        from handlers_part2 import organizations_menu
        await organizations_menu(callback, state)
        return

    if target == "biz_menu":
        from feature_pack import feature_business_menu
        await feature_business_menu(callback, state)
        return

    if target == "work_menu":
        from feature_pack import feature_work_menu
        await feature_work_menu(callback, state)
        return

    if target == "edu_menu":
        from feature_pack import feature_education_menu
        await feature_education_menu(callback, state)
        return

    if target == "prop_menu":
        from feature_pack import feature_property_menu
        await feature_property_menu(callback, state)
        return

    if target == "market_menu":
        from feature_pack import feature_market_menu
        await feature_market_menu(callback, state)
        return

    if target == "stock_exchange_menu":
        from feature_pack import feature_stock_exchange_menu
        await feature_stock_exchange_menu(callback, state)
        return

    if target == "referral_menu":
        from feature_pack import feature_referral_menu
        await feature_referral_menu(callback, state)
        return

    if target == "developer_menu":
        from feature_pack import feature_developer_menu
        await feature_developer_menu(callback, state)
        return

    if target == "casino_menu":
        from feature_pack import feature_casino_menu
        await feature_casino_menu(callback, state)
        return

    if target == "promo_menu":
        from feature_pack import promo_menu
        await promo_menu(callback, state)
        return

    if target == "fun_hub":
        from feature_pack import feature_fun_hub_menu
        await feature_fun_hub_menu(callback, state)
        return

    if target == "media_news_menu":
        from feature_pack import feature_media_news
        await feature_media_news(callback, state)
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

    if target == "ai_menu":
        await ai_menu(callback, state)
        return

    if target == "gov_radio_menu":
        await gov_radio_menu(callback, state)
        return

    if target == "daily_bonus":
        await daily_bonus(callback, state)
        return

    if target == "daily_tax_status":
        await daily_tax_status(callback, state)
        return

    if target == "charity_menu":
        await charity_menu(callback, state)
        return

    if target == "family_menu":
        await family_menu(callback, state)
        return

    if target == "pet_menu":
        await pet_menu(callback, state)
        return

    if target == "help_menu":
        await help_menu(callback)
        return

    if target == "tutorial_menu":
        await tutorial_menu(callback)
        return

    if target == "private_org_list":
        from feature_pack import feature_private_org_list
        await feature_private_org_list(callback, state)
        return

    if target == "gang_list":
        from feature_pack import feature_gang_menu
        await feature_gang_menu(callback, state)
        return

    await callback.answer("❌ Неизвестное действие меню.", show_alert=True)


@router.callback_query(F.data.startswith("menu:"))
async def legacy_menu_router(callback: CallbackQuery, state: FSMContext):
    """Маршрутизация старых callback кнопок menu:<action>."""
    action = (callback.data or "").split(":", 1)[1] if ":" in (callback.data or "") else ""
    await _dispatch_menu_action(callback, state, action)


@router.callback_query(F.data.startswith("menu_section_"))
async def compact_main_section_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    section = (callback.data or "").replace("menu_section_", "").strip().lower()
    await _render_section_menu(callback, section)


@router.callback_query(F.data == "state_flag_view")
async def state_flag_view(callback: CallbackQuery):
    await callback.answer()
    if callback.message is None:
        return
    flag = await db.get_state_flag()
    flag_text = " ".join(str(flag.get("state_flag_text") or "").split()).strip()
    flag_file_id = str(flag.get("state_flag_file_id") or "").strip()

    lines = [
        "🏳️ Государственный флаг Мирнастана",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if flag_text:
        lines.append(flag_text)
    else:
        lines.append("Текстовое описание флага пока не задано президентом.")
    if not flag_file_id:
        lines.append("")
        lines.append("Изображение флага пока не загружено.")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

    if flag_file_id:
        try:
            await callback.message.answer_photo(
                flag_file_id,
                caption=text,
                reply_markup=keyboard,
                parse_mode=None,
            )
            return
        except Exception:
            text += "\n\nНе удалось показать изображение, доступен текст флага."

    await callback.message.answer(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data == "tutorial_menu")
async def tutorial_menu(callback: CallbackQuery):
    """Пошаговое обучение с реальным прогрессом игрока."""
    await callback.answer()
    if callback.message is None:
        return
    progress = await _get_tutorial_progress(callback.from_user.id)
    user = progress.get("user") or {}
    if progress["done_count"] >= progress["total"] and not bool(user.get("tutorial_completed")):
        await db.update_user(callback.from_user.id, tutorial_completed=1)
        progress["user"]["tutorial_completed"] = 1
    text = _build_tutorial_text(progress)
    keyboard = _build_tutorial_keyboard(progress)
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode=None,
    )


@router.message(Command("tutorial"))
async def tutorial_command(message: Message):
    """Команда повторного открытия обучения с текущим прогрессом."""
    progress = await _get_tutorial_progress(message.from_user.id)
    user = progress.get("user") or {}
    if progress["done_count"] >= progress["total"] and not bool(user.get("tutorial_completed")):
        await db.update_user(message.from_user.id, tutorial_completed=1)
        progress["user"]["tutorial_completed"] = 1
    await message.answer(
        _build_tutorial_text(progress),
        reply_markup=_build_tutorial_keyboard(progress),
        parse_mode=None,
    )


@router.message(Command("tour"))
async def quick_tour_command(message: Message):
    """Короткий анимированный тур по ключевым механикам игры."""
    try:
        intro = await message.answer("🚀 Добро пожаловать в тур по Мирнастану...", parse_mode=None)
        await _text_animation(
            intro,
            [
                "🚀 Добро пожаловать в тур по Мирнастану...",
                "🏛️ Управляйте государством, вступайте в организации...",
                "💼 Устраивайтесь на работу и отрабатывайте смены...",
                "🎮 Развлекайтесь: казино, дуэли и события!",
            ],
            delay=0.5,
        )
    except Exception:
        pass

    lines = [
        "🏁 КРАТКИЙ ТУР ПО ИГРЕ",
        "━━━━━━━━━━━━━━━━━━━━",
        "1) Профиль: отслеживайте финансы и статус.",
        "2) Работа: подавайте заявки и отрабатывайте смены.",
        "3) Экономика: банк, кредиты, промокоды и донат-пакеты.",
        "4) Соц. механики: организации, партии, взаимодействия между игроками.",
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]])
    await send_section_screen(message, text="\n".join(lines), reply_markup=keyboard, parse_mode=None, section_key="bnr")


@router.message(Command("gift"))
async def gift_command(message: Message):
    """Подарить деньги другому игроку.

    Форматы:
    - В ответе на сообщение игрока: `/gift <сумма> [примечание]`
    - По id: `/gift <user_id> <сумма>`
    """
    parts = str(message.text or "").strip().split(maxsplit=2)
    target_id = None
    note = ""
    amount = None

    if message.reply_to_message and message.reply_to_message.from_user:
        # Формат: /gift <сумма> (в ответе на сообщение получателя)
        if len(parts) < 2:
            await message.answer("❌ Формат: /gift <сумма> (в ответе на сообщение получателя) или /gift <user_id> <сумма>", parse_mode=None)
            return
        target_id = int(message.reply_to_message.from_user.id)
        amount = _parse_money_amount(parts[1]) if len(parts) >= 2 else None
        note = parts[2].strip() if len(parts) >= 3 else ""
    else:
        # Формат: /gift <user_id> <сумма>
        if len(parts) < 3:
            await message.answer("❌ Формат: /gift <user_id> <сумма>", parse_mode=None)
            return
        if not parts[1].isdigit():
            await message.answer("❌ Укажите числовой user_id или используйте reply на сообщение игрока.", parse_mode=None)
            return
        target_id = int(parts[1])
        amount = _parse_money_amount(parts[2])

    if amount is None:
        await message.answer("❌ Неверная сумма.", parse_mode=None)
        return
    if target_id == message.from_user.id:
        await message.answer("❌ Нельзя дарить самому себе.", parse_mode=None)
        return

    # Используем запись взаимодействия, чтобы корректно логировать и изменять балансы
    ok, msg, payload = await db.record_player_interaction(
        actor_id=message.from_user.id,
        target_id=target_id,
        action_key="gift",
        action_title="Подарок",
        public_text=str(note or "")[:500],
        cost=amount,
        target_reward=amount,
        actor_reputation_delta=0.0,
        target_reputation_delta=0.0,
        target_happiness_delta=2.0,
    )

    if not ok:
        await message.answer(f"❌ {msg}", parse_mode=None)
        return

    await message.answer(f"✅ Подарок отправлен игроку {target_id}: ${amount:,.2f}\n{msg}", parse_mode=None)
    try:
        await message.bot.send_message(target_id, f"🎁 Вам прислали подарок ${amount:,.2f} от игрока {message.from_user.id}.\n{note}", parse_mode=None)
    except Exception:
        pass


@router.callback_query(F.data == "tutorial_complete")
async def tutorial_complete(callback: CallbackQuery):
    """Завершение обучения только после прохождения всех шагов."""
    if callback.message is None:
        await callback.answer("Сообщение обучения не найдено. Откройте /tutorial.", show_alert=True)
        return
    progress = await _get_tutorial_progress(callback.from_user.id)
    done_count = int(progress.get("done_count") or 0)
    total = int(progress.get("total") or 0)

    if done_count < total:
        await callback.answer(
            f"Сначала закройте все шаги обучения ({done_count}/{total}).",
            show_alert=True,
        )
        if callback.message:
            await callback.message.edit_text(
                _build_tutorial_text(progress),
                reply_markup=_build_tutorial_keyboard(progress),
                parse_mode=None,
            )
        return

    await db.update_user(callback.from_user.id, tutorial_completed=1)
    await callback.answer("Обучение завершено.")
    await callback.message.edit_text(
        "✅ Обучение завершено.\n\n"
        "Вы прошли все стартовые шаги. Теперь доступны все базовые механики.",
        reply_markup=get_back_button(callback="back_to_main"),
        parse_mode=None,
    )


@router.callback_query(F.data == "private_org_list")
async def private_org_menu_proxy(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий раздел частных организаций."""
    from feature_pack import feature_private_org_list
    await feature_private_org_list(callback, state)


@router.callback_query(F.data == "gang_list")
async def gang_menu_proxy(callback: CallbackQuery, state: FSMContext):
    """Прокси на рабочий раздел банд."""
    from feature_pack import feature_gang_menu
    await feature_gang_menu(callback, state)


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
        has_elections = False
        election_id = -1

        if not has_president:
            await db.ensure_presidential_election(duration_hours=15)
            active_pres = await db.get_active_presidential_election()
            has_elections = active_pres is not None
            if active_pres:
                election_id = active_pres['id']
        
        # При активных выборах главное меню недоступно: возвращаем в меню выборов.
        current_state = await state.get_state()
        if has_elections:
            await state.set_state(ElectionStates.global_lock)
            try:
                await callback.message.edit_text(
                    "🗳️ **ПЕРЕХОД В МЕНЮ ВЫБОРОВ**",
                    reply_markup=get_election_menu_keyboard(election_id),
                    parse_mode='Markdown'
                )
                return
            except Exception:
                # если не получилось отредактировать, отправляем новое сообщение
                await callback.message.answer(
                    "🗳️ **Меню выборов**",
                    reply_markup=get_election_menu_keyboard(election_id)
                )
                return

        # Если выборы уже завершены, но пользователь остался в election-state — сбрасываем его.
        if current_state and current_state.startswith("ElectionStates"):
            await state.clear()

        await state.set_state(MainStates.main_menu)
        flag_block = await _main_flag_block()
        info_block = await _main_info_block(callback.from_user.id)

        text = (
            "🏛️ **Государство Онлайн**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{flag_block}"
            f"{info_block}"
            "Выберите категорию:\n"
        )
        flag = await db.get_state_flag()
        await send_section_screen(
            callback,
            text=text,
            reply_markup=_main_menu_with_flag_button(is_new, has_elections, election_id),
            parse_mode="Markdown",
            flag_file_id=str(flag.get("state_flag_file_id") or ""),
        )
    except Exception:
        # Если edit_text не сработал, отправляем новое сообщение
        try:
            flag = await db.get_state_flag()
            await send_section_screen(
                callback,
                text=(
                    "🏛️ **Государство Онлайн**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Добро пожаловать! Выберите категорию:"
                ),
                reply_markup=_main_menu_with_flag_button(False, False, -1),
                parse_mode="Markdown",
                flag_file_id=str(flag.get("state_flag_file_id") or ""),
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

    start_arg = _extract_start_arg(message.text)
    referral_notice = ""
    if _is_referral_arg(start_arg):
        ref_ok, ref_msg, _ = await db.apply_referral_code(message.from_user.id, start_arg)
        if ref_ok:
            referral_notice = f"🎁 {ref_msg}\n\n"
            user = await db.get_user(message.from_user.id) or user

    if not _clean_name(user.get("nickname"), 28):
        await state.set_state(MainStates.setting_nickname)
        await message.answer(
            _nickname_required_text(referral_notice),
            reply_markup=_nickname_required_keyboard(),
            parse_mode=None,
        )
        return
    
    # Проверяем, прошел ли пользователь обучение
    is_new = not user.get('tutorial_completed')
    
    # Проверяем, есть ли активные выборы и нет ли президента
    has_president = await db.check_has_president()
    has_elections = False

    if not has_president:
        await db.ensure_presidential_election(duration_hours=15)
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
            f"{referral_notice}"
            "Выберите действие:",
            reply_markup=get_election_menu_keyboard(active_pres['id']) if active_pres else get_back_button()
        )
    else:
        # Нормальное начало
        await state.set_state(MainStates.main_menu)
        flag_block = await _main_flag_block()
        info_block = await _main_info_block(message.from_user.id)

        greeting = (
            "🏛️ **Государство Онлайн**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{flag_block}"
            f"{info_block}"
        )
        
        if is_new:
            greeting = (
                "👋 **Добро пожаловать, новичок!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Чтобы быстро разобраться в игре, рекомендуем пройти обучение.\n"
                "Вы получите начальный капитал и поймете, как всё работает.\n\n"
            ) + greeting
        
        greeting += (
            "Категории главного меню:\n"
            "• 🎮 Развлечения\n"
            "• 💼 Карьера\n"
            "• 💰 Экономика\n"
            "• 🏛️ Государство\n\n"
            "Для старта: откройте 🎓 Обучение.\n\n"
            f"{referral_notice}"
            "Выберите категорию:"
        )
        
        flag = await db.get_state_flag()
        await send_section_screen(
            message,
            text=greeting,
            reply_markup=_main_menu_with_flag_button(is_new, has_elections, -1),
            parse_mode="Markdown",
            flag_file_id=str(flag.get("state_flag_file_id") or ""),
        )


@router.message(Command("menu"))
async def menu_command(message: Message, state: FSMContext):
    """Быстрый переход в актуальное главное меню."""
    user = await db.create_or_update_user(
        message.from_user.id,
        message.from_user.username or "",
        f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip(),
    )

    has_president = await db.check_has_president()
    has_elections = False
    election_id = -1
    if not has_president:
        await db.ensure_presidential_election(duration_hours=15)
        active_pres = await db.get_active_presidential_election()
        has_elections = active_pres is not None
        if active_pres:
            election_id = int(active_pres.get("id") or -1)

    if has_elections and election_id > 0:
        await state.set_state(ElectionStates.global_lock)
        await message.answer(
            "🗳️ **ПРЕЗИДЕНТСКИЕ ВЫБОРЫ АКТИВНЫ**\n\n"
            "Главное меню временно ограничено. Используйте меню выборов:",
            reply_markup=get_election_menu_keyboard(election_id),
            parse_mode="Markdown",
        )
        return

    await state.set_state(MainStates.main_menu)
    flag_block = await _main_flag_block()
    info_block = await _main_info_block(message.from_user.id)
    text = (
        "🏛️ **Государство Онлайн**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{flag_block}"
        f"{info_block}"
        "Выберите категорию:"
    )
    flag = await db.get_state_flag()
    await send_section_screen(
        message,
        text=text,
        reply_markup=_main_menu_with_flag_button(not bool(user.get("tutorial_completed")), False, -1),
        parse_mode="Markdown",
        flag_file_id=str(flag.get("state_flag_file_id") or ""),
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
        "/nick — установить персональный ник\n"
        "/ai — AI-ассистент и рекомендации\n"
        "/radio — гос-рация (правительство/ФБР)\n"
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
        "/tax — ежедневные налоги\n"
        "/charity — пожертвования в городской фонд\n"
        "/daily — бонус дня\n\n"
        
        "⚖️ **ПРАВОСУДИЕ:**\n"
        "/court — суд и судебные дела\n"
        "/police — меню полиции\n\n"
        
        "🏥 **ЗДОРОВЬЕ:**\n"
        "/med — лечение в больнице\n\n"
        
        "🏠 **ИМУЩЕСТВО:**\n"
        "/prop — недвижимость\n"
        "/gang — банды и криминал\n\n"

        "👨‍👩‍👧 **СЕМЬЯ И ПИТОМЦЫ:**\n"
        "/marry — предложение брака (reply в группе)\n"
        "/divorce — развод (добавьте 'тихо' для скрытого режима)\n"
        "/family — семейная панель\n"
        "/pet — управление питомцем\n"
        "/petname Имя — переименовать питомца\n\n"
        
        "📣 **ПОЛИТИКА:**\n"
        "/government — система правления\n"
        "/protest — митинги и восстания\n"
        "/revolution — революции\n\n"
        
        "📝 **ДРУГОЕ:**\n"
        "/market — городская площадка\n"
        "/stocks — акции и биржа\n"
        "/ref — реферальная система и маркетинг\n"
        "/builder — проекты застройщика\n"
        "/casino — одиночное казино\n"
        "/donate — донат и поддержка проекта\n"
        "/promo — промокоды и бонусы\n"
        "В группе (reply): кости 1000 | автомат 5000 | рулетка red 2000 | баскетбол 4 2000\n"
        "Для костей правило: у кого больше выпало, тот победил.\n"
        "Для автомата: тройка > пара > разные.\n"
        "Комиссия групповой дуэли: 1% с выигрыша.\n"
        "Семейные reply-команды (без privacy mode): брак | обнять | поцеловать | погладить\n"
        "+ (reply) — +1 репутация\n"
        "Если privacy mode включен: используйте /marry и /duel кости 6 1000 (reply)\n"
        "/id — узнать ID игрока (reply на сообщение)\n\n"
        
        "ℹ️ **ИНФОРМАЦИЯ:**\n"
        "В группах при privacy mode бот видит только команды.\n"
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
        "• Торговать акциями на бирже\n\n"
        
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

        "🤖 **AI-ПОМОЩНИК:**\n"
        "• Персональные рекомендации по развитию\n"
        "• AI-миссии с наградой и опытом\n"
        "• Быстрая городская сводка событий\n\n"

        "📡 **ГОС-РАЦИЯ:**\n"
        "• Эфир правительства для объявлений\n"
        "• ФБР имеет доступ к прослушиванию\n"
        "• Любой гражданин может отправить обращение президенту\n"
        "• Если есть вице-президент, обращение сначала идет ему\n"
        "• Команда: /radio\n\n"

        "🎮 **PVP-КАЗИНО В ГРУППЕ:**\n"
        "• Ответьте на сообщение игрока и напишите:\n"
        "  кости [число] [ставка]\n"
        "  автомат [число] [ставка]\n"
        "  баскетбол [число] [ставка]\n"
        "• Для костей: оба бросают, у кого число больше — тот выигрывает\n"
        "• Для автомата/баскетбола: если выпало выбранное число — выигрывает инициатор\n"
        "• Иначе выигрывает соперник\n\n"
        "• Комиссия дуэли: 1% с выигрыша\n\n"
        
        "⚠️ **ВАЖНО:**\n"
        "• Все ваши действия влияют на репутацию\n"
        "• Налоги и долги отслеживаются автоматически\n"
        "• Президент имеет полную власть над системой\n\n"
        
        "💡 **СОВЕТ:**\n"
        "Начните с малого - устройтесь на работу в государстве "
        "или в бизнес, получайте опыт и развивайте свой персонаж!"
    )
    
    await callback.message.edit_text(
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
            f"👤 **{_escape_markdown(_display_user_name(user, fallback_id=message.from_user.id))}**\n"
            f"Ваш ID: `{message.from_user.id}`",
            parse_mode='Markdown'
        )


# ==================== РЕПУТАЦИЯ ПО ПЛЮСАМ ====================

def _humanize_minutes(total_minutes: int) -> str:
    safe_total = max(0, int(total_minutes or 0))
    hours, minutes = divmod(safe_total, 60)
    if hours and minutes:
        return f"{hours}ч {minutes}м"
    if hours:
        return f"{hours}ч"
    return f"{minutes}м"


async def _apply_plus_reputation(message: Message):
    """
    Выдать репутацию по reply-команде: "+" или /plus.
    """
    try:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply("❌ Ответьте на сообщение игрока.", parse_mode=None)
            return

        target_tg_user = message.reply_to_message.from_user
        target_user_id = int(target_tg_user.id)

        if target_tg_user.is_bot:
            await message.reply("❌ Нельзя выдавать репутацию боту.", parse_mode=None)
            return
        if int(message.from_user.id) == target_user_id:
            await message.reply("❌ Нельзя выдавать репутацию самому себе.", parse_mode=None)
            return

        # Цель может не иметь профиля, если еще не писала боту в ЛС.
        await db.create_or_update_user(
            target_user_id,
            target_tg_user.username or "",
            f"{target_tg_user.first_name or ''} {target_tg_user.last_name or ''}".strip(),
        )
        target_user = await db.get_user(target_user_id) or {}

        cooldown_key = f"reputation_plus_{target_user_id}"
        ok, remain = await db.check_and_set_user_cooldown(int(message.from_user.id), cooldown_key, 1440)
        if not ok:
            await message.reply(
                "⏳ Этому игроку уже ставили + сегодня.\n"
                f"Попробуйте через {_humanize_minutes(remain)}.",
                parse_mode=None,
            )
            return

        current_rep = float(target_user.get("reputation", 50) or 50)
        new_rep = round(min(100.0, current_rep + 1.0), 2)
        await db.update_user(target_user_id, reputation=new_rep)

        target_name = _display_user_name(target_user, fallback_id=target_user_id)
        await message.reply(
            f"✅ {target_name}: +1 репутации (теперь {new_rep:.1f}/100).",
            parse_mode=None,
        )
    except Exception:
        logger.exception(
            "Ошибка выдачи репутации по reply-команде: actor=%s chat=%s",
            int((message.from_user.id if message.from_user else 0) or 0),
            int((message.chat.id if message.chat else 0) or 0),
        )
        await message.reply("⚠️ Не удалось выдать репутацию. Попробуйте еще раз.", parse_mode=None)


@router.message(F.text.regexp(r"^\s*\+\s*$"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
@router.message(F.text.regexp(r"(?iu)^\s*плюс\s*[.!?]?\s*$"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
async def plus_reputation(message: Message):
    await _apply_plus_reputation(message)


@router.message(Command("plus", "rep"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
async def plus_reputation_command(message: Message):
    await _apply_plus_reputation(message)


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
        message = callback.message
        if message is None:
            await callback.answer("❌ Сообщение недоступно.", show_alert=True)
            return
        # Небольшая анимация загрузки профиля
        try:
            await _text_animation(
                message,
                ["👤 Загружаю профиль...", "🔎 Собираю данные...", "📋 Готово!"],
                delay=0.18,
            )
        except Exception:
            pass
    
    if not user:
        await message.answer("❌ Профиль не найден")
        return
    
    org = await db.get_organization(user.get('organization')) if user.get('organization') else None
    authority = await db.get_government_authority(int(user.get("user_id") or 0))
    display_name = _display_user_name(user, fallback_id=int(user.get("user_id") or 0))
    nickname = _clean_name(user.get("nickname"), 28) or "не задан"
    username = _clean_name(user.get("username"), 40).lstrip("@") or "not_set"
    org_name = _clean_name((org or {}).get("name"), 60) if org else ""
    role_name = _clean_name(user.get("role"), 60) or "Гражданин"
    citizen_job = _clean_name(user.get("citizen_job"), 60) or "нет"
    life_state = _clean_name(user.get("life_state"), 24) or "alive"
    injury = _clean_name(user.get("injury_severity"), 24) or "нет"
    family = await db.get_active_marriage(int(user.get("user_id") or 0))
    family_account = await db.get_family_account(int(user.get("user_id") or 0))
    pet = await db.get_user_pet(int(user.get("user_id") or 0))
    balance = float(user.get("balance", 0) or 0)
    bank_balance = float(user.get("bank", 0) or 0)
    cash_balance = float(user.get("cash", 0) or 0)
    shadow_balance = float(user.get("shadow_balance", 0) or 0)
    net_worth = balance + bank_balance + cash_balance + shadow_balance
    last_activity = str(user.get("last_activity") or "—")[:16]

    profile_text = (
        f"👤 **{_escape_markdown(display_name)}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 **ID:** {int(user.get('user_id') or 0)}\n"
        f"🎭 **Ник:** {_escape_markdown(nickname)}\n"
        f"📱 **Username:** @{_escape_markdown(username)}\n"
        f"🕒 **Активность:** {_escape_markdown(last_activity)}\n"
        f"🏛️ **Гос.полномочия:** {_escape_markdown(_gov_authority_label(authority))}\n\n"
        "💰 **ФИНАНСЫ:**\n"
        f"• Баланс: {_lum(balance)}\n"
        f"• Банк: {_lum(bank_balance)}\n"
        f"• Наличные: {_lum(cash_balance)}\n"
        f"• Теневой баланс: {_lum(shadow_balance)}\n"
        f"• Капитал: {_lum(net_worth)}\n"
        f"• Налоговый долг: {_lum(float(user.get('tax_debt', 0) or 0))}\n"
        f"• Всего налогов начислено: {_lum(await db.get_user_total_tax_charged(int(user.get('user_id') or 0)))}\n"
        f"• Всего налогов оплачено: {_lum(await db.get_user_total_tax_paid(int(user.get('user_id') or 0)))}\n\n"
        "📊 **СТАТИСТИКА:**\n"
        f"• Уровень: {int(user.get('level', 1) or 1)}\n"
        f"• Образование: {int(user.get('education', 1) or 1)}\n"
        f"• Опыт: {int(user.get('experience', 0) or 0)}\n"
        f"• Репутация: {float(user.get('reputation', 50) or 50):.1f}/100\n"
        f"• Коррупционный риск: {int(user.get('corruption_score', 0) or 0)}/100\n\n"
        "💼 **ЗАНЯТОСТЬ:**\n"
    )

    if org:
        profile_text += (
            f"• Организация: {_escape_markdown(org_name)}\n"
            f"• Должность: {_escape_markdown(role_name)}\n"
            f"• Зарплата: {_lum(float(user.get('salary', 0) or 0))}/час\n\n"
        )
    else:
        profile_text += "• Не состоит в организации\n\n"

    profile_text += (
        "👨‍💼 **ГРАЖДАНСКАЯ РАБОТА:**\n"
        f"• Должность: {_escape_markdown(citizen_job)}\n"
        f"• Зарплата: {_lum(float(user.get('citizen_salary', 0) or 0))}/час\n\n"
        "🏥 **ЗДОРОВЬЕ:**\n"
        f"• Состояние: {_escape_markdown(life_state)}\n"
        f"• Травма: {_escape_markdown(injury)}\n"
    )

    if family:
        spouse_id = int(family.get("spouse_id") or 0)
        spouse_name = _display_user_name(await db.get_user(spouse_id), fallback_id=spouse_id)
        relation_level = int(family.get("relationship_level") or 1)
        relation_points = int(family.get("relationship_points") or 0)
        profile_text += (
            "\n👨‍👩‍👧 **СЕМЬЯ:**\n"
            f"• Статус: в браке с {_escape_markdown(spouse_name)}\n"
            f"• Вместе: {int(family.get('days_together') or 0)} дн.\n"
            f"• Уровень отношений: {relation_level}/25 ({relation_points} очк.)\n"
            f"• Семейный долг: {_lum(float(family_account.get('family_debt') or 0))}\n"
        )
    else:
        profile_text += "\n👨‍👩‍👧 **СЕМЬЯ:**\n• Статус: не в браке\n"
    if pet:
        pet_title = PET_TYPE_LABELS.get(str(pet.get("pet_type") or "").lower(), "Питомец")
        profile_text += (
            f"• Питомец: {_escape_markdown(pet_title)} "
            f"'{_escape_markdown(str(pet.get('pet_name') or ''))}' "
            f"(ур. {int(pet.get('level') or 1)})\n"
        )
    else:
        profile_text += "• Питомец: нет\n"

    keyboard = [
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="profile_finance"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="profile_stats"),
        ],
        [
            InlineKeyboardButton(text="🎁 Подарить", callback_data="bank_transfer_start"),
        ],
        [
            InlineKeyboardButton(text="💌 Письма", callback_data="profile_messages"),
            InlineKeyboardButton(text="✏️ Ник", callback_data="set_nick_start"),
        ],
        [
            InlineKeyboardButton(text="🤝 Взаимодействия", callback_data="profile_interactions"),
        ],
        [InlineKeyboardButton(text="👨‍👩‍👧 Семья", callback_data="family_menu")],
        [
            InlineKeyboardButton(text="🤖 AI-помощник", callback_data="ai_menu"),
            InlineKeyboardButton(text="📡 Гос-рация", callback_data="gov_radio_menu"),
        ],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await send_section_screen(
        update,
        text=profile_text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
        section_key="profile",
    )


@router.callback_query(F.data == "profile_finance")
async def profile_finance(callback: CallbackQuery):
    """Детализация финансов пользователя."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ Профиль не найден.", reply_markup=get_back_button(callback="back_to_main"))
        return

    total_tax_charged = await db.get_user_total_tax_charged(callback.from_user.id)
    total_tax_paid = await db.get_user_total_tax_paid(callback.from_user.id)
    text = (
        "💰 **ФИНАНСОВЫЙ ОТЧЕТ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Баланс: {_lum(float(user.get('balance', 0) or 0))}\n"
        f"• Налоговый долг: {_lum(float(user.get('tax_debt', 0) or 0))}\n"
        f"• Всего налогов начислено: {_lum(total_tax_charged)}\n"
        f"• Всего налогов оплачено: {_lum(total_tax_paid)}\n"
        f"• Штрафы оплачены: {_lum(float(user.get('fines_paid', 0) or 0))}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
    ])
    await send_section_screen(
        callback,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
        section_key="profile",
    )


@router.callback_query(F.data == "profile_interactions")
async def profile_interactions(callback: CallbackQuery):
    """Показать недавние взаимодействия игрока (последние 10)."""
    await callback.answer()
    user_id = callback.from_user.id
    rows = await db.get_recent_player_interactions(user_id=user_id, limit=12)
    if not rows:
        await callback.message.edit_text(
            "🤝 Взаимодействий пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В профиль", callback_data="profile_menu")]]),
            parse_mode=None,
        )
        return

    lines = ["🤝 **ПОСЛЕДНИЕ ВЗАИМОДЕЙСТВИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    for r in rows[:12]:
        created = str(r.get("created_date") or "")[:16]
        actor = str(r.get("actor_name") or r.get("actor_id") or "?")
        target = str(r.get("target_name") or r.get("target_id") or "?")
        title = str(r.get("action_title") or "Действие")
        value = float(r.get("value") or 0)
        lines.append(f"• {created} | {title}: {actor} → {target} | ${value:,.2f}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
    ])
    await send_section_screen(
        callback,
        text="\n".join(lines),
        reply_markup=keyboard,
        parse_mode="Markdown",
        section_key="profile",
    )


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
        [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
    ])
    await send_section_screen(
        callback,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
        section_key="profile",
    )


@router.callback_query(F.data == "profile_messages")
async def profile_messages(callback: CallbackQuery):
    """Центр личных сообщений."""
    await callback.answer()
    user_id = callback.from_user.id

    query = """
        SELECT m.id,
               m.sender_id,
               m.recipient_id,
               m.subject,
               m.content,
               m.created_date,
               m.read_date,
               COALESCE(NULLIF(su.nickname, ''), NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(m.sender_id AS TEXT)) AS sender_name,
               COALESCE(NULLIF(ru.nickname, ''), NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(m.recipient_id AS TEXT)) AS recipient_name
        FROM messages m
        LEFT JOIN users su ON su.user_id = m.sender_id
        LEFT JOIN users ru ON ru.user_id = m.recipient_id
        WHERE (m.sender_id = ? AND COALESCE(m.deleted_by_sender, 0) = 0)
           OR (m.recipient_id = ? AND COALESCE(m.deleted_by_recipient, 0) = 0)
        ORDER BY m.created_date DESC
        LIMIT 12
    """
    unread_query = """
        SELECT COUNT(*)
        FROM messages
        WHERE recipient_id = ?
          AND read_date IS NULL
          AND COALESCE(deleted_by_recipient, 0) = 0
    """

    rows = []
    unread = 0
    try:
        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, (int(user_id), int(user_id))) as cur:
                rows = await cur.fetchall()
            async with conn.execute(unread_query, (int(user_id),)) as cur:
                unread_row = await cur.fetchone()
                unread = int((unread_row[0] if unread_row else 0) or 0)
    except Exception:
        rows = []
        unread = 0

    lines = [
        "💌 **ЛИЧНЫЕ СООБЩЕНИЯ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Непрочитанных: {unread}",
        "",
    ]
    if not rows:
        lines.append("Диалогов пока нет.")
    else:
        for row in rows:
            incoming = int(row["recipient_id"] or 0) == int(user_id)
            icon = "📥" if incoming else "📤"
            peer_name = _clean_name(row["sender_name"] if incoming else row["recipient_name"], 36) or "Игрок"
            created = str(row["created_date"] or "")[:16]
            subject = str(row["subject"] or "Без темы")
            content = str(row["content"] or "")
            if len(content) > 72:
                content = content[:69] + "..."
            unread_mark = " • NEW" if incoming and not row["read_date"] else ""
            lines.append(f"{icon} [{created}] {peer_name}{unread_mark}")
            lines.append(f"Тема: {_escape_markdown(subject)}")
            if content:
                lines.append(_escape_markdown(content))
            lines.append("")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать письмо", callback_data="msg_compose_start")],
        [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
    ])
    await send_section_screen(
        callback,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
        section_key="pismo",
    )


async def _render_message_recipient_picker(callback: CallbackQuery, offset: int = 0) -> None:
    safe_offset = max(0, int(offset or 0))
    user_id = callback.from_user.id
    total = await db.count_players(exclude_user_id=user_id)
    players = await db.get_players_page(
        limit=MESSAGE_PICK_PAGE_SIZE,
        offset=safe_offset,
        exclude_user_id=user_id,
    )
    page = (safe_offset // MESSAGE_PICK_PAGE_SIZE) + 1
    pages = max(1, (total + MESSAGE_PICK_PAGE_SIZE - 1) // MESSAGE_PICK_PAGE_SIZE)
    lines = [
        "✉️ **НОВОЕ ПИСЬМО**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "Выберите получателя:",
        f"Страница: {page}/{pages}",
        "",
    ]
    if not players:
        lines.append("Нет доступных игроков.")
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for player in players:
        target_id = int(player.get("user_id") or 0)
        if target_id <= 0:
            continue
        name = _display_user_name(player, fallback_id=target_id)
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"👤 {name}", callback_data=f"msg_pick_{target_id}")]
        )

    nav_row: list[InlineKeyboardButton] = []
    if safe_offset > 0:
        prev_offset = max(0, safe_offset - MESSAGE_PICK_PAGE_SIZE)
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"msg_compose_page_{prev_offset}"))
    if safe_offset + MESSAGE_PICK_PAGE_SIZE < total:
        next_offset = safe_offset + MESSAGE_PICK_PAGE_SIZE
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"msg_compose_page_{next_offset}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton(text="🔙 К письмам", callback_data="profile_messages")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "msg_compose_start")
@router.callback_query(F.data.startswith("msg_compose_page_"))
async def message_compose_start(callback: CallbackQuery, state: FSMContext):
    """Открыть список игроков для отправки личного письма."""
    await callback.answer()
    offset = 0
    if (callback.data or "").startswith("msg_compose_page_"):
        raw = (callback.data or "").replace("msg_compose_page_", "")
        if raw.isdigit():
            offset = int(raw)
    await state.set_state(MessageStates.message_recipient)
    await state.update_data(msg_compose_offset=offset)
    await _render_message_recipient_picker(callback, offset=offset)


@router.callback_query(F.data.startswith("msg_pick_"))
async def message_compose_pick_recipient(callback: CallbackQuery, state: FSMContext):
    """Выбрать получателя и перейти к вводу темы письма."""
    await callback.answer()
    raw = (callback.data or "").replace("msg_pick_", "")
    if not raw.isdigit():
        await callback.answer("❌ Некорректный получатель.", show_alert=True)
        return
    recipient_id = int(raw)
    if recipient_id == callback.from_user.id:
        await callback.answer("❌ Нельзя отправить письмо самому себе.", show_alert=True)
        return
    recipient = await db.get_user(recipient_id)
    if not recipient:
        await callback.answer("❌ Получатель не найден.", show_alert=True)
        return

    recipient_name = _display_user_name(recipient, fallback_id=recipient_id)
    await state.set_state(MessageStates.message_subject)
    await state.update_data(msg_recipient_id=recipient_id, msg_recipient_name=recipient_name)

    text = (
        "✉️ **НОВОЕ ПИСЬМО**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Получатель: {_escape_markdown(recipient_name)}\n\n"
        "Введите тему письма (до 120 символов).\n"
        "Если тема не нужна, отправьте `-`"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👥 Выбрать другого", callback_data="msg_compose_start")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="msg_cancel_compose")],
            ]
        ),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "msg_cancel_compose")
async def message_compose_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменить отправку письма и вернуться в центр сообщений."""
    await state.set_state(MainStates.main_menu)
    await profile_messages(callback)


@router.message(MessageStates.message_subject, F.text, ~F.text.startswith("/"))
async def message_compose_subject_input(message: Message, state: FSMContext):
    """Сохранить тему письма и перейти к вводу текста."""
    data = await state.get_data()
    recipient_name = _display_user_name(
        {"nickname": data.get("msg_recipient_name")},
        fallback_id=int(data.get("msg_recipient_id") or 0),
    )
    raw_subject = " ".join((message.text or "").strip().split())
    subject = "Без темы" if raw_subject in {"", "-"} else raw_subject[:120]

    await state.set_state(MessageStates.message_content)
    await state.update_data(msg_subject=subject)
    await message.answer(
        "📝 Введите текст письма (до 2500 символов):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="msg_cancel_compose")],
                [InlineKeyboardButton(text="👤 Получатель", callback_data="msg_compose_start")],
            ]
        ),
        parse_mode=None,
    )
    await message.answer(
        f"Получатель: {recipient_name}\nТема: {subject}",
        parse_mode=None,
    )


@router.message(MessageStates.message_content, F.text, ~F.text.startswith("/"))
async def message_compose_content_input(message: Message, state: FSMContext):
    """Отправить письмо выбранному игроку."""
    data = await state.get_data()
    recipient_id = int(data.get("msg_recipient_id") or 0)
    subject = str(data.get("msg_subject") or "Без темы")
    content = " ".join((message.text or "").strip().split())[:2500]
    if recipient_id <= 0:
        await state.set_state(MainStates.main_menu)
        await message.answer("❌ Сессия отправки письма устарела.", parse_mode=None)
        return
    if not content:
        await message.answer("❌ Письмо пустое. Введите текст.", parse_mode=None)
        return

    ok, db_msg, _ = await db.send_private_message(
        sender_id=message.from_user.id,
        recipient_id=recipient_id,
        subject=subject,
        content=content,
        message_type="private",
    )
    if not ok:
        await message.answer(f"❌ {db_msg}", parse_mode=None)
        return

    sender_name = await db.get_user_public_name_by_id(message.from_user.id)
    notify_text = (
        f"💌 Вам пришло новое письмо от {sender_name}.\n"
        f"Тема: {subject}\n"
        "Откройте Профиль -> Письма."
    )
    await _notify_user_safe(message.bot, recipient_id, notify_text)
    await db.log_player_activity(
        user_id=message.from_user.id,
        activity_type="private_message_send",
        details=f"Письмо игроку #{recipient_id}",
        value=0,
    )

    await state.set_state(MainStates.main_menu)
    await message.answer(
        "✅ Письмо отправлено.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💌 К письмам", callback_data="profile_messages")],
                [InlineKeyboardButton(text="👤 В профиль", callback_data="profile_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.message(MessageStates.message_subject)
async def message_compose_subject_invalid(message: Message):
    await message.answer("❌ Введите тему обычным текстом.", parse_mode=None)


@router.message(MessageStates.message_content)
async def message_compose_content_invalid(message: Message):
    await message.answer("❌ Введите текст письма обычным сообщением.", parse_mode=None)


@router.callback_query(F.data == "set_nick_start")
@router.message(Command("nick"))
async def set_nick_start(update, state: FSMContext):
    """Установить персональный ник игрока."""
    if isinstance(update, CallbackQuery):
        await update.answer()
        if update.message is None:
            return
        await state.set_state(MainStates.setting_nickname)
        await update.message.edit_text(
            "✏️ НИК ИГРОКА\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Введите ник (3-28 символов, без спецсимволов).\n"
            "Этот шаг обязателен: без ника играть нельзя.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")],
                ]
            ),
            parse_mode=None,
        )
        return

    message = update
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        ok, msg, nick = await db.set_user_nickname(message.from_user.id, parts[1])
        prefix = "✅" if ok else "❌"
        shown = f"\nТекущий ник: {_escape_markdown(nick)}" if ok and nick else ""
        await state.set_state(MainStates.main_menu if ok else MainStates.setting_nickname)
        await message.answer(
            f"{prefix} {msg}{shown}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🏠 В меню" if ok else "✏️ Ввести ник",
                        callback_data="back_to_main" if ok else "set_nick_start",
                    )
                ]]
            ),
            parse_mode="Markdown",
        )
        return

    await state.set_state(MainStates.setting_nickname)
    await message.answer(
        "✏️ Введите ник (3-28 символов, без спецсимволов).\n"
        "Без ника игра недоступна.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")]]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "set_nick_reset")
async def set_nick_reset(callback: CallbackQuery, state: FSMContext):
    """Быстрый сброс пользовательского ника."""
    await callback.answer()
    if callback.message is None:
        return
    ok, msg, _ = await db.set_user_nickname(callback.from_user.id, "reset")
    await state.set_state(MainStates.setting_nickname)
    await callback.message.edit_text(
        ("✅ " if ok else "❌ ")
        + msg
        + "\n\nВведите новый ник для продолжения игры.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")]]
        ),
        parse_mode=None,
    )


@router.message(MainStates.setting_nickname, F.text, ~F.text.startswith("/"))
async def set_nick_finish(message: Message, state: FSMContext):
    """Сохранить введенный ник."""
    text = (message.text or "").strip()
    if text.lower() in {"отмена", "cancel", "назад"}:
        user = await db.get_user(message.from_user.id) or {}
        if _clean_name(user.get("nickname"), 28):
            await state.set_state(MainStates.main_menu)
            await message.answer(
                "Изменение ника отменено.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")]]
                ),
            )
            return
        await state.set_state(MainStates.setting_nickname)
        await message.answer(
            "❗ Ник обязателен. Введите ник для продолжения.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")]]
            ),
            parse_mode=None,
        )
        return

    ok, msg, nick = await db.set_user_nickname(message.from_user.id, text)
    await state.set_state(MainStates.main_menu if ok else MainStates.setting_nickname)
    prefix = "✅" if ok else "❌"
    shown = f"\nТекущий ник: {_escape_markdown(nick)}" if ok and nick else ""
    await message.answer(
        f"{prefix} {msg}{shown}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🏠 В меню" if ok else "✏️ Ввести ник",
                    callback_data="back_to_main" if ok else "set_nick_start",
                )
            ]]
        ),
        parse_mode="Markdown",
    )


async def _render_ai_menu(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    user = await db.get_user(user_id) or {}
    authority = await db.get_government_authority(user_id)
    pending_app = await db.get_user_pending_job_application(user_id)
    task_state = await db.get_user_job_task_status(user_id)
    active_task = task_state.get("active_task")
    mission_remain = await db.get_user_cooldown_remaining(user_id, "ai_personal_mission", 40)
    news_remain = await db.get_user_cooldown_remaining(user_id, "ai_city_news_refresh", 20)

    recommendations: list[str] = []
    if not str(user.get("citizen_job") or "").strip():
        recommendations.append("Подайте заявление на работу: `Работа → Вакансии`.")
    elif pending_app:
        recommendations.append("У вас висит HR-заявка. Нажмите `Авто-решение HR` в меню работы.")
    else:
        recommendations.append("Работа активна: держите регулярный цикл смен и подработок.")

    if active_task:
        recommendations.append(
            f"Рабочая цель: {int(active_task.get('progress') or 0)}/{int(active_task.get('goal') or 1)} смен."
        )
    if int(user.get("education") or 1) < 3:
        recommendations.append("Поднимите образование до 3+, это откроет более выгодные вакансии.")
    if float(user.get("tax_debt") or 0) > 0:
        recommendations.append("Есть налоговый долг. Закройте его, чтобы снизить риски блокировок.")
    if float(user.get("balance") or 0) < 20_000:
        recommendations.append("Низкая ликвидность: сделайте 2-3 микроподработки подряд.")
    if not recommendations:
        recommendations.append("Портфель стабильный. Расширяйтесь через бизнес и контрактный рынок.")

    lines = [
        "🤖 **AI-АССИСТЕНТ**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Игрок: {_escape_markdown(_display_user_name(user, fallback_id=user_id))}",
        f"Полномочия: {_escape_markdown(_gov_authority_label(authority))}",
        f"Баланс: ${float(user.get('balance') or 0):,.0f}",
        f"Репутация: {float(user.get('reputation') or 50):.1f}/100",
        f"Риск: {int(user.get('corruption_score') or 0)}/100",
        "",
        "Рекомендации AI:",
    ]
    for tip in recommendations[:5]:
        lines.append(f"• {_escape_markdown(tip)}")
    lines.extend(
        [
            "",
            f"AI-миссия: {'доступна' if mission_remain <= 0 else f'через {mission_remain} мин'}",
            f"AI-сводка города: {'доступна' if news_remain <= 0 else f'через {news_remain} мин'}",
        ]
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ AI-миссия", callback_data="ai_mission"),
                InlineKeyboardButton(text="📰 AI-сводка", callback_data="ai_city_news"),
            ],
            [
                InlineKeyboardButton(text="📡 Гос-рация", callback_data="gov_radio_menu"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu"),
            ],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")
    else:
        await event.answer("\n".join(lines), reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("ai"))
@router.callback_query(F.data == "ai_menu")
async def ai_menu(event, state: FSMContext):
    """Персональный AI-помощник игрока."""
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(MainStates.main_menu)
    await _render_ai_menu(event, state)


@router.callback_query(F.data == "ai_mission")
async def ai_mission(callback: CallbackQuery, state: FSMContext):
    """AI выдает персональную мини-миссию с наградой."""
    await callback.answer()
    user_id = callback.from_user.id
    remain = await db.get_user_cooldown_remaining(user_id, "ai_personal_mission", 40)
    if remain > 0:
        await callback.answer(f"AI-миссия будет доступна через {remain} мин.", show_alert=True)
        return

    allowed, remain = await db.check_and_set_user_cooldown(user_id, "ai_personal_mission", 40)
    if not allowed:
        await callback.answer(f"AI-миссия будет доступна через {remain} мин.", show_alert=True)
        return

    user = await db.get_user(user_id) or {}
    authority = await db.get_government_authority(user_id)
    reward = float(random.randint(1200, 3600))
    if str(user.get("citizen_job") or "").strip():
        reward = round(reward * 1.12, 2)
    if authority in {"president", "vice_president", "finance_minister", "minister"}:
        reward = round(reward * 1.08, 2)
    xp = int(random.randint(18, 48))
    rep_gain = round(random.uniform(0.12, 0.35), 2)

    new_balance = round(float(user.get("balance") or 0) + reward, 2)
    new_exp = int(user.get("experience") or 0) + xp
    new_rep = min(100.0, round(float(user.get("reputation") or 50) + rep_gain, 2))
    await db.update_user(user_id, balance=new_balance, experience=new_exp, reputation=new_rep)
    await db.log_player_activity(
        user_id=user_id,
        activity_type="ai_mission",
        details="Выполнена персональная AI-миссия.",
        value=reward,
    )

    await callback.message.edit_text(
        "⚡ **AI-МИССИЯ ВЫПОЛНЕНА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Награда: ${reward:,.0f}\n"
        f"Опыт: +{xp}\n"
        f"Репутация: +{rep_gain:.2f}\n"
        f"Новый баланс: ${new_balance:,.0f}\n\n"
        "Следующая AI-миссия через 40 минут.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤖 К AI-панели", callback_data="ai_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "ai_city_news")
async def ai_city_news(callback: CallbackQuery, state: FSMContext):
    """AI-сводка городских новостей и активности."""
    await callback.answer()
    user_id = callback.from_user.id
    remain = await db.get_user_cooldown_remaining(user_id, "ai_city_news_refresh", 20)
    if remain <= 0:
        await db.check_and_set_user_cooldown(user_id, "ai_city_news_refresh", 20)
        await db.generate_hourly_news()

    news_rows = await db.get_latest_media_news(limit=6)
    severity_icon = {"normal": "•", "hot": "🔥", "high": "⚠️", "critical": "🚨"}
    lines = [
        "📰 **AI-СВОДКА ГОРОДА**",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if remain > 0:
        lines.append(f"Обновление сводки снова доступно через {remain} мин.")
    lines.append("")
    if not news_rows:
        lines.append("Новостной поток пока пуст.")
    else:
        for row in news_rows:
            created = str(row.get("created_date") or "")[:16]
            icon = severity_icon.get(str(row.get("severity") or "normal").lower(), "•")
            title = _escape_markdown(str(row.get("title") or "Новость"))
            body = _escape_markdown(str(row.get("body") or ""))
            if len(body) > 180:
                body = body[:177] + "..."
            lines.append(f"{icon} [{created}] **{title}**")
            lines.append(body)
            lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить сводку", callback_data="ai_city_news")],
                [InlineKeyboardButton(text="🤖 К AI-панели", callback_data="ai_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode="Markdown",
    )


def _format_gov_radio_lines(rows: list[dict]) -> list[str]:
    lines = []
    for row in rows:
        created = str(row.get("created_date") or "")[11:16]
        speaker = _display_user_name(row, fallback_id=int(row.get("user_id") or 0))
        content = str(row.get("content") or "")
        if len(content) > 260:
            content = content[:257] + "..."
        lines.append(f"[{created}] {_escape_markdown(speaker)}")
        lines.append(_escape_markdown(content))
        lines.append("")
    return lines


def _appeal_status_label(code: str) -> str:
    mapping = {
        "pending_vice": "⏳ На проверке вице-президента",
        "pending_president": "⏳ На проверке президента",
        "rejected_by_vice": "❌ Отклонено вице-президентом",
        "rejected_by_president": "❌ Отклонено президентом",
        "approved_by_president": "✅ Одобрено президентом",
    }
    return mapping.get((code or "").strip().lower(), code or "неизвестно")


async def _notify_user_safe(bot_obj, user_id: int, text: str) -> None:
    try:
        await bot_obj.send_message(int(user_id), text, parse_mode=None)
    except Exception:
        pass


async def _render_gov_radio(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    can_view = await db.can_access_government_radio(user_id, for_send=False)
    can_send = await db.can_access_government_radio(user_id, for_send=True)
    pending_appeals = await db.get_pending_citizen_appeal_count(user_id)

    if not can_view:
        text = (
            "📡 **ГОС-РАЦИЯ**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Доступ к эфиру есть у сотрудников правительства и ФБР.\n\n"
            "Вы можете отправить обращение президенту."
        )
        keyboard_rows = [
            [InlineKeyboardButton(text="✉️ Написать президенту", callback_data="pres_appeal_start")],
            [InlineKeyboardButton(text="📨 Мои обращения", callback_data="pres_appeal_my")],
            [InlineKeyboardButton(text="🤖 AI-помощник", callback_data="ai_menu")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    else:
        rows = await db.get_government_radio_messages(limit=16)
        lines = [
            "📡 **ГОС-РАЦИЯ (ПРАВИТЕЛЬСТВО)**",
            "━━━━━━━━━━━━━━━━━━━━",
            "Официальный канал объявлений и распоряжений.",
            "",
        ]
        if not rows:
            lines.append("Пока нет сообщений эфира.")
        else:
            lines.extend(_format_gov_radio_lines(rows))
        text = "\n".join(lines)

        keyboard_rows = []
        if can_send:
            keyboard_rows.append([InlineKeyboardButton(text="📢 Выйти в эфир", callback_data="gov_radio_send")])
        keyboard_rows.append([InlineKeyboardButton(text="✉️ Обращение президенту", callback_data="pres_appeal_start")])
        keyboard_rows.append([InlineKeyboardButton(text="📨 Мои обращения", callback_data="pres_appeal_my")])
        if pending_appeals > 0:
            keyboard_rows.append([InlineKeyboardButton(text=f"📥 Входящие обращения ({pending_appeals})", callback_data="pres_appeal_inbox")])
        keyboard_rows.extend(
            [
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="gov_radio_menu")],
                [InlineKeyboardButton(text="🤖 AI-помощник", callback_data="ai_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await event.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@router.message(Command("radio"))
@router.callback_query(F.data == "gov_radio_menu")
async def gov_radio_menu(event, state: FSMContext):
    """Меню и лента государственной рации."""
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(MainStates.main_menu)
    await _render_gov_radio(event, state)


@router.callback_query(F.data == "gov_radio_send")
async def gov_radio_send_start(callback: CallbackQuery, state: FSMContext):
    """Начать отправку сообщения в эфир гос-рации."""
    await callback.answer()
    can_send = await db.can_access_government_radio(callback.from_user.id, for_send=True)
    if not can_send:
        await callback.answer("Эфир доступен только правительству.", show_alert=True)
        return
    await state.set_state(MainStates.sending_gov_radio)
    await callback.message.edit_text(
        "📢 **ВЫХОД В ЭФИР ГОС-РАЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Введите текст объявления.\n"
        "Максимум: 1200 символов.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К рации", callback_data="gov_radio_menu")],
            ]
        ),
        parse_mode="Markdown",
    )


@router.message(MainStates.sending_gov_radio, F.text, ~F.text.startswith("/"))
async def gov_radio_send_finish(message: Message, state: FSMContext):
    """Сохранить сообщение в гос-рацию."""
    ok, msg = await db.send_government_radio_message(message.from_user.id, message.text or "")
    await state.set_state(MainStates.main_menu if ok else MainStates.sending_gov_radio)
    await message.answer(
        ("✅ " if ok else "❌ ") + msg,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📡 Открыть рацию", callback_data="gov_radio_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_appeal_start")
async def president_appeal_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(MainStates.sending_president_appeal)
    if callback.message is None:
        return
    await callback.message.edit_text(
        "✉️ **ОБРАЩЕНИЕ ПРЕЗИДЕНТУ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Напишите обращение одним сообщением.\n"
        "Если есть вице-президент, сначала он проверит обращение,\n"
        "после одобрения оно попадет президенту.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К рации", callback_data="gov_radio_menu")],
            ]
        ),
        parse_mode="Markdown",
    )


@router.message(MainStates.sending_president_appeal, F.text, ~F.text.startswith("/"))
async def president_appeal_finish(message: Message, state: FSMContext):
    ok, msg, payload = await db.create_citizen_appeal(message.from_user.id, message.text or "")
    await state.set_state(MainStates.main_menu if ok else MainStates.sending_president_appeal)

    if ok and payload:
        vice_id = int(payload.get("vice_id") or 0)
        president_id = int(payload.get("president_id") or 0)
        appeal_id = int(payload.get("appeal_id") or 0)
        status = str(payload.get("status") or "")
        sender_name = _display_user_name(await db.get_user(message.from_user.id), fallback_id=message.from_user.id)
        notify_text = (
            "📩 Новое обращение гражданина\n"
            f"ID обращения: #{appeal_id}\n"
            f"От: {sender_name}\n"
            "Откройте вкладку входящих обращений в гос-рации."
        )
        if status == "pending_vice" and vice_id > 0:
            await _notify_user_safe(message.bot, vice_id, notify_text)
        elif president_id > 0:
            await _notify_user_safe(message.bot, president_id, notify_text)

    await message.answer(
        ("✅ " if ok else "❌ ") + msg,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📨 Мои обращения", callback_data="pres_appeal_my")],
                [InlineKeyboardButton(text="📡 К рации", callback_data="gov_radio_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode=None,
    )


@router.message(MainStates.sending_president_appeal)
async def president_appeal_invalid(message: Message):
    await message.answer(
        "❌ Отправьте текст обращения обычным сообщением.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К рации", callback_data="gov_radio_menu")],
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data == "pres_appeal_my")
async def president_appeal_my(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.message is None:
        return
    rows = await db.get_user_citizen_appeals(callback.from_user.id, limit=12)
    lines = ["📨 **МОИ ОБРАЩЕНИЯ**", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Вы еще не отправляли обращения.")
    else:
        for row in rows:
            created = str(row.get("created_date") or "")[:16]
            status = _appeal_status_label(str(row.get("status") or ""))
            content = str(row.get("content") or "")
            if len(content) > 120:
                content = content[:117] + "..."
            lines.append(f"#{int(row.get('id') or 0)} [{created}] {status}")
            lines.append(_escape_markdown(content))
            lines.append("")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✉️ Новое обращение", callback_data="pres_appeal_start")],
                [InlineKeyboardButton(text="📡 К рации", callback_data="gov_radio_menu")],
            ]
        ),
        parse_mode="Markdown",
    )


async def _render_appeal_inbox(callback: CallbackQuery):
    if callback.message is None:
        return
    rows = await db.get_pending_citizen_appeals(callback.from_user.id, limit=10)
    if not rows:
        await callback.message.edit_text(
            "📥 **ВХОДЯЩИЕ ОБРАЩЕНИЯ**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Новых обращений нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="pres_appeal_inbox")],
                    [InlineKeyboardButton(text="📡 К рации", callback_data="gov_radio_menu")],
                ]
            ),
            parse_mode="Markdown",
        )
        return

    lines = [
        "📥 **ВХОДЯЩИЕ ОБРАЩЕНИЯ ГРАЖДАН**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        aid = int(row.get("id") or 0)
        created = str(row.get("created_date") or "")[:16]
        author = _display_user_name(
            {
                "nickname": row.get("citizen_name"),
                "username": row.get("citizen_username"),
                "user_id": row.get("citizen_id"),
            },
            fallback_id=int(row.get("citizen_id") or 0),
        )
        content = str(row.get("content") or "")
        if len(content) > 120:
            content = content[:117] + "..."
        lines.append(f"#{aid} [{created}] {_escape_markdown(author)}")
        lines.append(_escape_markdown(content))
        lines.append("")
        keyboard_rows.append([
            InlineKeyboardButton(text=f"✅ Одобрить #{aid}", callback_data=f"pres_appeal_accept_{aid}"),
            InlineKeyboardButton(text=f"❌ Отклонить #{aid}", callback_data=f"pres_appeal_reject_{aid}"),
        ])

    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="pres_appeal_inbox")])
    keyboard_rows.append([InlineKeyboardButton(text="📡 К рации", callback_data="gov_radio_menu")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "pres_appeal_inbox")
async def president_appeal_inbox(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    count = await db.get_pending_citizen_appeal_count(callback.from_user.id)
    if count <= 0:
        await callback.answer("У вас нет входящих обращений.", show_alert=True)
    await _render_appeal_inbox(callback)


@router.callback_query(F.data.startswith("pres_appeal_accept_"))
@router.callback_query(F.data.startswith("pres_appeal_reject_"))
async def president_appeal_decision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    approve = (callback.data or "").startswith("pres_appeal_accept_")
    raw = (callback.data or "").replace("pres_appeal_accept_", "").replace("pres_appeal_reject_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный ID обращения.", show_alert=True)
        return
    ok, msg, payload = await db.review_citizen_appeal(
        reviewer_id=callback.from_user.id,
        appeal_id=int(raw),
        approve=approve,
        note="Решение через гос-рацию",
    )
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    if ok and payload:
        citizen_id = int(payload.get("citizen_id") or 0)
        new_status = str(payload.get("new_status") or "")
        appeal_id = int(payload.get("id") or raw)
        await _notify_user_safe(
            callback.bot,
            citizen_id,
            f"📨 Ваше обращение #{appeal_id}: {_appeal_status_label(new_status)}",
        )
        if new_status == "pending_president":
            president_id = int(payload.get("president_id") or 0)
            if president_id > 0:
                await _notify_user_safe(
                    callback.bot,
                    president_id,
                    f"📩 Вице-президент одобрил обращение #{appeal_id}. Требуется ваше решение.",
                )
    await _render_appeal_inbox(callback)


# ==================== ГРУППОВОЕ PVP-КАЗИНО ====================

@router.message(
    F.reply_to_message,
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(
        r"(?i)^/?(?:duel|casino_duel|pvp|кости|кость|кубик|dice|автомат|автомат3|слот|слоты|slot|slots|slot3|slots3|баскет|баскетбол|basket|basketball|рулетка|roulette|redblack|rb|red|black|красное|черное|чёрное)(?:@\w+)?(?:\s+.*)?$"
    ),
)
@router.message(Command("duel"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
@router.message(Command("casino_duel"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
@router.message(Command("pvp"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
async def group_casino_duel_start(message: Message, state: FSMContext):
    parsed = _parse_group_casino_command(message.text or "")
    if not parsed:
        return UNHANDLED
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return UNHANDLED

    challenger_id = int(message.from_user.id)
    opponent_user = message.reply_to_message.from_user
    opponent_id = int(opponent_user.id)
    if opponent_id == challenger_id:
        await message.reply("❌ Нельзя вызывать себя.")
        return
    if opponent_user.is_bot:
        await message.reply("❌ Нельзя вызывать бота.")
        return

    game, target, bet = parsed
    cfg = GROUP_CASINO_CFG.get(game, {})
    target_min = int(cfg.get("min", 0))
    target_max = int(cfg.get("max", 0))
    if game not in {"dice", "slots3", "slots"} and (target < target_min or target > target_max):
        await message.reply(
            f"❌ Для игры '{cfg.get('title', game)}' число должно быть от {cfg.get('min')} до {cfg.get('max')}."
        )
        return

    # На случай, если соперник еще не писал команд боту, создаем карточку игрока.
    await db.create_or_update_user(
        opponent_id,
        opponent_user.username or "",
        f"{opponent_user.first_name or ''} {opponent_user.last_name or ''}".strip(),
    )

    ok, msg, payload = await db.create_group_casino_duel(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        chat_id=int(message.chat.id),
        game_type=game,
        target_value=target,
        bet_amount=bet,
        challenge_message_id=message.message_id,
        expires_minutes=5,
    )
    if not ok or not payload:
        await message.reply(f"❌ {msg}")
        return

    duel_id = int(payload.get("duel_id") or 0)
    challenger_name = _display_user_name(await db.get_user(challenger_id), fallback_id=challenger_id)
    opponent_name = _display_user_name(await db.get_user(opponent_id), fallback_id=opponent_id)
    if game == "dice":
        condition_text = "Правило: у кого больше число на кости — тот победил."
    elif game in {"slots3", "slots"}:
        condition_text = "Правило: у кого сильнее комбинация в автомате (тройка > пара > разные) — тот победил."
    elif game == "roulette":
        color_name = "красное" if target == 1 else "черное"
        condition_text = f"Условие: ставка инициатора на {color_name}. Выпадает {color_name} — побеждает инициатор."
    else:
        condition_text = f"Условие: выпадает число {target}"
    await message.reply(
        "🎮 Дуэль в казино создана\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Инициатор: {challenger_name}\n"
        f"Соперник: {opponent_name}\n"
        f"Игра: {cfg.get('title')}\n"
        f"{condition_text}\n"
        f"Ставка: ${bet:,.2f}\n\n"
        "Комиссия системы: 1% с выигрыша.\n\n"
        "Соперник, примите или отклоните вызов:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=f"pvpduel_accept_{duel_id}"),
                    InlineKeyboardButton(text="❌ Отказ", callback_data=f"pvpduel_reject_{duel_id}"),
                ]
            ]
        ),
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("pvpduel_reject_"))
async def group_casino_duel_reject(callback: CallbackQuery, state: FSMContext):
    raw = (callback.data or "").replace("pvpduel_reject_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный вызов.", show_alert=True)
        return
    ok, msg, payload = await db.reject_group_casino_duel(int(raw), callback.from_user.id)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    await callback.answer("Вызов отклонен.")
    duel = payload or {}
    challenger_name = _display_user_name(await db.get_user(int(duel.get("challenger_id") or 0)), fallback_id=int(duel.get("challenger_id") or 0))
    opponent_name = _display_user_name(await db.get_user(int(duel.get("opponent_id") or 0)), fallback_id=int(duel.get("opponent_id") or 0))
    if callback.message:
        await callback.message.edit_text(
            "❌ Дуэль не состоится\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{challenger_name} vs {opponent_name}\n"
            f"Причина: {msg}",
            parse_mode=None,
        )


@router.callback_query(F.data.startswith("pvpduel_accept_"))
async def group_casino_duel_accept(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        return
    raw = (callback.data or "").replace("pvpduel_accept_", "")
    if not raw.isdigit():
        await callback.answer("Некорректный вызов.", show_alert=True)
        return

    duel = await db.get_group_casino_duel(int(raw))
    if not duel:
        await callback.answer("Вызов не найден.", show_alert=True)
        return
    if str(duel.get("status") or "") != "pending":
        await callback.answer("Этот вызов уже неактивен.", show_alert=True)
        return
    if int(duel.get("opponent_id") or 0) != int(callback.from_user.id):
        await callback.answer("Принять вызов может только выбранный соперник.", show_alert=True)
        return

    game_type = str(duel.get("game_type") or "")
    cfg = GROUP_CASINO_CFG.get(game_type)
    if not cfg:
        await callback.answer("Ошибка игры.", show_alert=True)
        return

    await callback.answer("Вызов принят.")
    challenger_roll: int | None = None
    opponent_roll: int | None = None
    roll_value: int | None = None
    if game_type == "dice":
        challenger_name = _display_user_name(
            await db.get_user(int(duel.get("challenger_id") or 0)),
            fallback_id=int(duel.get("challenger_id") or 0),
        )
        opponent_name = _display_user_name(
            await db.get_user(int(duel.get("opponent_id") or 0)),
            fallback_id=int(duel.get("opponent_id") or 0),
        )
        round_no = 1
        while True:
            await callback.message.answer(f"🎲 Раунд {round_no}: бросок {challenger_name}", parse_mode=None)
            ch_msg = await callback.message.answer_dice(emoji=str(cfg.get("emoji")))
            challenger_roll = int((ch_msg.dice.value if ch_msg and ch_msg.dice else 0) or 0)

            await callback.message.answer(f"🎲 Раунд {round_no}: бросок {opponent_name}", parse_mode=None)
            op_msg = await callback.message.answer_dice(emoji=str(cfg.get("emoji")))
            opponent_roll = int((op_msg.dice.value if op_msg and op_msg.dice else 0) or 0)

            if challenger_roll != opponent_roll:
                break
            round_no += 1
            await callback.message.answer(
                f"🤝 Ничья ({challenger_roll}:{opponent_roll}). Переброс!",
                parse_mode=None,
            )

        ok, msg, payload = await db.resolve_group_casino_duel(
            duel_id=int(raw),
            accepter_id=callback.from_user.id,
            challenger_roll=challenger_roll,
            opponent_roll=opponent_roll,
        )
    elif game_type in {"slots3", "slots"}:
        challenger_name = _display_user_name(
            await db.get_user(int(duel.get("challenger_id") or 0)),
            fallback_id=int(duel.get("challenger_id") or 0),
        )
        opponent_name = _display_user_name(
            await db.get_user(int(duel.get("opponent_id") or 0)),
            fallback_id=int(duel.get("opponent_id") or 0),
        )
        round_no = 1
        while True:
            await callback.message.answer(f"🎰 Раунд {round_no}: вращение {challenger_name}", parse_mode=None)
            ch_msg = await callback.message.answer_dice(emoji="🎰")
            challenger_roll = int((ch_msg.dice.value if ch_msg and ch_msg.dice else 0) or 0)

            await callback.message.answer(f"🎰 Раунд {round_no}: вращение {opponent_name}", parse_mode=None)
            op_msg = await callback.message.answer_dice(emoji="🎰")
            opponent_roll = int((op_msg.dice.value if op_msg and op_msg.dice else 0) or 0)

            ok, msg, payload = await db.resolve_group_casino_duel(
                duel_id=int(raw),
                accepter_id=callback.from_user.id,
                challenger_roll=challenger_roll,
                opponent_roll=opponent_roll,
            )
            if ok:
                break
            if "ничья" in str(msg).lower():
                round_no += 1
                await callback.message.answer("🤝 Равные комбинации. Крутим еще раз!", parse_mode=None)
                continue
            await callback.message.answer(f"❌ {msg}", parse_mode=None)
            return
    elif game_type == "roulette":
        roll_value = random.randint(1, 36)
        await callback.message.answer(f"🎯 Рулетка крутится... Выпало число: {roll_value}", parse_mode=None)
        ok, msg, payload = await db.resolve_group_casino_duel(
            duel_id=int(raw),
            accepter_id=callback.from_user.id,
            roll_value=roll_value,
        )
    else:
        dice_msg = await callback.message.answer_dice(emoji=str(cfg.get("emoji")))
        roll_value = int((dice_msg.dice.value if dice_msg and dice_msg.dice else 0) or 0)
        ok, msg, payload = await db.resolve_group_casino_duel(
            duel_id=int(raw),
            accepter_id=callback.from_user.id,
            roll_value=roll_value,
        )
    if not ok or not payload:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
        return

    winner_id = int(payload.get("winner_id") or 0)
    loser_id = int(payload.get("loser_id") or 0)
    bet_amount = float(payload.get("bet_amount") or 0)
    house_fee = float(payload.get("house_fee") or 0)
    winner_gain = float(payload.get("winner_gain") or 0)
    winner_name = _display_user_name(await db.get_user(winner_id), fallback_id=winner_id)
    loser_name = _display_user_name(await db.get_user(loser_id), fallback_id=loser_id)
    if game_type == "dice":
        c_roll = int(payload.get("challenger_roll") or 0)
        o_roll = int(payload.get("opponent_roll") or 0)
        result_text = (
            "🏁 Дуэль завершена\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Игра: {cfg.get('title')}\n"
            "Правило: большее число побеждает\n"
            f"Бросок инициатора: {c_roll}\n"
            f"Бросок соперника: {o_roll}\n"
            f"Победитель: {winner_name}\n"
            f"Проиграл: {loser_name}\n"
            f"Ставка: ${bet_amount:,.2f}\n"
            f"Комиссия (1%): ${house_fee:,.2f}\n"
            f"Победитель получил: ${winner_gain:,.2f}"
        )
    elif game_type in {"slots3", "slots"}:
        c_slots = str(payload.get("challenger_slots") or payload.get("challenger_roll") or "-")
        o_slots = str(payload.get("opponent_slots") or payload.get("opponent_roll") or "-")
        combo_labels = {"triple": "тройка", "pair": "пара", "none": "разные"}
        c_combo = combo_labels.get(str(payload.get("challenger_slots_combo") or ""), "разные")
        o_combo = combo_labels.get(str(payload.get("opponent_slots_combo") or ""), "разные")
        result_text = (
            "🏁 Дуэль завершена\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Игра: {cfg.get('title')}\n"
            "Правило: тройка > пара > разные\n"
            f"Инициатор: {c_slots} ({c_combo})\n"
            f"Соперник: {o_slots} ({o_combo})\n"
            f"Победитель: {winner_name}\n"
            f"Проиграл: {loser_name}\n"
            f"Ставка: ${bet_amount:,.2f}\n"
            f"Комиссия (1%): ${house_fee:,.2f}\n"
            f"Победитель получил: ${winner_gain:,.2f}"
        )
    elif game_type == "roulette":
        target_value = int(payload.get("target_value") or 0)
        target_color = "red" if target_value == 1 else "black"
        spin_number = int(payload.get("roll_value") or 0)
        spin_color = str(payload.get("roulette_color") or "unknown")
        result_text = (
            "🏁 Дуэль завершена\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Игра: {cfg.get('title')}\n"
            f"Ставка инициатора: {target_color}\n"
            f"Выпало: {spin_number} ({spin_color})\n"
            f"Победитель: {winner_name}\n"
            f"Проиграл: {loser_name}\n"
            f"Ставка: ${bet_amount:,.2f}\n"
            f"Комиссия (1%): ${house_fee:,.2f}\n"
            f"Победитель получил: ${winner_gain:,.2f}"
        )
    else:
        target_value = int(payload.get("target_value") or 0)
        result_text = (
            "🏁 Дуэль завершена\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Игра: {cfg.get('title')}\n"
            f"Условие: число {target_value}\n"
            f"Выпало: {roll_value}\n"
            f"Победитель: {winner_name}\n"
            f"Проиграл: {loser_name}\n"
            f"Ставка: ${bet_amount:,.2f}\n"
            f"Комиссия (1%): ${house_fee:,.2f}\n"
            f"Победитель получил: ${winner_gain:,.2f}"
        )
    await callback.message.answer(result_text, parse_mode=None)


# ==================== СЕМЬЯ, БРАКИ, ПИТОМЦЫ ====================

PET_TYPE_LABELS = {
    "cat": "Кот",
    "dog": "Пес",
    "rabbit": "Кролик",
    "parrot": "Попугай",
    "fox": "Лис",
}

SOCIAL_ACTIONS = {
    "обнять": "обнял(а)",
    "поцеловать": "поцеловал(а)",
    "погладить": "погладил(а)",
    "укусить": "укусил(а)",
}

RELATIONSHIP_SPEND_BUTTONS = [
    ("gift_small", "🎁 Подарок · 4 000"),
    ("date_night", "🍽 Свидание · 18 000"),
    ("weekend_trip", "✈️ Поездка · 60 000"),
    ("resort_vacation", "🏝 Курорт · 140 000"),
]
RELATIONSHIP_REPLY_SPEND_MAP = {
    "подарок": "gift_small",
    "свидание": "date_night",
    "поездка": "weekend_trip",
    "курорт": "resort_vacation",
    "gift": "gift_small",
    "date": "date_night",
    "trip": "weekend_trip",
    "resort": "resort_vacation",
}


async def _render_family_menu(update, answer_query: bool = True):
    if isinstance(update, CallbackQuery):
        callback = update
        if answer_query:
            await callback.answer()
        message = callback.message
        if message is None:
            return
        user_id = int(callback.from_user.id)
    else:
        message = update
        user_id = int(message.from_user.id)

    marriage = await db.get_active_marriage(user_id)
    account = await db.get_family_account(user_id)
    estimate = await db.estimate_daily_family_expense(user_id)
    pet = await db.get_user_pet(user_id)
    relation_actions = sorted(db.list_relationship_actions(), key=lambda item: float(item.get("cost") or 0.0))

    lines = [
        "👨‍👩‍👧 СЕМЬЯ",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if marriage:
        spouse_id = int(marriage.get("spouse_id") or 0)
        spouse_user = await db.get_user(spouse_id)
        spouse_name = _display_user_name(spouse_user, fallback_id=spouse_id)
        relation_level = int(marriage.get("relationship_level") or 1)
        relation_points = int(marriage.get("relationship_points") or 0)
        points_to_next = int(marriage.get("relationship_points_to_next") or 0)
        upkeep_multiplier = float(marriage.get("relationship_upkeep_multiplier") or 1.0)
        lines.extend(
            [
                f"Статус: в браке с {spouse_name}",
                f"Вместе дней: {int(marriage.get('days_together') or 0)}",
                f"Уровень отношений: {relation_level}/25 ({relation_points} очков)",
                (
                    f"До следующего уровня: {points_to_next} очк."
                    if points_to_next > 0
                    else "Достигнут максимальный уровень отношений."
                ),
                f"Коэффициент семейных расходов: x{upkeep_multiplier:.2f}",
            ]
        )
    else:
        lines.append("Статус: не в браке")

    if pet:
        pet_title = PET_TYPE_LABELS.get(str(pet.get("pet_type") or "").lower(), "Питомец")
        lines.extend(
            [
                f"Питомец: {pet_title} '{pet.get('pet_name')}'",
                (
                    f"Показатели: сытость {int(pet.get('hunger') or 0)}/100, "
                    f"настроение {int(pet.get('mood') or 0)}/100, "
                    f"энергия {int(pet.get('energy') or 0)}/100"
                ),
            ]
        )
    else:
        lines.append("Питомец: нет")

    lines.extend(
        [
            "",
            f"Ежедневные семейные расходы: {_lum(float(estimate.get('daily_total') or 0))}",
            (
                f"Базовое содержание семьи: {_lum(float(estimate.get('base_expense') or 0))}"
                if marriage
                else "Базовое содержание семьи: 0.00 люмов"
            ),
            f"Семейный долг: {_lum(float(account.get('family_debt') or 0))}",
            f"Всего начислено: {_lum(float(account.get('total_family_charged') or 0))}",
            f"Всего оплачено: {_lum(float(account.get('total_family_paid') or 0))}",
            "",
            "Групповые команды (reply): брак, обнять, поцеловать, погладить, подарок, свидание, поездка, курорт",
        ]
    )
    if marriage and relation_actions:
        lines.append("")
        lines.append("Семейные дела для роста отношений:")
        for action in relation_actions[:5]:
            lines.append(
                f"• {action.get('title')}: {_lum(float(action.get('cost') or 0))} "
                f"(+{int(action.get('points') or 0)} очк.)"
            )

    keyboard_rows = []
    if float(account.get("family_debt") or 0) > 0:
        keyboard_rows.append([InlineKeyboardButton(text="💸 Погасить семейный долг", callback_data="family_pay_debt")])
    if marriage:
        for action in relation_actions[:5]:
            action_key = str(action.get("key") or "").strip()
            if not action_key:
                continue
            label = f"💞 {str(action.get('title') or 'Действие')} · {int(float(action.get('cost') or 0)):,.0f}"
            keyboard_rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"family_rel_spend_{action_key}")]
            )
    keyboard_rows.append([InlineKeyboardButton(text="🐾 Питомец", callback_data="pet_menu")])
    keyboard_rows.append([InlineKeyboardButton(text="🏆 Топ браков", callback_data="family_top")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    if isinstance(update, CallbackQuery):
        await message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)
    else:
        await message.answer("\n".join(lines), reply_markup=keyboard, parse_mode=None)


async def _render_pet_menu(update, answer_query: bool = True):
    if isinstance(update, CallbackQuery):
        callback = update
        if answer_query:
            await callback.answer()
        message = callback.message
        if message is None:
            return
        user_id = int(callback.from_user.id)
    else:
        message = update
        user_id = int(message.from_user.id)

    pet = await db.get_user_pet(user_id)
    if not pet:
        text = (
            "🐾 ПИТОМЕЦ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "У вас пока нет питомца.\n"
            "Стоимость усыновления: 1,500.00 люмов."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🐱 Взять кота", callback_data="pet_adopt_cat")],
                [InlineKeyboardButton(text="🐶 Взять пса", callback_data="pet_adopt_dog")],
                [InlineKeyboardButton(text="🐰 Взять кролика", callback_data="pet_adopt_rabbit")],
                [InlineKeyboardButton(text="🦜 Взять попугая", callback_data="pet_adopt_parrot")],
                [InlineKeyboardButton(text="🦊 Взять лиса", callback_data="pet_adopt_fox")],
                [InlineKeyboardButton(text="🎁 Ящики питомцев", callback_data="pet_loot_menu")],
                [InlineKeyboardButton(text="🔙 К семье", callback_data="family_menu")],
            ]
        )
        if isinstance(update, CallbackQuery):
            await message.edit_text(text, reply_markup=keyboard, parse_mode=None)
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode=None)
        return

    pet_title = PET_TYPE_LABELS.get(str(pet.get("pet_type") or "").lower(), "Питомец")
    rarity = str(pet.get("rarity") or "обычный")
    bonus_type = str(pet.get("bonus_type") or "").strip().lower()
    bonus_value = float(pet.get("bonus_value") or 0.0)
    bonus_line = ""
    if bonus_type == "family_discount_pct" and bonus_value > 0:
        bonus_line = f"Бонус: -{bonus_value * 100:.0f}% к семейным расходам\n"

    text = (
        "🐾 ПИТОМЕЦ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{pet_title}: {pet.get('pet_name')}\n"
        f"Редкость: {rarity}\n"
        f"Уровень: {int(pet.get('level') or 1)} (XP: {int(pet.get('xp') or 0)})\n"
        f"Сытость: {int(pet.get('hunger') or 0)}/100\n"
        f"Настроение: {int(pet.get('mood') or 0)}/100\n"
        f"Энергия: {int(pet.get('energy') or 0)}/100\n"
        f"Здоровье: {int(pet.get('health') or 0)}/100\n\n"
        f"{bonus_line}"
        "Команды:\n"
        "/petname <имя> — переименовать питомца"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍖 Покормить", callback_data="pet_action_feed")],
            [InlineKeyboardButton(text="🎾 Поиграть", callback_data="pet_action_play")],
            [InlineKeyboardButton(text="🎓 Тренировка", callback_data="pet_action_train")],
            [InlineKeyboardButton(text="🎁 Ящики питомцев", callback_data="pet_loot_menu")],
            [InlineKeyboardButton(text="🕊️ Отпустить", callback_data="pet_release")],
            [InlineKeyboardButton(text="🔙 К семье", callback_data="family_menu")],
        ]
    )
    if isinstance(update, CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard, parse_mode=None)
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode=None)


async def _start_marriage_from_reply(message: Message):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ Ответьте на сообщение игрока, которому хотите сделать предложение.")
        return

    proposer_id = int(message.from_user.id)
    target_user = message.reply_to_message.from_user
    target_id = int(target_user.id)
    if target_user.is_bot:
        await message.reply("❌ Нельзя предложить брак боту.")
        return
    if proposer_id == target_id:
        await message.reply("❌ Нельзя создать брак с самим собой.")
        return

    await db.create_or_update_user(
        target_id,
        target_user.username or "",
        f"{target_user.first_name or ''} {target_user.last_name or ''}".strip(),
    )
    ok, msg, payload = await db.create_marriage_proposal(
        proposer_id=proposer_id,
        target_id=target_id,
        source_chat_id=int(message.chat.id),
    )
    if not ok or not payload:
        await message.reply(f"❌ {msg}", parse_mode=None)
        return

    proposal_id = int(payload.get("proposal_id") or 0)
    proposer_name = _display_user_name(await db.get_user(proposer_id), fallback_id=proposer_id)
    target_name = _display_user_name(await db.get_user(target_id), fallback_id=target_id)
    await message.reply(
        "💍 ПРЕДЛОЖЕНИЕ БРАКА\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Инициатор: {proposer_name}\n"
        f"Партнер: {target_name}\n"
        "⏳ Действует 5 минут.\n\n"
        "Партнеру нужно нажать кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=f"fm_marry_accept_{proposal_id}"),
                    InlineKeyboardButton(text="❌ Отказать", callback_data=f"fm_marry_reject_{proposal_id}"),
                ]
            ]
        ),
        parse_mode=None,
    )


@router.message(Command("marry", "брак"), F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
@router.message(
    F.reply_to_message,
    F.chat.type.in_({"group", "supergroup"}),
    F.text.regexp(r"^/(?:marry|брак)(?:@\w+)?(?:\s.*)?$"),
)
async def family_marry_command(message: Message, state: FSMContext):
    await _start_marriage_from_reply(message)


@router.message(Command("marry", "брак"))
async def family_marry_usage(message: Message, state: FSMContext):
    await message.answer(
        "Использование: ответьте на сообщение человека в группе и напишите /marry\n"
        "Также поддерживается /брак или reply-команда «брак» (если в группе выключен privacy mode).",
        parse_mode=None,
    )


@router.callback_query(F.data.startswith("fm_marry_accept_"))
@router.callback_query(F.data.startswith("fm_marry_reject_"))
async def family_marry_decision(callback: CallbackQuery, state: FSMContext):
    data = callback.data or ""
    accept = data.startswith("fm_marry_accept_")
    raw = data.replace("fm_marry_accept_", "").replace("fm_marry_reject_", "")
    if not raw.isdigit():
        await callback.answer("Некорректное предложение.", show_alert=True)
        return
    ok, msg, payload = await db.respond_marriage_proposal(
        target_user_id=callback.from_user.id,
        proposal_id=int(raw),
        accept=accept,
    )
    if not ok:
        if callback.message and "истек" in str(msg or "").lower():
            await callback.message.edit_text(
                "⌛ ПРЕДЛОЖЕНИЕ ИСТЕКЛО\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "На ответ было 5 минут. Отправьте новое предложение.",
                parse_mode=None,
            )
        await callback.answer(msg, show_alert=True)
        return

    await callback.answer("Готово.")
    proposal = payload or {}
    proposer_id = int(proposal.get("proposer_id") or 0)
    target_id = int(proposal.get("target_id") or 0)
    proposer_name = _display_user_name(await db.get_user(proposer_id), fallback_id=proposer_id)
    target_name = _display_user_name(await db.get_user(target_id), fallback_id=target_id)
    if callback.message:
        if accept:
            await callback.message.edit_text(
                "💒 БРАК ЗАРЕГИСТРИРОВАН\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{proposer_name} ❤️ {target_name}\n"
                "Теперь у вас общий семейный статус.\n"
                "Команда: /family",
                parse_mode=None,
            )
        else:
            await callback.message.edit_text(
                "💔 ПРЕДЛОЖЕНИЕ ОТКЛОНЕНО\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"{target_name} отклонил(а) предложение от {proposer_name}.",
                parse_mode=None,
            )


@router.message(Command("divorce"))
async def family_divorce_command(message: Message, state: FSMContext):
    lowered = (message.text or "").lower()
    mode = "silent" if ("тихо" in lowered or "silent" in lowered) else "public"
    ok, msg, payload = await db.divorce_marriage(message.from_user.id, mode=mode)
    if not ok or not payload:
        await message.answer(f"❌ {msg}", parse_mode=None)
        return
    data = payload or {}
    spouse_id = int(data.get("spouse_id") or 0)
    spouse_name = _display_user_name(await db.get_user(spouse_id), fallback_id=spouse_id)
    days = int(data.get("days_together") or 0)
    if mode == "public" and message.chat.type in {"group", "supergroup"}:
        await message.answer(
            "⚖️ СЕМЕЙНЫЙ СТАТУС ОБНОВЛЕН\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Развод оформлен с {spouse_name}.\n"
            f"Стаж брака: {days} дн.",
            parse_mode=None,
        )
    else:
        await message.answer(
            f"✅ Развод оформлен. Стаж брака: {days} дн.\nПартнер: {spouse_name}",
            parse_mode=None,
        )


@router.message(Command("family"))
@router.callback_query(F.data == "family_menu")
async def family_menu(update, state: FSMContext):
    await _render_family_menu(update)


@router.callback_query(F.data == "family_pay_debt")
async def family_pay_debt(callback: CallbackQuery, state: FSMContext):
    ok, msg, payload = await db.pay_family_debt(callback.from_user.id, amount=None)
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    if ok and callback.message and payload:
        await callback.message.answer(
            "💸 СЕМЕЙНЫЙ ДОЛГ ОПЛАЧЕН\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Оплачено: {_lum(float(payload.get('paid_total') or 0))}\n"
            f"Остаток долга: {_lum(float(payload.get('debt_after') or 0))}",
            parse_mode=None,
        )
    await _render_family_menu(callback, answer_query=False)


@router.callback_query(F.data.startswith("family_rel_spend_"))
async def family_relationship_spend(callback: CallbackQuery, state: FSMContext):
    action_key = (callback.data or "").replace("family_rel_spend_", "", 1).strip()
    ok, msg, payload = await db.spend_on_partner(callback.from_user.id, action_key)
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    if ok and callback.message and payload:
        spouse_id = int(payload.get("partner_id") or 0)
        spouse_name = _display_user_name(await db.get_user(spouse_id), fallback_id=spouse_id)
        level_up = int(payload.get("level_up") or 0)
        level_after = int(payload.get("relationship_level") or 1)
        points_after = int(payload.get("relationship_points") or 0)
        next_points = int(payload.get("relationship_points_to_next") or 0)
        message_lines = [
            "💞 СЕМЕЙНАЯ ТРАТА",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Действие: {payload.get('action_title')}",
            f"Партнер: {spouse_name}",
            f"Списано: {_lum(float(payload.get('cost') or 0))}",
            f"Бонус отношений: +{int(payload.get('points_added') or 0)} очк.",
            f"Бонус репутации (обоим): +{float(payload.get('reputation_bonus') or 0):.2f}",
            f"Уровень отношений: {level_after}/25 ({points_after} очк.)",
        ]
        if next_points > 0:
            message_lines.append(f"До следующего уровня: {next_points} очк.")
        else:
            message_lines.append("Максимальный уровень отношений достигнут.")
        if level_up > 0:
            message_lines.append(f"🎉 Повышение: +{level_up} ур.")
        await callback.message.answer("\n".join(message_lines), parse_mode=None)
    await _render_family_menu(callback, answer_query=False)


@router.message(Command("familytop"))
@router.callback_query(F.data == "family_top")
async def family_top(update, state: FSMContext):
    if isinstance(update, CallbackQuery):
        await update.answer()
        message = update.message
        if message is None:
            return
    else:
        message = update

    rows = await db.list_marriage_top(limit=10)
    lines = ["🏆 ТОП БРАКОВ", "━━━━━━━━━━━━━━━━━━━━", ""]
    if not rows:
        lines.append("Пока нет активных браков.")
    else:
        for idx, row in enumerate(rows, start=1):
            lines.append(
                f"{idx}. {row.get('user1_name')} ❤️ {row.get('user2_name')} — "
                f"{int(row.get('days_together') or 0)} дн. | "
                f"ур. {int(row.get('relationship_level') or 1)}/25"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К семье", callback_data="family_menu")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
        ]
    )
    if isinstance(update, CallbackQuery):
        await message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode=None)
    else:
        await message.answer("\n".join(lines), reply_markup=keyboard, parse_mode=None)


@router.message(Command("pet"))
@router.callback_query(F.data == "pet_menu")
async def pet_menu(update, state: FSMContext):
    await _render_pet_menu(update)


@router.callback_query(F.data.startswith("pet_adopt_"))
async def pet_adopt(callback: CallbackQuery, state: FSMContext):
    pet_type = (callback.data or "").replace("pet_adopt_", "")
    ok, msg, payload = await db.adopt_pet(callback.from_user.id, pet_type, pet_name=PET_TYPE_LABELS.get(pet_type, "Питомец"))
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    if ok and callback.message and payload:
        await callback.message.answer(
            "🐾 Новый член семьи!\n"
            f"{payload.get('pet_title')} по имени {payload.get('pet_name')} теперь с вами.",
            parse_mode=None,
        )
    await _render_pet_menu(callback, answer_query=False)


@router.callback_query(F.data.startswith("pet_action_"))
async def pet_action(callback: CallbackQuery, state: FSMContext):
    action = (callback.data or "").replace("pet_action_", "")
    ok, msg, payload = await db.interact_with_pet(callback.from_user.id, action)
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    if ok and callback.message and payload:
        add = ""
        if int(payload.get("level_up") or 0) > 0:
            add = f"\n🎉 Уровень питомца повышен на {int(payload.get('level_up') or 0)}!"
        await callback.message.answer(
            f"🐾 {payload.get('pet_name')}: действие выполнено."
            f"\nСытость: {int(payload.get('hunger') or 0)}/100"
            f"\nНастроение: {int(payload.get('mood') or 0)}/100"
            f"\nЭнергия: {int(payload.get('energy') or 0)}/100"
            f"{add}",
            parse_mode=None,
        )
    await _render_pet_menu(callback, answer_query=False)


@router.callback_query(F.data == "pet_release")
async def pet_release(callback: CallbackQuery, state: FSMContext):
    ok, msg = await db.release_pet(callback.from_user.id)
    await callback.answer(("✅ " if ok else "❌ ") + msg, show_alert=not ok)
    await _render_pet_menu(callback, answer_query=False)


@router.message(Command("petname"))
async def pet_rename(message: Message, state: FSMContext):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("❌ Использование: /petname НовоеИмя", parse_mode=None)
        return
    ok, msg, payload = await db.rename_pet(message.from_user.id, parts[1].strip())
    if not ok:
        await message.answer(f"❌ {msg}", parse_mode=None)
        return
    await message.answer(
        f"✅ Питомец переименован: {payload.get('old_name')} -> {payload.get('new_name')}",
        parse_mode=None,
    )


@router.callback_query(F.data == "pet_loot_menu")
async def pet_loot_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    text = (
        "🎁 ЯЩИКИ ПИТОМЦЕВ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Откройте ящик и получите питомца с редкостью и бонусами.\n"
        "Важно: открыть можно только если у вас нет активного питомца.\n\n"
        "Типы ящиков:\n"
        "• Обычный — 5,000 люмов\n"
        "• Редкий — 15,000 люмов\n"
        "• Эпик — 40,000 люмов\n"
        "• Мифический — 90,000 люмов\n"
        "• Легендарный — 200,000 люмов"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Обычный", callback_data="pet_loot_open_common")],
            [InlineKeyboardButton(text="📦 Редкий", callback_data="pet_loot_open_rare")],
            [InlineKeyboardButton(text="📦 Эпик", callback_data="pet_loot_open_epic")],
            [InlineKeyboardButton(text="📦 Мифический", callback_data="pet_loot_open_myth")],
            [InlineKeyboardButton(text="📦 Легендарный", callback_data="pet_loot_open_legend")],
            [InlineKeyboardButton(text="🔙 К питомцу", callback_data="pet_menu")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=None)


@router.callback_query(F.data.startswith("pet_loot_open_"))
async def pet_loot_open(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    box_key = (callback.data or "").replace("pet_loot_open_", "").strip().lower()
    ok, msg, payload = await db.open_pet_lootbox(callback.from_user.id, box_key)
    if not ok:
        await callback.message.answer(f"❌ {msg}", parse_mode=None)
        await _render_pet_menu(callback, answer_query=False)
        return
    payload = payload or {}
    bonus_value = float(payload.get("bonus_value") or 0.0)
    await callback.message.answer(
        "🎉 Питомец получен!\n"
        f"Редкость: {payload.get('rarity')}\n"
        f"Питомец: {payload.get('pet_title')} {payload.get('pet_name')}\n"
        f"Бонус: -{bonus_value * 100:.0f}% к семейным расходам\n"
        f"Списано: {float(payload.get('price') or 0):,.2f} люмов",
        parse_mode=None,
    )
    await _render_pet_menu(callback, answer_query=False)


@router.message(F.reply_to_message, F.chat.type.in_({"group", "supergroup"}))
async def group_family_quick_actions(message: Message, state: FSMContext):
    raw = str(message.text or "")
    cmd = _normalize_reply_token(raw)
    if not cmd:
        return UNHANDLED
    if cmd in {"+", "плюс"}:
        await _apply_plus_reputation(message)
        return
    if cmd in {"брак", "marry"}:
        await _start_marriage_from_reply(message)
        return
    if cmd in RELATIONSHIP_REPLY_SPEND_MAP:
        target_user = message.reply_to_message.from_user if message.reply_to_message else None
        if not target_user or target_user.is_bot:
            await message.reply("❌ Ответьте на сообщение партнера по браку.", parse_mode=None)
            return
        ok, msg, payload = await db.spend_on_partner(
            actor_id=message.from_user.id,
            action_key=RELATIONSHIP_REPLY_SPEND_MAP[cmd],
            target_partner_id=int(target_user.id),
        )
        if not ok or not payload:
            await message.reply(f"❌ {msg}", parse_mode=None)
            return
        level_after = int(payload.get("relationship_level") or 1)
        points_after = int(payload.get("relationship_points") or 0)
        next_points = int(payload.get("relationship_points_to_next") or 0)
        level_up = int(payload.get("level_up") or 0)
        text = (
            f"💞 {message.from_user.full_name} устроил(а) '{payload.get('action_title')}' для партнера.\n"
            f"Списано: {_lum(float(payload.get('cost') or 0))}\n"
            f"Бонус отношений: +{int(payload.get('points_added') or 0)} очк.\n"
            f"Уровень отношений: {level_after}/25 ({points_after} очк.)"
        )
        if next_points > 0:
            text += f"\nДо следующего уровня: {next_points} очк."
        if level_up > 0:
            text += f"\n🎉 Повышение: +{level_up} ур."
        await message.reply(text, parse_mode=None)
        return
    if cmd in {"развод", "divorce"}:
        ok, msg, payload = await db.divorce_marriage(message.from_user.id, mode="public")
        if not ok:
            await message.reply(f"❌ {msg}", parse_mode=None)
            return
        spouse_id = int((payload or {}).get("spouse_id") or 0)
        spouse_name = _display_user_name(await db.get_user(spouse_id), fallback_id=spouse_id)
        await message.reply(
            f"⚖️ Развод оформлен публично. Партнер: {spouse_name}",
            parse_mode=None,
        )
        return
    if cmd not in SOCIAL_ACTIONS:
        return UNHANDLED

    target_user = message.reply_to_message.from_user if message.reply_to_message else None
    if not target_user:
        return UNHANDLED
    if target_user.is_bot:
        await message.reply("❌ С ботом взаимодействие недоступно.", parse_mode=None)
        return
    actor_id = int(message.from_user.id)
    target_id = int(target_user.id)
    if actor_id == target_id:
        await message.reply("❌ Нельзя использовать это действие на себе.", parse_mode=None)
        return

    await db.create_or_update_user(
        target_id,
        target_user.username or "",
        f"{target_user.first_name or ''} {target_user.last_name or ''}".strip(),
    )
    actor_name = _display_user_name(await db.get_user(actor_id), fallback_id=actor_id)
    target_name = _display_user_name(await db.get_user(target_id), fallback_id=target_id)
    verb = SOCIAL_ACTIONS[cmd]

    marriage = await db.get_active_marriage(actor_id)
    is_spouse = bool(marriage and int(marriage.get("spouse_id") or 0) == target_id)
    rep_bonus = 0.0
    if is_spouse and cmd in {"обнять", "поцеловать", "погладить"}:
        rep_bonus = 0.2
        target_user_data = await db.get_user(target_id) or {}
        new_rep = round(min(100.0, float(target_user_data.get("reputation") or 50.0) + rep_bonus), 2)
        await db.update_user(target_id, reputation=new_rep)
        rel_ok, _, rel_payload = await db.add_marriage_relationship_points(
            actor_id=actor_id,
            partner_id=target_id,
            points=4 if cmd == "поцеловать" else 3,
            reason=f"social:{cmd}",
        )
        if rel_ok and rel_payload:
            rel_level = int(rel_payload.get("relationship_level") or 1)
            rel_left = int(rel_payload.get("relationship_points_to_next") or 0)
            text_suffix = f"\n💞 Уровень отношений: {rel_level}/25."
            if rel_left > 0:
                text_suffix += f" До следующего: {rel_left} очк."
            if int(rel_payload.get("level_up") or 0) > 0:
                text_suffix += f" 🎉 +{int(rel_payload.get('level_up') or 0)} ур."
        else:
            text_suffix = ""
    else:
        text_suffix = ""

    text = f"💬 {actor_name} {verb} {target_name}."
    if is_spouse and rep_bonus > 0:
        text += f"\n💞 Семейная близость: +{rep_bonus:.1f} репутации для {target_name}."
        text += text_suffix
    await message.reply(text, parse_mode=None)


# ==================== ЕЖЕДНЕВНЫЕ НАЛОГИ ====================

@router.callback_query(F.data == "daily_tax_status")
@router.message(Command("tax"))
async def daily_tax_status(update, state: FSMContext):
    if isinstance(update, Message):
        user_id = update.from_user.id
        message = update
    else:
        user_id = update.from_user.id
        await update.answer()
        message = update.message
        if message is None:
            return

    user = await db.get_user(user_id) or {}
    status = await db.get_user_daily_tax_status(user_id)
    pending = status.get("pending") or {}
    latest = status.get("latest") or {}
    total_tax_charged = await db.get_user_total_tax_charged(user_id)
    total_tax_paid = await db.get_user_total_tax_paid(user_id)

    lines = [
        "🧾 ЕЖЕДНЕВНЫЕ НАЛОГИ",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Баланс: {_lum(float(user.get('balance') or 0))}",
        f"Налоговый долг: {_lum(float(user.get('tax_debt') or 0))}",
        f"Всего начислено: {_lum(total_tax_charged)}",
        f"Всего оплачено: {_lum(total_tax_paid)}",
        "",
    ]
    keyboard_rows: list[list[InlineKeyboardButton]] = []

    if pending:
        cycle_date = str(pending.get("cycle_date") or "")
        token = _tax_cycle_to_token(cycle_date)
        due_total = float(pending.get("total_due") or 0)
        living_tax = float(pending.get("living_tax") or 0)
        work_tax = float(pending.get("work_tax") or 0)
        property_tax = float(pending.get("property_tax") or 0)
        business_tax = float(pending.get("business_tax") or 0)
        private_org_tax = float(pending.get("private_org_tax") or 0)
        citizen_tax = float(pending.get("citizen_tax") or 0)
        if living_tax <= 0 and citizen_tax > 0:
            living_tax = min(citizen_tax, 5000.0)
        debt_interest = float(pending.get("debt_interest") or 0)
        scheduled_payment = float(pending.get("scheduled_payment") or 0)
        lines.extend(
            [
                f"Дата счета: {cycle_date}",
                f"К оплате сегодня: {_lum(due_total)}",
                f"• Налог на проживание: {_lum(living_tax)}",
                f"• Налог на работу: {_lum(work_tax)}",
                f"• Налог на недвижимость и капитал: {_lum(property_tax)}",
                f"• Налог на бизнесы и банды: {_lum(business_tax)}",
                f"• Налог на частные организации: {_lum(private_org_tax)}",
                f"• Проценты по долгу: {_lum(debt_interest)}",
                f"• Плановый платеж долга: {_lum(scheduled_payment)}",
                "",
                "Ставка налога:",
                "• 15% от общего имущества (все активы игрока).",
                "",
                "Оплатите до следующего налогового цикла, иначе начисление уйдет в долг.",
                "При просрочке дополнительно списывается штраф 1.5% от общего налогового долга.",
            ]
        )
        if token:
            keyboard_rows.append(
                [InlineKeyboardButton(text=f"💳 Оплатить {_lum(due_total)}", callback_data=f"daily_tax_pay_{token}")]
            )
    else:
        lines.append("✅ На сегодня неоплаченных налогов нет.")
        if latest:
            lines.append(f"Последний счет: {latest.get('cycle_date')} ({latest.get('status')})")

    keyboard_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="daily_tax_status")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await send_section_screen(
        update,
        text="\n".join(lines),
        reply_markup=keyboard,
        parse_mode=None,
        section_key="nalog",
    )


@router.callback_query(F.data.startswith("daily_tax_pay_"))
async def daily_tax_pay(callback: CallbackQuery, state: FSMContext):
    token = (callback.data or "").replace("daily_tax_pay_", "", 1)
    cycle_date = _tax_token_to_cycle(token)
    if not cycle_date:
        await callback.answer("❌ Некорректная дата платежа.", show_alert=True)
        return

    ok, msg, details = await db.pay_daily_tax_invoice(callback.from_user.id, cycle_date=cycle_date)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    await callback.answer("✅ Счет обработан.")
    paid_total = float(details.get("paid_total") or 0)
    debt_after = float(details.get("tax_debt_after") or 0)
    balance_after = float(details.get("balance_after") or 0)
    if details.get("president_exempt"):
        text = (
            "✅ Налоговый счет закрыт\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Президент освобожден от ежедневного налога.\n"
            f"Дата счета: {details.get('cycle_date')}\n"
            f"Баланс: {_lum(balance_after)}\n"
            f"Налоговый долг: {_lum(debt_after)}"
        )
    else:
        text = (
            "✅ Налог за день оплачен\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Дата: {details.get('cycle_date')}\n"
            f"Оплачено: {_lum(paid_total)}\n"
            f"Баланс после оплаты: {_lum(balance_after)}\n"
            f"Налоговый долг: {_lum(debt_after)}"
        )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧾 Статус налогов", callback_data="daily_tax_status")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
        ]
    )
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=None)


# ==================== CHARITY ====================

@router.callback_query(F.data == "charity_menu")
@router.message(Command("charity"))
async def charity_menu(update, state: FSMContext):
    await state.set_state(MainStates.main_menu)
    if isinstance(update, Message):
        user_id = update.from_user.id
        message = update
    else:
        user_id = update.from_user.id
        await update.answer()
        message = update.message
        if message is None:
            return

    user = await db.get_user(user_id) or {}
    lines = [
        "🤝 CHARITY-ФОНД МИРНАСТАНА",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Ваш баланс: {_lum(float(user.get('balance') or 0))}",
        "",
        "Пожертвования не исчезают из игры:",
        "• 70% идет в госбюджет",
        "• 30% идет в налоговую службу",
        "",
        "За пожертвование растет репутация.",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💝 Пожертвовать 1 000", callback_data="charity_donate_1000")],
            [InlineKeyboardButton(text="💝 Пожертвовать 5 000", callback_data="charity_donate_5000")],
            [InlineKeyboardButton(text="💝 Пожертвовать 20 000", callback_data="charity_donate_20000")],
            [InlineKeyboardButton(text="💝 Пожертвовать 100 000", callback_data="charity_donate_100000")],
            [InlineKeyboardButton(text="✍️ Ввести свою сумму", callback_data="charity_donate_custom")],
            [InlineKeyboardButton(text="🔙 В экономику", callback_data="menu_section_economy")],
        ]
    )
    await send_section_screen(
        update,
        text="\n".join(lines),
        reply_markup=keyboard,
        parse_mode=None,
        section_key="charity",
    )


@router.callback_query(F.data == "charity_donate_custom")
async def charity_donate_custom_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(MainStates.charity_custom_amount)
    if callback.message is not None:
        await callback.message.answer(
            "Введите сумму пожертвования (например: 7500):",
            reply_markup=get_back_button("🔙 Отмена", "charity_menu"),
            parse_mode=None,
        )


@router.callback_query(F.data.startswith("charity_donate_"))
async def charity_donate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MainStates.main_menu)
    raw = (callback.data or "").replace("charity_donate_", "", 1)
    if not raw.isdigit():
        await callback.answer("Некорректная сумма.", show_alert=True)
        return
    amount = float(raw)
    ok, msg, payload = await db.donate_to_charity(callback.from_user.id, amount)
    if not ok:
        await callback.answer(msg, show_alert=True)
        return
    payload = payload or {}
    await callback.answer("Пожертвование отправлено.")
    if callback.message is not None:
        await callback.message.answer(
            "✅ Charity выполнен\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Пожертвовано: {_lum(float(payload.get('amount') or 0))}\n"
            f"Бонус репутации: +{float(payload.get('rep_bonus') or 0):.2f}\n"
            f"В госбюджет: {_lum(float(payload.get('government_credit') or 0))}\n"
            f"В налоговую: {_lum(float(payload.get('tax_service_credit') or 0))}\n"
            f"Новый баланс: {_lum(float(payload.get('balance_after') or 0))}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🤝 Еще donation", callback_data="charity_menu")],
                    [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
                ]
            ),
            parse_mode=None,
        )


@router.message(MainStates.charity_custom_amount, F.text, ~F.text.startswith("/"))
async def charity_donate_custom_amount_input(message: Message, state: FSMContext):
    amount = _parse_money_amount(message.text or "")
    if amount is None:
        await message.answer(
            "❌ Некорректная сумма. Введите число больше нуля.",
            reply_markup=get_back_button("🔙 Отмена", "charity_menu"),
            parse_mode=None,
        )
        return
    ok, msg, payload = await db.donate_to_charity(message.from_user.id, amount)
    if not ok:
        await message.answer(
            f"❌ {msg}",
            reply_markup=get_back_button("🔙 К charity", "charity_menu"),
            parse_mode=None,
        )
        return
    await state.set_state(MainStates.main_menu)
    payload = payload or {}
    await message.answer(
        "✅ Charity выполнен\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Пожертвовано: {_lum(float(payload.get('amount') or 0))}\n"
        f"Бонус репутации: +{float(payload.get('rep_bonus') or 0):.2f}\n"
        f"В госбюджет: {_lum(float(payload.get('government_credit') or 0))}\n"
        f"В налоговую: {_lum(float(payload.get('tax_service_credit') or 0))}\n"
        f"Новый баланс: {_lum(float(payload.get('balance_after') or 0))}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🤝 Еще donation", callback_data="charity_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
            ]
        ),
        parse_mode=None,
    )


@router.message(MainStates.charity_custom_amount)
async def charity_donate_custom_amount_invalid(message: Message):
    await message.answer(
        "❌ Отправьте сумму обычным текстом (например: 10000).",
        reply_markup=get_back_button("🔙 Отмена", "charity_menu"),
        parse_mode=None,
    )


# ==================== ЕЖЕДНЕВНЫЙ БОНУС ====================

@router.callback_query(F.data == "daily_bonus")
@router.message(Command("daily"))
async def daily_bonus(update, state: FSMContext):
    """Получить ежедневный бонус"""
    
    if isinstance(update, Message):
        user_id = update.from_user.id
        message = update
    else:
        user_id = update.from_user.id
        await update.answer()
        message = update.message
        if message is None:
            return
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ История не найдена")
        return
    
    today = datetime.now().date().isoformat()
    
    # Проверяем, а уже ли получал бонус сегодня
    last_daily_bonus = str(user.get('last_daily_bonus') or "")
    if last_daily_bonus.startswith(today):
        await message.answer(
            "⏳ **Вы уже получали бонус сегодня!**\n"
            "Приходите завтра для нового раунда.",
            reply_markup=get_back_button()
        )
        return
    
    # Выдаем бонус (случайное значение от 250 до 900)
    import random
    bonus = random.randint(250, 900)
    
    new_balance = float(user.get('balance', 0) or 0) + bonus
    await db.update_user(user_id, balance=new_balance, last_daily_bonus=datetime.now().isoformat())
    
    bonus_text = (
        f"✅ **БОНУС ПОЛУЧЕН!**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 **+${bonus:,}**\n\n"
        f"Ваш новый баланс: ${new_balance:,.0f}\n\n"
        f"⏰ Следующий бонус доступен через 24 часа."
    )
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    
    if isinstance(update, Message):
        await message.answer(bonus_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
    else:
        await message.edit_text(bonus_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')
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

    created = await db.ensure_presidential_election(duration_hours=15)
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
        display = _display_user_name(player, fallback_id=target_id)
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
    async with db._connect() as conn:
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
async def election_view_brief(callback: CallbackQuery, callback_data: ElectionCallback, state: FSMContext):
    """Совместимость со старой кнопкой view."""
    await election_view_party(callback, callback_data, state)


@router.callback_query(ElectionCallback.filter(F.action == "view_party"))
async def election_view_party(callback: CallbackQuery, callback_data: ElectionCallback, state: FSMContext):
    """Главное меню выборов."""
    await callback.answer()
    await state.set_state(ElectionStates.global_lock)

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
        buttons.append([
            InlineKeyboardButton(
                text="🔁 Сменить/покинуть партию",
                callback_data=PartyCallback(action="leave", party_id=user_party['id'], election_id=election_id).pack(),
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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ])

    await _safe_edit(callback, "\n".join(text_lines), InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(ElectionCallback.filter(F.action == "stage_next"))
async def election_stage_next(callback: CallbackQuery, callback_data: ElectionCallback):
    """Ручной перевод этапов отключен: этапы меняются автоматически."""
    await callback.answer()

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
    text = (
        "ℹ️ Этапы выборов меняются автоматически по времени.\n"
        f"Текущий этап: {stage_label}"
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
            author = _display_user_name(row, fallback_id=int(row.get("user_id") or 0))
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


@router.message(ElectionStates.debate_message, F.text, ~F.text.startswith("/"))
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

    await state.set_state(ElectionStates.party_name_input)
    await state.update_data(election_id=election_id)

    await callback.message.answer(
        "🟢 Введите название партии (2-32 символа).\n"
        "Разрешены буквы, цифры, пробел и дефис.",
        reply_markup=_election_back_markup(election_id),
        parse_mode=None,
    )


@router.message(ElectionStates.party_name_input, F.text, ~F.text.startswith("/"))
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
        "Лидер партии автоматически добавлен в кандидаты.\n"
        "Теперь можно приглашать участников и вести кампанию.",
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
        cand_name = _display_user_name(cand, fallback_id=int(cand.get('candidate_id') or 0))
        party_name = cand.get('party_name')
        party_chunk = f" | Партия: {party_name}" if party_name else ""
        text += f"{idx}. {cand_name}{party_chunk} — {cand.get('votes', 0)} голосов\n"

    buttons = []
    if not already_voted:
        for cand in candidates:
            cand_name = _display_user_name(cand, fallback_id=int(cand.get('candidate_id') or 0))
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
    candidate_name = _display_user_name(candidate or {}, fallback_id=candidate_id)

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
        cand_name = _display_user_name(cand, fallback_id=int(cand.get('candidate_id') or 0))
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

        is_own_party = bool(user_party and int(user_party.get('id') or -1) == int(p.get('id') or -2))
        if (not is_own_party) and int(p.get('leader_id') or 0) != user_id:
            join_label = f"➕ Вступить: {pname}" if not user_party else f"🔁 Перейти: {pname}"
            buttons.append([
                InlineKeyboardButton(
                    text=join_label,
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

    if int(party.get('leader_id') or 0) == user_id:
        await _safe_edit(callback, "❌ Вы уже лидер этой партии.", _election_back_markup(election_id))
        return

    election = await db.get_election(election_id)
    if not election or str(election.get("status") or "") != "active":
        await _safe_edit(callback, "❌ Выборы уже завершены.", _election_back_markup(election_id))
        return

    current_party = await db.get_user_party_for_election(user_id, election_id)
    switch_note = ""
    if current_party:
        if int(current_party.get("id") or -1) == party_id:
            await _safe_edit(callback, "❌ Вы уже состоите в этой партии.", _election_back_markup(election_id))
            return
        left_ok, left_msg = await db.leave_party_for_election(user_id, election_id)
        if not left_ok:
            await _safe_edit(callback, left_msg, _election_back_markup(election_id))
            return
        switch_note = f"{left_msg}\n"

    now = datetime.now().isoformat()
    async with db._connect() as conn:
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
            inviter_user = await db.get_user(user_id)
            display_name = _display_user_name(inviter_user or {}, fallback_id=user_id)
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

    await _safe_edit(callback, f"{switch_note}✅ Запрос отправлен лидеру партии.", _election_back_markup(election_id))


@router.callback_query(PartyCallback.filter(F.action == "leave"))
async def party_leave(callback: CallbackQuery, callback_data: PartyCallback):
    """Покинуть текущую партию, чтобы вступить в другую."""
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
    if not election or str(election.get("status") or "") != "active":
        await _safe_edit(callback, "❌ Выборы уже завершены.", _election_back_markup(election_id))
        return

    current_party = await db.get_user_party_for_election(user_id, election_id)
    if not current_party:
        await _safe_edit(callback, "❌ Вы не состоите в партии.", _election_back_markup(election_id))
        return

    ok, msg = await db.leave_party_for_election(user_id, election_id)
    if not ok:
        await _safe_edit(callback, msg, _election_back_markup(election_id))
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Выбрать новую партию", callback_data=ElectionCallback(action="list_parties", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🟢 Создать свою партию", callback_data=ElectionCallback(action="create_party", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 В меню выборов", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
    ])
    await _safe_edit(callback, msg, keyboard)


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

    if int(party.get("election_id") or -1) != election_id:
        await _safe_edit(callback, "❌ Заявка относится к другим выборам.", _election_back_markup(election_id))
        return

    election = await db.get_election(election_id)
    if not election or str(election.get("status") or "") != "active":
        await _safe_edit(callback, "❌ Выборы уже завершены.", _election_back_markup(election_id))
        return

    if int(party.get('leader_id') or 0) != leader_id:
        await callback.answer("❌ Только лидер партии может обрабатывать заявки.", show_alert=True)
        return

    async with db._connect() as conn:
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

        async with db._connect() as conn:
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
        async with db._connect() as conn:
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
    election_id = int(callback_data.election_id or -1)
    if election_id <= 0:
        election_id = await _resolve_active_election_id(callback_data.election_id)
    if election_id <= 0:
        await _safe_edit(
            callback,
            "❌ Не удалось определить выборы для этой партии.",
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
        member_name = _display_user_name(member, fallback_id=int(member.get("user_id") or 0))
        text += f"{idx}. {member_name} ({role})\n"

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
    requested_party_id = int(callback_data.party_id or -1)
    party = await db.get_party(requested_party_id) if requested_party_id > 0 else None
    if not party:
        election_id = int(callback_data.election_id or -1)
        if election_id > 0:
            party = await db.get_party_by_leader(user_id, election_id)
        if not party:
            fallback_election_id = await _resolve_active_election_id(callback_data.election_id)
            if fallback_election_id > 0:
                party = await db.get_party_by_leader(user_id, fallback_election_id)

    if not party:
        await _safe_edit(
            callback,
            "❌ Партия не найдена или вы не лидер партии.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]])
        )
        return

    if int(party.get("leader_id") or 0) != user_id:
        election_id = int(party.get("election_id") or -1)
        await _safe_edit(callback, "❌ Только лидер партии может отправлять приглашения.", _election_back_markup(election_id))
        return

    election_id = int(party.get("election_id") or -1)
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

    invited_name = _display_user_name(invited_user or {}, fallback_id=invited_user_id)
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
    election_id = int(callback_data.election_id or -1)

    if party_id <= 0:
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

    party_election_id = int(party.get("election_id") or -1)
    if election_id > 0 and party_election_id != election_id:
        await _safe_edit(callback, "❌ Приглашение относится к другим выборам.", _election_back_markup(election_id))
        return

    election_id = party_election_id

    async with db._connect() as conn:
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
        switch_note = ""
        current_party = await db.get_user_party_for_election(user_id, election_id)
        if current_party and int(current_party.get("id") or -1) != party_id:
            left_ok, left_msg = await db.leave_party_for_election(user_id, election_id)
            if not left_ok:
                await _safe_edit(callback, left_msg, _election_back_markup(election_id))
                return
            switch_note = f"{left_msg}\n"

        success, msg = await db.add_party_member(party_id, user_id)
        if not success:
            await _safe_edit(callback, f"❌ Не удалось вступить в партию: {msg}", _election_back_markup(election_id))
            return

        async with db._connect() as conn:
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

        await _safe_edit(callback, f"{switch_note}✅ Вы вступили в партию '{party.get('name')}'.", _election_back_markup(election_id))
    else:
        async with db._connect() as conn:
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

