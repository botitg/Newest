"""
economy.py - Экономическая система
Налоги, кредиты, зарплаты и финансовые операции
"""

import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot

from database import db

logger = logging.getLogger(__name__)

# Экономические параметры (дневные ставки)
DAILY_CITIZEN_TAX_RATE = 0.0035  # 0.35% дневного налога
DAILY_MIN_CITIZEN_TAX = 30.0  # Минимум $30/день
DAILY_PROPERTY_TAX_RATE = 0.00025  # 0.025% от стоимости имущества
DAILY_BUSINESS_TAX_RATE = 0.001  # 0.1% дневного налога на бизнес
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015  # 0.15% дневного налога
DAILY_LOAN_PENALTY_RATE = 0.01  # 1% штрафа за просрочку кредита
DAILY_REPUTATION_PENALTY = 0.1  # -0.1 репутации в день за неуплаченные налоги
BUSINESS_EQUIP_BASE_COST = 25000.0  # Базовая стоимость оборудования


async def apply_daily_taxes(bot: Bot = None):
    """
    Ежедневный расчет налогов и сборов.
    Вызывается один раз в день в 00:00.
    """
    try:
        logger.info("=== ЗАПУСК ДНЕВНОГО НАЛОГОВОГО ЦИКЛА ===")
        summary = await db.run_advanced_tax_cycle()
        logger.info(
            "Налоговый цикл завершен: users=%s debtors=%s collected=$%.2f new_debt=$%.2f",
            summary.get("processed_users", 0),
            summary.get("debtors", 0),
            float(summary.get("total_collected", 0)),
            float(summary.get("total_new_debt", 0)),
        )
        
    except Exception as e:
        logger.error(f"Ошибка в экономическом цикле: {e}")


async def calculate_citizen_tax(user_id: int) -> float:
    """
    Расчет ежедневного налога для гражданина.
    Формула: balance * DAILY_CITIZEN_TAX_RATE или DAILY_MIN_CITIZEN_TAX (что больше)
    """
    try:
        user = await db.get_user(user_id)
        balance = user.get('balance', 0)
        
        tax = max(balance * DAILY_CITIZEN_TAX_RATE, DAILY_MIN_CITIZEN_TAX)
        return round(tax, 2)
        
    except Exception as e:
        logger.error(f"Error calculating tax for user {user_id}: {e}")
        return DAILY_MIN_CITIZEN_TAX


async def calculate_business_tax(business_id: int) -> float:
    """
    Расчет налога на бизнес.
    Формула: daily_income * DAILY_BUSINESS_TAX_RATE
    """
    try:
        # business = await db.get_business(business_id)
        daily_income = 1000.0  # Заглушка
        
        tax = daily_income * DAILY_BUSINESS_TAX_RATE
        return round(tax, 2)
        
    except Exception as e:
        logger.error(f"Error calculating business tax for business {business_id}: {e}")
        return 0.0


async def apply_citizen_tax(user_id: int) -> dict:
    """
    Применение налога на доход гражданину.
    Возвращает словарь с информацией о налоге.
    """
    try:
        user = await db.get_user(user_id)
        current_tax = user.get('tax_debt', 0)
        daily_tax = await calculate_citizen_tax(user_id)
        
        # Если баланс недостаточен, накапливаем долг
        if user.get('balance', 0) < daily_tax:
            new_debt = current_tax + daily_tax
            new_balance = user.get('balance', 0)
            new_reputation = user.get('reputation', 50) - DAILY_REPUTATION_PENALTY
        else:
            # Списываем налог
            new_balance = user.get('balance', 0) - daily_tax
            new_debt = current_tax
            new_reputation = user.get('reputation', 50)
        
        # Обновляем пользователя
        await db.update_user(
            user_id,
            balance=new_balance,
            tax_debt=new_debt,
            reputation=max(0, min(100, new_reputation))
        )
        
        return {
            'user_id': user_id,
            'daily_tax': daily_tax,
            'total_debt': new_debt,
            'balance': new_balance,
            'status': 'paid' if new_debt == current_tax else 'unpaid'
        }
        
    except Exception as e:
        logger.error(f"Error applying tax to user {user_id}: {e}")
        return {'error': str(e)}


async def process_loan_payments(user_id: int) -> dict:
    """
    Обработка выплат по кредитам.
    Применяется ежедневно с штрафом за просрочку.
    """
    try:
        user = await db.get_user(user_id)
        # loans = await db.get_user_loans(user_id)
        
        # Для каждого кредита:
        #   1. Считаем процент за день
        #   2. Если не оплачен ежемесячный платёж, применяем штраф
        #   3. Уменьшаем репутацию при просрочке
        
        return {'user_id': user_id, 'loans_processed': 0}
        
    except Exception as e:
        logger.error(f"Error processing loans for user {user_id}: {e}")
        return {'error': str(e)}


async def distribute_government_salaries(org_id: int) -> dict:
    """
    Распределение зарплат сотрудникам организации.
    Вычитается из бюджета организации.
    """
    try:
        org = await db.get_organization_by_id(org_id)
        organization_budget = org.get('budget', 0)
        
        # Получаем всех сотрудников организации
        # members = await db.get_organization_members(org_id)
        
        # total_salaries = sum(member.get('salary', 0) for member in members)
        total_salaries = 0  # Заглушка
        
        if organization_budget < total_salaries:
            # Недостаточно средств
            logger.warning(f"Insufficient budget for org {org_id} salaries")
            return {
                'org_id': org_id,
                'status': 'insufficient_funds',
                'needed': total_salaries,
                'available': organization_budget
            }
        
        # Выплачиваем зарплаты каждому сотруднику
        # for member in members:
        #     salary = member.get('salary', 0)
        #     if salary > 0:
        #         await db.update_user(
        #             member['user_id'],
        #             balance=member.get('balance', 0) + salary
        #         )
        
        # Вычитаем из бюджета
        new_budget = organization_budget - total_salaries
        # await db.update_organization(org_id, budget=new_budget)
        
        return {
            'org_id': org_id,
            'status': 'paid',
            'total_salaries': total_salaries,
            'remaining_budget': new_budget
        }
        
    except Exception as e:
        logger.error(f"Error distributing salaries for org {org_id}: {e}")
        return {'error': str(e)}


async def apply_reputation_decay(user_id: int) -> dict:
    """
    Снижение репутации с течением времени без активности.
    -1 репутация в неделю без активности.
    """
    try:
        user = await db.get_user(user_id)
        current_reputation = user.get('reputation', 50)
        last_activity = user.get('last_activity')
        
        if last_activity:
            # Рассчитываем дни неактивности
            last_activity_date = datetime.fromisoformat(last_activity)
            days_inactive = (datetime.now() - last_activity_date).days
            reputation_decay = days_inactive // 7  # -1 за неделю
        else:
            reputation_decay = 0
        
        new_reputation = max(0, current_reputation - reputation_decay)
        
        # Обновляем репутацию
        await db.update_user(user_id, reputation=new_reputation)
        
        return {
            'user_id': user_id,
            'previous_reputation': current_reputation,
            'new_reputation': new_reputation,
            'decay': reputation_decay
        }
        
    except Exception as e:
        logger.error(f"Error applying reputation decay to user {user_id}: {e}")
        return {'error': str(e)}


async def apply_business_income(business_id: int) -> dict:
    """
    Начисление ежедневного дохода бизнеса.
    Зависит от оборудования и эффективности.
    """
    try:
        # business = await db.get_business(business_id)
        owner_id = 1  # Заглушка
        daily_income = 1000.0  # Заглушка
        
        # Применяем налог
        tax = await calculate_business_tax(business_id)
        net_income = daily_income - tax
        
        # Зачисляем доход владельцу
        owner = await db.get_user(owner_id)
        # await db.update_user(owner_id, balance=owner.get('balance', 0) + net_income)
        
        return {
            'business_id': business_id,
            'gross_income': daily_income,
            'tax': tax,
            'net_income': net_income,
            'owner_id': owner_id
        }
        
    except Exception as e:
        logger.error(f"Error applying business income for business {business_id}: {e}")
        return {'error': str(e)}


async def check_and_freeze_businesses():
    """
    Проверка бизнесов с отрицательным балансом.
    Замораживает бизнес если владелец не может платить расходы.
    """
    try:
        logger.info("Checking businesses for freezing...")
        
        # businesses = await db.get_all_businesses()
        # for business in businesses:
        #     owner = await db.get_user(business['owner_id'])
        #     if owner.get('balance', 0) < business.get('daily_expenses', 0):
        #         await db.update_business(business['id'], frozen=True)
        #         logger.info(f"Business {business['id']} frozen due to insufficient funds")
        
        pass
        
    except Exception as e:
        logger.error(f"Error checking businesses: {e}")


async def process_loan_defaults():
    """
    Обработка просроченных кредитов.
    Если кредит не выплачен за 30 дней, разоряет должника.
    """
    try:
        logger.info("Processing loan defaults...")
        
        # loans = await db.get_overdue_loans(days=30)
        # for loan in loans:
        #     borrower = await db.get_user(loan['borrower_id'])
        #     # Применяем штраф и понижающую репутацию
        #     await db.update_user(
        #         loan['borrower_id'],
        #         reputation=max(0, borrower.get('reputation', 50) - 10),
        #         loan_defaults=borrower.get('loan_defaults', 0) + 1
        #     )
        #     # Список должников может использоваться для розыска
        #     logger.info(f"User {loan['borrower_id']} defaulted on loan {loan['id']}")
        
        pass
        
    except Exception as e:
        logger.error(f"Error processing loan defaults: {e}")


async def update_government_budget(org_id: int = None):
    """
    Обновление государственного бюджета на основе налоговых поступлений.
    Добавляет налоги в бюджет государства.
    """
    try:
        logger.info("Updating government budget from taxes...")
        
        # Получаем государственную организацию
        # gov_org = await db.get_organization("Правительство")
        # 
        # Считаем налоговые поступления за день
        # tax_revenue = 0  # await db.calculate_daily_tax_revenue()
        # 
        # Добавляем в бюджет
        # new_budget = gov_org.get('budget', 0) + tax_revenue
        # await db.update_organization(gov_org['id'], budget=new_budget)
        
        pass
        
    except Exception as e:
        logger.error(f"Error updating government budget: {e}")


async def calculate_government_stability(org_id: int = None) -> float:
    """
    Расчет стабильности правительства на основе корреляций.
    Факторы: коррупция, удовлетворение населения, экономический рост
    """
    try:
        gov = await db.get_government_system()
        
        # Если правительство не инициализировано, возвращаем стандартное значение
        if not gov:
            return 50.0
        
        corruption = gov.get('corruption', 50)
        satisfaction = gov.get('satisfaction', 50)
        
        # Формула: (100 - corruption)/100 * satisfaction/100 * 100
        stability = ((100 - corruption) / 100) * (satisfaction / 100) * 100
        
        return round(stability, 2)
        
    except Exception as e:
        logger.error(f"Error calculating government stability: {e}")
        return 50.0


async def run_daily_economy_cycle(bot: Bot = None):
    """
    Главная функция ежедневного экономического цикла.
    Вызывается один раз в день в 00:00.
    """
    while True:
        logger.info("=" * 50)
        logger.info("ЗАПУСК ЕЖЕДНЕВНОГО ЭКОНОМИЧЕСКОГО ЦИКЛА")
        logger.info("=" * 50)

        try:
            summary = await db.run_advanced_tax_cycle()
            stability = await calculate_government_stability()
            logger.info(
                "Налоговый цикл: users=%s debtors=%s collected=$%.2f new_debt=$%.2f stability=%.2f",
                summary.get("processed_users", 0),
                summary.get("debtors", 0),
                float(summary.get("total_collected", 0)),
                float(summary.get("total_new_debt", 0)),
                stability,
            )
            logger.info("ЭКОНОМИЧЕСКИЙ ЦИКЛ ЗАВЕРШЕН")
        except Exception as e:
            logger.error(f"Critical error in economy cycle: {e}")

        await asyncio.sleep(24 * 60 * 60)


# Готовые функции для быстрого использования
async def give_daily_bonus(user_id: int, amount: float = 1000) -> bool:
    """Выдать ежедневный бонус игроку"""
    try:
        user = await db.get_user(user_id)
        new_balance = user.get('balance', 0) + amount
        await db.update_user(user_id, balance=new_balance)
        return True
    except Exception as e:
        logger.error(f"Error giving bonus to {user_id}: {e}")
        return False


async def fine_player(user_id: int, amount: float) -> bool:
    """Выписать штраф игроку"""
    try:
        user = await db.get_user(user_id)
        new_balance = max(0, user.get('balance', 0) - amount)
        await db.update_user(user_id, balance=new_balance)
        return True
    except Exception as e:
        logger.error(f"Error fining {user_id}: {e}")
        return False


async def transfer_money(from_user_id: int, to_user_id: int, amount: float) -> bool:
    """Трансфер денег между игроками"""
    try:
        from_user = await db.get_user(from_user_id)
        to_user = await db.get_user(to_user_id)
        
        if from_user.get('balance', 0) < amount:
            return False
        
        await db.update_user(
            from_user_id,
            balance=from_user.get('balance', 0) - amount
        )
        
        await db.update_user(
            to_user_id,
            balance=to_user.get('balance', 0) + amount
        )
        
        return True
    except Exception as e:
        logger.error(f"Error transferring money: {e}")
        return False
