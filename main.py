"""
main.py - точка входа Telegram-бота на aiogram 3.x (асинхронный)
"""

import asyncio
import logging
import os
import warnings
from dotenv import load_dotenv

# Подавляем предупреждение pydantic об aiogram
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
from aiogram import Bot, Dispatcher, Router
from aiogram.types import BotCommand, BotCommandScopeDefault, CallbackQuery
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

async def init_default_data():
    """Инициализировать данные по умолчанию"""
    logger.info("Инициализация БД...")
    await db.init_db()
    await db.init_default_organizations()
    
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
    
    # 3. Регистрация Middleware (Важен порядок!)
    dp.message.middleware(EnsureUserMiddleware())
    dp.callback_query.middleware(EnsureUserMiddleware())
    # Middleware, блокирующий пользователей с active action_banned_until
    from middlewares import ActionBanMiddleware
    dp.message.middleware(ActionBanMiddleware())
    dp.callback_query.middleware(ActionBanMiddleware())
    # Global lock for election mode
    dp.message.middleware(GlobalLockMiddleware())
    dp.callback_query.middleware(GlobalLockMiddleware())
    
    # 4. Регистрация Роутеров
    # Сначала специфичные, потом общие
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
    asyncio.create_task(run_daily_economy_cycle(bot))
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
