"""
Middleware'ы для aiogram 3.x - проверки доступа и валидация
"""

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from typing import Callable, Any, Awaitable, Dict
from database import db


class EnsureUserMiddleware(BaseMiddleware):
    """Middleware для создания/обновления пользователя при каждом взаимодействии"""
    
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        """Проверить/создать пользователя перед обработкой события"""
        
        # Получаем пользователя из события
        user = None
        
        # Проверяем тип события
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        elif isinstance(event, Update):
            # Если это Update, проверяем message и callback_query
            if event.message:
                user = event.message.from_user
            elif event.callback_query:
                user = event.callback_query.from_user
        
        if user:
            # Убеждаемся, что пользователь существует в БД
            await db.create_or_update_user(
                user_id=user.id,
                username=user.username or "",
                full_name=f"{user.first_name or ''} {user.last_name or ''}".strip()
            )
        
        # Передаем управление следующему handler'у
        return await handler(event, data)


class PrivateChatOnlyMiddleware(BaseMiddleware):
    """Middleware для проверки, что обращение из личного чата"""
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Разрешить только личные чаты"""
        
        if isinstance(event, Message):
            if event.chat.type != "private":
                await event.answer(
                    "❌ Эта функция доступна только в личных сообщениях.\n"
                    f"💬 Напишите боту в ЛС: @{(await event.bot.get_me()).username}"
                )
                return
        
        return await handler(event, data)


class IsOrganizationMemberMiddleware(BaseMiddleware):
    """Middleware для проверки членства в организации"""
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Проверить, является ли пользователь членом организации"""
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if user:
            # Здесь можно добавить проверку членства в организации
            # data['user_org'] = await db.get_user_organization(user.id)
            pass
        
        return await handler(event, data)


class AdminOnlyMiddleware(BaseMiddleware):
    """Middleware для проверки администраторского статуса"""
    
    # Встроенные админы (можешь расширить)
    ADMIN_IDS = [6000066043]  # Замени на свой ID
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Разрешить только администраторам"""
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if user and user.id not in self.ADMIN_IDS:
            if isinstance(event, Message):
                await event.answer("❌ Доступ запрещен. Это функция только для администраторов.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Доступ запрещен!", show_alert=True)
            return
        
        return await handler(event, data)


class PresidentOnlyMiddleware(BaseMiddleware):
    """Middleware для проверки, что пользователь президент"""
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Разрешить только президенту"""
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if user:
            # Проверяем, является ли пользователь президентом
            gov_system = await db.get_government_system()
            if not gov_system or gov_system.get('current_leader_id') != user.id:
                msg = "❌ Только президент может использовать эту команду!"
                if isinstance(event, Message):
                    await event.answer(msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                return
        
        return await handler(event, data)


class RoleBasedMiddleware(BaseMiddleware):
    """Middleware для проверки ролей в организации"""
    
    def __init__(self, required_roles: list):
        self.required_roles = required_roles
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Проверить роль пользователя в организации"""
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if user:
            user_data = await db.get_user(user.id)
            user_role = user_data.get('role') if user_data else None
            
            if user_role not in self.required_roles:
                msg = f"❌ Требуется одна из ролей: {', '.join(self.required_roles)}"
                if isinstance(event, Message):
                    await event.answer(msg)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                return
        
        return await handler(event, data)


class GlobalLockMiddleware(BaseMiddleware):
    """Middleware для проверки ГЛОБАЛЬНОЙ БЛОКИРОВКИ (режим выборов президента)"""
    
    # Разрешенные действия в режиме блокировки (по префиксам CallbackData)
    ALLOWED_CALLBACK_PREFIXES = [
        "election:",     # ElectionCallback
        "party:",        # PartyCallback (для приглашений в партию)
        "back_to_main",  # Кнопка "назад"
        "help_menu",     # Меню помощи
        "menu:help_menu",  # Старый callback формат
    ]
    
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        """Проверить, находимся ли мы в режиме глобальной блокировки"""
        
        # Проверяем, есть ли активные выборы и нет ли президента
        has_president = await db.check_has_president()
        
        # Если есть президент, блокировка отключена
        if has_president:
            return await handler(event, data)
        
        # Проверяем активные президентские выборы
        active_election = await db.get_active_presidential_election()
        if not active_election:
            # Подстраховка: если президента нет, поднимаем выборы автоматически
            await db.ensure_presidential_election(duration_hours=30)
            active_election = await db.get_active_presidential_election()
            if not active_election:
                return await handler(event, data)
        
        # Находимся в режиме блокировки - проверяем права
        if isinstance(event, CallbackQuery):
            callback_data = event.data
            
            # Проверяем, разрешен ли этот callback
            allowed = False
            for prefix in self.ALLOWED_CALLBACK_PREFIXES:
                if callback_data.startswith(prefix):
                    allowed = True
                    break
            
            if not allowed:
                await event.answer(
                    "🔒 РЕЖИМ ВЫБОРОВ АКТИВЕН!\n\n"
                    "Сейчас в стране проходят выборы президента.\n"
                    "Все остальные функции заблокированы до результатов выборов.\n\n"
                    "📌 Вы можете:\n"
                    "• Создать партию\n"
                    "• Голосовать\n"
                    "• Просмотреть мою партию",
                    show_alert=True
                )
                return

        if isinstance(event, Message):
            # Разрешаем ввод текста только внутри сценариев выборов (например, название партии).
            fsm_state = data.get("state")
            if fsm_state:
                try:
                    current_state = await fsm_state.get_state()
                    if current_state and current_state.startswith("ElectionStates"):
                        return await handler(event, data)
                except Exception:
                    pass

            # Разрешаем только базовые команды во время глобальной блокировки.
            command = (event.text or "").strip().split(" ", 1)[0].lower()
            if command in {"/start", "/menu", "/help", "/id"}:
                return await handler(event, data)

            await event.answer(
                "🔒 РЕЖИМ ВЫБОРОВ АКТИВЕН!\n\n"
                "Сейчас доступны только действия, связанные с выборами."
            )
            return
        
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Middleware для ограничения частоты запросов"""
    
    def __init__(self, calls: int = 10, period: int = 2):
        """
        calls - кол-во допустимых запросов
        period - за сколько секунд
        """
        self.calls = calls
        self.period = period
        self.user_requests: Dict[int, list] = {}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Ограничить частоту запросов от пользователя"""
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        
        if not user:
            return await handler(event, data)
        
        # Здесь можно добавить логику рейт-лимита
        # Пока просто пропускаем
        
        return await handler(event, data)


class ActionBanMiddleware(BaseMiddleware):
    """Middleware которое блокирует действия пользователей, если у них установлен action_banned_until в будущем."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Если `action_banned_until` в будущем — блокируем большинство действий."""

        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        # Получаем данные пользователя из БД
        try:
            u = await db.get_user(user.id)
        except Exception:
            u = None

        if not u:
            return await handler(event, data)

        # Проверяем бан на действия
        ban_until = u.get('action_banned_until')
        if ban_until:
            try:
                from datetime import datetime
                ban_dt = datetime.fromisoformat(ban_until)
                if ban_dt > datetime.now():
                    # Разрешим только базовые информационные команды
                    if isinstance(event, CallbackQuery):
                        await event.answer("⛔ Вам временно запрещены некоторые действия из-за наказания.", show_alert=True)
                        return
                    elif isinstance(event, Message):
                        await event.answer("⛔ Вам временно запрещены некоторые действия из-за наказания. Попробуйте позже.")
                        return
            except Exception:
                # некорректный формат — пропускаем
                pass

        # Также можно реализовать проверку dictator_until/ temp_title если нужно
        return await handler(event, data)
