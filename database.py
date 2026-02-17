"""
Асинхронная база данных на aiosqlite для нового Telegram-бота (aiogram 3.x)
Все операции async/await, никаких блокировок
"""

import aiosqlite
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import sqlite3

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
        return ("фбр" in role) or ("фбр" in org)

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

db = AsyncDatabase()
