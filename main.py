"""
main.py - точка входа Telegram-бота на aiogram 3.x (асинхронный)
"""

import asyncio
import json
import logging
import os
import warnings
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

# Загружаем .env до импорта внутренних модулей, чтобы настройки были доступны в import-time.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# Подавляем предупреждение pydantic об aiogram
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    CallbackQuery,
    ChatMemberUpdated,
    Message,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods.base import TelegramType

# Импорт твоих модулей
from database import db
from middlewares import (
    ActionBanMiddleware,
    EnsureUserMiddleware,
    MandatoryNicknameMiddleware,
    RateLimitMiddleware,
)
from handlers_part1 import router as main_router
from handlers_part2 import router as handlers_part2_router
from handlers_part3 import router as handlers_part3_router
from feature_pack import router as feature_router
from presidential_admin import router as presidential_router
from fbi_intercept import router as fbi_router
from revolutions import router as revolution_router
from economy import run_daily_economy_cycle, run_state_money_print_processor
from ai_governance import run_ai_governance_cycle

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)

TOKEN = os.getenv("BOT_TOKEN")
INSTANCE_LOCK_PATH = os.path.join(BASE_DIR, ".bot_instance.lock")


class _AiogramDispatcherNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage() or "").lower()
        if "telegramconflicterror" in msg:
            return False
        if "terminated by other getupdates request" in msg:
            return False
        if "failed to fetch updates" in msg and "conflict" in msg:
            return False
        if "sleep for" in msg and "try again" in msg and "bot id" in msg:
            return False
        return True


logging.getLogger("aiogram.dispatcher").addFilter(_AiogramDispatcherNoiseFilter())


class SingleInstanceLock:
    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fh = None
        self._locked = False

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        try:
            self._fh = open(self.lock_path, "a+", encoding="utf-8")
            self._fh.seek(0)
            if not self._fh.read(1):
                self._fh.seek(0)
                self._fh.write("0")
                self._fh.flush()
            self._fh.seek(0)
        except Exception:
            try:
                if self._fh is not None:
                    self._fh.close()
            except Exception:
                pass
            self._fh = None
            self._locked = False
            return False

        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            self._locked = False
            return False

        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        self._locked = True
        return True

    def release(self) -> None:
        if not self._fh:
            return
        try:
            if self._locked:
                if os.name == "nt":
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self._fh.close()
        except Exception:
            pass
        self._fh = None
        self._locked = False

# Универсальная защита от edit_text на фото-сообщениях.
if not getattr(Message, "_safe_edit_text_patched", False):
    _ORIG_EDIT_TEXT = Message.edit_text

    async def _safe_edit_text(self: Message, text: str, *args, **kwargs):
        safe_text = str(text or "")
        if len(safe_text) > 4000:
            safe_text = safe_text[:3997] + "..."
        if getattr(self, "photo", None):
            if len(args) >= 1 and "reply_markup" not in kwargs:
                kwargs["reply_markup"] = args[0]
            if len(args) >= 2 and "parse_mode" not in kwargs:
                kwargs["parse_mode"] = args[1]
            # У подписи Telegram жесткий лимит 1024 символа; для длинных экранов
            # отправляем обычное текстовое сообщение вместо падения.
            if len(safe_text) > 1024:
                return await self.answer(
                    safe_text,
                    reply_markup=kwargs.get("reply_markup"),
                    parse_mode=kwargs.get("parse_mode"),
                )
            try:
                return await self.edit_caption(caption=safe_text, **kwargs)
            except TelegramBadRequest as exc:
                err = str(exc).lower()
                if "media_caption_too_long" in err or "caption is too long" in err:
                    return await self.answer(
                        safe_text,
                        reply_markup=kwargs.get("reply_markup"),
                        parse_mode=kwargs.get("parse_mode"),
                    )
                raise
        return await _ORIG_EDIT_TEXT(self, safe_text, *args, **kwargs)

    Message.edit_text = _safe_edit_text
    Message._safe_edit_text_patched = True


def _read_float_env(name: str, default: float) -> float:
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _read_int_env(name: str, default: int, *, min_value: int | None = None) -> int:
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if min_value is not None and parsed < min_value:
        return default
    return parsed


def _read_admin_ids() -> set[int]:
    admin_ids = {6000066043}
    raw = (os.getenv("ADMIN_IDS") or "").replace(";", ",")
    for chunk in raw.split(","):
        candidate = chunk.strip()
        if candidate.isdigit():
            admin_ids.add(int(candidate))
    return admin_ids


TELEGRAM_REQUEST_TIMEOUT = _read_float_env("TELEGRAM_REQUEST_TIMEOUT", 20.0)
BOT_ADMIN_IDS = _read_admin_ids()
ADMIN_ENABLE_CODE = (os.getenv("ADMIN_ENABLE_CODE") or "MIRNASTAN01").strip().upper()
ADMIN_DISABLE_CODE = (os.getenv("ADMIN_DISABLE_CODE") or "MIRNASTAN00").strip().upper()

try:
    UZBEKISTAN_TZ = ZoneInfo("Asia/Tashkent")
except ZoneInfoNotFoundError:
    logger.warning("tzdata не найдена, используем fallback UTC+5 для времени Узбекистана.")
    UZBEKISTAN_TZ = timezone(timedelta(hours=5), name="UTC+5")
WORK_START_HOUR = 8
WORK_END_HOUR = 21
SHUTDOWN_WARNING_HOUR = 20
SHUTDOWN_WARNING_MINUTE = 50

runtime_state: dict[str, Any] = {
    "is_online": False,
    "force_online": False,
    "last_warning_date": None,
    "last_media_news_slot": None,
}
session_startup_announced_groups: set[int] = set()
session_offline_start_notified_groups: set[int] = set()

STARTUP_TEXT = (
    "🟢 Мирнастан онлайн\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Бот включился и готов к работе.\n"
    "🕗 Режим: 24/7 (Asia/Tashkent, UTC+5)."
)
PROCESS_STARTED_OFFLINE_TEXT = (
    "🛠 Мирнастан запущен\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Бот работает 24/7 и готов к взаимодействию."
)
SHUTDOWN_WARNING_TEXT = (
    "⚠️ Внимание\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "Бот работает 24/7 и не планируется к отключению."
)
MEDIA_NEWS_GROUP_BROADCAST_ENABLED = os.getenv("MEDIA_NEWS_GROUP_BROADCAST_ENABLED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}
LOCAL_SERVER_ENABLED = os.getenv("LOCAL_SERVER_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
LOCAL_SERVER_HOST = os.getenv("LOCAL_SERVER_HOST", "127.0.0.1")
LOCAL_SERVER_PORT = _read_int_env("LOCAL_SERVER_PORT", 8787, min_value=1)
GROUP_ACTIVITY_SYNC_SECONDS = _read_float_env("GROUP_ACTIVITY_SYNC_SECONDS", 45.0)
_group_sync_cache: dict[int, float] = {}
_group_sync_cache_cleanup_at = 0.0


def is_working_hours(now: datetime) -> bool:
    start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    end = now.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    return start <= now < end


def get_next_start_time(now: datetime) -> datetime:
    today_start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    if now < today_start:
        return today_start
    return (now + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)


def should_sync_group_chat(chat_id: int) -> bool:
    """Троттлинг апдейтов активности групп в БД, чтобы снизить лишнюю нагрузку."""
    global _group_sync_cache_cleanup_at

    now = monotonic()
    safe_chat_id = int(chat_id)
    last_sync = _group_sync_cache.get(safe_chat_id)
    if last_sync is not None and (now - last_sync) < GROUP_ACTIVITY_SYNC_SECONDS:
        return False
    _group_sync_cache[safe_chat_id] = now

    if len(_group_sync_cache) > 5000 and now > _group_sync_cache_cleanup_at:
        cutoff = now - (GROUP_ACTIVITY_SYNC_SECONDS * 3)
        stale_ids = [cid for cid, ts in _group_sync_cache.items() if ts < cutoff]
        for cid in stale_ids:
            _group_sync_cache.pop(cid, None)
        _group_sync_cache_cleanup_at = now + 120

    return True


async def _is_activation_admin(message: Message) -> bool:
    user = message.from_user
    if not user:
        return False
    if user.id in BOT_ADMIN_IDS:
        return True
    if message.chat.type not in {"group", "supergroup"}:
        return False
    try:
        member = await message.bot.get_chat_member(message.chat.id, user.id)
    except Exception:
        logger.exception("Не удалось проверить права пользователя %s в чате %s", user.id, message.chat.id)
        return False
    return member.status in {"administrator", "creator"}


class TelegramRetryMiddleware(BaseRequestMiddleware):
    """Ретраи для временных ошибок Telegram API."""

    def __init__(self, retries: int = 2, base_delay: float = 1.0):
        self.retries = max(0, int(retries))
        self.base_delay = max(0.2, float(base_delay))

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method,
    ):
        attempt = 0
        while True:
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                if type(method).__name__ == "AnswerCallbackQuery":
                    logger.debug(
                        "Flood control on callback answer; skip retry (retry_after=%.1f sec)",
                        float(getattr(exc, "retry_after", 0) or 0),
                    )
                    return True
                attempt += 1
                if attempt > self.retries:
                    raise
                wait_seconds = max(float(getattr(exc, "retry_after", 1)), self.base_delay)
                logger.warning(
                    "Flood control for %s, retry in %.1f sec (%s/%s)",
                    type(method).__name__,
                    wait_seconds,
                    attempt,
                    self.retries,
                )
                await asyncio.sleep(wait_seconds)
            except (TelegramNetworkError, TelegramServerError) as exc:
                attempt += 1
                if attempt > self.retries:
                    raise
                wait_seconds = self.base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Telegram API transient error for %s: %s. Retry in %.1f sec (%s/%s)",
                    type(method).__name__,
                    exc,
                    wait_seconds,
                    attempt,
                    self.retries,
                )
                await asyncio.sleep(wait_seconds)


MOJIBAKE_WEIRD_CHARS = set("ЂЃ‚ѓ„…†‡€‰Љ‹ЊЌЋЏђ‘’“”•–—™љ›ќћџў")
MOJIBAKE_TOKENS = ("рџ", "пё", "вЂ")


def _looks_like_mojibake(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    if any(token in text for token in MOJIBAKE_TOKENS):
        return True
    if any(ch in MOJIBAKE_WEIRD_CHARS for ch in text):
        return True
    return False


def _repair_mojibake(text: str) -> str:
    if not _looks_like_mojibake(text):
        return text

    best = text
    for source_encoding in ("cp1251", "latin1"):
        try:
            candidate = text.encode(source_encoding).decode("utf-8")
        except UnicodeError:
            continue
        if not candidate:
            continue
        # Берем вариант только если он действительно устраняет "битые" паттерны.
        if not _looks_like_mojibake(candidate):
            return candidate
        if len(candidate) >= len(best) and candidate.count("�") < best.count("�"):
            best = candidate
    return best


class TextSanitizerRequestMiddleware(BaseRequestMiddleware):
    """Чинит mojibake в исходящих методах Telegram API (текст и кнопки)."""

    TEXT_ATTRS = ("text", "caption", "question", "explanation", "title", "message")

    def _sanitize_markup(self, markup: Any) -> None:
        if markup is None:
            return
        for attr in ("inline_keyboard", "keyboard"):
            rows = getattr(markup, attr, None)
            if not rows:
                continue
            for row in rows:
                for button in row or []:
                    label = getattr(button, "text", None)
                    if not isinstance(label, str) or not label:
                        continue
                    fixed = _repair_mojibake(label)
                    if fixed != label:
                        try:
                            button.text = fixed
                        except Exception:
                            pass

    def _sanitize_method(self, method: Any) -> None:
        for attr in self.TEXT_ATTRS:
            value = getattr(method, attr, None)
            if not isinstance(value, str) or not value:
                continue
            fixed = _repair_mojibake(value)
            if fixed != value:
                try:
                    setattr(method, attr, fixed)
                except Exception:
                    pass

        self._sanitize_markup(getattr(method, "reply_markup", None))

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method,
    ):
        try:
            self._sanitize_method(method)
        except Exception:
            # Санитайзер не должен ломать отправку.
            logger.exception("Ошибка санитайзера текста в методе %s", type(method).__name__)
        return await make_request(bot, method)


class TransientTelegramErrorMiddleware(BaseMiddleware):
    """Не даем временным сетевым ошибкам разваливать обработку update."""

    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except (TelegramNetworkError, TelegramServerError) as exc:
            logger.warning("Временная ошибка Telegram API во время обработки update: %s", exc)
            return None
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            if "message is not modified" in err:
                return None
            if "media_caption_too_long" in err or "caption is too long" in err:
                logger.debug("Пропущена длинная подпись media в update: %s", exc)
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("Экран слишком длинный, откройте меню заново через /start.", show_alert=True)
                    except Exception:
                        pass
                return None
            if "bot was blocked by the user" in err or "chat not found" in err or "user is deactivated" in err:
                logger.debug("Сообщение не доставлено: %s", exc)
                return None
            raise
        except Exception:
            logger.exception("Необработанная ошибка в обработчике update")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⚠️ Внутренняя ошибка. Нажмите кнопку еще раз или /start.", show_alert=True)
                except Exception:
                    pass
                return None
            if isinstance(event, Message):
                try:
                    await event.answer("⚠️ Внутренняя ошибка. Повторите действие позже или откройте /start.")
                except Exception:
                    pass
                return None
            return None


class WorkingHoursMiddleware(BaseMiddleware):
    """Ограничивает обработку команд рабочим временем 08:00-21:00 (Asia/Tashkent)."""

    def __init__(self, state: dict[str, Any]):
        self.state = state

    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            raw_text = (event.text or "").strip().upper()
            if raw_text in {ADMIN_ENABLE_CODE, ADMIN_DISABLE_CODE}:
                if not await _is_activation_admin(event):
                    await event.answer("❌ Этот код доступен только администратору.", parse_mode=None)
                    return

                if raw_text == ADMIN_ENABLE_CODE:
                    if self.state.get("force_online") and self.state.get("is_online"):
                        await event.answer("✅ Бот уже работает в принудительном режиме.", parse_mode=None)
                        return
                    self.state["force_online"] = True
                    self.state["is_online"] = True
                    self.state["last_warning_date"] = None
                    session_offline_start_notified_groups.clear()
                    session_startup_announced_groups.clear()
                    sent_ids = await broadcast_to_active_groups(event.bot, STARTUP_TEXT)
                    session_startup_announced_groups.update(sent_ids)
                    await event.answer("✅ Бот принудительно включен администратором.", parse_mode=None)
                    logger.info("Принудительное включение бота админом %s", event.from_user.id if event.from_user else "unknown")
                    return

                self.state["force_online"] = False
                now_local = datetime.now(UZBEKISTAN_TZ)
                self.state["is_online"] = is_working_hours(now_local)
                mode_text = (
                    "✅ Принудительный режим отключен. Бот работает по расписанию."
                    if self.state["is_online"]
                    else "✅ Принудительный режим отключен. Сейчас бот вне рабочего времени."
                )
                await event.answer(mode_text, parse_mode=None)
                logger.info("Принудительный режим выключен админом %s", event.from_user.id if event.from_user else "unknown")
                return

        if self.state.get("is_online") or self.state.get("force_online"):
            return await handler(event, data)

        now = datetime.now(UZBEKISTAN_TZ)
        next_start = get_next_start_time(now)

        if isinstance(event, Message):
            if event.chat.type in {"group", "supergroup"}:
                # Даже вне рабочего окна обновляем реестр групп, чтобы утренние рассылки работали.
                if should_sync_group_chat(event.chat.id):
                    await db.upsert_bot_chat(
                        chat_id=event.chat.id,
                        chat_type=event.chat.type,
                        title=event.chat.title or "",
                    )
                if event.chat.id not in session_offline_start_notified_groups:
                    try:
                        await event.bot.send_message(event.chat.id, PROCESS_STARTED_OFFLINE_TEXT, parse_mode=None)
                        session_offline_start_notified_groups.add(event.chat.id)
                    except Exception:
                        logger.exception("Не удалось отправить оффлайн-уведомление в чат %s", event.chat.id)
                return
            if event.chat.type == "private":
                await event.answer(
                    "⏸ Бот временно недоступен. Попробуйте позже."
                )
            return

        if isinstance(event, CallbackQuery):
            await event.answer(
                "⏸ Бот временно недоступен. Попробуйте позже.",
                show_alert=True,
            )
            return

        return


service_router = Router()


@service_router.my_chat_member()
async def track_bot_membership(update: ChatMemberUpdated):
    """Фиксируем добавление/удаление бота в группах."""
    chat = update.chat
    if chat.type not in {"group", "supergroup"}:
        return

    status = update.new_chat_member.status
    if status in {"member", "administrator", "creator", "restricted"}:
        await db.upsert_bot_chat(
            chat_id=chat.id,
            chat_type=chat.type,
            title=chat.title or "",
        )
        if runtime_state.get("is_online") and chat.id not in session_startup_announced_groups:
            try:
                await update.bot.send_message(chat.id, STARTUP_TEXT, parse_mode=None)
                session_startup_announced_groups.add(chat.id)
            except Exception:
                logger.exception("Не удалось отправить приветствие в чат %s", chat.id)
        logger.info("Чат %s зарегистрирован как активный", chat.id)
        return

    if status in {"left", "kicked"}:
        await db.deactivate_bot_chat(chat.id)
        logger.info("Чат %s помечен неактивным", chat.id)


@service_router.message(
    F.chat.type.in_({"group", "supergroup"}),
    ~F.reply_to_message,
    ~F.text.startswith("/"),
)
async def track_group_activity(message: Message):
    """
    Обновляем реестр групп при активности.
    Это помогает сохранить список чатов даже при редких my_chat_member update.
    """
    if should_sync_group_chat(message.chat.id):
        await db.upsert_bot_chat(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            title=message.chat.title or "",
        )
    if runtime_state.get("is_online") and message.chat.id not in session_startup_announced_groups:
        try:
            await message.bot.send_message(message.chat.id, STARTUP_TEXT, parse_mode=None)
            session_startup_announced_groups.add(message.chat.id)
        except Exception:
            logger.exception("Не удалось отправить стартовое сообщение в чат %s", message.chat.id)

    # В этом сервисном хендлере только поддерживаем реестр групп.
    # Игровые reply-команды и реакции обрабатываются профильными роутерами.
    return UNHANDLED


async def broadcast_to_active_groups(bot: Bot, text: str) -> set[int]:
    chats = await db.get_active_group_chats()
    if not chats:
        logger.info("Нет активных групп для рассылки")
        return set()

    sent = 0
    failed = 0
    sent_chat_ids: set[int] = set()
    for chat in chats:
        chat_id = int(chat["chat_id"])
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
            sent += 1
            sent_chat_ids.add(chat_id)
        except Exception as exc:
            failed += 1
            error_text = str(exc).lower()
            if any(token in error_text for token in ("forbidden", "kicked", "chat not found")):
                await db.deactivate_bot_chat(chat_id)

    logger.debug("Групповая рассылка завершена: отправлено=%s, ошибок=%s", sent, failed)
    return sent_chat_ids


async def run_work_hours_controller(bot: Bot, state: dict[str, Any]):
    """Переключает доступность бота по расписанию и делает системные рассылки."""
    while True:
        try:
            if state.get("force_online"):
                if not state.get("is_online"):
                    state["is_online"] = True
                    state["last_warning_date"] = None
                    logger.info("Рабочий режим: ONLINE (принудительно)")
                await asyncio.sleep(5)
                continue

            now = datetime.now(UZBEKISTAN_TZ)
            today = now.date().isoformat()
            online_now = is_working_hours(now)

            if online_now and not state.get("is_online"):
                state["is_online"] = True
                state["last_warning_date"] = None
                session_offline_start_notified_groups.clear()
                session_startup_announced_groups.clear()
                sent_ids = await broadcast_to_active_groups(bot, STARTUP_TEXT)
                session_startup_announced_groups.update(sent_ids)
                logger.info("Рабочий режим: ONLINE")

            if not online_now and state.get("is_online"):
                state["is_online"] = False
                logger.info("Рабочий режим: OFFLINE")

            warning_time = now.replace(
                hour=SHUTDOWN_WARNING_HOUR,
                minute=SHUTDOWN_WARNING_MINUTE,
                second=0,
                microsecond=0,
            )
            if state.get("is_online") and now >= warning_time and state.get("last_warning_date") != today:
                await broadcast_to_active_groups(bot, SHUTDOWN_WARNING_TEXT)
                state["last_warning_date"] = today
        except Exception:
            logger.exception("Ошибка в контроллере рабочего времени")

        await asyncio.sleep(5)


def _media_news_slot_key(now: datetime, *, period_minutes: int = 10) -> str:
    safe_period = max(1, int(period_minutes or 10))
    slot_minute = (now.minute // safe_period) * safe_period
    return now.strftime("%Y-%m-%d %H:") + f"{slot_minute:02d}"


async def run_media_news_digest(bot: Bot, state: dict[str, Any], period_minutes: int = 10):
    """Генерирует и рассылает СМИ-новость раз в N минут (по умолчанию 10)."""
    safe_period = max(1, int(period_minutes or 10))
    state_key = "last_media_news_slot"
    persisted_state_key = "media_last_news_slot"
    while True:
        try:
            now = datetime.now(UZBEKISTAN_TZ)
            key = _media_news_slot_key(now, period_minutes=safe_period)
            last_key = state.get(state_key)
            if last_key is None:
                persisted_key = await db.get_system_state(persisted_state_key)
                if not persisted_key:
                    # Fallback со старого hourly-ключа (для плавной миграции).
                    persisted_key = await db.get_system_state("media_last_hourly_news_key")
                state[state_key] = persisted_key or ""
                last_key = state[state_key]
            if (
                state.get("is_online")
                and last_key != key
            ):
                news = await db.generate_hourly_news()
                if news:
                    created = str(news.get("created_date") or "")
                    created_short = created[11:16] if len(created) >= 16 else "сейчас"
                    severity = str(news.get("severity") or "normal").strip().lower()
                    severity_label = {
                        "critical": "🔥 критично",
                        "high": "⚠️ важное",
                        "hot": "📣 горячее",
                    }.get(severity, "🟢 обычное")
                    source = str(news.get("source_name") or "").strip()
                    text = (
                        "📰 ЛЕНТА СМИ MIRNASTAN\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🕙 {created_short} | {severity_label}\n\n"
                        f"Заголовок: {news.get('title')}\n\n"
                        f"{news.get('body')}\n"
                        + (f"\nИсточник: {source}" if source else "")
                    )
                    if MEDIA_NEWS_GROUP_BROADCAST_ENABLED:
                        await broadcast_to_active_groups(bot, text)
                    state[state_key] = key
                    await db.set_system_state(persisted_state_key, key)
        except Exception:
            logger.exception("Ошибка в задаче новостей СМИ")
        await asyncio.sleep(15)


async def run_local_health_server(state: dict[str, Any]):
    """Локальный HTTP health endpoint для мониторинга процесса."""
    async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            # Читаем только заголовки запроса; содержимое не требуется.
            try:
                await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2.0)
            except Exception:
                pass

            now = datetime.now(UZBEKISTAN_TZ)
            payload = {
                "status": "ok",
                "time_uz": now.isoformat(),
                "is_online": bool(state.get("is_online")),
                "work_window": f"{WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00",
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
            )
            writer.write(headers + body)
            await writer.drain()
        except Exception:
            logger.exception("Ошибка обработки запроса локального сервера")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    try:
        server = await asyncio.start_server(_handle_client, host=LOCAL_SERVER_HOST, port=LOCAL_SERVER_PORT)
    except Exception:
        logger.exception("Не удалось запустить локальный сервер %s:%s", LOCAL_SERVER_HOST, LOCAL_SERVER_PORT)
        return

    sockets = ", ".join(str(sock.getsockname()) for sock in (server.sockets or []))
    logger.info("Локальный сервер здоровья запущен: %s", sockets or f"{LOCAL_SERVER_HOST}:{LOCAL_SERVER_PORT}")
    async with server:
        await server.serve_forever()

async def init_default_data():
    """Инициализировать данные по умолчанию"""
    logger.info("Инициализация БД...")
    await db.init_db()
    await db.init_default_organizations()
    normalized = await db.normalize_organization_budgets(minimum_budget=0.0)
    if int(normalized.get("updated_count") or 0) > 0:
        logger.warning(
            "Нормализованы бюджеты организаций: count=%s min=%s",
            normalized.get("updated_count"),
            normalized.get("minimum_budget"),
        )
    gov_floor = await db.ensure_government_budget_floor(minimum_budget=25_000_000.0)
    if gov_floor.get("updated"):
        logger.warning(
            "Госбюджет скорректирован до минимума: old=$%.2f new=$%.2f",
            float(gov_floor.get("old_budget") or 0),
            float(gov_floor.get("new_budget") or 0),
        )
    tax_reset_checkpoint = await db.get_system_state("tax_reset_2026_03_ai_reform_done")
    if tax_reset_checkpoint != "1":
        reset_summary = await db.reset_tax_system_state()
        await db.set_system_state("tax_reset_2026_03_ai_reform_done", "1")
        logger.warning(
            "Налоги и долги обнулены: users=%s invoices_deleted=%s tax_logs_deleted=%s",
            int(reset_summary.get("users_total", 0)),
            int(reset_summary.get("invoices_deleted", 0)),
            int(reset_summary.get("tax_logs_deleted", 0)),
        )
    await db.bootstrap_world_data()
    rebalance = await db.apply_currency_rebalance_once()
    if rebalance.get("applied"):
        logger.info(
            "Валютный ребаланс применен: factor=%s tables=%s columns=%s users_reset=%s",
            rebalance.get("factor"),
            rebalance.get("scaled_tables"),
            rebalance.get("scaled_columns"),
            rebalance.get("users_reset"),
        )
    salary_rebalance = await db.apply_salary_rebalance_once(multiplier=2.5)
    if salary_rebalance.get("applied"):
        logger.info(
            "Ребаланс зарплат применен: x%s, вакансии=%s (+floor=%s), орг-состав=%s, заявки=%s (+floor=%s)",
            salary_rebalance.get("multiplier"),
            salary_rebalance.get("citizens_updated"),
            salary_rebalance.get("citizens_floor_fixed"),
            salary_rebalance.get("org_members_updated"),
            salary_rebalance.get("applications_updated"),
            salary_rebalance.get("applications_floor_fixed"),
        )
    salary_floor = await db.ensure_citizen_salary_floor_once(minimum_salary=1500.0)
    if salary_floor.get("applied"):
        logger.info(
            "Применен минимальный порог зарплаты: min=$%.2f users=%s pending_apps=%s catalog=%s",
            float(salary_floor.get("minimum_salary") or 0),
            int(salary_floor.get("users_updated") or 0),
            int(salary_floor.get("applications_updated") or 0),
            int(salary_floor.get("catalog_updated") or 0),
        )
    property_raise = await db.raise_property_prices_once(multiplier=1.65)
    if property_raise.get("applied"):
        logger.info(
            "Недвижимость удорожена: x%s, обновлено объектов=%s",
            property_raise.get("multiplier"),
            property_raise.get("updated_rows"),
        )

    election_id = await db.ensure_presidential_election(duration_hours=15)
    if election_id:
        logger.info(f"Активированы президентские выборы (ID {election_id})")

async def setup_bot_commands(bot: Bot):
    """Установить список команд в меню Telegram"""
    commands = [
        BotCommand(command="start", description="🎮 Начать игру"),
        BotCommand(command="menu", description="🏛️ Главное меню"),
        BotCommand(command="profile", description="👤 Мой профиль"),
        BotCommand(command="nick", description="✏️ Изменить персональный ник"),
        BotCommand(command="ai", description="🤖 AI-ассистент"),
        BotCommand(command="radio", description="📡 Гос-рация"),
        BotCommand(command="orgs", description="🏛️ Организации"),
        BotCommand(command="biz", description="🏢 Бизнес"),
        BotCommand(command="work", description="💼 Работа и подработки"),
        BotCommand(command="tax", description="🧾 Налоги за день"),
        BotCommand(command="charity", description="🤝 Пожертвование в фонд"),
        BotCommand(command="edu", description="🎓 Образование"),
        BotCommand(command="prop", description="🏠 Недвижимость"),
        BotCommand(command="sellprop", description="💸 Продажа недвижимости"),
        BotCommand(command="priv", description="🏢 Частные организации"),
        BotCommand(command="gang", description="🕶️ Банды"),
        BotCommand(command="leavegang", description="🚪 Выйти из банды"),
        BotCommand(command="marry", description="💍 Предложение брака (reply)"),
        BotCommand(command="divorce", description="💔 Развод"),
        BotCommand(command="family", description="👨‍👩‍👧 Семейная панель"),
        BotCommand(command="pet", description="🐾 Питомец"),
        BotCommand(command="petname", description="✏️ Имя питомца"),
        BotCommand(command="market", description="📣 Городская площадка"),
        BotCommand(command="ref", description="👥 Рефералы и маркетинг"),
        BotCommand(command="builder", description="🏗️ Панель застройщика"),
        BotCommand(command="stocks", description="📈 Акции и биржа"),
        BotCommand(command="fun", description="🎪 Сюжетное событие"),
        BotCommand(command="casino", description="🎰 Казино"),
        BotCommand(command="donate", description="💎 Донат и поддержка"),
        BotCommand(command="promo", description="🎟️ Промокоды"),
        BotCommand(command="botadmin", description="🛠 Админ-панель бота"),
        BotCommand(command="grantdonate", description="💎 Выдать донат-пакет"),
        BotCommand(command="paysupport", description="🧾 Помощь по оплате"),
        BotCommand(command="terms", description="📜 Условия доната"),
        BotCommand(command="duel", description="🎲 Дуэль в группе (reply)"),
        BotCommand(command="plus", description="👍 +1 репутация (reply)"),
        BotCommand(command="news", description="📰 Новости СМИ"),
        BotCommand(command="id", description="🆔 Мой ID"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# --- Вспомогательный хендлер для отладки ---
debug_router = Router()
@debug_router.callback_query()
async def global_debug_callback(callback: CallbackQuery):
    """Если кнопка не сработала в основных роутерах, она попадет сюда"""
    logger.debug("Необработанный callback: %s", callback.data)
    await callback.answer("Кнопка устарела. Откройте меню заново через /start.", show_alert=True)

async def main() -> int:
    if not TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")
    instance_lock = SingleInstanceLock(INSTANCE_LOCK_PATH)
    if not instance_lock.acquire():
        logger.warning("Обнаружен уже запущенный экземпляр бота. Этот процесс завершен.")
        return 11

    bot: Bot | None = None
    try:
        # 1. Инициализация БД
        await init_default_data()
        
        # 2. Настройка бота
        session = AiohttpSession(timeout=TELEGRAM_REQUEST_TIMEOUT)
        session.middleware(TextSanitizerRequestMiddleware())
        session.middleware(TelegramRetryMiddleware(retries=2, base_delay=1.0))
        bot = Bot(
            token=TOKEN,
            session=session,
            default=DefaultBotProperties(parse_mode="Markdown")
        )
        dp = Dispatcher(storage=MemoryStorage())

        # Инициализация состояния рабочего времени при старте процесса
        # По умолчанию включаем принудительный 24/7 режим (убираем расписание).
        now_uz = datetime.now(UZBEKISTAN_TZ)
        runtime_state["is_online"] = True
        runtime_state["force_online"] = True
        runtime_state["last_warning_date"] = None
        
        # 3. Регистрация Middleware (Важен порядок!)
        dp.message.middleware(TransientTelegramErrorMiddleware())
        dp.callback_query.middleware(TransientTelegramErrorMiddleware())
        # Сначала ограничиваем спам, чтобы не нагружать БД и обработчики лишними апдейтами.
        dp.message.middleware(RateLimitMiddleware(calls=8, period=2.0, callback_calls=12, callback_period=2.0))
        dp.callback_query.middleware(RateLimitMiddleware(calls=8, period=2.0, callback_calls=12, callback_period=2.0))
        dp.message.middleware(EnsureUserMiddleware())
        dp.callback_query.middleware(EnsureUserMiddleware())
        dp.message.middleware(WorkingHoursMiddleware(runtime_state))
        dp.callback_query.middleware(WorkingHoursMiddleware(runtime_state))
        dp.message.middleware(MandatoryNicknameMiddleware())
        dp.callback_query.middleware(MandatoryNicknameMiddleware())
        # Middleware, блокирующий пользователей с active action_banned_until
        dp.message.middleware(ActionBanMiddleware())
        dp.callback_query.middleware(ActionBanMiddleware())
        # 4. Регистрация Роутеров
        # Сначала специфичные, потом общие
        dp.include_router(service_router)
        dp.include_router(feature_router)
        dp.include_router(presidential_router)
        dp.include_router(fbi_router)
        dp.include_router(revolution_router)
        dp.include_router(handlers_part3_router)
        dp.include_router(handlers_part2_router)
        dp.include_router(main_router) # Главный роутер обычно последний
        
        # Рекомендую добавить этот роутер ПОСЛЕДНИМ для отладки
        dp.include_router(debug_router)
        
        # 5. Команды и фон
        await setup_bot_commands(bot)
        if runtime_state["is_online"]:
            sent_ids = await broadcast_to_active_groups(bot, STARTUP_TEXT)
            session_startup_announced_groups.update(sent_ids)
        else:
            sent_ids = await broadcast_to_active_groups(bot, PROCESS_STARTED_OFFLINE_TEXT)
            session_offline_start_notified_groups.update(sent_ids)
        asyncio.create_task(run_work_hours_controller(bot, runtime_state))
        asyncio.create_task(run_daily_economy_cycle(bot))
        asyncio.create_task(run_state_money_print_processor(bot))
        asyncio.create_task(run_ai_governance_cycle(bot))
        asyncio.create_task(run_media_news_digest(bot, runtime_state, period_minutes=10))
        if LOCAL_SERVER_ENABLED:
            asyncio.create_task(run_local_health_server(runtime_state))
        # Фоновое обслуживание выборов
        async def run_election_maintenance(bot: Bot):
            """Проверяет и поддерживает президентские выборы."""
            while True:
                try:
                    # Если президента нет — гарантируем существование активных выборов
                    await db.ensure_presidential_election(duration_hours=15)

                    # Автоматически синхронизируем этапы активных выборов по времени
                    stage_changes = await db.sync_active_election_stages()
                    for change in stage_changes:
                        logger.info(
                            "Выборы %s: этап %s -> %s",
                            change.get("election_id"),
                            change.get("old_stage"),
                            change.get("new_stage"),
                        )

                    # Завершаем просроченные выборы
                    results = await db.finalize_expired_elections()
                    for result in results:
                        election_id = result.get('election_id')
                        status = result.get('status')
                        if status == 'extended_no_candidates':
                            logger.info(
                                f"Выборы {election_id} продлены: нет кандидатов до {result.get('new_end_date')}"
                            )
                            continue

                        if status != 'finished':
                            continue

                        winner_id = result.get('winner_id')
                        candidate_ids = result.get('candidate_ids', [])
                        tie_note = "\nПобеда определена тай-брейком." if result.get('is_tie_break') else ""

                        if winner_id:
                            try:
                                await bot.send_message(
                                    winner_id,
                                    f"🏆 Вы победили на выборах (ID {election_id}) и назначены президентом.{tie_note}",
                                    parse_mode=None,
                                )
                            except Exception:
                                pass

                        for candidate_id in candidate_ids:
                            if candidate_id == winner_id:
                                continue
                            try:
                                await bot.send_message(
                                    candidate_id,
                                    f"ℹ️ Выборы (ID {election_id}) завершены. Победитель: ID {winner_id}.",
                                    parse_mode=None,
                                )
                            except Exception:
                                pass

                except Exception:
                    logger.exception("Ошибка в фоновой задаче выборов")
                await asyncio.sleep(60)

        asyncio.create_task(run_election_maintenance(bot))
        
        # 6. Запуск
        logger.info("🤖 Бот запущен и готов к работе!")
        # Удаляем вебхуки и запускаем чистый поллинг
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(
            bot,
            polling_timeout=25,
            tasks_concurrency_limit=12,
            allowed_updates=dp.resolve_used_update_types(),
        )
        return 0
    finally:
        if bot is not None:
            await bot.session.close()
        instance_lock.release()

if __name__ == "__main__":
    try:
        exit_code = int(asyncio.run(main()) or 0)
        if exit_code != 0:
            raise SystemExit(exit_code)
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except SystemExit as exc:
        if int(getattr(exc, "code", 0) or 0) == 11:
            logger.info("Второй экземпляр завершен: основной бот уже запущен.")
        else:
            logger.info("Бот остановлен")
        raise
