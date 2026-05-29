"""
Middleware для aiogram 3.x: проверки доступа, режим выборов, баны.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from time import monotonic
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update

from database import db
from states import MainStates


class EnsureUserMiddleware(BaseMiddleware):
    """Создает/обновляет пользователя, но с троттлингом по времени."""

    def __init__(self, refresh_seconds: float = 45.0):
        self.refresh_seconds = max(5.0, float(refresh_seconds or 45.0))
        self._last_sync: Dict[int, float] = {}
        self._last_cleanup = 0.0

    def _should_sync_user(self, user_id: int) -> bool:
        now = monotonic()
        last = self._last_sync.get(user_id)
        if last is not None and (now - last) < self.refresh_seconds:
            return False

        self._last_sync[user_id] = now

        # Периодическая очистка, чтобы кэш не рос бесконечно.
        if len(self._last_sync) > 5000 and (now - self._last_cleanup) > 300:
            cutoff = now - (self.refresh_seconds * 4)
            self._last_sync = {uid: ts for uid, ts in self._last_sync.items() if ts >= cutoff}
            self._last_cleanup = now

        return True

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        elif isinstance(event, Update):
            if event.message:
                user = event.message.from_user
            elif event.callback_query:
                user = event.callback_query.from_user

        if user and self._should_sync_user(int(user.id)):
            await db.create_or_update_user(
                user_id=user.id,
                username=user.username or "",
                full_name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
            )

        return await handler(event, data)


class MandatoryNicknameMiddleware(BaseMiddleware):
    """Блокирует игровой функционал, пока пользователь не задаст ник."""

    ALLOWED_COMMANDS = {
        "/start",
        "/nick",
        "/help",
        "/id",
        "/marry",
        "/брак",
        "/divorce",
        "/развод",
        "/plus",
        "/rep",
        "/botadmin",
        "/adminpanel",
        "/grantdonate",
    }
    ALLOWED_CALLBACK_PREFIXES = {
        "set_nick_start",
        "set_nick_reset",
        "help_menu",
        "menu:help_menu",
        "bot_admin_",
    }
    GROUP_INTERACTION_PREFIXES = {
        "кости",
        "кость",
        "кубик",
        "dice",
        "автомат",
        "слот",
        "слоты",
        "slot",
        "slots",
        "баскет",
        "баскетбол",
        "basket",
        "basketball",
        "брак",
        "развод",
        "обнять",
        "поцеловать",
        "погладить",
        "marry",
        "divorce",
        "+",
        "плюс",
    }

    def __init__(self, notify_cooldown_seconds: float = 15.0):
        self.notify_cooldown_seconds = max(3.0, float(notify_cooldown_seconds or 15.0))
        self._last_notify: Dict[tuple[str, int], float] = {}

    @staticmethod
    def _extract_user(event: Any):
        if isinstance(event, Message):
            return event.from_user
        if isinstance(event, CallbackQuery):
            return event.from_user
        if isinstance(event, Update):
            if event.message:
                return event.message.from_user
            if event.callback_query:
                return event.callback_query.from_user
        return None

    @staticmethod
    def _command_from_text(text: str) -> str:
        head = (text or "").strip().split(" ", 1)[0].lower()
        if "@" in head:
            head = head.split("@", 1)[0]
        return head

    @classmethod
    def _is_group_interaction_text(cls, text: str) -> bool:
        content = " ".join((text or "").strip().split())
        if not content:
            return False
        if content.startswith("/"):
            return True
        first = content.split(" ", 1)[0].lower()
        if "@" in first:
            first = first.split("@", 1)[0]
        first = first.strip(".,!?;:()[]{}<>\"'`«»")
        return first in cls.GROUP_INTERACTION_PREFIXES

    def _should_notify(self, scope: str, user_id: int) -> bool:
        now = monotonic()
        key = (scope, int(user_id))
        last = self._last_notify.get(key)
        if last is not None and (now - last) < self.notify_cooldown_seconds:
            return False
        self._last_notify[key] = now
        return True

    async def _has_required_nickname(self, user_id: int) -> bool:
        user = await db.get_user(int(user_id)) or {}
        nickname = str(user.get("nickname") or "").strip()
        return bool(nickname)

    @staticmethod
    def _nickname_required_text() -> str:
        return (
            "❗ Ник обязателен для игры.\n\n"
            "Сначала установите ник (3-28 символов), затем откроются все функции."
        )

    @staticmethod
    def _nickname_required_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Установить ник", callback_data="set_nick_start")],
                [InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")],
            ]
        )

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user = self._extract_user(event)
        if not user:
            return await handler(event, data)

        fsm_state = data.get("state")
        current_state = ""
        if fsm_state:
            try:
                current_state = str(await fsm_state.get_state() or "")
            except Exception:
                current_state = ""
        is_nickname_state = current_state == MainStates.setting_nickname.state

        if isinstance(event, Message):
            if getattr(event, "successful_payment", None):
                return await handler(event, data)
            text = str(event.text or "")
            command = self._command_from_text(text)
            if command in self.ALLOWED_COMMANDS:
                return await handler(event, data)
            if is_nickname_state and text and not text.strip().startswith("/"):
                return await handler(event, data)

            if event.chat.type in {"group", "supergroup"} and not self._is_group_interaction_text(text):
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            callback_data = str(event.data or "")
            if any(callback_data.startswith(prefix) for prefix in self.ALLOWED_CALLBACK_PREFIXES):
                return await handler(event, data)

        if await self._has_required_nickname(int(user.id)):
            return await handler(event, data)

        if fsm_state:
            try:
                await fsm_state.set_state(MainStates.setting_nickname)
            except Exception:
                pass

        text = self._nickname_required_text()
        keyboard = self._nickname_required_keyboard()

        if isinstance(event, CallbackQuery):
            if self._should_notify("cb", int(user.id)):
                try:
                    await event.answer("Сначала установите ник.", show_alert=True)
                except Exception:
                    pass
            if event.message and event.message.chat.type == "private" and self._should_notify("cb_msg", int(user.id)):
                try:
                    await event.message.edit_text(text, reply_markup=keyboard, parse_mode=None)
                except Exception:
                    try:
                        await event.message.answer(text, reply_markup=keyboard, parse_mode=None)
                    except Exception:
                        pass
            return

        if isinstance(event, Message):
            if event.chat.type in {"group", "supergroup"}:
                if self._should_notify("grp", int(user.id)):
                    await event.answer(
                        "❗ Для игры нужен ник.\n"
                        "Откройте личный чат с ботом и нажмите /start.",
                        parse_mode=None,
                    )
                return
            if self._should_notify("pv", int(user.id)):
                await event.answer(text, reply_markup=keyboard, parse_mode=None)
            return

        return


class PrivateChatOnlyMiddleware(BaseMiddleware):
    """Разрешить обработчик только в личном чате."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type != "private":
            await event.answer(
                "❌ Эта функция доступна только в личных сообщениях.\n"
                f"💬 Напишите боту в ЛС: @{(await event.bot.get_me()).username}"
            )
            return

        return await handler(event, data)


class IsOrganizationMemberMiddleware(BaseMiddleware):
    """Проверка членства в организации для обработчиков, где это требуется."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    """Ограничение доступа только администраторам."""

    ADMIN_IDS = [6000066043]

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user and user.id not in self.ADMIN_IDS:
            if isinstance(event, Message):
                await event.answer("❌ Доступ запрещен. Эта функция только для администраторов.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Доступ запрещен!", show_alert=True)
            return

        return await handler(event, data)


class PresidentOnlyMiddleware(BaseMiddleware):
    """Ограничение доступа только президенту."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            gov_system = await db.get_government_system()
            if not gov_system or gov_system.get("current_leader_id") != user.id:
                msg = "❌ Только президент может использовать эту команду!"
                if isinstance(event, Message):
                    await event.answer(msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                return

        return await handler(event, data)


class RoleBasedMiddleware(BaseMiddleware):
    """Ограничение доступа по ролям в организации."""

    def __init__(self, required_roles: list):
        self.required_roles = required_roles

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            user_data = await db.get_user(user.id)
            user_role = user_data.get("role") if user_data else None
            if user_role not in self.required_roles:
                msg = f"❌ Требуется одна из ролей: {', '.join(self.required_roles)}"
                if isinstance(event, Message):
                    await event.answer(msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                return

        return await handler(event, data)


class GlobalLockMiddleware(BaseMiddleware):
    """Глобальная блокировка функций во время первых президентских выборов."""

    ALLOWED_CALLBACK_PREFIXES = [
        "election:",
        "party:",
        "pinvpg:",
        "pinvsel:",
        "back_to_main",
        "help_menu",
        "menu:help_menu",
        "bot_admin_",
    ]

    def __init__(self, cache_ttl_seconds: float = 3.0):
        self.cache_ttl_seconds = max(1.0, float(cache_ttl_seconds or 3.0))
        self._cache_expires_at = 0.0
        self._cached_has_president = False
        self._cached_has_active_election = False

    async def _read_lock_state(self) -> tuple[bool, bool]:
        now = monotonic()
        if now < self._cache_expires_at:
            return self._cached_has_president, self._cached_has_active_election

        has_president = await db.check_has_president()
        has_active_election = False

        if not has_president:
            active_election = await db.get_active_presidential_election()
            if not active_election:
                await db.ensure_presidential_election(duration_hours=15)
                active_election = await db.get_active_presidential_election()
            has_active_election = active_election is not None

        self._cached_has_president = bool(has_president)
        self._cached_has_active_election = bool(has_active_election)
        self._cache_expires_at = now + self.cache_ttl_seconds
        return self._cached_has_president, self._cached_has_active_election

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        has_president, has_active_election = await self._read_lock_state()

        if has_president or not has_active_election:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            callback_data = event.data or ""
            allowed = any(callback_data.startswith(prefix) for prefix in self.ALLOWED_CALLBACK_PREFIXES)
            if not allowed:
                await event.answer(
                    "🔒 РЕЖИМ ВЫБОРОВ АКТИВЕН!\n\n"
                    "Сейчас в стране проходят выборы президента.\n"
                    "Все остальные функции заблокированы до результатов выборов.\n\n"
                    "📌 Вы можете:\n"
                    "• Создать партию\n"
                    "• Голосовать\n"
                    "• Просмотреть мою партию",
                    show_alert=True,
                )
                return

        if isinstance(event, Message):
            fsm_state = data.get("state")
            if fsm_state:
                try:
                    current_state = await fsm_state.get_state()
                    if current_state and current_state.startswith("ElectionStates"):
                        return await handler(event, data)
                except Exception:
                    pass

            command = (event.text or "").strip().split(" ", 1)[0].lower()
            if "@" in command:
                command = command.split("@", 1)[0]
            if command in {"/start", "/menu", "/help", "/id", "/marry", "/брак", "/divorce", "/развод", "/plus", "/rep", "/botadmin", "/adminpanel", "/grantdonate"}:
                return await handler(event, data)
            token = command.lstrip("/").strip(".,!?;:()[]{}<>\"'`«»")
            if event.reply_to_message and token in {
                "брак",
                "marry",
                "развод",
                "divorce",
                "обнять",
                "поцеловать",
                "погладить",
                "+",
                "плюс",
            }:
                return await handler(event, data)

            await event.answer(
                "🔒 РЕЖИМ ВЫБОРОВ АКТИВЕН!\n\n"
                "Сейчас доступны только действия, связанные с выборами."
            )
            return

        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Ограничивает частоту запросов от одного пользователя."""

    def __init__(
        self,
        calls: int = 8,
        period: float = 2.0,
        callback_calls: int | None = None,
        callback_period: float | None = None,
    ):
        self.calls = max(1, int(calls or 8))
        self.period = max(0.5, float(period or 2.0))
        self.callback_calls = max(1, int(callback_calls or self.calls))
        self.callback_period = max(0.5, float(callback_period or self.period))
        self._buckets: Dict[tuple[str, int], deque[float]] = {}
        self._last_cleanup = 0.0

    @staticmethod
    def _extract_user(event: Any):
        if isinstance(event, Message):
            return event.from_user
        if isinstance(event, CallbackQuery):
            return event.from_user
        if isinstance(event, Update):
            if event.message:
                return event.message.from_user
            if event.callback_query:
                return event.callback_query.from_user
        return None

    def _is_limited(self, key: tuple[str, int], limit_calls: int, limit_period: float) -> tuple[bool, float]:
        now = monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = deque()
            self._buckets[key] = bucket

        threshold = now - limit_period
        while bucket and bucket[0] <= threshold:
            bucket.popleft()

        if len(bucket) >= limit_calls:
            wait_seconds = max(0.1, limit_period - (now - bucket[0]))
            return True, wait_seconds

        bucket.append(now)

        # Периодическая очистка старых bucket-ов, чтобы кэш не рос бесконечно.
        if (now - self._last_cleanup) > 30 and len(self._buckets) > 2000:
            stale_before = now - (max(self.period, self.callback_period) * 2)
            self._buckets = {
                bucket_key: q
                for bucket_key, q in self._buckets.items()
                if q and q[-1] >= stale_before
            }
            self._last_cleanup = now

        return False, 0.0

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = self._extract_user(event)
        if not user:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            key = ("cb", int(user.id))
            limit_calls, limit_period = self.callback_calls, self.callback_period
        else:
            key = ("msg", int(user.id))
            limit_calls, limit_period = self.calls, self.period

        is_limited, wait_seconds = self._is_limited(key, limit_calls, limit_period)
        if not is_limited:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(
                f"Слишком часто. Подождите {wait_seconds:.1f} сек.",
                show_alert=False,
            )
            return

        if isinstance(event, Message):
            await event.answer(f"Слишком часто. Подождите {wait_seconds:.1f} сек.")
            return

        return await handler(event, data)


class ActionBanMiddleware(BaseMiddleware):
    """Блокирует действия пользователя, если active action_banned_until в будущем."""

    def __init__(self, cache_ttl_seconds: float = 5.0):
        self.cache_ttl_seconds = max(1.0, float(cache_ttl_seconds or 5.0))
        self._ban_cache: Dict[int, tuple[float, str | None]] = {}

    async def _get_ban_until(self, user_id: int) -> str | None:
        now = monotonic()
        cached = self._ban_cache.get(user_id)
        if cached and cached[0] > now:
            return cached[1]

        try:
            user = await db.get_user(user_id)
        except Exception:
            user = None

        ban_until = (user or {}).get("action_banned_until")
        self._ban_cache[user_id] = (now + self.cache_ttl_seconds, ban_until)
        return ban_until

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        ban_until = await self._get_ban_until(int(user.id))
        if ban_until:
            try:
                ban_dt = datetime.fromisoformat(ban_until)
                if ban_dt > datetime.now():
                    if isinstance(event, CallbackQuery):
                        await event.answer(
                            "⛔ Вам временно запрещены некоторые действия из-за наказания.",
                            show_alert=True,
                        )
                        return
                    if isinstance(event, Message):
                        await event.answer(
                            "⛔ Вам временно запрещены некоторые действия из-за наказания. Попробуйте позже."
                        )
                        return
            except Exception:
                pass

        return await handler(event, data)
