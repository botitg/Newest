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
DAILY_CITIZEN_TAX_RATE = 0.0035  # 0.35% дневного налога
DAILY_MIN_CITIZEN_TAX = 3.0  # Минимум $3/день
DAILY_PROPERTY_TAX_RATE = 0.00025  # 0.025% от стоимости имущества
DAILY_BUSINESS_TAX_RATE = 0.001  # 0.1% дневного налога на бизнес
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015  # 0.15% дневного налога
DAILY_LOAN_PENALTY_RATE = 0.01  # 1% штрафа за просрочку кредита
DAILY_REPUTATION_PENALTY = 0.1  # -0.1 репутации в день за неуплаченные налоги
BUSINESS_EQUIP_BASE_COST = 2500.0  # Базовая стоимость оборудования


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
        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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
        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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

        async with aiosqlite.connect(db.db_path) as conn:
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
            last_cycle_date = await db.get_system_state("economy_last_cycle_date")
            if last_cycle_date == cycle_date:
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
            stability = await calculate_government_stability()

            logger.info(
                "Налоговый цикл: users=%s debtors=%s invoices=%s due=$%.2f collected=$%.2f new_debt=$%.2f stability=%.2f",
                summary.get("processed_users", 0),
                summary.get("debtors", 0),
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

            if bot:
                notify_stats = await notify_daily_tax_invoices(bot, cycle_date)
                logger.info(
                    "Daily tax notifications: sent=%s total=%s",
                    int(notify_stats.get("sent", 0)),
                    int(notify_stats.get("total", 0)),
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
                    for uid in tax_users:
                        try:
                            await bot.send_message(uid, tax_text, parse_mode=None)
                        except Exception:
                            logger.warning("Could not send tax summary to user %s", uid)

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
            logger.error(f"Error in money print processor: {e}")
        await asyncio.sleep(30)


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
            f"💳 К оплате сейчас: ${total_due:,.2f}\n\n"
            "Состав платежа:\n"
            f"• Налог на проживание: ${living_tax:,.2f}\n"
            f"• Налог на работу: ${work_tax:,.2f}\n"
            f"• Налог на недвижимость: ${property_tax:,.2f}\n"
            f"• Налог на бизнесы: ${business_tax:,.2f}\n"
            f"• Налог на частные организации: ${private_org_tax:,.2f}\n"
            f"• Проценты по долгу: ${debt_interest:,.2f}\n"
            f"• Плановый платеж: ${scheduled_payment:,.2f}\n\n"
            "Оплатите счет кнопкой ниже, чтобы не накапливать долг."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ Оплатить сейчас ${total_due:,.2f}", callback_data=f"daily_tax_pay_{token}")],
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
            logger.warning("Could not send daily tax invoice to user %s", user_id)

    return {"cycle_date": safe_cycle, "total": len(invoices), "sent": sent, "failed": failed}


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
