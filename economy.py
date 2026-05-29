"""
economy.py - Экономическая система
Налоги, кредиты, зарплаты и финансовые операции
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
import random
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import aiosqlite
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import db

logger = logging.getLogger(__name__)
try:
    UZBEKISTAN_TZ = ZoneInfo("Asia/Tashkent")
except ZoneInfoNotFoundError:
    logger.warning("tzdata не найдена, используем fallback UTC+5 для времени Узбекистана.")
    UZBEKISTAN_TZ = timezone(timedelta(hours=5), name="UTC+5")

# Экономические параметры (дневные ставки)
DAILY_CITIZEN_TAX_RATE = 0.004  # 0.40% дневного налога
DAILY_MIN_CITIZEN_TAX = 3.0  # Минимум $3/день
DAILY_PROPERTY_TAX_RATE = 0.00025  # 0.025% от стоимости имущества
DAILY_BUSINESS_TAX_RATE = 0.001  # 0.1% дневного налога на бизнес
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015  # 0.15% дневного налога
DAILY_LOAN_PENALTY_RATE = 0.007  # 0.7% штрафа за просрочку кредита
DAILY_REPUTATION_PENALTY = 0.05  # мягче штраф по репутации за налоги
BUSINESS_EQUIP_BASE_COST = 3800.0  # Базовая стоимость оборудования


async def apply_daily_taxes(bot: Bot = None):
    """
    Ежедневный расчет налогов и сборов.
    Вызывается один раз в день в 00:00.
    """
    try:
        logger.info("=== ЗАПУСК ДНЕВНОГО НАЛОГОВОГО ЦИКЛА ===")
        summary = await db.run_advanced_tax_cycle()
        business_summary = await db.generate_business_tax_reports()
        loan_summary = await process_all_daily_loan_payments(str(summary.get("cycle_date") or ""))
        logger.info(
            "Налоговый цикл завершен: users=%s debtors=%s collected=$%.2f new_debt=$%.2f",
            summary.get("processed_users", 0),
            summary.get("debtors", 0),
            float(summary.get("total_collected", 0)),
            float(summary.get("total_new_debt", 0)),
        )
        logger.info(
            "Кредитный цикл: borrowers=%s loans=%s paid=%s penalty=%s paid_total=$%.2f penalty_total=$%.2f defaults=%s",
            int(loan_summary.get("borrowers", 0)),
            int(loan_summary.get("loans_processed", 0)),
            int(loan_summary.get("paid_count", 0)),
            int(loan_summary.get("penalty_count", 0)),
            float(loan_summary.get("total_paid", 0)),
            float(loan_summary.get("total_penalty", 0)),
            int(loan_summary.get("defaults", 0)),
        )
        if bot:
            notify_stats = await notify_daily_tax_invoices(bot, str(summary.get("cycle_date") or ""))
            logger.info(
                "Tax invoices notified: sent=%s total=%s",
                int(notify_stats.get("sent", 0)),
                int(notify_stats.get("total", 0)),
            )
        logger.info(
            "Business tax reports: created=%s paid=$%.2f unpaid=%s",
            business_summary.get("reports_created", 0),
            float(business_summary.get("total_tax_paid", 0)),
            business_summary.get("unpaid_count", 0),
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
        query = """
            SELECT income_daily, expense_daily
            FROM businesses
            WHERE id = ?
            LIMIT 1
        """
        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, (int(business_id),)) as cur:
                business = await cur.fetchone()
        if not business:
            return 0.0

        daily_income = float(business["income_daily"] or 0)
        expense_daily = float(business["expense_daily"] or 0)
        taxable_base = max(0.0, daily_income - expense_daily * 0.25)
        tax = taxable_base * DAILY_BUSINESS_TAX_RATE
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
        user = await db.get_user(user_id) or {}
        if not user:
            return {'user_id': user_id, 'loans_processed': 0}

        now = datetime.now().isoformat()
        paid_count = 0
        penalty_count = 0
        total_paid = 0.0
        total_penalty = 0.0

        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("BEGIN IMMEDIATE")
            async with conn.execute(
                """
                SELECT *
                FROM loans
                WHERE applicant_id = ?
                  AND status IN ('approved', 'active')
                  AND COALESCE(remaining_balance, 0) > 0
                ORDER BY application_date ASC
                """,
                (int(user_id),),
            ) as cur:
                loans = await cur.fetchall()

            balance = float(user.get("balance") or 0)
            reputation = float(user.get("reputation") or 50)

            for loan in loans:
                remaining = float(loan["remaining_balance"] or 0)
                if remaining <= 0:
                    continue
                daily_payment = float(loan["daily_payment"] or 0)
                if daily_payment <= 0:
                    term_days = max(30, int(loan["term_months"] or 1) * 30)
                    daily_payment = round(remaining / term_days, 2)

                amount_to_pay = round(min(remaining, daily_payment), 2)
                if amount_to_pay > 0 and balance >= amount_to_pay:
                    balance = round(balance - amount_to_pay, 2)
                    remaining = round(max(0.0, remaining - amount_to_pay), 2)
                    paid_count += 1
                    total_paid += amount_to_pay
                    new_status = "paid" if remaining <= 0 else str(loan["status"] or "active")
                    await conn.execute(
                        """
                        UPDATE loans
                        SET remaining_balance = ?, status = ?, last_payment_date = ?
                        WHERE id = ?
                        """,
                        (remaining, new_status, now, int(loan["id"])),
                    )
                else:
                    penalty = round(remaining * DAILY_LOAN_PENALTY_RATE, 2)
                    remaining = round(remaining + penalty, 2)
                    penalty_count += 1
                    total_penalty += penalty
                    reputation = max(0.0, reputation - 0.2)
                    await conn.execute(
                        """
                        UPDATE loans
                        SET remaining_balance = ?, status = 'active'
                        WHERE id = ?
                        """,
                        (remaining, int(loan["id"])),
                    )

            await conn.execute(
                "UPDATE users SET balance = ?, reputation = ? WHERE user_id = ?",
                (balance, round(reputation, 2), int(user_id)),
            )
            await conn.commit()

        return {
            'user_id': user_id,
            'loans_processed': len(loans),
            'paid_count': paid_count,
            'penalty_count': penalty_count,
            'total_paid': round(total_paid, 2),
            'total_penalty': round(total_penalty, 2),
        }
        
    except Exception as e:
        logger.error(f"Error processing loans for user {user_id}: {e}")
        return {'error': str(e)}


async def process_all_daily_loan_payments(cycle_date: str | None = None) -> dict:
    """
    Глобальный дневной цикл кредитов (один раз в день):
    - списывает daily_payment по всем активным кредитам;
    - при нехватке средств начисляет дневной штраф;
    - запускает обработку дефолтов.
    """
    try:
        safe_cycle = (cycle_date or datetime.now(UZBEKISTAN_TZ).date().isoformat()).strip()
        checkpoint_key = "economy_loan_cycle_date"
        already_done = await db.get_system_state(checkpoint_key)
        if already_done == safe_cycle:
            return {
                "status": "already_processed",
                "cycle_date": safe_cycle,
                "borrowers": 0,
                "loans_processed": 0,
                "paid_count": 0,
                "penalty_count": 0,
                "total_paid": 0.0,
                "total_penalty": 0.0,
                "defaults": 0,
            }

        async with db._connect() as conn:
            async with conn.execute(
                """
                SELECT DISTINCT applicant_id
                FROM loans
                WHERE status IN ('approved', 'active')
                  AND COALESCE(remaining_balance, 0) > 0
                ORDER BY applicant_id ASC
                """
            ) as cur:
                rows = await cur.fetchall()
        borrower_ids = [int(r[0]) for r in rows if r and r[0] is not None]

        borrowers = 0
        loans_processed = 0
        paid_count = 0
        penalty_count = 0
        total_paid = 0.0
        total_penalty = 0.0

        for borrower_id in borrower_ids:
            result = await process_loan_payments(int(borrower_id))
            if result.get("error"):
                continue
            borrowers += 1
            loans_processed += int(result.get("loans_processed", 0) or 0)
            paid_count += int(result.get("paid_count", 0) or 0)
            penalty_count += int(result.get("penalty_count", 0) or 0)
            total_paid = round(total_paid + float(result.get("total_paid", 0) or 0), 2)
            total_penalty = round(total_penalty + float(result.get("total_penalty", 0) or 0), 2)

        defaults_result = await process_loan_defaults()
        defaults = int(defaults_result.get("defaults", 0) or 0)

        await db.set_system_state(checkpoint_key, safe_cycle)
        return {
            "status": "processed",
            "cycle_date": safe_cycle,
            "borrowers": borrowers,
            "loans_processed": loans_processed,
            "paid_count": paid_count,
            "penalty_count": penalty_count,
            "total_paid": round(total_paid, 2),
            "total_penalty": round(total_penalty, 2),
            "defaults": defaults,
        }
    except Exception as e:
        logger.error(f"Error in global daily loan cycle: {e}")
        return {
            "status": "error",
            "cycle_date": (cycle_date or datetime.now(UZBEKISTAN_TZ).date().isoformat()),
            "borrowers": 0,
            "loans_processed": 0,
            "paid_count": 0,
            "penalty_count": 0,
            "total_paid": 0.0,
            "total_penalty": 0.0,
            "defaults": 0,
            "error": str(e),
        }


async def distribute_government_salaries(org_id: int) -> dict:
    """
    Распределение зарплат сотрудникам организации.
    Вычитается из бюджета организации.
    """
    try:
        org = await db.get_organization_by_id(org_id) or {}
        if not org:
            return {'org_id': org_id, 'status': 'not_found'}

        members = await db.get_organization_members(org_id, limit=500)
        total_salaries = round(sum(float(m.get('salary') or 0) for m in members if float(m.get('salary') or 0) > 0), 2)
        organization_budget = float(org.get('budget') or 0)

        if total_salaries <= 0:
            return {
                'org_id': org_id,
                'status': 'nothing_to_pay',
                'total_salaries': 0.0,
                'remaining_budget': organization_budget,
            }

        pay_ratio = 1.0 if organization_budget >= total_salaries else max(0.0, organization_budget / total_salaries)
        paid_total = 0.0
        paid_members = 0

        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("BEGIN IMMEDIATE")
            for member in members:
                salary = float(member.get('salary') or 0)
                if salary <= 0:
                    continue
                payment = round(salary * pay_ratio, 2)
                if payment <= 0:
                    continue
                async with conn.execute("SELECT balance FROM users WHERE user_id = ?", (int(member["user_id"]),)) as cur:
                    row = await cur.fetchone()
                if not row:
                    continue
                new_balance = round(float(row["balance"] or 0) + payment, 2)
                await conn.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (new_balance, int(member["user_id"])),
                )
                paid_total = round(paid_total + payment, 2)
                paid_members += 1

            new_budget = round(max(0.0, organization_budget - paid_total), 2)
            await conn.execute("UPDATE organizations SET budget = ? WHERE id = ?", (new_budget, int(org_id)))
            await conn.commit()

        return {
            'org_id': org_id,
            'status': 'paid_full' if pay_ratio >= 0.999 else 'paid_partial',
            'paid_members': paid_members,
            'total_salaries': total_salaries,
            'paid_total': paid_total,
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
        query = """
            SELECT id, owner_id, income_daily, expense_daily, budget, status
            FROM businesses
            WHERE id = ?
            LIMIT 1
        """
        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, (int(business_id),)) as cur:
                business = await cur.fetchone()
        if not business:
            return {'error': f'business {business_id} not found'}
        if str(business["status"] or "active") == "frozen":
            return {'business_id': business_id, 'status': 'frozen', 'net_income': 0.0}

        owner_id = int(business["owner_id"] or 0)
        gross_base = float(business["income_daily"] or 0)
        expense = float(business["expense_daily"] or 0)
        variation = random.uniform(0.88, 1.17)
        gross_income = round(max(0.0, gross_base * variation), 2)
        tax = await calculate_business_tax(business_id)
        net_income = round(gross_income - expense - tax, 2)

        owner = await db.get_user(owner_id) or {}
        owner_balance = round(float(owner.get("balance") or 0) + net_income, 2)
        business_budget = round(float(business["budget"] or 0) + net_income, 2)
        await db.update_user(owner_id, balance=max(0.0, owner_balance))

        async with db._connect() as conn:
            await conn.execute(
                "UPDATE businesses SET budget = ?, last_income_date = ? WHERE id = ?",
                (business_budget, datetime.now().isoformat(), int(business_id)),
            )
            await conn.commit()

        return {
            'business_id': business_id,
            'gross_income': gross_income,
            'expense': expense,
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
        active = await db.list_all_businesses(limit=1000)
        frozen_count = 0
        unfrozen_count = 0

        async with db._connect() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            for business in active:
                bid = int(business.get("id") or 0)
                owner_id = int(business.get("owner_id") or 0)
                expense = float(business.get("expense_daily") or 0)
                status = str(business.get("status") or "active")
                biz_budget = float(business.get("budget") or 0)
                owner = await db.get_user(owner_id) or {}
                owner_balance = float(owner.get("balance") or 0)
                runway = owner_balance + biz_budget
                need = max(300.0, expense * 2)

                if runway < need and status != "frozen":
                    await conn.execute("UPDATE businesses SET status = 'frozen' WHERE id = ?", (bid,))
                    frozen_count += 1
                elif runway >= need * 2 and status == "frozen":
                    await conn.execute("UPDATE businesses SET status = 'active' WHERE id = ?", (bid,))
                    unfrozen_count += 1
            await conn.commit()

        logger.info("Business freeze check completed: frozen=%s unfrozen=%s", frozen_count, unfrozen_count)
        return {"frozen": frozen_count, "unfrozen": unfrozen_count}
        
    except Exception as e:
        logger.error(f"Error checking businesses: {e}")


async def process_loan_defaults():
    """
    Обработка просроченных кредитов.
    Если кредит не выплачен за 30 дней, разоряет должника.
    """
    try:
        logger.info("Processing loan defaults...")
        now = datetime.now()
        defaults = 0

        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("BEGIN IMMEDIATE")
            async with conn.execute(
                """
                SELECT id, applicant_id, remaining_balance, due_date
                FROM loans
                WHERE status IN ('approved', 'active')
                  AND COALESCE(remaining_balance, 0) > 0
                  AND due_date IS NOT NULL
                """
            ) as cur:
                loans = await cur.fetchall()

            for loan in loans:
                due_raw = str(loan["due_date"] or "").strip()
                try:
                    due = datetime.fromisoformat(due_raw)
                except Exception:
                    continue
                if (now - due).days < 30:
                    continue

                borrower_id = int(loan["applicant_id"] or 0)
                remaining = float(loan["remaining_balance"] or 0)
                penalty_debt = round(remaining * 0.05, 2)

                await conn.execute(
                    "UPDATE loans SET status = 'defaulted' WHERE id = ?",
                    (int(loan["id"]),),
                )
                await conn.execute(
                    """
                    UPDATE users
                    SET reputation = MAX(0, COALESCE(reputation, 50) - 10),
                        loan_defaults = COALESCE(loan_defaults, 0) + 1,
                        tax_debt = COALESCE(tax_debt, 0) + ?
                    WHERE user_id = ?
                    """,
                    (penalty_debt, borrower_id),
                )
                defaults += 1
            await conn.commit()

        logger.info("Loan defaults processed: %s", defaults)
        return {"defaults": defaults}
        
    except Exception as e:
        logger.error(f"Error processing loan defaults: {e}")


async def update_government_budget(org_id: int = None):
    """
    Обновление государственного бюджета на основе налоговых поступлений.
    Добавляет налоги в бюджет государства.
    """
    try:
        logger.info("Updating government budget from taxes...")
        target_date = datetime.now(UZBEKISTAN_TZ).date().isoformat()
        checkpoint_key = "economy_budget_update_date"
        already_done = await db.get_system_state(checkpoint_key)
        if already_done == target_date:
            return {"status": "already_updated", "date": target_date, "added": 0.0}

        gov_org = await db.get_organization("Правительство")
        if not gov_org:
            return {"status": "no_government_org", "added": 0.0}

        async with db._connect() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT COALESCE(SUM(paid_total), 0) AS revenue
                FROM tax_logs
                WHERE cycle_date = ?
                """,
                (target_date,),
            ) as cur:
                row = await cur.fetchone()
                revenue = round(float(row["revenue"] or 0), 2) if row else 0.0

            if revenue > 0:
                new_budget = round(float(gov_org.get("budget") or 0) + revenue, 2)
                await conn.execute(
                    "UPDATE organizations SET budget = ? WHERE id = ?",
                    (new_budget, int(gov_org["id"])),
                )
                await conn.commit()
            else:
                new_budget = float(gov_org.get("budget") or 0)

        await db.set_system_state(checkpoint_key, target_date)
        return {"status": "updated", "date": target_date, "added": revenue, "new_budget": new_budget}
        
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
    """Run economy cycle once per calendar day (Asia/Tashkent)."""
    while True:
        try:
            now_uz = datetime.now(UZBEKISTAN_TZ)
            cycle_date = now_uz.date().isoformat()
            hour_slot = now_uz.strftime("%Y-%m-%d %H")

            salary_hourly = await db.process_hourly_salary_to_bank(hour_slot=hour_slot)
            if salary_hourly.get("status") == "processed":
                logger.info(
                    "Hourly salary: paid_users=%s total=$%.2f org_paid=$%.2f citizen_paid=$%.2f partial_org=%s slot=%s",
                    int(salary_hourly.get("paid_users", 0)),
                    float(salary_hourly.get("total_paid", 0)),
                    float(salary_hourly.get("total_org_paid", 0)),
                    float(salary_hourly.get("total_citizen_paid", 0)),
                    int(salary_hourly.get("partial_org_payments", 0)),
                    salary_hourly.get("slot"),
                )
                if bot:
                    salary_notify = await notify_hourly_salary_credits(
                        bot=bot,
                        hour_slot=str(salary_hourly.get("slot") or hour_slot),
                        payments=list(salary_hourly.get("payments") or []),
                    )
                    if int(salary_notify.get("sent", 0)) > 0:
                        logger.info(
                            "Hourly salary notifications: sent=%s total=%s",
                            int(salary_notify.get("sent", 0)),
                            int(salary_notify.get("total", 0)),
                        )

            interest_hourly = await db.apply_hourly_bank_interest(hour_slot=hour_slot)
            if interest_hourly.get("status") == "processed":
                logger.info(
                    "Hourly bank interest: users=%s total=$%.2f slot=%s",
                    int(interest_hourly.get("credited_users", 0)),
                    float(interest_hourly.get("total_interest", 0)),
                    interest_hourly.get("slot"),
                )
                if bot:
                    interest_notify = await notify_hourly_bank_interest_credits(
                        bot=bot,
                        hour_slot=str(interest_hourly.get("slot") or hour_slot),
                        credits=list(interest_hourly.get("credits") or []),
                    )
                    if int(interest_notify.get("sent", 0)) > 0:
                        logger.info(
                            "Hourly bank interest notifications: sent=%s total=%s",
                            int(interest_notify.get("sent", 0)),
                            int(interest_notify.get("total", 0)),
                        )

            enterprise_hourly = await db.run_hourly_enterprise_income(hour_slot=hour_slot)
            if enterprise_hourly.get("status") == "processed":
                logger.info(
                    "Hourly enterprise income: businesses=%s net=$%.2f owner_bonus=$%.2f private_orgs=%s net=$%.2f leader_bonus=$%.2f slot=%s",
                    int(enterprise_hourly.get("businesses_processed", 0)),
                    float(enterprise_hourly.get("business_total_net", 0)),
                    float(enterprise_hourly.get("owner_dividend_total", 0)),
                    int(enterprise_hourly.get("private_orgs_processed", 0)),
                    float(enterprise_hourly.get("private_org_total_net", 0)),
                    float(enterprise_hourly.get("leader_bonus_total", 0)),
                    enterprise_hourly.get("slot"),
                )
                if bot:
                    passive_notify = await notify_hourly_enterprise_credits(
                        bot=bot,
                        hour_slot=str(enterprise_hourly.get("slot") or hour_slot),
                        owner_credits=list(enterprise_hourly.get("owner_credits") or []),
                        leader_credits=list(enterprise_hourly.get("leader_credits") or []),
                    )
                    if int(passive_notify.get("sent", 0)) > 0:
                        logger.info(
                            "Hourly enterprise income notifications: sent=%s total=%s",
                            int(passive_notify.get("sent", 0)),
                            int(passive_notify.get("total", 0)),
                        )

            penalty_window = now_uz.hour == 20 and now_uz.minute >= 50

            last_cycle_date = await db.get_system_state("economy_last_cycle_date")
            if last_cycle_date == cycle_date:
                if penalty_window:
                    penalty_summary = await db.apply_daily_tax_nonpayment_penalty(cycle_date=cycle_date)
                    if penalty_summary.get("status") == "applied":
                        logger.info(
                            "Tax nonpayment penalty applied: debtors=%s penalized=%s due=$%.2f charged=$%.2f cycle=%s",
                            int(penalty_summary.get("processed_debtors", 0)),
                            int(penalty_summary.get("penalized_users", 0)),
                            float(penalty_summary.get("total_penalty_due", 0)),
                            float(penalty_summary.get("total_balance_penalty", 0)),
                            penalty_summary.get("cycle_date"),
                        )
                loan_retry_summary = await process_all_daily_loan_payments(cycle_date)
                if loan_retry_summary.get("status") == "processed":
                    logger.info(
                        "Кредитный цикл (retry): borrowers=%s loans=%s paid=%s penalty=%s paid_total=$%.2f penalty_total=$%.2f defaults=%s",
                        int(loan_retry_summary.get("borrowers", 0)),
                        int(loan_retry_summary.get("loans_processed", 0)),
                        int(loan_retry_summary.get("paid_count", 0)),
                        int(loan_retry_summary.get("penalty_count", 0)),
                        float(loan_retry_summary.get("total_paid", 0)),
                        float(loan_retry_summary.get("total_penalty", 0)),
                        int(loan_retry_summary.get("defaults", 0)),
                    )
                if bot:
                    notify_stats = await notify_daily_tax_invoices(bot, cycle_date)
                    if int(notify_stats.get("sent", 0)) > 0:
                        logger.info(
                            "Daily tax notifications retry: sent=%s total=%s",
                            int(notify_stats.get("sent", 0)),
                            int(notify_stats.get("total", 0)),
                        )
                await asyncio.sleep(60)
                continue

            logger.info("=" * 50)
            logger.info("ЗАПУСК ЕЖЕДНЕВНОГО ЭКОНОМИЧЕСКОГО ЦИКЛА")
            logger.info("=" * 50)

            summary = await db.run_advanced_tax_cycle(cycle_date=cycle_date)
            business_summary = await db.generate_business_tax_reports()
            loan_summary = await process_all_daily_loan_payments(cycle_date)
            inflation_summary = await db.apply_daily_inflation()
            education_decay = await db.apply_daily_education_decay(max_drop_per_cycle=1)
            family_summary = await db.process_daily_family_expenses(cycle_date=cycle_date)
            stability = await calculate_government_stability()

            logger.info(
                "Налоговый цикл: users=%s debtors=%s penalties=%s penalty_total=$%.2f invoices=%s due=$%.2f collected=$%.2f new_debt=$%.2f stability=%.2f",
                summary.get("processed_users", 0),
                summary.get("debtors", 0),
                summary.get("penalized_users", 0),
                float(summary.get("total_balance_penalty", 0)),
                summary.get("created_invoices", 0),
                float(summary.get("total_due_created", 0)),
                float(summary.get("total_collected", 0)),
                float(summary.get("total_new_debt", 0)),
                stability,
            )
            logger.info(
                "Business tax reports: created=%s paid=$%.2f unpaid=%s",
                business_summary.get("reports_created", 0),
                float(business_summary.get("total_tax_paid", 0)),
                business_summary.get("unpaid_count", 0),
            )
            logger.info(
                "Кредитный цикл: borrowers=%s loans=%s paid=%s penalty=%s paid_total=$%.2f penalty_total=$%.2f defaults=%s",
                int(loan_summary.get("borrowers", 0)),
                int(loan_summary.get("loans_processed", 0)),
                int(loan_summary.get("paid_count", 0)),
                int(loan_summary.get("penalty_count", 0)),
                float(loan_summary.get("total_paid", 0)),
                float(loan_summary.get("total_penalty", 0)),
                int(loan_summary.get("defaults", 0)),
            )
            if inflation_summary.get("applied"):
                logger.info(
                    "Inflation updated: rate=%.4f%% factor=%.6f index=%.6f",
                    float(inflation_summary.get("inflation_daily_rate", 0)) * 100,
                    float(inflation_summary.get("inflation_factor", 1)),
                    float(inflation_summary.get("inflation_index_after", 1)),
                )
            else:
                logger.info(
                    "Inflation already applied today: index=%.6f",
                    float(inflation_summary.get("inflation_index", inflation_summary.get("inflation_index_after", 1))),
                )
            logger.info(
                "Education control: status=%s reminded_users=%s decreased_users=%s",
                education_decay.get("status"),
                int(education_decay.get("reminded_users", 0)),
                int(education_decay.get("decreased_users", 0)),
            )
            logger.info(
                "Family expenses: status=%s users=%s charged=$%.2f paid=$%.2f debt_added=$%.2f",
                family_summary.get("status"),
                int(family_summary.get("processed_users", 0)),
                float(family_summary.get("total_charged", 0)),
                float(family_summary.get("total_paid", 0)),
                float(family_summary.get("total_debt_added", 0)),
            )

            if bot:
                notify_stats = await notify_daily_tax_invoices(bot, cycle_date)
                logger.info(
                    "Daily tax notifications: sent=%s total=%s",
                    int(notify_stats.get("sent", 0)),
                    int(notify_stats.get("total", 0)),
                )
                family_notify = await notify_daily_family_expenses(
                    bot=bot,
                    cycle_date=cycle_date,
                    charges=list(family_summary.get("charges") or []),
                )
                if int(family_notify.get("sent", 0)) > 0:
                    logger.info(
                        "Family expense notifications: sent=%s total=%s",
                        int(family_notify.get("sent", 0)),
                        int(family_notify.get("total", 0)),
                    )
                education_notify = await notify_education_discipline(bot, education_decay)
                if int(education_notify.get("sent", 0)) > 0:
                    logger.info(
                        "Education discipline notifications: sent=%s total=%s",
                        int(education_notify.get("sent", 0)),
                        int(education_notify.get("total", 0)),
                    )
                tax_users = await db.get_tax_service_user_ids()
                if tax_users:
                    tax_text = (
                        "🧾 Налоговая сводка за цикл\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"Создано ежедневных счетов: {int(summary.get('created_invoices', 0))}\n"
                        f"Сумма к оплате сегодня: ${float(summary.get('total_due_created', 0)):,.2f}\n"
                        f"Бизнес-отчетов: {business_summary.get('reports_created', 0)}\n"
                        f"Оплачено бизнес-налогов: ${float(business_summary.get('total_tax_paid', 0)):,.2f}\n"
                        f"Неоплаченных: {business_summary.get('unpaid_count', 0)}\n"
                        f"Инфляция за сутки: {float(inflation_summary.get('inflation_daily_rate', 0)) * 100:.2f}%\n"
                        f"Индекс инфляции: {float(inflation_summary.get('inflation_index_after', inflation_summary.get('inflation_index', 1))):.4f}\n"
                        f"Дата цикла: {business_summary.get('cycle_date')}"
                    )
                    tax_summary_sent = 0
                    tax_summary_failed = 0
                    for uid in tax_users:
                        try:
                            await bot.send_message(uid, tax_text, parse_mode=None)
                            tax_summary_sent += 1
                        except Exception:
                            tax_summary_failed += 1
                            logger.debug("Could not send tax summary to user %s", uid)
                    if tax_summary_failed > 0:
                        logger.info(
                            "Tax summary notifications: sent=%s failed=%s",
                            tax_summary_sent,
                            tax_summary_failed,
                        )

            if penalty_window:
                penalty_summary = await db.apply_daily_tax_nonpayment_penalty(cycle_date=cycle_date)
                if penalty_summary.get("status") == "applied":
                    logger.info(
                        "Tax nonpayment penalty applied: debtors=%s penalized=%s due=$%.2f charged=$%.2f cycle=%s",
                        int(penalty_summary.get("processed_debtors", 0)),
                        int(penalty_summary.get("penalized_users", 0)),
                        float(penalty_summary.get("total_penalty_due", 0)),
                        float(penalty_summary.get("total_balance_penalty", 0)),
                        penalty_summary.get("cycle_date"),
                    )

            await db.set_system_state("economy_last_cycle_date", cycle_date)
            logger.info("ЭКОНОМИЧЕСКИЙ ЦИКЛ ЗАВЕРШЕН")
        except Exception as e:
            logger.error(f"Critical error in economy cycle: {e}")

        await asyncio.sleep(60)


async def run_state_money_print_processor(bot: Bot = None):
    """Периодически завершает готовые задания печати денег."""
    while True:
        try:
            result = await db.claim_ready_state_money_print_jobs(actor_id=None, enforce_authority=False)
            claimed = int(result.get("claimed_jobs") or 0)
            if claimed > 0:
                minted = float(result.get("minted_total") or 0)
                gov_budget = float(result.get("government_budget_after") or 0)
                logger.info(
                    "State money print jobs completed: count=%s minted=$%.2f gov_budget=$%.2f",
                    claimed,
                    minted,
                    gov_budget,
                )
        except Exception as e:
            if "database is locked" in str(e).lower():
                logger.warning("Money print processor skipped: database is locked")
            else:
                logger.error(f"Error in money print processor: {e}")
        await asyncio.sleep(90)


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


async def notify_daily_tax_invoices(bot: Bot, cycle_date: str) -> dict:
    """Разослать игрокам уведомления об ежедневном налоге с кнопкой оплаты."""
    safe_cycle = str(cycle_date or "").strip()
    if not safe_cycle:
        safe_cycle = datetime.now(UZBEKISTAN_TZ).date().isoformat()

    token = safe_cycle.replace("-", "")
    invoices = await db.list_pending_daily_tax_invoices(
        cycle_date=safe_cycle,
        limit=20_000,
        only_not_notified=True,
    )
    sent = 0
    failed = 0
    for row in invoices:
        user_id = int(row.get("user_id") or 0)
        if user_id <= 0:
            continue
        total_due = float(row.get("total_due") or 0)
        if total_due <= 0:
            await db.mark_daily_tax_invoice_notified(user_id, safe_cycle)
            continue
        living_tax = float(row.get("living_tax") or 0)
        work_tax = float(row.get("work_tax") or 0)
        property_tax = float(row.get("property_tax") or 0)
        business_tax = float(row.get("business_tax") or 0)
        private_org_tax = float(row.get("private_org_tax") or 0)
        citizen_tax = float(row.get("citizen_tax") or 0)
        if living_tax <= 0 and citizen_tax > 0:
            living_tax = min(citizen_tax, 5000.0)
        debt_interest = float(row.get("debt_interest") or 0)
        scheduled_payment = float(row.get("scheduled_payment") or 0)

        text = (
            "🧾 НАЛОГОВОЕ УВЕДОМЛЕНИЕ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Дата счета: {safe_cycle}\n"
            f"💳 К оплате сейчас: {total_due:,.2f} люмов\n\n"
            "Состав платежа:\n"
            f"• Налог на проживание: {living_tax:,.2f} люмов\n"
            f"• Налог на работу: {work_tax:,.2f} люмов\n"
            f"• Налог на недвижимость и капитал: {property_tax:,.2f} люмов\n"
            f"• Налог на бизнесы и банды: {business_tax:,.2f} люмов\n"
            f"• Налог на частные организации: {private_org_tax:,.2f} люмов\n"
            f"• Проценты по долгу: {debt_interest:,.2f} люмов\n"
            f"• Плановый платеж: {scheduled_payment:,.2f} люмов\n\n"
            "Оплатите счет кнопкой ниже, чтобы не накапливать долг.\n"
            "⚠️ При просрочке списывается штраф 1.5% от общего налогового долга."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ Оплатить сейчас {total_due:,.2f} люмов", callback_data=f"daily_tax_pay_{token}")],
            ]
        )
        try:
            sent_message = await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode=None)
            # По запросу игроков пытаемся закрепить налоговый счет в чате.
            try:
                await bot.pin_chat_message(
                    chat_id=user_id,
                    message_id=sent_message.message_id,
                    disable_notification=True,
                )
            except Exception:
                pass
            await db.mark_daily_tax_invoice_notified(user_id, safe_cycle)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send daily tax invoice to user %s", user_id)

    return {"cycle_date": safe_cycle, "total": len(invoices), "sent": sent, "failed": failed}


async def notify_hourly_salary_credits(bot: Bot, hour_slot: str, payments: list[dict]) -> dict:
    """Разослать игрокам уведомления о почасовом зачислении зарплаты."""
    safe_slot = str(hour_slot or "").strip()[:13] or datetime.now(UZBEKISTAN_TZ).strftime("%Y-%m-%d %H")
    sent = 0
    failed = 0
    for row in payments or []:
        user_id = int(row.get("user_id") or 0)
        payout_total = float(row.get("payout_total") or 0)
        if user_id <= 0 or payout_total <= 0:
            continue
        citizen_part = float(row.get("citizen_part") or 0)
        citizen_job_title = str(row.get("citizen_job_title") or "").strip()
        org_part = float(row.get("org_part") or 0)
        org_expected = float(row.get("org_expected") or 0)
        org_name = str(row.get("org_name") or "").strip()
        bank_after = float(row.get("bank_after") or 0)
        org_line = ""
        if org_part > 0:
            org_line = f"\n• Организация{f' ({org_name})' if org_name else ''}: {org_part:,.2f} люмов"
            if org_expected > org_part:
                org_line += " (частично)"

        citizen_line = f"• Гражданская работа: {citizen_part:,.2f} люмов"
        if citizen_part > 0 and citizen_job_title:
            citizen_line += f" ({citizen_job_title})"

        text = (
            "💼 ПОЧАСОВАЯ ЗАРПЛАТА\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Час начисления: {safe_slot}:00\n"
            f"{citizen_line}"
            f"{org_line}\n"
            f"✅ Итого зачислено: {payout_total:,.2f} люмов\n"
            f"🏦 Баланс банковского счета: {bank_after:,.2f} люмов"
        )
        try:
            await bot.send_message(user_id, text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send hourly salary notification to user %s", user_id)

    return {"hour_slot": safe_slot, "total": len(payments or []), "sent": sent, "failed": failed}


async def notify_hourly_bank_interest_credits(bot: Bot, hour_slot: str, credits: list[dict]) -> dict:
    """Разослать уведомления о почасовых процентах по банковскому счету."""
    safe_slot = str(hour_slot or "").strip()[:13] or datetime.now(UZBEKISTAN_TZ).strftime("%Y-%m-%d %H")
    sent = 0
    failed = 0
    total = 0
    for row in credits or []:
        user_id = int(row.get("user_id") or 0)
        amount = float(row.get("amount") or 0)
        if user_id <= 0 or amount <= 0:
            continue
        total += 1
        rate = float(row.get("rate") or 0)
        bank_after = float(row.get("bank_after") or 0)
        text = (
            "🏦 ПОЧАСОВОЙ БАНКОВСКИЙ ДОХОД\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Час начисления: {safe_slot}:00\n"
            f"• Ставка: {rate * 100:.4f}%/ч\n"
            f"✅ Начислено: {amount:,.2f} люмов\n"
            f"🏦 Банк после начисления: {bank_after:,.2f} люмов"
        )
        try:
            await bot.send_message(user_id, text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send hourly bank interest notification to user %s", user_id)
    return {"hour_slot": safe_slot, "total": total, "sent": sent, "failed": failed}


async def notify_hourly_enterprise_credits(
    bot: Bot,
    hour_slot: str,
    owner_credits: list[dict],
    leader_credits: list[dict],
) -> dict:
    """Разослать уведомления о пассивном доходе с бизнеса и частных организаций."""
    safe_slot = str(hour_slot or "").strip()[:13] or datetime.now(UZBEKISTAN_TZ).strftime("%Y-%m-%d %H")
    aggregate: dict[int, dict] = {}

    for row in owner_credits or []:
        user_id = int(row.get("user_id") or 0)
        amount = float(row.get("amount") or 0)
        if user_id <= 0 or amount <= 0:
            continue
        state = aggregate.setdefault(
            user_id,
            {"owner_total": 0.0, "owner_count": 0, "leader_total": 0.0, "leader_count": 0},
        )
        state["owner_total"] = round(float(state["owner_total"]) + amount, 2)
        state["owner_count"] = int(state["owner_count"]) + 1

    for row in leader_credits or []:
        user_id = int(row.get("user_id") or 0)
        amount = float(row.get("amount") or 0)
        if user_id <= 0 or amount <= 0:
            continue
        state = aggregate.setdefault(
            user_id,
            {"owner_total": 0.0, "owner_count": 0, "leader_total": 0.0, "leader_count": 0},
        )
        state["leader_total"] = round(float(state["leader_total"]) + amount, 2)
        state["leader_count"] = int(state["leader_count"]) + 1

    sent = 0
    failed = 0
    total = len(aggregate)
    for user_id, payload in aggregate.items():
        owner_total = round(float(payload.get("owner_total") or 0), 2)
        leader_total = round(float(payload.get("leader_total") or 0), 2)
        owner_count = int(payload.get("owner_count") or 0)
        leader_count = int(payload.get("leader_count") or 0)
        total_income = round(owner_total + leader_total, 2)
        if total_income <= 0:
            continue

        parts = []
        if owner_total > 0:
            parts.append(f"• Бизнес-дивиденды ({owner_count}): {owner_total:,.2f} люмов")
        if leader_total > 0:
            parts.append(f"• Бонусы лидера частной орг. ({leader_count}): {leader_total:,.2f} люмов")
        parts_text = "\n".join(parts) if parts else "• Начислений нет"
        text = (
            "💹 ПАССИВНЫЙ ДОХОД\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Час начисления: {safe_slot}:00\n"
            f"{parts_text}\n"
            f"✅ Итого начислено: {total_income:,.2f} люмов"
        )
        try:
            await bot.send_message(int(user_id), text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send hourly enterprise income notification to user %s", user_id)
    return {"hour_slot": safe_slot, "total": total, "sent": sent, "failed": failed}


async def notify_daily_family_expenses(bot: Bot, cycle_date: str, charges: list[dict]) -> dict:
    """Разослать игрокам уведомления о ежедневных семейных расходах."""
    safe_cycle = str(cycle_date or "").strip() or datetime.now(UZBEKISTAN_TZ).date().isoformat()
    sent = 0
    failed = 0
    total = 0

    for row in charges or []:
        user_id = int(row.get("user_id") or 0)
        if user_id <= 0:
            continue
        total += 1
        expense_total = float(row.get("expense_total") or 0)
        base_expense = float(row.get("base_expense") or 0)
        pet_expense = float(row.get("pet_expense") or 0)
        paid_total = float(row.get("paid_total") or 0)
        debt_added = float(row.get("debt_added") or 0)
        pet_count = int(row.get("pet_count") or 0)
        partner_id = int(row.get("partner_id") or 0)
        relation_level = int(row.get("relationship_level") or 0)
        relation_multiplier = float(row.get("relationship_multiplier") or 1.0)

        spouse_line = (
            f"• Семейный быт: {base_expense:,.2f} люмов (ур. {relation_level}/25, x{relation_multiplier:.2f})"
            if partner_id > 0
            else ""
        )
        pet_line = f"• Уход за питомцами ({pet_count}): {pet_expense:,.2f} люмов" if pet_count > 0 else ""
        details = [line for line in (spouse_line, pet_line) if line]
        details_text = "\n".join(details) if details else "• Дополнительных расходов нет"
        debt_line = (
            f"\n⚠️ В семейный долг добавлено: {debt_added:,.2f} люмов"
            if debt_added > 0
            else "\n✅ Полностью оплачено без долга."
        )
        text = (
            "🏠 ЕЖЕДНЕВНЫЕ СЕМЕЙНЫЕ РАСХОДЫ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Цикл: {safe_cycle}\n"
            f"{details_text}\n"
            f"💸 Начислено: {expense_total:,.2f} люмов\n"
            f"✅ Списано сейчас: {paid_total:,.2f} люмов"
            f"{debt_line}"
        )
        try:
            await bot.send_message(user_id, text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send family expense notification to user %s", user_id)

    return {"cycle_date": safe_cycle, "total": total, "sent": sent, "failed": failed}


async def notify_education_discipline(bot: Bot, decay_result: dict) -> dict:
    """Уведомления по ежедневной дисциплине обучения."""
    payload = decay_result or {}
    reminded_raw = payload.get("reminder_user_ids") or []
    decreased_raw = payload.get("decreased_user_ids") or []
    reminded_ids = []
    for uid in reminded_raw:
        try:
            safe_uid = int(uid)
        except Exception:
            safe_uid = 0
        if safe_uid > 0 and safe_uid not in reminded_ids:
            reminded_ids.append(safe_uid)

    decreased_ids = set()
    for uid in decreased_raw:
        try:
            safe_uid = int(uid)
        except Exception:
            safe_uid = 0
        if safe_uid > 0:
            decreased_ids.add(safe_uid)

    sent = 0
    failed = 0
    total = len(reminded_ids)
    for user_id in reminded_ids:
        dropped = user_id in decreased_ids
        if dropped:
            text = (
                "🎓 КОНТРОЛЬ ОБРАЗОВАНИЯ\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Вы пропустили обучение после вчерашнего напоминания.\n"
                "⚠️ Уровень образования снижен на 1.\n"
                "Зайдите в раздел «Образование» и выполните занятие сегодня, чтобы избежать следующего штрафа."
            )
        else:
            text = (
                "🎓 НАПОМИНАНИЕ ОБ ОБРАЗОВАНИИ\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Сегодня вы еще не занимались обучением.\n"
                "Зайдите в раздел «Образование» и пройдите тест или учебную сессию.\n"
                "Если проигнорировать напоминание, завтра уровень образования снизится на 1."
            )
        try:
            await bot.send_message(user_id, text, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            logger.debug("Could not send education discipline notification to user %s", user_id)

    return {
        "total": total,
        "sent": sent,
        "failed": failed,
        "decreased_notified": len([uid for uid in reminded_ids if uid in decreased_ids]),
    }


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

