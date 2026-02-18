"""
main.py - точка входа Telegram-бота на aiogram 3.x (асинхронный)
"""

import asyncio
import logging
import os
import warnings
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

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
from aiogram.fsm.storage.memory import MemoryStorage

# Импорт твоих модулей
from database import db
from middlewares import (
    EnsureUserMiddleware,
    GlobalLockMiddleware,
)
from handlers_part1 import router as main_router
from handlers_part2 import router as handlers_part2_router
from handlers_part3 import router as handlers_part3_router
from feature_pack import router as feature_router
from presidential_admin import router as presidential_router
from fbi_intercept import router as fbi_router
from revolutions import router as revolution_router
from economy import run_daily_economy_cycle

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

UZBEKISTAN_TZ = ZoneInfo("Asia/Tashkent")
WORK_START_HOUR = 8
WORK_END_HOUR = 21
SHUTDOWN_WARNING_HOUR = 20
SHUTDOWN_WARNING_MINUTE = 50

runtime_state: dict[str, Any] = {
    "is_online": False,
    "last_warning_date": None,
    "last_hourly_news_key": None,
}
session_startup_announced_groups: set[int] = set()
session_offline_start_notified_groups: set[int] = set()

STARTUP_TEXT = (
    "🟢 Бот включился и работает.\n"
    "🕗 Режим: 08:00-21:00 (UTC+5, Asia/Tashkent)."
)
PROCESS_STARTED_OFFLINE_TEXT = (
    "🛠 Бот запущен, но сейчас вне рабочего времени.\n"
    "🕗 Режим: 08:00-21:00 (UTC+5, Asia/Tashkent)."
)
SHUTDOWN_WARNING_TEXT = (
    "⚠️ Бот выключится через 10 минут.\n"
    "⏰ Отключение в 21:00 по времени Узбекистана (UTC+5)."
)


def is_working_hours(now: datetime) -> bool:
    start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    end = now.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    return start <= now < end


def get_next_start_time(now: datetime) -> datetime:
    today_start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    if now < today_start:
        return today_start
    return (now + timedelta(days=1)).replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)


class WorkingHoursMiddleware(BaseMiddleware):
    """Ограничивает обработку команд рабочим временем 08:00-21:00 (Asia/Tashkent)."""

    def __init__(self, state: dict[str, Any]):
        self.state = state

    async def __call__(self, handler, event, data):
        if self.state.get("is_online"):
            return await handler(event, data)

        now = datetime.now(UZBEKISTAN_TZ)
        next_start = get_next_start_time(now)

        if isinstance(event, Message):
            if event.chat.type in {"group", "supergroup"}:
                # Даже вне рабочего окна обновляем реестр групп, чтобы утренние рассылки работали.
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
                    "⏸ Бот сейчас выключен.\n"
                    "Рабочее время: 08:00-21:00 (UTC+5, Asia/Tashkent).\n"
                    f"Следующее включение: {next_start:%d.%m %H:%M}"
                )
            return

        if isinstance(event, CallbackQuery):
            await event.answer(
                f"⏸ Бот выключен. Включится в {next_start:%H:%M} (Asia/Tashkent).",
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


@service_router.message(F.chat.type.in_({"group", "supergroup"}))
async def track_group_activity(message: Message):
    """
    Обновляем реестр групп при активности.
    Это помогает сохранить список чатов даже при редких my_chat_member update.
    """
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

    logger.info("Групповая рассылка завершена: отправлено=%s, ошибок=%s", sent, failed)
    return sent_chat_ids


async def run_work_hours_controller(bot: Bot, state: dict[str, Any]):
    """Переключает доступность бота по расписанию и делает системные рассылки."""
    while True:
        try:
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


async def run_hourly_media_news(bot: Bot, state: dict[str, Any]):
    """Раз в час генерирует новость СМИ и рассылает ее в активные группы."""
    while True:
        try:
            now = datetime.now(UZBEKISTAN_TZ)
            key = now.strftime("%Y-%m-%d %H")
            last_key = state.get("last_hourly_news_key")
            if last_key is None:
                persisted_key = await db.get_system_state("media_last_hourly_news_key")
                state["last_hourly_news_key"] = persisted_key or ""
                last_key = state["last_hourly_news_key"]
            if (
                state.get("is_online")
                and now.minute == 0
                and last_key != key
            ):
                news = await db.generate_hourly_news()
                if news:
                    text = (
                        "📰 НОВОСТИ СМИ\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"{news.get('title')}\n\n"
                        f"{news.get('body')}"
                    )
                    await broadcast_to_active_groups(bot, text)
                    state["last_hourly_news_key"] = key
                    await db.set_system_state("media_last_hourly_news_key", key)
        except Exception:
            logger.exception("Ошибка в задаче почасовых новостей")
        await asyncio.sleep(20)

async def init_default_data():
    """Инициализировать данные по умолчанию"""
    logger.info("Инициализация БД...")
    await db.init_db()
    await db.init_default_organizations()
    await db.bootstrap_world_data()
    
    election_id = await db.ensure_presidential_election(duration_hours=30)
    if election_id:
        logger.info(f"Активированы президентские выборы (ID {election_id})")

async def setup_bot_commands(bot: Bot):
    """Установить список команд в меню Telegram"""
    commands = [
        BotCommand(command="start", description="🎮 Начать игру"),
        BotCommand(command="menu", description="🏛️ Главное меню"),
        BotCommand(command="profile", description="👤 Мой профиль"),
        BotCommand(command="orgs", description="🏛️ Организации"),
        BotCommand(command="biz", description="🏢 Бизнес"),
        BotCommand(command="work", description="💼 Работа и подработки"),
        BotCommand(command="edu", description="🎓 Образование"),
        BotCommand(command="prop", description="🏠 Недвижимость"),
        BotCommand(command="priv", description="🏢 Частные организации"),
        BotCommand(command="gang", description="🕶️ Банды"),
        BotCommand(command="market", description="📣 Городская площадка"),
        BotCommand(command="casino", description="🎰 Казино"),
        BotCommand(command="news", description="📰 Новости СМИ"),
        BotCommand(command="id", description="🆔 Мой ID"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# --- Вспомогательный хендлер для отладки ---
debug_router = Router()
@debug_router.callback_query()
async def global_debug_callback(callback: CallbackQuery):
    """Если кнопка не сработала в основных роутерах, она попадет сюда"""
    logger.warning(f"⚠️ Необработанный callback: {callback.data}")
    await callback.answer("Эта кнопка еще не настроена в коде", show_alert=True)

async def main():
    if not TOKEN:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана.")

    # 1. Инициализация БД
    await init_default_data()
    
    # 2. Настройка бота
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode="Markdown")
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация состояния рабочего времени при старте процесса
    now_uz = datetime.now(UZBEKISTAN_TZ)
    runtime_state["is_online"] = is_working_hours(now_uz)
    runtime_state["last_warning_date"] = None
    
    # 3. Регистрация Middleware (Важен порядок!)
    dp.message.middleware(EnsureUserMiddleware())
    dp.callback_query.middleware(EnsureUserMiddleware())
    dp.message.middleware(WorkingHoursMiddleware(runtime_state))
    dp.callback_query.middleware(WorkingHoursMiddleware(runtime_state))
    # Middleware, блокирующий пользователей с active action_banned_until
    from middlewares import ActionBanMiddleware
    dp.message.middleware(ActionBanMiddleware())
    dp.callback_query.middleware(ActionBanMiddleware())
    # Global lock for election mode
    dp.message.middleware(GlobalLockMiddleware())
    dp.callback_query.middleware(GlobalLockMiddleware())
    
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
    asyncio.create_task(run_hourly_media_news(bot, runtime_state))
    # Фоновое обслуживание выборов
    async def run_election_maintenance(bot: Bot):
        """Проверяет и поддерживает президентские выборы."""
        while True:
            try:
                # Если президента нет — гарантируем существование активных выборов
                await db.ensure_presidential_election(duration_hours=30)

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
    try:
        logger.info("🤖 Бот запущен и готов к работе!")
        # Удаляем вебхуки и запускаем чистый поллинг
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
