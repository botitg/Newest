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

DATABASE_PATH = "state_game_async.db"

# Экономические параметры
DAILY_CITIZEN_TAX_RATE = 0.0035
DAILY_MIN_CITIZEN_TAX = 30.0
DAILY_PROPERTY_TAX_RATE = 0.00025
DAILY_BUSINESS_TAX_RATE = 0.001
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015
DAILY_LOAN_PENALTY_RATE = 0.01
BUSINESS_EQUIP_BASE_COST = 25000.0
PRIVATE_ORG_EQUIP_MULTIPLIER = 5.0

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
                    balance REAL DEFAULT 10000,
                    cash REAL DEFAULT 5000,
                    bank REAL DEFAULT 5000,
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
            else:
                # Создаем
                await db.execute(
                    '''INSERT INTO users (user_id, username, full_name, created_date, last_activity)
                       VALUES (?, ?, ?, ?, ?)''',
                    (user_id, username, full_name, now, now)
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
                          u.full_name,
                          u.username
                   FROM organization_members om
                   LEFT JOIN users u ON u.user_id = om.user_id
                   WHERE om.org_id = ?
                   ORDER BY om.rank DESC, om.join_date ASC
                   LIMIT ?''',
                (org_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def init_default_organizations(self):
        """Инициализировать стандартные организации"""
        now = datetime.now().isoformat()
        
        organizations = [
            ('Правительство', 'government', 'Управление государством', 5000000, 100),
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

    async def apply_to_organization(self, user_id: int, org_id: int, application_text: str) -> tuple[bool, str]:
        """Подать заявку в организацию"""
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существующую заявку
            async with db.execute(
                'SELECT id FROM organization_applications WHERE user_id = ? AND org_id = ? AND status = ?',
                (user_id, org_id, 'pending')
            ) as cursor:
                if await cursor.fetchone():
                    return False, "📭 Вы уже подали заявку в эту организацию!"
            
            # Проверяем членство
            async with db.execute(
                'SELECT id FROM organization_members WHERE user_id = ? AND org_id = ?',
                (user_id, org_id)
            ) as cursor:
                if await cursor.fetchone():
                    return False, "👥 Вы уже являетесь членом этой организации!"
            
            # Создаем заявку
            await db.execute(
                '''INSERT INTO organization_applications 
                   (org_id, user_id, application_text, applied_date, status)
                   VALUES (?, ?, ?, ?, ?)''',
                (org_id, user_id, application_text, now, 'pending')
            )
            
            await db.commit()
        
        return True, "✅ Заявка успешно подана на рассмотрение!"
    
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
                   WHERE o.name = ? AND e.position = ? AND e.status = 'active'
                   ORDER BY e.start_date DESC
                   LIMIT 1''',
                ('Правительство', 'President')
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def ensure_presidential_election(self, duration_hours: int = 30) -> Optional[int]:
        """Гарантировать наличие активных президентских выборов при отсутствии президента"""
        if await self.check_has_president():
            return None

        active = await self.get_active_presidential_election()
        if active:
            return int(active['id'])

        gov = await self.get_organization('Правительство')
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
                    'SELECT id, status, end_date FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены.", -1

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Эти выборы уже завершены.", -1

                try:
                    if datetime.fromisoformat(election['end_date']) <= datetime.now():
                        await db.rollback()
                        return False, "❌ Регистрация на эти выборы уже закрыта.", -1
                except Exception:
                    pass

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

                await db.commit()
                return True, f"✅ Партия '{clean_name}' успешно создана.", party_id

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
                '''SELECT pm.*, u.full_name, u.user_id FROM party_members pm
                   JOIN users u ON pm.user_id = u.user_id
                   WHERE pm.party_id = ?
                   ORDER BY CASE WHEN pm.role = 'leader' THEN 0 ELSE 1 END, u.full_name ASC''',
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
                '''SELECT u.user_id, u.full_name, u.username
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
                   ORDER BY COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) COLLATE NOCASE
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

    async def get_election_parties(self, election_id: int) -> List[Dict[str, Any]]:
        """Получить все партии на выборах"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                '''SELECT p.*, u.full_name as leader_name
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
                    'SELECT status, end_date FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены."

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Регистрация завершена: выборы неактивны."

                try:
                    if datetime.fromisoformat(election['end_date']) <= datetime.now():
                        await db.rollback()
                        return False, "❌ Регистрация завершена: срок выборов истек."
                except Exception:
                    pass

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
                          u.full_name,
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
                    'SELECT status, end_date FROM elections WHERE id = ?',
                    (election_id,)
                ) as cursor:
                    election = await cursor.fetchone()

                if not election:
                    await db.rollback()
                    return False, "❌ Выборы не найдены."

                if election['status'] != 'active':
                    await db.rollback()
                    return False, "❌ Выборы уже завершены."

                try:
                    if datetime.fromisoformat(election['end_date']) <= datetime.now():
                        await db.rollback()
                        return False, "❌ Голосование завершено."
                except Exception:
                    pass

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

    async def start_election(self, org_id: int, position: str, duration_hours: int = 30) -> int:
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
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                'SELECT id, current_leader_id FROM government_system ORDER BY id DESC LIMIT 1'
            ) as cursor:
                gov_row = await cursor.fetchone()

            if gov_row and gov_row['current_leader_id']:
                return True

            async with db.execute(
                "SELECT leader_id FROM organizations WHERE name = 'Правительство' LIMIT 1"
            ) as cursor:
                org_row = await cursor.fetchone()

            if org_row and org_row['leader_id']:
                leader_id = int(org_row['leader_id'])
                if gov_row:
                    await db.execute(
                        'UPDATE government_system SET current_leader_id = ?, last_changed = ? WHERE id = ?',
                        (leader_id, now, gov_row['id'])
                    )
                else:
                    await db.execute(
                        '''INSERT INTO government_system
                           (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                           VALUES (?, ?, ?, ?, 100, 0, 60)''',
                        ('democracy', leader_id, now, now)
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
                try:
                    end_dt = datetime.fromisoformat(row_dict['end_date'])
                except Exception:
                    continue
                if end_dt <= now_dt:
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
                        "UPDATE elections SET end_date = ?, stage = 'registration' WHERE id = ?",
                        (new_end, election_id)
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
                "(LOWER(COALESCE(u.full_name, '')) LIKE ? OR LOWER(COALESCE(u.username, '')) LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?)"
            )
            params.extend(
                [f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"]
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
                "(LOWER(COALESCE(u.full_name, '')) LIKE ? OR LOWER(COALESCE(u.username, '')) LIKE ? OR CAST(u.user_id AS TEXT) LIKE ?)"
            )
            params.extend(
                [f"%{clean_search}%", f"%{clean_search}%", f"%{clean_search}%"]
            )

        params.extend([safe_limit, safe_offset])
        query = f"""
            SELECT u.user_id,
                   u.full_name,
                   u.username,
                   u.organization,
                   u.role,
                   u.balance,
                   u.shadow_balance,
                   u.reputation
            FROM users u
            WHERE {' AND '.join(where_parts)}
            ORDER BY COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(u.user_id AS TEXT)) COLLATE NOCASE
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
        return any(token in role or token in org for token in tokens)

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

            role_lc = role_text.lower()
            if role_lc in {"leader", "лидер", "президент"}:
                await db.execute(
                    "UPDATE organizations SET leader_id = ? WHERE id = ?",
                    (target_user_id, org_id),
                )
            if role_lc in {"deputy", "заместитель", "вице-президент"}:
                await db.execute(
                    "UPDATE organizations SET deputy_id = ? WHERE id = ?",
                    (target_user_id, org_id),
                )

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
                        THEN COALESCE(NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(m.recipient_id AS TEXT))
                        ELSE COALESCE(NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(m.sender_id AS TEXT))
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(c.contact_id AS TEXT)) AS display_name,
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
                   COALESCE(NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(m.sender_id AS TEXT)) AS actor_name,
                   m.recipient_id AS target_id,
                   COALESCE(NULLIF(ru.full_name, ''), NULLIF(ru.username, ''), CAST(m.recipient_id AS TEXT)) AS target_name,
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(oc.user_id AS TEXT)) AS actor_name,
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ed.user_id AS TEXT)) AS actor_name,
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
                   COALESCE(NULLIF(ua.full_name, ''), NULLIF(ua.username, ''), CAST(co.actor_id AS TEXT)) AS actor_name,
                   COALESCE(co.target_id, 0) AS target_id,
                   COALESCE(NULLIF(ut.full_name, ''), NULLIF(ut.username, ''), '—') AS target_name,
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

        role = (user.get("role") or "").strip().lower()
        if "вице" in role and "президент" in role:
            return "vice_president"
        if "министр финансов" in role:
            return "finance_minister"
        if "министр" in role:
            return "minister"
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
        gov_org = await self.get_organization("Правительство")
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
                "SELECT id, budget FROM organizations WHERE name = ? LIMIT 1",
                ("Правительство",),
            ) as cursor:
                org_row = await cursor.fetchone()
            if not org_row:
                await db.rollback()
                return False, "Государственный бюджет недоступен.", {}

            new_budget = round(float(org_row["budget"] or 0) - safe_amount, 2)
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

    async def run_advanced_tax_cycle(self) -> Dict[str, Any]:
        """Усиленный налоговый цикл: прогрессивная шкала, проценты по долгу и логирование."""
        now_dt = datetime.now()
        now_iso = now_dt.isoformat()
        cycle_date = now_dt.date().isoformat()

        processed = 0
        debtors = 0
        total_collected = 0.0
        total_new_debt = 0.0

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT user_id, balance, tax_debt, reputation, total_tax_paid, shadow_balance
                FROM users
                """
            ) as cursor:
                users = await cursor.fetchall()

            for user in users:
                processed += 1
                user_id = int(user["user_id"])
                balance = float(user["balance"] or 0.0)
                debt = float(user["tax_debt"] or 0.0)
                shadow_balance = float(user["shadow_balance"] or 0.0)
                reputation = float(user["reputation"] or 50.0)
                total_paid = float(user["total_tax_paid"] or 0.0)

                taxable_base = max(0.0, balance + shadow_balance * 0.35)
                if taxable_base < 15_000:
                    rate = 0.010
                elif taxable_base < 70_000:
                    rate = 0.025
                elif taxable_base < 250_000:
                    rate = 0.045
                elif taxable_base < 750_000:
                    rate = 0.065
                else:
                    rate = 0.090

                citizen_tax = round(max(25.0, taxable_base * rate), 2)
                debt_interest = round(debt * 0.03, 2)
                scheduled_debt_payment = round(min(debt * 0.12, max(0.0, balance * 0.25)), 2)
                total_due = round(citizen_tax + debt_interest + scheduled_debt_payment, 2)

                paid_now = round(min(balance, total_due), 2)
                new_balance = round(balance - paid_now, 2)
                new_debt = round(max(0.0, debt + citizen_tax + debt_interest - paid_now), 2)
                total_paid = round(total_paid + paid_now, 2)
                total_collected += paid_now

                if new_debt > debt:
                    debtors += 1
                    reputation = max(0.0, reputation - min(4.0, (new_debt - debt) / 5000))
                elif debt > 0 and paid_now >= total_due:
                    reputation = min(100.0, reputation + 0.2)

                total_new_debt += max(0.0, new_debt - debt)

                if new_debt >= 200_000:
                    ban_until = (now_dt + timedelta(hours=12)).isoformat()
                    await db.execute(
                        """
                        UPDATE users
                        SET balance = ?, tax_debt = ?, total_tax_paid = ?, reputation = ?, action_banned_until = ?
                        WHERE user_id = ?
                        """,
                        (new_balance, new_debt, total_paid, round(reputation, 2), ban_until, user_id),
                    )
                else:
                    await db.execute(
                        """
                        UPDATE users
                        SET balance = ?, tax_debt = ?, total_tax_paid = ?, reputation = ?
                        WHERE user_id = ?
                        """,
                        (new_balance, new_debt, total_paid, round(reputation, 2), user_id),
                    )

                await db.execute(
                    """
                    INSERT INTO tax_logs
                    (user_id, cycle_date, citizen_tax, property_tax, business_tax, org_tax, paid_total, debt_total, created_at)
                    VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)
                    """,
                    (user_id, cycle_date, citizen_tax, paid_now, new_debt, now_iso),
                )

            async with db.execute(
                "SELECT id, budget FROM organizations WHERE name = 'Правительство' LIMIT 1"
            ) as cursor:
                gov = await cursor.fetchone()
            if gov:
                new_budget = round(float(gov["budget"] or 0) + total_collected, 2)
                await db.execute(
                    "UPDATE organizations SET budget = ? WHERE id = ?",
                    (new_budget, int(gov["id"])),
                )

            await db.commit()

        return {
            "processed_users": processed,
            "debtors": debtors,
            "total_collected": round(total_collected, 2),
            "total_new_debt": round(total_new_debt, 2),
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

    async def get_latest_media_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 20), 100))
        query = """
            SELECT mn.*,
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(mn.source_user_id AS TEXT)) AS source_name
            FROM media_news mn
            LEFT JOIN users u ON u.user_id = mn.source_user_id
            ORDER BY mn.created_date DESC
            LIMIT ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (safe_limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def generate_hourly_news(self) -> Optional[Dict[str, Any]]:
        now_dt = datetime.now()
        since = (now_dt - timedelta(hours=2)).isoformat()
        query = """
            SELECT pal.*,
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(pal.user_id AS TEXT)) AS actor_name
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(po.owner_id AS TEXT)) AS owner_name,
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

    async def list_all_businesses(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        query = """
            SELECT b.*,
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(b.owner_id AS TEXT)) AS owner_name,
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(po.leader_id AS TEXT)) AS leader_name,
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(btr.owner_id AS TEXT)) AS owner_name
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

    async def list_education_programs(self, active_only: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        where = "WHERE ep.active = 1" if active_only else ""
        query = f"""
            SELECT ep.*,
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(ep.teacher_id AS TEXT)) AS teacher_name
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
        today = now_dt.date().isoformat()
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
            if last_study.startswith(today):
                await db.rollback()
                return False, "Вы уже учились сегодня. Возвращайтесь завтра.", None

            progress_days = int(enrollment["progress_days"] or 0)
            duration_days = max(1, int(enrollment["duration_days"] or 1))
            increment = 2 if safe_mode == "practice" and random.random() < 0.45 else 1
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(c.owner_id AS TEXT)) AS owner_name
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

        cooldown_minutes = 45 if safe_type == "legal" else 60
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(g.leader_id AS TEXT)) AS leader_name,
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
                   COALESCE(NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(pa.suspect_id AS TEXT)) AS suspect_name,
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
                   COALESCE(NULLIF(su.full_name, ''), NULLIF(su.username, ''), CAST(pa.suspect_id AS TEXT)) AS suspect_name
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
        is_judge = ("суд" in role_lc) or ("judge" in role_lc) or ("суд" in org_lc) or ("court" in org_lc)

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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(cc.defendant_id AS TEXT)) AS defendant_name,
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

            return True, "Операция выполнена.", {
                "operation": op,
                "risk": 35,
                "fine_amount": float(fine),
                **(payload or {}),
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(oa.user_id AS TEXT)) AS applicant_name,
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

            if int(org["leader_id"] or 0) != int(reviewer_id) and int(org["deputy_id"] or 0) != int(reviewer_id):
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(rs.supporter_id AS TEXT)) AS supporter_name,
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
                   COALESCE(NULLIF(u.full_name, ''), NULLIF(u.username, ''), CAST(r.organizer_id AS TEXT)) AS organizer_name
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

db = AsyncDatabase()



