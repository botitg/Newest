"""
Асинхронная база данных на aiosqlite для нового Telegram-бота (aiogram 3.x)
Все операции async/await, никаких блокировок
"""

import aiosqlite
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import sqlite3
import random
import os
import re

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_game_async.db")

# Экономические параметры
DAILY_CITIZEN_TAX_RATE = 0.0035
DAILY_MIN_CITIZEN_TAX = 3.0
DAILY_PROPERTY_TAX_RATE = 0.00025
DAILY_BUSINESS_TAX_RATE = 0.001
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015
DAILY_LOAN_PENALTY_RATE = 0.01
BUSINESS_EQUIP_BASE_COST = 2500.0
PRIVATE_ORG_EQUIP_MULTIPLIER = 5.0

INVISIBLE_NAME_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")

JOB_CATALOG: List[Dict[str, Any]] = [
    {
        "code": "cleaner",
        "title": "Городской уборщик",
        "salary": 220.0,
        "edu_required": 1,
        "rep_required": 0.0,
        "description": "Базовая работа для старта карьеры.",
    },
    {
        "code": "clerk",
        "title": "Муниципальный клерк",
        "salary": 360.0,
        "edu_required": 2,
        "rep_required": 12.0,
        "description": "Работа с документами и городскими сервисами.",
    },
    {
        "code": "loader",
        "title": "Складской грузчик",
        "salary": 300.0,
        "edu_required": 1,
        "rep_required": 4.0,
        "description": "Погрузка, учет поставок и помощь складу.",
    },
    {
        "code": "driver",
        "title": "Городской водитель",
        "salary": 410.0,
        "edu_required": 2,
        "rep_required": 10.0,
        "description": "Перевозка сотрудников и городских грузов.",
    },
    {
        "code": "dispatcher",
        "title": "Диспетчер службы",
        "salary": 470.0,
        "edu_required": 2,
        "rep_required": 14.0,
        "description": "Координация заявок, вызовов и смен.",
    },
    {
        "code": "tech_support",
        "title": "Техподдержка",
        "salary": 520.0,
        "edu_required": 3,
        "rep_required": 16.0,
        "description": "Помощь гражданам и организациям по техвопросам.",
    },
    {
        "code": "medic_assistant",
        "title": "Фельдшер",
        "salary": 520.0,
        "edu_required": 3,
        "rep_required": 18.0,
        "description": "Помощь медперсоналу и городским службам.",
    },
    {
        "code": "officer",
        "title": "Патрульный офицер",
        "salary": 560.0,
        "edu_required": 3,
        "rep_required": 22.0,
        "description": "Поддержка порядка и патрулирование районов.",
    },
    {
        "code": "accountant",
        "title": "Муниципальный бухгалтер",
        "salary": 610.0,
        "edu_required": 3,
        "rep_required": 24.0,
        "description": "Финансовые отчеты, выплаты и сверка бюджета.",
    },
    {
        "code": "inspector",
        "title": "Городской инспектор",
        "salary": 660.0,
        "edu_required": 4,
        "rep_required": 28.0,
        "description": "Проверка предприятий и контроль регламентов.",
    },
    {
        "code": "analyst",
        "title": "Госаналитик",
        "salary": 700.0,
        "edu_required": 4,
        "rep_required": 30.0,
        "description": "Аналитика, отчеты и государственные проекты.",
    },
    {
        "code": "judge_assistant",
        "title": "Помощник суда",
        "salary": 820.0,
        "edu_required": 5,
        "rep_required": 38.0,
        "description": "Подготовка материалов и сопровождение дел.",
    },
]

STOCK_EXCHANGE_ASSETS: List[Dict[str, Any]] = [
    {"symbol": "MRTB", "name": "MirnaTech", "price": 180.0, "volatility": 0.045, "trend": 0.0018},
    {"symbol": "MRBN", "name": "MirnaBank", "price": 140.0, "volatility": 0.03, "trend": 0.0012},
    {"symbol": "MRGY", "name": "MirnaEnergy", "price": 220.0, "volatility": 0.04, "trend": 0.0015},
    {"symbol": "MRFD", "name": "MirnaFood", "price": 95.0, "volatility": 0.024, "trend": 0.0007},
    {"symbol": "MRBL", "name": "MirnaBuild", "price": 260.0, "volatility": 0.05, "trend": 0.0011},
    {"symbol": "MRMD", "name": "MirnaMed", "price": 130.0, "volatility": 0.028, "trend": 0.001},
    {"symbol": "MRMC", "name": "MirnaMedia", "price": 110.0, "volatility": 0.035, "trend": 0.0009},
]


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _sanitize_display_name(value: Any, max_len: int = 32) -> str:
    raw = str(value or "")
    for token in INVISIBLE_NAME_CHARS:
        raw = raw.replace(token, "")
    raw = " ".join(raw.split()).strip()
    if max_len > 0:
        raw = raw[:max_len]
    return raw


def _compose_public_name(user: Dict[str, Any] | None, fallback_id: Any = None) -> str:
    info = user or {}
    nickname = _sanitize_display_name(info.get("nickname"), 32)
    if nickname:
        return nickname
    full_name = _sanitize_display_name(info.get("full_name"), 32)
    if full_name:
        return full_name
    username = _sanitize_display_name(info.get("username"), 32).lstrip("@")
    if username:
        return f"@{username}"
    uid = info.get("user_id") or fallback_id
    return f"Игрок #{uid}" if uid else "Неизвестный игрок"


def _parse_org_requirement_thresholds(requirements_text: str | None) -> tuple[int, float]:
    """
    Вытащить минимальные требования (образование/репутация) из текстового поля требований.
    Примеры поддерживаемых фрагментов:
    - "Образование 4+"
    - "Репутация 70+"
    - "education 3+"
    - "rep 55+"
    """
    raw = str(requirements_text or "").lower()
    if not raw:
        return 1, 0.0

    min_edu = 1
    min_rep = 0.0

    edu_patterns = [
        r"(?:образован\w*|education)\s*[:\-]?\s*(\d{1,2})\s*\+?",
        r"(?:edu)\s*[:\-]?\s*(\d{1,2})\s*\+?",
    ]
    rep_patterns = [
        r"(?:репутац\w*|reputation|rep)\s*[:\-]?\s*(\d{1,3}(?:[.,]\d+)?)\s*\+?",
    ]

    for pattern in edu_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            try:
                min_edu = max(1, min(12, int(match.group(1))))
            except Exception:
                min_edu = 1
            break

    for pattern in rep_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            try:
                min_rep = float(str(match.group(1)).replace(",", "."))
                min_rep = max(0.0, min(100.0, min_rep))
            except Exception:
                min_rep = 0.0
            break

    return min_edu, min_rep


def _now_for_datetime(target: datetime) -> datetime:
    if target.tzinfo is not None:
        return datetime.now(target.tzinfo)
    return datetime.now()


def _normalize_election_stage(stage_value: Any) -> str:
    aliases = {
        "nomination": "registration",
        "register": "registration",
    }
    stage = aliases.get(str(stage_value or "registration").strip().lower(), str(stage_value or "registration").strip().lower())
    if stage not in {"registration", "campaign", "debates", "voting", "finished"}:
        return "registration"
    return stage


class AsyncDatabase:
    """Асинхронная база данных с полной защитой от блокировок"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных - создание всех таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA busy_timeout=2000")
            
            # Пользователи
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    nickname TEXT,
                    balance REAL DEFAULT 1000,
                    cash REAL DEFAULT 0,
                    bank REAL DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    experience INTEGER DEFAULT 0,
                    education INTEGER DEFAULT 1,
                    job TEXT,
                    salary REAL DEFAULT 0,
                    organization TEXT,
                    role TEXT,
                    health INTEGER DEFAULT 100,
                    hunger INTEGER DEFAULT 0,
                    happiness INTEGER DEFAULT 100,
                    reputation REAL DEFAULT 50,
                    arrested INTEGER DEFAULT 0,
                    arrested_until TEXT,
                    in_hospital INTEGER DEFAULT 0,
                    hospital_until TEXT,
                    business_owner INTEGER DEFAULT 0,
                    gang_member INTEGER DEFAULT 0,
                    property_owner INTEGER DEFAULT 0,
                    arrests_made INTEGER DEFAULT 0,
                    patients_treated INTEGER DEFAULT 0,
                    crimes_committed INTEGER DEFAULT 0,
                    fines_paid REAL DEFAULT 0,
                    last_activity TEXT,
                    created_date TEXT,
                    life_state TEXT DEFAULT 'alive',
                    injury_severity TEXT,
                    injured_until TEXT,
                    tutorial_step INTEGER DEFAULT 0,
                    tutorial_completed INTEGER DEFAULT 0,
                    first_login TEXT,
                    last_daily_bonus TEXT,
                    last_economy_update TEXT,
                    total_tax_paid REAL DEFAULT 0,
                    tax_debt REAL DEFAULT 0,
                    citizen_job TEXT,
                    citizen_salary REAL DEFAULT 0,
                    last_job_shift TEXT,
                    loan_defaults INTEGER DEFAULT 0
                )
            ''')
            
            # Организации
            await db.execute('''
                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    leader_id INTEGER,
                    deputy_id INTEGER,
                    budget REAL DEFAULT 1000000,
                    members INTEGER DEFAULT 0,
                    reputation INTEGER DEFAULT 50,
                    created_date TEXT NOT NULL,
                    last_election TEXT,
                    policy TEXT DEFAULT 'neutral',
                    description TEXT,
                    requirements TEXT,
                    income_tax REAL DEFAULT 0.1,
                    property_tax REAL DEFAULT 0.05,
                    business_tax REAL DEFAULT 0.15
                )
            ''')
            
            # Члены организаций
            await db.execute('''
                CREATE TABLE IF NOT EXISTS organization_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT,
                    salary REAL DEFAULT 0,
                    permissions TEXT,
                    join_date TEXT NOT NULL,
                    last_promotion TEXT,
                    performance INTEGER DEFAULT 100,
                    department TEXT DEFAULT 'general',
                    rank INTEGER DEFAULT 1,
                    experience INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0
                )
            ''')
            
            # Заявки в организации
            await db.execute('''
                CREATE TABLE IF NOT EXISTS organization_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    application_text TEXT,
                    status TEXT DEFAULT 'pending',
                    applied_date TEXT NOT NULL,
                    reviewed_by INTEGER,
                    reviewed_date TEXT,
                    notes TEXT
                )
            ''')
            
            # Система правления
            await db.execute('''
                CREATE TABLE IF NOT EXISTS government_system (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_type TEXT DEFAULT 'democracy',
                    current_leader_id INTEGER,
                    established_date TEXT,
                    last_changed TEXT,
                    stability INTEGER DEFAULT 100,
                    corruption INTEGER DEFAULT 0,
                    public_satisfaction INTEGER DEFAULT 60
                )
            ''')
            
            # Партии
            await db.execute('''
                CREATE TABLE IF NOT EXISTS parties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    leader_id INTEGER NOT NULL,
                    election_id INTEGER NOT NULL,
                    created_date TEXT NOT NULL,
                    members_count INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    votes_total INTEGER DEFAULT 0
                )
            ''')
            
            # Члены партии
            await db.execute('''
                CREATE TABLE IF NOT EXISTS party_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    party_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_date TEXT NOT NULL,
                    role TEXT DEFAULT 'member',
                    UNIQUE(party_id, user_id)
                )
            ''')
            
            # Приглашения в партию
            await db.execute('''
                CREATE TABLE IF NOT EXISTS party_invitations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    party_id INTEGER NOT NULL,
                    invited_user_id INTEGER NOT NULL,
                    invited_by_id INTEGER NOT NULL,
                    created_date TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    UNIQUE(party_id, invited_user_id)
                )
            ''')

            # Миграция старой схемы партий (name UNIQUE глобально -> уникальность внутри выборов)
            async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='parties'") as cursor:
                party_table = await cursor.fetchone()
                party_table_sql = (party_table[0] or "").lower() if party_table else ""

            if "name text unique" in party_table_sql:
                await db.execute("ALTER TABLE parties RENAME TO parties_old")
                await db.execute('''
                    CREATE TABLE parties (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        leader_id INTEGER NOT NULL,
                        election_id INTEGER NOT NULL,
                        created_date TEXT NOT NULL,
                        members_count INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'active',
                        votes_total INTEGER DEFAULT 0
                    )
                ''')
                await db.execute(
                    '''INSERT INTO parties
                       (id, name, leader_id, election_id, created_date, members_count, status, votes_total)
                       SELECT id, name, leader_id, election_id, created_date, members_count, status, votes_total
                       FROM parties_old'''
                )
                await db.execute("DROP TABLE parties_old")

            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_parties_election_name ON parties(election_id, name)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_party_members_user ON party_members(user_id)"
            )
            
            # Выборы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS elections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    position TEXT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    winner_id INTEGER,
                    total_voters INTEGER DEFAULT 0
                )
            ''')
            # Добавим поле stage, если его нет (миграция)
            async with db.execute("PRAGMA table_info(elections)") as cursor:
                cols = await cursor.fetchall()
                col_names = [c[1] for c in cols]
            if 'stage' not in col_names:
                await db.execute("ALTER TABLE elections ADD COLUMN stage TEXT DEFAULT 'nomination'")
            # Миграции для пользователей: временные титулы и ограничения
            async with db.execute("PRAGMA table_info(users)") as cursor:
                ucols = await cursor.fetchall()
                ucol_names = [c[1] for c in ucols]
            if 'temp_title' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN temp_title TEXT")
            if 'nickname' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN nickname TEXT")
            if 'action_banned_until' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN action_banned_until TEXT")
            if 'dictator_until' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN dictator_until TEXT")
            if 'shadow_balance' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN shadow_balance REAL DEFAULT 0")
            if 'corruption_score' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN corruption_score INTEGER DEFAULT 0")
            if 'last_side_hustle_at' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN last_side_hustle_at TEXT")
            if 'last_illegal_hustle_at' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN last_illegal_hustle_at TEXT")
            if 'last_education_test_at' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN last_education_test_at TEXT")
            if 'referrer_id' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
            if 'referral_code' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
            if 'referral_earnings' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN referral_earnings REAL DEFAULT 0")
            if 'marketing_level' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN marketing_level INTEGER DEFAULT 0")
            if 'referral_gift_eligible' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN referral_gift_eligible INTEGER DEFAULT 0")
            if 'referral_gift_claimed' not in ucol_names:
                await db.execute("ALTER TABLE users ADD COLUMN referral_gift_claimed INTEGER DEFAULT 0")
            await db.execute(
                "UPDATE users SET referral_code = 'REF' || CAST(user_id AS TEXT) WHERE COALESCE(referral_code, '') = ''"
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_referral_code ON users(referral_code)"
            )

            async with db.execute("PRAGMA table_info(government_system)") as cursor:
                gcols = await cursor.fetchall()
                gcol_names = [c[1] for c in gcols]
            if 'state_flag_text' not in gcol_names:
                await db.execute("ALTER TABLE government_system ADD COLUMN state_flag_text TEXT")
            if 'state_flag_file_id' not in gcol_names:
                await db.execute("ALTER TABLE government_system ADD COLUMN state_flag_file_id TEXT")
            
            # Кандидаты на выборах
            await db.execute('''
                CREATE TABLE IF NOT EXISTS election_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    election_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    votes INTEGER DEFAULT 0,
                    program TEXT,
                    promises TEXT
                )
            ''')
            
            # Голоса на выборах
            await db.execute('''
                CREATE TABLE IF NOT EXISTS election_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    election_id INTEGER NOT NULL,
                    voter_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    vote_date TEXT NOT NULL,
                    UNIQUE(election_id, voter_id)
                )
            ''')
            await db.execute(
                '''DELETE FROM election_candidates
                   WHERE id NOT IN (
                       SELECT MIN(id) FROM election_candidates GROUP BY election_id, candidate_id
                   )'''
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_election_candidate ON election_candidates(election_id, candidate_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_elections_status_end_date ON elections(status, end_date)"
            )
            
            # Правительственные правила
            await db.execute('''
                CREATE TABLE IF NOT EXISTS government_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_number TEXT UNIQUE,
                    rule_text TEXT,
                    created_by INTEGER,
                    created_date TEXT,
                    status TEXT DEFAULT 'active',
                    violation_penalty REAL DEFAULT 1000,
                    violations_count INTEGER DEFAULT 0
                )
            ''')
            
            # Нарушения правил
            await db.execute('''
                CREATE TABLE IF NOT EXISTS rule_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER,
                    violator_id INTEGER,
                    officer_id INTEGER,
                    violation_date TEXT,
                    description TEXT,
                    fine REAL DEFAULT 0,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # Сообщения (письма между игроками)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    subject TEXT,
                    content TEXT,
                    created_date TEXT NOT NULL,
                    read_date TEXT,
                    message_type TEXT DEFAULT 'private',
                    deleted_by_sender INTEGER DEFAULT 0,
                    deleted_by_recipient INTEGER DEFAULT 0
                )
            ''')
            
            # Перехваченные ФБР письма
            await db.execute('''
                CREATE TABLE IF NOT EXISTS intercepted_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_message_id INTEGER,
                    intercepted_by_id INTEGER,
                    intercepted_date TEXT,
                    action TEXT DEFAULT 'logged'
                )
            ''')
            
            # Революции
            await db.execute('''
                CREATE TABLE IF NOT EXISTS revolutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_date TEXT NOT NULL,
                    ended_date TEXT,
                    organizer_id INTEGER NOT NULL,
                    target_leader_id INTEGER,
                    new_government_type TEXT,
                    supporters_count INTEGER DEFAULT 0,
                    supporters_needed INTEGER DEFAULT 100,
                    status TEXT DEFAULT 'active',
                    reason TEXT,
                    result TEXT DEFAULT 'pending'
                )
            ''')
            
            # Сторонники революции
            await db.execute('''
                CREATE TABLE IF NOT EXISTS revolution_supporters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revolution_id INTEGER NOT NULL,
                    supporter_id INTEGER NOT NULL,
                    joined_date TEXT NOT NULL,
                    UNIQUE(revolution_id, supporter_id)
                )
            ''')
            
            # Кредиты
            await db.execute('''
                CREATE TABLE IF NOT EXISTS loans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    applicant_id INTEGER NOT NULL,
                    bank_officer_id INTEGER,
                    amount REAL,
                    interest_rate REAL,
                    term_months INTEGER,
                    monthly_payment REAL,
                    purpose TEXT,
                    status TEXT DEFAULT 'pending',
                    application_date TEXT NOT NULL,
                    approval_date TEXT,
                    due_date TEXT,
                    remaining_balance REAL,
                    collateral TEXT,
                    credit_score INTEGER DEFAULT 500,
                    daily_payment REAL DEFAULT 0,
                    last_payment_date TEXT
                )
            ''')
            
            # Налоговые логи
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tax_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cycle_date TEXT NOT NULL,
                    citizen_tax REAL DEFAULT 0,
                    property_tax REAL DEFAULT 0,
                    business_tax REAL DEFAULT 0,
                    org_tax REAL DEFAULT 0,
                    paid_total REAL DEFAULT 0,
                    debt_total REAL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            ''')

            # Дебаты по выборам
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS election_debates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    election_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    candidate_id INTEGER,
                    party_id INTEGER,
                    message TEXT NOT NULL,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_election_debates_election_date ON election_debates(election_id, created_date DESC)"
            )

            # Чаты организаций (включая скрытые сообщения)
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS organization_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    is_hidden INTEGER DEFAULT 0,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_org_chats_org_date ON organization_chats(org_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_org_chats_user_date ON organization_chats(user_id, created_date DESC)"
            )

            # Коррупционные операции
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS corruption_ops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    target_id INTEGER,
                    op_type TEXT NOT NULL,
                    amount REAL DEFAULT 0,
                    risk INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'logged',
                    details TEXT,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_corruption_actor_date ON corruption_ops(actor_id, created_date DESC)"
            )

            # Привилегированные переводы из бюджета
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS privileged_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    reason TEXT,
                    is_shadow INTEGER DEFAULT 0,
                    authority TEXT,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_priv_transfers_actor_date ON privileged_transfers(actor_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_priv_transfers_target_date ON privileged_transfers(target_id, created_date DESC)"
            )

            # Ежедневные налоговые счета для ручной оплаты игроками
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS daily_tax_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cycle_date TEXT NOT NULL,
                    citizen_tax REAL DEFAULT 0,
                    debt_interest REAL DEFAULT 0,
                    scheduled_payment REAL DEFAULT 0,
                    total_due REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    paid_total REAL DEFAULT 0,
                    paid_date TEXT,
                    notified_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, cycle_date)
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_tax_cycle_status ON daily_tax_invoices(cycle_date, status)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_tax_user_cycle ON daily_tax_invoices(user_id, cycle_date DESC)"
            )
            async with db.execute("PRAGMA table_info(daily_tax_invoices)") as cursor:
                dti_cols = await cursor.fetchall()
                dti_col_names = [c[1] for c in dti_cols]
            if "living_tax" not in dti_col_names:
                await db.execute("ALTER TABLE daily_tax_invoices ADD COLUMN living_tax REAL DEFAULT 0")
            if "work_tax" not in dti_col_names:
                await db.execute("ALTER TABLE daily_tax_invoices ADD COLUMN work_tax REAL DEFAULT 0")
            if "property_tax" not in dti_col_names:
                await db.execute("ALTER TABLE daily_tax_invoices ADD COLUMN property_tax REAL DEFAULT 0")
            if "business_tax" not in dti_col_names:
                await db.execute("ALTER TABLE daily_tax_invoices ADD COLUMN business_tax REAL DEFAULT 0")
            if "private_org_tax" not in dti_col_names:
                await db.execute("ALTER TABLE daily_tax_invoices ADD COLUMN private_org_tax REAL DEFAULT 0")

            # Переводы госбюджета в бюджеты организаций (президент)
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS state_org_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    target_org_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    reason TEXT,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_org_transfers_actor_date ON state_org_transfers(actor_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_org_transfers_org_date ON state_org_transfers(target_org_id, created_date DESC)"
            )

            # Очередь печати денег из госбюджета (с ожиданием по времени)
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS state_money_print_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    production_cost REAL NOT NULL,
                    status TEXT DEFAULT 'printing',
                    created_date TEXT NOT NULL,
                    ready_at TEXT NOT NULL,
                    completed_date TEXT
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_money_print_status_ready ON state_money_print_jobs(status, ready_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_money_print_actor_date ON state_money_print_jobs(actor_id, created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS government_authority_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    authority TEXT NOT NULL,
                    granted_by INTEGER,
                    granted_date TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_gov_authority_active ON government_authority_assignments(is_active, authority)"
            )
            
            # Логи репутации
            await db.execute('''
                CREATE TABLE IF NOT EXISTS reputation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    delta REAL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Задания игроков
            await db.execute('''
                CREATE TABLE IF NOT EXISTS player_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_code TEXT,
                    title TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    progress INTEGER DEFAULT 0,
                    goal INTEGER DEFAULT 1,
                    reward REAL DEFAULT 0,
                    assigned_date TEXT NOT NULL,
                    completed_date TEXT
                )
            ''')
            
            # Недвижимость
            await db.execute('''
                CREATE TABLE IF NOT EXISTS properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    price REAL NOT NULL,
                    rent REAL NOT NULL,
                    location TEXT,
                    status TEXT DEFAULT 'available',
                    category TEXT DEFAULT 'residential',
                    maintenance_daily REAL DEFAULT 120,
                    condition INTEGER DEFAULT 100
                )
            ''')
            
            # Собственность недвижимости
            await db.execute('''
                CREATE TABLE IF NOT EXISTS property_ownership (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    acquired_date TEXT NOT NULL,
                    last_rent_claimed TEXT
                )
            ''')
            
            # Бизнесы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS businesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    owner_id INTEGER NOT NULL,
                    type TEXT,
                    budget REAL DEFAULT 100000,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    location TEXT,
                    created_date TEXT NOT NULL,
                    property_id INTEGER,
                    equipment_level INTEGER DEFAULT 1,
                    income_daily REAL DEFAULT 800,
                    expense_daily REAL DEFAULT 300,
                    last_income_date TEXT
                )
            ''')
            
            # Сотрудники бизнесов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS business_employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT,
                    salary REAL DEFAULT 0,
                    join_date TEXT NOT NULL
                )
            ''')
            
            # Заявки в бизнесы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS business_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    application_text TEXT,
                    status TEXT DEFAULT 'pending',
                    applied_date TEXT NOT NULL,
                    reviewed_by INTEGER,
                    reviewed_date TEXT
                )
            ''')
            
            # Частные организации
            await db.execute('''
                CREATE TABLE IF NOT EXISTS private_orgs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    leader_id INTEGER NOT NULL,
                    budget REAL DEFAULT 50000,
                    description TEXT,
                    policy TEXT,
                    status TEXT DEFAULT 'active',
                    created_date TEXT NOT NULL,
                    property_id INTEGER,
                    equipment_level INTEGER DEFAULT 1
                )
            ''')
            
            # Члены частных организаций
            await db.execute('''
                CREATE TABLE IF NOT EXISTS private_org_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT,
                    join_date TEXT NOT NULL
                )
            ''')
            
            # Заявки в частные организации
            await db.execute('''
                CREATE TABLE IF NOT EXISTS private_org_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    application_text TEXT,
                    status TEXT DEFAULT 'pending',
                    applied_date TEXT NOT NULL,
                    reviewed_by INTEGER,
                    reviewed_date TEXT
                )
            ''')
            
            # Банды
            await db.execute('''
                CREATE TABLE IF NOT EXISTS gangs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    leader_id INTEGER NOT NULL,
                    territory TEXT,
                    reputation INTEGER DEFAULT 50,
                    status TEXT DEFAULT 'active',
                    created_date TEXT NOT NULL
                )
            ''')
            
            # Члены банд
            await db.execute('''
                CREATE TABLE IF NOT EXISTS gang_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gang_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT,
                    join_date TEXT NOT NULL
                )
            ''')
            
            # Заявки в банды
            await db.execute('''
                CREATE TABLE IF NOT EXISTS gang_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gang_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    application_text TEXT,
                    status TEXT DEFAULT 'pending',
                    applied_date TEXT NOT NULL,
                    reviewed_by INTEGER,
                    reviewed_date TEXT
                )
            ''')
            
            # Статистика системы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            await db.execute(
                '''
                DELETE FROM private_org_members
                WHERE id NOT IN (
                    SELECT MIN(id) FROM private_org_members GROUP BY org_id, user_id
                )
                '''
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_private_org_members_org_user ON private_org_members(org_id, user_id)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS private_org_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL UNIQUE,
                    raw_materials REAL DEFAULT 0,
                    daily_consumption REAL DEFAULT 0,
                    last_order_date TEXT,
                    updated_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_private_org_resources_org ON private_org_resources(org_id)"
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS business_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER NOT NULL UNIQUE,
                    raw_materials REAL DEFAULT 0,
                    daily_consumption REAL DEFAULT 0,
                    last_order_date TEXT,
                    updated_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_business_resources_business ON business_resources(business_id)"
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS user_action_cooldowns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action_key TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    UNIQUE(user_id, action_key)
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_action_cooldowns_user_action ON user_action_cooldowns(user_id, action_key)"
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS referral_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL UNIQUE,
                    reward_amount REAL DEFAULT 0,
                    welcome_bonus REAL DEFAULT 0,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_referral_events_referrer_date ON referral_events(referrer_id, created_date DESC)"
            )
            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS developer_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    project_name TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    invested REAL NOT NULL,
                    expected_payout REAL NOT NULL,
                    status TEXT DEFAULT 'building',
                    started_date TEXT NOT NULL,
                    ready_date TEXT NOT NULL,
                    claimed_date TEXT
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_developer_projects_owner_status ON developer_projects(owner_id, status, ready_date)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS bot_chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    chat_type TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    joined_date TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    left_date TEXT
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bot_chats_active_type ON bot_chats(is_active, chat_type)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS player_activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    details TEXT,
                    value REAL DEFAULT 0,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_user_date ON player_activity_log(user_id, created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS media_news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source_user_id INTEGER,
                    severity TEXT DEFAULT 'normal',
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_news_date ON media_news(created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS casinos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    owner_id INTEGER,
                    casino_type TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    min_bet REAL DEFAULT 100,
                    max_bet REAL DEFAULT 500000,
                    house_edge REAL DEFAULT 0.03,
                    balance REAL DEFAULT 2000000,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_casinos_type_status ON casinos(casino_type, status)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS casino_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    casino_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    prediction TEXT,
                    bet_amount REAL NOT NULL,
                    roll_value INTEGER,
                    payout REAL DEFAULT 0,
                    result TEXT NOT NULL,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_casino_games_user_date ON casino_games(user_id, created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS citizen_appeals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    citizen_id INTEGER NOT NULL,
                    vice_id INTEGER,
                    president_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    vice_note TEXT,
                    president_note TEXT,
                    created_date TEXT NOT NULL,
                    vice_review_date TEXT,
                    president_review_date TEXT
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_appeals_status ON citizen_appeals(status, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_appeals_vice ON citizen_appeals(vice_id, status, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_appeals_president ON citizen_appeals(president_id, status, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_appeals_citizen ON citizen_appeals(citizen_id, created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS group_casino_duels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    challenger_id INTEGER NOT NULL,
                    opponent_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    target_value INTEGER NOT NULL,
                    bet_amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    challenge_message_id INTEGER,
                    roll_value INTEGER,
                    winner_id INTEGER,
                    loser_id INTEGER,
                    created_date TEXT NOT NULL,
                    resolved_date TEXT,
                    expires_at TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_group_casino_duels_pending ON group_casino_duels(status, chat_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_group_casino_duels_players ON group_casino_duels(challenger_id, opponent_id, status)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS business_tax_holidays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER NOT NULL,
                    granted_by INTEGER NOT NULL,
                    reason TEXT,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_tax_holiday_business_date ON business_tax_holidays(business_id, end_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS business_tax_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    cycle_date TEXT NOT NULL,
                    tax_due REAL DEFAULT 0,
                    tax_paid REAL DEFAULT 0,
                    status TEXT NOT NULL,
                    note TEXT,
                    holiday_by INTEGER,
                    created_at TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_business_tax_reports_cycle ON business_tax_reports(cycle_date DESC, status)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS side_hustle_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    hustle_type TEXT NOT NULL,
                    variant TEXT,
                    result TEXT NOT NULL,
                    payout REAL DEFAULT 0,
                    risk INTEGER DEFAULT 0,
                    created_date TEXT NOT NULL
                )
                '''
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_side_hustle_user_date ON side_hustle_runs(user_id, created_date DESC)"
            )

            await db.execute(
                '''
                CREATE TABLE IF NOT EXISTS drug_cartels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gang_id INTEGER UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    stock REAL DEFAULT 0,
                    purity REAL DEFAULT 50,
                    laundering_level INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    created_date TEXT NOT NULL
                )
                '''
            )
            
            # Образовательные программы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS education_programs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    duration_days INTEGER DEFAULT 14,
                    tuition_fee REAL DEFAULT 0,
                    min_education INTEGER DEFAULT 1,
                    min_reputation REAL DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    created_date TEXT NOT NULL,
                    creator_id INTEGER,
                    teacher_id INTEGER
                )
            ''')
            
            # Обучение студентов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS education_enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    program_id INTEGER NOT NULL,
                    teacher_id INTEGER,
                    status TEXT DEFAULT 'active',
                    start_date TEXT NOT NULL,
                    last_study_date TEXT,
                    progress_days INTEGER DEFAULT 0,
                    completed_date TEXT,
                    study_choice TEXT DEFAULT 'theory'
                )
            ''')
            
            # Гражданские работы
            await db.execute('''
                CREATE TABLE IF NOT EXISTS job_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    job_code TEXT,
                    job_title TEXT,
                    expected_salary REAL,
                    application_text TEXT,
                    status TEXT DEFAULT 'pending',
                    applied_date TEXT NOT NULL,
                    reviewed_by INTEGER,
                    reviewed_date TEXT,
                    review_note TEXT
                )
            ''')
            
            await db.commit()
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    async def create_or_update_user(self, user_id: int, username: str, full_name: str) -> Dict[str, Any]:
        """Создать или обновить пользователя"""
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существование пользователя
            async with db.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,)) as cursor:
                existing = await cursor.fetchone()
            
            if existing:
                # Обновляем
                await db.execute(
                    'UPDATE users SET username = ?, full_name = ?, last_activity = ? WHERE user_id = ?',
                    (username, full_name, now, user_id)
                )
                await db.execute(
                    "UPDATE users SET referral_code = COALESCE(NULLIF(referral_code, ''), ?) WHERE user_id = ?",
                    (f"REF{int(user_id)}", int(user_id)),
                )
            else:
                # Создаем
                await db.execute(
                    '''INSERT INTO users
                       (user_id, username, full_name, balance, cash, bank, referral_code, created_date, last_activity)
                       VALUES (?, ?, ?, 1000, 0, 0, ?, ?, ?)''',
                    (user_id, username, full_name, f"REF{int(user_id)}", now, now)
                )
                # Инициализируем правительственную систему если нужно
                async with db.execute('SELECT COUNT(*) FROM government_system') as cursor:
                    count = await cursor.fetchone()
                    if count[0] == 0:
                        await db.execute(
                            '''INSERT INTO government_system 
                               (current_type, established_date, last_changed, stability, corruption, public_satisfaction)
                               VALUES (?, ?, ?, 100, 0, 60)''',
                            ('democracy', now, now)
                        )
            
            await db.commit()
        
        return await self.get_user(user_id) or {}
    
    async def update_user(self, user_id: int, **kwargs) -> bool:
        """Обновить данные пользователя"""
        if not kwargs:
            return True
        
        # Построить SQL динамически
        set_clause = ', '.join([f'{key} = ?' for key in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f'UPDATE users SET {set_clause} WHERE user_id = ?', values)
            await db.commit()
        
        return True

    def get_user_public_name(self, user: Dict[str, Any] | None, fallback_id: Optional[int] = None) -> str:
        """Получить безопасное отображаемое имя пользователя."""
        return _compose_public_name(user, fallback_id=fallback_id)

    async def get_user_public_name_by_id(self, user_id: int) -> str:
        """Получить отображаемое имя пользователя по ID."""
        user = await self.get_user(int(user_id))
        return _compose_public_name(user, fallback_id=user_id)

    async def set_user_nickname(self, user_id: int, nickname: str) -> tuple[bool, str, Optional[str]]:
        """Установить или сбросить пользовательский ник."""
        raw = str(nickname or "")
        lowered = raw.strip().lower()
        reset_tokens = {"-", "reset", "off", "none", "сброс", "удалить", "clear"}
        clean = "" if lowered in reset_tokens else _sanitize_display_name(raw, 28)

        if clean.startswith("@"):
            clean = clean.lstrip("@").strip()

        if clean and len(clean) < 3:
            return False, "Ник слишком короткий (минимум 3 символа).", None
        if len(clean) > 28:
            return False, "Ник слишком длинный (максимум 28 символов).", None
        if clean and clean.isdigit():
            return False, "Ник не может состоять только из цифр.", None
        if clean and any(ch in "\\`*_[]()~>#+-=|{}!" for ch in clean):
            return False, "Ник содержит запрещенные спецсимволы.", None

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users WHERE user_id = ? LIMIT 1", (int(user_id),)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False, "Профиль не найден.", None
            await db.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (clean or None, int(user_id)))
            await db.commit()

        if clean:
            await self.log_player_activity(
                user_id=user_id,
                activity_type="nickname_update",
                details=f"Установлен ник: {clean}",
                value=0,
            )
            return True, "Ник успешно обновлен.", clean
        await self.log_player_activity(
            user_id=user_id,
            activity_type="nickname_reset",
            details="Пользователь сбросил персональный ник.",
            value=0,
        )
        return True, "Ник сброшен. Используется системное имя.", None
    
    async def get_organization(self, org_name: str) -> Optional[Dict[str, Any]]:
        """Получить организацию по имени"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM organizations WHERE name = ?', (org_name,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    async def get_organization_by_id(self, org_id: int) -> Optional[Dict[str, Any]]:
        """Получить организацию по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM organizations WHERE id = ?', (org_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_government_organization(self) -> Optional[Dict[str, Any]]:
        """Получить организацию правительства (по type=government, с fallback по имени)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM organizations
                WHERE lower(COALESCE(type, '')) = 'government'
                ORDER BY id ASC
                LIMIT 1
                """
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

            async with db.execute(
                "SELECT * FROM organizations WHERE name = ? ORDER BY id ASC LIMIT 1",
                ("Правительство",),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    async def list_organizations(self) -> List[Dict[str, Any]]:
        """Получить список всех организаций"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT id, name, type FROM organizations ORDER BY name ASC') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_organization_members(self, org_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить участников организации с базовой информацией профиля."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT om.user_id,
                          om.role,
                          om.salary,
                          om.join_date,
                          om.rank,
                          om.department,
                          om.performance,
                          u.nickname,
                          u.full_name,
                          u.username,
                          COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(om.user_id AS TEXT)) AS display_name
                   FROM organization_members om
                   LEFT JOIN users u ON u.user_id = om.user_id
                   WHERE om.org_id = ?
                   ORDER BY om.rank DESC, om.join_date ASC
                   LIMIT ?''',
                (org_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def is_user_org_member(self, user_id: int, org_id: int) -> bool:
        """Проверить членство игрока в организации с fallback по лидеру/названию."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT 1 FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                (int(org_id), int(user_id)),
            ) as cursor:
                if await cursor.fetchone():
                    return True

            async with db.execute(
                "SELECT leader_id, deputy_id, name FROM organizations WHERE id = ? LIMIT 1",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                return False

            if int(org["leader_id"] or 0) == int(user_id) or int(org["deputy_id"] or 0) == int(user_id):
                return True

            async with db.execute(
                "SELECT organization FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                return False
            return str(user["organization"] or "").strip().lower() == str(org["name"] or "").strip().lower()

    async def is_user_in_org_type(self, user_id: int, org_type: str) -> bool:
        """Проверить принадлежность игрока к организации определенного типа."""
        safe_user_id = int(user_id)
        safe_type = str(org_type or "").strip().lower()
        if safe_user_id <= 0 or not safe_type:
            return False

        token_map: dict[str, tuple[str, ...]] = {
            "government": ("правитель", "government", "президент", "president"),
            "police": ("полиц", "police"),
            "hospital": ("больниц", "госпитал", "hospital", "medical", "medic"),
            "court": ("суд", "court", "judge"),
            "bank": ("банк", "bank"),
            "education": ("универс", "образов", "education", "teacher"),
            "fbi": ("фбр", "fbi"),
            "tax": ("налог", "tax"),
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, name, leader_id, deputy_id
                FROM organizations
                WHERE lower(COALESCE(type, '')) = ?
                """,
                (safe_type,),
            ) as cursor:
                org_rows = await cursor.fetchall()

            for org in org_rows:
                org_id = int(org["id"] or 0)
                if org_id <= 0:
                    continue

                async with db.execute(
                    "SELECT 1 FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                    (org_id, safe_user_id),
                ) as cursor:
                    if await cursor.fetchone():
                        return True

                if safe_user_id in {int(org["leader_id"] or 0), int(org["deputy_id"] or 0)}:
                    return True

            async with db.execute(
                "SELECT organization, role FROM users WHERE user_id = ? LIMIT 1",
                (safe_user_id,),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                return False

            org_lc = str(user["organization"] or "").strip().lower()
            role_lc = str(user["role"] or "").strip().lower()
            for token in token_map.get(safe_type, (safe_type,)):
                if token and (token in org_lc or token in role_lc):
                    return True
        return False

    async def can_manage_organization(self, user_id: int, org_id: int) -> bool:
        """
        Проверить доступ к управлению организацией.
        Основной критерий: leader_id/deputy_id.
        Fallback: руководящая роль в organization_members или users при совпадении организации.
        """
        safe_user_id = int(user_id)
        safe_org_id = int(org_id)
        if safe_user_id <= 0 or safe_org_id <= 0:
            return False

        authority = await self.get_government_authority(safe_user_id)
        if authority in {"president", "vice_president"}:
            return True

        manager_tokens = (
            "лидер",
            "зам",
            "заместитель",
            "глава",
            "директор",
            "шеф",
            "руковод",
            "leader",
            "deputy",
            "director",
            "head",
            "chief",
            "manager",
        )
        leader_tokens = ("лидер", "глава", "leader", "chief", "head")
        deputy_tokens = ("зам", "заместитель", "deputy", "vice")

        def _is_manager_role(raw_role: Any) -> bool:
            role_lc = str(raw_role or "").strip().lower()
            return any(token in role_lc for token in manager_tokens)

        def _is_leader_like(raw_role: Any) -> bool:
            role_lc = str(raw_role or "").strip().lower()
            return any(token in role_lc for token in leader_tokens)

        def _is_deputy_like(raw_role: Any) -> bool:
            role_lc = str(raw_role or "").strip().lower()
            return any(token in role_lc for token in deputy_tokens)

        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, name, leader_id, deputy_id FROM organizations WHERE id = ? LIMIT 1",
                (safe_org_id,),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                return False

            current_leader_id = int(org["leader_id"] or 0)
            current_deputy_id = int(org["deputy_id"] or 0)
            if safe_user_id in {current_leader_id, current_deputy_id}:
                return True

            async with db.execute(
                "SELECT id, role FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                (safe_org_id, safe_user_id),
            ) as cursor:
                member = await cursor.fetchone()

            if member and _is_manager_role(member["role"]):
                updates: list[tuple[str, tuple[Any, ...]]] = []
                if current_leader_id <= 0 and _is_leader_like(member["role"]):
                    updates.append(("UPDATE organizations SET leader_id = ? WHERE id = ?", (safe_user_id, safe_org_id)))
                if current_deputy_id <= 0 and _is_deputy_like(member["role"]):
                    updates.append(("UPDATE organizations SET deputy_id = ? WHERE id = ?", (safe_user_id, safe_org_id)))
                if updates:
                    for sql, params in updates:
                        await db.execute(sql, params)
                    await db.commit()
                return True

            async with db.execute(
                "SELECT organization, role FROM users WHERE user_id = ? LIMIT 1",
                (safe_user_id,),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                return False

            user_org_lc = str(user["organization"] or "").strip().lower()
            org_name_lc = str(org["name"] or "").strip().lower()
            if user_org_lc != org_name_lc or not _is_manager_role(user["role"]):
                return False

            role_for_member = str(user["role"] or "").strip() or "Руководитель"
            if not member:
                await db.execute(
                    """
                    INSERT INTO organization_members
                    (org_id, user_id, role, salary, join_date, last_promotion)
                    VALUES (?, ?, ?, 0, ?, ?)
                    """,
                    (safe_org_id, safe_user_id, role_for_member, now, now),
                )

            updates: list[tuple[str, tuple[Any, ...]]] = []
            if current_leader_id <= 0 and _is_leader_like(user["role"]):
                updates.append(("UPDATE organizations SET leader_id = ? WHERE id = ?", (safe_user_id, safe_org_id)))
            if current_deputy_id <= 0 and _is_deputy_like(user["role"]):
                updates.append(("UPDATE organizations SET deputy_id = ? WHERE id = ?", (safe_user_id, safe_org_id)))
            for sql, params in updates:
                await db.execute(sql, params)
            await db.commit()
            return True
    
    async def init_default_organizations(self):
        """Инициализировать стандартные организации"""
        now = datetime.now().isoformat()
        
        organizations = [
            ('Правительство', 'government', 'Управление государством', 10000000, 100),
            ('Полиция', 'police', 'Правопорядок и безопасность', 2000000, 80),
            ('Больница', 'hospital', 'Медицинские услуги', 1500000, 90),
            ('Суд', 'court', 'Судебная система', 1000000, 95),
            ('Банк', 'bank', 'Финансы и кредиты', 10000000, 85),
            ('Университет', 'education', 'Образование и наука', 800000, 75),
            ('ФБР', 'fbi', 'Расследования и безопасность', 3000000, 70),
            ('Налоговая служба', 'tax', 'Сбор налогов и контроль долгов', 1800000, 88),
        ]
        
        async with aiosqlite.connect(self.db_path) as db:
            for org_name, org_type, description, budget, reputation in organizations:
                # Проверяем существование
                async with db.execute('SELECT id FROM organizations WHERE name = ?', (org_name,)) as cursor:
                    if not await cursor.fetchone():
                        await db.execute(
                            '''INSERT INTO organizations 
                               (name, type, budget, reputation, created_date, policy, description, requirements,
                                income_tax, property_tax, business_tax)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.12, 0.04, 0.15)''',
                            (org_name, org_type, budget, reputation, now, 'neutral', description, 'No requirements')
                        )
            
            await db.commit()

    async def normalize_organization_budgets(self, minimum_budget: float = 0.0) -> Dict[str, Any]:
        """
        Нормализовать бюджеты организаций:
        - NULL -> minimum_budget
        - значения ниже minimum_budget -> minimum_budget
        """
        safe_min = round(float(minimum_budget or 0.0), 2)
        if safe_min < 0:
            safe_min = 0.0

        changed: list[tuple[int, str, float]] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT id, name, budget
                FROM organizations
                WHERE budget IS NULL OR budget < ?
                ORDER BY id ASC
                """,
                (safe_min,),
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                org_id = int(row["id"] or 0)
                if org_id <= 0:
                    continue
                org_name = str(row["name"] or f"Org#{org_id}")
                old_budget = round(float(row["budget"] or 0.0), 2)
                changed.append((org_id, org_name, old_budget))

            if changed:
                await db.execute(
                    """
                    UPDATE organizations
                    SET budget = ?
                    WHERE budget IS NULL OR budget < ?
                    """,
                    (safe_min, safe_min),
                )
            await db.commit()

        return {
            "updated_count": len(changed),
            "minimum_budget": safe_min,
            "changed": [
                {"org_id": org_id, "org_name": org_name, "old_budget": old_budget}
                for org_id, org_name, old_budget in changed
            ],
        }

    async def ensure_government_budget_floor(self, minimum_budget: float = 10_000_000.0) -> Dict[str, Any]:
        """
        Гарантирует минимальный бюджет правительства.
        Если текущий бюджет ниже порога, поднимаем до порога.
        """
        safe_min = round(float(minimum_budget or 0.0), 2)
        if safe_min < 0:
            safe_min = 0.0

        gov_org = await self.get_government_organization()
        if not gov_org:
            return {"updated": False, "reason": "no_government_org", "minimum_budget": safe_min}

        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return {"updated": False, "reason": "invalid_government_org", "minimum_budget": safe_min}

        current_budget = round(float(gov_org.get("budget") or 0.0), 2)
        if current_budget >= safe_min:
            return {
                "updated": False,
                "reason": "already_enough",
                "minimum_budget": safe_min,
                "old_budget": current_budget,
                "new_budget": current_budget,
                "org_id": gov_org_id,
            }

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE organizations SET budget = ? WHERE id = ?", (safe_min, gov_org_id))
            await db.commit()

        return {
            "updated": True,
            "minimum_budget": safe_min,
            "old_budget": current_budget,
            "new_budget": safe_min,
            "org_id": gov_org_id,
        }
    
    async def upsert_bot_chat(self, chat_id: int, chat_type: str, title: str = "") -> bool:
        """Создать или обновить запись чата, где бот находится."""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''
                INSERT INTO bot_chats (chat_id, title, chat_type, is_active, joined_date, last_seen, left_date)
                VALUES (?, ?, ?, 1, ?, ?, NULL)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    chat_type = excluded.chat_type,
                    is_active = 1,
                    last_seen = excluded.last_seen,
                    left_date = NULL
                ''',
                (chat_id, title or "", chat_type, now, now),
            )
            await db.commit()
        return True

    async def deactivate_bot_chat(self, chat_id: int) -> bool:
        """Пометить чат как неактивный (бот покинул чат или был удален)."""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''
                UPDATE bot_chats
                SET is_active = 0,
                    left_date = ?,
                    last_seen = ?
                WHERE chat_id = ?
                ''',
                (now, now, chat_id),
            )
            await db.commit()
        return True

    async def get_active_group_chats(self) -> List[Dict[str, Any]]:
        """Получить список активных групп и супергрупп, где состоит бот."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''
                SELECT chat_id, title, chat_type
                FROM bot_chats
                WHERE is_active = 1
                  AND chat_type IN ('group', 'supergroup')
                ORDER BY chat_id ASC
                '''
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_system_state(self, key: str) -> Optional[str]:
        safe_key = (key or "").strip()[:120]
        if not safe_key:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM system_state WHERE key = ? LIMIT 1",
                (safe_key,),
            ) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row and row[0] is not None else None

    async def set_system_state(self, key: str, value: Any) -> bool:
        safe_key = (key or "").strip()[:120]
        if not safe_key:
            return False
        safe_value = "" if value is None else str(value)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (safe_key, safe_value),
            )
            await db.commit()
        return True

    async def apply_currency_rebalance_once(self, force: bool = False) -> Dict[str, Any]:
        """
        Одноразовый ребаланс валюты:
        - масштабирует основные денежные поля x0.1;
        - устанавливает всем игрокам стартовый баланс $1000 (cash/bank обнуляются).
        """
        done_key = "currency_rebalance_v1_done"
        if not force:
            done_flag = await self.get_system_state(done_key)
            if done_flag == "1":
                return {"applied": False, "reason": "already_applied"}

        factor = 0.1
        now = datetime.now().isoformat()
        scale_targets: Dict[str, List[str]] = {
            "users": [
                "cash",
                "bank",
                "salary",
                "fines_paid",
                "total_tax_paid",
                "tax_debt",
                "citizen_salary",
                "shadow_balance",
                "referral_earnings",
            ],
            "organizations": ["budget"],
            "organization_members": ["salary"],
            "businesses": ["budget", "income_daily", "expense_daily"],
            "business_employees": ["salary"],
            "business_tax_reports": ["tax_due", "tax_paid"],
            "private_orgs": ["budget"],
            "bank_transactions": ["amount", "balance_before", "balance_after", "bank_before", "bank_after"],
            "loans": ["amount", "monthly_payment", "remaining_balance", "daily_payment"],
            "market_contracts": ["reward", "escrow_amount"],
            "properties": ["price", "rent", "maintenance_daily"],
            "education_programs": ["tuition_fee"],
            "casinos": ["min_bet", "max_bet", "balance"],
            "casino_games": ["bet_amount", "payout"],
            "group_casino_duels": ["bet_amount"],
            "player_tasks": ["reward"],
            "police_arrests": ["fine_amount"],
            "privileged_transfers": ["amount"],
            "corruption_ops": ["amount"],
            "rule_violations": ["fine"],
            "government_rules": ["violation_penalty"],
            "tax_logs": ["citizen_tax", "property_tax", "business_tax", "org_tax", "paid_total", "debt_total"],
            "job_applications": ["expected_salary"],
            "side_hustle_runs": ["payout"],
            "referral_events": ["reward_amount", "welcome_bonus"],
            "developer_projects": ["invested", "expected_payout"],
            "player_activity_log": ["value"],
        }

        scaled_tables = 0
        scaled_columns = 0
        users_reset = 0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            for table_name, columns in scale_targets.items():
                async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
                    table_cols = await cursor.fetchall()
                if not table_cols:
                    continue

                existing = {str(col[1]) for col in table_cols}
                applied = 0
                for column in columns:
                    if column not in existing:
                        continue
                    await db.execute(
                        f"UPDATE {table_name} SET {column} = ROUND(COALESCE({column}, 0) * ?, 2)",
                        (factor,),
                    )
                    applied += 1

                if applied > 0:
                    scaled_tables += 1
                    scaled_columns += applied

            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                users_reset = int((row[0] if row else 0) or 0)

            await db.execute(
                """
                UPDATE users
                SET balance = 1000,
                    cash = 0,
                    bank = 0,
                    referral_code = COALESCE(NULLIF(referral_code, ''), 'REF' || CAST(user_id AS TEXT))
                """
            )

            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (done_key, "1"),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("currency_rebalance_applied_at", now),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("currency_scale_factor", str(factor)),
            )
            await db.commit()

        return {
            "applied": True,
            "factor": factor,
            "scaled_tables": scaled_tables,
            "scaled_columns": scaled_columns,
            "users_reset": users_reset,
            "applied_at": now,
        }

    def _normalize_referral_code(self, raw_code: str) -> str:
        raw = str(raw_code or "").strip()
        if not raw:
            return ""
        lowered = raw.lower()
        if lowered.startswith("ref_"):
            raw = raw[4:]
        elif lowered.startswith("invite_"):
            raw = raw[7:]
        clean = re.sub(r"[^a-zA-Z0-9]", "", raw).upper()
        if not clean:
            return ""
        if clean.isdigit():
            clean = f"REF{clean}"
        elif not clean.startswith("REF"):
            clean = f"REF{clean}"
        return clean[:40]

    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        safe_user_id = int(user_id)
        query = """
            SELECT
                u.user_id,
                COALESCE(NULLIF(u.referral_code, ''), 'REF' || CAST(u.user_id AS TEXT)) AS referral_code,
                COALESCE(u.referrer_id, 0) AS referrer_id,
                COALESCE(u.referral_earnings, 0) AS referral_earnings,
                COALESCE(u.marketing_level, 0) AS marketing_level,
                COALESCE(u.referral_gift_eligible, 0) AS referral_gift_eligible,
                COALESCE(u.referral_gift_claimed, 0) AS referral_gift_claimed,
                COALESCE((
                    SELECT COUNT(*)
                    FROM referral_events re
                    WHERE re.referrer_id = u.user_id
                ), 0) AS referrals_count
            FROM users u
            WHERE u.user_id = ?
            LIMIT 1
        """
        recent_query = """
            SELECT
                re.referred_id,
                re.reward_amount,
                re.welcome_bonus,
                re.created_date,
                COALESCE(NULLIF(ru.nickname, ''), NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(re.referred_id AS TEXT)) AS referred_name
            FROM referral_events re
            LEFT JOIN users ru ON ru.user_id = re.referred_id
            WHERE re.referrer_id = ?
            ORDER BY re.created_date DESC
            LIMIT 12
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_user_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return {
                    "user_id": safe_user_id,
                    "referral_code": f"REF{safe_user_id}",
                    "referrals_count": 0,
                    "referral_earnings": 0.0,
                    "marketing_level": 0,
                    "referral_gift_eligible": 0,
                    "referral_gift_claimed": 0,
                    "gift_goal": 50,
                    "gift_remaining": 50,
                    "recent_referrals": [],
                }
            async with db.execute(recent_query, (safe_user_id,)) as cursor:
                recent_rows = await cursor.fetchall()
        data = dict(row)
        count = int(data.get("referrals_count") or 0)
        data["gift_goal"] = 50
        data["gift_remaining"] = max(0, 50 - count)
        data["recent_referrals"] = [dict(r) for r in recent_rows]
        return data

    async def apply_referral_code(
        self,
        referred_user_id: int,
        raw_code: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        referral_code = self._normalize_referral_code(raw_code)
        if not referral_code:
            return False, "Реферальный код пустой или некорректный.", None

        referred_id = int(referred_user_id)
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute("SELECT * FROM users WHERE user_id = ? LIMIT 1", (referred_id,)) as cursor:
                referred = await cursor.fetchone()
            if not referred:
                await db.rollback()
                return False, "Профиль игрока не найден.", None
            if int(referred["referrer_id"] or 0) > 0:
                await db.rollback()
                return False, "Реферальный код уже был активирован ранее.", None

            async with db.execute(
                """
                SELECT *
                FROM users
                WHERE upper(COALESCE(referral_code, '')) = ?
                LIMIT 1
                """,
                (referral_code,),
            ) as cursor:
                referrer = await cursor.fetchone()
            if not referrer:
                await db.rollback()
                return False, "Реферальный код не найден.", None

            referrer_id = int(referrer["user_id"] or 0)
            if referrer_id == referred_id:
                await db.rollback()
                return False, "Нельзя активировать собственный реферальный код.", None

            async with db.execute(
                "SELECT id FROM referral_events WHERE referred_id = ? LIMIT 1",
                (referred_id,),
            ) as cursor:
                existing_event = await cursor.fetchone()
            if existing_event:
                await db.rollback()
                return False, "Реферальная привязка уже существует.", None

            marketing_level = int(referrer["marketing_level"] or 0)
            ref_reward = round(120 + min(450, marketing_level * 8), 2)
            welcome_bonus = round(60 + min(180, marketing_level * 2), 2)

            new_referrer_balance = round(float(referrer["balance"] or 0) + ref_reward, 2)
            new_referred_balance = round(float(referred["balance"] or 0) + welcome_bonus, 2)
            new_ref_earnings = round(float(referrer["referral_earnings"] or 0) + ref_reward, 2)

            await db.execute(
                """
                UPDATE users
                SET balance = ?,
                    referral_earnings = ?,
                    referral_code = COALESCE(NULLIF(referral_code, ''), ?)
                WHERE user_id = ?
                """,
                (new_referrer_balance, new_ref_earnings, f"REF{referrer_id}", referrer_id),
            )
            await db.execute(
                """
                UPDATE users
                SET balance = ?,
                    referrer_id = ?,
                    referral_code = COALESCE(NULLIF(referral_code, ''), ?)
                WHERE user_id = ?
                """,
                (new_referred_balance, referrer_id, f"REF{referred_id}", referred_id),
            )
            await db.execute(
                """
                INSERT INTO referral_events
                (referrer_id, referred_id, reward_amount, welcome_bonus, created_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (referrer_id, referred_id, ref_reward, welcome_bonus, now),
            )

            async with db.execute(
                "SELECT COUNT(*) AS c FROM referral_events WHERE referrer_id = ?",
                (referrer_id,),
            ) as cursor:
                count_row = await cursor.fetchone()
            referrals_count = int((count_row["c"] if count_row else 0) or 0)
            gift_eligible = 1 if referrals_count >= 50 else 0
            await db.execute(
                "UPDATE users SET referral_gift_eligible = CASE WHEN ? = 1 THEN 1 ELSE referral_gift_eligible END WHERE user_id = ?",
                (gift_eligible, referrer_id),
            )

            await db.commit()

        try:
            await self.log_player_activity(
                user_id=referrer_id,
                activity_type="referral_reward",
                details=f"Новый реферал #{referred_id}",
                value=ref_reward,
            )
            await self.log_player_activity(
                user_id=referred_id,
                activity_type="referral_join",
                details=f"Привязан к рефералу #{referrer_id}",
                value=welcome_bonus,
            )
            if referrals_count in {1, 5, 10, 25, 50}:
                await self.create_media_news(
                    title="Реферальная программа набирает обороты",
                    body=(
                        f"Игрок #{referrer_id} достиг отметки {referrals_count} приглашенных граждан "
                        "и усиливает свое влияние через маркетинг."
                    ),
                    source_user_id=referrer_id,
                    severity="hot" if referrals_count >= 25 else "normal",
                )
        except Exception:
            pass

        result = {
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "referral_code": referral_code,
            "ref_reward": ref_reward,
            "welcome_bonus": welcome_bonus,
            "referrals_count": referrals_count,
            "gift_eligible": gift_eligible,
        }
        text = (
            f"Реферальный код активирован. Бонус +${welcome_bonus:,.2f}. "
            f"Пригласивший игрок получил +${ref_reward:,.2f}."
        )
        return True, text, result

    async def run_marketing_campaign(
        self,
        user_id: int,
        budget: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        uid = int(user_id)
        safe_budget = round(float(budget or 0), 2)
        if safe_budget < 50:
            return False, "Минимальный бюджет маркетинга: $50.", None
        if safe_budget > 50_000:
            return False, "Слишком большой бюджет маркетинга за один запуск.", None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute("SELECT * FROM users WHERE user_id = ? LIMIT 1", (uid,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            balance = float(user["balance"] or 0)
            if balance < safe_budget:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${safe_budget:,.2f}.", None

            marketing_level = int(user["marketing_level"] or 0)
            level_gain = max(1, int(safe_budget // 350))
            new_level = min(250, marketing_level + level_gain)

            performance = random.uniform(0.7, 1.4) * (1 + marketing_level * 0.015)
            cashback = round(min(safe_budget * 0.92, safe_budget * 0.22 * performance), 2)
            coverage_points = int(max(1, round((safe_budget / 35.0) * performance)))
            net_spent = round(max(0.0, safe_budget - cashback), 2)
            new_balance = round(balance - safe_budget + cashback, 2)

            await db.execute(
                "UPDATE users SET balance = ?, marketing_level = ? WHERE user_id = ?",
                (new_balance, new_level, uid),
            )
            await db.commit()

        try:
            await self.log_player_activity(
                user_id=uid,
                activity_type="marketing_campaign",
                details=f"Маркетинг-кампания бюджетом ${safe_budget:,.2f}",
                value=max(0.0, safe_budget),
            )
        except Exception:
            pass

        result = {
            "user_id": uid,
            "budget": safe_budget,
            "cashback": cashback,
            "net_spent": net_spent,
            "coverage_points": coverage_points,
            "marketing_level_before": marketing_level,
            "marketing_level_after": new_level,
            "new_balance": new_balance,
        }
        text = (
            "Кампания запущена: "
            f"охват {coverage_points:,}, возврат ${cashback:,.2f}, "
            f"уровень маркетинга {marketing_level} -> {new_level}."
        )
        return True, text, result

    async def claim_referral_gift(self, user_id: int) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        uid = int(user_id)
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT
                    u.user_id,
                    COALESCE(u.referral_gift_claimed, 0) AS gift_claimed,
                    COALESCE(u.referral_gift_eligible, 0) AS gift_eligible,
                    COALESCE(u.balance, 0) AS balance
                FROM users u
                WHERE u.user_id = ?
                LIMIT 1
                """,
                (uid,),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            async with db.execute(
                "SELECT COUNT(*) AS c FROM referral_events WHERE referrer_id = ?",
                (uid,),
            ) as cursor:
                count_row = await cursor.fetchone()
            referrals_count = int((count_row["c"] if count_row else 0) or 0)

            if referrals_count < 50:
                await db.rollback()
                return False, f"Нужно 50 приглашений. Сейчас: {referrals_count}.", None
            if int(user["gift_claimed"] or 0) == 1:
                await db.rollback()
                return False, "Подарок уже был выдан ранее.", None

            cash_gift = 5000.0
            gift_code = f"TGIFT-{uid}-{datetime.now().strftime('%Y%m%d')}"
            new_balance = round(float(user["balance"] or 0) + cash_gift, 2)

            await db.execute(
                """
                UPDATE users
                SET referral_gift_eligible = 1,
                    referral_gift_claimed = 1,
                    balance = ?
                WHERE user_id = ?
                """,
                (new_balance, uid),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (f"ref_gift_code_{uid}", gift_code),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (f"ref_gift_claimed_at_{uid}", now),
            )
            await db.commit()

        try:
            await self.log_player_activity(
                user_id=uid,
                activity_type="referral_gift_claim",
                details="Получен подарок за 50 рефералов",
                value=5000.0,
            )
            await self.create_media_news(
                title="Игрок получил награду за 50 рефералов",
                body=f"Игрок #{uid} достиг планки в 50 приглашений и активировал крупный бонус.",
                source_user_id=uid,
                severity="high",
            )
        except Exception:
            pass

        result = {
            "gift_code": gift_code,
            "cash_gift": 5000.0,
            "new_balance": new_balance,
            "referrals_count": referrals_count,
        }
        text = (
            "Подарок активирован: "
            f"+${cash_gift:,.2f} и заявка на Telegram-подарок зарегистрирована (код: {gift_code})."
        )
        return True, text, result

    async def get_developer_projects(self, user_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 100))
        query = """
            SELECT *
            FROM developer_projects
            WHERE owner_id = ?
            ORDER BY
                CASE status WHEN 'building' THEN 0 WHEN 'ready' THEN 1 ELSE 2 END,
                ready_date ASC,
                id DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def start_developer_project(
        self,
        owner_id: int,
        tier: str,
        project_name: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_owner = int(owner_id)
        tier_code = str(tier or "").strip().lower()
        tier_cfg: Dict[str, Dict[str, Any]] = {
            "small": {"title": "Малый ЖК", "invest": 280.0, "minutes": 25, "mult_min": 1.20, "mult_max": 1.42},
            "district": {"title": "Городской квартал", "invest": 950.0, "minutes": 90, "mult_min": 1.24, "mult_max": 1.56},
            "mega": {"title": "Сити-проект", "invest": 2600.0, "minutes": 240, "mult_min": 1.30, "mult_max": 1.65},
        }
        cfg = tier_cfg.get(tier_code)
        if not cfg:
            return False, "Неизвестный тип проекта.", None

        now_dt = datetime.now()
        now = now_dt.isoformat()
        ready_dt = now_dt + timedelta(minutes=int(cfg["minutes"]))
        ready_date = ready_dt.isoformat()
        invested = float(cfg["invest"])

        clean_name = " ".join((project_name or "").strip().split())
        if not clean_name:
            clean_name = f"{cfg['title']} #{now_dt.strftime('%H%M')}"
        clean_name = clean_name[:80]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute("SELECT * FROM users WHERE user_id = ? LIMIT 1", (safe_owner,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            async with db.execute(
                "SELECT COUNT(*) AS c FROM developer_projects WHERE owner_id = ? AND status = 'building'",
                (safe_owner,),
            ) as cursor:
                active_row = await cursor.fetchone()
            active_count = int((active_row["c"] if active_row else 0) or 0)
            if active_count >= 5:
                await db.rollback()
                return False, "Лимит: максимум 5 активных стройпроектов одновременно.", None

            balance = float(user["balance"] or 0)
            if balance < invested:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${invested:,.2f}.", None

            inflation_index = 1.0
            async with db.execute("SELECT value FROM system_state WHERE key = 'inflation_index' LIMIT 1") as cursor:
                inf_row = await cursor.fetchone()
            if inf_row and inf_row[0] is not None:
                try:
                    inflation_index = max(0.6, min(3.5, float(inf_row[0])))
                except Exception:
                    inflation_index = 1.0

            random_mult = random.uniform(float(cfg["mult_min"]), float(cfg["mult_max"]))
            inflation_bonus = 1.0 + ((inflation_index - 1.0) * 0.10)
            expected_payout = round(invested * random_mult * inflation_bonus, 2)
            new_balance = round(balance - invested, 2)

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, safe_owner))
            cursor = await db.execute(
                """
                INSERT INTO developer_projects
                (owner_id, project_name, tier, invested, expected_payout, status, started_date, ready_date)
                VALUES (?, ?, ?, ?, ?, 'building', ?, ?)
                """,
                (safe_owner, clean_name, tier_code, invested, expected_payout, now, ready_date),
            )
            project_id = int(cursor.lastrowid or 0)
            await db.commit()

        try:
            await self.log_player_activity(
                user_id=safe_owner,
                activity_type="developer_project_start",
                details=f"Старт проекта '{clean_name}' ({tier_code})",
                value=invested,
            )
        except Exception:
            pass

        result = {
            "project_id": project_id,
            "tier": tier_code,
            "project_name": clean_name,
            "invested": invested,
            "expected_payout": expected_payout,
            "ready_date": ready_date,
            "new_balance": new_balance,
        }
        text = (
            f"Проект запущен: {clean_name}. "
            f"Инвестиция ${invested:,.2f}, ожидаемая выплата ${expected_payout:,.2f}."
        )
        return True, text, result

    async def claim_developer_project(
        self,
        owner_id: int,
        project_id: int,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_owner = int(owner_id)
        safe_project = int(project_id)
        now_dt = datetime.now()
        now = now_dt.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT *
                FROM developer_projects
                WHERE id = ? AND owner_id = ?
                LIMIT 1
                """,
                (safe_project, safe_owner),
            ) as cursor:
                project = await cursor.fetchone()
            if not project:
                await db.rollback()
                return False, "Проект не найден.", None

            status = str(project["status"] or "building").strip().lower()
            if status == "claimed":
                await db.rollback()
                return False, "Выплата по проекту уже получена.", None

            ready_date_raw = str(project["ready_date"] or "")
            try:
                ready_dt = datetime.fromisoformat(ready_date_raw) if ready_date_raw else now_dt
            except Exception:
                ready_dt = now_dt

            if now_dt < ready_dt:
                await db.rollback()
                remain = ready_dt - now_dt
                remain_minutes = max(1, int(remain.total_seconds() // 60))
                return False, f"Проект еще строится. Осталось ~{remain_minutes} мин.", None

            async with db.execute("SELECT balance FROM users WHERE user_id = ? LIMIT 1", (safe_owner,)) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "Игрок не найден.", None

            payout = round(float(project["expected_payout"] or 0), 2)
            new_balance = round(float(user_row["balance"] or 0) + payout, 2)

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, safe_owner))
            await db.execute(
                """
                UPDATE developer_projects
                SET status = 'claimed',
                    claimed_date = ?
                WHERE id = ?
                """,
                (now, safe_project),
            )
            await db.commit()

        try:
            await self.log_player_activity(
                user_id=safe_owner,
                activity_type="developer_project_claim",
                details=f"Завершен проект #{safe_project}",
                value=payout,
            )
        except Exception:
            pass

        result = {
            "project_id": safe_project,
            "payout": payout,
            "new_balance": new_balance,
            "project_name": str(project["project_name"] or ""),
        }
        text = f"Проект завершен. Выплата: +${payout:,.2f}."
        return True, text, result

    async def get_inflation_snapshot(self) -> Dict[str, Any]:
        values = {
            "inflation_index": "1.0",
            "inflation_daily_rate": "0.0025",
            "inflation_last_date": "",
        }
        query = """
            SELECT key, value
            FROM system_state
            WHERE key IN ('inflation_index', 'inflation_daily_rate', 'inflation_last_date')
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    if row and row[0] in values:
                        values[str(row[0])] = "" if row[1] is None else str(row[1])

        try:
            index = float(values["inflation_index"])
        except Exception:
            index = 1.0
        try:
            daily_rate = float(values["inflation_daily_rate"])
        except Exception:
            daily_rate = 0.0025
        return {
            "inflation_index": max(0.5, min(index, 10.0)),
            "inflation_daily_rate": max(0.0005, min(daily_rate, 0.02)),
            "inflation_last_date": values["inflation_last_date"],
        }

    async def apply_daily_inflation(self) -> Dict[str, Any]:
        snapshot = await self.get_inflation_snapshot()
        today = datetime.now().date().isoformat()
        if snapshot.get("inflation_last_date") == today:
            return {"applied": False, "date": today, **snapshot}

        index_before = float(snapshot.get("inflation_index") or 1.0)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT
                    COUNT(*) AS users_count,
                    COALESCE(AVG(COALESCE(balance, 0) + COALESCE(bank, 0) + COALESCE(cash, 0)), 0) AS avg_wealth
                FROM users
                """
            ) as cursor:
                row = await cursor.fetchone()
            users_count = int((row["users_count"] if row else 0) or 0)
            avg_wealth = float((row["avg_wealth"] if row else 0) or 0)

            base_rate = 0.0020
            pressure = (avg_wealth - 1000.0) / 12000.0
            pressure = max(-0.35, min(0.85, pressure))
            daily_rate = max(0.0007, min(0.012, base_rate + pressure * 0.0022))
            inflation_factor = round(1.0 + daily_rate, 6)
            index_after = round(index_before * inflation_factor, 6)

            await db.execute(
                "UPDATE properties SET price = ROUND(COALESCE(price, 0) * ?, 2), rent = ROUND(COALESCE(rent, 0) * ?, 2), maintenance_daily = ROUND(COALESCE(maintenance_daily, 0) * ?, 2)",
                (inflation_factor, inflation_factor, inflation_factor),
            )
            await db.execute(
                "UPDATE education_programs SET tuition_fee = ROUND(COALESCE(tuition_fee, 0) * ?, 2)",
                (inflation_factor,),
            )
            await db.execute(
                "UPDATE casinos SET min_bet = ROUND(COALESCE(min_bet, 0) * ?, 2), max_bet = ROUND(COALESCE(max_bet, 0) * ?, 2)",
                (inflation_factor, inflation_factor),
            )

            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES ('inflation_index', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(index_after),),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES ('inflation_daily_rate', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(round(daily_rate, 6)),),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES ('inflation_last_date', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (today,),
            )
            await db.commit()

        return {
            "applied": True,
            "date": today,
            "users_count": users_count,
            "avg_wealth": round(avg_wealth, 2),
            "inflation_factor": inflation_factor,
            "inflation_daily_rate": round(daily_rate, 6),
            "inflation_index_before": round(index_before, 6),
            "inflation_index_after": index_after,
            "inflation_last_date": today,
        }

    async def apply_to_organization(self, user_id: int, org_id: int, application_text: str) -> tuple[bool, str]:
        """Подать заявку в организацию"""
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            # Проверяем существующую заявку
            async with db.execute(
                'SELECT id FROM organization_applications WHERE user_id = ? AND org_id = ? AND status = ?',
                (user_id, org_id, 'pending')
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "📭 Вы уже подали заявку в эту организацию!"
            
            # Проверяем членство
            async with db.execute(
                'SELECT id FROM organization_members WHERE user_id = ? AND org_id = ?',
                (user_id, org_id)
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "👥 Вы уже являетесь членом этой организации!"

            async with db.execute(
                "SELECT id, name, requirements FROM organizations WHERE id = ? LIMIT 1",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "❌ Организация не найдена."
            org_name = str(org["name"] or "")
            org_requirements = str(org["requirements"] or "")

            async with db.execute(
                "SELECT education, reputation FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "❌ Игрок не найден."

            user_edu = int(user_row["education"] or 1)
            user_rep = float(user_row["reputation"] or 0.0)
            req_edu, req_rep = _parse_org_requirement_thresholds(org_requirements)
            if user_edu < req_edu:
                await db.rollback()
                return False, f"❌ Требуется образование {req_edu}+."
            if user_rep < req_rep:
                await db.rollback()
                return False, f"❌ Требуется репутация {req_rep:.1f}+."
              
            # Создаем заявку
            cursor = await db.execute(
                '''INSERT INTO organization_applications 
                   (org_id, user_id, application_text, applied_date, status)
                   VALUES (?, ?, ?, ?, ?)''',
                (org_id, user_id, application_text, now, 'pending')
            )
            app_id = int(cursor.lastrowid or 0)

            # Подсчет кадровиков (для текста причины автообработки).
            async with db.execute(
                """
                SELECT COUNT(*) AS c
                FROM organization_members om
                LEFT JOIN users u ON u.user_id = om.user_id
                WHERE om.org_id = ?
                  AND (
                        lower(COALESCE(om.role, '')) LIKE '%кадр%'
                        OR lower(COALESCE(om.role, '')) LIKE '%hr%'
                        OR lower(COALESCE(om.role, '')) LIKE '%персонал%'
                        OR lower(COALESCE(om.department, '')) LIKE '%кадр%'
                        OR lower(COALESCE(om.department, '')) LIKE '%hr%'
                        OR lower(COALESCE(u.role, '')) LIKE '%кадр%'
                        OR lower(COALESCE(u.role, '')) LIKE '%hr%'
                      )
                """,
                (int(org_id),),
            ) as cursor:
                hr_row = await cursor.fetchone()
            hr_count = int((hr_row["c"] if hr_row else 0) or 0)

            auto_reason = (
                "Автоодобрение: соответствует требованиям, кадровый отдел не требуется"
                if hr_count <= 0
                else "Автоодобрение: соответствует требованиям организации"
            )
            await db.execute(
                """
                UPDATE organization_applications
                SET status = 'approved',
                    reviewed_by = 0,
                    reviewed_date = ?,
                    notes = ?
                WHERE id = ?
                """,
                (now, auto_reason, app_id),
            )
            async with db.execute(
                "SELECT id FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                (int(org_id), int(user_id)),
            ) as cursor:
                member_row = await cursor.fetchone()
            if not member_row:
                await db.execute(
                    """
                    INSERT INTO organization_members
                    (org_id, user_id, role, salary, permissions, join_date, department, rank, experience, tasks_completed)
                    VALUES (?, ?, 'Стажер', 0, '', ?, 'general', 1, 0, 0)
                    """,
                    (int(org_id), int(user_id), now),
                )
            await db.execute(
                "UPDATE users SET organization = ?, role = 'Стажер' WHERE user_id = ?",
                (org_name, int(user_id)),
            )
            async with db.execute(
                "SELECT COUNT(*) AS c FROM organization_members WHERE org_id = ?",
                (int(org_id),),
            ) as cursor:
                count_row = await cursor.fetchone()
            members_count = int((count_row["c"] if count_row else 0) or 0)
            await db.execute(
                "UPDATE organizations SET members = ? WHERE id = ?",
                (members_count, int(org_id)),
            )
            await db.commit()
            return True, "✅ Заявка одобрена автоматически по требованиям организации."
    
    async def get_government_system(self) -> Optional[Dict[str, Any]]:
        """Получить текущую систему правления"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM government_system ORDER BY id DESC LIMIT 1') as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None
    
    # ==================== ПАРТИИ И ВЫБОРЫ ====================

    async def get_election(self, election_id: int) -> Optional[Dict[str, Any]]:
        """Получить выборы по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM elections WHERE id = ?', (election_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_active_presidential_election(self) -> Optional[Dict[str, Any]]:
        """Получить активные выборы президента"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT e.* FROM elections e
                   JOIN organizations o ON o.id = e.org_id
                   WHERE lower(COALESCE(o.type, '')) = 'government'
                     AND (
                          lower(COALESCE(e.position, '')) = 'president'
                          OR COALESCE(e.position, '') IN ('Президент', 'президент')
                     )
                     AND e.status = 'active'
                   ORDER BY e.start_date DESC
                   LIMIT 1''',
                ()
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def ensure_presidential_election(self, duration_hours: int = 15) -> Optional[int]:
        """Гарантировать наличие активных президентских выборов при отсутствии президента"""
        if await self.check_has_president():
            return None

        active = await self.get_active_presidential_election()
        if active:
            return int(active['id'])

        gov = await self.get_government_organization()
        if not gov:
            return None

        return await self.start_election(gov['id'], 'President', duration_hours=duration_hours)

    async def create_party(self, party_name: str, leader_id: int, election_id: int) -> tuple:
        """Создать новую партию в рамках конкретных выборов"""
        now = datetime.now().isoformat()
        clean_name = " ".join((party_name or "").strip().split())
        if not clean_name:
            return False, "❌ Укажите корректное название партии.", -1

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    'SELECT id, status, end_date, stage FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены.", -1

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Эти выборы уже завершены.", -1

                stage = _normalize_election_stage(election["stage"])
                if stage in {"voting", "finished"}:
                    await db.rollback()
                    return False, "❌ Создание партий закрыто на текущем этапе выборов.", -1

                end_dt = _parse_iso_datetime(election["end_date"])
                if end_dt and end_dt <= _now_for_datetime(end_dt):
                    await db.rollback()
                    return False, "❌ Регистрация на эти выборы уже закрыта.", -1

                async with db.execute(
                    '''SELECT p.id
                       FROM party_members pm
                       JOIN parties p ON p.id = pm.party_id
                       WHERE pm.user_id = ? AND p.election_id = ?
                       LIMIT 1''',
                    (leader_id, election_id)
                ) as cursor:
                    if await cursor.fetchone():
                        await db.rollback()
                        return False, "❌ Вы уже состоите в партии на этих выборах.", -1

                async with db.execute(
                    'SELECT id FROM parties WHERE election_id = ? AND lower(name) = lower(?)',
                    (election_id, clean_name)
                ) as cursor:
                    if await cursor.fetchone():
                        await db.rollback()
                        return False, "❌ Партия с таким названием уже зарегистрирована.", -1

                async with db.execute(
                    '''INSERT INTO parties (name, leader_id, election_id, created_date, members_count, status, votes_total)
                       VALUES (?, ?, ?, ?, 1, 'active', 0)''',
                    (clean_name, leader_id, election_id, now)
                ) as cursor:
                    party_id = cursor.lastrowid

                await db.execute(
                    '''INSERT INTO party_members (party_id, user_id, joined_date, role)
                       VALUES (?, ?, ?, 'leader')''',
                    (party_id, leader_id, now)
                )

                # Лидер новой партии автоматически становится кандидатом.
                await db.execute(
                    '''INSERT OR IGNORE INTO election_candidates
                       (election_id, candidate_id, votes, program, promises)
                       VALUES (?, ?, 0, ?, ?)''',
                    (
                        election_id,
                        leader_id,
                        f"Программа партии '{clean_name}'",
                        "",
                    ),
                )

                await db.commit()
                return True, f"✅ Партия '{clean_name}' успешно создана. Лидер добавлен в кандидаты.", party_id

        except aiosqlite.IntegrityError:
            return False, "❌ Не удалось создать партию: дублирующиеся данные.", -1
        except Exception as e:
            return False, f"❌ Ошибка при создании партии: {str(e)}", -1

    async def get_party_by_leader(self, leader_id: int, election_id: int) -> Optional[Dict[str, Any]]:
        """Получить партию лидера в рамках конкретных выборов"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM parties WHERE leader_id = ? AND election_id = ? LIMIT 1',
                (leader_id, election_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_user_party_for_election(self, user_id: int, election_id: int) -> Optional[Dict[str, Any]]:
        """Получить партию пользователя (как лидера или участника) в текущих выборах"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT p.* FROM parties p
                   JOIN party_members pm ON pm.party_id = p.id
                   WHERE pm.user_id = ? AND p.election_id = ?
                   LIMIT 1''',
                (user_id, election_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_party(self, party_id: int) -> Optional[Dict[str, Any]]:
        """Получить партию по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM parties WHERE id = ?', (party_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_party_members(self, party_id: int) -> List[Dict[str, Any]]:
        """Получить всех членов партии"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT pm.*,
                          u.user_id,
                          u.nickname,
                          u.full_name,
                          u.username,
                          COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) AS display_name
                   FROM party_members pm
                   JOIN users u ON pm.user_id = u.user_id
                   WHERE pm.party_id = ?
                   ORDER BY CASE WHEN pm.role = 'leader' THEN 0 ELSE 1 END,
                            COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) COLLATE NOCASE ASC''',
                (party_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def count_invitable_players_for_party(self, election_id: int, party_id: int, leader_id: int) -> int:
        """Посчитать игроков, которых можно пригласить в партию на текущих выборах."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                '''SELECT COUNT(*)
                   FROM users u
                   WHERE u.user_id != ?
                     AND NOT EXISTS (
                         SELECT 1
                         FROM party_members pm
                         JOIN parties p ON p.id = pm.party_id
                         WHERE pm.user_id = u.user_id
                           AND p.election_id = ?
                     )
                     AND NOT EXISTS (
                         SELECT 1
                         FROM party_invitations pi
                         WHERE pi.party_id = ?
                           AND pi.invited_user_id = u.user_id
                           AND pi.status IN ('pending', 'request')
                     )''',
                (leader_id, election_id, party_id),
            ) as cursor:
                row = await cursor.fetchone()
                return int((row[0] if row else 0) or 0)

    async def get_invitable_players_for_party(
        self,
        election_id: int,
        party_id: int,
        leader_id: int,
        limit: int = 8,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Получить страницу игроков, которых можно пригласить в партию."""
        safe_limit = max(1, min(int(limit or 8), 30))
        safe_offset = max(0, int(offset or 0))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT u.user_id,
                          u.nickname,
                          u.full_name,
                          u.username
                   FROM users u
                   WHERE u.user_id != ?
                     AND NOT EXISTS (
                         SELECT 1
                         FROM party_members pm
                         JOIN parties p ON p.id = pm.party_id
                         WHERE pm.user_id = u.user_id
                           AND p.election_id = ?
                     )
                     AND NOT EXISTS (
                         SELECT 1
                         FROM party_invitations pi
                         WHERE pi.party_id = ?
                           AND pi.invited_user_id = u.user_id
                           AND pi.status IN ('pending', 'request')
                     )
                   ORDER BY COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) COLLATE NOCASE
                   LIMIT ? OFFSET ?''',
                (leader_id, election_id, party_id, safe_limit, safe_offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def add_party_member(self, party_id: int, user_id: int) -> tuple:
        """Добавить члена в партию"""
        now = datetime.now().isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    'SELECT election_id FROM parties WHERE id = ?',
                    (party_id,)
                ) as cursor:
                    party_row = await cursor.fetchone()

                if not party_row:
                    await db.rollback()
                    return False, "❌ Партия не найдена."

                election_id = party_row['election_id']

                async with db.execute(
                    '''SELECT pm.id
                       FROM party_members pm
                       JOIN parties p ON p.id = pm.party_id
                       WHERE pm.user_id = ? AND p.election_id = ?
                       LIMIT 1''',
                    (user_id, election_id)
                ) as cursor:
                    if await cursor.fetchone():
                        await db.rollback()
                        return False, "❌ Игрок уже состоит в партии на этих выборах."

                await db.execute(
                    '''INSERT INTO party_members (party_id, user_id, joined_date, role)
                       VALUES (?, ?, ?, 'member')''',
                    (party_id, user_id, now)
                )
                await db.execute(
                    'UPDATE parties SET members_count = members_count + 1 WHERE id = ?',
                    (party_id,)
                )
                await db.commit()
                return True, "✅ Игрок добавлен в партию."

        except aiosqlite.IntegrityError:
            return False, "❌ Этот игрок уже состоит в партии."
        except Exception as e:
            return False, f"❌ Ошибка: {str(e)}"

    async def leave_party_for_election(self, user_id: int, election_id: int) -> tuple[bool, str]:
        """
        Выйти из текущей партии в рамках выборов.
        Если выходит лидер:
        - передает лидерство старшему участнику, если он есть;
        - иначе партия автоматически распускается.
        """
        now = datetime.now().isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    """
                    SELECT p.id AS party_id, p.leader_id, p.name, pm.role
                    FROM parties p
                    JOIN party_members pm ON pm.party_id = p.id
                    WHERE p.election_id = ? AND pm.user_id = ?
                    LIMIT 1
                    """,
                    (int(election_id), int(user_id)),
                ) as cursor:
                    membership = await cursor.fetchone()

                if not membership:
                    await db.rollback()
                    return False, "❌ Вы не состоите в партии на этих выборах."

                party_id = int(membership["party_id"])
                party_name = membership["name"] or "Партия"
                is_leader = str(membership["role"] or "").lower() == "leader"

                if is_leader:
                    async with db.execute(
                        """
                        SELECT user_id
                        FROM party_members
                        WHERE party_id = ? AND user_id != ?
                        ORDER BY joined_date ASC, id ASC
                        LIMIT 1
                        """,
                        (party_id, int(user_id)),
                    ) as cursor:
                        successor = await cursor.fetchone()

                    if successor:
                        successor_id = int(successor["user_id"])
                        await db.execute(
                            "UPDATE party_members SET role = 'leader' WHERE party_id = ? AND user_id = ?",
                            (party_id, successor_id),
                        )
                        await db.execute(
                            "UPDATE parties SET leader_id = ? WHERE id = ?",
                            (successor_id, party_id),
                        )
                        await db.execute(
                            "DELETE FROM party_members WHERE party_id = ? AND user_id = ?",
                            (party_id, int(user_id)),
                        )
                        await db.execute(
                            "UPDATE parties SET members_count = MAX(0, members_count - 1) WHERE id = ?",
                            (party_id,),
                        )
                        await db.commit()
                        return True, f"✅ Вы вышли из партии '{party_name}'. Лидерство передано участнику ID {successor_id}."

                    # Лидер последний участник — распускаем партию
                    await db.execute("DELETE FROM party_invitations WHERE party_id = ?", (party_id,))
                    await db.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
                    await db.execute("DELETE FROM parties WHERE id = ?", (party_id,))
                    await db.commit()
                    return True, f"✅ Вы вышли из партии '{party_name}'. Партия распущена."

                await db.execute(
                    "DELETE FROM party_members WHERE party_id = ? AND user_id = ?",
                    (party_id, int(user_id)),
                )
                await db.execute(
                    "UPDATE parties SET members_count = MAX(0, members_count - 1) WHERE id = ?",
                    (party_id,),
                )
                await db.commit()
                return True, f"✅ Вы вышли из партии '{party_name}'."

        except Exception as e:
            return False, f"❌ Ошибка выхода из партии: {str(e)}"

    async def get_election_parties(self, election_id: int) -> List[Dict[str, Any]]:
        """Получить все партии на выборах"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT p.*,
                          COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(p.leader_id AS TEXT)) AS leader_name
                   FROM parties p
                   LEFT JOIN users u ON p.leader_id = u.user_id
                   WHERE p.election_id = ?
                   ORDER BY p.members_count DESC, p.votes_total DESC, p.name ASC''',
                (election_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def register_candidate(self, election_id: int, user_id: int, program: str = "Моя программа") -> tuple:
        """Зарегистрировать кандидата на выборах"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    'SELECT status, end_date, stage FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены."

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Регистрация завершена: выборы неактивны."

                stage = _normalize_election_stage(election["stage"])
                if stage in {"voting", "finished"}:
                    await db.rollback()
                    return False, "❌ Регистрация кандидатов закрыта."

                end_dt = _parse_iso_datetime(election["end_date"])
                if end_dt and end_dt <= _now_for_datetime(end_dt):
                    await db.rollback()
                    return False, "❌ Регистрация завершена: срок выборов истек."

                await db.execute(
                    '''INSERT INTO election_candidates (election_id, candidate_id, votes, program, promises)
                       VALUES (?, ?, 0, ?, ?)''',
                    (election_id, user_id, program, "")
                )
                await db.commit()
                return True, "✅ Вы успешно зарегистрированы кандидатом."

        except aiosqlite.IntegrityError:
            return False, "❌ Вы уже зарегистрированы кандидатом на этих выборах."
        except Exception as e:
            return False, f"❌ Ошибка при регистрации кандидата: {str(e)}"

    async def get_election_candidates(self, election_id: int) -> List[Dict[str, Any]]:
        """Список кандидатов на выборах с именами"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT ec.id,
                          ec.election_id,
                          ec.candidate_id,
                          ec.votes,
                          ec.program,
                          ec.promises,
                          u.nickname,
                          u.full_name,
                          u.username,
                          COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ec.candidate_id AS TEXT)) AS candidate_name,
                          p.id AS party_id,
                          p.name AS party_name
                   FROM election_candidates ec
                   LEFT JOIN users u ON u.user_id = ec.candidate_id
                   LEFT JOIN parties p ON p.election_id = ec.election_id AND p.leader_id = ec.candidate_id
                   WHERE ec.election_id = ?
                   ORDER BY ec.votes DESC, ec.id ASC''',
                (election_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def has_user_voted(self, election_id: int, user_id: int) -> bool:
        """Проверить, голосовал ли пользователь на этих выборах"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT 1 FROM election_votes WHERE election_id = ? AND voter_id = ? LIMIT 1',
                (election_id, user_id)
            ) as cursor:
                return await cursor.fetchone() is not None

    async def cast_vote(self, election_id: int, voter_id: int, candidate_id: int) -> tuple:
        """Проголосовать за кандидата"""
        now = datetime.now().isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    'SELECT status, end_date, stage FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены."

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Выборы уже завершены."

                stage = _normalize_election_stage(election["stage"])
                if stage != "voting":
                    await db.rollback()
                    return False, "❌ Голосование на текущем этапе недоступно."

                end_dt = _parse_iso_datetime(election["end_date"])
                if end_dt and end_dt <= _now_for_datetime(end_dt):
                    await db.rollback()
                    return False, "❌ Голосование завершено."

                async with db.execute(
                    '''SELECT 1 FROM election_candidates
                       WHERE election_id = ? AND candidate_id = ?
                       LIMIT 1''',
                    (election_id, candidate_id)
                ) as cursor:
                    if not await cursor.fetchone():
                        await db.rollback()
                        return False, "❌ Кандидат не найден."

                try:
                    await db.execute(
                        '''INSERT INTO election_votes (election_id, voter_id, candidate_id, vote_date)
                           VALUES (?, ?, ?, ?)''',
                        (election_id, voter_id, candidate_id, now)
                    )
                except aiosqlite.IntegrityError:
                    await db.rollback()
                    return False, "❌ Вы уже голосовали на этих выборах."

                await db.execute(
                    '''UPDATE election_candidates
                       SET votes = votes + 1
                       WHERE election_id = ? AND candidate_id = ?''',
                    (election_id, candidate_id)
                )
                await db.execute(
                    '''UPDATE parties
                       SET votes_total = votes_total + 1
                       WHERE election_id = ? AND leader_id = ?''',
                    (election_id, candidate_id)
                )

                async with db.execute(
                    'SELECT COUNT(*) FROM election_votes WHERE election_id = ?',
                    (election_id,)
                ) as cursor:
                    count_row = await cursor.fetchone()
                    total_voters = int((count_row[0] if count_row else 0) or 0)

                await db.execute(
                    'UPDATE elections SET total_voters = ? WHERE id = ?',
                    (total_voters, election_id)
                )

                await db.commit()
                return True, "✅ Ваш голос учтен."

        except Exception as e:
            return False, f"❌ Ошибка при голосовании: {str(e)}"

    async def start_election(self, org_id: int, position: str, duration_hours: int = 15) -> int:
        """Начать выборы. Если уже есть активные по этой должности в этой организации - вернуть существующие."""
        start_date = datetime.now()
        end_date = start_date + timedelta(hours=duration_hours)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT id FROM elections
                   WHERE org_id = ? AND position = ? AND status = 'active'
                   ORDER BY start_date DESC
                   LIMIT 1''',
                (org_id, position)
            ) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return int(existing['id'])

            async with db.execute(
                '''INSERT INTO elections (org_id, position, start_date, end_date, status, stage)
                   VALUES (?, ?, ?, ?, 'active', 'registration')''',
                (org_id, position, start_date.isoformat(), end_date.isoformat())
            ) as cursor:
                election_id = cursor.lastrowid

            await db.commit()

        return election_id

    async def get_active_elections(self, org_id: int) -> List[Dict[str, Any]]:
        """Получить активные выборы в организации"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT * FROM elections
                   WHERE org_id = ? AND status = 'active'
                   ORDER BY start_date DESC''',
                (org_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def check_has_president(self) -> bool:
        """Проверить, есть ли действующий президент"""
        def _positive_int(value: Any) -> int:
            try:
                parsed = int(value or 0)
            except (TypeError, ValueError):
                return 0
            return parsed if parsed > 0 else 0

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT id, current_type, current_leader_id FROM government_system ORDER BY id DESC LIMIT 1"
            ) as cursor:
                gov_row = await cursor.fetchone()

            gov_id = int(gov_row["id"]) if gov_row else 0
            gov_type = str((gov_row["current_type"] if gov_row else "") or "democracy")
            leader_from_gov = _positive_int(gov_row["current_leader_id"] if gov_row else 0)

            if leader_from_gov:
                async with db.execute(
                    "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
                    (leader_from_gov,),
                ) as cursor:
                    user_exists = await cursor.fetchone()
                if user_exists:
                    return True

                # Если лидер в government_system указывает на несуществующего пользователя,
                # очищаем устаревшее значение и продолжаем восстановление по организациям.
                if gov_id > 0:
                    await db.execute(
                        "UPDATE government_system SET current_leader_id = NULL, last_changed = ? WHERE id = ?",
                        (now, gov_id),
                    )
                    await db.commit()

            async with db.execute(
                """
                SELECT id, name, leader_id
                FROM organizations
                WHERE lower(COALESCE(type, '')) = 'government'
                ORDER BY id ASC
                LIMIT 1
                """
            ) as cursor:
                org_row = await cursor.fetchone()

            org_id = int(org_row["id"]) if org_row else 0
            org_name = str((org_row["name"] if org_row else "") or "")
            leader_from_org = _positive_int(org_row["leader_id"] if org_row else 0)

            if leader_from_org:
                if gov_id > 0:
                    await db.execute(
                        "UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?",
                        (leader_from_org, now, gov_id),
                    )
                else:
                    await db.execute(
                        """
                        INSERT INTO government_system
                        (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                        VALUES (?, ?, ?, ?, 100, 0, 60)
                        """,
                        (gov_type or "democracy", leader_from_org, now, now),
                    )
                await db.commit()
                return True

            if org_id > 0:
                async with db.execute(
                    """
                    SELECT om.user_id, om.role
                    FROM organization_members om
                    WHERE om.org_id = ?
                    ORDER BY om.last_promotion DESC, om.join_date DESC, om.id DESC
                    """,
                    (org_id,),
                ) as cursor:
                    member_rows = await cursor.fetchall()

                leader_from_members = 0
                for member_row in member_rows:
                    role_lc = str((member_row["role"] or "")).strip().lower()
                    is_president_role = (
                        role_lc in {"президент", "leader", "лидер"}
                        or ("президент" in role_lc and "вице" not in role_lc)
                    )
                    if not is_president_role:
                        continue
                    leader_from_members = _positive_int(member_row["user_id"])
                    if leader_from_members:
                        break

                if leader_from_members:
                    await db.execute(
                        "UPDATE organizations SET leader_id = ? WHERE id = ?",
                        (leader_from_members, org_id),
                    )
                    if gov_id > 0:
                        await db.execute(
                            "UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?",
                            (leader_from_members, now, gov_id),
                        )
                    else:
                        await db.execute(
                            """
                            INSERT INTO government_system
                            (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                            VALUES (?, ?, ?, ?, 100, 0, 60)
                            """,
                            (gov_type or "democracy", leader_from_members, now, now),
                        )
                    await db.commit()
                    return True

                if org_name:
                    async with db.execute(
                        """
                        SELECT user_id, role
                        FROM users
                        WHERE organization = ?
                        ORDER BY last_activity DESC, created_date DESC, user_id DESC
                        """,
                        (org_name,),
                    ) as cursor:
                        user_rows = await cursor.fetchall()

                    leader_from_users = 0
                    for user_row in user_rows:
                        role_lc = str((user_row["role"] or "")).strip().lower()
                        is_president_role = (
                            role_lc in {"президент", "leader", "лидер"}
                            or ("президент" in role_lc and "вице" not in role_lc)
                        )
                        if not is_president_role:
                            continue
                        leader_from_users = _positive_int(user_row["user_id"])
                        if leader_from_users:
                            break

                    if leader_from_users:
                        await db.execute(
                            "UPDATE organizations SET leader_id = ? WHERE id = ?",
                            (leader_from_users, org_id),
                        )
                        if gov_id > 0:
                            await db.execute(
                                "UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?",
                                (leader_from_users, now, gov_id),
                            )
                        else:
                            await db.execute(
                                """
                                INSERT INTO government_system
                                (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                                VALUES (?, ?, ?, ?, 100, 0, 60)
                                """,
                                (gov_type or "democracy", leader_from_users, now, now),
                            )
                        await db.commit()
                        return True

        return False

    async def advance_election_stage(self, election_id: int, new_stage: str):
        """Обновить stage у выборов (служебный метод)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('UPDATE elections SET stage = ? WHERE id = ?', (new_stage, election_id))
            await db.commit()

    async def get_active_elections_full(self) -> List[Dict[str, Any]]:
        """Вернуть все активные выборы"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM elections WHERE status = 'active' ORDER BY start_date ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def sync_active_election_stages(self) -> List[Dict[str, Any]]:
        """
        Автоматически синхронизировать этапы активных выборов по времени.
        Переход ручными кнопками не требуется.
        """
        changes: List[Dict[str, Any]] = []
        # 4 рабочих этапа на интервале выборов:
        # registration -> campaign -> debates -> voting
        # finished выставляется только в finalize_expired_elections.
        def stage_by_ratio(ratio: float) -> str:
            if ratio < 0.25:
                return "registration"
            if ratio < 0.55:
                return "campaign"
            if ratio < 0.80:
                return "debates"
            return "voting"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT id, start_date, end_date, status, stage FROM elections WHERE status = 'active' ORDER BY id ASC"
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                election_id = int(row["id"])
                current_stage = _normalize_election_stage(row["stage"])
                if current_stage == "finished":
                    current_stage = "registration"

                start_dt = _parse_iso_datetime(row["start_date"])
                end_dt = _parse_iso_datetime(row["end_date"])
                if not start_dt or not end_dt:
                    continue

                if start_dt.tzinfo is not None and end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=start_dt.tzinfo)
                elif start_dt.tzinfo is None and end_dt.tzinfo is not None:
                    start_dt = start_dt.replace(tzinfo=end_dt.tzinfo)
                elif start_dt.tzinfo is not None and end_dt.tzinfo is not None:
                    end_dt = end_dt.astimezone(start_dt.tzinfo)

                now_dt = _now_for_datetime(start_dt)
                if end_dt <= start_dt:
                    continue
                if now_dt >= end_dt:
                    target_stage = "voting"
                elif now_dt <= start_dt:
                    target_stage = "registration"
                else:
                    total_seconds = max(1.0, (end_dt - start_dt).total_seconds())
                    elapsed_seconds = max(0.0, (now_dt - start_dt).total_seconds())
                    ratio = min(0.999, max(0.0, elapsed_seconds / total_seconds))
                    target_stage = stage_by_ratio(ratio)

                if target_stage != current_stage:
                    await db.execute(
                        "UPDATE elections SET stage = ? WHERE id = ?",
                        (target_stage, election_id),
                    )
                    changes.append(
                        {
                            "election_id": election_id,
                            "old_stage": current_stage,
                            "new_stage": target_stage,
                        }
                    )

            await db.commit()

        return changes

    async def finalize_expired_elections(self) -> List[Dict[str, Any]]:
        """Завершить просроченные выборы и назначить победителей"""
        now_dt = datetime.now()
        now_iso = now_dt.isoformat()
        results: List[Dict[str, Any]] = []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT * FROM elections WHERE status = 'active' ORDER BY end_date ASC"
            ) as cursor:
                active_rows = await cursor.fetchall()

            expired_elections: List[Dict[str, Any]] = []
            for row in active_rows:
                row_dict = dict(row)
                end_dt = _parse_iso_datetime(row_dict.get("end_date"))
                if not end_dt:
                    continue
                if end_dt <= _now_for_datetime(end_dt):
                    expired_elections.append(row_dict)

            for election in expired_elections:
                election_id = int(election['id'])
                org_id = int(election['org_id'])
                position = election.get('position') or ""

                async with db.execute(
                    '''SELECT id, candidate_id, votes
                       FROM election_candidates
                       WHERE election_id = ?
                       ORDER BY votes DESC, id ASC''',
                    (election_id,)
                ) as cursor:
                    candidate_rows = await cursor.fetchall()

                if not candidate_rows:
                    new_end = (now_dt + timedelta(hours=6)).isoformat()
                    await db.execute(
                        "UPDATE elections SET start_date = ?, end_date = ?, stage = 'registration' WHERE id = ?",
                        (now_iso, new_end, election_id)
                    )
                    results.append({
                        'election_id': election_id,
                        'status': 'extended_no_candidates',
                        'new_end_date': new_end,
                    })
                    continue

                winner_id = int(candidate_rows[0]['candidate_id'])
                winner_votes = int(candidate_rows[0]['votes'] or 0)
                tied_ids = [int(r['candidate_id']) for r in candidate_rows if int(r['votes'] or 0) == winner_votes]

                async with db.execute(
                    'SELECT COUNT(*) FROM election_votes WHERE election_id = ?',
                    (election_id,)
                ) as cursor:
                    count_row = await cursor.fetchone()
                    total_voters = int((count_row[0] if count_row else 0) or 0)

                await db.execute(
                    '''UPDATE elections
                       SET status = 'finished', winner_id = ?, total_voters = ?, stage = 'finished'
                       WHERE id = ?''',
                    (winner_id, total_voters, election_id)
                )
                await db.execute(
                    "UPDATE organizations SET leader_id = ?, last_election = ? WHERE id = ?",
                    (winner_id, now_iso, org_id)
                )

                is_presidential = (position.lower() == 'president')
                if not is_presidential:
                    async with db.execute("SELECT name FROM organizations WHERE id = ?", (org_id,)) as cursor:
                        org_row = await cursor.fetchone()
                    is_presidential = bool(org_row and org_row['name'] == 'Правительство')

                if is_presidential:
                    async with db.execute(
                        'SELECT id FROM government_system ORDER BY id DESC LIMIT 1'
                    ) as cursor:
                        gov_row = await cursor.fetchone()

                    if gov_row:
                        await db.execute(
                            'UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?',
                            (winner_id, now_iso, gov_row['id'])
                        )
                    else:
                        await db.execute(
                            '''INSERT INTO government_system
                               (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                               VALUES (?, ?, ?, ?, 100, 0, 60)''',
                            ('democracy', winner_id, now_iso, now_iso)
                        )

                results.append({
                    'election_id': election_id,
                    'status': 'finished',
                    'winner_id': winner_id,
                    'winner_votes': winner_votes,
                    'candidate_ids': [int(r['candidate_id']) for r in candidate_rows],
                    'is_tie_break': len(tied_ids) > 1,
                })

            await db.commit()

        return results

# Создаем глобальный экземпляр БД
    async def update_government_system(self, **kwargs) -> bool:
        """Обновить текущую запись government_system."""
        if not kwargs:
            return True

        field_aliases = {
            "government_type": "current_type",
            "satisfaction": "public_satisfaction",
        }
        normalized: Dict[str, Any] = {}
        for key, value in kwargs.items():
            normalized[field_aliases.get(key, key)] = value

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM government_system ORDER BY id DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                set_clause = ", ".join(f"{k} = ?" for k in normalized.keys())
                values = list(normalized.values()) + [row["id"]]
                await db.execute(
                    f"UPDATE government_system SET {set_clause} WHERE id = ?",
                    values,
                )
            else:
                current_type = normalized.get("current_type", "democracy")
                current_leader_id = normalized.get("current_leader_id")
                stability = int(normalized.get("stability", 100) or 100)
                corruption = int(normalized.get("corruption", 0) or 0)
                satisfaction = int(normalized.get("public_satisfaction", 60) or 60)
                now = datetime.now().isoformat()
                await db.execute(
                    """
                    INSERT INTO government_system
                    (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        current_type,
                        current_leader_id,
                        now,
                        now,
                        stability,
                        corruption,
                        satisfaction,
                    ),
                )

            await db.commit()
        return True

    async def count_players(self, search: str = "", exclude_user_id: Optional[int] = None) -> int:
        """Количество игроков для списков с опциональным поиском."""
        where_parts = ["1=1"]
        params: List[Any] = []

        if exclude_user_id is not None:
            where_parts.append("u.user_id != ?")
            params.append(int(exclude_user_id))

        clean_search = (search or "").strip().lower()
        if clean_search:
            where_parts.append(
                "(LOWER(COALESCE(u.nickname, '')) LIKE ? OR LOWER(COALESCE(u.full_name, '')) LIKE ? OR LOWER(COALESCE(u.username, '')) LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?)"
            )
            params.extend(
                [f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"]
            )

        query = f"SELECT COUNT(*) FROM users u WHERE {' AND '.join(where_parts)}"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                return int((row[0] if row else 0) or 0)

    async def get_players_page(
        self,
        limit: int = 10,
        offset: int = 0,
        search: str = "",
        exclude_user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Пагинированный список игроков."""
        safe_limit = max(1, min(int(limit or 10), 50))
        safe_offset = max(0, int(offset or 0))

        where_parts = ["1=1"]
        params: List[Any] = []

        if exclude_user_id is not None:
            where_parts.append("u.user_id != ?")
            params.append(int(exclude_user_id))

        clean_search = (search or "").strip().lower()
        if clean_search:
            where_parts.append(
                "(LOWER(COALESCE(u.nickname, '')) LIKE ? OR LOWER(COALESCE(u.full_name, '')) LIKE ? OR LOWER(COALESCE(u.username, '')) LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?)"
            )
            params.extend(
                [f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"]
            )

        params.extend([safe_limit, safe_offset])
        query = f"""
            SELECT u.user_id,
                   u.nickname,
                   u.full_name,
                   u.username,
                   u.organization,
                   u.role,
                   u.balance,
                   u.shadow_balance,
                   u.reputation,
                   u.tax_debt,
                   u.crimes_committed
            FROM users u
            WHERE {' AND '.join(where_parts)}
            ORDER BY COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) COLLATE NOCASE
            LIMIT ? OFFSET ?
        """

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def is_fbi_agent(self, user_id: int) -> bool:
        """Проверить, имеет ли игрок доступ к инструментам ФБР."""
        user = await self.get_user(user_id)
        if not user:
            return False
        role = (user.get("role") or "").lower()
        org = (user.get("organization") or "").lower()
        tokens = ("fbi", "\u0444\u0431\u0440")
        if any(token in role or token in org for token in tokens):
            return True
        return await self.is_user_in_org_type(user_id, "fbi")

    async def get_user_organization_id(self, user_id: int) -> Optional[int]:
        """Получить org_id по полю users.organization."""
        user = await self.get_user(user_id)
        if not user or not user.get("organization"):
            return None
        org = await self.get_organization(user["organization"])
        if not org:
            return None
        return int(org["id"])

    async def appoint_user_to_organization(
        self,
        target_user_id: int,
        org_id: int,
        role: str,
        appointed_by_id: Optional[int] = None,
    ) -> tuple[bool, str]:
        """Назначить игрока в организацию и должность."""
        org = await self.get_organization_by_id(org_id)
        user = await self.get_user(target_user_id)
        if not org:
            return False, "Организация не найдена."
        if not user:
            return False, "Игрок не найден."

        role_text = (role or "").strip() or "Сотрудник"
        now = datetime.now().isoformat()
        role_lc = role_text.lower()
        is_government_org = str(org.get("type") or "").lower() == "government"
        is_head_role = role_lc in {"leader", "лидер", "президент"} or ("президент" in role_lc and "вице" not in role_lc)
        is_deputy_role = role_lc in {"deputy", "заместитель", "вице-президент", "вице президент"} or ("вице" in role_lc and "президент" in role_lc)

        authority_to_grant: Optional[str] = None
        if is_government_org and is_head_role:
            authority_to_grant = "president"
        elif "вице" in role_lc and "президент" in role_lc:
            authority_to_grant = "vice_president"
        elif "министр финансов" in role_lc:
            authority_to_grant = "finance_minister"
        elif "министр" in role_lc:
            authority_to_grant = "minister"

        appointing_authority: Optional[str] = None
        if appointed_by_id is not None:
            appointing_authority = await self.get_government_authority(int(appointed_by_id))
        appointed_by_president = appointing_authority == "president"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            old_org_id: Optional[int] = None
            old_org_name = user.get("organization")
            if old_org_name:
                async with db.execute(
                    "SELECT id FROM organizations WHERE name = ? LIMIT 1",
                    (old_org_name,),
                ) as cursor:
                    old_org_row = await cursor.fetchone()
                    if old_org_row:
                        old_org_id = int(old_org_row["id"])

            # Если переводим сотрудника в другую организацию, снимаем его со старых лидерских полей.
            if old_org_id and old_org_id != int(org_id):
                await db.execute(
                    """
                    UPDATE organizations
                    SET leader_id = CASE WHEN leader_id = ? THEN NULL ELSE leader_id END,
                        deputy_id = CASE WHEN deputy_id = ? THEN NULL ELSE deputy_id END
                    WHERE id = ?
                    """,
                    (int(target_user_id), int(target_user_id), int(old_org_id)),
                )

            await db.execute(
                "DELETE FROM organization_members WHERE user_id = ? AND org_id != ?",
                (target_user_id, org_id),
            )

            async with db.execute(
                "SELECT id FROM organization_members WHERE user_id = ? AND org_id = ? LIMIT 1",
                (target_user_id, org_id),
            ) as cursor:
                member_row = await cursor.fetchone()

            if member_row:
                await db.execute(
                    """
                    UPDATE organization_members
                    SET role = ?, last_promotion = ?
                    WHERE id = ?
                    """,
                    (role_text, now, member_row["id"]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO organization_members
                    (org_id, user_id, role, salary, join_date, last_promotion)
                    VALUES (?, ?, ?, 0, ?, ?)
                    """,
                    (org_id, target_user_id, role_text, now, now),
                )

            await db.execute(
                "UPDATE users SET organization = ?, role = ? WHERE user_id = ?",
                (org["name"], role_text, target_user_id),
            )

            if is_head_role:
                await db.execute(
                    """
                    UPDATE organizations
                    SET leader_id = ?,
                        deputy_id = CASE WHEN deputy_id = ? THEN NULL ELSE deputy_id END
                    WHERE id = ?
                    """,
                    (target_user_id, target_user_id, org_id),
                )
            elif is_deputy_role:
                await db.execute(
                    """
                    UPDATE organizations
                    SET deputy_id = ?,
                        leader_id = CASE WHEN leader_id = ? THEN NULL ELSE leader_id END
                    WHERE id = ?
                    """,
                    (target_user_id, target_user_id, org_id),
                )
            else:
                # Если назначили на обычную роль, убираем возможные лидерские хвосты.
                await db.execute(
                    """
                    UPDATE organizations
                    SET leader_id = CASE WHEN leader_id = ? THEN NULL ELSE leader_id END,
                        deputy_id = CASE WHEN deputy_id = ? THEN NULL ELSE deputy_id END
                    WHERE id = ?
                    """,
                    (target_user_id, target_user_id, org_id),
                )

            if is_government_org and is_head_role:
                async with db.execute(
                    "SELECT id FROM government_system ORDER BY id DESC LIMIT 1"
                ) as cursor:
                    gov_row = await cursor.fetchone()
                if gov_row:
                    await db.execute(
                        "UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?",
                        (target_user_id, now, int(gov_row["id"])),
                    )
                else:
                    await db.execute(
                        """
                        INSERT INTO government_system
                        (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                        VALUES ('democracy', ?, ?, ?, 100, 0, 60)
                        """,
                        (target_user_id, now, now),
                    )

                # Если президент назначен вручную, закрываем активные президентские выборы.
                await db.execute(
                    """
                    UPDATE elections
                    SET status = 'finished',
                        winner_id = ?,
                        stage = 'finished',
                        end_date = ?
                    WHERE status = 'active'
                      AND org_id = ?
                      AND (
                           lower(COALESCE(position, '')) = 'president'
                           OR COALESCE(position, '') IN ('Президент', 'президент')
                      )
                    """,
                    (target_user_id, now, org_id),
                )

            if appointed_by_president:
                try:
                    if authority_to_grant in {"vice_president", "finance_minister", "minister"}:
                        await db.execute(
                            """
                            INSERT INTO government_authority_assignments
                            (user_id, authority, granted_by, granted_date, is_active)
                            VALUES (?, ?, ?, ?, 1)
                            ON CONFLICT(user_id) DO UPDATE SET
                                authority = excluded.authority,
                                granted_by = excluded.granted_by,
                                granted_date = excluded.granted_date,
                                is_active = 1
                            """,
                            (int(target_user_id), str(authority_to_grant), int(appointed_by_id), now),
                        )
                    else:
                        await db.execute(
                            "DELETE FROM government_authority_assignments WHERE user_id = ?",
                            (int(target_user_id),),
                        )
                except sqlite3.OperationalError as exc:
                    if "government_authority_assignments" not in str(exc).lower():
                        raise

            org_ids_to_recount = {org_id}
            if old_org_id and old_org_id != org_id:
                org_ids_to_recount.add(old_org_id)

            for recount_org_id in org_ids_to_recount:
                async with db.execute(
                    "SELECT COUNT(*) AS c FROM organization_members WHERE org_id = ?",
                    (recount_org_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    members_count = int((row["c"] if row else 0) or 0)
                await db.execute(
                    "UPDATE organizations SET members = ? WHERE id = ?",
                    (members_count, recount_org_id),
                )

            if appointed_by_id is not None:
                await db.execute(
                    """
                    INSERT INTO corruption_ops
                    (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                    VALUES (?, ?, 'appointment', 0, 5, 'logged', ?, ?)
                    """,
                    (
                        appointed_by_id,
                        target_user_id,
                        f"Назначение в {org['name']} на роль '{role_text}'",
                        now,
                    ),
                )

            await db.commit()

        return True, "Назначение выполнено."

    async def dismiss_organization_leader(
        self,
        actor_id: int,
        org_id: int,
        mode: str = "silent",
        reason: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Снять лидера организации.
        mode:
          - silent: без новостной публикации
          - public: с публикацией в СМИ
        """
        safe_org_id = int(org_id)
        safe_actor_id = int(actor_id)
        mode_lc = str(mode or "silent").strip().lower()
        if mode_lc not in {"silent", "public"}:
            mode_lc = "silent"

        org = await self.get_organization_by_id(safe_org_id)
        if not org:
            return False, "Организация не найдена.", None
        leader_id = int(org.get("leader_id") or 0)
        if leader_id <= 0:
            return False, "У организации нет назначенного лидера.", None

        authority = await self.get_government_authority(safe_actor_id)
        can_dismiss = safe_actor_id == leader_id or authority in {"president", "vice_president"}
        if not can_dismiss:
            return False, "Только президент, вице-президент или сам лидер могут снять лидера.", None

        actor = await self.get_user(safe_actor_id) or {}
        leader = await self.get_user(leader_id) or {}
        now = datetime.now().isoformat()
        clean_reason = " ".join((reason or "").strip().split())[:500]
        if not clean_reason:
            clean_reason = "Без указания причины"

        org_type = str(org.get("type") or "").strip().lower()
        org_name = str(org.get("name") or f"Организация #{safe_org_id}")
        actor_name = self.get_user_public_name(actor, fallback_id=safe_actor_id)
        leader_name = self.get_user_public_name(leader, fallback_id=leader_id)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT leader_id FROM organizations WHERE id = ? LIMIT 1",
                (safe_org_id,),
            ) as cursor:
                current = await cursor.fetchone()
            if not current:
                await db.rollback()
                return False, "Организация не найдена.", None
            if int(current["leader_id"] or 0) != leader_id:
                await db.rollback()
                return False, "Лидер организации уже изменился. Обновите панель.", None

            await db.execute(
                "UPDATE organizations SET leader_id = NULL WHERE id = ?",
                (safe_org_id,),
            )

            await db.execute(
                """
                UPDATE organization_members
                SET role = CASE
                    WHEN lower(COALESCE(role, '')) LIKE '%лидер%'
                      OR lower(COALESCE(role, '')) LIKE '%leader%'
                      OR lower(COALESCE(role, '')) LIKE '%chief%'
                      OR lower(COALESCE(role, '')) LIKE '%head%'
                      OR (
                           lower(COALESCE(role, '')) LIKE '%президент%'
                           AND lower(COALESCE(role, '')) NOT LIKE '%вице%'
                         )
                    THEN 'Сотрудник'
                    ELSE role
                END,
                    last_promotion = ?
                WHERE org_id = ? AND user_id = ?
                """,
                (now, safe_org_id, leader_id),
            )
            await db.execute(
                """
                UPDATE users
                SET role = CASE
                    WHEN lower(COALESCE(role, '')) LIKE '%лидер%'
                      OR lower(COALESCE(role, '')) LIKE '%leader%'
                      OR lower(COALESCE(role, '')) LIKE '%chief%'
                      OR lower(COALESCE(role, '')) LIKE '%head%'
                      OR (
                           lower(COALESCE(role, '')) LIKE '%президент%'
                           AND lower(COALESCE(role, '')) NOT LIKE '%вице%'
                         )
                    THEN 'Сотрудник'
                    ELSE role
                END
                WHERE user_id = ?
                """,
                (leader_id,),
            )

            if org_type == "government":
                async with db.execute("SELECT id, current_leader_id FROM government_system ORDER BY id DESC LIMIT 1") as cursor:
                    gov_row = await cursor.fetchone()
                if gov_row and int(gov_row["current_leader_id"] or 0) == leader_id:
                    await db.execute(
                        "UPDATE government_system SET current_leader_id = NULL, last_changed = ? WHERE id = ?",
                        (now, int(gov_row["id"])),
                    )
                    await db.execute(
                        "DELETE FROM government_authority_assignments WHERE user_id = ?",
                        (leader_id,),
                    )

            await db.execute(
                """
                INSERT INTO corruption_ops
                (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                VALUES (?, ?, ?, 0, ?, 'logged', ?, ?)
                """,
                (
                    safe_actor_id,
                    leader_id,
                    f"leader_dismiss_{mode_lc}",
                    12 if mode_lc == "public" else 6,
                    f"Снят лидер организации {org_name}. Причина: {clean_reason}",
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=safe_actor_id,
            activity_type="leader_dismissal",
            details=f"Снят лидер {leader_name} в {org_name} ({mode_lc})",
            value=0,
        )
        await self.log_player_activity(
            user_id=leader_id,
            activity_type="leader_removed",
            details=f"Снят с лидерской должности в {org_name}",
            value=0,
        )

        if mode_lc == "public":
            await self.create_media_news(
                title=f"Смена руководства в {org_name}",
                body=(
                    f"{leader_name} снят(а) с лидерской должности. "
                    f"Решение оформил(а): {actor_name}. Причина: {clean_reason}."
                ),
                source_user_id=safe_actor_id,
                severity="high",
            )

        notice_text = (
            f"Вы сняты с должности лидера организации {org_name}.\n"
            f"Решение: {'публичное' if mode_lc == 'public' else 'тихое'}.\n"
            f"Инициатор: {actor_name}.\n"
            f"Причина: {clean_reason}."
        )
        await self.send_private_message(
            sender_id=safe_actor_id,
            recipient_id=leader_id,
            subject=f"🔔 Снятие с лидерской должности ({org_name})",
            content=notice_text,
            message_type="system",
        )

        payload = {
            "org_id": safe_org_id,
            "org_name": org_name,
            "leader_id": leader_id,
            "leader_name": leader_name,
            "mode": mode_lc,
            "reason": clean_reason,
            "initiator_name": actor_name,
        }
        return True, "Лидер успешно снят с должности.", payload

    async def get_election_debate_posts(
        self,
        election_id: int,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Получить ленту дебатов по выборам."""
        safe_limit = max(1, min(int(limit or 20), 100))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT ed.id,
                       ed.election_id,
                       ed.user_id,
                       ed.candidate_id,
                       ed.party_id,
                       ed.message,
                       ed.created_date,
                       u.nickname,
                       u.full_name,
                       u.username,
                       p.name AS party_name
                FROM election_debates ed
                LEFT JOIN users u ON u.user_id = ed.user_id
                LEFT JOIN parties p ON p.id = ed.party_id
                WHERE ed.election_id = ?
                ORDER BY ed.created_date DESC
                LIMIT ?
                """,
                (election_id, safe_limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def add_election_debate_post(
        self,
        election_id: int,
        user_id: int,
        message: str,
    ) -> tuple[bool, str]:
        """Опубликовать сообщение в дебатах."""
        clean = " ".join((message or "").strip().split())
        if len(clean) < 5:
            return False, "Слишком короткое сообщение (минимум 5 символов)."
        if len(clean) > 700:
            return False, "Слишком длинное сообщение (максимум 700 символов)."

        election = await self.get_election(election_id)
        if not election:
            return False, "Выборы не найдены."
        if election.get("status") != "active":
            return False, "Дебаты закрыты: выборы неактивны."

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                """
                SELECT candidate_id
                FROM election_candidates
                WHERE election_id = ? AND candidate_id = ?
                LIMIT 1
                """,
                (election_id, user_id),
            ) as cursor:
                cand = await cursor.fetchone()

            candidate_id = int(cand["candidate_id"]) if cand else None

            party_id = None
            async with db.execute(
                """
                SELECT p.id
                FROM parties p
                JOIN party_members pm ON pm.party_id = p.id
                WHERE p.election_id = ? AND pm.user_id = ?
                LIMIT 1
                """,
                (election_id, user_id),
            ) as cursor:
                party = await cursor.fetchone()
                if party:
                    party_id = int(party["id"])

            await db.execute(
                """
                INSERT INTO election_debates
                (election_id, user_id, candidate_id, party_id, message, created_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (election_id, user_id, candidate_id, party_id, clean, now),
            )
            await db.commit()

        return True, "Сообщение опубликовано в дебатах."

    async def cycle_election_stage(self, election_id: int) -> tuple[bool, str, str]:
        """Перевести выборы на следующий этап."""
        stages = ["registration", "campaign", "debates", "voting", "finished"]
        stage_alias = {
            "nomination": "registration",
            "register": "registration",
        }

        election = await self.get_election(election_id)
        if not election:
            return False, "Выборы не найдены.", "unknown"
        if election.get("status") != "active":
            return False, "Выборы неактивны.", str(election.get("stage") or "finished")

        current_stage = str(election.get("stage") or "registration").strip().lower()
        current_stage = stage_alias.get(current_stage, current_stage)
        if current_stage not in stages:
            current_stage = "registration"

        if current_stage == "finished":
            return False, "Этапы уже завершены.", "finished"

        next_index = min(stages.index(current_stage) + 1, len(stages) - 1)
        next_stage = stages[next_index]

        async with aiosqlite.connect(self.db_path) as db:
            if next_stage == "finished":
                await db.execute(
                    "UPDATE elections SET stage = ?, status = 'finished' WHERE id = ?",
                    (next_stage, election_id),
                )
            else:
                await db.execute(
                    "UPDATE elections SET stage = ? WHERE id = ?",
                    (next_stage, election_id),
                )
            await db.commit()

        return True, "Этап выборов обновлен.", next_stage

    async def send_private_message(
        self,
        sender_id: int,
        recipient_id: int,
        subject: str,
        content: str,
        message_type: str = "private",
    ) -> tuple[bool, str, int]:
        """Отправить личное или системное сообщение в центр писем."""
        safe_sender = int(sender_id or 0)
        safe_recipient = int(recipient_id or 0)
        if safe_recipient <= 0:
            return False, "Получатель не найден.", 0
        if safe_sender < 0:
            return False, "Некорректный отправитель.", 0

        clean_subject = " ".join((subject or "").strip().split())[:120]
        clean_content = " ".join((content or "").strip().split())[:2500]
        safe_type = str(message_type or "private").strip().lower()[:24]
        if safe_type not in {"private", "system", "service", "gov"}:
            safe_type = "private"

        if not clean_content:
            return False, "Пустое сообщение.", 0
        if not clean_subject:
            clean_subject = "Сообщение"

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO messages
                (sender_id, recipient_id, subject, content, created_date, message_type, deleted_by_sender, deleted_by_recipient)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0)
                """,
                (safe_sender, safe_recipient, clean_subject, clean_content, now, safe_type),
            )
            message_id = int(cursor.lastrowid or 0)
            await db.commit()

        return True, "Сообщение отправлено.", message_id

    async def send_organization_chat_message(
        self,
        org_id: int,
        user_id: int,
        content: str,
        is_hidden: bool = False,
    ) -> tuple[bool, str]:
        """Отправить сообщение в чат организации."""
        clean = " ".join((content or "").strip().split())
        if len(clean) < 2:
            return False, "Слишком короткое сообщение."
        if len(clean) > 1200:
            return False, "Слишком длинное сообщение (максимум 1200 символов)."

        org = await self.get_organization_by_id(org_id)
        if not org:
            return False, "Организация не найдена."
        if not await self.is_user_org_member(user_id, org_id):
            return False, "Только сотрудники организации могут писать в этот чат."

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO organization_chats (org_id, user_id, content, message_type, is_hidden, created_date)
                VALUES (?, ?, ?, 'text', ?, ?)
                """,
                (org_id, user_id, clean, 1 if is_hidden else 0, now),
            )

            if is_hidden:
                risk = min(100, max(15, len(clean) // 8))
                await db.execute(
                    """
                    INSERT INTO corruption_ops
                    (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                    VALUES (?, NULL, 'hidden_chat', 0, ?, 'logged', ?, ?)
                    """,
                    (user_id, risk, f"Скрытый чат в организации {org['name']}", now),
                )
                await db.execute(
                    """
                    UPDATE users
                    SET corruption_score = COALESCE(corruption_score, 0) + ?
                    WHERE user_id = ?
                    """,
                    (max(1, risk // 10), user_id),
                )

            await db.commit()

        return True, "Сообщение отправлено."

    async def get_organization_chat_messages(
        self,
        org_id: int,
        limit: int = 30,
        include_hidden: bool = False,
    ) -> List[Dict[str, Any]]:
        """Получить сообщения чата организации."""
        safe_limit = max(1, min(int(limit or 30), 100))
        hidden_filter = "" if include_hidden else "AND oc.is_hidden = 0"
        query = f"""
            SELECT oc.id,
                   oc.org_id,
                   oc.user_id,
                   oc.content,
                   oc.message_type,
                   oc.is_hidden,
                   oc.created_date,
                   u.nickname,
                   u.full_name,
                   u.username
            FROM organization_chats oc
            LEFT JOIN users u ON u.user_id = oc.user_id
            WHERE oc.org_id = ?
              {hidden_filter}
            ORDER BY oc.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (org_id, safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_organization_activity_snapshot(
        self,
        org_id: int,
        hours: int = 24,
    ) -> Dict[str, Any]:
        safe_org_id = int(org_id or 0)
        if safe_org_id <= 0:
            return {}

        org = await self.get_organization_by_id(safe_org_id)
        if not org:
            return {}

        safe_hours = max(1, min(int(hours or 24), 168))
        since = (datetime.now() - timedelta(hours=safe_hours)).isoformat()

        payload: Dict[str, Any] = {
            "org_id": safe_org_id,
            "org_name": str(org.get("name") or f"Организация #{safe_org_id}"),
            "org_type": str(org.get("type") or ""),
            "policy": str(org.get("policy") or ""),
            "budget": float(org.get("budget") or 0),
            "hours": safe_hours,
            "members": 0,
            "pending_apps": 0,
            "payroll_daily": 0.0,
            "chat_messages": 0,
            "hidden_messages": 0,
            "activity_events": 0,
            "top_chat_members": [],
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                """
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(COALESCE(salary, 0)), 0) AS payroll
                FROM organization_members
                WHERE org_id = ?
                """,
                (safe_org_id,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    payload["members"] = int(row["c"] or 0)
                    payload["payroll_daily"] = float(row["payroll"] or 0)

            async with db.execute(
                """
                SELECT COUNT(*) AS c
                FROM organization_applications
                WHERE org_id = ?
                  AND status = 'pending'
                """,
                (safe_org_id,),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    payload["pending_apps"] = int(row["c"] or 0)

            async with db.execute(
                """
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(CASE WHEN is_hidden = 1 THEN 1 ELSE 0 END), 0) AS hidden_c
                FROM organization_chats
                WHERE org_id = ?
                  AND created_date >= ?
                """,
                (safe_org_id, since),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    payload["chat_messages"] = int(row["c"] or 0)
                    payload["hidden_messages"] = int(row["hidden_c"] or 0)

            async with db.execute(
                """
                SELECT COUNT(*) AS c
                FROM player_activity_log pal
                JOIN organization_members om ON om.user_id = pal.user_id
                WHERE om.org_id = ?
                  AND pal.created_date >= ?
                """,
                (safe_org_id, since),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    payload["activity_events"] = int(row["c"] or 0)

            async with db.execute(
                """
                SELECT oc.user_id,
                       COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(oc.user_id AS TEXT)) AS member_name,
                       COUNT(*) AS c
                FROM organization_chats oc
                LEFT JOIN users u ON u.user_id = oc.user_id
                WHERE oc.org_id = ?
                  AND oc.created_date >= ?
                GROUP BY oc.user_id, member_name
                ORDER BY c DESC, member_name ASC
                LIMIT 5
                """,
                (safe_org_id, since),
            ) as cur:
                rows = await cur.fetchall()
                payload["top_chat_members"] = [
                    {
                        "user_id": int(r["user_id"] or 0),
                        "member_name": str(r["member_name"] or f"#{int(r['user_id'] or 0)}"),
                        "messages": int(r["c"] or 0),
                    }
                    for r in rows
                ]

        return payload

    async def publish_organization_news(
        self,
        actor_id: int,
        org_id: int,
        title: str,
        body: str,
        severity: str = "hot",
    ) -> tuple[bool, str, int]:
        safe_actor = int(actor_id or 0)
        safe_org_id = int(org_id or 0)
        if safe_actor <= 0 or safe_org_id <= 0:
            return False, "Некорректные параметры публикации.", 0

        org = await self.get_organization_by_id(safe_org_id)
        if not org:
            return False, "Организация не найдена.", 0
        if not await self.can_manage_organization(safe_actor, safe_org_id):
            return False, "Нет прав на публикацию от имени организации.", 0

        clean_title = " ".join((title or "").split()).strip()
        clean_body = " ".join((body or "").split()).strip()
        if len(clean_body) < 8:
            return False, "Текст новости слишком короткий.", 0
        if not clean_title:
            clean_title = "Официальное сообщение"

        org_name = str(org.get("name") or f"Организация #{safe_org_id}")
        full_title = f"{org_name}: {clean_title}"
        safe_severity = (severity or "hot").strip().lower()
        if safe_severity not in {"normal", "high", "critical", "hot"}:
            safe_severity = "hot"

        news_id = await self.create_media_news(
            title=full_title,
            body=clean_body,
            source_user_id=safe_actor,
            severity=safe_severity,
        )
        if news_id <= 0:
            return False, "Не удалось опубликовать новость.", 0

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO organization_chats (org_id, user_id, content, message_type, is_hidden, created_date)
                VALUES (?, ?, ?, 'bulletin', 0, ?)
                """,
                (safe_org_id, safe_actor, f"Официальная публикация: {clean_title}", now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=safe_actor,
            activity_type="org_news_publish",
            details=f"Публикация от {org_name}: {clean_title}",
            value=0.0,
        )
        return True, "Новость опубликована в ленте СМИ.", news_id

    async def can_access_government_radio(self, user_id: int, for_send: bool = False) -> bool:
        """Проверить доступ к гос-рации: просмотр (правительство/ФБР), эфир (правительство)."""
        authority = await self.get_government_authority(user_id)
        if authority in {"president", "vice_president", "finance_minister", "minister"}:
            return True
        if not for_send and await self.is_fbi_agent(user_id):
            return True

        gov_org = await self.get_government_organization()
        if not gov_org:
            return False
        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return False
        return await self.is_user_org_member(user_id, gov_org_id)

    async def get_government_radio_messages(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Получить ленту сообщений гос-рации."""
        gov_org = await self.get_government_organization()
        if not gov_org:
            await self.init_default_organizations()
            gov_org = await self.get_government_organization()
        if not gov_org:
            return []
        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return []
        safe_limit = max(1, min(int(limit or 25), 100))
        query = """
            SELECT oc.id,
                   oc.org_id,
                   oc.user_id,
                   oc.content,
                   oc.message_type,
                   oc.created_date,
                   u.nickname,
                   u.full_name,
                   u.username
            FROM organization_chats oc
            LEFT JOIN users u ON u.user_id = oc.user_id
            WHERE oc.org_id = ?
              AND lower(COALESCE(oc.message_type, '')) IN ('radio', 'gov_radio')
            ORDER BY oc.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (gov_org_id, safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def send_government_radio_message(self, user_id: int, content: str) -> tuple[bool, str]:
        """Отправить сообщение в эфир гос-рации."""
        if not await self.can_access_government_radio(user_id, for_send=True):
            return False, "Эфир доступен только сотрудникам правительства."

        clean = " ".join((content or "").strip().split())
        if len(clean) < 3:
            return False, "Сообщение слишком короткое."
        if len(clean) > 1200:
            return False, "Сообщение слишком длинное (максимум 1200 символов)."

        allowed, remain = await self.check_and_set_user_cooldown(user_id, "government_radio_broadcast", 2)
        if not allowed:
            return False, f"Слишком часто. Повторите через {remain} мин."

        gov_org = await self.get_government_organization()
        if not gov_org:
            await self.init_default_organizations()
            gov_org = await self.get_government_organization()
        if not gov_org:
            return False, "Правительство не найдено. Попробуйте перезапустить бота."
        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return False, "Ошибка данных правительства."

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO organization_chats (org_id, user_id, content, message_type, is_hidden, created_date)
                VALUES (?, ?, ?, 'radio', 0, ?)
                """,
                (gov_org_id, int(user_id), clean, now),
            )
            await db.commit()

        speaker = await self.get_user_public_name_by_id(user_id)
        await self.log_player_activity(
            user_id=user_id,
            activity_type="government_radio",
            details=f"Эфир гос-рации: {clean[:160]}",
            value=0,
        )
        await self.create_media_news(
            title="Эфир гос-рации",
            body=f"{speaker}: {clean[:260]}",
            source_user_id=user_id,
            severity="normal",
        )
        return True, "Сообщение отправлено в гос-рацию."

    async def get_current_president_id(self) -> Optional[int]:
        gov = await self.get_government_system() or {}
        leader_id = int(gov.get("current_leader_id") or 0)
        if leader_id > 0:
            user = await self.get_user(leader_id)
            if user:
                return leader_id

        gov_org = await self.get_government_organization()
        if gov_org:
            org_leader = int(gov_org.get("leader_id") or 0)
            if org_leader > 0 and await self.get_user(org_leader):
                return org_leader

        query = """
            SELECT user_id
            FROM users
            WHERE lower(COALESCE(role, '')) LIKE '%президент%'
              AND lower(COALESCE(role, '')) NOT LIKE '%вице%'
            ORDER BY last_activity DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                row = await cursor.fetchone()
                if row:
                    return int(row["user_id"])
        return None

    async def get_current_vice_president_id(self) -> Optional[int]:
        query = """
            SELECT user_id
            FROM users
            WHERE lower(COALESCE(role, '')) LIKE '%вице%'
              AND lower(COALESCE(role, '')) LIKE '%президент%'
            ORDER BY last_activity DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                row = await cursor.fetchone()
                if row:
                    return int(row["user_id"])
        return None

    async def create_citizen_appeal(
        self,
        citizen_id: int,
        content: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        user = await self.get_user(int(citizen_id))
        if not user:
            return False, "Профиль гражданина не найден.", None

        clean = " ".join((content or "").strip().split())
        if len(clean) < 10:
            return False, "Обращение слишком короткое (минимум 10 символов).", None
        if len(clean) > 1400:
            return False, "Обращение слишком длинное (максимум 1400 символов).", None

        allowed, remain = await self.check_and_set_user_cooldown(int(citizen_id), "appeal_to_president", 1)
        if not allowed:
            return False, f"Слишком часто. Повторите через {remain} мин.", None

        president_id = await self.get_current_president_id()
        if not president_id:
            return False, "Президент пока не назначен. Обращение временно недоступно.", None

        vice_id = await self.get_current_vice_president_id()
        if vice_id == president_id:
            vice_id = None

        status = "pending_vice" if vice_id else "pending_president"
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO citizen_appeals
                (citizen_id, vice_id, president_id, content, status, created_date)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(citizen_id), int(vice_id) if vice_id else None, int(president_id), clean, status, now),
            )
            appeal_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=int(citizen_id),
            activity_type="citizen_appeal",
            details="Отправлено обращение президенту.",
            value=0,
        )
        return True, (
            "Обращение отправлено вице-президенту на проверку."
            if status == "pending_vice"
            else "Обращение отправлено напрямую президенту."
        ), {
            "appeal_id": appeal_id,
            "status": status,
            "citizen_id": int(citizen_id),
            "vice_id": int(vice_id) if vice_id else None,
            "president_id": int(president_id),
        }

    async def get_pending_citizen_appeal_count(self, reviewer_id: int) -> int:
        authority = await self.get_government_authority(int(reviewer_id))
        if authority == "vice_president":
            query = "SELECT COUNT(*) FROM citizen_appeals WHERE status = 'pending_vice' AND vice_id = ?"
            params = (int(reviewer_id),)
        elif authority == "president":
            query = "SELECT COUNT(*) FROM citizen_appeals WHERE status = 'pending_president' AND president_id = ?"
            params = (int(reviewer_id),)
        else:
            return 0

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return int((row[0] if row else 0) or 0)

    async def get_pending_citizen_appeals(self, reviewer_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        authority = await self.get_government_authority(int(reviewer_id))
        if authority == "vice_president":
            where_sql = "ca.status = 'pending_vice' AND ca.vice_id = ?"
        elif authority == "president":
            where_sql = "ca.status = 'pending_president' AND ca.president_id = ?"
        else:
            return []

        query = f"""
            SELECT ca.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ca.citizen_id AS TEXT)) AS citizen_name,
                   u.username AS citizen_username
            FROM citizen_appeals ca
            LEFT JOIN users u ON u.user_id = ca.citizen_id
            WHERE {where_sql}
            ORDER BY ca.created_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(reviewer_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_citizen_appeals(self, citizen_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 10), 50))
        query = """
            SELECT *
            FROM citizen_appeals
            WHERE citizen_id = ?
            ORDER BY created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(citizen_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def review_citizen_appeal(
        self,
        reviewer_id: int,
        appeal_id: int,
        approve: bool,
        note: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_note = " ".join((note or "").strip().split())[:400]
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM citizen_appeals WHERE id = ? LIMIT 1", (int(appeal_id),)) as cursor:
                row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return False, "Обращение не найдено.", None
            appeal = dict(row)
            status = str(appeal.get("status") or "")

            if status == "pending_vice":
                if int(appeal.get("vice_id") or 0) != int(reviewer_id):
                    await db.rollback()
                    return False, "Это обращение должен проверить вице-президент.", None
                if approve:
                    new_status = "pending_president"
                    await db.execute(
                        """
                        UPDATE citizen_appeals
                        SET status = ?, vice_note = ?, vice_review_date = ?
                        WHERE id = ?
                        """,
                        (new_status, safe_note or "Одобрено вице-президентом", now, int(appeal_id)),
                    )
                    msg = "Обращение одобрено и передано президенту."
                else:
                    new_status = "rejected_by_vice"
                    await db.execute(
                        """
                        UPDATE citizen_appeals
                        SET status = ?, vice_note = ?, vice_review_date = ?
                        WHERE id = ?
                        """,
                        (new_status, safe_note or "Отклонено вице-президентом", now, int(appeal_id)),
                    )
                    msg = "Обращение отклонено вице-президентом."
            elif status == "pending_president":
                if int(appeal.get("president_id") or 0) != int(reviewer_id):
                    await db.rollback()
                    return False, "Это обращение должен проверить президент.", None
                if approve:
                    new_status = "approved_by_president"
                    msg = "Обращение одобрено президентом."
                else:
                    new_status = "rejected_by_president"
                    msg = "Обращение отклонено президентом."
                await db.execute(
                    """
                    UPDATE citizen_appeals
                    SET status = ?, president_note = ?, president_review_date = ?
                    WHERE id = ?
                    """,
                    (new_status, safe_note or ("Одобрено президентом" if approve else "Отклонено президентом"), now, int(appeal_id)),
                )
            else:
                await db.rollback()
                return False, "Обращение уже обработано.", None

            await db.commit()

        appeal["new_status"] = new_status
        return True, msg, appeal

    async def get_player_surveillance_feed(
        self,
        player_id: int,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Единая лента активности игрока для ФБР."""
        safe_limit = max(1, min(int(limit or 30), 200))
        query = """
            SELECT m.created_date AS created_date,
                   CASE WHEN m.sender_id = ? THEN 'dm_out' ELSE 'dm_in' END AS source,
                   CASE WHEN m.sender_id = ? THEN m.recipient_id ELSE m.sender_id END AS peer_id,
                   CASE WHEN m.sender_id = ?
                        THEN COALESCE(NULLIF(ru.nickname, ''), NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(m.recipient_id AS TEXT))
                        ELSE COALESCE(NULLIF(su.nickname, ''), NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(m.sender_id AS TEXT))
                   END AS peer_name,
                   COALESCE(NULLIF(m.subject, ''), 'Личное сообщение') AS title,
                   m.content AS content,
                   0 AS is_hidden
            FROM messages m
            LEFT JOIN users su ON su.user_id = m.sender_id
            LEFT JOIN users ru ON ru.user_id = m.recipient_id
            WHERE m.sender_id = ? OR m.recipient_id = ?

            UNION ALL

            SELECT oc.created_date AS created_date,
                   'org_chat' AS source,
                   oc.org_id AS peer_id,
                   COALESCE(o.name, CAST(oc.org_id AS TEXT)) AS peer_name,
                   CASE WHEN oc.is_hidden = 1 THEN 'Скрытый канал' ELSE 'Чат организации' END AS title,
                   oc.content AS content,
                   oc.is_hidden AS is_hidden
            FROM organization_chats oc
            LEFT JOIN organizations o ON o.id = oc.org_id
            WHERE oc.user_id = ?

            UNION ALL

            SELECT ed.created_date AS created_date,
                   'debate' AS source,
                   ed.election_id AS peer_id,
                   'Выборы #' || CAST(ed.election_id AS TEXT) AS peer_name,
                   'Дебаты' AS title,
                   ed.message AS content,
                   0 AS is_hidden
            FROM election_debates ed
            WHERE ed.user_id = ?

            ORDER BY created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            params = (
                player_id,
                player_id,
                player_id,
                player_id,
                player_id,
                player_id,
                player_id,
                safe_limit,
            )
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_player_contact_stats(
        self,
        player_id: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Топ контактов игрока по личным сообщениям."""
        safe_limit = max(1, min(int(limit or 10), 50))
        query = """
            SELECT c.contact_id AS user_id,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(c.contact_id AS TEXT)) AS display_name,
                   c.msg_count,
                   c.last_contact
            FROM (
                SELECT CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END AS contact_id,
                       COUNT(*) AS msg_count,
                       MAX(created_date) AS last_contact
                FROM messages
                WHERE sender_id = ? OR recipient_id = ?
                GROUP BY CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END
            ) c
            LEFT JOIN users u ON u.user_id = c.contact_id
            ORDER BY c.msg_count DESC, c.last_contact DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            params = (player_id, player_id, player_id, player_id, safe_limit)
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_fbi_global_feed(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Глобальная лента перехвата для ФБР из всех каналов."""
        safe_limit = max(1, min(int(limit or 50), 300))
        query = """
            SELECT m.created_date AS created_date,
                   'dm' AS source,
                   m.sender_id AS actor_id,
                   COALESCE(NULLIF(su.nickname, ''), NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(m.sender_id AS TEXT)) AS actor_name,
                   m.recipient_id AS target_id,
                   COALESCE(NULLIF(ru.nickname, ''), NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(m.recipient_id AS TEXT)) AS target_name,
                   COALESCE(NULLIF(m.subject, ''), 'Личное сообщение') AS title,
                   m.content AS content,
                   0 AS is_hidden
            FROM messages m
            LEFT JOIN users su ON su.user_id = m.sender_id
            LEFT JOIN users ru ON ru.user_id = m.recipient_id

            UNION ALL

            SELECT oc.created_date AS created_date,
                   'org_chat' AS source,
                   oc.user_id AS actor_id,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(oc.user_id AS TEXT)) AS actor_name,
                   oc.org_id AS target_id,
                   COALESCE(o.name, CAST(oc.org_id AS TEXT)) AS target_name,
                   CASE WHEN oc.is_hidden = 1 THEN 'Скрытый чат' ELSE 'Чат организации' END AS title,
                   oc.content AS content,
                   oc.is_hidden AS is_hidden
            FROM organization_chats oc
            LEFT JOIN users u ON u.user_id = oc.user_id
            LEFT JOIN organizations o ON o.id = oc.org_id

            UNION ALL

            SELECT ed.created_date AS created_date,
                   'debate' AS source,
                   ed.user_id AS actor_id,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ed.user_id AS TEXT)) AS actor_name,
                   ed.election_id AS target_id,
                   'Выборы #' || CAST(ed.election_id AS TEXT) AS target_name,
                   'Дебаты' AS title,
                   ed.message AS content,
                   0 AS is_hidden
            FROM election_debates ed
            LEFT JOIN users u ON u.user_id = ed.user_id

            UNION ALL

            SELECT co.created_date AS created_date,
                   'corruption' AS source,
                   co.actor_id AS actor_id,
                   COALESCE(NULLIF(ua.nickname, ''), NULLIF(ua.full_name, ''), NULLIF(ua.username, ''), CAST(co.actor_id AS TEXT)) AS actor_name,
                   COALESCE(co.target_id, 0) AS target_id,
                   COALESCE(NULLIF(ut.nickname, ''), NULLIF(ut.full_name, ''), NULLIF(ut.username, ''), '—') AS target_name,
                   co.op_type AS title,
                   COALESCE(co.details, '') AS content,
                   1 AS is_hidden
            FROM corruption_ops co
            LEFT JOIN users ua ON ua.user_id = co.actor_id
            LEFT JOIN users ut ON ut.user_id = co.target_id

            ORDER BY created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_government_authority(self, user_id: int) -> Optional[str]:
        """Определить уровень полномочий игрока в госфинансах."""
        user = await self.get_user(user_id)
        gov = await self.get_government_system()
        if not user or not gov:
            return None

        if int(gov.get("current_leader_id") or 0) == int(user_id):
            return "president"

        assignment = None
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT authority
                    FROM government_authority_assignments
                    WHERE user_id = ? AND is_active = 1
                    LIMIT 1
                    """,
                    (int(user_id),),
                ) as cursor:
                    assignment = await cursor.fetchone()
        except sqlite3.OperationalError as exc:
            if "government_authority_assignments" not in str(exc).lower():
                raise
        if assignment:
            authority = str(assignment["authority"] or "").strip().lower()
            if authority in {"vice_president", "finance_minister", "minister"}:
                return authority

        role = (user.get("role") or "").strip().lower()
        if "президент" in role and "вице" not in role:
            user_org_name = (user.get("organization") or "").strip()
            gov_org = await self.get_government_organization()
            if gov_org and (
                str(gov_org.get("name") or "") == user_org_name
                or int(await self.get_user_organization_id(user_id) or 0) == int(gov_org.get("id") or 0)
            ):
                return "president"

        inferred: Optional[str] = None
        if "вице" in role and "президент" in role:
            inferred = "vice_president"
        elif "министр финансов" in role:
            inferred = "finance_minister"
        elif "министр" in role:
            inferred = "minister"

        if inferred:
            # Fallback для старых сохранений: если полномочия получены до появления таблицы назначений,
            # фиксируем их как активное назначение.
            now = datetime.now().isoformat()
            granted_by = int(gov.get("current_leader_id") or 0) or None
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        INSERT INTO government_authority_assignments
                        (user_id, authority, granted_by, granted_date, is_active)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(user_id) DO UPDATE SET
                            authority = excluded.authority,
                            granted_by = excluded.granted_by,
                            granted_date = excluded.granted_date,
                            is_active = 1
                        """,
                        (int(user_id), inferred, granted_by, now),
                    )
                    await db.commit()
            except sqlite3.OperationalError as exc:
                if "government_authority_assignments" not in str(exc).lower():
                    raise
            return inferred
        return None

    async def issue_state_funds(
        self,
        actor_id: int,
        target_id: int,
        amount: float,
        reason: str,
        is_shadow: bool = False,
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Выдать средства из госбюджета по привилегии роли."""
        authority = await self.get_government_authority(actor_id)
        if authority not in {"president", "vice_president", "finance_minister", "minister"}:
            return False, "Недостаточно полномочий для перевода средств.", {}

        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", {}
        if safe_amount > 10_000_000_000:
            return False, "Слишком большая сумма.", {}

        actor = await self.get_user(actor_id)
        target = await self.get_user(target_id)
        gov_org = await self.get_government_organization()
        if not actor or not target or not gov_org:
            return False, "Не удалось выполнить перевод: отсутствуют данные участника/госбюджета.", {}

        reason_text = " ".join((reason or "").strip().split())
        if not reason_text:
            reason_text = "Без комментария"

        now = datetime.now().isoformat()
        risk = min(100, max(5, int(safe_amount // 25_000)))
        if is_shadow:
            risk = min(100, risk + 20)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE id = ? LIMIT 1",
                (int(gov_org["id"]),),
            ) as cursor:
                org_row = await cursor.fetchone()
            if not org_row:
                await db.rollback()
                return False, "Государственный бюджет недоступен.", {}

            current_budget = round(float(org_row["budget"] or 0), 2)
            if current_budget < safe_amount:
                await db.rollback()
                return (
                    False,
                    f"Недостаточно средств в госбюджете. Доступно: ${current_budget:,.2f}.",
                    {"available_budget": current_budget},
                )

            new_budget = round(current_budget - safe_amount, 2)
            await db.execute(
                "UPDATE organizations SET budget = ? WHERE id = ?",
                (new_budget, int(org_row["id"])),
            )

            if is_shadow:
                await db.execute(
                    """
                    UPDATE users
                    SET shadow_balance = COALESCE(shadow_balance, 0) + ?,
                        corruption_score = COALESCE(corruption_score, 0) + ?
                    WHERE user_id = ?
                    """,
                    (safe_amount, max(1, risk // 8), target_id),
                )
            else:
                await db.execute(
                    "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?",
                    (safe_amount, target_id),
                )

            if is_shadow or safe_amount >= 150_000:
                await db.execute(
                    """
                    INSERT INTO corruption_ops
                    (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                    VALUES (?, ?, ?, ?, ?, 'logged', ?, ?)
                    """,
                    (
                        actor_id,
                        target_id,
                        "shadow_transfer" if is_shadow else "elite_transfer",
                        safe_amount,
                        risk,
                        reason_text,
                        now,
                    ),
                )
                await db.execute(
                    """
                    UPDATE users
                    SET corruption_score = COALESCE(corruption_score, 0) + ?
                    WHERE user_id = ?
                    """,
                    (max(1, risk // 10), actor_id),
                )

            cursor = await db.execute(
                """
                INSERT INTO privileged_transfers
                (actor_id, target_id, amount, reason, is_shadow, authority, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_id,
                    target_id,
                    safe_amount,
                    reason_text,
                    1 if is_shadow else 0,
                    authority,
                    now,
                ),
            )
            transfer_id = int(cursor.lastrowid or 0)
            await db.commit()

        details = {
            "transfer_id": transfer_id,
            "authority": authority,
            "amount": safe_amount,
            "is_shadow": is_shadow,
            "new_budget": new_budget,
        }
        return True, "Перевод выполнен.", details

    async def withdraw_state_funds(
        self,
        actor_id: int,
        amount: float,
        reason: str,
        is_shadow: bool = False,
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Вывести средства из бюджета на свой счет."""
        return await self.issue_state_funds(
            actor_id=actor_id,
            target_id=actor_id,
            amount=amount,
            reason=reason,
            is_shadow=is_shadow,
        )

    async def transfer_state_budget_to_organization(
        self,
        actor_id: int,
        target_org_id: int,
        amount: float,
        reason: str,
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Пополнить бюджет организации из госбюджета (только президент)."""
        authority = await self.get_government_authority(actor_id)
        if authority != "president":
            return False, "Пополнение организаций из госбюджета доступно только президенту.", {}

        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", {}
        if safe_amount > 10_000_000_000:
            return False, "Слишком большая сумма.", {}

        gov_org = await self.get_government_organization()
        target_org = await self.get_organization_by_id(int(target_org_id))
        if not gov_org or not target_org:
            return False, "Организация или госбюджет не найдены.", {}

        gov_org_id = int(gov_org.get("id") or 0)
        safe_target_org_id = int(target_org.get("id") or 0)
        if gov_org_id <= 0 or safe_target_org_id <= 0:
            return False, "Некорректная организация.", {}
        if gov_org_id == safe_target_org_id:
            return False, "Нельзя пополнить сам госбюджет через эту операцию.", {}

        clean_reason = " ".join((reason or "").strip().split()) or "Пополнение из госбюджета"
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE id = ? LIMIT 1",
                (gov_org_id,),
            ) as cursor:
                gov_row = await cursor.fetchone()
            async with db.execute(
                "SELECT id, budget, name FROM organizations WHERE id = ? LIMIT 1",
                (safe_target_org_id,),
            ) as cursor:
                target_row = await cursor.fetchone()
            if not gov_row or not target_row:
                await db.rollback()
                return False, "Организация или госбюджет недоступны.", {}

            gov_budget_before = round(float(gov_row["budget"] or 0), 2)
            if gov_budget_before < safe_amount:
                await db.rollback()
                return (
                    False,
                    f"Недостаточно средств в госбюджете. Доступно: ${gov_budget_before:,.2f}.",
                    {"available_budget": gov_budget_before},
                )

            target_budget_before = round(float(target_row["budget"] or 0), 2)
            gov_budget_after = round(gov_budget_before - safe_amount, 2)
            target_budget_after = round(target_budget_before + safe_amount, 2)

            await db.execute(
                "UPDATE organizations SET budget = ? WHERE id = ?",
                (gov_budget_after, gov_org_id),
            )
            await db.execute(
                "UPDATE organizations SET budget = ? WHERE id = ?",
                (target_budget_after, safe_target_org_id),
            )
            cursor = await db.execute(
                """
                INSERT INTO state_org_transfers
                (actor_id, target_org_id, amount, reason, created_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(actor_id), safe_target_org_id, safe_amount, clean_reason, now),
            )
            transfer_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=int(actor_id),
            activity_type="state_org_funding",
            details=f"Пополнена организация '{target_row['name']}' на ${safe_amount:,.2f}",
            value=safe_amount,
        )
        details = {
            "transfer_id": transfer_id,
            "authority": authority,
            "target_org_id": safe_target_org_id,
            "target_org_name": str(target_row["name"] or safe_target_org_id),
            "amount": safe_amount,
            "government_budget_after": gov_budget_after,
            "target_budget_after": target_budget_after,
        }
        return True, "Бюджет организации пополнен.", details

    async def get_recent_state_org_transfers(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT sot.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(sot.actor_id AS TEXT)) AS actor_name,
                   COALESCE(NULLIF(o.name, ''), CAST(sot.target_org_id AS TEXT)) AS target_org_name
            FROM state_org_transfers sot
            LEFT JOIN users u ON u.user_id = sot.actor_id
            LEFT JOIN organizations o ON o.id = sot.target_org_id
            ORDER BY sot.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def start_state_money_print_job(
        self,
        actor_id: int,
        amount: float,
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Запустить печать денег: требует время и производственные затраты."""
        authority = await self.get_government_authority(actor_id)
        if authority not in {"president", "finance_minister"}:
            return False, "Запуск печати денег доступен президенту или министру финансов.", {}

        safe_amount = round(float(amount or 0), 2)
        if safe_amount < 5_000:
            return False, "Минимальная сумма печати: $5,000.", {}
        if safe_amount > 100_000_000:
            return False, "Слишком большая сумма за один запуск (максимум $100,000,000).", {}

        production_cost = round(max(2_500.0, safe_amount * 0.08), 2)
        duration_minutes = max(5, min(360, int(round(5 + safe_amount / 250_000.0))))

        gov_org = await self.get_government_organization()
        if not gov_org:
            return False, "Государственный бюджет недоступен.", {}
        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return False, "Государственный бюджет недоступен.", {}

        now_dt = datetime.now()
        now = now_dt.isoformat()
        ready_at_dt = now_dt + timedelta(minutes=duration_minutes)
        ready_at = ready_at_dt.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT COUNT(*) FROM state_money_print_jobs WHERE status = 'printing'"
            ) as cursor:
                active_count_row = await cursor.fetchone()
            active_jobs = int((active_count_row[0] if active_count_row else 0) or 0)
            if active_jobs >= 5:
                await db.rollback()
                return False, "Очередь печати переполнена. Дождитесь завершения текущих запусков.", {}

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE id = ? LIMIT 1",
                (gov_org_id,),
            ) as cursor:
                gov_row = await cursor.fetchone()
            if not gov_row:
                await db.rollback()
                return False, "Государственный бюджет недоступен.", {}

            gov_budget_before = round(float(gov_row["budget"] or 0), 2)
            if gov_budget_before < production_cost:
                await db.rollback()
                return (
                    False,
                    f"Недостаточно средств для запуска печати. Нужно ${production_cost:,.2f}, доступно ${gov_budget_before:,.2f}.",
                    {"required_cost": production_cost, "available_budget": gov_budget_before},
                )

            gov_budget_after = round(gov_budget_before - production_cost, 2)
            await db.execute(
                "UPDATE organizations SET budget = ? WHERE id = ?",
                (gov_budget_after, gov_org_id),
            )
            cursor = await db.execute(
                """
                INSERT INTO state_money_print_jobs
                (actor_id, amount, production_cost, status, created_date, ready_at)
                VALUES (?, ?, ?, 'printing', ?, ?)
                """,
                (int(actor_id), safe_amount, production_cost, now, ready_at),
            )
            job_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=int(actor_id),
            activity_type="state_money_print_start",
            details=f"Запущена печать ${safe_amount:,.2f}, себестоимость ${production_cost:,.2f}",
            value=safe_amount,
        )
        details = {
            "job_id": job_id,
            "amount": safe_amount,
            "production_cost": production_cost,
            "duration_minutes": duration_minutes,
            "ready_at": ready_at,
            "government_budget_after": gov_budget_after,
            "authority": authority,
        }
        return True, "Печать денег запущена.", details

    async def claim_ready_state_money_print_jobs(
        self,
        actor_id: Optional[int] = None,
        enforce_authority: bool = False,
    ) -> Dict[str, Any]:
        """Зачислить в госбюджет завершенные по времени задания печати денег."""
        if enforce_authority:
            if actor_id is None:
                return {"claimed_jobs": 0, "minted_total": 0.0, "government_budget_after": 0.0, "error": "actor_required"}
            authority = await self.get_government_authority(int(actor_id))
            if authority not in {"president", "finance_minister"}:
                return {"claimed_jobs": 0, "minted_total": 0.0, "government_budget_after": 0.0, "error": "forbidden"}

        now = datetime.now().isoformat()
        gov_org = await self.get_government_organization()
        if not gov_org:
            return {"claimed_jobs": 0, "minted_total": 0.0, "government_budget_after": 0.0, "error": "no_gov_org"}
        gov_org_id = int(gov_org.get("id") or 0)
        if gov_org_id <= 0:
            return {"claimed_jobs": 0, "minted_total": 0.0, "government_budget_after": 0.0, "error": "no_gov_org"}

        claimed_jobs = 0
        minted_total = 0.0
        new_budget = round(float(gov_org.get("budget") or 0), 2)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT id, amount
                FROM state_money_print_jobs
                WHERE status = 'printing' AND ready_at <= ?
                ORDER BY ready_at ASC, id ASC
                """,
                (now,),
            ) as cursor:
                ready_jobs = await cursor.fetchall()

            if not ready_jobs:
                await db.rollback()
                return {
                    "claimed_jobs": 0,
                    "minted_total": 0.0,
                    "government_budget_after": new_budget,
                    "claimed_job_ids": [],
                }

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE id = ? LIMIT 1",
                (gov_org_id,),
            ) as cursor:
                gov_row = await cursor.fetchone()
            if not gov_row:
                await db.rollback()
                return {"claimed_jobs": 0, "minted_total": 0.0, "government_budget_after": 0.0, "error": "no_gov_org"}

            new_budget = round(float(gov_row["budget"] or 0), 2)
            claimed_ids: List[int] = []
            for row in ready_jobs:
                job_id = int(row["id"])
                amount_value = round(float(row["amount"] or 0), 2)
                if amount_value <= 0:
                    continue
                new_budget = round(new_budget + amount_value, 2)
                minted_total = round(minted_total + amount_value, 2)
                claimed_jobs += 1
                claimed_ids.append(job_id)

            if claimed_jobs > 0:
                await db.execute(
                    "UPDATE organizations SET budget = ? WHERE id = ?",
                    (new_budget, gov_org_id),
                )
                await db.execute(
                    """
                    UPDATE state_money_print_jobs
                    SET status = 'completed', completed_date = ?
                    WHERE status = 'printing' AND ready_at <= ?
                    """,
                    (now, now),
                )
                await db.commit()
            else:
                await db.rollback()

        if claimed_jobs > 0 and int(actor_id or 0) > 0:
            await self.log_player_activity(
                user_id=int(actor_id or 0),
                activity_type="state_money_print_claim",
                details=f"Завершено {claimed_jobs} запусков печати, зачислено ${minted_total:,.2f}",
                value=minted_total,
            )
        return {
            "claimed_jobs": claimed_jobs,
            "minted_total": minted_total,
            "government_budget_after": new_budget,
            "claimed_job_ids": claimed_ids if claimed_jobs > 0 else [],
        }

    async def get_recent_state_money_print_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT smpj.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(smpj.actor_id AS TEXT)) AS actor_name
            FROM state_money_print_jobs smpj
            LEFT JOIN users u ON u.user_id = smpj.actor_id
            ORDER BY smpj.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_recent_privileged_transfers(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Получить последние привилегированные переводы."""
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT pt.*,
                   COALESCE(NULLIF(a.full_name, ''), NULLIF(a.username, ''), CAST(pt.actor_id AS TEXT)) AS actor_name,
                   COALESCE(NULLIF(t.full_name, ''), NULLIF(t.username, ''), CAST(pt.target_id AS TEXT)) AS target_name
            FROM privileged_transfers pt
            LEFT JOIN users a ON a.user_id = pt.actor_id
            LEFT JOIN users t ON t.user_id = pt.target_id
            ORDER BY pt.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_recent_corruption_ops(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Получить последние коррупционные операции."""
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT co.*,
                   COALESCE(NULLIF(a.full_name, ''), NULLIF(a.username, ''), CAST(co.actor_id AS TEXT)) AS actor_name,
                   COALESCE(NULLIF(t.full_name, ''), NULLIF(t.username, ''), CAST(co.target_id AS TEXT)) AS target_name
            FROM corruption_ops co
            LEFT JOIN users a ON a.user_id = co.actor_id
            LEFT JOIN users t ON t.user_id = co.target_id
            ORDER BY co.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_daily_tax_invoices(self, cycle_date: Optional[str] = None) -> Dict[str, Any]:
        """Создать ежедневные счета налогов (без автосписания)."""
        now_dt = datetime.now()
        now_iso = now_dt.isoformat()
        cycle = (cycle_date or now_dt.date().isoformat()).strip()

        processed = 0
        created = 0
        total_due = 0.0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT user_id, balance, tax_debt, shadow_balance, citizen_job, citizen_salary, role
                FROM users
                ORDER BY user_id ASC
                """
            ) as cursor:
                users = await cursor.fetchall()

            async with db.execute("SELECT current_leader_id FROM government_system LIMIT 1") as cursor:
                gov_row = await cursor.fetchone()
                current_leader_id = int((gov_row[0] if gov_row else 0) or 0)

            property_values: Dict[int, float] = {}
            async with db.execute(
                """
                SELECT po.owner_id AS user_id, COALESCE(SUM(COALESCE(p.price, 0)), 0) AS total_value
                FROM property_ownership po
                JOIN properties p ON p.id = po.property_id
                GROUP BY po.owner_id
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    property_values[int(row["user_id"] or 0)] = float(row["total_value"] or 0.0)

            business_budgets: Dict[int, float] = {}
            async with db.execute(
                """
                SELECT owner_id AS user_id, COALESCE(SUM(COALESCE(budget, 0)), 0) AS total_budget
                FROM businesses
                WHERE status = 'active'
                GROUP BY owner_id
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    business_budgets[int(row["user_id"] or 0)] = float(row["total_budget"] or 0.0)

            private_org_budgets: Dict[int, float] = {}
            async with db.execute(
                """
                SELECT leader_id AS user_id, COALESCE(SUM(COALESCE(budget, 0)), 0) AS total_budget
                FROM private_orgs
                WHERE status = 'active'
                GROUP BY leader_id
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    private_org_budgets[int(row["user_id"] or 0)] = float(row["total_budget"] or 0.0)

            for user in users:
                processed += 1
                user_id = int(user["user_id"] or 0)
                if user_id <= 0:
                    continue

                balance = float(user["balance"] or 0.0)
                debt = float(user["tax_debt"] or 0.0)
                role_lc = str(user["role"] or "").strip().lower()
                is_president_role = "президент" in role_lc and "вице" not in role_lc
                is_president = bool(user_id == current_leader_id or is_president_role)
                if is_president:
                    await db.execute(
                        """
                        UPDATE daily_tax_invoices
                        SET status = 'paid', paid_total = 0, paid_date = ?, notified_at = COALESCE(notified_at, ?)
                        WHERE user_id = ? AND cycle_date = ? AND status = 'pending'
                        """,
                        (now_iso, now_iso, user_id, cycle),
                    )
                    continue

                living_tax = 5000.0
                has_job = bool(str(user["citizen_job"] or "").strip())
                work_salary = float(user["citizen_salary"] or 0.0)
                if has_job and work_salary <= 0:
                    work_salary = 220.0
                work_tax = round(max(300.0, work_salary * 0.35), 2) if has_job else 0.0

                property_total = max(0.0, float(property_values.get(user_id, 0.0)))
                business_total = max(0.0, float(business_budgets.get(user_id, 0.0)))
                private_org_total = max(0.0, float(private_org_budgets.get(user_id, 0.0)))

                property_tax = round(property_total * 0.0006, 2)
                business_tax = round(business_total * 0.0018, 2)
                private_org_tax = round(private_org_total * 0.0015, 2)

                citizen_tax = round(living_tax + work_tax + property_tax + business_tax + private_org_tax, 2)
                debt_interest = round(max(0.0, debt * 0.03), 2)
                scheduled_payment = round(min(max(0.0, debt * 0.12), max(0.0, balance * 0.25)), 2)
                total = round(citizen_tax + debt_interest + scheduled_payment, 2)
                if total <= 0:
                    continue

                cursor = await db.execute(
                    """
                    INSERT OR IGNORE INTO daily_tax_invoices
                    (user_id, cycle_date, living_tax, work_tax, property_tax, business_tax, private_org_tax, citizen_tax, debt_interest, scheduled_payment, total_due, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        user_id,
                        cycle,
                        living_tax,
                        work_tax,
                        property_tax,
                        business_tax,
                        private_org_tax,
                        citizen_tax,
                        debt_interest,
                        scheduled_payment,
                        total,
                        now_iso,
                    ),
                )
                if int(cursor.rowcount or 0) > 0:
                    created += 1
                    total_due = round(total_due + total, 2)

            async with db.execute(
                "SELECT COUNT(*) FROM daily_tax_invoices WHERE cycle_date = ? AND status = 'pending'",
                (cycle,),
            ) as cursor:
                row = await cursor.fetchone()
                pending_count = int((row[0] if row else 0) or 0)

            await db.commit()

        return {
            "cycle_date": cycle,
            "processed_users": processed,
            "created_invoices": created,
            "pending_invoices": pending_count,
            "total_due_created": total_due,
        }

    async def settle_overdue_daily_tax_invoices(self, cycle_date: Optional[str] = None) -> Dict[str, Any]:
        """Перевести неоплаченные счета прошлых дней в налоговый долг."""
        now_dt = datetime.now()
        now_iso = now_dt.isoformat()
        cycle = (cycle_date or now_dt.date().isoformat()).strip()

        debtors = 0
        total_new_debt = 0.0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT dti.id, dti.user_id, dti.cycle_date, dti.citizen_tax, dti.debt_interest,
                       dti.living_tax, dti.work_tax, dti.property_tax, dti.business_tax, dti.private_org_tax,
                       u.tax_debt, u.reputation, u.role
                FROM daily_tax_invoices dti
                JOIN users u ON u.user_id = dti.user_id
                WHERE dti.status = 'pending' AND dti.cycle_date < ?
                ORDER BY dti.cycle_date ASC, dti.id ASC
                """,
                (cycle,),
            ) as cursor:
                overdue = await cursor.fetchall()

            async with db.execute("SELECT current_leader_id FROM government_system LIMIT 1") as cursor:
                gov_row = await cursor.fetchone()
                current_leader_id = int((gov_row[0] if gov_row else 0) or 0)

            for row in overdue:
                invoice_id = int(row["id"] or 0)
                user_id = int(row["user_id"] or 0)
                if invoice_id <= 0 or user_id <= 0:
                    continue

                role_lc = str(row["role"] or "").strip().lower()
                is_president_role = "президент" in role_lc and "вице" not in role_lc
                is_president = bool(user_id == current_leader_id or is_president_role)
                if is_president:
                    await db.execute(
                        "UPDATE daily_tax_invoices SET status = 'paid', paid_total = 0, paid_date = ? WHERE id = ?",
                        (now_iso, invoice_id),
                    )
                    continue

                living_tax = round(float(row["living_tax"] or 0), 2)
                work_tax = round(float(row["work_tax"] or 0), 2)
                property_tax = round(float(row["property_tax"] or 0), 2)
                business_tax = round(float(row["business_tax"] or 0), 2)
                private_org_tax = round(float(row["private_org_tax"] or 0), 2)
                citizen_tax_total = round(living_tax + work_tax + property_tax + business_tax + private_org_tax, 2)
                if citizen_tax_total <= 0:
                    citizen_tax_total = round(float(row["citizen_tax"] or 0), 2)
                citizen_tax_log = round(living_tax + work_tax, 2) if (living_tax > 0 or work_tax > 0) else citizen_tax_total
                debt_interest = round(float(row["debt_interest"] or 0), 2)
                debt_add = round(max(0.0, citizen_tax_total + debt_interest), 2)
                if debt_add <= 0:
                    await db.execute(
                        "UPDATE daily_tax_invoices SET status = 'debt', paid_total = 0, paid_date = ? WHERE id = ?",
                        (now_iso, invoice_id),
                    )
                    continue

                debt_before = round(float(row["tax_debt"] or 0), 2)
                reputation_before = float(row["reputation"] or 50.0)
                debt_after = round(max(0.0, debt_before + debt_add), 2)
                reputation_after = round(max(0.0, reputation_before - min(4.0, debt_add / 5000.0)), 2)

                # Получаем current total_tax_paid, чтобы обновить его
                async with db.execute(
                    "SELECT total_tax_paid FROM users WHERE user_id = ? LIMIT 1",
                    (user_id,),
                ) as cursor_tax:
                    user_tax_row = await cursor_tax.fetchone()
                    total_tax_paid_before = round(float((user_tax_row[0] if user_tax_row else 0) or 0), 2)
                
                # Include the debt_add in total_tax_paid to track all taxes charged (paid + unpaid)
                total_tax_paid_after = round(total_tax_paid_before + debt_add, 2)

                if debt_after >= 200_000:
                    ban_until = (now_dt + timedelta(hours=12)).isoformat()
                    await db.execute(
                        """
                        UPDATE users
                        SET tax_debt = ?, reputation = ?, action_banned_until = ?, total_tax_paid = ?
                        WHERE user_id = ?
                        """,
                        (debt_after, reputation_after, ban_until, total_tax_paid_after, user_id),
                    )
                else:
                    await db.execute(
                        "UPDATE users SET tax_debt = ?, reputation = ?, total_tax_paid = ? WHERE user_id = ?",
                        (debt_after, reputation_after, total_tax_paid_after, user_id),
                    )

                await db.execute(
                    """
                    UPDATE daily_tax_invoices
                    SET status = 'debt', paid_total = 0, paid_date = ?
                    WHERE id = ?
                    """,
                    (now_iso, invoice_id),
                )
                await db.execute(
                    """
                    INSERT INTO tax_logs
                    (user_id, cycle_date, citizen_tax, property_tax, business_tax, org_tax, paid_total, debt_total, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        user_id,
                        str(row["cycle_date"] or cycle),
                        citizen_tax_log,
                        property_tax,
                        business_tax,
                        private_org_tax,
                        debt_after,
                        now_iso,
                    ),
                )

                debtors += 1
                total_new_debt = round(total_new_debt + debt_add, 2)

            await db.commit()

        return {
            "cycle_date": cycle,
            "debtors": debtors,
            "total_new_debt": total_new_debt,
        }

    async def list_pending_daily_tax_invoices(
        self,
        cycle_date: Optional[str] = None,
        limit: int = 3000,
        only_not_notified: bool = False,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 3000), 20_000))
        cycle = (cycle_date or datetime.now().date().isoformat()).strip()

        where = ["dti.cycle_date = ?", "dti.status = 'pending'"]
        params: List[Any] = [cycle]
        if only_not_notified:
            where.append("dti.notified_at IS NULL")
        params.append(safe_limit)

        query = f"""
            SELECT dti.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(dti.user_id AS TEXT)) AS user_name
            FROM daily_tax_invoices dti
            LEFT JOIN users u ON u.user_id = dti.user_id
            WHERE {' AND '.join(where)}
            ORDER BY dti.user_id ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_daily_tax_invoice_notified(self, user_id: int, cycle_date: str) -> bool:
        safe_cycle = (cycle_date or "").strip()
        if int(user_id or 0) <= 0 or not safe_cycle:
            return False
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE daily_tax_invoices
                SET notified_at = COALESCE(notified_at, ?)
                WHERE user_id = ? AND cycle_date = ? AND status = 'pending'
                """,
                (now, int(user_id), safe_cycle),
            )
            await db.commit()
        return True

    async def get_pending_daily_tax_invoice(
        self,
        user_id: int,
        cycle_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return None
        safe_cycle = (cycle_date or "").strip()

        where = ["user_id = ?", "status = 'pending'"]
        params: List[Any] = [safe_user_id]
        if safe_cycle:
            where.append("cycle_date = ?")
            params.append(safe_cycle)

        query = f"""
            SELECT *
            FROM daily_tax_invoices
            WHERE {' AND '.join(where)}
            ORDER BY cycle_date ASC, id ASC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def pay_daily_tax_invoice(
        self,
        user_id: int,
        cycle_date: Optional[str] = None,
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Оплатить ежедневный налоговый счет игрока."""
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return False, "Некорректный пользователь.", {}

        now = datetime.now().isoformat()
        safe_cycle = (cycle_date or "").strip()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            if safe_cycle:
                async with db.execute(
                    """
                    SELECT *
                    FROM daily_tax_invoices
                    WHERE user_id = ? AND cycle_date = ? AND status = 'pending'
                    LIMIT 1
                    """,
                    (safe_user_id, safe_cycle),
                ) as cursor:
                    invoice = await cursor.fetchone()
            else:
                async with db.execute(
                    """
                    SELECT *
                    FROM daily_tax_invoices
                    WHERE user_id = ? AND status = 'pending'
                    ORDER BY cycle_date ASC, id ASC
                    LIMIT 1
                    """,
                    (safe_user_id,),
                ) as cursor:
                    invoice = await cursor.fetchone()

            if not invoice:
                await db.rollback()
                return False, "Нет активного ежедневного налога для оплаты.", {}

            async with db.execute(
                "SELECT balance, tax_debt, total_tax_paid, reputation, role FROM users WHERE user_id = ? LIMIT 1",
                (safe_user_id,),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", {}

            async with db.execute("SELECT current_leader_id FROM government_system LIMIT 1") as cursor:
                gov_state_row = await cursor.fetchone()
                current_leader_id = int((gov_state_row[0] if gov_state_row else 0) or 0)
            role_lc = str(user["role"] or "").strip().lower()
            is_president_role = "президент" in role_lc and "вице" not in role_lc
            is_president = bool(safe_user_id == current_leader_id or is_president_role)

            due_total = round(float(invoice["total_due"] or 0), 2)
            if is_president:
                await db.execute(
                    "UPDATE daily_tax_invoices SET status = 'paid', paid_total = 0, paid_date = ? WHERE id = ?",
                    (now, int(invoice["id"])),
                )
                await db.commit()
                return True, "Президент освобожден от ежедневного налога.", {
                    "invoice_id": int(invoice["id"] or 0),
                    "cycle_date": str(invoice["cycle_date"] or ""),
                    "paid_total": 0.0,
                    "balance_after": round(float(user["balance"] or 0), 2),
                    "tax_debt_after": round(float(user["tax_debt"] or 0), 2),
                    "government_budget_after": None,
                    "president_exempt": True,
                }

            if due_total <= 0:
                await db.execute(
                    "UPDATE daily_tax_invoices SET status = 'paid', paid_total = 0, paid_date = ? WHERE id = ?",
                    (now, int(invoice["id"])),
                )
                await db.commit()
                return True, "Счет закрыт (сумма к оплате = 0).", {"paid_total": 0.0}

            balance_before = round(float(user["balance"] or 0), 2)
            if balance_before < due_total:
                await db.rollback()
                return (
                    False,
                    f"Недостаточно средств. Нужно ${due_total:,.2f}, доступно ${balance_before:,.2f}.",
                    {"required": due_total, "balance": balance_before},
                )

            debt_before = round(float(user["tax_debt"] or 0), 2)
            total_tax_paid_before = round(float(user["total_tax_paid"] or 0), 2)
            reputation_before = float(user["reputation"] or 50.0)

            living_tax = round(float(invoice["living_tax"] or 0), 2)
            work_tax = round(float(invoice["work_tax"] or 0), 2)
            property_tax = round(float(invoice["property_tax"] or 0), 2)
            business_tax = round(float(invoice["business_tax"] or 0), 2)
            private_org_tax = round(float(invoice["private_org_tax"] or 0), 2)
            citizen_tax = round(float(invoice["citizen_tax"] or 0), 2)
            citizen_component = round(living_tax + work_tax, 2) if (living_tax > 0 or work_tax > 0) else citizen_tax
            tax_components_total = round(citizen_component + property_tax + business_tax + private_org_tax, 2)
            if tax_components_total <= 0:
                tax_components_total = citizen_tax

            debt_interest = round(float(invoice["debt_interest"] or 0), 2)
            scheduled_payment = round(float(invoice["scheduled_payment"] or 0), 2)

            new_balance = round(balance_before - due_total, 2)
            debt_after = round(max(0.0, debt_before + tax_components_total + debt_interest - scheduled_payment), 2)
            total_tax_paid_after = round(total_tax_paid_before + due_total, 2)
            reputation_after = reputation_before
            if debt_before > 0 and debt_after < debt_before:
                reputation_after = round(min(100.0, reputation_before + 0.2), 2)

            await db.execute(
                """
                UPDATE users
                SET balance = ?, tax_debt = ?, total_tax_paid = ?, reputation = ?
                WHERE user_id = ?
                """,
                (new_balance, debt_after, total_tax_paid_after, reputation_after, safe_user_id),
            )
            await db.execute(
                """
                UPDATE daily_tax_invoices
                SET status = 'paid', paid_total = ?, paid_date = ?
                WHERE id = ?
                """,
                (due_total, now, int(invoice["id"])),
            )

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE name = 'Правительство' LIMIT 1"
            ) as cursor:
                gov = await cursor.fetchone()
            government_budget_after = None
            if gov:
                government_budget_after = round(float(gov["budget"] or 0) + due_total, 2)
                await db.execute(
                    "UPDATE organizations SET budget = ? WHERE id = ?",
                    (government_budget_after, int(gov["id"])),
                )

            await db.execute(
                """
                INSERT INTO tax_logs
                (user_id, cycle_date, citizen_tax, property_tax, business_tax, org_tax, paid_total, debt_total, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_user_id,
                    str(invoice["cycle_date"] or ""),
                    citizen_component,
                    property_tax,
                    business_tax,
                    private_org_tax,
                    due_total,
                    debt_after,
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=safe_user_id,
            activity_type="daily_tax_paid",
            details=f"Оплачен ежедневный налог за {invoice['cycle_date']} на ${due_total:,.2f}",
            value=due_total,
        )
        details = {
            "invoice_id": int(invoice["id"] or 0),
            "cycle_date": str(invoice["cycle_date"] or ""),
            "paid_total": due_total,
            "balance_after": new_balance,
            "tax_debt_after": debt_after,
            "government_budget_after": government_budget_after,
            "living_tax": living_tax,
            "work_tax": work_tax,
            "property_tax": property_tax,
            "business_tax": business_tax,
            "private_org_tax": private_org_tax,
        }
        return True, "Ежедневный налог оплачен.", details

    async def get_user_daily_tax_status(self, user_id: int) -> Dict[str, Any]:
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return {"pending": None, "latest": None}

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM daily_tax_invoices
                WHERE user_id = ? AND status = 'pending'
                ORDER BY cycle_date ASC, id ASC
                LIMIT 1
                """,
                (safe_user_id,),
            ) as cursor:
                pending = await cursor.fetchone()

            async with db.execute(
                """
                SELECT *
                FROM daily_tax_invoices
                WHERE user_id = ?
                ORDER BY cycle_date DESC, id DESC
                LIMIT 1
                """,
                (safe_user_id,),
            ) as cursor:
                latest = await cursor.fetchone()

        return {
            "pending": dict(pending) if pending else None,
            "latest": dict(latest) if latest else None,
        }

    async def get_user_total_tax_charged(self, user_id: int) -> float:
        """
        Получить общую сумму начисленных налогов (включая уже уплаченные и в долг).
        Рассчитывается из таблицы tax_logs.
        """
        safe_user_id = int(user_id or 0)
        if safe_user_id <= 0:
            return 0.0
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """
                    SELECT COALESCE(SUM(
                        COALESCE(citizen_tax, 0) + 
                        COALESCE(property_tax, 0) + 
                        COALESCE(business_tax, 0) + 
                        COALESCE(org_tax, 0)
                    ), 0.0) as total_charged
                    FROM tax_logs
                    WHERE user_id = ?
                    """,
                    (safe_user_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return round(float(row[0] or 0.0), 2)
        except Exception:
            pass
        
        return 0.0

    async def run_advanced_tax_cycle(self, cycle_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Налоговый цикл нового формата:
        - просроченные счета прошлых дней переводятся в долг;
        - на текущий день создаются счета для ручной оплаты кнопкой.
        """
        now_dt = datetime.now()
        cycle_date = (cycle_date or now_dt.date().isoformat()).strip()

        overdue_summary = await self.settle_overdue_daily_tax_invoices(cycle_date=cycle_date)
        invoices_summary = await self.create_daily_tax_invoices(cycle_date=cycle_date)

        return {
            "processed_users": int(invoices_summary.get("processed_users") or 0),
            "debtors": int(overdue_summary.get("debtors") or 0),
            "total_collected": 0.0,
            "total_new_debt": round(float(overdue_summary.get("total_new_debt") or 0), 2),
            "created_invoices": int(invoices_summary.get("created_invoices") or 0),
            "pending_invoices": int(invoices_summary.get("pending_invoices") or 0),
            "total_due_created": round(float(invoices_summary.get("total_due_created") or 0), 2),
            "cycle_date": cycle_date,
        }

    async def bootstrap_world_data(self) -> None:
        """Заполнить стартовые данные мира (идемпотентно)."""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT id FROM government_system ORDER BY id DESC LIMIT 1") as cursor:
                gov_row = await cursor.fetchone()
            if not gov_row:
                await db.execute(
                    """
                    INSERT INTO government_system
                    (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                    VALUES ('democracy', NULL, ?, ?, 100, 0, 60)
                    """,
                    (now, now),
                )
            properties_seed = [
                ("ЖК Сапфир Плаза", 220_000, 3_200, "Ташкент, Юнусабад", "residential", 180),
                ("БЦ Capital Tower", 780_000, 11_500, "Ташкент, Мирабад", "commercial", 460),
                ("Технопарк Восток", 1_450_000, 20_000, "Ташкент, Сергелий", "industrial", 950),
                ("Старый завод #14", 980_000, 13_500, "Самарканд, Промзона", "industrial", 820),
                ("Исторический особняк", 620_000, 8_400, "Бухара, Центр", "residential", 370),
                ("Логистический хаб Север", 1_850_000, 26_000, "Ташкент, Чиланзар", "industrial", 1_250),
                ("Торговая галерея Meridian", 1_120_000, 16_500, "Ташкент, Центр", "commercial", 910),
                ("Гостевой комплекс RiverLine", 690_000, 9_800, "Наманган", "commercial", 520),
                ("Микрорайонный ТЦ Гранит", 540_000, 7_200, "Андижан", "commercial", 390),
                ("Башня Horizon One", 2_600_000, 34_000, "Ташкент-Сити", "commercial", 1_700),
            ]
            for name, price, rent, location, category, maintenance in properties_seed:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO properties
                    (name, price, rent, location, status, category, maintenance_daily, condition)
                    VALUES (?, ?, ?, ?, 'available', ?, ?, 100)
                    """,
                    (name, float(price), float(rent), location, category, float(maintenance)),
                )

            education_seed = [
                ("Базовая грамотность управления", "Основа экономики и госуправления для новичков.", 5, 2_500, 1, 0.0),
                ("Финансовая аналитика", "Практика бюджета, налоги и контроль расходов.", 7, 8_000, 1, 20.0),
                ("Юридический интенсив", "Законодательный процесс и правоприменение.", 10, 14_000, 2, 30.0),
                ("Государственный менеджмент", "Кадровая политика и управление организациями.", 14, 21_000, 3, 40.0),
                ("Магистратура: Геоэкономика", "Сложные макромодели и кризисное управление.", 18, 34_000, 4, 55.0),
            ]
            for name, description, duration_days, tuition_fee, min_education, min_reputation in education_seed:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO education_programs
                    (name, description, duration_days, tuition_fee, min_education, min_reputation, active, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        name,
                        description,
                        int(duration_days),
                        float(tuition_fee),
                        int(min_education),
                        float(min_reputation),
                        now,
                    ),
                )

            casino_seed = [
                ("ГосКазино Республики", None, "state", 500, 900_000, 0.028, 8_000_000),
                ("Ночной Клуб Рулетка", None, "state", 200, 350_000, 0.033, 4_000_000),
            ]
            for name, owner_id, casino_type, min_bet, max_bet, house_edge, balance in casino_seed:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO casinos
                    (name, owner_id, casino_type, status, min_bet, max_bet, house_edge, balance, created_date)
                    VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        owner_id,
                        casino_type,
                        float(min_bet),
                        float(max_bet),
                        float(house_edge),
                        float(balance),
                        now,
                    ),
                )

            async with db.execute("SELECT COUNT(*) FROM government_rules") as cursor:
                rules_count_row = await cursor.fetchone()
            if int((rules_count_row[0] if rules_count_row else 0) or 0) == 0:
                default_rules = [
                    ("Соблюдать налоговую дисциплину для всех активов и бизнесов.", 10_000),
                    ("Запрещены нападения на госслужащих при исполнении.", 15_000),
                    ("Незаконные обороты контрабанды и наркотиков караются усиленным штрафом.", 25_000),
                    ("Гос. средства можно распределять только по служебным основаниям.", 30_000),
                    ("Фальсификация выборов и дебатов запрещена.", 18_000),
                ]
                for idx, (rule_text, penalty) in enumerate(default_rules, start=1):
                    await db.execute(
                        """
                        INSERT INTO government_rules
                        (rule_number, rule_text, created_by, created_date, status, violation_penalty, violations_count)
                        VALUES (?, ?, 0, ?, 'active', ?, 0)
                        """,
                        (f"LAW-{idx:03d}", rule_text, now, float(penalty)),
                    )
            await db.commit()

    async def log_player_activity(
        self,
        user_id: int,
        activity_type: str,
        details: str = "",
        value: float = 0.0,
    ) -> bool:
        now = datetime.now().isoformat()
        safe_activity = (activity_type or "").strip().lower()[:64]
        safe_details = (details or "").strip()[:600]
        if not safe_activity:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO player_activity_log (user_id, activity_type, details, value, created_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), safe_activity, safe_details, float(value or 0), now),
            )
            await db.commit()
        return True

    async def create_media_news(
        self,
        title: str,
        body: str,
        source_user_id: Optional[int] = None,
        severity: str = "normal",
    ) -> int:
        now = datetime.now().isoformat()
        safe_title = " ".join((title or "").strip().split())[:160]
        safe_body = " ".join((body or "").strip().split())[:1200]
        safe_severity = (severity or "normal").strip().lower()
        if safe_severity not in {"normal", "high", "critical", "hot"}:
            safe_severity = "normal"
        if not safe_title or not safe_body:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO media_news (title, body, source_user_id, severity, created_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (safe_title, safe_body, source_user_id, safe_severity, now),
            )
            news_id = int(cursor.lastrowid or 0)
            await db.commit()
            return news_id

    async def get_latest_media_news(
        self,
        limit: int = 20,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        safe_severity = (severity or "").strip().lower()
        if safe_severity not in {"normal", "high", "critical", "hot"}:
            safe_severity = ""

        where = "WHERE mn.severity = ?" if safe_severity else ""
        query = f"""
            SELECT mn.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(mn.source_user_id AS TEXT)) AS source_name
            FROM media_news mn
            LEFT JOIN users u ON u.user_id = mn.source_user_id
            {where}
            ORDER BY mn.created_date DESC
            LIMIT ?
        """
        params: tuple[Any, ...]
        if safe_severity:
            params = (safe_severity, safe_limit)
        else:
            params = (safe_limit,)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_media_news_digest(self, hours: int = 24) -> Dict[str, Any]:
        safe_hours = max(1, min(int(hours or 24), 168))
        since = (datetime.now() - timedelta(hours=safe_hours)).isoformat()

        payload: Dict[str, Any] = {
            "hours": safe_hours,
            "total": 0,
            "normal": 0,
            "high": 0,
            "critical": 0,
            "hot": 0,
            "top_sources": [],
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                """
                SELECT COALESCE(severity, 'normal') AS severity, COUNT(*) AS c
                FROM media_news
                WHERE created_date >= ?
                GROUP BY COALESCE(severity, 'normal')
                """,
                (since,),
            ) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    sev = str(row["severity"] or "normal").strip().lower()
                    cnt = int(row["c"] or 0)
                    if sev in {"normal", "high", "critical", "hot"}:
                        payload[sev] = cnt
                        payload["total"] = int(payload["total"]) + cnt

            async with db.execute(
                """
                SELECT COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(mn.source_user_id AS TEXT), 'Система') AS source_name,
                       COUNT(*) AS c
                FROM media_news mn
                LEFT JOIN users u ON u.user_id = mn.source_user_id
                WHERE mn.created_date >= ?
                GROUP BY source_name
                ORDER BY c DESC, source_name ASC
                LIMIT 5
                """,
                (since,),
            ) as cur:
                rows = await cur.fetchall()
                payload["top_sources"] = [
                    {"source_name": str(r["source_name"] or "Система"), "count": int(r["c"] or 0)}
                    for r in rows
                ]

        return payload

    async def generate_hourly_news(self) -> Optional[Dict[str, Any]]:
        now_dt = datetime.now()
        since = (now_dt - timedelta(hours=2)).isoformat()
        query = """
            SELECT pal.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(pal.user_id AS TEXT)) AS actor_name
            FROM player_activity_log pal
            LEFT JOIN users u ON u.user_id = pal.user_id
            WHERE pal.created_date >= ?
            ORDER BY pal.value DESC, pal.created_date DESC
            LIMIT 20
        """

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (since,)) as cursor:
                rows = await cursor.fetchall()

        title = "Экономический бюллетень часа"
        body = "Крупных событий не зафиксировано. Игроки укрепляют позиции и готовятся к новым шагам."
        source_user_id: Optional[int] = None
        severity = "normal"

        if rows:
            row = dict(random.choice(rows))
            actor = row.get("actor_name") or f"Игрок {row.get('user_id')}"
            details = (row.get("details") or "").strip()
            activity = str(row.get("activity_type") or "").strip().lower()
            value = float(row.get("value") or 0)
            source_user_id = int(row.get("user_id") or 0)

            title_map = {
                "property_purchase": "Сделка с недвижимостью потрясла рынок",
                "business_open": "Новый бизнес меняет баланс рынка",
                "private_org_open": "Появилась новая частная организация",
                "casino_win": "Громкий выигрыш в казино",
                "side_hustle_legal": "Горожане наращивают легальные подработки",
                "side_hustle_illegal": "Теневой сектор снова активен",
                "education_complete": "Игрок завершил престижное обучение",
                "gang_create": "В городе создана новая банда",
                "cartel_operation": "Картельная активность набирает обороты",
            }
            title = title_map.get(activity, "Новость часа: резонансное действие игрока")
            body = f"{actor}: {details or 'зафиксировано значимое действие'}."
            if value >= 400_000:
                severity = "critical"
            elif value >= 120_000:
                severity = "high"
            elif value >= 30_000:
                severity = "hot"

        news_id = await self.create_media_news(title=title, body=body, source_user_id=source_user_id, severity=severity)
        if news_id <= 0:
            return None
        rows = await self.get_latest_media_news(limit=1)
        return rows[0] if rows else None

    async def get_state_flag(self) -> Dict[str, Any]:
        gov = await self.get_government_system() or {}
        return {
            "state_flag_text": (gov.get("state_flag_text") or "").strip(),
            "state_flag_file_id": (gov.get("state_flag_file_id") or "").strip(),
        }

    async def set_state_flag(
        self,
        actor_id: int,
        flag_text: Optional[str] = None,
        flag_file_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        authority = await self.get_government_authority(actor_id)
        if authority != "president":
            return False, "Только президент может менять государственный флаг."

        updates: Dict[str, Any] = {"last_changed": datetime.now().isoformat()}
        if flag_text is not None:
            updates["state_flag_text"] = (flag_text or "").strip()[:180]
        if flag_file_id is not None:
            updates["state_flag_file_id"] = (flag_file_id or "").strip()[:300]
        if len(updates) == 1:
            return False, "Нет данных для обновления флага."

        await self.update_government_system(**updates)
        await self.log_player_activity(
            user_id=actor_id,
            activity_type="flag_update",
            details="Президент обновил государственный флаг.",
            value=10_000,
        )
        return True, "Государственный флаг обновлен."

    async def list_government_rules(
        self,
        include_archived: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 100), 500))
        where_clause = "" if include_archived else "WHERE status != 'archived'"
        query = f"""
            SELECT *
            FROM government_rules
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_government_rule(
        self,
        actor_id: int,
        rule_text: str,
        penalty: float = 1000.0,
    ) -> tuple[bool, str, Optional[int]]:
        authority = await self.get_government_authority(actor_id)
        if authority != "president":
            return False, "Только президент может принимать законы.", None

        clean_text = " ".join((rule_text or "").strip().split())
        if len(clean_text) < 10:
            return False, "Текст закона слишком короткий (минимум 10 символов).", None
        if len(clean_text) > 800:
            return False, "Текст закона слишком длинный (максимум 800 символов).", None

        safe_penalty = max(100.0, min(float(penalty or 1000.0), 2_000_000.0))
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT MAX(id) FROM government_rules") as cursor:
                row = await cursor.fetchone()
            next_num = int((row[0] if row and row[0] is not None else 0) or 0) + 1
            rule_number = f"LAW-{next_num:03d}"
            cursor = await db.execute(
                """
                INSERT INTO government_rules
                (rule_number, rule_text, created_by, created_date, status, violation_penalty, violations_count)
                VALUES (?, ?, ?, ?, 'active', ?, 0)
                """,
                (rule_number, clean_text, actor_id, now, safe_penalty),
            )
            rule_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="law_created",
            details=f"Принят закон {rule_number}",
            value=safe_penalty,
        )
        return True, f"Закон {rule_number} принят.", rule_id

    async def edit_government_rule(
        self,
        actor_id: int,
        rule_id: int,
        rule_text: Optional[str] = None,
        penalty: Optional[float] = None,
        status: Optional[str] = None,
    ) -> tuple[bool, str]:
        authority = await self.get_government_authority(actor_id)
        if authority != "president":
            return False, "Только президент может редактировать законы."

        updates: Dict[str, Any] = {}
        if rule_text is not None:
            clean_text = " ".join((rule_text or "").strip().split())
            if len(clean_text) < 10:
                return False, "Текст закона слишком короткий."
            updates["rule_text"] = clean_text[:800]
        if penalty is not None:
            updates["violation_penalty"] = max(100.0, min(float(penalty), 2_000_000.0))
        if status is not None:
            safe_status = (status or "").strip().lower()
            if safe_status not in {"active", "suspended", "archived"}:
                return False, "Некорректный статус закона."
            updates["status"] = safe_status
        if not updates:
            return False, "Нет параметров для обновления закона."

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [int(rule_id)]
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM government_rules WHERE id = ?", (int(rule_id),)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False, "Закон не найден."
            await db.execute(f"UPDATE government_rules SET {set_clause} WHERE id = ?", values)
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="law_edited",
            details=f"Изменен закон #{int(rule_id)}",
            value=0,
        )
        return True, "Закон обновлен."

    async def list_properties(self, available_only: bool = False, limit: int = 100) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 100), 500))
        where = "WHERE po.owner_id IS NULL" if available_only else ""
        query = f"""
            SELECT p.*,
                   po.owner_id,
                   po.acquired_date,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(po.owner_id AS TEXT)) AS owner_name,
                   CASE WHEN b.id IS NULL THEN 0 ELSE 1 END AS has_business,
                   CASE WHEN porg.id IS NULL THEN 0 ELSE 1 END AS has_private_org
            FROM properties p
            LEFT JOIN property_ownership po ON po.property_id = p.id
            LEFT JOIN users u ON u.user_id = po.owner_id
            LEFT JOIN businesses b ON b.property_id = p.id AND b.status = 'active'
            LEFT JOIN private_orgs porg ON porg.property_id = p.id AND porg.status = 'active'
            {where}
            ORDER BY p.price ASC, p.id ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_properties(self, user_id: int) -> List[Dict[str, Any]]:
        query = """
            SELECT p.*,
                   po.acquired_date,
                   CASE WHEN b.id IS NULL THEN 0 ELSE 1 END AS has_business,
                   CASE WHEN porg.id IS NULL THEN 0 ELSE 1 END AS has_private_org
            FROM property_ownership po
            JOIN properties p ON p.id = po.property_id
            LEFT JOIN businesses b ON b.property_id = p.id AND b.status = 'active'
            LEFT JOIN private_orgs porg ON porg.property_id = p.id AND porg.status = 'active'
            WHERE po.owner_id = ?
            ORDER BY po.acquired_date DESC
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def buy_property(self, user_id: int, property_id: int) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            async with db.execute("SELECT * FROM properties WHERE id = ?", (int(property_id),)) as cursor:
                prop = await cursor.fetchone()
            if not prop:
                await db.rollback()
                return False, "Объект недвижимости не найден.", None

            async with db.execute(
                "SELECT owner_id FROM property_ownership WHERE property_id = ? LIMIT 1",
                (int(property_id),),
            ) as cursor:
                owner_row = await cursor.fetchone()
            if owner_row:
                await db.rollback()
                return False, "Этот объект уже куплен другим игроком.", None

            price = float(prop["price"] or 0)
            balance = float(user["balance"] or 0)
            if balance < price:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${price:,.2f}.", None

            new_balance = round(balance - price, 2)
            await db.execute(
                "UPDATE users SET balance = ?, property_owner = 1 WHERE user_id = ?",
                (new_balance, int(user_id)),
            )
            await db.execute(
                "INSERT INTO property_ownership (property_id, owner_id, acquired_date, last_rent_claimed) VALUES (?, ?, ?, ?)",
                (int(property_id), int(user_id), now, now),
            )
            await db.execute("UPDATE properties SET status = 'owned' WHERE id = ?", (int(property_id),))
            await db.commit()

        prop_data = dict(prop)
        await self.log_player_activity(
            user_id=user_id,
            activity_type="property_purchase",
            details=f"Куплена недвижимость: {prop_data.get('name')}",
            value=price,
        )
        return True, "Недвижимость успешно куплена.", {"property": prop_data, "new_balance": new_balance}

    async def get_business_by_id(self, business_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM businesses WHERE id = ?", (int(business_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_user_businesses(self, owner_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT b.*,
                       p.name AS property_name
                FROM businesses b
                LEFT JOIN properties p ON p.id = b.property_id
                WHERE b.owner_id = ?
                ORDER BY b.created_date DESC
                """,
                (int(owner_id),),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def check_and_set_user_cooldown(
        self,
        user_id: int,
        action_key: str,
        cooldown_minutes: int,
    ) -> tuple[bool, int]:
        safe_key = " ".join((action_key or "").strip().split())[:80]
        if not safe_key:
            return True, 0

        safe_cooldown = max(1, min(int(cooldown_minutes or 1), 24 * 60))
        now_dt = datetime.now()
        now = now_dt.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT last_used_at
                FROM user_action_cooldowns
                WHERE user_id = ? AND action_key = ?
                LIMIT 1
                """,
                (int(user_id), safe_key),
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                last_dt = _parse_iso_datetime(row["last_used_at"])
                if last_dt:
                    remain = safe_cooldown - int((now_dt - last_dt).total_seconds() // 60)
                    if remain > 0:
                        await db.rollback()
                        return False, remain
                await db.execute(
                    """
                    UPDATE user_action_cooldowns
                    SET last_used_at = ?
                    WHERE user_id = ? AND action_key = ?
                    """,
                    (now, int(user_id), safe_key),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO user_action_cooldowns (user_id, action_key, last_used_at)
                    VALUES (?, ?, ?)
                    """,
                    (int(user_id), safe_key, now),
                )
            await db.commit()
        return True, 0

    async def get_user_cooldown_remaining(
        self,
        user_id: int,
        action_key: str,
        cooldown_minutes: int,
    ) -> int:
        """Проверить оставшийся кулдаун (в минутах) без изменения таймера."""
        safe_key = " ".join((action_key or "").strip().split())[:80]
        if not safe_key:
            return 0
        safe_cooldown = max(1, min(int(cooldown_minutes or 1), 24 * 60))
        now_dt = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT last_used_at
                FROM user_action_cooldowns
                WHERE user_id = ? AND action_key = ?
                LIMIT 1
                """,
                (int(user_id), safe_key),
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return 0
        last_dt = _parse_iso_datetime(row["last_used_at"])
        if not last_dt:
            return 0
        remain = safe_cooldown - int((now_dt - last_dt).total_seconds() // 60)
        return max(0, remain)

    async def get_business_resources(self, business_id: int) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM businesses WHERE id = ? LIMIT 1",
                (int(business_id),),
            ) as cursor:
                exists = await cursor.fetchone()
            if not exists:
                return {
                    "business_id": int(business_id),
                    "raw_materials": 0.0,
                    "daily_consumption": 0.0,
                    "last_order_date": None,
                    "updated_date": now,
                }

            async with db.execute(
                "SELECT * FROM business_resources WHERE business_id = ? LIMIT 1",
                (int(business_id),),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                return dict(row)

            await db.execute(
                """
                INSERT INTO business_resources
                (business_id, raw_materials, daily_consumption, last_order_date, updated_date)
                VALUES (?, 0, 0, NULL, ?)
                """,
                (int(business_id), now),
            )
            await db.commit()
            return {
                "business_id": int(business_id),
                "raw_materials": 0.0,
                "daily_consumption": 0.0,
                "last_order_date": None,
                "updated_date": now,
            }

    async def order_business_raw_materials(
        self,
        owner_id: int,
        business_id: int,
        amount: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Количество сырья должно быть больше нуля.", None
        if safe_amount > 150_000:
            return False, "Слишком большой объем закупки.", None

        unit_price = 95.0
        total_cost = round(safe_amount * unit_price, 2)
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM businesses WHERE id = ? AND status = 'active' LIMIT 1",
                (int(business_id),),
            ) as cursor:
                business = await cursor.fetchone()
            if not business:
                await db.rollback()
                return False, "Бизнес не найден.", None
            if int(business["owner_id"] or 0) != int(owner_id):
                await db.rollback()
                return False, "Только владелец бизнеса может закупать сырье.", None

            budget = float(business["budget"] or 0)
            if budget < total_cost:
                await db.rollback()
                return False, f"Недостаточно бюджета бизнеса. Нужно ${total_cost:,.2f}.", None

            await db.execute(
                "UPDATE businesses SET budget = ? WHERE id = ?",
                (round(budget - total_cost, 2), int(business_id)),
            )
            await db.execute(
                """
                INSERT INTO business_resources
                (business_id, raw_materials, daily_consumption, last_order_date, updated_date)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    raw_materials = COALESCE(raw_materials, 0) + excluded.raw_materials,
                    last_order_date = excluded.last_order_date,
                    updated_date = excluded.updated_date
                """,
                (int(business_id), safe_amount, now, now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=owner_id,
            activity_type="business_raw_order",
            details=f"Закупка сырья для бизнеса #{int(business_id)}",
            value=total_cost,
        )
        return True, "Сырье для бизнеса закуплено.", {"amount": safe_amount, "total_cost": total_cost}

    async def transfer_business_funds(
        self,
        owner_id: int,
        business_id: int,
        amount: float,
        direction: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        safe_direction = (direction or "").strip().lower()
        if safe_direction not in {"to_business", "to_owner"}:
            return False, "Некорректное направление перевода.", None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM businesses WHERE id = ? LIMIT 1", (int(business_id),)) as cursor:
                business = await cursor.fetchone()
            if not business:
                await db.rollback()
                return False, "Бизнес не найден.", None
            if int(business["owner_id"] or 0) != int(owner_id):
                await db.rollback()
                return False, "Только владелец может переводить средства.", None

            async with db.execute("SELECT balance FROM users WHERE user_id = ? LIMIT 1", (int(owner_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Владелец не найден.", None

            owner_balance = float(user["balance"] or 0)
            biz_budget = float(business["budget"] or 0)
            if safe_direction == "to_business":
                if owner_balance < safe_amount:
                    await db.rollback()
                    return False, "Недостаточно средств на личном счете.", None
                owner_balance = round(owner_balance - safe_amount, 2)
                biz_budget = round(biz_budget + safe_amount, 2)
            else:
                if biz_budget < safe_amount:
                    await db.rollback()
                    return False, "Недостаточно средств на счету бизнеса.", None
                owner_balance = round(owner_balance + safe_amount, 2)
                biz_budget = round(biz_budget - safe_amount, 2)

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (owner_balance, int(owner_id)))
            await db.execute("UPDATE businesses SET budget = ? WHERE id = ?", (biz_budget, int(business_id)))
            await db.commit()

        return True, "Перевод выполнен.", {
            "owner_balance": owner_balance,
            "business_budget": biz_budget,
            "amount": safe_amount,
            "direction": safe_direction,
        }

    async def run_business_operation(
        self,
        owner_id: int,
        business_id: int,
        operation: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        op = (operation or "").strip().lower()
        if op not in {"production", "marketing", "contract"}:
            return False, "Неизвестная операция бизнеса.", None

        allowed, remain = await self.check_and_set_user_cooldown(
            owner_id,
            f"bizop:{int(business_id)}:{op}",
            20 if op == "contract" else 30,
        )
        if not allowed:
            return False, f"Кулдаун операции: еще {remain} мин.", {"cooldown_minutes": remain}

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM businesses WHERE id = ? AND status = 'active' LIMIT 1",
                (int(business_id),),
            ) as cursor:
                business = await cursor.fetchone()
            if not business:
                await db.rollback()
                return False, "Бизнес не найден.", None
            if int(business["owner_id"] or 0) != int(owner_id):
                await db.rollback()
                return False, "Только владелец может запускать операции.", None

            budget = float(business["budget"] or 0)
            income_daily = float(business["income_daily"] or 0)
            expense_daily = float(business["expense_daily"] or 0)
            equipment_level = max(1, int(business["equipment_level"] or 1))

            async with db.execute(
                "SELECT raw_materials FROM business_resources WHERE business_id = ? LIMIT 1",
                (int(business_id),),
            ) as cursor:
                res = await cursor.fetchone()
            raw_materials = float(res["raw_materials"] or 0) if res else 0.0

            delta_budget = 0.0
            delta_income = 0.0
            delta_expense = 0.0
            consumed = 0.0

            if op == "production":
                consumed = round(min(raw_materials, random.uniform(18.0, 55.0)), 2)
                if consumed <= 0:
                    await db.rollback()
                    return False, "Недостаточно сырья для производственной смены.", None
                produced_value = consumed * random.uniform(130.0, 210.0) * (1 + equipment_level * 0.04)
                delta_budget = round(produced_value - consumed * 35.0, 2)
                delta_income = round(max(0.0, consumed * 0.35), 2)
            elif op == "marketing":
                spend = round(min(budget, random.uniform(4_000.0, 18_000.0)), 2)
                if spend <= 0:
                    await db.rollback()
                    return False, "Недостаточно бюджета для маркетинга.", None
                effect = random.uniform(0.03, 0.11)
                delta_budget = -spend
                delta_income = round(income_daily * effect, 2)
                delta_expense = round(spend * 0.04, 2)
            else:  # contract
                cost = round(min(budget, random.uniform(2_000.0, 9_000.0)), 2)
                if cost <= 0:
                    await db.rollback()
                    return False, "Недостаточно бюджета для контракта.", None
                success = random.random() < 0.72
                if success:
                    gain = round(cost * random.uniform(1.4, 2.6), 2)
                    delta_budget = round(gain - cost, 2)
                    delta_income = round(gain * 0.08, 2)
                else:
                    delta_budget = -cost
                    delta_expense = round(cost * 0.06, 2)

            new_budget = round(max(0.0, budget + delta_budget), 2)
            new_income = round(max(120.0, income_daily + delta_income), 2)
            new_expense = round(max(80.0, expense_daily + delta_expense), 2)

            await db.execute(
                """
                UPDATE businesses
                SET budget = ?, income_daily = ?, expense_daily = ?, last_income_date = ?
                WHERE id = ?
                """,
                (new_budget, new_income, new_expense, now, int(business_id)),
            )
            if consumed > 0:
                await db.execute(
                    """
                    INSERT INTO business_resources (business_id, raw_materials, daily_consumption, last_order_date, updated_date)
                    VALUES (?, ?, ?, NULL, ?)
                    ON CONFLICT(business_id) DO UPDATE SET
                        raw_materials = MAX(0, COALESCE(raw_materials, 0) - ?),
                        daily_consumption = ?,
                        updated_date = excluded.updated_date
                    """,
                    (int(business_id), raw_materials, consumed, now, consumed, consumed),
                )
            await db.commit()

        await self.log_player_activity(
            user_id=owner_id,
            activity_type="business_operation",
            details=f"Операция {op} для бизнеса #{int(business_id)}",
            value=delta_budget,
        )
        return True, "Операция бизнеса выполнена.", {
            "operation": op,
            "delta_budget": delta_budget,
            "new_budget": new_budget,
            "new_income_daily": new_income,
            "new_expense_daily": new_expense,
            "raw_consumed": consumed,
        }

    async def list_all_businesses(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        query = """
            SELECT b.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(b.owner_id AS TEXT)) AS owner_name,
                   p.name AS property_name
            FROM businesses b
            LEFT JOIN users u ON u.user_id = b.owner_id
            LEFT JOIN properties p ON p.id = b.property_id
            ORDER BY b.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_business_from_property(
        self,
        owner_id: int,
        property_id: int,
        name: str,
        business_type: str,
        description: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        clean_name = " ".join((name or "").strip().split())
        if len(clean_name) < 3:
            return False, "Название бизнеса слишком короткое.", None
        if len(clean_name) > 60:
            return False, "Название бизнеса слишком длинное.", None

        type_code = (business_type or "service").strip().lower()
        if type_code not in {"restaurant", "shop", "factory", "hotel", "service", "media", "it"}:
            type_code = "service"

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(owner_id),)) as cursor:
                owner = await cursor.fetchone()
            if not owner:
                await db.rollback()
                return False, "Владелец не найден.", None

            async with db.execute(
                "SELECT p.* FROM properties p JOIN property_ownership po ON po.property_id = p.id WHERE p.id = ? AND po.owner_id = ?",
                (int(property_id), int(owner_id)),
            ) as cursor:
                prop = await cursor.fetchone()
            if not prop:
                await db.rollback()
                return False, "Вы не владеете этим объектом.", None

            async with db.execute("SELECT id FROM businesses WHERE lower(name) = lower(?) LIMIT 1", (clean_name,)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Бизнес с таким названием уже существует.", None

            async with db.execute("SELECT id FROM businesses WHERE property_id = ? AND status = 'active' LIMIT 1", (int(property_id),)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "В этом здании уже работает бизнес.", None

            async with db.execute("SELECT id FROM private_orgs WHERE property_id = ? AND status = 'active' LIMIT 1", (int(property_id),)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Здание занято частной организацией.", None

            property_price = float(prop["price"] or 0)
            registration_fee = round(max(50_000.0, property_price * 0.55), 2)
            owner_balance = float(owner["balance"] or 0)
            if owner_balance < registration_fee:
                await db.rollback()
                return False, f"Недостаточно средств для открытия бизнеса. Нужно ${registration_fee:,.2f}.", None

            type_config = {
                "restaurant": (1_900, 1_250, 130_000),
                "shop": (1_450, 980, 110_000),
                "factory": (3_200, 2_250, 190_000),
                "hotel": (2_500, 1_730, 165_000),
                "media": (1_700, 1_050, 120_000),
                "it": (2_300, 1_290, 150_000),
                "service": (1_350, 890, 100_000),
            }
            income_daily, expense_daily, start_budget = type_config[type_code]

            new_owner_balance = round(owner_balance - registration_fee, 2)
            await db.execute(
                "UPDATE users SET balance = ?, business_owner = 1 WHERE user_id = ?",
                (new_owner_balance, int(owner_id)),
            )
            cursor = await db.execute(
                """
                INSERT INTO businesses
                (name, owner_id, type, budget, description, status, location, created_date, property_id, equipment_level, income_daily, expense_daily, last_income_date)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    clean_name,
                    int(owner_id),
                    type_code,
                    float(start_budget),
                    (description or "").strip()[:500],
                    prop["location"],
                    now,
                    int(property_id),
                    float(income_daily),
                    float(expense_daily),
                    now,
                ),
            )
            business_id = int(cursor.lastrowid or 0)
            await db.execute("UPDATE properties SET status = 'business' WHERE id = ?", (int(property_id),))
            await db.commit()

        await self.log_player_activity(
            user_id=owner_id,
            activity_type="business_open",
            details=f"Открыт бизнес '{clean_name}' в объекте #{int(property_id)}",
            value=registration_fee,
        )
        return True, "Бизнес успешно открыт.", {
            "business_id": business_id,
            "registration_fee": registration_fee,
            "new_balance": new_owner_balance,
            "type": type_code,
        }

    async def list_private_orgs(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        query = """
            SELECT po.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(po.leader_id AS TEXT)) AS leader_name,
                   p.name AS property_name
            FROM private_orgs po
            LEFT JOIN users u ON u.user_id = po.leader_id
            LEFT JOIN properties p ON p.id = po.property_id
            ORDER BY po.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_private_org_from_property(
        self,
        leader_id: int,
        property_id: int,
        name: str,
        description: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        clean_name = " ".join((name or "").strip().split())
        if len(clean_name) < 3:
            return False, "Название организации слишком короткое.", None
        if len(clean_name) > 70:
            return False, "Название организации слишком длинное.", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(leader_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            async with db.execute(
                "SELECT p.* FROM properties p JOIN property_ownership po ON po.property_id = p.id WHERE p.id = ? AND po.owner_id = ?",
                (int(property_id), int(leader_id)),
            ) as cursor:
                prop = await cursor.fetchone()
            if not prop:
                await db.rollback()
                return False, "Вы не владеете этим объектом.", None

            async with db.execute("SELECT id FROM private_orgs WHERE lower(name) = lower(?) LIMIT 1", (clean_name,)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Частная организация с таким названием уже существует.", None

            async with db.execute("SELECT id FROM private_orgs WHERE property_id = ? AND status = 'active' LIMIT 1", (int(property_id),)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "В этом здании уже зарегистрирована частная организация.", None

            async with db.execute("SELECT id FROM businesses WHERE property_id = ? AND status = 'active' LIMIT 1", (int(property_id),)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Здание уже используется активным бизнесом.", None

            property_price = float(prop["price"] or 0)
            registration_fee = round(max(80_000.0, property_price * 0.8), 2)
            balance = float(user["balance"] or 0)
            if balance < registration_fee:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${registration_fee:,.2f}.", None

            new_balance = round(balance - registration_fee, 2)
            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, int(leader_id)))
            cursor = await db.execute(
                """
                INSERT INTO private_orgs
                (name, leader_id, budget, description, policy, status, created_date, property_id, equipment_level)
                VALUES (?, ?, ?, ?, 'private', 'active', ?, ?, 1)
                """,
                (
                    clean_name,
                    int(leader_id),
                    180_000.0,
                    (description or "").strip()[:500],
                    now,
                    int(property_id),
                ),
            )
            org_id = int(cursor.lastrowid or 0)
            await db.execute(
                "INSERT INTO private_org_members (org_id, user_id, role, join_date) VALUES (?, ?, 'Лидер', ?)",
                (org_id, int(leader_id), now),
            )
            await db.execute("UPDATE properties SET status = 'private_org' WHERE id = ?", (int(property_id),))
            await db.commit()

        await self.log_player_activity(
            user_id=leader_id,
            activity_type="private_org_open",
            details=f"Создана частная организация '{clean_name}'",
            value=registration_fee,
        )
        return True, "Частная организация успешно зарегистрирована.", {
            "org_id": org_id,
            "registration_fee": registration_fee,
            "new_balance": new_balance,
        }

    async def get_private_org_by_id(self, org_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT po.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(po.leader_id AS TEXT)) AS leader_name,
                   p.name AS property_name
            FROM private_orgs po
            LEFT JOIN users u ON u.user_id = po.leader_id
            LEFT JOIN properties p ON p.id = po.property_id
            WHERE po.id = ?
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(org_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_private_org_membership(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT po.*,
                   pom.role AS member_role
            FROM private_org_members pom
            JOIN private_orgs po ON po.id = pom.org_id
            WHERE pom.user_id = ?
              AND po.status = 'active'
            ORDER BY pom.join_date DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_private_org_members(self, org_id: int, limit: int = 40) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 40), 200))
        query = """
            SELECT pom.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(pom.user_id AS TEXT)) AS display_name,
                   u.nickname,
                   u.full_name,
                   u.username
            FROM private_org_members pom
            LEFT JOIN users u ON u.user_id = pom.user_id
            WHERE pom.org_id = ?
            ORDER BY CASE WHEN lower(COALESCE(pom.role, '')) = 'лидер' THEN 0 ELSE 1 END ASC,
                     pom.join_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(org_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def apply_to_private_org(self, user_id: int, org_id: int, application_text: str) -> tuple[bool, str, Optional[int]]:
        clean_text = " ".join((application_text or "").strip().split())
        if len(clean_text) < 8:
            return False, "Заявление слишком короткое (минимум 8 символов).", None
        if len(clean_text) > 900:
            return False, "Заявление слишком длинное (максимум 900 символов).", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT id, status FROM private_orgs WHERE id = ?",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org or str(org["status"] or "") != "active":
                await db.rollback()
                return False, "Частная организация не найдена или закрыта.", None

            async with db.execute(
                "SELECT id FROM private_org_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                (int(org_id), int(user_id)),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Вы уже состоите в этой организации.", None

            async with db.execute(
                """
                SELECT id
                FROM private_org_applications
                WHERE org_id = ? AND user_id = ? AND status = 'pending'
                LIMIT 1
                """,
                (int(org_id), int(user_id)),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "У вас уже есть активная заявка в эту организацию.", None

            cursor = await db.execute(
                """
                INSERT INTO private_org_applications
                (org_id, user_id, application_text, status, applied_date, reviewed_by, reviewed_date)
                VALUES (?, ?, ?, 'pending', ?, NULL, NULL)
                """,
                (int(org_id), int(user_id), clean_text, now),
            )
            app_id = int(cursor.lastrowid or 0)
            await db.commit()

        return True, "Заявление отправлено руководству частной организации.", app_id

    async def get_private_org_applications(
        self,
        org_id: int,
        status: str = "pending",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 100))
        query = """
            SELECT poa.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(poa.user_id AS TEXT)) AS applicant_name,
                   u.username AS applicant_username
            FROM private_org_applications poa
            LEFT JOIN users u ON u.user_id = poa.user_id
            WHERE poa.org_id = ? AND poa.status = ?
            ORDER BY poa.applied_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(org_id), str(status), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def review_private_org_application(
        self,
        reviewer_id: int,
        application_id: int,
        approve: bool,
    ) -> tuple[bool, str]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT * FROM private_org_applications WHERE id = ? LIMIT 1",
                (int(application_id),),
            ) as cursor:
                app = await cursor.fetchone()
            if not app:
                await db.rollback()
                return False, "Заявление не найдено."
            if str(app["status"] or "") != "pending":
                await db.rollback()
                return False, "Заявление уже рассмотрено."

            async with db.execute(
                "SELECT * FROM private_orgs WHERE id = ? LIMIT 1",
                (int(app["org_id"]),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "Организация не найдена."
            if int(org["leader_id"] or 0) != int(reviewer_id):
                await db.rollback()
                return False, "Только лидер частной организации может рассматривать заявления."

            new_status = "approved" if approve else "rejected"
            await db.execute(
                """
                UPDATE private_org_applications
                SET status = ?, reviewed_by = ?, reviewed_date = ?
                WHERE id = ?
                """,
                (new_status, int(reviewer_id), now, int(application_id)),
            )

            if approve:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO private_org_members (org_id, user_id, role, join_date)
                    VALUES (?, ?, 'Сотрудник', ?)
                    """,
                    (int(app["org_id"]), int(app["user_id"]), now),
                )

            await db.commit()
        return True, ("Заявление одобрено." if approve else "Заявление отклонено.")

    async def get_private_org_resources(self, org_id: int) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM private_orgs WHERE id = ? LIMIT 1",
                (int(org_id),),
            ) as cursor:
                exists = await cursor.fetchone()
            if not exists:
                return {
                    "org_id": int(org_id),
                    "raw_materials": 0.0,
                    "daily_consumption": 0.0,
                    "last_order_date": None,
                    "updated_date": now,
                }
            async with db.execute(
                "SELECT * FROM private_org_resources WHERE org_id = ? LIMIT 1",
                (int(org_id),),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                return dict(row)
            await db.execute(
                """
                INSERT INTO private_org_resources (org_id, raw_materials, daily_consumption, last_order_date, updated_date)
                VALUES (?, 0, 0, NULL, ?)
                """,
                (int(org_id), now),
            )
            await db.commit()
            return {
                "org_id": int(org_id),
                "raw_materials": 0.0,
                "daily_consumption": 0.0,
                "last_order_date": None,
                "updated_date": now,
            }

    async def order_private_org_raw_materials(
        self,
        leader_id: int,
        org_id: int,
        amount: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Количество сырья должно быть больше нуля.", None
        if safe_amount > 100_000:
            return False, "Слишком большой объем заказа.", None

        unit_price = 115.0
        total_cost = round(safe_amount * unit_price, 2)
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT * FROM private_orgs WHERE id = ? AND status = 'active' LIMIT 1",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "Частная организация не найдена.", None
            if int(org["leader_id"] or 0) != int(leader_id):
                await db.rollback()
                return False, "Заказывать сырье может только лидер организации.", None

            budget = float(org["budget"] or 0)
            if budget < total_cost:
                await db.rollback()
                return False, f"Недостаточно бюджета. Нужно ${total_cost:,.2f}.", None

            await db.execute(
                "UPDATE private_orgs SET budget = ? WHERE id = ?",
                (round(budget - total_cost, 2), int(org_id)),
            )
            await db.execute(
                """
                INSERT INTO private_org_resources (org_id, raw_materials, daily_consumption, last_order_date, updated_date)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(org_id) DO UPDATE SET
                    raw_materials = COALESCE(raw_materials, 0) + excluded.raw_materials,
                    last_order_date = excluded.last_order_date,
                    updated_date = excluded.updated_date
                """,
                (int(org_id), safe_amount, now, now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=leader_id,
            activity_type="private_org_raw_order",
            details=f"Закупка сырья для частной организации #{int(org_id)}",
            value=total_cost,
        )
        return True, "Сырье успешно заказано.", {
            "amount": safe_amount,
            "total_cost": total_cost,
        }

    async def transfer_private_org_funds(
        self,
        leader_id: int,
        org_id: int,
        amount: float,
        direction: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        safe_direction = (direction or "").strip().lower()
        if safe_direction not in {"to_org", "to_user"}:
            return False, "Некорректное направление перевода.", None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM private_orgs WHERE id = ? AND status = 'active' LIMIT 1",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "Частная организация не найдена.", None
            if int(org["leader_id"] or 0) != int(leader_id):
                await db.rollback()
                return False, "Перевод может выполнять только лидер организации.", None

            async with db.execute("SELECT balance FROM users WHERE user_id = ? LIMIT 1", (int(leader_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Лидер не найден.", None

            user_balance = float(user["balance"] or 0)
            org_budget = float(org["budget"] or 0)
            if safe_direction == "to_org":
                if user_balance < safe_amount:
                    await db.rollback()
                    return False, "Недостаточно средств на личном счете.", None
                user_balance = round(user_balance - safe_amount, 2)
                org_budget = round(org_budget + safe_amount, 2)
            else:
                if org_budget < safe_amount:
                    await db.rollback()
                    return False, "Недостаточно средств в бюджете организации.", None
                user_balance = round(user_balance + safe_amount, 2)
                org_budget = round(org_budget - safe_amount, 2)

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (user_balance, int(leader_id)))
            await db.execute("UPDATE private_orgs SET budget = ? WHERE id = ?", (org_budget, int(org_id)))
            await db.commit()

        return True, "Перевод выполнен.", {
            "user_balance": user_balance,
            "org_budget": org_budget,
            "amount": safe_amount,
            "direction": safe_direction,
        }

    async def run_private_org_operation(
        self,
        leader_id: int,
        org_id: int,
        operation: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        op = (operation or "").strip().lower()
        if op not in {"production", "campaign", "security"}:
            return False, "Неизвестная операция организации.", None

        allowed, remain = await self.check_and_set_user_cooldown(
            leader_id,
            f"porg:{int(org_id)}:{op}",
            30,
        )
        if not allowed:
            return False, f"Кулдаун операции: еще {remain} мин.", {"cooldown_minutes": remain}

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM private_orgs WHERE id = ? AND status = 'active' LIMIT 1",
                (int(org_id),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "Организация не найдена.", None
            if int(org["leader_id"] or 0) != int(leader_id):
                await db.rollback()
                return False, "Операцию может запускать только лидер.", None

            budget = float(org["budget"] or 0)
            eq_level = max(1, int(org["equipment_level"] or 1))
            async with db.execute(
                "SELECT raw_materials FROM private_org_resources WHERE org_id = ? LIMIT 1",
                (int(org_id),),
            ) as cursor:
                res = await cursor.fetchone()
            raw_materials = float(res["raw_materials"] or 0) if res else 0.0

            delta_budget = 0.0
            delta_rep = 0.0
            consumed = 0.0

            if op == "production":
                consumed = round(min(raw_materials, random.uniform(20.0, 65.0)), 2)
                if consumed <= 0:
                    await db.rollback()
                    return False, "Недостаточно сырья для операционного цикла.", None
                gain = consumed * random.uniform(120.0, 195.0) * (1 + eq_level * 0.03)
                delta_budget = round(gain - consumed * 28.0, 2)
                delta_rep = random.uniform(0.15, 0.5)
            elif op == "campaign":
                spend = round(min(budget, random.uniform(3_000.0, 14_000.0)), 2)
                if spend <= 0:
                    await db.rollback()
                    return False, "Недостаточно бюджета для кампании.", None
                delta_budget = -spend
                delta_rep = random.uniform(0.4, 1.2)
            else:  # security
                spend = round(min(budget, random.uniform(2_000.0, 8_000.0)), 2)
                if spend <= 0:
                    await db.rollback()
                    return False, "Недостаточно бюджета для аудита безопасности.", None
                delta_budget = -spend
                delta_rep = random.uniform(0.2, 0.8)

            new_budget = round(max(0.0, budget + delta_budget), 2)
            # Репутация частных организаций хранится как эффект в activity log.

            await db.execute(
                "UPDATE private_orgs SET budget = ? WHERE id = ?",
                (new_budget, int(org_id)),
            )
            if consumed > 0:
                await db.execute(
                    """
                    INSERT INTO private_org_resources (org_id, raw_materials, daily_consumption, last_order_date, updated_date)
                    VALUES (?, ?, ?, NULL, ?)
                    ON CONFLICT(org_id) DO UPDATE SET
                        raw_materials = MAX(0, COALESCE(raw_materials, 0) - ?),
                        daily_consumption = ?,
                        updated_date = excluded.updated_date
                    """,
                    (int(org_id), raw_materials, consumed, now, consumed, consumed),
                )
            await db.commit()

        await self.log_player_activity(
            user_id=leader_id,
            activity_type="private_org_operation",
            details=f"Операция {op} в частной организации #{int(org_id)}",
            value=delta_budget,
        )
        return True, "Операция частной организации выполнена.", {
            "operation": op,
            "delta_budget": delta_budget,
            "new_budget": new_budget,
            "raw_consumed": consumed,
            "reputation_delta": round(delta_rep, 2),
        }

    async def _get_active_tax_holiday_row(self, db_conn: aiosqlite.Connection, business_id: int) -> Optional[aiosqlite.Row]:
        now = datetime.now().isoformat()
        async with db_conn.execute(
            """
            SELECT *
            FROM business_tax_holidays
            WHERE business_id = ?
              AND status = 'active'
              AND start_date <= ?
              AND end_date >= ?
            ORDER BY created_date DESC
            LIMIT 1
            """,
            (int(business_id), now, now),
        ) as cursor:
            return await cursor.fetchone()

    async def grant_business_tax_holiday(
        self,
        actor_id: int,
        business_id: int,
        reason: str,
        days: int = 1,
    ) -> tuple[bool, str]:
        authority = await self.get_government_authority(actor_id)
        if authority not in {"president", "vice_president", "finance_minister", "minister"}:
            return False, "Недостаточно полномочий для налоговых каникул."

        safe_days = max(1, min(int(days or 1), 3))
        clean_reason = " ".join((reason or "").strip().split())[:350]
        if not clean_reason:
            clean_reason = "Особый режим"

        business = await self.get_business_by_id(int(business_id))
        if not business:
            return False, "Бизнес не найден."

        now_dt = datetime.now()
        start_date = now_dt.isoformat()
        end_date = (now_dt + timedelta(days=safe_days)).isoformat()
        now = now_dt.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO business_tax_holidays
                (business_id, granted_by, reason, start_date, end_date, status, created_date)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (int(business_id), int(actor_id), clean_reason, start_date, end_date, now),
            )
            await db.execute(
                """
                INSERT INTO corruption_ops
                (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                VALUES (?, ?, 'tax_holiday', 0, 35, 'logged', ?, ?)
                """,
                (
                    int(actor_id),
                    int(business.get("owner_id") or 0),
                    f"Налоговые каникулы для бизнеса '{business.get('name')}' на {safe_days} дн.: {clean_reason}",
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="tax_holiday",
            details=f"Налоговые каникулы бизнесу '{business.get('name')}'",
            value=0,
        )
        return True, "Налоговые каникулы назначены."

    async def generate_business_tax_reports(self, cycle_date: Optional[str] = None) -> Dict[str, Any]:
        now_dt = datetime.now()
        now = now_dt.isoformat()
        cycle = (cycle_date or now_dt.date().isoformat()).strip()

        reports_created = 0
        total_tax_paid = 0.0
        unpaid_count = 0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                UPDATE business_tax_holidays
                SET status = 'expired'
                WHERE status = 'active' AND end_date < ?
                """,
                (now,),
            )

            async with db.execute(
                """
                SELECT b.*,
                       u.balance AS owner_balance,
                       u.tax_debt AS owner_tax_debt,
                       u.total_tax_paid AS owner_total_tax_paid,
                       u.reputation AS owner_reputation
                FROM businesses b
                JOIN users u ON u.user_id = b.owner_id
                WHERE b.status = 'active'
                ORDER BY b.id ASC
                """
            ) as cursor:
                businesses = await cursor.fetchall()

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE name = 'Правительство' LIMIT 1"
            ) as cursor:
                gov_row = await cursor.fetchone()
            gov_id = int(gov_row["id"]) if gov_row else 0
            gov_budget = float(gov_row["budget"] or 0) if gov_row else 0.0

            for business in businesses:
                business_id = int(business["id"])
                owner_id = int(business["owner_id"])
                income_daily = float(business["income_daily"] or 0)
                expense_daily = float(business["expense_daily"] or 0)
                owner_balance = float(business["owner_balance"] or 0)
                owner_tax_debt = float(business["owner_tax_debt"] or 0)
                owner_total_tax_paid = float(business["owner_total_tax_paid"] or 0)
                owner_reputation = float(business["owner_reputation"] or 50)

                tax_base = max(0.0, income_daily - expense_daily * 0.25)
                tax_due = round(max(80.0, tax_base * DAILY_BUSINESS_TAX_RATE), 2)
                tax_paid = 0.0
                status = "pending"
                note = ""
                holiday_by: Optional[int] = None

                holiday = await self._get_active_tax_holiday_row(db, business_id)
                if holiday:
                    status = "holiday"
                    note = holiday["reason"] or "Налоговые каникулы"
                    holiday_by = int(holiday["granted_by"] or 0)
                    tax_due = 0.0
                else:
                    if owner_balance >= tax_due:
                        status = "paid"
                        tax_paid = tax_due
                        owner_balance = round(owner_balance - tax_due, 2)
                        owner_total_tax_paid = round(owner_total_tax_paid + tax_due, 2)
                        total_tax_paid += tax_paid
                        await db.execute(
                            "UPDATE users SET balance = ?, total_tax_paid = ? WHERE user_id = ?",
                            (owner_balance, owner_total_tax_paid, owner_id),
                        )
                        if gov_id > 0:
                            gov_budget = round(gov_budget + tax_paid, 2)
                    else:
                        status = "unpaid"
                        unpaid_count += 1
                        owner_tax_debt = round(owner_tax_debt + tax_due, 2)
                        owner_reputation = round(max(0.0, owner_reputation - 0.4), 2)
                        await db.execute(
                            "UPDATE users SET tax_debt = ?, reputation = ? WHERE user_id = ?",
                            (owner_tax_debt, owner_reputation, owner_id),
                        )
                        note = "Недостаточно средств на счете владельца."

                await db.execute(
                    """
                    INSERT INTO business_tax_reports
                    (business_id, owner_id, cycle_date, tax_due, tax_paid, status, note, holiday_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        business_id,
                        owner_id,
                        cycle,
                        tax_due,
                        tax_paid,
                        status,
                        note,
                        holiday_by,
                        now,
                    ),
                )
                reports_created += 1

            if gov_id > 0:
                await db.execute("UPDATE organizations SET budget = ? WHERE id = ?", (gov_budget, gov_id))
            await db.commit()

        return {
            "cycle_date": cycle,
            "reports_created": reports_created,
            "total_tax_paid": round(total_tax_paid, 2),
            "unpaid_count": unpaid_count,
        }

    async def get_latest_business_tax_reports(
        self,
        limit: int = 25,
        owner_id: Optional[int] = None,
        unpaid_only: bool = False,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 25), 200))
        where_parts: List[str] = []
        params: List[Any] = []
        if owner_id is not None:
            where_parts.append("btr.owner_id = ?")
            params.append(int(owner_id))
        if unpaid_only:
            where_parts.append("btr.status = 'unpaid'")
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(safe_limit)

        query = f"""
            SELECT btr.*,
                   b.name AS business_name,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(btr.owner_id AS TEXT)) AS owner_name
            FROM business_tax_reports btr
            LEFT JOIN businesses b ON b.id = btr.business_id
            LEFT JOIN users u ON u.user_id = btr.owner_id
            {where_clause}
            ORDER BY btr.created_at DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_tax_service_user_ids(self) -> List[int]:
        query = """
            SELECT user_id
            FROM users
            WHERE (organization = 'Налоговая служба' OR lower(COALESCE(role, '')) LIKE '%налог%')
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [int(row[0]) for row in rows if row and row[0] is not None]

    async def ensure_education_program_catalog(self) -> Dict[str, int]:
        """
        Гарантирует наличие и актуальность базового каталога программ обучения.
        Возвращает статистику: сколько создано/обновлено программ.
        """
        now = datetime.now().isoformat()
        catalog: List[Dict[str, Any]] = [
            {
                "name": "Базовая грамотность управления",
                "description": "Экономика для новичков: бюджет, налоги, финансовая дисциплина.",
                "duration_days": 4,
                "tuition_fee": 1200.0,
                "min_education": 1,
                "min_reputation": 0.0,
            },
            {
                "name": "Финансовая аналитика",
                "description": "Расчеты, инвестиции, риск-менеджмент и базовые отчеты.",
                "duration_days": 6,
                "tuition_fee": 2800.0,
                "min_education": 2,
                "min_reputation": 8.0,
            },
            {
                "name": "Юридический интенсив",
                "description": "Законодательство, ответственность и правовые процедуры.",
                "duration_days": 7,
                "tuition_fee": 4200.0,
                "min_education": 3,
                "min_reputation": 14.0,
            },
            {
                "name": "Государственный менеджмент",
                "description": "Управление структурами, KPI, кадровые процессы и контроль.",
                "duration_days": 8,
                "tuition_fee": 5600.0,
                "min_education": 4,
                "min_reputation": 20.0,
            },
            {
                "name": "Инженерный практикум инфраструктуры",
                "description": "Городская инфраструктура, логистика, оптимизация процессов.",
                "duration_days": 9,
                "tuition_fee": 6900.0,
                "min_education": 4,
                "min_reputation": 24.0,
            },
            {
                "name": "Магистратура: Геоэкономика",
                "description": "Сложные макромодели, кризисы и стратегические решения.",
                "duration_days": 11,
                "tuition_fee": 8900.0,
                "min_education": 5,
                "min_reputation": 30.0,
            },
            {
                "name": "Доктрина антикризисного управления",
                "description": "Высший курс для лидеров: госбюджет, реформы, устойчивость.",
                "duration_days": 12,
                "tuition_fee": 12000.0,
                "min_education": 7,
                "min_reputation": 40.0,
            },
        ]

        created = 0
        updated = 0
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            for item in catalog:
                name = str(item["name"]).strip()[:96]
                duration_days = max(2, min(int(item["duration_days"] or 4), 30))
                tuition_fee = round(max(0.0, float(item["tuition_fee"] or 0.0)), 2)
                min_education = max(1, min(int(item["min_education"] or 1), 12))
                min_reputation = round(max(0.0, float(item["min_reputation"] or 0.0)), 2)
                description = str(item["description"] or "").strip()[:600]

                async with db.execute(
                    "SELECT id FROM education_programs WHERE name = ? ORDER BY id ASC LIMIT 1",
                    (name,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    await db.execute(
                        """
                        UPDATE education_programs
                        SET description = ?,
                            duration_days = ?,
                            tuition_fee = ?,
                            min_education = ?,
                            min_reputation = ?,
                            active = 1
                        WHERE id = ?
                        """,
                        (
                            description,
                            duration_days,
                            tuition_fee,
                            min_education,
                            min_reputation,
                            int(row["id"]),
                        ),
                    )
                    updated += 1
                else:
                    await db.execute(
                        """
                        INSERT INTO education_programs
                        (name, description, duration_days, tuition_fee, min_education, min_reputation, active, created_date)
                        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            name,
                            description,
                            duration_days,
                            tuition_fee,
                            min_education,
                            min_reputation,
                            now,
                        ),
                    )
                    created += 1
            await db.commit()
        return {"created": created, "updated": updated}

    async def list_education_programs(self, active_only: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        where = "WHERE ep.active = 1" if active_only else ""
        query = f"""
            SELECT ep.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ep.teacher_id AS TEXT)) AS teacher_name
            FROM education_programs ep
            LEFT JOIN users u ON u.user_id = ep.teacher_id
            {where}
            ORDER BY ep.tuition_fee ASC, ep.duration_days ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_education_status(self, user_id: int) -> Dict[str, Any]:
        user = await self.get_user(user_id) or {}
        result: Dict[str, Any] = {"user": user, "active_enrollment": None, "completed_count": 0}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT ee.*,
                       ep.name AS program_name,
                       ep.duration_days,
                       ep.tuition_fee
                FROM education_enrollments ee
                JOIN education_programs ep ON ep.id = ee.program_id
                WHERE ee.user_id = ? AND ee.status = 'active'
                ORDER BY ee.start_date DESC
                LIMIT 1
                """,
                (int(user_id),),
            ) as cursor:
                active = await cursor.fetchone()
            if active:
                result["active_enrollment"] = dict(active)

            async with db.execute(
                "SELECT COUNT(*) FROM education_enrollments WHERE user_id = ? AND status = 'completed'",
                (int(user_id),),
            ) as cursor:
                row = await cursor.fetchone()
                result["completed_count"] = int((row[0] if row else 0) or 0)
        return result

    async def enroll_education_program(
        self,
        user_id: int,
        program_id: int,
        study_choice: str = "theory",
    ) -> tuple[bool, str]:
        now = datetime.now().isoformat()
        choice = (study_choice or "theory").strip().lower()
        if choice not in {"theory", "practice"}:
            choice = "theory"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден."

            async with db.execute("SELECT * FROM education_programs WHERE id = ? AND active = 1", (int(program_id),)) as cursor:
                program = await cursor.fetchone()
            if not program:
                await db.rollback()
                return False, "Программа не найдена."

            async with db.execute(
                "SELECT id FROM education_enrollments WHERE user_id = ? AND status = 'active' LIMIT 1",
                (int(user_id),),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "У вас уже есть активное обучение."

            current_education = int(user["education"] or 1)
            current_reputation = float(user["reputation"] or 50)
            min_education = int(program["min_education"] or 1)
            min_reputation = float(program["min_reputation"] or 0)
            tuition_fee = float(program["tuition_fee"] or 0)
            balance = float(user["balance"] or 0)

            if current_education < min_education:
                await db.rollback()
                return False, f"Требуется уровень образования {min_education}+."
            if current_reputation < min_reputation:
                await db.rollback()
                return False, f"Требуется репутация {min_reputation:.1f}+."
            if balance < tuition_fee:
                await db.rollback()
                return False, f"Недостаточно средств. Стоимость обучения: ${tuition_fee:,.2f}."

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (round(balance - tuition_fee, 2), int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO education_enrollments
                (user_id, program_id, teacher_id, status, start_date, last_study_date, progress_days, completed_date, study_choice)
                VALUES (?, ?, ?, 'active', ?, NULL, 0, NULL, ?)
                """,
                (int(user_id), int(program_id), program["teacher_id"], now, choice),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="education_enroll",
            details=f"Начато обучение: {program['name']}",
            value=float(program["tuition_fee"] or 0),
        )
        return True, "Вы успешно зачислены на программу."

    async def study_education_session(
        self,
        user_id: int,
        mode: str = "theory",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now_dt = datetime.now()
        now = now_dt.isoformat()
        session_cooldown_minutes = 360
        safe_mode = (mode or "theory").strip().lower()
        if safe_mode not in {"theory", "practice"}:
            safe_mode = "theory"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT ee.*,
                       ep.name AS program_name,
                       ep.duration_days
                FROM education_enrollments ee
                JOIN education_programs ep ON ep.id = ee.program_id
                WHERE ee.user_id = ? AND ee.status = 'active'
                ORDER BY ee.start_date DESC
                LIMIT 1
                """,
                (int(user_id),),
            ) as cursor:
                enrollment = await cursor.fetchone()
            if not enrollment:
                await db.rollback()
                return False, "У вас нет активной программы обучения.", None

            last_study = str(enrollment["last_study_date"] or "")
            if last_study:
                try:
                    last_dt = datetime.fromisoformat(last_study)
                    passed_minutes = int((now_dt - last_dt).total_seconds() // 60)
                    remain = session_cooldown_minutes - passed_minutes
                    if remain > 0:
                        await db.rollback()
                        return False, f"Следующая учебная сессия доступна через {remain} мин.", {
                            "cooldown_minutes": remain
                        }
                except Exception:
                    pass

            progress_days = int(enrollment["progress_days"] or 0)
            duration_days = max(1, int(enrollment["duration_days"] or 1))
            increment = 1
            if safe_mode == "practice":
                increment = 2 if random.random() < 0.65 else 1
                if random.random() < 0.12:
                    increment = 3
            new_progress = min(duration_days, progress_days + increment)

            complete = new_progress >= duration_days
            await db.execute(
                """
                UPDATE education_enrollments
                SET progress_days = ?, last_study_date = ?, study_choice = ?, status = ?, completed_date = ?
                WHERE id = ?
                """,
                (
                    new_progress,
                    now,
                    safe_mode,
                    "completed" if complete else "active",
                    now if complete else None,
                    int(enrollment["id"]),
                ),
            )

            async with db.execute("SELECT education, reputation FROM users WHERE user_id = ?", (int(user_id),)) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "Игрок не найден.", None

            current_education = int(user_row["education"] or 1)
            current_reputation = float(user_row["reputation"] or 50)
            new_education = current_education
            rep_delta = 0.2 if safe_mode == "practice" else 0.1
            if complete:
                new_education = min(12, current_education + 1)
                rep_delta = 1.5 if safe_mode == "practice" else 1.0

            await db.execute(
                "UPDATE users SET education = ?, reputation = ? WHERE user_id = ?",
                (
                    new_education,
                    round(min(100.0, current_reputation + rep_delta), 2),
                    int(user_id),
                ),
            )
            await db.commit()

        if complete:
            await self.log_player_activity(
                user_id=user_id,
                activity_type="education_complete",
                details=f"Завершено обучение: {enrollment['program_name']}",
                value=15_000,
            )
        else:
            await self.log_player_activity(
                user_id=user_id,
                activity_type="education_study",
                details=f"Учебная сессия: {enrollment['program_name']}",
                value=2_000,
            )

        payload = {
            "program_name": enrollment["program_name"],
            "progress_days": new_progress,
            "duration_days": duration_days,
            "completed": complete,
            "new_education": new_education,
        }
        return True, "Учебная сессия завершена.", payload

    async def complete_quick_education_test(
        self,
        user_id: int,
        passed: bool,
        score: Optional[int] = None,
        total_questions: Optional[int] = None,
        difficulty: Optional[float] = None,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now_dt = datetime.now()
        now = now_dt.isoformat()
        cooldown_minutes = 45
        safe_total = max(1, min(int(total_questions or 1), 20))
        safe_score = max(0, min(int(score or (1 if passed else 0)), safe_total))
        safe_difficulty = max(1.0, min(float(difficulty or 1.0), 5.0))

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT education, reputation, balance, last_education_test_at FROM users WHERE user_id = ?",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            last_test_at = str(user["last_education_test_at"] or "")
            if last_test_at:
                try:
                    last_dt = datetime.fromisoformat(last_test_at)
                    remain = cooldown_minutes - int((now_dt - last_dt).total_seconds() // 60)
                    if remain > 0:
                        await db.rollback()
                        return False, f"Следующий тест доступен через {remain} мин.", {"cooldown_minutes": remain}
                except Exception:
                    pass

            education = int(user["education"] or 1)
            reputation = float(user["reputation"] or 50)
            balance = float(user["balance"] or 0)
            reward = 0.0
            education_delta = 0

            if passed:
                education_delta = 1
                reward = 220.0 + safe_score * 95.0 + (safe_difficulty * 40.0)
                if safe_score >= safe_total:
                    reward += 250.0
                reward = round(reward, 2)
                education = min(12, education + 1)
                rep_bonus = 0.2 + (safe_score / safe_total) * 0.35
                reputation = min(100.0, reputation + rep_bonus)
                balance = round(balance + reward, 2)
            else:
                ratio = safe_score / safe_total
                if ratio >= 0.5:
                    reward = round(80.0 + ratio * 140.0, 2)
                    balance = round(balance + reward, 2)
                    reputation = min(100.0, reputation + 0.05)
                else:
                    reputation = max(0.0, reputation - 0.18)

            await db.execute(
                """
                UPDATE users
                SET education = ?, reputation = ?, balance = ?, last_education_test_at = ?
                WHERE user_id = ?
                """,
                (education, round(reputation, 2), balance, now, int(user_id)),
            )
            await db.commit()

        if passed:
            await self.log_player_activity(
                user_id=user_id,
                activity_type="education_test_passed",
                details="Успешно сдан быстрый тест образования",
                value=reward,
            )

        return True, ("Тест пройден." if passed else "Тест не пройден."), {
            "passed": bool(passed),
            "education_delta": education_delta,
            "new_education": education,
            "new_balance": balance,
            "reward": reward,
            "cooldown_minutes": cooldown_minutes,
            "score": safe_score,
            "total_questions": safe_total,
            "difficulty": round(safe_difficulty, 2),
        }

    def list_citizen_jobs(self) -> List[Dict[str, Any]]:
        return [dict(job) for job in JOB_CATALOG]

    def get_citizen_job(self, job_code: str) -> Optional[Dict[str, Any]]:
        code = (job_code or "").strip().lower()
        for job in JOB_CATALOG:
            if str(job.get("code") or "").lower() == code:
                return dict(job)
        return None

    async def get_user_pending_job_application(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT *
            FROM job_applications
            WHERE user_id = ? AND status = 'pending'
            ORDER BY applied_date DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def apply_for_citizen_job(
        self,
        user_id: int,
        job_code: str,
        application_text: str,
    ) -> tuple[bool, str, Optional[int]]:
        job = self.get_citizen_job(job_code)
        if not job:
            return False, "Вакансия не найдена.", None

        clean_text = " ".join((application_text or "").strip().split())
        if len(clean_text) < 12:
            return False, "Заявление слишком короткое (минимум 12 символов).", None
        if len(clean_text) > 900:
            return False, "Заявление слишком длинное (максимум 900 символов).", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT citizen_job, education, reputation FROM users WHERE user_id = ?",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None
            if str(user["citizen_job"] or "").strip():
                await db.rollback()
                return False, "Вы уже трудоустроены. Увольтесь перед новой заявкой.", None

            user_edu = int(user["education"] or 1)
            user_rep = float(user["reputation"] or 0)
            if user_edu < int(job["edu_required"]):
                await db.rollback()
                return False, f"Требуется образование {int(job['edu_required'])}+.", None
            if user_rep < float(job["rep_required"]):
                await db.rollback()
                return False, f"Требуется репутация {float(job['rep_required']):.1f}+.", None

            async with db.execute(
                "SELECT id FROM job_applications WHERE user_id = ? AND status = 'pending' LIMIT 1",
                (int(user_id),),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "У вас уже есть активная HR-заявка.", None

            cursor = await db.execute(
                """
                INSERT INTO job_applications
                (user_id, job_code, job_title, expected_salary, application_text, status, applied_date, reviewed_by, reviewed_date, review_note)
                VALUES (?, ?, ?, ?, ?, 'approved', ?, 0, ?, ?)
                """,
                (
                    int(user_id),
                    str(job["code"]),
                    str(job["title"]),
                    float(job["salary"]),
                    clean_text,
                    now,
                    now,
                    "Автоодобрение: соответствует требованиям вакансии",
                ),
            )
            app_id = int(cursor.lastrowid or 0)
            await db.execute(
                """
                UPDATE users
                SET citizen_job = ?, citizen_salary = ?, salary = ?, last_job_shift = NULL
                WHERE user_id = ?
                """,
                (
                    str(job["title"]),
                    float(job["salary"]),
                    float(job["salary"]),
                    int(user_id),
                ),
            )
            await db.commit()

        return True, "HR-заявление одобрено автоматически: вы приняты на должность.", app_id

    async def get_pending_job_applications(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 120))
        query = """
            SELECT ja.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ja.user_id AS TEXT)) AS applicant_name,
                   u.education,
                   u.reputation,
                   u.balance
            FROM job_applications ja
            LEFT JOIN users u ON u.user_id = ja.user_id
            WHERE ja.status = 'pending'
            ORDER BY ja.applied_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def process_job_application(
        self,
        application_id: int,
        reviewer_id: int,
        approve: bool,
        note: str = "",
    ) -> tuple[bool, str, Optional[int]]:
        authority = await self.get_government_authority(reviewer_id)
        if authority not in {"president", "vice_president", "finance_minister", "minister"}:
            gov_org = await self.get_government_organization()
            gov_ok = False
            if gov_org:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT leader_id, deputy_id FROM organizations WHERE id = ? LIMIT 1",
                        (int(gov_org["id"]),),
                    ) as cursor:
                        org = await cursor.fetchone()
                    if org and int(reviewer_id) in {int(org["leader_id"] or 0), int(org["deputy_id"] or 0)}:
                        gov_ok = True
            if not gov_ok:
                return False, "Рассматривать HR-заявки может только правительство.", None

        now = datetime.now().isoformat()
        clean_note = " ".join((note or "").strip().split())[:500]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM job_applications WHERE id = ? LIMIT 1",
                (int(application_id),),
            ) as cursor:
                app = await cursor.fetchone()
            if not app:
                await db.rollback()
                return False, "Заявка не найдена.", None
            if str(app["status"] or "") != "pending":
                await db.rollback()
                return False, "Заявка уже обработана.", None

            async with db.execute(
                "SELECT citizen_job FROM users WHERE user_id = ? LIMIT 1",
                (int(app["user_id"]),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Кандидат не найден.", None
            if str(user["citizen_job"] or "").strip():
                await db.rollback()
                return False, "Кандидат уже трудоустроен.", None

            new_status = "approved" if approve else "rejected"
            await db.execute(
                """
                UPDATE job_applications
                SET status = ?, reviewed_by = ?, reviewed_date = ?, review_note = ?
                WHERE id = ?
                """,
                (new_status, int(reviewer_id), now, clean_note, int(application_id)),
            )

            if approve:
                await db.execute(
                    """
                    UPDATE users
                    SET citizen_job = ?, citizen_salary = ?, salary = ?, last_job_shift = NULL
                    WHERE user_id = ?
                    """,
                    (
                        str(app["job_title"] or "Госслужащий"),
                        float(app["expected_salary"] or 0),
                        float(app["expected_salary"] or 0),
                        int(app["user_id"]),
                    ),
                )
            await db.commit()

        return True, ("Кандидат принят на должность." if approve else "Заявка отклонена."), int(app["user_id"])

    async def get_user_job_task_status(self, user_id: int) -> Dict[str, Any]:
        query = """
            SELECT *
            FROM player_tasks
            WHERE user_id = ? AND task_code = 'job_shift_goal' AND status = 'active'
            ORDER BY assigned_date DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id),)) as cursor:
                row = await cursor.fetchone()
                active = dict(row) if row else None
        return {"active_task": active}

    async def work_citizen_shift(self, user_id: int) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now_dt = datetime.now()
        now = now_dt.isoformat()
        cooldown_minutes = 120

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT citizen_job, citizen_salary, last_job_shift, balance, reputation, education
                FROM users
                WHERE user_id = ?
                """,
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            if not str(user["citizen_job"] or "").strip():
                await db.rollback()
                return False, "Сначала устройтесь на работу через раздел вакансий.", None

            last_shift = str(user["last_job_shift"] or "")
            if last_shift:
                try:
                    last_dt = datetime.fromisoformat(last_shift)
                    remain = cooldown_minutes - int((now_dt - last_dt).total_seconds() // 60)
                    if remain > 0:
                        await db.rollback()
                        return False, f"Следующая смена доступна через {remain} мин.", {"cooldown_minutes": remain}
                except Exception:
                    pass

            salary = float(user["citizen_salary"] or 0)
            if salary <= 0:
                salary = 180.0
            education = int(user["education"] or 1)
            reputation = float(user["reputation"] or 50)
            base = salary
            edu_bonus = min(0.4, education * 0.02)
            rep_bonus = min(0.25, max(0.0, reputation / 500.0))
            payout = round(base * (1.0 + edu_bonus + rep_bonus), 2)
            new_balance = round(float(user["balance"] or 0) + payout, 2)
            new_reputation = round(min(100.0, reputation + 0.15), 2)

            await db.execute(
                "UPDATE users SET balance = ?, reputation = ?, last_job_shift = ? WHERE user_id = ?",
                (new_balance, new_reputation, now, int(user_id)),
            )

            async with db.execute(
                """
                SELECT *
                FROM player_tasks
                WHERE user_id = ? AND task_code = 'job_shift_goal' AND status = 'active'
                ORDER BY assigned_date DESC
                LIMIT 1
                """,
                (int(user_id),),
            ) as cursor:
                task = await cursor.fetchone()

            bonus_reward = 0.0
            task_progress = 0
            task_goal = 0
            next_task_goal = None
            if task:
                task_progress = int(task["progress"] or 0) + 1
                task_goal = max(1, int(task["goal"] or 1))
                if task_progress >= task_goal:
                    bonus_reward = round(float(task["reward"] or 0), 2)
                    new_balance = round(new_balance + bonus_reward, 2)
                    await db.execute(
                        "UPDATE users SET balance = ? WHERE user_id = ?",
                        (new_balance, int(user_id)),
                    )
                    await db.execute(
                        """
                        UPDATE player_tasks
                        SET status = 'completed', progress = ?, completed_date = ?
                        WHERE id = ?
                        """,
                        (task_goal, now, int(task["id"])),
                    )
                    next_task_goal = min(task_goal + 1, 8)
                    next_reward = round(max(1500.0, salary * (1.2 + next_task_goal * 0.08)), 2)
                    await db.execute(
                        """
                        INSERT INTO player_tasks
                        (user_id, task_code, title, description, status, progress, goal, reward, assigned_date, completed_date)
                        VALUES (?, 'job_shift_goal', ?, ?, 'active', 0, ?, ?, ?, NULL)
                        """,
                        (
                            int(user_id),
                            f"Рабочая цель: {next_task_goal} смен",
                            "Отработайте смены и заберите премию.",
                            next_task_goal,
                            next_reward,
                            now,
                        ),
                    )
                else:
                    await db.execute(
                        "UPDATE player_tasks SET progress = ? WHERE id = ?",
                        (task_progress, int(task["id"])),
                    )
            else:
                task_goal = 3
                task_progress = 1
                starter_reward = round(max(1200.0, salary * 1.4), 2)
                await db.execute(
                    """
                    INSERT INTO player_tasks
                    (user_id, task_code, title, description, status, progress, goal, reward, assigned_date, completed_date)
                    VALUES (?, 'job_shift_goal', ?, ?, 'active', ?, ?, ?, ?, NULL)
                    """,
                    (
                        int(user_id),
                        "Рабочая цель: 3 смены",
                        "Отработайте 3 смены и получите премию.",
                        task_progress,
                        task_goal,
                        starter_reward,
                        now,
                    ),
                )

            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="job_shift",
            details=f"Отработана смена: {user['citizen_job']}",
            value=payout + bonus_reward,
        )
        return True, "Смена успешно отработана.", {
            "payout": payout,
            "bonus_reward": bonus_reward,
            "new_balance": new_balance,
            "task_progress": task_progress,
            "task_goal": task_goal,
            "next_task_goal": next_task_goal,
            "cooldown_minutes": cooldown_minutes,
            "job_title": str(user["citizen_job"] or ""),
        }

    async def cancel_user_pending_job_application(self, user_id: int) -> tuple[bool, str]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT id
                FROM job_applications
                WHERE user_id = ? AND status = 'pending'
                ORDER BY applied_date DESC
                LIMIT 1
                """,
                (int(user_id),),
            ) as cursor:
                app = await cursor.fetchone()
            if not app:
                await db.rollback()
                return False, "Активной HR-заявки нет."

            await db.execute(
                """
                UPDATE job_applications
                SET status = 'cancelled', reviewed_by = ?, reviewed_date = ?, review_note = ?
                WHERE id = ?
                """,
                (int(user_id), now, "Отозвано соискателем", int(app["id"])),
            )
            await db.commit()
        return True, "HR-заявка отозвана."

    async def auto_review_user_job_application(
        self,
        user_id: int,
        min_wait_minutes: int = 1,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_wait = max(0, min(int(1 if min_wait_minutes is None else min_wait_minutes), 60))
        now_dt = datetime.now()
        now = now_dt.isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                """
                SELECT *
                FROM job_applications
                WHERE user_id = ? AND status = 'pending'
                ORDER BY applied_date ASC
                LIMIT 1
                """,
                (int(user_id),),
            ) as cursor:
                app = await cursor.fetchone()
            if not app:
                await db.rollback()
                return False, "Заявок на авто-рассмотрение нет.", None

            applied_dt = _parse_iso_datetime(app["applied_date"])
            if applied_dt:
                remain = safe_wait - int((now_dt - applied_dt).total_seconds() // 60)
                if remain > 0:
                    await db.rollback()
                    return False, f"Заявка еще на рассмотрении ({remain} мин).", {"remaining_minutes": remain}

            async with db.execute(
                "SELECT citizen_job, education, reputation FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            if str(user["citizen_job"] or "").strip():
                await db.execute(
                    """
                    UPDATE job_applications
                    SET status = 'rejected', reviewed_by = 0, reviewed_date = ?, review_note = ?
                    WHERE id = ?
                    """,
                    (now, "Авто-отклонение: соискатель уже трудоустроен", int(app["id"])),
                )
                await db.commit()
                return True, "Заявка закрыта: вы уже трудоустроены.", {
                    "approved": False,
                    "job_title": str(app["job_title"] or ""),
                }

            job = self.get_citizen_job(str(app["job_code"] or ""))
            req_edu = int((job or {}).get("edu_required") or 1)
            req_rep = float((job or {}).get("rep_required") or 0)
            user_edu = int(user["education"] or 1)
            user_rep = float(user["reputation"] or 0)

            if req_edu <= 1 and req_rep <= 5:
                score = 1.0
                approved = True
            else:
                score = 0.58
                score += min(0.30, max(0.0, (user_edu - req_edu) * 0.07))
                score += min(0.22, max(0.0, (user_rep - req_rep) / 200.0))
                if req_edu <= 2:
                    score += 0.08
                if user_edu >= req_edu + 1 and user_rep >= req_rep + 8:
                    score += 0.12
                score = max(0.25, min(0.97, score))
                approved = random.random() < score

            await db.execute(
                """
                UPDATE job_applications
                SET status = ?, reviewed_by = 0, reviewed_date = ?, review_note = ?
                WHERE id = ?
                """,
                (
                    "approved" if approved else "rejected",
                    now,
                    "Авто-рассмотрение HR",
                    int(app["id"]),
                ),
            )
            if approved:
                await db.execute(
                    """
                    UPDATE users
                    SET citizen_job = ?, citizen_salary = ?, salary = ?, last_job_shift = NULL
                    WHERE user_id = ?
                    """,
                    (
                        str(app["job_title"] or "Госслужащий"),
                        float(app["expected_salary"] or 0),
                        float(app["expected_salary"] or 0),
                        int(user_id),
                    ),
                )
            await db.commit()

        return True, ("Заявка одобрена автоматически." if approved else "Заявка отклонена автоматически."), {
            "approved": approved,
            "job_title": str(app["job_title"] or ""),
            "score": round(score, 3),
        }

    async def run_microjob(
        self,
        user_id: int,
        job_key: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_key = (job_key or "").strip().lower()
        jobs = {
            "courier": {"title": "Курьерский рейс", "min": 900, "max": 2200, "cooldown": 7, "rep": 0.18},
            "taxi": {"title": "Ночная смена такси", "min": 1100, "max": 2500, "cooldown": 9, "rep": 0.15},
            "repair": {"title": "Срочный ремонт", "min": 1200, "max": 2800, "cooldown": 10, "rep": 0.2},
            "freelance": {"title": "Фриланс-заказ", "min": 1300, "max": 3100, "cooldown": 11, "rep": 0.22},
            "street_trade": {"title": "Уличная торговля", "min": 1000, "max": 2400, "cooldown": 8, "rep": 0.12},
            "delivery_plus": {"title": "Экспресс-доставка", "min": 1400, "max": 3300, "cooldown": 12, "rep": 0.24},
            "warehouse": {"title": "Складская инвентаризация", "min": 1150, "max": 2650, "cooldown": 9, "rep": 0.17},
            "stream": {"title": "Локальный стрим", "min": 800, "max": 3600, "cooldown": 13, "rep": 0.21},
            "assistant": {"title": "Персональный ассистент", "min": 1250, "max": 2950, "cooldown": 10, "rep": 0.19},
        }
        cfg = jobs.get(safe_key)
        if not cfg:
            return False, "Неизвестная микроподработка.", None

        allowed, remain = await self.check_and_set_user_cooldown(
            user_id,
            f"micro:{safe_key}",
            int(cfg["cooldown"]),
        )
        if not allowed:
            return False, f"Следующая попытка через {remain} мин.", {"cooldown_minutes": remain}

        user = await self.get_user(user_id)
        if not user:
            return False, "Игрок не найден.", None

        payout = float(random.randint(int(cfg["min"]), int(cfg["max"])))
        critical = random.random() < 0.12
        if critical:
            payout = round(payout * 1.55, 2)
        reputation = float(user.get("reputation") or 50)
        new_reputation = round(min(100.0, reputation + float(cfg["rep"])), 2)
        new_balance = round(float(user.get("balance") or 0) + payout, 2)
        await self.update_user(user_id, balance=new_balance, reputation=new_reputation)
        await self.log_player_activity(
            user_id=user_id,
            activity_type="microjob",
            details=f"Выполнено: {cfg['title']}",
            value=payout,
        )

        return True, "Микроподработка завершена.", {
            "job_key": safe_key,
            "job_title": cfg["title"],
            "payout": payout,
            "critical": critical,
            "new_balance": new_balance,
            "cooldown_minutes": int(cfg["cooldown"]),
        }

    async def list_casinos(self, casino_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        where_parts = ["c.status = 'active'"]
        params: List[Any] = []
        if casino_type:
            where_parts.append("c.casino_type = ?")
            params.append((casino_type or "").strip().lower())
        params.append(safe_limit)
        query = f"""
            SELECT c.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(c.owner_id AS TEXT)) AS owner_name
            FROM casinos c
            LEFT JOIN users u ON u.user_id = c.owner_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY c.casino_type ASC, c.name ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_private_casino(
        self,
        owner_id: int,
        name: str,
        min_bet: float = 500.0,
        max_bet: float = 500_000.0,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        clean_name = " ".join((name or "").strip().split())
        if len(clean_name) < 4:
            return False, "Название казино слишком короткое.", None
        if len(clean_name) > 70:
            return False, "Название казино слишком длинное.", None

        safe_min_bet = max(100.0, min(float(min_bet or 500.0), 50_000.0))
        safe_max_bet = max(safe_min_bet * 5, min(float(max_bet or 500_000.0), 3_000_000.0))
        registration_fee = 350_000.0
        start_balance = 2_400_000.0
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (int(owner_id),)) as cursor:
                owner = await cursor.fetchone()
            if not owner:
                await db.rollback()
                return False, "Владелец не найден.", None
            async with db.execute("SELECT id FROM casinos WHERE lower(name) = lower(?) LIMIT 1", (clean_name,)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Казино с таким названием уже существует.", None

            balance = float(owner["balance"] or 0)
            if balance < registration_fee:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${registration_fee:,.2f}.", None

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (round(balance - registration_fee, 2), int(owner_id)))
            cursor = await db.execute(
                """
                INSERT INTO casinos
                (name, owner_id, casino_type, status, min_bet, max_bet, house_edge, balance, created_date)
                VALUES (?, ?, 'private', 'active', ?, ?, 0.03, ?, ?)
                """,
                (clean_name, int(owner_id), safe_min_bet, safe_max_bet, start_balance, now),
            )
            casino_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=owner_id,
            activity_type="casino_open",
            details=f"Открыто частное казино '{clean_name}'",
            value=registration_fee,
        )
        return True, "Частное казино успешно открыто.", {"casino_id": casino_id, "registration_fee": registration_fee}

    async def play_casino_game(
        self,
        user_id: int,
        casino_id: int,
        game_type: str,
        prediction: str,
        bet_amount: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_bet = round(float(bet_amount or 0), 2)
        if safe_bet <= 0:
            return False, "Ставка должна быть больше нуля.", None
        safe_game = (game_type or "").strip().lower()
        if safe_game not in {"coin", "dice", "slots"}:
            return False, "Неизвестная игра.", None
        safe_prediction = (prediction or "").strip().lower()
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None
            async with db.execute("SELECT * FROM casinos WHERE id = ? AND status = 'active'", (int(casino_id),)) as cursor:
                casino = await cursor.fetchone()
            if not casino:
                await db.rollback()
                return False, "Казино не найдено.", None

            min_bet = float(casino["min_bet"] or 0)
            max_bet = float(casino["max_bet"] or 0)
            if safe_bet < min_bet or safe_bet > max_bet:
                await db.rollback()
                return False, f"Ставка должна быть от ${min_bet:,.0f} до ${max_bet:,.0f}.", None
            user_balance = float(user["balance"] or 0)
            if user_balance < safe_bet:
                await db.rollback()
                return False, "Недостаточно средств для ставки.", None

            roll_value = random.randint(1, 100)
            payout = 0.0
            result = "lose"
            if safe_game == "coin":
                if safe_prediction not in {"heads", "tails"}:
                    await db.rollback()
                    return False, "Для монетки выберите heads или tails.", None
                target = 1 if safe_prediction == "heads" else 0
                coin_roll = random.randint(0, 1)
                roll_value = coin_roll
                if coin_roll == target and random.random() < 0.98:
                    payout = round(safe_bet * 1.92, 2)
                    result = "win"
            elif safe_game == "dice":
                if safe_prediction not in {"high", "low"}:
                    await db.rollback()
                    return False, "Для кубика выберите high или low.", None
                dice_roll = random.randint(1, 6)
                roll_value = dice_roll
                if (safe_prediction == "high" and dice_roll >= 4) or (safe_prediction == "low" and dice_roll <= 3):
                    if random.random() < 0.96:
                        payout = round(safe_bet * 1.88, 2)
                        result = "win"
            else:
                if roll_value <= 6:
                    payout = round(safe_bet * 6.0, 2)
                    result = "jackpot"
                elif roll_value <= 26:
                    payout = round(safe_bet * 2.1, 2)
                    result = "win"

            casino_balance = float(casino["balance"] or 0)
            max_payout = round(casino_balance + safe_bet, 2)
            if payout > max_payout:
                payout = max_payout
                result = "limited_win"

            new_user_balance = round(user_balance - safe_bet + payout, 2)
            new_casino_balance = round(casino_balance + safe_bet - payout, 2)
            profit = round(payout - safe_bet, 2)

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_user_balance, int(user_id)))
            await db.execute("UPDATE casinos SET balance = ? WHERE id = ?", (new_casino_balance, int(casino_id)))
            await db.execute(
                """
                INSERT INTO casino_games
                (casino_id, user_id, game_type, prediction, bet_amount, roll_value, payout, result, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(casino_id),
                    int(user_id),
                    safe_game,
                    safe_prediction,
                    safe_bet,
                    int(roll_value),
                    float(payout),
                    result,
                    now,
                ),
            )
            await db.commit()

        if profit > 0:
            await self.log_player_activity(
                user_id=user_id,
                activity_type="casino_win",
                details=f"Выигрыш в казино #{int(casino_id)} ({safe_game})",
                value=profit,
            )

        return True, "Игра завершена.", {
            "result": result,
            "roll_value": roll_value,
            "bet": safe_bet,
            "payout": payout,
            "profit": profit,
            "new_balance": new_user_balance,
        }

    async def get_user_recent_casino_games(self, user_id: int, limit: int = 15) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 15), 100))
        query = """
            SELECT cg.*,
                   c.name AS casino_name
            FROM casino_games cg
            LEFT JOIN casinos c ON c.id = cg.casino_id
            WHERE cg.user_id = ?
            ORDER BY cg.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_group_casino_duel(
        self,
        challenger_id: int,
        opponent_id: int,
        chat_id: int,
        game_type: str,
        target_value: int,
        bet_amount: float,
        challenge_message_id: Optional[int] = None,
        expires_minutes: int = 5,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_game = (game_type or "").strip().lower()
        cfg = {
            "dice": {"min": 1, "max": 6},
            "slots": {"min": 1, "max": 64},
            "basketball": {"min": 1, "max": 5},
        }.get(safe_game)
        if not cfg:
            return False, "Неизвестный тип игры.", None

        if safe_game == "dice":
            # Для костей параметр target оставлен только ради совместимости команды.
            try:
                safe_target = int(target_value)
            except Exception:
                safe_target = 0
        else:
            try:
                safe_target = int(target_value)
            except Exception:
                return False, "Некорректное целевое число.", None
            if safe_target < int(cfg["min"]) or safe_target > int(cfg["max"]):
                return False, f"Для этой игры число должно быть от {cfg['min']} до {cfg['max']}.", None

        safe_bet = round(float(bet_amount or 0), 2)
        if safe_bet < 10:
            return False, "Минимальная ставка: $10.", None
        if safe_bet > 100_000_000:
            return False, "Слишком большая ставка.", None
        if int(challenger_id) == int(opponent_id):
            return False, "Нельзя вызвать себя на дуэль.", None

        now_dt = datetime.now()
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(minutes=max(1, min(int(expires_minutes or 5), 30)))).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT user_id, balance FROM users WHERE user_id IN (?, ?)",
                (int(challenger_id), int(opponent_id)),
            ) as cursor:
                users = await cursor.fetchall()
            users_map = {int(row["user_id"]): dict(row) for row in users}
            if int(challenger_id) not in users_map or int(opponent_id) not in users_map:
                await db.rollback()
                return False, "Оба игрока должны иметь профиль в боте.", None

            challenger_balance = float(users_map[int(challenger_id)]["balance"] or 0)
            if challenger_balance < safe_bet:
                await db.rollback()
                return False, "Недостаточно средств для создания дуэли.", None

            async with db.execute(
                """
                SELECT id
                FROM group_casino_duels
                WHERE chat_id = ?
                  AND status = 'pending'
                  AND expires_at > ?
                  AND (
                        (challenger_id = ? AND opponent_id = ?)
                        OR
                        (challenger_id = ? AND opponent_id = ?)
                      )
                LIMIT 1
                """,
                (int(chat_id), now, int(challenger_id), int(opponent_id), int(opponent_id), int(challenger_id)),
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Между этими игроками уже есть активный вызов.", None

            cursor = await db.execute(
                """
                INSERT INTO group_casino_duels
                (chat_id, challenger_id, opponent_id, game_type, target_value, bet_amount, status, challenge_message_id, created_date, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    int(chat_id),
                    int(challenger_id),
                    int(opponent_id),
                    safe_game,
                    safe_target,
                    safe_bet,
                    int(challenge_message_id) if challenge_message_id else None,
                    now,
                    expires_at,
                ),
            )
            duel_id = int(cursor.lastrowid or 0)
            await db.commit()

        return True, "Вызов создан.", {
            "duel_id": duel_id,
            "chat_id": int(chat_id),
            "challenger_id": int(challenger_id),
            "opponent_id": int(opponent_id),
            "game_type": safe_game,
            "target_value": safe_target,
            "bet_amount": safe_bet,
            "expires_at": expires_at,
        }

    async def get_group_casino_duel(self, duel_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT d.*,
                   COALESCE(NULLIF(cu.nickname, ''), NULLIF(cu.full_name, ''), NULLIF(cu.username, ''), CAST(d.challenger_id AS TEXT)) AS challenger_name,
                   COALESCE(NULLIF(ou.nickname, ''), NULLIF(ou.full_name, ''), NULLIF(ou.username, ''), CAST(d.opponent_id AS TEXT)) AS opponent_name
            FROM group_casino_duels d
            LEFT JOIN users cu ON cu.user_id = d.challenger_id
            LEFT JOIN users ou ON ou.user_id = d.opponent_id
            WHERE d.id = ?
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(duel_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def reject_group_casino_duel(
        self,
        duel_id: int,
        actor_id: int,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM group_casino_duels WHERE id = ? LIMIT 1", (int(duel_id),)) as cursor:
                row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return False, "Вызов не найден.", None
            duel = dict(row)
            if str(duel.get("status") or "") != "pending":
                await db.rollback()
                return False, "Этот вызов уже неактивен.", duel
            if int(actor_id) not in {int(duel.get("challenger_id") or 0), int(duel.get("opponent_id") or 0)}:
                await db.rollback()
                return False, "Только участники могут отклонять вызов.", None
            if int(actor_id) == int(duel.get("challenger_id") or 0):
                new_status = "cancelled"
                msg = "Вызов отменен инициатором."
            else:
                new_status = "rejected"
                msg = "Вызов отклонен соперником."
            await db.execute(
                "UPDATE group_casino_duels SET status = ?, resolved_date = ? WHERE id = ?",
                (new_status, now, int(duel_id)),
            )
            await db.commit()
            duel["status"] = new_status
        return True, msg, duel

    async def resolve_group_casino_duel(
        self,
        duel_id: int,
        accepter_id: int,
        roll_value: Optional[int] = None,
        challenger_roll: Optional[int] = None,
        opponent_roll: Optional[int] = None,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT * FROM group_casino_duels WHERE id = ? LIMIT 1", (int(duel_id),)) as cursor:
                row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return False, "Вызов не найден.", None
            duel = dict(row)
            if str(duel.get("status") or "") != "pending":
                await db.rollback()
                return False, "Этот вызов уже закрыт.", duel
            if int(duel.get("opponent_id") or 0) != int(accepter_id):
                await db.rollback()
                return False, "Принять вызов может только указанный соперник.", None
            if str(duel.get("expires_at") or "") <= now:
                await db.execute(
                    "UPDATE group_casino_duels SET status = 'expired', resolved_date = ? WHERE id = ?",
                    (now, int(duel_id)),
                )
                await db.commit()
                duel["status"] = "expired"
                return False, "Вызов уже истек.", duel

            challenger_id = int(duel.get("challenger_id") or 0)
            opponent_id = int(duel.get("opponent_id") or 0)
            safe_bet = round(float(duel.get("bet_amount") or 0), 2)
            target = int(duel.get("target_value") or 0)
            game_type = str(duel.get("game_type") or "").strip().lower()

            async with db.execute(
                "SELECT user_id, balance FROM users WHERE user_id IN (?, ?)",
                (challenger_id, opponent_id),
            ) as cursor:
                users = await cursor.fetchall()
            users_map = {int(r["user_id"]): dict(r) for r in users}
            if challenger_id not in users_map or opponent_id not in users_map:
                await db.rollback()
                return False, "Один из игроков не найден.", None

            c_balance = round(float(users_map[challenger_id]["balance"] or 0), 2)
            o_balance = round(float(users_map[opponent_id]["balance"] or 0), 2)
            if c_balance < safe_bet:
                await db.rollback()
                return False, "У инициатора недостаточно средств на ставку.", None
            if o_balance < safe_bet:
                await db.rollback()
                return False, "У соперника недостаточно средств на ставку.", None

            if game_type == "dice":
                try:
                    c_roll = int(challenger_roll)
                    o_roll = int(opponent_roll)
                except Exception:
                    await db.rollback()
                    return False, "Некорректные броски для дуэли в кости.", None

                if not (1 <= c_roll <= 6 and 1 <= o_roll <= 6):
                    await db.rollback()
                    return False, "Значения бросков для костей должны быть от 1 до 6.", None
                if c_roll == o_roll:
                    await db.rollback()
                    return False, "Ничья. Требуется переброс.", None

                challenger_wins = c_roll > o_roll
                safe_roll = c_roll if challenger_wins else o_roll
            else:
                cfg = {
                    "slots": {"min": 1, "max": 64},
                    "basketball": {"min": 1, "max": 5},
                }.get(game_type, {"min": 1, "max": 64})
                try:
                    safe_roll = int(roll_value)
                except Exception:
                    await db.rollback()
                    return False, "Некорректное значение броска.", None
                if safe_roll < int(cfg["min"]) or safe_roll > int(cfg["max"]):
                    await db.rollback()
                    return False, f"Значение броска должно быть от {cfg['min']} до {cfg['max']}.", None

                c_roll = None
                o_roll = None
                challenger_wins = safe_roll == target

            winner_id = challenger_id if challenger_wins else opponent_id
            loser_id = opponent_id if challenger_wins else challenger_id

            # Комиссия казино: 1% от ставки. Проигравший теряет full bet,
            # победитель получает ставку за вычетом комиссии.
            house_fee = round(safe_bet * 0.01, 2)
            winner_gain = round(max(0.0, safe_bet - house_fee), 2)
            loser_loss = safe_bet

            if winner_id == challenger_id:
                c_balance = round(c_balance + winner_gain, 2)
                o_balance = round(o_balance - loser_loss, 2)
                winner_new_balance = c_balance
                loser_new_balance = o_balance
            else:
                c_balance = round(c_balance - loser_loss, 2)
                o_balance = round(o_balance + winner_gain, 2)
                winner_new_balance = o_balance
                loser_new_balance = c_balance

            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (c_balance, challenger_id))
            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (o_balance, opponent_id))

            government_budget_after: float | None = None
            if house_fee > 0:
                async with db.execute(
                    """
                    SELECT id, budget
                    FROM organizations
                    WHERE lower(COALESCE(type, '')) = 'government'
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ) as cursor:
                    gov_row = await cursor.fetchone()
                if not gov_row:
                    async with db.execute(
                        "SELECT id, budget FROM organizations WHERE name = 'Правительство' ORDER BY id ASC LIMIT 1"
                    ) as cursor:
                        gov_row = await cursor.fetchone()
                if gov_row:
                    gov_org_id = int(gov_row["id"] or 0)
                    gov_budget_before = round(float(gov_row["budget"] or 0), 2)
                    government_budget_after = round(gov_budget_before + house_fee, 2)
                    await db.execute(
                        "UPDATE organizations SET budget = ? WHERE id = ?",
                        (government_budget_after, gov_org_id),
                    )
            await db.execute(
                """
                UPDATE group_casino_duels
                SET status = 'resolved',
                    roll_value = ?,
                    winner_id = ?,
                    loser_id = ?,
                    resolved_date = ?
                WHERE id = ?
                """,
                (safe_roll, winner_id, loser_id, now, int(duel_id)),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=winner_id,
            activity_type="pvp_casino_win",
            details=f"Победа в дуэли ({duel.get('game_type')})",
            value=winner_gain,
        )
        await self.log_player_activity(
            user_id=loser_id,
            activity_type="pvp_casino_lose",
            details=f"Поражение в дуэли ({duel.get('game_type')})",
            value=loser_loss,
        )

        duel["status"] = "resolved"
        duel["roll_value"] = safe_roll
        duel["winner_id"] = winner_id
        duel["loser_id"] = loser_id
        return True, "Дуэль завершена.", {
            **duel,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "winner_new_balance": winner_new_balance,
            "loser_new_balance": loser_new_balance,
            "bet_amount": safe_bet,
            "winner_gain": winner_gain,
            "loser_loss": loser_loss,
            "house_fee": house_fee,
            "commission_rate": 0.01,
            "government_budget_after": government_budget_after,
            "target_value": target,
            "roll_value": safe_roll,
            "challenger_roll": c_roll,
            "opponent_roll": o_roll,
        }

    async def run_side_hustle(
        self,
        user_id: int,
        hustle_type: str,
        variant: str,
        mini_success: bool = False,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_type = (hustle_type or "").strip().lower()
        if safe_type not in {"legal", "illegal"}:
            return False, "Неизвестный тип подработки.", None
        safe_variant = (variant or "").strip().lower()[:40] or "generic"
        now_dt = datetime.now()
        now = now_dt.isoformat()

        user = await self.get_user(user_id)
        if not user:
            return False, "Игрок не найден.", None

        gov = await self.get_government_system()
        role_lc = str(user.get("role") or "").strip().lower()
        is_president_role = "президент" in role_lc and "вице" not in role_lc
        is_president = bool(int((gov or {}).get("current_leader_id") or 0) == int(user_id) or is_president_role)

        # Личный кулдаун (по каждому игроку отдельно), без глобальной блокировки.
        cooldown_minutes = 12 if safe_type == "legal" else 18
        last_field = "last_side_hustle_at" if safe_type == "legal" else "last_illegal_hustle_at"
        last_raw = str(user.get(last_field) or "")
        if last_raw:
            try:
                last_dt = datetime.fromisoformat(last_raw)
                remain = cooldown_minutes - int((now_dt - last_dt).total_seconds() // 60)
                if remain > 0:
                    return False, f"Кулдаун подработки: еще {remain} мин.", {"cooldown_minutes": remain}
            except Exception:
                pass

        balance = float(user.get("balance") or 0)
        shadow_balance = float(user.get("shadow_balance") or 0)
        reputation = float(user.get("reputation") or 50)
        reputation_before = reputation
        risk = random.randint(4, 18) if safe_type == "legal" else random.randint(28, 82)
        fail_chance = 0.18 if safe_type == "legal" else 0.36
        if mini_success:
            fail_chance = max(0.05, fail_chance - 0.12)

        success = random.random() > fail_chance
        result = "success" if success else "fail"
        payout_total = 0.0
        visible_gain = 0.0
        shadow_gain = 0.0
        ban_until: Optional[str] = None

        if safe_type == "legal":
            base = random.randint(1_400, 3_000)
            if mini_success:
                base = int(base * 1.22)
            if success:
                payout_total = float(base)
                visible_gain = payout_total
                reputation = min(100.0, reputation + 0.25)
            else:
                payout_total = float(max(400, int(base * 0.35)))
                visible_gain = payout_total
                reputation = max(0.0, reputation - 0.1)
        else:
            base = random.randint(1_700, 3_300)
            if mini_success:
                base = int(base * 1.20)
            if success:
                payout_total = float(base)
                visible_gain = round(payout_total * 0.58, 2)
                shadow_gain = round(payout_total - visible_gain, 2)
                reputation = max(0.0, reputation - 0.35)
            else:
                fine = random.randint(600, 2_400)
                payout_total = -float(fine)
                visible_gain = payout_total
                reputation = max(0.0, reputation - 0.8)
                if random.random() < 0.35:
                    ban_until = (now_dt + timedelta(minutes=25)).isoformat()

        if is_president:
            if payout_total < 0:
                payout_total = 0.0
                visible_gain = 0.0
            if reputation < reputation_before:
                reputation = reputation_before
            ban_until = None

        new_balance = round(max(0.0, balance + visible_gain), 2)
        new_shadow = round(max(0.0, shadow_balance + shadow_gain), 2)
        updates: Dict[str, Any] = {
            "balance": new_balance,
            "shadow_balance": new_shadow,
            "reputation": round(reputation, 2),
            last_field: now,
        }
        if ban_until:
            updates["action_banned_until"] = ban_until
        await self.update_user(user_id, **updates)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO side_hustle_runs
                (user_id, hustle_type, variant, result, payout, risk, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(user_id), safe_type, safe_variant, result, float(payout_total), int(risk), now),
            )
            if safe_type == "illegal":
                await db.execute(
                    """
                    INSERT INTO corruption_ops
                    (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                    VALUES (?, NULL, 'street_scheme', ?, ?, 'logged', ?, ?)
                    """,
                    (
                        int(user_id),
                        float(payout_total),
                        int(risk),
                        f"Теневая подработка: {safe_variant}",
                        now,
                    ),
                )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type=f"side_hustle_{safe_type}",
            details=f"Подработка {safe_variant}: {result}",
            value=abs(float(payout_total)),
        )
        return True, "Подработка завершена.", {
            "hustle_type": safe_type,
            "variant": safe_variant,
            "result": result,
            "payout": round(payout_total, 2),
            "risk": risk,
            "mini_success": mini_success,
            "new_balance": new_balance,
            "new_shadow_balance": new_shadow,
            "ban_until": ban_until,
        }

    async def list_gangs(self, limit: int = 40) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 40), 200))
        query = """
            SELECT g.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(g.leader_id AS TEXT)) AS leader_name,
                   COALESCE(gm.members_count, 0) AS members_count
            FROM gangs g
            LEFT JOIN users u ON u.user_id = g.leader_id
            LEFT JOIN (
                SELECT gang_id, COUNT(*) AS members_count
                FROM gang_members
                GROUP BY gang_id
            ) gm ON gm.gang_id = g.id
            WHERE g.status = 'active'
            ORDER BY g.reputation DESC, g.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_gang(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT g.*,
                   gm.role AS member_role,
                   gm.join_date AS member_since
            FROM gang_members gm
            JOIN gangs g ON g.id = gm.gang_id
            WHERE gm.user_id = ? AND g.status = 'active'
            ORDER BY gm.join_date DESC
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(user_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_gang(
        self,
        leader_id: int,
        name: str,
        territory: str = "",
    ) -> tuple[bool, str, Optional[int]]:
        clean_name = " ".join((name or "").strip().split())
        if len(clean_name) < 3:
            return False, "Название банды слишком короткое.", None
        if len(clean_name) > 60:
            return False, "Название банды слишком длинное.", None
        if await self.get_user_gang(leader_id):
            return False, "Вы уже состоите в банде.", None

        user = await self.get_user(leader_id)
        if not user:
            return False, "Игрок не найден.", None
        fee = 120_000.0
        balance = float(user.get("balance") or 0)
        if balance < fee:
            return False, f"Недостаточно средств. Нужно ${fee:,.0f}.", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT id FROM gangs WHERE lower(name) = lower(?) LIMIT 1", (clean_name,)) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False, "Банда с таким названием уже существует.", None
            await db.execute("UPDATE users SET balance = ?, gang_member = 1 WHERE user_id = ?", (round(balance - fee, 2), int(leader_id)))
            cursor = await db.execute(
                """
                INSERT INTO gangs (name, leader_id, territory, reputation, status, created_date)
                VALUES (?, ?, ?, 55, 'active', ?)
                """,
                (clean_name, int(leader_id), (territory or "").strip()[:100], now),
            )
            gang_id = int(cursor.lastrowid or 0)
            await db.execute(
                "INSERT INTO gang_members (gang_id, user_id, role, join_date) VALUES (?, ?, 'Лидер', ?)",
                (gang_id, int(leader_id), now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=leader_id,
            activity_type="gang_create",
            details=f"Создана банда '{clean_name}'",
            value=fee,
        )
        return True, "Банда создана.", gang_id

    async def join_gang(self, user_id: int, gang_id: int) -> tuple[bool, str]:
        if await self.get_user_gang(user_id):
            return False, "Вы уже состоите в банде."
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT id FROM gangs WHERE id = ? AND status = 'active'", (int(gang_id),)) as cursor:
                gang = await cursor.fetchone()
            if not gang:
                await db.rollback()
                return False, "Банда не найдена."
            await db.execute(
                "INSERT INTO gang_members (gang_id, user_id, role, join_date) VALUES (?, ?, 'Участник', ?)",
                (int(gang_id), int(user_id), now),
            )
            await db.execute("UPDATE users SET gang_member = 1 WHERE user_id = ?", (int(user_id),))
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="gang_join",
            details=f"Вступление в банду #{int(gang_id)}",
            value=3_000,
        )
        return True, "Вы вступили в банду."

    async def get_gang_cartel(self, gang_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM drug_cartels WHERE gang_id = ?", (int(gang_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_drug_cartel(
        self,
        actor_id: int,
        gang_id: int,
        name: str,
    ) -> tuple[bool, str]:
        gang = await self.get_user_gang(actor_id)
        if not gang or int(gang.get("id") or 0) != int(gang_id):
            return False, "Вы не состоите в этой банде."
        if int(gang.get("leader_id") or 0) != int(actor_id):
            return False, "Только лидер банды может создать картель."
        if await self.get_gang_cartel(gang_id):
            return False, "У этой банды уже есть картель."

        clean_name = " ".join((name or "").strip().split())
        if len(clean_name) < 3:
            clean_name = f"Картель банды {gang.get('name', gang_id)}"
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO drug_cartels
                (gang_id, name, stock, purity, laundering_level, status, created_date)
                VALUES (?, ?, 60, 52, 1, 'active', ?)
                """,
                (int(gang_id), clean_name[:80], now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="cartel_created",
            details=f"Создан картель: {clean_name}",
            value=40_000,
        )
        return True, "Наркокартель сформирован."

    async def run_cartel_operation(
        self,
        actor_id: int,
        operation_type: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        user_gang = await self.get_user_gang(actor_id)
        if not user_gang:
            return False, "Вы не состоите в банде.", None
        gang_id = int(user_gang.get("id") or 0)
        cartel = await self.get_gang_cartel(gang_id)
        if not cartel:
            return False, "У вашей банды нет активного картеля.", None

        op = (operation_type or "").strip().lower()
        if op not in {"produce", "smuggle", "launder"}:
            return False, "Неизвестная операция.", None

        now = datetime.now().isoformat()
        stock = float(cartel.get("stock") or 0)
        purity = float(cartel.get("purity") or 50)
        laundering = int(cartel.get("laundering_level") or 1)

        user = await self.get_user(actor_id) or {}
        balance = float(user.get("balance") or 0)
        shadow = float(user.get("shadow_balance") or 0)
        reputation = float(user.get("reputation") or 50)

        delta_stock = 0.0
        delta_balance = 0.0
        delta_shadow = 0.0
        delta_purity = 0.0
        delta_laundering = 0
        risk = random.randint(45, 88)
        result = "success"

        if op == "produce":
            produced = random.uniform(18, 45)
            if random.random() < 0.2:
                result = "incident"
                produced *= 0.4
                reputation = max(0.0, reputation - 0.5)
            delta_stock = round(produced, 2)
            delta_purity = round(random.uniform(-2.5, 2.0), 2)
            delta_shadow = round(random.uniform(900, 1900), 2)
        elif op == "smuggle":
            if stock < 10:
                return False, "Недостаточно товара на складе картеля.", None
            sold = min(stock, random.uniform(10, 35))
            gross = sold * random.uniform(650, 1300) * (purity / 100)
            if random.random() < 0.28:
                result = "seized"
                gross *= 0.35
                reputation = max(0.0, reputation - 1.0)
            delta_stock = -round(sold, 2)
            delta_shadow = round(gross * 0.82, 2)
            delta_balance = round(gross * 0.18, 2)
        else:
            if shadow < 1200:
                return False, "Недостаточно теневых средств для отмывания.", None
            wash = min(shadow, random.uniform(1200, 12000))
            efficiency = min(0.92, 0.48 + laundering * 0.09)
            converted = wash * efficiency
            if random.random() < 0.18:
                result = "trace"
                converted *= 0.55
                reputation = max(0.0, reputation - 0.7)
            delta_shadow = -round(wash, 2)
            delta_balance = round(converted, 2)
            if random.random() < 0.32:
                delta_laundering = 1

        new_stock = round(max(0.0, stock + delta_stock), 2)
        new_purity = round(min(98.0, max(18.0, purity + delta_purity)), 2)
        new_laundering = max(1, laundering + delta_laundering)
        new_balance = round(max(0.0, balance + delta_balance), 2)
        new_shadow = round(max(0.0, shadow + delta_shadow), 2)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "UPDATE drug_cartels SET stock = ?, purity = ?, laundering_level = ? WHERE gang_id = ?",
                (new_stock, new_purity, new_laundering, gang_id),
            )
            await db.execute(
                "UPDATE users SET balance = ?, shadow_balance = ?, reputation = ? WHERE user_id = ?",
                (new_balance, new_shadow, round(reputation, 2), int(actor_id)),
            )
            await db.execute(
                """
                INSERT INTO corruption_ops
                (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                VALUES (?, NULL, ?, ?, ?, 'logged', ?, ?)
                """,
                (
                    int(actor_id),
                    f"cartel_{op}",
                    round(max(0.0, delta_balance + max(0.0, delta_shadow)), 2),
                    int(risk),
                    f"Результат операции: {result}",
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="cartel_operation",
            details=f"Картельная операция {op}: {result}",
            value=max(0.0, delta_balance + max(0.0, delta_shadow)),
        )
        return True, "Операция картеля завершена.", {
            "operation": op,
            "result": result,
            "risk": risk,
            "delta_stock": delta_stock,
            "delta_balance": delta_balance,
            "delta_shadow": delta_shadow,
            "new_stock": new_stock,
            "new_balance": new_balance,
            "new_shadow_balance": new_shadow,
        }

    async def _ensure_market_contracts_table(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS market_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER NOT NULL,
                    assignee_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    reward REAL NOT NULL DEFAULT 0,
                    escrow_amount REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    deadline_date TEXT,
                    created_date TEXT NOT NULL,
                    claimed_date TEXT,
                    completed_date TEXT,
                    cancelled_date TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_contracts_status_created ON market_contracts(status, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_contracts_creator ON market_contracts(creator_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_contracts_assignee ON market_contracts(assignee_id)"
            )
            await db.commit()

    async def create_market_contract(
        self,
        creator_id: int,
        title: str,
        description: str,
        reward: float,
        deadline_hours: int = 48,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_market_contracts_table()

        clean_title = " ".join((title or "").strip().split())
        clean_description = " ".join((description or "").strip().split())
        safe_reward = round(float(reward or 0), 2)
        if len(clean_title) < 4:
            return False, "Название контракта слишком короткое.", None
        if safe_reward < 100:
            return False, "Минимальная награда контракта: $100.", None
        if safe_reward > 50_000_000:
            return False, "Слишком большая сумма контракта.", None
        if len(clean_description) > 1500:
            clean_description = clean_description[:1500]

        hours = max(1, min(int(deadline_hours or 48), 24 * 30))
        now = datetime.now()
        now_iso = now.isoformat()
        deadline_iso = (now + timedelta(hours=hours)).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (int(creator_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            balance = float(user["balance"] or 0)
            if balance < safe_reward:
                await db.rollback()
                return False, "Недостаточно средств для депозита контракта.", None

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (round(balance - safe_reward, 2), int(creator_id)),
            )
            cursor = await db.execute(
                """
                INSERT INTO market_contracts
                (creator_id, assignee_id, title, description, reward, escrow_amount, status, deadline_date, created_date)
                VALUES (?, NULL, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    int(creator_id),
                    clean_title,
                    clean_description,
                    safe_reward,
                    safe_reward,
                    deadline_iso,
                    now_iso,
                ),
            )
            contract_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=creator_id,
            activity_type="market_contract_create",
            details=f"Создан контракт #{contract_id}: {clean_title}",
            value=safe_reward,
        )
        return True, "Контракт создан.", {
            "contract_id": contract_id,
            "reward": safe_reward,
            "deadline_date": deadline_iso,
        }

    async def list_market_contracts(
        self,
        viewer_id: Optional[int] = None,
        include_closed: bool = False,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        await self._ensure_market_contracts_table()
        safe_limit = max(1, min(int(limit or 25), 100))

        where_parts = []
        params: List[Any] = []
        if not include_closed:
            where_parts.append("mc.status IN ('open', 'claimed')")
        if viewer_id is not None:
            where_parts.append("(mc.creator_id = ? OR mc.assignee_id = ? OR mc.status = 'open')")
            params.extend([int(viewer_id), int(viewer_id)])

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(safe_limit)

        query = f"""
            SELECT mc.*,
                   COALESCE(NULLIF(cu.full_name, ''), NULLIF(cu.username, ''), CAST(mc.creator_id AS TEXT)) AS creator_name,
                   COALESCE(NULLIF(au.full_name, ''), NULLIF(au.username, ''), CAST(mc.assignee_id AS TEXT)) AS assignee_name
            FROM market_contracts mc
            LEFT JOIN users cu ON cu.user_id = mc.creator_id
            LEFT JOIN users au ON au.user_id = mc.assignee_id
            {where_sql}
            ORDER BY
                CASE mc.status WHEN 'open' THEN 0 WHEN 'claimed' THEN 1 ELSE 2 END,
                mc.created_date DESC
            LIMIT ?
        """

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def claim_market_contract(self, actor_id: int, contract_id: int) -> tuple[bool, str]:
        await self._ensure_market_contracts_table()
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM market_contracts WHERE id = ?",
                (int(contract_id),),
            ) as cursor:
                contract = await cursor.fetchone()
            if not contract:
                await db.rollback()
                return False, "Контракт не найден."
            if str(contract["status"]) != "open":
                await db.rollback()
                return False, "Контракт уже недоступен."
            if int(contract["creator_id"]) == int(actor_id):
                await db.rollback()
                return False, "Нельзя взять собственный контракт."

            await db.execute(
                """
                UPDATE market_contracts
                SET status = 'claimed', assignee_id = ?, claimed_date = ?
                WHERE id = ?
                """,
                (int(actor_id), now, int(contract_id)),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="market_contract_claim",
            details=f"Взят контракт #{int(contract_id)}",
            value=float(contract["reward"] or 0),
        )
        return True, "Контракт взят в работу."

    async def complete_market_contract(
        self,
        actor_id: int,
        contract_id: int,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_market_contracts_table()
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM market_contracts WHERE id = ?",
                (int(contract_id),),
            ) as cursor:
                contract = await cursor.fetchone()
            if not contract:
                await db.rollback()
                return False, "Контракт не найден.", None
            if str(contract["status"]) != "claimed":
                await db.rollback()
                return False, "Контракт нельзя завершить в текущем статусе.", None

            creator_id = int(contract["creator_id"] or 0)
            assignee_id = int(contract["assignee_id"] or 0)
            if int(actor_id) not in {creator_id, assignee_id}:
                await db.rollback()
                return False, "Недостаточно прав для завершения контракта.", None
            if assignee_id <= 0:
                await db.rollback()
                return False, "У контракта нет исполнителя.", None

            payout = round(float(contract["escrow_amount"] or contract["reward"] or 0), 2)
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (assignee_id,),
            ) as cursor:
                assignee = await cursor.fetchone()
            if not assignee:
                await db.rollback()
                return False, "Исполнитель контракта не найден.", None

            assignee_balance = round(float(assignee["balance"] or 0) + payout, 2)
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (assignee_balance, assignee_id),
            )
            await db.execute(
                """
                UPDATE market_contracts
                SET status = 'completed', completed_date = ?
                WHERE id = ?
                """,
                (now, int(contract_id)),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=assignee_id,
            activity_type="market_contract_complete",
            details=f"Завершен контракт #{int(contract_id)}",
            value=payout,
        )
        if creator_id != assignee_id:
            await self.log_player_activity(
                user_id=creator_id,
                activity_type="market_contract_paid",
                details=f"Контракт #{int(contract_id)} подтвержден",
                value=payout,
            )
        return True, "Контракт завершен.", {
            "contract_id": int(contract_id),
            "payout": payout,
            "assignee_id": assignee_id,
            "assignee_balance": assignee_balance,
        }

    async def cancel_market_contract(
        self,
        actor_id: int,
        contract_id: int,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_market_contracts_table()
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM market_contracts WHERE id = ?",
                (int(contract_id),),
            ) as cursor:
                contract = await cursor.fetchone()
            if not contract:
                await db.rollback()
                return False, "Контракт не найден.", None
            if int(contract["creator_id"] or 0) != int(actor_id):
                await db.rollback()
                return False, "Отмена доступна только создателю контракта.", None
            if str(contract["status"]) != "open":
                await db.rollback()
                return False, "Можно отменить только свободный контракт.", None

            refund = round(float(contract["escrow_amount"] or contract["reward"] or 0), 2)
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (int(actor_id),),
            ) as cursor:
                creator = await cursor.fetchone()
            if not creator:
                await db.rollback()
                return False, "Создатель контракта не найден.", None
            new_balance = round(float(creator["balance"] or 0) + refund, 2)
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, int(actor_id)),
            )
            await db.execute(
                """
                UPDATE market_contracts
                SET status = 'cancelled', cancelled_date = ?
                WHERE id = ?
                """,
                (now, int(contract_id)),
            )
            await db.commit()

        return True, "Контракт отменен, депозит возвращен.", {
            "refund": refund,
            "new_balance": new_balance,
        }

    async def _ensure_bank_transactions_table(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS bank_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    tx_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_before REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    bank_before REAL NOT NULL,
                    bank_after REAL NOT NULL,
                    note TEXT,
                    created_date TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bank_transactions_user_date ON bank_transactions(user_id, created_date DESC)"
            )
            await db.commit()

    async def deposit_to_bank(
        self,
        user_id: int,
        amount: float,
        note: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_bank_transactions_table()
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        if safe_amount > 100_000_000:
            return False, "Слишком большая сумма.", None

        now = datetime.now().isoformat()
        note_clean = " ".join((note or "").strip().split())[:220]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT balance, bank FROM users WHERE user_id = ?",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            balance_before = round(float(user["balance"] or 0), 2)
            bank_before = round(float(user["bank"] or 0), 2)
            if balance_before < safe_amount:
                await db.rollback()
                return False, "Недостаточно наличного баланса.", None

            balance_after = round(balance_before - safe_amount, 2)
            bank_after = round(bank_before + safe_amount, 2)

            await db.execute(
                "UPDATE users SET balance = ?, bank = ? WHERE user_id = ?",
                (balance_after, bank_after, int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'deposit', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    safe_amount,
                    balance_before,
                    balance_after,
                    bank_before,
                    bank_after,
                    note_clean,
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="bank_deposit",
            details="Пополнение банковского счета",
            value=safe_amount,
        )
        return True, "Депозит выполнен.", {
            "amount": safe_amount,
            "balance": balance_after,
            "bank": bank_after,
        }

    async def withdraw_from_bank(
        self,
        user_id: int,
        amount: float,
        note: str = "",
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_bank_transactions_table()
        safe_amount = round(float(amount or 0), 2)
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        if safe_amount > 100_000_000:
            return False, "Слишком большая сумма.", None

        now = datetime.now().isoformat()
        note_clean = " ".join((note or "").strip().split())[:220]
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT balance, bank FROM users WHERE user_id = ?",
                (int(user_id),),
            ) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return False, "Игрок не найден.", None

            balance_before = round(float(user["balance"] or 0), 2)
            bank_before = round(float(user["bank"] or 0), 2)
            if bank_before < safe_amount:
                await db.rollback()
                return False, "Недостаточно средств на банковском счете.", None

            balance_after = round(balance_before + safe_amount, 2)
            bank_after = round(bank_before - safe_amount, 2)

            await db.execute(
                "UPDATE users SET balance = ?, bank = ? WHERE user_id = ?",
                (balance_after, bank_after, int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'withdraw', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    safe_amount,
                    balance_before,
                    balance_after,
                    bank_before,
                    bank_after,
                    note_clean,
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="bank_withdraw",
            details="Снятие средств с банковского счета",
            value=safe_amount,
        )
        return True, "Вывод выполнен.", {
            "amount": safe_amount,
            "balance": balance_after,
            "bank": bank_after,
        }

    async def transfer_between_players(
        self,
        sender_id: int,
        recipient_id: int,
        amount: float,
        note: str = "",
        apply_commission: bool = True,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """Прямой перевод денег между игроками (наличные -> наличные) с комиссией 2%."""
        await self._ensure_bank_transactions_table()
        safe_sender_id = int(sender_id or 0)
        safe_recipient_id = int(recipient_id or 0)
        safe_amount = round(float(amount or 0), 2)

        if safe_sender_id <= 0 or safe_recipient_id <= 0:
            return False, "Некорректный отправитель или получатель.", None
        if safe_sender_id == safe_recipient_id:
            return False, "Нельзя переводить самому себе.", None
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        if safe_amount > 100_000_000:
            return False, "Слишком большая сумма.", None

        # Комиссия банка: 2% от суммы
        commission_rate = 0.02 if apply_commission else 0.0
        commission = round(safe_amount * commission_rate, 2)
        total_debit = round(safe_amount + commission, 2)

        now = datetime.now().isoformat()
        note_clean = " ".join((note or "").strip().split())[:220]
        if not note_clean:
            note_clean = "Перевод между игроками"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT user_id, balance, bank, nickname, full_name, username FROM users WHERE user_id = ? LIMIT 1",
                (safe_sender_id,),
            ) as cursor:
                sender = await cursor.fetchone()
            async with db.execute(
                "SELECT user_id, balance, bank, nickname, full_name, username FROM users WHERE user_id = ? LIMIT 1",
                (safe_recipient_id,),
            ) as cursor:
                recipient = await cursor.fetchone()
            if not sender or not recipient:
                await db.rollback()
                return False, "Отправитель или получатель не найдены.", None

            sender_balance_before = round(float(sender["balance"] or 0), 2)
            sender_bank_before = round(float(sender["bank"] or 0), 2)
            recipient_balance_before = round(float(recipient["balance"] or 0), 2)
            recipient_bank_before = round(float(recipient["bank"] or 0), 2)

            if sender_balance_before < total_debit:
                await db.rollback()
                return False, f"Недостаточно средств. Нужно ${total_debit:,.2f} (сумма + комиссия {commission_rate*100:.0f}%).", None

            sender_balance_after = round(sender_balance_before - total_debit, 2)
            recipient_balance_after = round(recipient_balance_before + safe_amount, 2)

            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (sender_balance_after, safe_sender_id),
            )
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (recipient_balance_after, safe_recipient_id),
            )
            
            # Заносим перевод отправителю (с комиссией)
            commission_note = f" (комиссия ${commission:,.2f})" if commission > 0 else ""
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'transfer_out', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_sender_id,
                    total_debit,
                    sender_balance_before,
                    sender_balance_after,
                    sender_bank_before,
                    sender_bank_before,
                    f"Кому: {safe_recipient_id}. ${safe_amount:,.2f}{commission_note}. {note_clean}",
                    now,
                ),
            )
            
            # Заносим перевод получателю
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'transfer_in', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_recipient_id,
                    safe_amount,
                    recipient_balance_before,
                    recipient_balance_after,
                    recipient_bank_before,
                    recipient_bank_before,
                    f"От: {safe_sender_id}. ${safe_amount:,.2f}. {note_clean}",
                    now,
                ),
            )
            
            # Если есть комиссия, добавляем в бюджет правительства
            if commission > 0:
                await db.execute(
                    """
                    INSERT INTO bank_transactions
                    (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                    VALUES (?, 'commission', ?, 0, ?, 0, 0, ?, ?)
                    """,
                    (
                        0,  # система
                        commission,
                        commission,
                        f"Комиссия за перевод: {safe_sender_id} -> {safe_recipient_id}",
                        now,
                    ),
                )
            
            await db.commit()

        sender_name = _compose_public_name(dict(sender), fallback_id=safe_sender_id)
        recipient_name = _compose_public_name(dict(recipient), fallback_id=safe_recipient_id)
        await self.log_player_activity(
            user_id=safe_sender_id,
            activity_type="player_transfer_out",
            details=f"Перевод {recipient_name} на ${safe_amount:,.2f} (комиссия ${commission:,.2f})",
            value=total_debit,
        )
        await self.log_player_activity(
            user_id=safe_recipient_id,
            activity_type="player_transfer_in",
            details=f"Получен перевод от {sender_name} на ${safe_amount:,.2f}",
            value=safe_amount,
        )

        return True, "Перевод выполнен.", {
            "amount": safe_amount,
            "commission": commission,
            "total_debit": total_debit,
            "sender_balance": sender_balance_after,
            "recipient_balance": recipient_balance_after,
            "sender_name": sender_name,
            "recipient_name": recipient_name,
        }

    async def get_user_bank_transactions(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        await self._ensure_bank_transactions_table()
        safe_limit = max(1, min(int(limit or 20), 100))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT *
                FROM bank_transactions
                WHERE user_id = ?
                ORDER BY created_date DESC
                LIMIT ?
                """,
                (int(user_id), safe_limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def _ensure_police_court_tables(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS court_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filed_by_id INTEGER NOT NULL,
                    defendant_id INTEGER NOT NULL,
                    judge_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    requested_penalty REAL DEFAULT 0,
                    imposed_penalty REAL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    verdict_text TEXT,
                    created_date TEXT NOT NULL,
                    updated_date TEXT NOT NULL,
                    closed_date TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_court_cases_status ON court_cases(status, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_court_cases_defendant ON court_cases(defendant_id, created_date DESC)"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS police_arrests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    officer_id INTEGER NOT NULL,
                    suspect_id INTEGER NOT NULL,
                    reason TEXT,
                    fine_amount REAL DEFAULT 0,
                    jail_minutes INTEGER DEFAULT 120,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_date TEXT NOT NULL,
                    arrested_until TEXT,
                    released_date TEXT,
                    case_id INTEGER,
                    notes TEXT
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_police_arrests_officer ON police_arrests(officer_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_police_arrests_suspect ON police_arrests(suspect_id, created_date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_police_arrests_status ON police_arrests(status, created_date DESC)"
            )
            await db.commit()

    async def get_police_suspects(
        self,
        limit: int = 15,
        search: str = "",
        exclude_user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        await self._ensure_police_court_tables()
        safe_limit = max(1, min(int(limit or 15), 50))
        clean_search = (search or "").strip().lower()

        where_parts = [
            "(COALESCE(u.crimes_committed, 0) > 0 OR COALESCE(u.tax_debt, 0) > 100 OR COALESCE(u.corruption_score, 0) > 2 OR COALESCE(u.shadow_balance, 0) > 5000 OR COALESCE(u.arrested, 0) = 1)"
        ]
        params: List[Any] = []
        if exclude_user_id is not None:
            where_parts.append("u.user_id != ?")
            params.append(int(exclude_user_id))
        if clean_search:
            where_parts.append(
                "(LOWER(COALESCE(u.full_name, '')) LIKE ? OR LOWER(COALESCE(u.username, '')) LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?)"
            )
            params.extend([f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"])
        params.append(safe_limit)

        query = f"""
            SELECT u.user_id,
                   u.full_name,
                   u.username,
                   u.organization,
                   u.role,
                   COALESCE(u.crimes_committed, 0) AS crimes_committed,
                   COALESCE(u.tax_debt, 0) AS tax_debt,
                   COALESCE(u.corruption_score, 0) AS corruption_score,
                   COALESCE(u.shadow_balance, 0) AS shadow_balance,
                   COALESCE(u.reputation, 50) AS reputation,
                   COALESCE(u.arrested, 0) AS arrested,
                   u.arrested_until,
                   (
                       COALESCE(u.crimes_committed, 0) * 15
                       + COALESCE(u.corruption_score, 0) * 6
                       + (COALESCE(u.tax_debt, 0) / 3000.0)
                       + (COALESCE(u.shadow_balance, 0) / 12000.0)
                       + CASE WHEN COALESCE(u.reputation, 50) < 40 THEN (40 - COALESCE(u.reputation, 50)) ELSE 0 END
                   ) AS risk_score
            FROM users u
            WHERE {' AND '.join(where_parts)}
            ORDER BY risk_score DESC, COALESCE(u.crimes_committed, 0) DESC, u.user_id ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_court_case(
        self,
        filed_by_id: int,
        defendant_id: int,
        title: str,
        description: str = "",
        requested_penalty: float = 0,
        judge_id: Optional[int] = None,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_police_court_tables()
        clean_title = " ".join((title or "").strip().split())
        clean_desc = " ".join((description or "").strip().split())
        if len(clean_title) < 3:
            return False, "Название дела слишком короткое.", None
        penalty = max(0.0, round(float(requested_penalty or 0), 2))
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (int(defendant_id),)) as cursor:
                defendant = await cursor.fetchone()
            if not defendant:
                await db.rollback()
                return False, "Ответчик не найден.", None

            cursor = await db.execute(
                """
                INSERT INTO court_cases
                (filed_by_id, defendant_id, judge_id, title, description, requested_penalty, imposed_penalty, status, verdict_text, created_date, updated_date, closed_date)
                VALUES (?, ?, ?, ?, ?, ?, 0, 'open', '', ?, ?, NULL)
                """,
                (
                    int(filed_by_id),
                    int(defendant_id),
                    int(judge_id) if judge_id else None,
                    clean_title[:200],
                    clean_desc[:2500],
                    penalty,
                    now,
                    now,
                ),
            )
            case_id = int(cursor.lastrowid or 0)
            await db.commit()

        await self.log_player_activity(
            user_id=filed_by_id,
            activity_type="court_case_create",
            details=f"Открыто дело #{case_id}",
            value=penalty,
        )
        return True, "Судебное дело открыто.", {"case_id": case_id}

    async def register_police_arrest(
        self,
        officer_id: int,
        suspect_id: int,
        reason: str,
        fine_amount: float = 0,
        jail_minutes: int = 120,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_police_court_tables()
        if int(officer_id) == int(suspect_id):
            return False, "Нельзя арестовать самого себя.", None

        clean_reason = " ".join((reason or "").strip().split())
        if len(clean_reason) < 3:
            clean_reason = "Проверка по подозрению"
        safe_fine = max(0.0, min(round(float(fine_amount or 0), 2), 10_000_000))
        safe_minutes = max(30, min(int(jail_minutes or 120), 24 * 7 * 60))

        now_dt = datetime.now()
        now = now_dt.isoformat()
        arrested_until = (now_dt + timedelta(minutes=safe_minutes)).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT user_id, balance, fines_paid, arrested, arrested_until FROM users WHERE user_id = ?",
                (int(suspect_id),),
            ) as cursor:
                suspect = await cursor.fetchone()
            async with db.execute(
                "SELECT user_id, arrests_made FROM users WHERE user_id = ?",
                (int(officer_id),),
            ) as cursor:
                officer = await cursor.fetchone()

            if not suspect or not officer:
                await db.rollback()
                return False, "Офицер или подозреваемый не найден.", None
            if int(suspect["arrested"] or 0) == 1:
                until = str(suspect["arrested_until"] or "")
                if until and until > now:
                    await db.rollback()
                    return False, "Игрок уже находится под арестом.", None

            suspect_balance = round(float(suspect["balance"] or 0), 2)
            fine_paid = round(min(suspect_balance, safe_fine), 2)
            suspect_balance_after = round(max(0.0, suspect_balance - fine_paid), 2)
            fines_paid_total = round(float(suspect["fines_paid"] or 0) + fine_paid, 2)

            await db.execute(
                """
                UPDATE users
                SET balance = ?, fines_paid = ?, arrested = 1, arrested_until = ?
                WHERE user_id = ?
                """,
                (suspect_balance_after, fines_paid_total, arrested_until, int(suspect_id)),
            )
            await db.execute(
                """
                UPDATE users
                SET arrests_made = COALESCE(arrests_made, 0) + 1
                WHERE user_id = ?
                """,
                (int(officer_id),),
            )

            case_title = f"Арест игрока #{int(suspect_id)}"
            case_desc = f"Основание ареста: {clean_reason}"
            case_cursor = await db.execute(
                """
                INSERT INTO court_cases
                (filed_by_id, defendant_id, judge_id, title, description, requested_penalty, imposed_penalty, status, verdict_text, created_date, updated_date, closed_date)
                VALUES (?, ?, NULL, ?, ?, ?, 0, 'open', '', ?, ?, NULL)
                """,
                (
                    int(officer_id),
                    int(suspect_id),
                    case_title[:200],
                    case_desc[:2500],
                    safe_fine,
                    now,
                    now,
                ),
            )
            case_id = int(case_cursor.lastrowid or 0)

            arrest_cursor = await db.execute(
                """
                INSERT INTO police_arrests
                (officer_id, suspect_id, reason, fine_amount, jail_minutes, status, created_date, arrested_until, released_date, case_id, notes)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL, ?, '')
                """,
                (
                    int(officer_id),
                    int(suspect_id),
                    clean_reason[:500],
                    safe_fine,
                    safe_minutes,
                    now,
                    arrested_until,
                    case_id,
                ),
            )
            arrest_id = int(arrest_cursor.lastrowid or 0)

            if fine_paid > 0:
                await db.execute(
                    "UPDATE organizations SET budget = COALESCE(budget, 0) + ? WHERE name = 'Полиция'",
                    (fine_paid,),
                )
            await db.commit()

        await self.log_player_activity(
            user_id=officer_id,
            activity_type="police_arrest",
            details=f"Арест игрока #{int(suspect_id)} ({clean_reason})",
            value=fine_paid,
        )
        await self.log_player_activity(
            user_id=suspect_id,
            activity_type="got_arrested",
            details=f"Арест: {clean_reason}",
            value=fine_paid,
        )
        return True, "Арест зарегистрирован.", {
            "arrest_id": arrest_id,
            "case_id": case_id,
            "fine_paid": fine_paid,
            "arrested_until": arrested_until,
            "suspect_balance": suspect_balance_after,
        }

    async def issue_security_penalty(
        self,
        actor_id: int,
        target_id: int,
        agency: str,
        reason: str,
        fine_amount: float = 0.0,
        ban_minutes: int = 0,
        reputation_delta: float = 0.0,
        tax_debt_delta: float = 0.0,
        corruption_delta: int = 0,
        seize_percent: float = 0.0,
        public_notice: bool = False,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_actor = int(actor_id)
        safe_target = int(target_id)
        if safe_actor == safe_target:
            return False, "Нельзя выдать наказание самому себе.", None

        agency_lc = str(agency or "").strip().lower()
        if agency_lc not in {"police", "fbi"}:
            return False, "Некорректное ведомство наказания.", None

        actor = await self.get_user(safe_actor)
        target = await self.get_user(safe_target)
        if not actor or not target:
            return False, "Игрок-инициатор или цель не найдены.", None

        authority = await self.get_government_authority(safe_actor)
        actor_role = str(actor.get("role") or "").lower()
        actor_org = str(actor.get("organization") or "").lower()

        is_police_actor = (
            ("полиц" in actor_role)
            or ("police" in actor_role)
            or ("полиц" in actor_org)
            or ("police" in actor_org)
            or await self.is_user_in_org_type(safe_actor, "police")
        )
        is_fbi_actor = (
            ("фбр" in actor_role)
            or ("fbi" in actor_role)
            or ("фбр" in actor_org)
            or ("fbi" in actor_org)
            or await self.is_fbi_agent(safe_actor)
            or await self.is_user_in_org_type(safe_actor, "fbi")
        )

        allowed = False
        if agency_lc == "police":
            allowed = is_police_actor or is_fbi_actor or authority in {"president", "vice_president", "minister"}
        elif agency_lc == "fbi":
            allowed = is_fbi_actor or authority in {"president", "vice_president", "minister"}
        if not allowed:
            return False, "Недостаточно прав для выдачи такого наказания.", None

        clean_reason = " ".join((reason or "").strip().split())[:500]
        if len(clean_reason) < 4:
            clean_reason = "Служебное наказание"

        safe_fine = max(0.0, min(round(float(fine_amount or 0), 2), 10_000_000.0))
        safe_ban = max(0, min(int(ban_minutes or 0), 60 * 24 * 7))
        safe_rep_delta = round(float(reputation_delta or 0), 2)
        safe_tax_delta = max(0.0, round(float(tax_debt_delta or 0), 2))
        safe_corr_delta = max(0, min(int(corruption_delta or 0), 100))
        safe_seize_pct = max(0.0, min(float(seize_percent or 0), 0.95))

        now_dt = datetime.now()
        now = now_dt.isoformat()
        actor_name = self.get_user_public_name(actor, fallback_id=safe_actor)
        target_name = self.get_user_public_name(target, fallback_id=safe_target)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT balance, fines_paid, reputation, tax_debt, corruption_score, action_banned_until FROM users WHERE user_id = ? LIMIT 1",
                (safe_target,),
            ) as cursor:
                target_row = await cursor.fetchone()
            if not target_row:
                await db.rollback()
                return False, "Цель наказания не найдена.", None

            balance_before = round(float(target_row["balance"] or 0), 2)
            fines_before = round(float(target_row["fines_paid"] or 0), 2)
            rep_before = round(float(target_row["reputation"] or 50), 2)
            debt_before = round(float(target_row["tax_debt"] or 0), 2)
            corr_before = int(target_row["corruption_score"] or 0)
            prev_ban_raw = str(target_row["action_banned_until"] or "")

            fine_paid = round(min(balance_before, safe_fine), 2)
            after_fine_balance = round(max(0.0, balance_before - fine_paid), 2)
            seized_amount = round(min(after_fine_balance, after_fine_balance * safe_seize_pct), 2) if safe_seize_pct > 0 else 0.0
            balance_after = round(max(0.0, after_fine_balance - seized_amount), 2)

            fines_after = round(fines_before + fine_paid, 2)
            rep_after = round(max(0.0, min(100.0, rep_before + safe_rep_delta)), 2)
            debt_after = round(max(0.0, debt_before + safe_tax_delta), 2)
            corr_after = max(0, corr_before + safe_corr_delta)

            ban_until = prev_ban_raw
            if safe_ban > 0:
                new_ban_dt = now_dt + timedelta(minutes=safe_ban)
                try:
                    prev_dt = datetime.fromisoformat(prev_ban_raw) if prev_ban_raw else None
                except Exception:
                    prev_dt = None
                if not prev_dt or prev_dt < new_ban_dt:
                    ban_until = new_ban_dt.isoformat()

            await db.execute(
                """
                UPDATE users
                SET balance = ?,
                    fines_paid = ?,
                    reputation = ?,
                    tax_debt = ?,
                    corruption_score = ?,
                    action_banned_until = ?
                WHERE user_id = ?
                """,
                (
                    balance_after,
                    fines_after,
                    rep_after,
                    debt_after,
                    corr_after,
                    ban_until if ban_until else None,
                    safe_target,
                ),
            )

            credited_amount = round(fine_paid + seized_amount, 2)
            if credited_amount > 0:
                if agency_lc == "police":
                    async with db.execute(
                        "SELECT id FROM organizations WHERE lower(COALESCE(type, '')) = 'police' ORDER BY id ASC LIMIT 1"
                    ) as cursor:
                        org_row = await cursor.fetchone()
                else:
                    async with db.execute(
                        "SELECT id FROM organizations WHERE lower(COALESCE(type, '')) = 'government' ORDER BY id ASC LIMIT 1"
                    ) as cursor:
                        org_row = await cursor.fetchone()
                    if not org_row:
                        async with db.execute(
                            "SELECT id FROM organizations WHERE lower(COALESCE(type, '')) = 'fbi' ORDER BY id ASC LIMIT 1"
                        ) as cursor:
                            org_row = await cursor.fetchone()
                if org_row:
                    await db.execute(
                        "UPDATE organizations SET budget = COALESCE(budget, 0) + ? WHERE id = ?",
                        (credited_amount, int(org_row["id"])),
                    )

            risk = 6 + min(70, int((safe_fine + seized_amount + safe_tax_delta) // 80)) + (5 if agency_lc == "fbi" else 0)
            await db.execute(
                """
                INSERT INTO corruption_ops
                (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                VALUES (?, ?, ?, ?, ?, 'logged', ?, ?)
                """,
                (
                    safe_actor,
                    safe_target,
                    f"{agency_lc}_penalty_{'public' if public_notice else 'silent'}",
                    round(safe_fine + safe_tax_delta + seized_amount, 2),
                    int(risk),
                    clean_reason,
                    now,
                ),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=safe_actor,
            activity_type=f"{agency_lc}_penalty_issue",
            details=f"Наказание для {target_name}: {clean_reason}",
            value=round(safe_fine + seized_amount, 2),
        )
        await self.log_player_activity(
            user_id=safe_target,
            activity_type=f"{agency_lc}_penalty_received",
            details=clean_reason,
            value=round(safe_fine + seized_amount, 2),
        )

        lines = [
            f"Вам выдано наказание ведомством {'ФБР' if agency_lc == 'fbi' else 'Полиция'}.",
            f"Инициатор: {actor_name}.",
            f"Основание: {clean_reason}.",
        ]
        if fine_paid > 0:
            lines.append(f"Списан штраф: ${fine_paid:,.2f}.")
        if seized_amount > 0:
            lines.append(f"Изъято средств: ${seized_amount:,.2f}.")
        if safe_tax_delta > 0:
            lines.append(f"Начислен налоговый долг: +${safe_tax_delta:,.2f}.")
        if safe_rep_delta != 0:
            lines.append(f"Репутация изменена на {safe_rep_delta:+.1f}.")
        if safe_corr_delta > 0:
            lines.append(f"Риск коррупции увеличен на {safe_corr_delta}.")
        if ban_until:
            lines.append(f"Ограничение действий до: {str(ban_until)[:16]}.")
        target_notice_text = "\n".join(lines)

        await self.send_private_message(
            sender_id=safe_actor,
            recipient_id=safe_target,
            subject=f"⚖️ Наказание ({'ФБР' if agency_lc == 'fbi' else 'Полиция'})",
            content=target_notice_text,
            message_type="system",
        )

        if public_notice:
            await self.create_media_news(
                title=f"Публичное постановление: {'ФБР' if agency_lc == 'fbi' else 'Полиция'}",
                body=f"Игрок {target_name} получил публичное наказание. Основание: {clean_reason}.",
                source_user_id=safe_actor,
                severity="high" if agency_lc == "fbi" else "normal",
            )

        payload = {
            "agency": agency_lc,
            "target_id": safe_target,
            "target_name": target_name,
            "reason": clean_reason,
            "fine_paid": fine_paid,
            "seized_amount": seized_amount,
            "balance_after": balance_after,
            "tax_debt_delta": safe_tax_delta,
            "reputation_delta": safe_rep_delta,
            "corruption_delta": safe_corr_delta,
            "ban_until": ban_until,
            "public_notice": bool(public_notice),
            "target_notice_text": target_notice_text,
        }
        return True, "Наказание применено.", payload

    async def get_police_arrests(
        self,
        officer_id: Optional[int] = None,
        suspect_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        await self._ensure_police_court_tables()
        safe_limit = max(1, min(int(limit or 30), 100))
        where_parts = ["1=1"]
        params: List[Any] = []
        if officer_id is not None:
            where_parts.append("pa.officer_id = ?")
            params.append(int(officer_id))
        if suspect_id is not None:
            where_parts.append("pa.suspect_id = ?")
            params.append(int(suspect_id))
        if status:
            where_parts.append("pa.status = ?")
            params.append(str(status))
        params.append(safe_limit)

        query = f"""
            SELECT pa.*,
                   COALESCE(NULLIF(ou.full_name, ''), NULLIF(ou.username, ''), CAST(pa.officer_id AS TEXT)) AS officer_name,
                   COALESCE(NULLIF(su.nickname, ''), NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(pa.suspect_id AS TEXT)) AS suspect_name,
                   cc.status AS case_status
            FROM police_arrests pa
            LEFT JOIN users ou ON ou.user_id = pa.officer_id
            LEFT JOIN users su ON su.user_id = pa.suspect_id
            LEFT JOIN court_cases cc ON cc.id = pa.case_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY pa.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_active_investigations(
        self,
        officer_id: Optional[int] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        await self._ensure_police_court_tables()
        safe_limit = max(1, min(int(limit or 30), 100))
        where_parts = ["(pa.status = 'active' OR cc.status IN ('open', 'hearing'))"]
        params: List[Any] = []
        if officer_id is not None:
            where_parts.append("pa.officer_id = ?")
            params.append(int(officer_id))
        params.append(safe_limit)
        query = f"""
            SELECT pa.id AS arrest_id,
                   pa.created_date,
                   pa.reason,
                   pa.fine_amount,
                   pa.jail_minutes,
                   pa.status AS arrest_status,
                   pa.case_id,
                   cc.status AS case_status,
                   cc.title AS case_title,
                   COALESCE(NULLIF(su.nickname, ''), NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(pa.suspect_id AS TEXT)) AS suspect_name
            FROM police_arrests pa
            LEFT JOIN court_cases cc ON cc.id = pa.case_id
            LEFT JOIN users su ON su.user_id = pa.suspect_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY pa.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_court_cases(
        self,
        status: Optional[str] = None,
        defendant_id: Optional[int] = None,
        judge_id: Optional[int] = None,
        filed_by_id: Optional[int] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        await self._ensure_police_court_tables()
        safe_limit = max(1, min(int(limit or 40), 200))
        where_parts = ["1=1"]
        params: List[Any] = []
        if status:
            where_parts.append("cc.status = ?")
            params.append(str(status))
        if defendant_id is not None:
            where_parts.append("cc.defendant_id = ?")
            params.append(int(defendant_id))
        if judge_id is not None:
            where_parts.append("cc.judge_id = ?")
            params.append(int(judge_id))
        if filed_by_id is not None:
            where_parts.append("cc.filed_by_id = ?")
            params.append(int(filed_by_id))
        params.append(safe_limit)

        query = f"""
            SELECT cc.*,
                   COALESCE(NULLIF(fu.full_name, ''), NULLIF(fu.username, ''), CAST(cc.filed_by_id AS TEXT)) AS filed_by_name,
                   COALESCE(NULLIF(du.full_name, ''), NULLIF(du.username, ''), CAST(cc.defendant_id AS TEXT)) AS defendant_name,
                   COALESCE(NULLIF(ju.full_name, ''), NULLIF(ju.username, ''), CAST(cc.judge_id AS TEXT)) AS judge_name
            FROM court_cases cc
            LEFT JOIN users fu ON fu.user_id = cc.filed_by_id
            LEFT JOIN users du ON du.user_id = cc.defendant_id
            LEFT JOIN users ju ON ju.user_id = cc.judge_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY
                CASE cc.status WHEN 'open' THEN 0 WHEN 'hearing' THEN 1 ELSE 2 END,
                cc.updated_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_court_case_status(
        self,
        actor_id: int,
        case_id: int,
        status: str,
        verdict_text: str = "",
        imposed_penalty: Optional[float] = None,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        await self._ensure_police_court_tables()
        target_status = str(status or "").strip().lower()
        if target_status not in {"open", "hearing", "closed", "dismissed"}:
            return False, "Некорректный статус дела.", None

        actor = await self.get_user(actor_id) or {}
        role_lc = str(actor.get("role") or "").lower()
        org_lc = str(actor.get("organization") or "").lower()
        authority = await self.get_government_authority(actor_id)
        is_judge = (
            ("суд" in role_lc)
            or ("judge" in role_lc)
            or ("суд" in org_lc)
            or ("court" in org_lc)
            or await self.is_user_in_org_type(actor_id, "court")
        )

        now = datetime.now().isoformat()
        clean_verdict = " ".join((verdict_text or "").strip().split())[:2000]
        safe_penalty = round(float(imposed_penalty or 0), 2) if imposed_penalty is not None else None
        if safe_penalty is not None and safe_penalty < 0:
            safe_penalty = 0.0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM court_cases WHERE id = ?",
                (int(case_id),),
            ) as cursor:
                case_row = await cursor.fetchone()
            if not case_row:
                await db.rollback()
                return False, "Дело не найдено.", None

            can_manage = (
                is_judge
                or authority == "president"
                or int(case_row["filed_by_id"] or 0) == int(actor_id)
            )
            if not can_manage:
                await db.rollback()
                return False, "Недостаточно прав для изменения дела.", None

            defendant_id = int(case_row["defendant_id"] or 0)
            requested_penalty = round(float(case_row["requested_penalty"] or 0), 2)
            if safe_penalty is None:
                if target_status == "closed":
                    safe_penalty = requested_penalty if requested_penalty > 0 else 2_000.0
                else:
                    safe_penalty = round(float(case_row["imposed_penalty"] or 0), 2)

            collected_penalty = 0.0
            if target_status == "closed" and safe_penalty > 0 and defendant_id > 0:
                async with db.execute(
                    "SELECT balance, fines_paid FROM users WHERE user_id = ?",
                    (defendant_id,),
                ) as cursor:
                    defendant = await cursor.fetchone()
                if defendant:
                    bal = round(float(defendant["balance"] or 0), 2)
                    collected_penalty = round(min(bal, safe_penalty), 2)
                    bal_after = round(max(0.0, bal - collected_penalty), 2)
                    fines_after = round(float(defendant["fines_paid"] or 0) + collected_penalty, 2)
                    await db.execute(
                        "UPDATE users SET balance = ?, fines_paid = ? WHERE user_id = ?",
                        (bal_after, fines_after, defendant_id),
                    )
                    if collected_penalty > 0:
                        await db.execute(
                            "UPDATE organizations SET budget = COALESCE(budget, 0) + ? WHERE name = 'Суд'",
                            (collected_penalty,),
                        )

            closed_date = now if target_status in {"closed", "dismissed"} else None
            await db.execute(
                """
                UPDATE court_cases
                SET status = ?,
                    verdict_text = ?,
                    imposed_penalty = ?,
                    judge_id = COALESCE(judge_id, ?),
                    updated_date = ?,
                    closed_date = ?
                WHERE id = ?
                """,
                (
                    target_status,
                    clean_verdict,
                    round(float(safe_penalty or 0), 2),
                    int(actor_id),
                    now,
                    closed_date,
                    int(case_id),
                ),
            )

            if target_status in {"closed", "dismissed"}:
                await db.execute(
                    """
                    UPDATE police_arrests
                    SET status = 'closed', released_date = ?
                    WHERE case_id = ? AND status = 'active'
                    """,
                    (now, int(case_id)),
                )
                if defendant_id > 0:
                    await db.execute(
                        "UPDATE users SET arrested = 0, arrested_until = NULL WHERE user_id = ?",
                        (defendant_id,),
                    )

            await db.commit()

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="court_case_update",
            details=f"Дело #{int(case_id)}: статус {target_status}",
            value=collected_penalty if collected_penalty > 0 else float(safe_penalty or 0),
        )
        return True, "Статус дела обновлен.", {
            "case_id": int(case_id),
            "status": target_status,
            "imposed_penalty": round(float(safe_penalty or 0), 2),
            "collected_penalty": collected_penalty,
        }

    async def get_court_defendants(self, limit: int = 30) -> List[Dict[str, Any]]:
        await self._ensure_police_court_tables()
        safe_limit = max(1, min(int(limit or 30), 100))
        query = """
            SELECT cc.defendant_id,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(cc.defendant_id AS TEXT)) AS defendant_name,
                   SUM(CASE WHEN cc.status IN ('open', 'hearing') THEN 1 ELSE 0 END) AS active_cases,
                   SUM(CASE WHEN cc.status = 'closed' THEN 1 ELSE 0 END) AS convictions,
                   SUM(CASE WHEN cc.status = 'dismissed' THEN 1 ELSE 0 END) AS dismissals
            FROM court_cases cc
            LEFT JOIN users u ON u.user_id = cc.defendant_id
            GROUP BY cc.defendant_id
            ORDER BY active_cases DESC, convictions DESC, cc.defendant_id ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_court_status(self, user_id: int) -> Dict[str, Any]:
        await self._ensure_police_court_tables()
        result: Dict[str, Any] = {
            "open_cases": 0,
            "hearing_cases": 0,
            "closed_cases": 0,
            "dismissed_cases": 0,
            "recent": [],
        }
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_cases,
                    SUM(CASE WHEN status = 'hearing' THEN 1 ELSE 0 END) AS hearing_cases,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_cases,
                    SUM(CASE WHEN status = 'dismissed' THEN 1 ELSE 0 END) AS dismissed_cases
                FROM court_cases
                WHERE defendant_id = ?
                """,
                (int(user_id),),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    result["open_cases"] = int(row["open_cases"] or 0)
                    result["hearing_cases"] = int(row["hearing_cases"] or 0)
                    result["closed_cases"] = int(row["closed_cases"] or 0)
                    result["dismissed_cases"] = int(row["dismissed_cases"] or 0)
            async with db.execute(
                """
                SELECT id, title, status, requested_penalty, imposed_penalty, updated_date
                FROM court_cases
                WHERE defendant_id = ?
                ORDER BY updated_date DESC
                LIMIT 8
                """,
                (int(user_id),),
            ) as cursor:
                rows = await cursor.fetchall()
                result["recent"] = [dict(r) for r in rows]
        return result

    async def execute_fbi_operation(
        self,
        actor_id: int,
        target_id: int,
        operation: str,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        if int(actor_id) == int(target_id):
            return False, "Цель операции указана неверно.", None
        if not await self.is_fbi_agent(actor_id):
            return False, "Доступ разрешен только сотрудникам ФБР.", None

        op = str(operation or "").strip().lower()
        if op not in {"expose", "scandal", "arrest", "freeze", "blackmail"}:
            return False, "Неизвестный тип операции.", None

        target = await self.get_user(target_id)
        if not target:
            return False, "Цель не найдена.", None
        actor_name = await self.get_user_public_name_by_id(int(actor_id))
        target_name = self.get_user_public_name(target, fallback_id=int(target_id))

        if op == "arrest":
            fine = random.randint(2_500, 12_500)
            jail_minutes = random.randint(90, 360)
            ok, msg, payload = await self.register_police_arrest(
                officer_id=actor_id,
                suspect_id=target_id,
                reason="Операция ФБР: задержание",
                fine_amount=float(fine),
                jail_minutes=jail_minutes,
            )
            if not ok:
                return False, msg, None

            now = datetime.now().isoformat()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO corruption_ops
                    (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                    VALUES (?, ?, 'fbi_arrest', ?, 35, 'executed', ?, ?)
                    """,
                    (
                        int(actor_id),
                        int(target_id),
                        float(fine),
                        "Операция ФБР: арест и передача в суд",
                        now,
                    ),
                )
                await db.commit()

            arrest_payload = payload or {}
            fine_paid = round(float(arrest_payload.get("fine_paid") or fine), 2)
            case_id = int(arrest_payload.get("case_id") or 0)
            arrested_until = str(arrest_payload.get("arrested_until") or "")[:16]
            notice_lines = [
                "По вам проведена операция ФБР: задержание.",
                f"Исполнитель: {actor_name}.",
                f"Списано штрафов: ${fine_paid:,.2f}.",
            ]
            if case_id > 0:
                notice_lines.append(f"Открыто судебное дело: #{case_id}.")
            if arrested_until:
                notice_lines.append(f"Арест действует до: {arrested_until}.")
            target_notice_text = "\n".join(notice_lines)
            await self.send_private_message(
                sender_id=int(actor_id),
                recipient_id=int(target_id),
                subject="🚨 Операция ФБР: задержание",
                content=target_notice_text,
                message_type="system",
            )

            return True, "Операция выполнена.", {
                "operation": op,
                "risk": 35,
                "fine_amount": float(fine),
                "target_notice_text": target_notice_text,
                **arrest_payload,
            }

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT balance, shadow_balance, reputation, tax_debt, corruption_score FROM users WHERE user_id = ?",
                (int(target_id),),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return False, "Цель не найдена.", None

            balance = round(float(row["balance"] or 0), 2)
            shadow = round(float(row["shadow_balance"] or 0), 2)
            reputation = round(float(row["reputation"] or 50), 2)
            tax_debt = round(float(row["tax_debt"] or 0), 2)
            corruption = int(row["corruption_score"] or 0)

            delta_balance = 0.0
            delta_shadow = 0.0
            delta_reputation = 0.0
            delta_tax_debt = 0.0
            delta_corruption = 0
            actor_shadow_gain = 0.0
            risk = 20
            details = ""

            if op == "expose":
                delta_reputation = -float(random.randint(4, 11))
                delta_corruption = 2
                risk = 22
                details = "Публикация закрытых материалов"
            elif op == "scandal":
                delta_reputation = -float(random.randint(8, 16))
                delta_tax_debt = float(random.randint(2_000, 12_000))
                delta_corruption = 3
                risk = 30
                details = "Запуск публичного скандала"
            elif op == "freeze":
                frozen = round(min(balance, random.uniform(1200, max(1800, balance * 0.5))), 2)
                delta_balance = -frozen
                delta_tax_debt = round(frozen * 0.2, 2)
                delta_corruption = 2
                risk = 34
                details = f"Заморозка средств: {frozen:.2f}"
            else:  # blackmail
                payoff = round(min(balance, random.uniform(1500, 8000)), 2)
                delta_balance = -payoff
                actor_shadow_gain = round(payoff * 0.75, 2)
                delta_reputation = -float(random.randint(5, 10))
                delta_corruption = 4
                risk = 48
                details = f"Извлечено через шантаж: {payoff:.2f}"

            new_balance = round(max(0.0, balance + delta_balance), 2)
            new_shadow = round(max(0.0, shadow + delta_shadow), 2)
            new_reputation = round(max(0.0, min(100.0, reputation + delta_reputation)), 2)
            new_tax_debt = round(max(0.0, tax_debt + delta_tax_debt), 2)
            new_corruption = max(0, corruption + delta_corruption)

            await db.execute(
                """
                UPDATE users
                SET balance = ?, shadow_balance = ?, reputation = ?, tax_debt = ?, corruption_score = ?
                WHERE user_id = ?
                """,
                (
                    new_balance,
                    new_shadow,
                    new_reputation,
                    new_tax_debt,
                    new_corruption,
                    int(target_id),
                ),
            )
            if actor_shadow_gain > 0:
                await db.execute(
                    "UPDATE users SET shadow_balance = COALESCE(shadow_balance, 0) + ? WHERE user_id = ?",
                    (actor_shadow_gain, int(actor_id)),
                )

            seized_amount = max(0.0, -delta_balance)
            if op == "freeze" and seized_amount > 0:
                await db.execute(
                    "UPDATE organizations SET budget = COALESCE(budget, 0) + ? WHERE name = 'Правительство'",
                    (seized_amount,),
                )

            await db.execute(
                """
                INSERT INTO corruption_ops
                (actor_id, target_id, op_type, amount, risk, status, details, created_date)
                VALUES (?, ?, ?, ?, ?, 'executed', ?, ?)
                """,
                (
                    int(actor_id),
                    int(target_id),
                    f"fbi_{op}",
                    round(max(0.0, -delta_balance + actor_shadow_gain + delta_tax_debt), 2),
                    int(risk),
                    details,
                    now,
                ),
            )
            await db.commit()

        op_labels = {
            "expose": "раскрытие материалов",
            "scandal": "публичный скандал",
            "freeze": "заморозка активов",
            "blackmail": "шантаж",
        }
        op_subjects = {
            "expose": "📂 Операция ФБР: раскрытие материалов",
            "scandal": "📰 Операция ФБР: публичный скандал",
            "freeze": "🔒 Операция ФБР: заморозка активов",
            "blackmail": "🤐 Операция ФБР: шантаж",
        }
        impact_lines: List[str] = []
        if delta_balance < 0:
            impact_lines.append(f"Списано с баланса: ${abs(delta_balance):,.2f}.")
        if delta_reputation < 0:
            impact_lines.append(f"Репутация снижена на {abs(delta_reputation):.1f}.")
        if delta_tax_debt > 0:
            impact_lines.append(f"Налоговый долг увеличен на ${delta_tax_debt:,.2f}.")
        if actor_shadow_gain > 0 and op == "blackmail":
            impact_lines.append("Часть средств выведена в теневой контур.")

        notice_lines = [
            f"По вам проведена операция ФБР: {op_labels.get(op, op)}.",
            f"Исполнитель: {actor_name}.",
        ]
        if details:
            notice_lines.append(f"Детали: {details}.")
        notice_lines.extend(impact_lines)
        target_notice_text = "\n".join(notice_lines)
        await self.send_private_message(
            sender_id=int(actor_id),
            recipient_id=int(target_id),
            subject=op_subjects.get(op, "⚠️ Операция ФБР"),
            content=target_notice_text,
            message_type="system",
        )

        if op == "scandal":
            severity = "critical" if max(0.0, delta_tax_debt) >= 8_000 else "high"
            await self.create_media_news(
                title=f"Публичный скандал: {target_name}",
                body=(
                    f"ФБР инициировало публичный скандал вокруг {target_name}. "
                    f"Репутация снижена на {abs(delta_reputation):.1f}, "
                    f"налоговый долг увеличен на ${max(0.0, delta_tax_debt):,.2f}."
                ),
                source_user_id=int(actor_id),
                severity=severity,
            )

        await self.log_player_activity(
            user_id=actor_id,
            activity_type="fbi_operation",
            details=f"FBI operation {op} vs #{int(target_id)}",
            value=max(0.0, actor_shadow_gain),
        )
        return True, "Операция выполнена.", {
            "operation": op,
            "risk": risk,
            "delta_balance": round(delta_balance, 2),
            "delta_reputation": round(delta_reputation, 2),
            "delta_tax_debt": round(delta_tax_debt, 2),
            "actor_shadow_gain": round(actor_shadow_gain, 2),
            "target_notice_text": target_notice_text,
        }

    async def get_organization_applications(
        self,
        org_id: int,
        status: Optional[str] = "pending",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 100))
        where_sql = "WHERE oa.org_id = ?"
        params: List[Any] = [int(org_id)]
        if status:
            where_sql += " AND oa.status = ?"
            params.append(str(status))
        params.append(safe_limit)

        query = f"""
            SELECT oa.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(oa.user_id AS TEXT)) AS applicant_name,
                   u.username AS applicant_username
            FROM organization_applications oa
            LEFT JOIN users u ON u.user_id = oa.user_id
            {where_sql}
            ORDER BY oa.applied_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def review_organization_application(
        self,
        reviewer_id: int,
        application_id: int,
        approve: bool,
        note: str = "",
    ) -> tuple[bool, str]:
        now = datetime.now().isoformat()
        clean_note = " ".join((note or "").strip().split())[:600]

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT * FROM organization_applications WHERE id = ?",
                (int(application_id),),
            ) as cursor:
                app = await cursor.fetchone()
            if not app:
                await db.rollback()
                return False, "Заявка не найдена."
            if str(app["status"]) != "pending":
                await db.rollback()
                return False, "Заявка уже рассмотрена."

            async with db.execute(
                "SELECT * FROM organizations WHERE id = ?",
                (int(app["org_id"]),),
            ) as cursor:
                org = await cursor.fetchone()
            if not org:
                await db.rollback()
                return False, "Организация не найдена."

            reviewer_id_int = int(reviewer_id)
            reviewer_is_manager = reviewer_id_int in {
                int(org["leader_id"] or 0),
                int(org["deputy_id"] or 0),
            }
            manager_tokens = (
                "лидер",
                "зам",
                "заместитель",
                "глава",
                "директор",
                "шеф",
                "руковод",
                "leader",
                "deputy",
                "director",
                "head",
                "chief",
                "manager",
            )

            if not reviewer_is_manager:
                async with db.execute(
                    "SELECT role FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                    (int(org["id"]), reviewer_id_int),
                ) as cursor:
                    reviewer_member = await cursor.fetchone()
                if reviewer_member:
                    role_lc = str(reviewer_member["role"] or "").strip().lower()
                    reviewer_is_manager = any(token in role_lc for token in manager_tokens)

            if not reviewer_is_manager:
                async with db.execute(
                    "SELECT organization, role FROM users WHERE user_id = ? LIMIT 1",
                    (reviewer_id_int,),
                ) as cursor:
                    reviewer_user = await cursor.fetchone()
                if reviewer_user:
                    same_org = str(reviewer_user["organization"] or "").strip().lower() == str(org["name"] or "").strip().lower()
                    role_lc = str(reviewer_user["role"] or "").strip().lower()
                    reviewer_is_manager = same_org and any(token in role_lc for token in manager_tokens)

            if not reviewer_is_manager:
                await db.rollback()
                return False, "Недостаточно прав для рассмотрения заявки."

            new_status = "approved" if approve else "rejected"
            await db.execute(
                """
                UPDATE organization_applications
                SET status = ?, reviewed_by = ?, reviewed_date = ?, notes = ?
                WHERE id = ?
                """,
                (new_status, int(reviewer_id), now, clean_note, int(application_id)),
            )

            if approve:
                async with db.execute(
                    "SELECT id FROM organization_members WHERE org_id = ? AND user_id = ? LIMIT 1",
                    (int(org["id"]), int(app["user_id"])),
                ) as cursor:
                    exists = await cursor.fetchone()
                if not exists:
                    await db.execute(
                        """
                        INSERT INTO organization_members
                        (org_id, user_id, role, salary, permissions, join_date, department, rank, experience, tasks_completed)
                        VALUES (?, ?, 'Стажер', 0, '', ?, 'general', 1, 0, 0)
                        """,
                        (int(org["id"]), int(app["user_id"]), now),
                    )
                await db.execute(
                    "UPDATE users SET organization = ?, role = COALESCE(NULLIF(role, ''), 'Стажер') WHERE user_id = ?",
                    (str(org["name"]), int(app["user_id"])),
                )
                async with db.execute(
                    "SELECT COUNT(*) AS c FROM organization_members WHERE org_id = ?",
                    (int(org["id"]),),
                ) as cursor:
                    row = await cursor.fetchone()
                members_count = int((row["c"] if row else 0) or 0)
                await db.execute(
                    "UPDATE organizations SET members = ? WHERE id = ?",
                    (members_count, int(org["id"])),
                )

            await db.commit()

        return True, ("Заявка одобрена." if approve else "Заявка отклонена.")

    async def create_revolution(
        self,
        organizer_id: int,
        manifesto: str,
        supporters_needed: int = 50,
        budget_spent: float = 100_000.0,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        clean_manifesto = " ".join((manifesto or "").strip().split())
        if len(clean_manifesto) < 20:
            return False, "Манифест слишком короткий.", None
        if len(clean_manifesto) > 500:
            clean_manifesto = clean_manifesto[:500]

        safe_needed = max(10, min(int(supporters_needed or 50), 500))
        safe_budget = round(max(1_000.0, float(budget_spent or 100_000.0)), 2)
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT id FROM revolutions WHERE organizer_id = ? AND status = 'active' LIMIT 1",
                (int(organizer_id),),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing:
                await db.rollback()
                return False, "У вас уже есть активная революция.", None

            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (int(organizer_id),)) as cursor:
                organizer = await cursor.fetchone()
            if not organizer:
                await db.rollback()
                return False, "Организатор не найден.", None
            balance = float(organizer["balance"] or 0)
            if balance < safe_budget:
                await db.rollback()
                return False, "Недостаточно средств для старта революции.", None

            gov = await self.get_government_system() or {}
            target_leader_id = int(gov.get("current_leader_id") or 0) or None
            new_balance = round(balance - safe_budget, 2)
            await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, int(organizer_id)))

            cursor = await db.execute(
                """
                INSERT INTO revolutions
                (started_date, ended_date, organizer_id, target_leader_id, new_government_type,
                 supporters_count, supporters_needed, status, reason, result)
                VALUES (?, NULL, ?, ?, NULL, 1, ?, 'active', ?, 'pending')
                """,
                (now, int(organizer_id), target_leader_id, safe_needed, clean_manifesto),
            )
            revolution_id = int(cursor.lastrowid or 0)
            await db.execute(
                """
                INSERT OR IGNORE INTO revolution_supporters (revolution_id, supporter_id, joined_date)
                VALUES (?, ?, ?)
                """,
                (revolution_id, int(organizer_id), now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=organizer_id,
            activity_type="revolution_started",
            details=f"Запущена революция #{revolution_id}",
            value=safe_budget,
        )
        return True, "Революция запущена.", {
            "revolution_id": revolution_id,
            "supporters_needed": safe_needed,
            "supporters_count": 1,
            "budget_spent": safe_budget,
        }

    async def get_active_revolutions(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT r.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
            FROM revolutions r
            LEFT JOIN users u ON u.user_id = r.organizer_id
            WHERE r.status = 'active'
            ORDER BY r.started_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_revolution_by_id(self, revolution_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT r.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
            FROM revolutions r
            LEFT JOIN users u ON u.user_id = r.organizer_id
            WHERE r.id = ?
            LIMIT 1
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(revolution_id),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def add_revolution_supporter(self, user_id: int, revolution_id: int) -> tuple[bool, str]:
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT id, organizer_id, supporters_needed, supporters_count, status FROM revolutions WHERE id = ? LIMIT 1",
                (int(revolution_id),),
            ) as cursor:
                rev = await cursor.fetchone()
            if not rev:
                await db.rollback()
                return False, "Революция не найдена."
            if str(rev["status"]) != "active":
                await db.rollback()
                return False, "Революция уже завершена."

            async with db.execute(
                "SELECT id FROM revolution_supporters WHERE revolution_id = ? AND supporter_id = ? LIMIT 1",
                (int(revolution_id), int(user_id)),
            ) as cursor:
                exists = await cursor.fetchone()
            if exists:
                await db.rollback()
                return False, "Вы уже поддержали эту революцию."

            await db.execute(
                "INSERT INTO revolution_supporters (revolution_id, supporter_id, joined_date) VALUES (?, ?, ?)",
                (int(revolution_id), int(user_id), now),
            )
            async with db.execute(
                "SELECT COUNT(*) AS c FROM revolution_supporters WHERE revolution_id = ?",
                (int(revolution_id),),
            ) as cursor:
                row = await cursor.fetchone()
                supporters_count = int((row["c"] if row else 0) or 0)

            status = "active"
            result = "pending"
            ended_date = None
            if supporters_count >= int(rev["supporters_needed"] or 0):
                status = "success"
                result = "support_threshold_reached"
                ended_date = now

            await db.execute(
                """
                UPDATE revolutions
                SET supporters_count = ?, status = ?, result = ?, ended_date = COALESCE(ended_date, ?)
                WHERE id = ?
                """,
                (supporters_count, status, result, ended_date, int(revolution_id)),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="revolution_supported",
            details=f"Поддержка революции #{int(revolution_id)}",
            value=1,
        )
        return True, "Вы присоединились к революции."

    async def boost_revolution_support(self, revolution_id: int, delta: int = 1) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        inc = max(1, min(int(delta or 1), 5))
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT id, supporters_count, supporters_needed, status FROM revolutions WHERE id = ? LIMIT 1",
                (int(revolution_id),),
            ) as cursor:
                rev = await cursor.fetchone()
            if not rev:
                await db.rollback()
                return False, "Революция не найдена.", None
            if str(rev["status"]) != "active":
                await db.rollback()
                return False, "Революция неактивна.", None

            supporters_count = int(rev["supporters_count"] or 0) + inc
            supporters_needed = int(rev["supporters_needed"] or 50)
            status = "active"
            result = "pending"
            ended_date = None
            if supporters_count >= supporters_needed:
                status = "success"
                result = "support_threshold_reached"
                ended_date = now
            await db.execute(
                """
                UPDATE revolutions
                SET supporters_count = ?, status = ?, result = ?, ended_date = COALESCE(ended_date, ?)
                WHERE id = ?
                """,
                (supporters_count, status, result, ended_date, int(revolution_id)),
            )
            await db.commit()

        return True, "Поддержка усилена.", {
            "supporters_count": supporters_count,
            "supporters_needed": supporters_needed,
            "status": status,
        }

    async def get_revolution_supporters(self, revolution_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 30), 200))
        query = """
            SELECT rs.revolution_id,
                   rs.supporter_id,
                   rs.joined_date,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(rs.supporter_id AS TEXT)) AS supporter_name,
                   u.username AS supporter_username,
                   CASE WHEN rs.supporter_id = r.organizer_id THEN 'Организатор' ELSE 'Сторонник' END AS role
            FROM revolution_supporters rs
            JOIN revolutions r ON r.id = rs.revolution_id
            LEFT JOIN users u ON u.user_id = rs.supporter_id
            WHERE rs.revolution_id = ?
            ORDER BY rs.joined_date ASC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (int(revolution_id), safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_revolution_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT r.*,
                   COALESCE(NULLIF(u.nickname, ''), NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
            FROM revolutions r
            LEFT JOIN users u ON u.user_id = r.organizer_id
            WHERE r.status != 'active'
            ORDER BY COALESCE(r.ended_date, r.started_date) DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    def _normalize_stock_symbol(self, symbol: Any) -> str:
        safe_symbol = str(symbol or "").strip().upper()[:12]
        if not safe_symbol:
            return ""
        if not re.fullmatch(r"[A-Z0-9]{2,12}", safe_symbol):
            return ""
        return safe_symbol

    async def _ensure_stock_exchange_tables(self, db_conn: Optional[aiosqlite.Connection] = None) -> None:
        own_connection = db_conn is None
        db = db_conn or await aiosqlite.connect(self.db_path)
        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_exchange_assets (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL DEFAULT 100,
                    prev_close REAL NOT NULL DEFAULT 100,
                    volatility REAL NOT NULL DEFAULT 0.03,
                    trend REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_exchange_portfolio (
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0,
                    avg_price REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, symbol)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_exchange_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    total REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_exchange_limit_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    percent INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_exchange_trades_user_date ON stock_exchange_trades(user_id, created_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_exchange_portfolio_user ON stock_exchange_portfolio(user_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_exchange_orders_user_status ON stock_exchange_limit_orders(user_id, status, id DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_exchange_orders_status ON stock_exchange_limit_orders(status, id ASC)"
            )

            async with db.execute("SELECT COUNT(*) FROM stock_exchange_assets") as cursor:
                row = await cursor.fetchone()
                count = int((row[0] if row else 0) or 0)

            if count <= 0:
                now = datetime.now().isoformat()
                for asset in STOCK_EXCHANGE_ASSETS:
                    symbol = self._normalize_stock_symbol(asset.get("symbol"))
                    if not symbol:
                        continue
                    price = round(max(1.0, float(asset.get("price") or 100.0)), 2)
                    volatility = max(0.005, min(float(asset.get("volatility") or 0.03), 0.12))
                    trend = max(-0.03, min(float(asset.get("trend") or 0.0), 0.03))
                    name = str(asset.get("name") or symbol).strip()[:64] or symbol
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO stock_exchange_assets
                        (symbol, name, price, prev_close, volatility, trend, updated_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (symbol, name, price, price, volatility, trend, now),
                    )

            if own_connection:
                await db.commit()
        finally:
            if own_connection:
                await db.close()

    async def update_stock_exchange_market(
        self,
        force: bool = False,
        interval_minutes: int = 10,
    ) -> Dict[str, Any]:
        safe_interval = max(1, min(int(interval_minutes or 10), 180))
        now_dt = datetime.now()
        last_tick_raw = await self.get_system_state("stock_exchange_last_tick")
        last_tick_dt = _parse_iso_datetime(last_tick_raw)

        if not force and last_tick_dt:
            delta_sec = (now_dt - last_tick_dt).total_seconds()
            if delta_sec < safe_interval * 60:
                remain = int((safe_interval * 60 - delta_sec + 59) // 60)
                return {"updated": False, "minutes_to_next": max(1, remain)}

        changed_symbols: List[str] = []
        abs_changes: List[float] = []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)
            async with db.execute(
                """
                SELECT symbol, price, volatility, trend
                FROM stock_exchange_assets
                WHERE is_active = 1
                ORDER BY symbol ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()

            now = now_dt.isoformat()
            for row in rows:
                symbol = str(row["symbol"] or "").strip()
                old_price = round(max(1.0, float(row["price"] or 1.0)), 2)
                volatility = max(0.005, min(float(row["volatility"] or 0.03), 0.12))
                trend = max(-0.03, min(float(row["trend"] or 0.0), 0.03))

                random_component = random.uniform(-volatility, volatility)
                impulse_component = random.uniform(-0.004, 0.004)
                relative_change = max(-0.18, min(0.18, random_component + trend + impulse_component))
                new_price = round(max(1.0, old_price * (1 + relative_change)), 2)
                new_trend = max(-0.03, min(0.03, trend * 0.72 + random.uniform(-0.003, 0.003)))

                await db.execute(
                    """
                    UPDATE stock_exchange_assets
                    SET prev_close = ?, price = ?, trend = ?, updated_at = ?
                    WHERE symbol = ?
                    """,
                    (old_price, new_price, new_trend, now, symbol),
                )
                changed_symbols.append(symbol)
                abs_changes.append(abs(relative_change))
            await db.commit()

        await self.set_system_state("stock_exchange_last_tick", now_dt.isoformat())
        order_result = await self.process_stock_limit_orders(max_orders=80)
        avg_abs_change = (sum(abs_changes) / len(abs_changes)) if abs_changes else 0.0
        return {
            "updated": True,
            "assets_changed": len(changed_symbols),
            "avg_abs_change_pct": round(avg_abs_change * 100, 3),
            "minutes_to_next": safe_interval,
            "orders_executed": int(order_result.get("executed") or 0),
            "orders_failed": int(order_result.get("failed") or 0),
            "orders_scanned": int(order_result.get("scanned") or 0),
        }

    async def get_stock_exchange_snapshot(self, user_id: int, refresh: bool = True) -> Dict[str, Any]:
        await self._ensure_stock_exchange_tables()
        if refresh:
            await self.update_stock_exchange_market(force=False, interval_minutes=10)

        payload: Dict[str, Any] = {
            "assets": [],
            "holdings": [],
            "trades": [],
            "balance": 0.0,
            "portfolio_value": 0.0,
            "portfolio_cost": 0.0,
            "portfolio_pnl": 0.0,
            "market_change_avg_pct": 0.0,
            "last_tick": await self.get_system_state("stock_exchange_last_tick") or "",
            "open_orders": 0,
            "dividend_status": {},
        }

        user = await self.get_user(int(user_id)) or {}
        payload["balance"] = round(float(user.get("balance") or 0.0), 2)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._ensure_stock_exchange_tables(db)

            async with db.execute(
                """
                SELECT symbol, name, price, prev_close, volatility, trend, updated_at
                FROM stock_exchange_assets
                WHERE is_active = 1
                ORDER BY symbol ASC
                """
            ) as cursor:
                asset_rows = await cursor.fetchall()

            assets_out: List[Dict[str, Any]] = []
            market_changes: List[float] = []
            price_map: Dict[str, Dict[str, float]] = {}
            for row in asset_rows:
                symbol = str(row["symbol"] or "").strip()
                price = round(float(row["price"] or 0.0), 2)
                prev_close = round(float(row["prev_close"] or price or 1.0), 2)
                if prev_close <= 0:
                    prev_close = price or 1.0
                change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
                market_changes.append(change_pct)
                asset_data = {
                    "symbol": symbol,
                    "name": str(row["name"] or symbol),
                    "price": price,
                    "prev_close": prev_close,
                    "change_pct": round(change_pct, 3),
                    "volatility": round(float(row["volatility"] or 0.0), 4),
                    "trend": round(float(row["trend"] or 0.0), 4),
                    "updated_at": str(row["updated_at"] or ""),
                }
                assets_out.append(asset_data)
                price_map[symbol] = {"price": price}

            async with db.execute(
                """
                SELECT p.user_id, p.symbol, p.quantity, p.avg_price, p.updated_at
                FROM stock_exchange_portfolio p
                WHERE p.user_id = ?
                ORDER BY p.symbol ASC
                """,
                (int(user_id),),
            ) as cursor:
                holding_rows = await cursor.fetchall()

            holdings_out: List[Dict[str, Any]] = []
            portfolio_value = 0.0
            portfolio_cost = 0.0
            for row in holding_rows:
                symbol = str(row["symbol"] or "").strip()
                qty = round(max(0.0, float(row["quantity"] or 0.0)), 4)
                if qty <= 0:
                    continue
                avg_price = round(max(0.0, float(row["avg_price"] or 0.0)), 4)
                current_price = round(float((price_map.get(symbol) or {}).get("price") or 0.0), 2)
                current_value = round(qty * current_price, 2)
                cost_value = round(qty * avg_price, 2)
                pnl = round(current_value - cost_value, 2)
                portfolio_value += current_value
                portfolio_cost += cost_value
                holdings_out.append(
                    {
                        "symbol": symbol,
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "current_value": current_value,
                        "cost_value": cost_value,
                        "pnl": pnl,
                        "updated_at": str(row["updated_at"] or ""),
                    }
                )

            async with db.execute(
                """
                SELECT id, symbol, side, quantity, price, total, created_at
                FROM stock_exchange_trades
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (int(user_id),),
            ) as cursor:
                trade_rows = await cursor.fetchall()
                payload["trades"] = [dict(row) for row in trade_rows]

            async with db.execute(
                """
                SELECT COUNT(*)
                FROM stock_exchange_limit_orders
                WHERE user_id = ? AND status = 'open'
                """,
                (int(user_id),),
            ) as cursor:
                row = await cursor.fetchone()
                payload["open_orders"] = int((row[0] if row else 0) or 0)

        payload["assets"] = assets_out
        payload["holdings"] = holdings_out
        payload["portfolio_value"] = round(portfolio_value, 2)
        payload["portfolio_cost"] = round(portfolio_cost, 2)
        payload["portfolio_pnl"] = round(portfolio_value - portfolio_cost, 2)
        payload["market_change_avg_pct"] = round(
            (sum(market_changes) / len(market_changes)) if market_changes else 0.0,
            3,
        )
        payload["dividend_status"] = await self.get_stock_dividend_status(user_id)
        return payload

    async def stock_exchange_buy(
        self,
        user_id: int,
        symbol: str,
        amount: float,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_symbol = self._normalize_stock_symbol(symbol)
        safe_amount = round(float(amount or 0.0), 2)
        if not safe_symbol:
            return False, "Некорректный тикер.", None
        if safe_amount < 100:
            return False, "Минимальная сумма покупки: $100.", None
        if safe_amount > 5_000_000:
            return False, "Сумма слишком большая.", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)

            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "Профиль не найден.", None

            balance = round(float(user_row["balance"] or 0.0), 2)
            if balance < safe_amount:
                await db.rollback()
                return False, "Недостаточно средств для покупки.", None

            async with db.execute(
                """
                SELECT symbol, name, price
                FROM stock_exchange_assets
                WHERE symbol = ? AND is_active = 1
                LIMIT 1
                """,
                (safe_symbol,),
            ) as cursor:
                asset = await cursor.fetchone()
            if not asset:
                await db.rollback()
                return False, "Актив не найден.", None

            price = round(max(1.0, float(asset["price"] or 1.0)), 2)
            quantity = round(safe_amount / price, 4)
            if quantity <= 0:
                await db.rollback()
                return False, "Слишком маленькая сумма для этой цены.", None
            total_cost = round(quantity * price, 2)
            if total_cost <= 0 or total_cost > balance:
                await db.rollback()
                return False, "Недостаточно средств для этой сделки.", None

            async with db.execute(
                """
                SELECT quantity, avg_price
                FROM stock_exchange_portfolio
                WHERE user_id = ? AND symbol = ?
                LIMIT 1
                """,
                (int(user_id), safe_symbol),
            ) as cursor:
                holding = await cursor.fetchone()

            if holding:
                old_qty = round(float(holding["quantity"] or 0.0), 4)
                old_avg = round(float(holding["avg_price"] or 0.0), 4)
                new_qty = round(old_qty + quantity, 4)
                if new_qty <= 0:
                    await db.rollback()
                    return False, "Ошибка количества позиции.", None
                new_avg = round(((old_qty * old_avg) + (quantity * price)) / new_qty, 4)
                await db.execute(
                    """
                    UPDATE stock_exchange_portfolio
                    SET quantity = ?, avg_price = ?, updated_at = ?
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (new_qty, new_avg, now, int(user_id), safe_symbol),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO stock_exchange_portfolio (user_id, symbol, quantity, avg_price, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(user_id), safe_symbol, quantity, round(price, 4), now),
                )
                new_qty = quantity
                new_avg = round(price, 4)

            new_balance = round(balance - total_cost, 2)
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO stock_exchange_trades
                (user_id, symbol, side, quantity, price, total, created_at)
                VALUES (?, ?, 'buy', ?, ?, ?, ?)
                """,
                (int(user_id), safe_symbol, quantity, price, total_cost, now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="stock_buy",
            details=f"Покупка {safe_symbol}: {quantity:.4f} шт по ${price:,.2f}",
            value=total_cost,
        )
        if total_cost >= 80_000:
            await self.create_media_news(
                title=f"Крупная биржевая покупка: {safe_symbol}",
                body=f"Игрок совершил крупную покупку {safe_symbol} на ${total_cost:,.2f}.",
                source_user_id=user_id,
                severity="hot",
            )

        return True, "Сделка покупки исполнена.", {
            "symbol": safe_symbol,
            "name": str(asset["name"] or safe_symbol),
            "quantity": quantity,
            "price": price,
            "total": total_cost,
            "new_qty": new_qty,
            "avg_price": new_avg,
            "new_balance": new_balance,
        }

    async def stock_exchange_sell_percent(
        self,
        user_id: int,
        symbol: str,
        percent: int,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_symbol = self._normalize_stock_symbol(symbol)
        safe_percent = max(1, min(int(percent or 0), 100))
        if not safe_symbol:
            return False, "Некорректный тикер.", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)

            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "Профиль не найден.", None
            balance = round(float(user_row["balance"] or 0.0), 2)

            async with db.execute(
                """
                SELECT symbol, name, price
                FROM stock_exchange_assets
                WHERE symbol = ? AND is_active = 1
                LIMIT 1
                """,
                (safe_symbol,),
            ) as cursor:
                asset = await cursor.fetchone()
            if not asset:
                await db.rollback()
                return False, "Актив не найден.", None
            price = round(max(1.0, float(asset["price"] or 1.0)), 2)

            async with db.execute(
                """
                SELECT quantity, avg_price
                FROM stock_exchange_portfolio
                WHERE user_id = ? AND symbol = ?
                LIMIT 1
                """,
                (int(user_id), safe_symbol),
            ) as cursor:
                holding = await cursor.fetchone()
            if not holding:
                await db.rollback()
                return False, "У вас нет этой акции.", None

            old_qty = round(float(holding["quantity"] or 0.0), 4)
            avg_price = round(float(holding["avg_price"] or 0.0), 4)
            if old_qty <= 0:
                await db.rollback()
                return False, "У вас нет доступного объема для продажи.", None

            sell_qty = old_qty if safe_percent >= 100 else round(old_qty * safe_percent / 100.0, 4)
            if sell_qty <= 0:
                await db.rollback()
                return False, "Слишком маленький объем продажи.", None
            if sell_qty > old_qty:
                sell_qty = old_qty

            proceeds = round(sell_qty * price, 2)
            cost_basis = round(sell_qty * avg_price, 2)
            pnl = round(proceeds - cost_basis, 2)
            new_qty = round(old_qty - sell_qty, 4)

            if new_qty <= 0.00009:
                await db.execute(
                    "DELETE FROM stock_exchange_portfolio WHERE user_id = ? AND symbol = ?",
                    (int(user_id), safe_symbol),
                )
                new_qty = 0.0
            else:
                await db.execute(
                    """
                    UPDATE stock_exchange_portfolio
                    SET quantity = ?, updated_at = ?
                    WHERE user_id = ? AND symbol = ?
                    """,
                    (new_qty, now, int(user_id), safe_symbol),
                )

            new_balance = round(balance + proceeds, 2)
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO stock_exchange_trades
                (user_id, symbol, side, quantity, price, total, created_at)
                VALUES (?, ?, 'sell', ?, ?, ?, ?)
                """,
                (int(user_id), safe_symbol, sell_qty, price, proceeds, now),
            )
            await db.commit()

        await self.log_player_activity(
            user_id=user_id,
            activity_type="stock_sell",
            details=f"Продажа {safe_symbol}: {sell_qty:.4f} шт по ${price:,.2f}",
            value=proceeds,
        )
        if proceeds >= 80_000:
            await self.create_media_news(
                title=f"Крупная биржевая продажа: {safe_symbol}",
                body=f"Игрок зафиксировал сделку {safe_symbol} на ${proceeds:,.2f}.",
                source_user_id=user_id,
                severity="hot",
            )

        return True, "Сделка продажи исполнена.", {
            "symbol": safe_symbol,
            "name": str(asset["name"] or safe_symbol),
            "sold_qty": sell_qty,
            "price": price,
            "proceeds": proceeds,
            "pnl": pnl,
            "new_qty": new_qty,
            "new_balance": new_balance,
            "percent": safe_percent,
        }

    async def get_stock_exchange_recent_trades(self, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 12), 50))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._ensure_stock_exchange_tables(db)
            async with db.execute(
                """
                SELECT id, symbol, side, quantity, price, total, created_at
                FROM stock_exchange_trades
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(user_id), safe_limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    def _is_stock_order_triggered(self, order_type: str, current_price: float, target_price: float) -> bool:
        safe_type = str(order_type or "").strip().lower()
        current = float(current_price or 0.0)
        target = float(target_price or 0.0)
        if current <= 0 or target <= 0:
            return False
        if safe_type == "buy_limit":
            return current <= target
        if safe_type == "sell_take":
            return current >= target
        if safe_type == "sell_stop":
            return current <= target
        return False

    async def place_stock_limit_order(
        self,
        user_id: int,
        symbol: str,
        order_type: str,
        target_price: float,
        amount: float = 0.0,
        percent: int = 0,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        safe_symbol = self._normalize_stock_symbol(symbol)
        safe_type = str(order_type or "").strip().lower()
        safe_target = round(float(target_price or 0.0), 2)
        safe_amount = round(float(amount or 0.0), 2)
        safe_percent = max(0, min(int(percent or 0), 100))

        if safe_symbol == "":
            return False, "Некорректный тикер.", None
        if safe_type not in {"buy_limit", "sell_take", "sell_stop"}:
            return False, "Некорректный тип ордера.", None
        if safe_target < 1:
            return False, "Некорректная целевая цена.", None
        if safe_type == "buy_limit" and safe_amount < 100:
            return False, "Минимальный размер buy-ордера: $100.", None
        if safe_type in {"sell_take", "sell_stop"} and safe_percent < 1:
            return False, "Для sell-ордера нужен процент 1-100.", None

        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)

            async with db.execute(
                "SELECT symbol, name, price FROM stock_exchange_assets WHERE symbol = ? AND is_active = 1 LIMIT 1",
                (safe_symbol,),
            ) as cursor:
                asset_row = await cursor.fetchone()
            if not asset_row:
                await db.rollback()
                return False, "Актив не найден.", None

            if safe_type in {"sell_take", "sell_stop"}:
                async with db.execute(
                    "SELECT quantity FROM stock_exchange_portfolio WHERE user_id = ? AND symbol = ? LIMIT 1",
                    (int(user_id), safe_symbol),
                ) as cursor:
                    holding = await cursor.fetchone()
                if not holding or float(holding["quantity"] or 0.0) <= 0:
                    await db.rollback()
                    return False, "Нет позиции по этой акции для sell-ордера.", None

            cursor = await db.execute(
                """
                INSERT INTO stock_exchange_limit_orders
                (user_id, symbol, order_type, target_price, amount, percent, status, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', '', ?, ?)
                """,
                (
                    int(user_id),
                    safe_symbol,
                    safe_type,
                    safe_target,
                    safe_amount,
                    safe_percent,
                    now,
                    now,
                ),
            )
            order_id = int(cursor.lastrowid or 0)
            await db.commit()

        return True, "Ордер создан.", {
            "order_id": order_id,
            "symbol": safe_symbol,
            "order_type": safe_type,
            "target_price": safe_target,
            "amount": safe_amount,
            "percent": safe_percent,
            "current_price": round(float(asset_row["price"] or 0.0), 2),
            "name": str(asset_row["name"] or safe_symbol),
        }

    async def get_stock_limit_orders(
        self,
        user_id: int,
        status: str = "open",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        safe_status = str(status or "open").strip().lower()
        if safe_status not in {"open", "executed", "canceled", "failed", "all"}:
            safe_status = "open"

        await self._ensure_stock_exchange_tables()
        query = """
            SELECT o.*,
                   a.name AS asset_name,
                   a.price AS current_price
            FROM stock_exchange_limit_orders o
            LEFT JOIN stock_exchange_assets a ON a.symbol = o.symbol
            WHERE o.user_id = ?
        """
        params: List[Any] = [int(user_id)]
        if safe_status != "all":
            query += " AND o.status = ?"
            params.append(safe_status)
        query += " ORDER BY o.id DESC LIMIT ?"
        params.append(safe_limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._ensure_stock_exchange_tables(db)
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def cancel_stock_limit_order(self, user_id: int, order_id: int) -> tuple[bool, str]:
        safe_order_id = int(order_id or 0)
        if safe_order_id <= 0:
            return False, "Некорректный ID ордера."

        now = datetime.now().isoformat()
        await self._ensure_stock_exchange_tables()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)
            async with db.execute(
                "SELECT id, status FROM stock_exchange_limit_orders WHERE id = ? AND user_id = ? LIMIT 1",
                (safe_order_id, int(user_id)),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return False, "Ордер не найден."
            if str(row["status"] or "") != "open":
                await db.rollback()
                return False, "Отменить можно только открытый ордер."

            await db.execute(
                """
                UPDATE stock_exchange_limit_orders
                SET status = 'canceled', note = 'Отменен пользователем', updated_at = ?
                WHERE id = ?
                """,
                (now, safe_order_id),
            )
            await db.commit()
        return True, "Ордер отменен."

    async def process_stock_limit_orders(self, max_orders: int = 80) -> Dict[str, Any]:
        safe_limit = max(1, min(int(max_orders or 80), 400))
        await self._ensure_stock_exchange_tables()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._ensure_stock_exchange_tables(db)
            async with db.execute(
                """
                SELECT o.id, o.user_id, o.symbol, o.order_type, o.target_price, o.amount, o.percent,
                       a.price AS current_price
                FROM stock_exchange_limit_orders o
                LEFT JOIN stock_exchange_assets a ON a.symbol = o.symbol
                WHERE o.status = 'open'
                ORDER BY o.id ASC
                LIMIT ?
                """,
                (safe_limit,),
            ) as cursor:
                orders = [dict(row) for row in (await cursor.fetchall())]

        scanned = len(orders)
        triggered = 0
        executed = 0
        failed = 0

        for order in orders:
            order_id = int(order.get("id") or 0)
            if order_id <= 0:
                continue
            order_type = str(order.get("order_type") or "").strip().lower()
            symbol = str(order.get("symbol") or "").strip().upper()
            current_price = float(order.get("current_price") or 0.0)
            target_price = float(order.get("target_price") or 0.0)
            if not self._is_stock_order_triggered(order_type, current_price, target_price):
                continue
            triggered += 1

            user_id = int(order.get("user_id") or 0)
            success = False
            msg = "Неизвестная ошибка."
            if order_type == "buy_limit":
                success, msg, _ = await self.stock_exchange_buy(
                    user_id=user_id,
                    symbol=symbol,
                    amount=float(order.get("amount") or 0.0),
                )
            elif order_type in {"sell_take", "sell_stop"}:
                success, msg, _ = await self.stock_exchange_sell_percent(
                    user_id=user_id,
                    symbol=symbol,
                    percent=int(order.get("percent") or 0),
                )

            now = datetime.now().isoformat()
            async with aiosqlite.connect(self.db_path) as db:
                await self._ensure_stock_exchange_tables(db)
                if success:
                    executed += 1
                    await db.execute(
                        """
                        UPDATE stock_exchange_limit_orders
                        SET status = 'executed',
                            note = ?,
                            updated_at = ?
                        WHERE id = ? AND status = 'open'
                        """,
                        (f"Исполнен по цене ${current_price:,.2f}", now, order_id),
                    )
                else:
                    failed += 1
                    lowered = str(msg or "").lower()
                    hard_fail = ("актив не найден" in lowered) or ("некоррект" in lowered)
                    if hard_fail:
                        await db.execute(
                            """
                            UPDATE stock_exchange_limit_orders
                            SET status = 'failed',
                                note = ?,
                                updated_at = ?
                            WHERE id = ? AND status = 'open'
                            """,
                            (str(msg or "")[:240], now, order_id),
                        )
                    else:
                        await db.execute(
                            """
                            UPDATE stock_exchange_limit_orders
                            SET note = ?, updated_at = ?
                            WHERE id = ? AND status = 'open'
                            """,
                            (str(msg or "")[:240], now, order_id),
                        )
                await db.commit()

        return {
            "scanned": scanned,
            "triggered": triggered,
            "executed": executed,
            "failed": failed,
        }

    async def get_stock_dividend_status(self, user_id: int) -> Dict[str, Any]:
        key = f"stock_dividend_last_{int(user_id)}"
        last_raw = await self.get_system_state(key)
        last_dt = _parse_iso_datetime(last_raw)
        now = datetime.now()
        can_claim = True
        minutes_to_next = 0

        if last_dt and last_dt.date() == now.date():
            can_claim = False
            next_dt = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            delta_seconds = max(0.0, (next_dt - now).total_seconds())
            minutes_to_next = int((delta_seconds + 59) // 60)

        return {
            "can_claim": can_claim,
            "last_claim_at": last_raw or "",
            "minutes_to_next": minutes_to_next,
        }

    async def claim_stock_dividends(self, user_id: int) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        now_dt = datetime.now()
        now = now_dt.isoformat()
        key = f"stock_dividend_last_{int(user_id)}"
        await self._ensure_stock_exchange_tables()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            await self._ensure_stock_exchange_tables(db)

            async with db.execute(
                "SELECT value FROM system_state WHERE key = ? LIMIT 1",
                (key,),
            ) as cursor:
                state_row = await cursor.fetchone()
            claimed_raw = str(state_row["value"]) if state_row and state_row["value"] is not None else ""
            claimed_dt = _parse_iso_datetime(claimed_raw)
            if claimed_dt and claimed_dt.date() == now_dt.date():
                await db.rollback()
                status = await self.get_stock_dividend_status(user_id)
                return False, f"Дивиденды уже получены. Повтор через {int(status.get('minutes_to_next') or 0)} мин.", None

            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ) as cursor:
                user_row = await cursor.fetchone()
            if not user_row:
                await db.rollback()
                return False, "Профиль не найден.", None
            balance = float(user_row["balance"] or 0.0)

            async with db.execute(
                """
                SELECT p.symbol, p.quantity, a.price, a.volatility, a.trend
                FROM stock_exchange_portfolio p
                JOIN stock_exchange_assets a ON a.symbol = p.symbol
                WHERE p.user_id = ? AND p.quantity > 0 AND a.is_active = 1
                """,
                (int(user_id),),
            ) as cursor:
                holdings = [dict(row) for row in (await cursor.fetchall())]
            if not holdings:
                await db.rollback()
                return False, "Нет позиций в портфеле для начисления дивидендов.", None

            total_value = 0.0
            payout = 0.0
            details: List[Dict[str, Any]] = []
            for row in holdings:
                qty = max(0.0, float(row.get("quantity") or 0.0))
                price = max(0.0, float(row.get("price") or 0.0))
                if qty <= 0 or price <= 0:
                    continue
                symbol = str(row.get("symbol") or "").strip().upper()
                volatility = max(0.005, min(float(row.get("volatility") or 0.03), 0.12))
                trend = max(-0.03, min(float(row.get("trend") or 0.0), 0.03))
                current_value = round(qty * price, 2)
                total_value += current_value

                base_rate = 0.00085
                trend_bonus = max(-0.0005, min(0.0006, trend * 0.04))
                stability_bonus = max(-0.0004, min(0.0005, (0.04 - volatility) * 0.02))
                raw_rate = base_rate + trend_bonus + stability_bonus + random.uniform(-0.0001, 0.00015)
                dividend_rate = max(0.0003, min(raw_rate, 0.0024))
                amount = round(current_value * dividend_rate, 2)
                if amount <= 0:
                    continue
                payout += amount
                details.append({"symbol": symbol, "amount": amount, "rate": dividend_rate, "value": current_value})

            payout = round(payout, 2)
            if payout <= 0:
                await db.rollback()
                return False, "Сегодня дивиденды по вашим активам не начислены.", None

            new_balance = round(balance + payout, 2)
            await db.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (new_balance, int(user_id)),
            )
            await db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, now),
            )
            await db.commit()

        avg_yield_pct = round((payout / total_value * 100.0), 4) if total_value > 0 else 0.0
        await self.log_player_activity(
            user_id=user_id,
            activity_type="stock_dividend_claim",
            details=f"Начислены дивиденды: ${payout:,.2f}",
            value=payout,
        )
        if payout >= 18_000:
            await self.create_media_news(
                title="Крупная дивидендная выплата на бирже",
                body=f"Игрок получил дивиденды на сумму ${payout:,.2f}.",
                source_user_id=user_id,
                severity="hot",
            )

        return True, "Дивиденды зачислены.", {
            "payout": payout,
            "new_balance": new_balance,
            "total_value": round(total_value, 2),
            "avg_yield_pct": avg_yield_pct,
            "details": details[:12],
        }

    async def get_economy_statistics(self) -> Dict[str, Any]:
        """Получить макроэкономическую статистику: ВВП, денежная масса, и т.д."""
        async with aiosqlite.connect(self.db_path) as db:
            # Общий актив игроков
            async with db.execute(
                "SELECT COALESCE(SUM(balance + bank + cash + shadow_balance), 0.0) FROM users"
            ) as cursor:
                player_wealth = float((await cursor.fetchone())[0] or 0.0)
            
            # Бюджет правительства
            async with db.execute(
                "SELECT COALESCE(SUM(budget), 0.0) FROM organizations WHERE type = 'government'"
            ) as cursor:
                gov_budget = float((await cursor.fetchone())[0] or 0.0)
            
            # Бюджет организаций
            async with db.execute(
                "SELECT COALESCE(SUM(budget), 0.0) FROM organizations WHERE type != 'government' AND type != 'private_org'"
            ) as cursor:
                org_budgets = float((await cursor.fetchone())[0] or 0.0)
            
            # Количество игроков и организаций
            async with db.execute("SELECT COUNT(*) FROM users WHERE balance + bank + cash + shadow_balance > 0") as cursor:
                active_players = int((await cursor.fetchone())[0] or 0)
            
            async with db.execute("SELECT COUNT(*) FROM organizations") as cursor:
                total_orgs = int((await cursor.fetchone())[0] or 0)
            
            # Среднее благосостояние
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_players = int((await cursor.fetchone())[0] or 0)
            
            avg_wealth = round(player_wealth / total_players, 2) if total_players > 0 else 0.0
            
            # ВВП (валовый внутренний продукт) = сумма всех денег в экономике
            gdp = round(player_wealth + gov_budget + org_budgets, 2)
            
            return {
                "gdp": gdp,
                "player_wealth": round(player_wealth, 2),
                "government_budget": round(gov_budget, 2),
                "organization_budgets": round(org_budgets, 2),
                "total_money_supply": gdp,  # alias
                "active_players": active_players,
                "total_players": total_players,
                "total_organizations": total_orgs,
                "average_wealth_per_player": avg_wealth,
            }

    async def get_money_flow_report(self) -> Dict[str, Any]:
        """Получить отчет о движении денег в экономике (за последний день)."""
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        today = datetime.now().date().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Налоги собраны
            async with db.execute(
                """
                SELECT COALESCE(SUM(paid_total), 0.0)
                FROM daily_tax_invoices
                WHERE status = 'paid' AND DATE(paid_date) = ?
                """,
                (today,),
            ) as cursor:
                taxes_collected = float((await cursor.fetchone())[0] or 0.0)
            
            # Налоги в долг (начислено)
            async with db.execute(
                """
                SELECT COALESCE(SUM(
                    COALESCE(citizen_tax, 0) + 
                    COALESCE(property_tax, 0) + 
                    COALESCE(business_tax, 0) + 
                    COALESCE(org_tax, 0)
                ), 0.0)
                FROM tax_logs
                WHERE DATE(created_at) = ?
                """,
                (today,),
            ) as cursor:
                taxes_charged = float((await cursor.fetchone())[0] or 0.0)
            
            # Зарплаты выплачены
            async with db.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0)
                FROM player_activity_log
                WHERE activity_type = 'salary_received' AND DATE(created_date) = ?
                """,
                (today,),
            ) as cursor:
                salaries_paid = float((await cursor.fetchone())[0] or 0.0)
            
            # Кредиты выданы
            async with db.execute(
                """
                SELECT COALESCE(SUM(principal), 0.0)
                FROM loans
                WHERE status IN ('approved', 'active') AND DATE(application_date) = ?
                """,
                (today,),
            ) as cursor:
                loans_issued = float((await cursor.fetchone())[0] or 0.0)
            
            # Кредиты погашены
            async with db.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0)
                FROM player_activity_log
                WHERE activity_type = 'loan_payment' AND DATE(created_date) = ?
                """,
                (today,),
            ) as cursor:
                loans_repaid = float((await cursor.fetchone())[0] or 0.0)
            
            # Штрафы уплачены
            async with db.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0)
                FROM player_activity_log
                WHERE activity_type = 'fine_paid' AND DATE(created_date) = ?
                """,
                (today,),
            ) as cursor:
                fines_paid = float((await cursor.fetchone())[0] or 0.0)
            
            # Общие движения денег
            inflows = round(taxes_collected + loans_repaid + salaries_paid, 2)  # в гос бюджет
            outflows = round(loans_issued + fines_paid, 2)  # из гос бюджета
            net_flow = round(inflows - outflows, 2)
            
            return {
                "period": today,
                "taxes_collected": round(taxes_collected, 2),
                "taxes_charged": round(taxes_charged, 2),
                "taxes_unpaid_debt": round(taxes_charged - taxes_collected, 2),
                "salaries_paid": round(salaries_paid, 2),
                "loans_issued": round(loans_issued, 2),
                "loans_repaid": round(loans_repaid, 2),
                "fines_paid": round(fines_paid, 2),
                "total_inflows": inflows,
                "total_outflows": outflows,
                "net_flow": net_flow,
            }

    async def destroy_money_from_economy(
        self,
        amount: float,
        reason: str = "Удаление денег из экономики",
    ) -> tuple[bool, str, Dict[str, Any]]:
        """
        Удалить деньги из экономики (выкинуть из игры).
        Деньги берутся из правительственного бюджета.
        """
        amount = round(float(amount or 0.0), 2)
        if amount <= 0:
            return False, "Сумма должна быть положительной.", {}
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Получить правительственный бюджет
            async with db.execute(
                "SELECT id, budget FROM organizations WHERE name = 'Правительство' LIMIT 1"
            ) as cursor:
                gov = await cursor.fetchone()
            
            if not gov:
                return False, "Правительство не найдено.", {}
            
            gov_id = int(gov["id"] or 0)
            gov_budget = float(gov["budget"] or 0)
            
            if gov_budget < amount:
                return False, f"Недостаточно бюджета. Доступно ${gov_budget:,.2f}", {
                    "available": gov_budget,
                    "requested": amount,
                }
            
            # Удалить деньги
            new_budget = round(gov_budget - amount, 2)
            now = datetime.now().isoformat()
            
            await db.execute(
                "UPDATE organizations SET budget = ? WHERE id = ?",
                (new_budget, gov_id),
            )
            
            # Логирование
            await db.execute(
                """
                INSERT INTO player_activity_log
                (user_id, activity_type, details, value, created_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (0, "money_destroyed", reason, amount, now),
            )
            
            await db.commit()
        
        return True, f"✅ ${amount:,.2f} удалено из экономики.", {
            "amount": amount,
            "reason": reason,
            "budget_before": gov_budget,
            "budget_after": new_budget,
        }

    async def get_player_transfer_history(
        self,
        user_id: int,
        limit: int = 25,
        include_direction: Optional[str] = None,  # "sent", "received", or None for both
    ) -> List[Dict[str, Any]]:
        """
        Получить историю переводов игрока.
        include_direction: 'sent' (исходящие), 'received' (входящие), или None (все)
        """
        safe_limit = max(1, min(int(limit or 25), 100))
        safe_user_id = int(user_id or 0)
        safe_direction = str(include_direction or "").lower().strip()
        
        if safe_direction not in {"sent", "received", ""}:
            safe_direction = ""
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if safe_direction == "sent":
                # Исходящие переводы
                query = """
                    SELECT id, user_id, tx_type, amount, balance_before, balance_after, 
                           bank_before, bank_after, note, created_date
                    FROM bank_transactions
                    WHERE user_id = ? AND tx_type = 'transfer_out'
                    ORDER BY created_date DESC
                    LIMIT ?
                """
            elif safe_direction == "received":
                # Входящие переводы
                query = """
                    SELECT id, user_id, tx_type, amount, balance_before, balance_after,
                           bank_before, bank_after, note, created_date
                    FROM bank_transactions
                    WHERE user_id = ? AND tx_type = 'transfer_in'
                    ORDER BY created_date DESC
                    LIMIT ?
                """
            else:
                # Все переводы (отправленные и полученные)
                query = """
                    SELECT id, user_id, tx_type, amount, balance_before, balance_after,
                           bank_before, bank_after, note, created_date
                    FROM bank_transactions
                    WHERE user_id = ? AND tx_type IN ('transfer_out', 'transfer_in')
                    ORDER BY created_date DESC
                    LIMIT ?
                """
            
            async with db.execute(query, (safe_user_id, safe_limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def transfer_between_bank_accounts(
        self,
        sender_id: int,
        recipient_id: int,
        amount: float,
        note: str = "",
        apply_commission: bool = True,
    ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Перевод денег между банковскими счетами игроков.
        Деньги берутся со счета (bank), а не с наличных (balance).
        Также применяется комиссия 2%.
        """
        await self._ensure_bank_transactions_table()
        safe_sender_id = int(sender_id or 0)
        safe_recipient_id = int(recipient_id or 0)
        safe_amount = round(float(amount or 0), 2)
        
        if safe_sender_id <= 0 or safe_recipient_id <= 0:
            return False, "Некорректный отправитель или получатель.", None
        if safe_sender_id == safe_recipient_id:
            return False, "Нельзя переводить самому себе.", None
        if safe_amount <= 0:
            return False, "Сумма должна быть больше нуля.", None
        if safe_amount > 100_000_000:
            return False, "Слишком большая сумма.", None
        
        # Комиссия: 2% от суммы
        commission_rate = 0.02 if apply_commission else 0.0
        commission = round(safe_amount * commission_rate, 2)
        total_debit = round(safe_amount + commission, 2)
        
        now = datetime.now().isoformat()
        note_clean = " ".join((note or "").strip().split())[:220]
        if not note_clean:
            note_clean = "Перевод между банковскими счетами"
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            
            async with db.execute(
                "SELECT user_id, balance, bank, nickname, full_name, username FROM users WHERE user_id = ? LIMIT 1",
                (safe_sender_id,),
            ) as cursor:
                sender = await cursor.fetchone()
            async with db.execute(
                "SELECT user_id, balance, bank, nickname, full_name, username FROM users WHERE user_id = ? LIMIT 1",
                (safe_recipient_id,),
            ) as cursor:
                recipient = await cursor.fetchone()
            
            if not sender or not recipient:
                await db.rollback()
                return False, "Отправитель или получатель не найдены.", None
            
            sender_balance_before = round(float(sender["balance"] or 0), 2)
            sender_bank_before = round(float(sender["bank"] or 0), 2)
            recipient_balance_before = round(float(recipient["balance"] or 0), 2)
            recipient_bank_before = round(float(recipient["bank"] or 0), 2)
            
            # Проверка достаточности средств на банковском счете
            if sender_bank_before < total_debit:
                await db.rollback()
                return False, f"Недостаточно средств на счете. Нужно ${total_debit:,.2f} (сумма + комиссия {commission_rate*100:.0f}%).", None
            
            sender_bank_after = round(sender_bank_before - total_debit, 2)
            recipient_bank_after = round(recipient_bank_before + safe_amount, 2)
            
            # Обновляем банковские счета
            await db.execute(
                "UPDATE users SET bank = ? WHERE user_id = ?",
                (sender_bank_after, safe_sender_id),
            )
            await db.execute(
                "UPDATE users SET bank = ? WHERE user_id = ?",
                (recipient_bank_after, safe_recipient_id),
            )
            
            # Записываем транзакции для отправителя
            commission_note = f" (комиссия ${commission:,.2f})" if commission > 0 else ""
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'bank_transfer_out', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_sender_id,
                    total_debit,
                    sender_balance_before,
                    sender_balance_before,
                    sender_bank_before,
                    sender_bank_after,
                    f"[Счет→Счет] Кому: #{safe_recipient_id}. ${safe_amount:,.2f}{commission_note}. {note_clean}",
                    now,
                ),
            )
            
            # Записываем транзакции для получателя
            await db.execute(
                """
                INSERT INTO bank_transactions
                (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                VALUES (?, 'bank_transfer_in', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_recipient_id,
                    safe_amount,
                    recipient_balance_before,
                    recipient_balance_before,
                    recipient_bank_before,
                    recipient_bank_after,
                    f"[Счет←Счет] От: #{safe_sender_id}. ${safe_amount:,.2f}. {note_clean}",
                    now,
                ),
            )
            
            # Записываем комиссию в государственный бюджет (если есть комиссия)
            if commission > 0:
                await db.execute(
                    """
                    INSERT INTO bank_transactions
                    (user_id, tx_type, amount, balance_before, balance_after, bank_before, bank_after, note, created_date)
                    VALUES (?, 'commission', ?, 0, 0, 0, 0, ?, ?)
                    """,
                    (
                        0,  # Система/Правительство
                        commission,
                        f"Банковская комиссия: перевод #{safe_sender_id}→#{safe_recipient_id}",
                        now,
                    ),
                )
                # Добавляем комиссию в государственный бюджет
                await db.execute(
                    "UPDATE organizations SET budget = COALESCE(budget, 0) + ? WHERE name = 'Правительство'",
                    (commission,),
                )
            
            await db.commit()
        
        # Логируем операцию
        await self.log_player_activity(
            user_id=safe_sender_id,
            activity_type="bank_transfer_sent",
            details=f"Перевод со счета на счет: #{safe_recipient_id}, ${safe_amount:,.2f}",
            value=total_debit,
        )
        
        return True, "Перевод со счета на счет выполнен.", {
            "amount": safe_amount,
            "commission": commission,
            "total_debit": total_debit,
            "sender_bank": sender_bank_after,
            "recipient_bank": recipient_bank_after,
            "sender_balance": sender_balance_before,
            "recipient_balance": recipient_balance_before,
        }

db = AsyncDatabase()



