import sqlite3
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

DATABASE = "state_game.db"

# Экономические параметры (дневные)
DAILY_CITIZEN_TAX_RATE = 0.0035
DAILY_MIN_CITIZEN_TAX = 30.0
DAILY_PROPERTY_TAX_RATE = 0.00025
DAILY_BUSINESS_TAX_RATE = 0.001
DAILY_PRIVATE_ORG_TAX_RATE = 0.0015
DAILY_LOAN_PENALTY_RATE = 0.01
BUSINESS_EQUIP_BASE_COST = 35000.0
PRIVATE_ORG_EQUIP_MULTIPLIER = 5.0
EDUCATION_DAILY_REPUTATION_GAIN = 0.05
EDUCATION_COMPLETION_REPUTATION_GAIN = 1.5

def get_conn():
    conn = sqlite3.connect(DATABASE, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=1200")
    return conn


def back_markup(callback_data: str = "back_to_main", text: str = "🔙 В меню") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=callback_data)]])


def player_picker_markup(players, callback_prefix, back_callback, back_text="🔙 Назад"):
    keyboard = []
    for player in players:
        label = f"👤 {player['full_name'][:24]}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{callback_prefix}{player['user_id']}")])
    keyboard.append([InlineKeyboardButton(back_text, callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

class OrganizationSystem:
    def __init__(self):
        self.init_database()
        self.bot = None
    
    def init_database(self):
        """Инициализация таблиц для организаций"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем и создаем таблицу users если нет
        c.execute('''CREATE TABLE IF NOT EXISTS users (
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
            reputation INTEGER DEFAULT 50,
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
            created_date TEXT
        )''')

        # Добавляем колонки для состояния без "здоровья/энергии"
        self._ensure_column('users', 'life_state', "TEXT DEFAULT 'alive'", cursor=c)
        self._ensure_column('users', 'injury_severity', "TEXT", cursor=c)
        self._ensure_column('users', 'injured_until', "TEXT", cursor=c)
        self._ensure_column('users', 'tutorial_step', "INTEGER DEFAULT 0", cursor=c)
        self._ensure_column('users', 'tutorial_completed', "INTEGER DEFAULT 0", cursor=c)
        self._ensure_column('users', 'first_login', "TEXT", cursor=c)
        self._ensure_column('users', 'last_daily_bonus', "TEXT", cursor=c)
        self._ensure_column('users', 'last_economy_update', "TEXT", cursor=c)
        self._ensure_column('users', 'total_tax_paid', "REAL DEFAULT 0", cursor=c)
        self._ensure_column('users', 'tax_debt', "REAL DEFAULT 0", cursor=c)
        self._ensure_column('users', 'citizen_job', "TEXT", cursor=c)
        self._ensure_column('users', 'citizen_salary', "REAL DEFAULT 0", cursor=c)
        self._ensure_column('users', 'last_job_shift', "TEXT", cursor=c)
        self._ensure_column('users', 'loan_defaults', "INTEGER DEFAULT 0", cursor=c)
        
        # Организации
        c.execute('''CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            type TEXT,
            leader_id INTEGER,
            deputy_id INTEGER,
            budget REAL DEFAULT 1000000,
            members INTEGER DEFAULT 0,
            reputation INTEGER DEFAULT 50,
            created_date TEXT,
            last_election TEXT,
            policy TEXT DEFAULT 'neutral',
            description TEXT,
            requirements TEXT,
            income_tax REAL DEFAULT 0.1,
            property_tax REAL DEFAULT 0.05,
            business_tax REAL DEFAULT 0.15
        )''')
        
        # Члены организаций
        c.execute('''CREATE TABLE IF NOT EXISTS organization_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            user_id INTEGER,
            role TEXT,
            salary REAL DEFAULT 0,
            permissions TEXT,
            join_date TEXT,
            last_promotion TEXT,
            performance INTEGER DEFAULT 100,
            department TEXT DEFAULT 'general',
            rank INTEGER DEFAULT 1,
            experience INTEGER DEFAULT 0,
            tasks_completed INTEGER DEFAULT 0
        )''')
        
        # Заявки в организации
        c.execute('''CREATE TABLE IF NOT EXISTS organization_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            user_id INTEGER,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT,
            notes TEXT
        )''')
        
        # Задания организации
        c.execute('''CREATE TABLE IF NOT EXISTS org_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            creator_id INTEGER,
            title TEXT,
            description TEXT,
            reward REAL DEFAULT 0,
            deadline TEXT,
            status TEXT DEFAULT 'active',
            assigned_to INTEGER,
            created_date TEXT,
            completed_date TEXT
        )''')
        
        # Выборы в организациях
        c.execute('''CREATE TABLE IF NOT EXISTS elections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            position TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'active',
            winner_id INTEGER,
            total_voters INTEGER DEFAULT 0
        )''')
        
        # Кандидаты на выборах
        c.execute('''CREATE TABLE IF NOT EXISTS election_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id INTEGER,
            candidate_id INTEGER,
            votes INTEGER DEFAULT 0,
            program TEXT,
            promises TEXT
        )''')
        
        # Голоса на выборах
        c.execute('''CREATE TABLE IF NOT EXISTS election_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id INTEGER,
            voter_id INTEGER,
            candidate_id INTEGER,
            vote_date TEXT,
            UNIQUE(election_id, voter_id)
        )''')
        
        # Законы (Правительство)
        c.execute('''CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            law_number TEXT UNIQUE,
            title TEXT,
            description TEXT,
            proposed_by INTEGER,
            proposed_date TEXT,
            votes_for INTEGER DEFAULT 0,
            votes_against INTEGER DEFAULT 0,
            status TEXT DEFAULT 'proposed',
            voting_end TEXT,
            passed_date TEXT,
            category TEXT
        )''')
        
        # Голоса за законы
        c.execute('''CREATE TABLE IF NOT EXISTS law_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            law_id INTEGER,
            voter_id INTEGER,
            vote_type TEXT,
            vote_date TEXT,
            UNIQUE(law_id, voter_id)
        )''')
        
        # Судебные дела
        c.execute('''CREATE TABLE IF NOT EXISTS court_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number TEXT UNIQUE,
            plaintiff_id INTEGER,
            defendant_id INTEGER,
            judge_id INTEGER,
            prosecutor_id INTEGER,
            lawyer_id INTEGER,
            description TEXT,
            evidence TEXT,
            status TEXT DEFAULT 'open',
            verdict TEXT,
            sentence TEXT,
            fine REAL DEFAULT 0,
            jail_time INTEGER DEFAULT 0,
            opened_date TEXT,
            closed_date TEXT,
            court_fees REAL DEFAULT 0
        )''')
        
        # Аресты (Полиция)
        c.execute('''CREATE TABLE IF NOT EXISTS arrests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            officer_id INTEGER,
            suspect_id INTEGER,
            reason TEXT,
            evidence TEXT,
            arrest_date TEXT,
            release_date TEXT,
            status TEXT DEFAULT 'active',
            fine REAL DEFAULT 0,
            location TEXT,
            severity TEXT DEFAULT 'medium'
        )''')
        
        # Кредиты (Банк)
        c.execute('''CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id INTEGER,
            bank_officer_id INTEGER,
            amount REAL,
            interest_rate REAL,
            term_months INTEGER,
            monthly_payment REAL,
            purpose TEXT,
            status TEXT DEFAULT 'pending',
            application_date TEXT,
            approval_date TEXT,
            due_date TEXT,
            remaining_balance REAL,
            collateral TEXT,
            credit_score INTEGER DEFAULT 500
        )''')
        self._ensure_column('loans', 'daily_payment', "REAL DEFAULT 0", cursor=c)
        self._ensure_column('loans', 'last_payment_date', "TEXT", cursor=c)
        
        # Лечение (Больница)
        c.execute('''CREATE TABLE IF NOT EXISTS treatments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            doctor_id INTEGER,
            diagnosis TEXT,
            treatment TEXT,
            cost REAL,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'in_progress',
            result TEXT,
            hospital_days INTEGER DEFAULT 1,
            medication TEXT
        )''')
        
        # Исследования (Университет)
        c.execute('''CREATE TABLE IF NOT EXISTS researches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            researcher_id INTEGER,
            title TEXT,
            description TEXT,
            field TEXT,
            budget REAL,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'active',
            results TEXT,
            publication_date TEXT
        )''')
        
        # Расследования (ФБР)
        c.execute('''CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            target_id INTEGER,
            case_type TEXT,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'open',
            evidence TEXT,
            findings TEXT,
            clearance_level TEXT DEFAULT 'confidential'
        )''')
        
        # Сообщения и уведомления
        c.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message_type TEXT,
            subject TEXT,
            content TEXT,
            date TEXT,
            priority INTEGER DEFAULT 1,
            read_status INTEGER DEFAULT 0
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS tax_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            cycle_date TEXT,
            citizen_tax REAL DEFAULT 0,
            property_tax REAL DEFAULT 0,
            business_tax REAL DEFAULT 0,
            org_tax REAL DEFAULT 0,
            paid_total REAL DEFAULT 0,
            debt_total REAL DEFAULT 0,
            created_at TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS reputation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            delta REAL,
            reason TEXT,
            created_at TEXT
        )''')

        # Задания игроков (обучение и квесты)
        c.execute('''CREATE TABLE IF NOT EXISTS player_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_code TEXT,
            title TEXT,
            description TEXT,
            status TEXT DEFAULT 'active',
            progress INTEGER DEFAULT 0,
            goal INTEGER DEFAULT 1,
            reward REAL DEFAULT 0,
            assigned_date TEXT,
            completed_date TEXT
        )''')

        # Недвижимость
        c.execute('''CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price REAL,
            rent REAL,
            location TEXT,
            status TEXT DEFAULT 'available'
        )''')
        self._ensure_column('properties', 'category', "TEXT DEFAULT 'residential'", cursor=c)
        self._ensure_column('properties', 'maintenance_daily', "REAL DEFAULT 120", cursor=c)
        self._ensure_column('properties', 'condition', "INTEGER DEFAULT 100", cursor=c)

        c.execute('''CREATE TABLE IF NOT EXISTS property_ownership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER,
            owner_id INTEGER,
            acquired_date TEXT,
            last_rent_claimed TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS property_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER UNIQUE,
            facility_type TEXT,
            facility_id INTEGER,
            owner_id INTEGER,
            setup_cost REAL DEFAULT 0,
            setup_level INTEGER DEFAULT 1,
            created_date TEXT
        )''')

        # Контрактная биржа
        c.execute('''CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            title TEXT,
            description TEXT,
            reward REAL,
            status TEXT DEFAULT 'open',
            accepted_by INTEGER,
            created_date TEXT,
            completed_date TEXT
        )''')
        self._ensure_column('contracts', 'escrow_reserved', "REAL DEFAULT 0", cursor=c)
        self._ensure_column('contracts', 'category', "TEXT DEFAULT 'general'", cursor=c)
        self._ensure_column('contracts', 'priority', "TEXT DEFAULT 'normal'", cursor=c)

        c.execute('''CREATE TABLE IF NOT EXISTS protests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            title TEXT,
            description TEXT,
            location TEXT,
            status TEXT DEFAULT 'active',
            support_count INTEGER DEFAULT 0,
            against_count INTEGER DEFAULT 0,
            created_date TEXT,
            end_date TEXT,
            result_summary TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS protest_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protest_id INTEGER,
            user_id INTEGER,
            stance TEXT,
            join_date TEXT,
            UNIQUE(protest_id, user_id)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            job_code TEXT,
            job_title TEXT,
            expected_salary REAL,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT,
            review_note TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS education_programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            duration_days INTEGER DEFAULT 14,
            tuition_fee REAL DEFAULT 0,
            min_education INTEGER DEFAULT 1,
            min_reputation REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_date TEXT,
            creator_id INTEGER,
            teacher_id INTEGER
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS education_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            program_id INTEGER,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT,
            review_note TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS education_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            program_id INTEGER,
            teacher_id INTEGER,
            status TEXT DEFAULT 'active',
            start_date TEXT,
            last_study_date TEXT,
            progress_days INTEGER DEFAULT 0,
            completed_date TEXT
        )''')

        # Инициализация недвижимости
        c.execute('SELECT COUNT(*) FROM properties')
        if c.fetchone()[0] == 0:
            properties = [
                ('Квартира в центре', 250000, 2500, 'Центр', 'residential', 80),
                ('Дом в пригороде', 450000, 4200, 'Пригород', 'residential', 120),
                ('Офис класса B', 600000, 6000, 'Деловой район', 'commercial', 180),
                ('Склад', 300000, 3200, 'Промзона', 'commercial', 150),
                ('Магазин у метро', 550000, 5200, 'Торговый квартал', 'commercial', 170),
            ]
            for p in properties:
                c.execute('''INSERT INTO properties (name, price, rent, location, category, maintenance_daily)
                             VALUES (?, ?, ?, ?, ?, ?)''', p)
        else:
            c.execute("""UPDATE properties
                         SET category = CASE
                             WHEN name LIKE '%Офис%' OR name LIKE '%Склад%' OR name LIKE '%Магазин%'
                             THEN 'commercial'
                             ELSE COALESCE(category, 'residential')
                         END
                         WHERE category IS NULL OR category = ''""")

        # Бизнесы
        c.execute('SELECT COUNT(*) FROM education_programs')
        if c.fetchone()[0] == 0:
            programs = [
                ('Базовая школа', 'Обязательная школьная программа с базовой подготовкой.', 8, 1800, 1, 10),
                ('Технический колледж', 'Практическая программа для рабочих специальностей.', 12, 3200, 2, 40),
                ('Экономический факультет', 'Финансы, управление и основы экономики.', 16, 5200, 3, 55),
                ('Юридический факультет', 'Право, судебная практика и правоприменение.', 18, 6200, 4, 65),
                ('Медицинская академия', 'Профессиональная медицинская подготовка.', 20, 7400, 4, 70),
            ]
            for p in programs:
                c.execute('''INSERT INTO education_programs
                             (name, description, duration_days, tuition_fee, min_education, min_reputation, active, created_date)
                             VALUES (?, ?, ?, ?, ?, ?, 1, ?)''',
                          (p[0], p[1], p[2], p[3], p[4], p[5], datetime.now().isoformat()))
        # Балансируем существующие записи при обновлении проекта.
        c.execute('''UPDATE education_programs
                     SET duration_days = MAX(duration_days, 8),
                         tuition_fee = MAX(tuition_fee, 1800),
                         min_education = MAX(min_education, 1),
                         min_reputation = MAX(min_reputation, 10)
                     WHERE name = 'Базовая школа' ''')
        c.execute('''UPDATE education_programs
                     SET duration_days = MAX(duration_days, 12),
                         tuition_fee = MAX(tuition_fee, 3200),
                         min_education = MAX(min_education, 2),
                         min_reputation = MAX(min_reputation, 40)
                     WHERE name = 'Технический колледж' ''')
        c.execute('''UPDATE education_programs
                     SET duration_days = MAX(duration_days, 16),
                         tuition_fee = MAX(tuition_fee, 5200),
                         min_education = MAX(min_education, 3),
                         min_reputation = MAX(min_reputation, 55)
                     WHERE name = 'Экономический факультет' ''')
        c.execute('''UPDATE education_programs
                     SET duration_days = MAX(duration_days, 18),
                         tuition_fee = MAX(tuition_fee, 6200),
                         min_education = MAX(min_education, 4),
                         min_reputation = MAX(min_reputation, 65)
                     WHERE name = 'Юридический факультет' ''')
        c.execute('''UPDATE education_programs
                     SET duration_days = MAX(duration_days, 20),
                         tuition_fee = MAX(tuition_fee, 7400),
                         min_education = MAX(min_education, 4),
                         min_reputation = MAX(min_reputation, 70)
                     WHERE name = 'Медицинская академия' ''')

        c.execute('''CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            owner_id INTEGER,
            type TEXT,
            budget REAL DEFAULT 100000,
            description TEXT,
            status TEXT DEFAULT 'active',
            location TEXT,
            created_date TEXT
        )''')
        self._ensure_column('businesses', 'property_id', "INTEGER", cursor=c)
        self._ensure_column('businesses', 'equipment_level', "INTEGER DEFAULT 1", cursor=c)

        c.execute('''CREATE TABLE IF NOT EXISTS business_employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            user_id INTEGER,
            role TEXT,
            salary REAL DEFAULT 0,
            join_date TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS business_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            user_id INTEGER,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT
        )''')

        # Доп. колонки для бизнесов (экономика)
        self._ensure_column('businesses', 'income_daily', "REAL DEFAULT 800", cursor=c)
        self._ensure_column('businesses', 'expense_daily', "REAL DEFAULT 300", cursor=c)
        self._ensure_column('businesses', 'last_income_date', "TEXT", cursor=c)

        c.execute('''CREATE TABLE IF NOT EXISTS business_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            user_id INTEGER,
            amount REAL,
            tx_type TEXT,
            description TEXT,
            tx_date TEXT
        )''')

        # Частные организации (НКО/партии/компании без гос. статуса)
        c.execute('''CREATE TABLE IF NOT EXISTS private_orgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            leader_id INTEGER,
            budget REAL DEFAULT 50000,
            description TEXT,
            policy TEXT,
            status TEXT DEFAULT 'active',
            created_date TEXT
        )''')
        self._ensure_column('private_orgs', 'property_id', "INTEGER", cursor=c)
        self._ensure_column('private_orgs', 'equipment_level', "INTEGER DEFAULT 1", cursor=c)

        c.execute('''CREATE TABLE IF NOT EXISTS private_org_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            user_id INTEGER,
            role TEXT,
            join_date TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS private_org_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            user_id INTEGER,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT
        )''')

        # Банды
        c.execute('''CREATE TABLE IF NOT EXISTS gangs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            leader_id INTEGER,
            territory TEXT,
            reputation INTEGER DEFAULT 50,
            status TEXT DEFAULT 'active',
            created_date TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS gang_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gang_id INTEGER,
            user_id INTEGER,
            role TEXT,
            join_date TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS gang_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gang_id INTEGER,
            user_id INTEGER,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS gang_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gang_id INTEGER,
            actor_id INTEGER,
            target_id INTEGER,
            action_type TEXT,
            severity TEXT,
            result TEXT,
            action_date TEXT
        )''')

        # Дополнительные колонки для учителей
        self._ensure_column('education_enrollments', 'study_choice', "TEXT DEFAULT 'theory'", cursor=c)
        
        # Заявки на должность учителя
        c.execute('''CREATE TABLE IF NOT EXISTS teacher_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            application_text TEXT,
            status TEXT DEFAULT 'pending',
            applied_date TEXT,
            reviewed_by INTEGER,
            reviewed_date TEXT,
            review_note TEXT
        )''')
        
        # Доклады и отчеты в организациях
        c.execute('''CREATE TABLE IF NOT EXISTS organization_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            author_id INTEGER,
            title TEXT,
            content TEXT,
            report_type TEXT DEFAULT 'statement',
            date TEXT,
            status TEXT DEFAULT 'published'
        )''')
        
        self._ensure_column('organization_reports', 'title', "TEXT", cursor=c)
        self._ensure_column('organization_reports', 'report_type', "TEXT DEFAULT 'statement'", cursor=c)
        self._ensure_column('organization_reports', 'status', "TEXT DEFAULT 'published'", cursor=c)
        
        # Инициализация базовых организаций
        orgs = [
            ('Правительство', 'government', None, None, 5000000, 0, 100, 
             datetime.now().isoformat(), None, 'democratic',
             'Высший орган управления государством. Контролирует законы, бюджет и международные отношения.',
             'Образование 5+, Репутация 80+, Стаж 3+ месяца', 0.13, 0.05, 0.2),
            
            ('Полиция', 'police', None, None, 2000000, 0, 80, 
             datetime.now().isoformat(), None, 'lawful',
             'Орган правопорядка. Обеспечивает безопасность граждан и расследует преступления.',
             'Образование 3+, Репутация 60+, Здоровье 70+', 0.1, 0.03, 0.1),
            
            ('Больница', 'hospital', None, None, 1500000, 0, 90, 
             datetime.now().isoformat(), None, 'neutral',
             'Медицинское учреждение. Оказывает помощь больным и проводит лечение.',
             'Образование 4+ (медицинское), Репутация 70+, Лицензия врача', 0.12, 0.04, 0.12),
            
            ('Суд', 'court', None, None, 1000000, 0, 95, 
             datetime.now().isoformat(), None, 'lawful',
             'Судебная система. Рассматривает дела и выносит приговоры.',
             'Образование 5+ (юридическое), Репутация 90+, Стаж 6+ месяцев', 0.15, 0.05, 0.15),
            
            ('Банк', 'bank', None, None, 10000000, 0, 85, 
             datetime.now().isoformat(), None, 'capitalist',
             'Финансовое учреждение. Управляет деньгами, выдает кредиты и обрабатывает платежи.',
             'Образование 4+ (экономическое), Репутация 75+, Финансовая грамотность', 0.11, 0.04, 0.18),
            
            ('Университет', 'education', None, None, 800000, 0, 75, 
             datetime.now().isoformat(), None, 'progressive',
             'Образовательное учреждение. Проводит обучение и научные исследования.',
             'Образование 5+, Репутация 85+, Научные публикации', 0.1, 0.02, 0.08),
            
            ('ФБР', 'fbi', None, None, 3000000, 0, 70, 
             datetime.now().isoformat(), None, 'secretive',
             'Федеральное бюро расследований. Расследует серьезные преступления и обеспечивает безопасность.',
             'Образование 4+, Репутация 80+, Допуск к секретам', 0.14, 0.06, 0.2),

            ('Налоговая служба', 'tax', None, None, 1800000, 0, 88,
             datetime.now().isoformat(), None, 'strict',
             'Орган контроля налогов. Следит за сборами, долгами и прозрачностью платежей.',
             'Образование 4+ (экономика/право), Репутация 70+, Без долгов по налогам', 0.12, 0.05, 0.17),
        ]
        
        for org in orgs:
            c.execute('''INSERT OR IGNORE INTO organizations 
                        (name, type, leader_id, deputy_id, budget, members, reputation, 
                         created_date, last_election, policy, description, requirements,
                         income_tax, property_tax, business_tax)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', org)
        
        # Типы правления
        c.execute('''CREATE TABLE IF NOT EXISTS government_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            elected_position TEXT DEFAULT 'President',
            election_frequency_days INTEGER DEFAULT 30,
            max_powers INTEGER DEFAULT 5,
            created_at TEXT
        )''')
        
        # Система правления государства
        c.execute('''CREATE TABLE IF NOT EXISTS government_system (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_type TEXT DEFAULT 'democracy',
            current_leader_id INTEGER,
            established_date TEXT,
            last_changed TEXT,
            stability INTEGER DEFAULT 100,
            corruption INTEGER DEFAULT 0,
            public_satisfaction INTEGER DEFAULT 60
        )''')
        
        # Правила и законы президента
        c.execute('''CREATE TABLE IF NOT EXISTS government_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_number TEXT UNIQUE,
            rule_text TEXT,
            created_by INTEGER,
            created_date TEXT,
            status TEXT DEFAULT 'active',
            violation_penalty REAL DEFAULT 1000,
            violations_count INTEGER DEFAULT 0
        )''')
        
        # Нарушения правил
        c.execute('''CREATE TABLE IF NOT EXISTS rule_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            violator_id INTEGER,
            officer_id INTEGER,
            violation_date TEXT,
            description TEXT,
            fine REAL DEFAULT 0,
            status TEXT DEFAULT 'active'
        )''')
        
        # Письма и сообщения
        c.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            recipient_id INTEGER,
            subject TEXT,
            content TEXT,
            created_date TEXT,
            read_date TEXT,
            message_type TEXT DEFAULT 'private',
            deleted_by_sender INTEGER DEFAULT 0,
            deleted_by_recipient INTEGER DEFAULT 0
        )''')
        
        # Перехвачены ФБР письма
        c.execute('''CREATE TABLE IF NOT EXISTS intercepted_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_message_id INTEGER,
            intercepted_by_id INTEGER,
            intercepted_date TEXT,
            action TEXT DEFAULT 'logged'
        )''')
        
        # Чаты организаций
        c.execute('''CREATE TABLE IF NOT EXISTS org_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            sender_id INTEGER,
            content TEXT,
            created_date TEXT,
            message_type TEXT DEFAULT 'general'
        )''')
        
        # Революции и восстания
        c.execute('''CREATE TABLE IF NOT EXISTS revolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_date TEXT,
            ended_date TEXT,
            organizer_id INTEGER,
            target_leader_id INTEGER,
            new_government_type TEXT,
            supporters_count INTEGER DEFAULT 0,
            supporters_needed INTEGER DEFAULT 100,
            status TEXT DEFAULT 'active',
            reason TEXT,
            result TEXT DEFAULT 'pending'
        )''')
        
        # Участники революции
        c.execute('''CREATE TABLE IF NOT EXISTS revolution_supporters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revolution_id INTEGER,
            supporter_id INTEGER,
            joined_date TEXT,
            UNIQUE(revolution_id, supporter_id)
        )''')
        
        # Инициализируем систему правления (если не существует)
        c.execute('SELECT COUNT(*) FROM government_system')
        if c.fetchone()[0] == 0:
            c.execute('''INSERT INTO government_system
                        (current_type, current_leader_id, established_date, last_changed, stability, corruption, public_satisfaction)
                        VALUES (?, NULL, ?, ?, 100, 0, 60)''',
                     ('democracy', datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        """Получение пользователя из базы данных"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        
        if user:
            columns = [description[0] for description in c.description]
            return dict(zip(columns, user))
        return None

    def get_all_users(self):
        """Получение всех пользователей"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT user_id, full_name FROM users ORDER BY full_name')
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'full_name': row[1] or 'Игрок'
            })
        return result

    def list_recent_players(self, exclude_user_id=None, limit=20):
        conn = get_conn()
        c = conn.cursor()
        if exclude_user_id:
            c.execute('''SELECT user_id, full_name, reputation, balance
                         FROM users
                         WHERE user_id != ?
                         ORDER BY COALESCE(last_activity, created_date) DESC
                         LIMIT ?''', (exclude_user_id, limit))
        else:
            c.execute('''SELECT user_id, full_name, reputation, balance
                         FROM users
                         ORDER BY COALESCE(last_activity, created_date) DESC
                         LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'user_id': row[0],
                'full_name': row[1] or 'Игрок',
                'reputation': float(row[2] or 50),
                'balance': float(row[3] or 0),
            })
        return result

    def ensure_user(self, tg_user):
        """Создание или обновление профиля пользователя"""
        if not tg_user:
            return None
        user_id = tg_user.id
        full_name = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip()
        username = tg_user.username or None
        now = datetime.now().isoformat()

        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        existing = c.fetchone()
        
        # Проверяем нужно ли запустить инициальные выборы
        is_first_user = not existing
        
        if existing:
            c.execute('''UPDATE users
                         SET username = ?, full_name = ?, last_activity = ?
                         WHERE user_id = ?''',
                      (username, full_name, now, user_id))
        else:
            c.execute('''INSERT INTO users
                         (user_id, username, full_name, created_date, last_activity)
                         VALUES (?, ?, ?, ?, ?)''',
                      (user_id, username, full_name, now, now))
            # Назначаем стартовые задания новому игроку
            conn.commit()
            conn.close()
            
            # Если это первый пользователь - запускаем выборы президента
            if is_first_user:
                self.check_and_start_initial_election()
            
            self.assign_starter_tasks(user_id)
            self.update_user(user_id, first_login=now, tutorial_step=0, tutorial_completed=0)
            return self.get_user(user_id)
        conn.commit()
        conn.close()
        
        # На всякий случай назначаем задачи, если их нет
        self.assign_starter_tasks(user_id)
        user = self.get_user(user_id)
        # Если у старых пользователей NULL в обучении — исправим
        if user and user.get('tutorial_completed') is None:
            self.update_user(user_id, tutorial_completed=0)
        if user and user.get('tutorial_step') is None:
            self.update_user(user_id, tutorial_step=0)
        return self.get_user(user_id)
    
    def update_user(self, user_id, **kwargs):
        """Обновление данных пользователя"""
        if not kwargs:
            return
        
        conn = get_conn()
        c = conn.cursor()
        
        for key, value in kwargs.items():
            # Проверяем существует ли колонка
            c.execute(f"PRAGMA table_info(users)")
            columns = [col[1] for col in c.fetchall()]
            
            if key in columns:
                c.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
        
        conn.commit()
        conn.close()
    
    def get_organization(self, org_name):
        """Получение организации по имени"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM organizations WHERE name = ?', (org_name,))
        org = c.fetchone()
        conn.close()
        
        if org:
            return {
                'id': org[0],
                'name': org[1],
                'type': org[2],
                'leader_id': org[3],
                'deputy_id': org[4],
                'budget': org[5],
                'members': org[6],
                'reputation': org[7],
                'created_date': org[8],
                'last_election': org[9],
                'policy': org[10],
                'description': org[11],
                'requirements': org[12],
                'income_tax': org[13],
                'property_tax': org[14],
                'business_tax': org[15]
            }
        return None
    
    def get_organization_by_id(self, org_id):
        """Получение организации по ID"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM organizations WHERE id = ?', (org_id,))
        org = c.fetchone()
        conn.close()
        
        if org:
            return {
                'id': org[0],
                'name': org[1],
                'type': org[2],
                'leader_id': org[3],
                'deputy_id': org[4],
                'budget': org[5],
                'members': org[6],
                'reputation': org[7],
                'created_date': org[8],
                'last_election': org[9],
                'policy': org[10],
                'description': org[11],
                'requirements': org[12],
                'income_tax': org[13],
                'property_tax': org[14],
                'business_tax': org[15]
            }
        return None

    def list_organizations(self):
        """Получение списка всех организаций"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT id, name, type FROM organizations ORDER BY name ASC')
        orgs = c.fetchall()
        conn.close()
        
        result = []
        for org in orgs:
            result.append({
                'id': org[0],
                'name': org[1],
                'type': org[2],
            })
        return result

    
    def get_user_organization(self, user_id):
        """Получение организации пользователя"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT o.*, om.role, om.salary, om.department, om.rank 
                     FROM organization_members om
                     JOIN organizations o ON om.org_id = o.id
                     WHERE om.user_id = ?''', (user_id,))
        org = c.fetchone()
        conn.close()
        
        if org:
            return {
                'id': org[0],
                'name': org[1],
                'type': org[2],
                'leader_id': org[3],
                'deputy_id': org[4],
                'budget': org[5],
                'members': org[6],
                'reputation': org[7],
                'role': org[16],
                'salary': org[17],
                'department': org[18],
                'rank': org[19]
            }
        return None
    
    def get_organization_members(self, org_id, limit=20):
        """Получение членов организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT om.*, u.full_name, u.username, u.level, u.reputation, u.experience 
                     FROM organization_members om
                     LEFT JOIN users u ON om.user_id = u.user_id
                     WHERE om.org_id = ?
                     ORDER BY 
                         CASE om.role
                             WHEN 'Президент' THEN 1
                             WHEN 'Лидер' THEN 2
                             WHEN 'Директор' THEN 3
                             WHEN 'Глава' THEN 4
                             WHEN 'Шеф' THEN 5
                             WHEN 'Руководитель' THEN 6
                             WHEN 'Заместитель' THEN 7
                             ELSE 8
                         END,
                         om.rank DESC, om.experience DESC
                     LIMIT ?''', (org_id, limit))
        members = c.fetchall()
        conn.close()
        
        result = []
        for member in members:
            result.append({
                'id': member[0],
                'org_id': member[1],
                'user_id': member[2],
                'role': member[3],
                'salary': member[4],
                'permissions': member[5],
                'join_date': member[6],
                'last_promotion': member[7],
                'performance': member[8],
                'department': member[9],
                'rank': member[10],
                'experience': member[11],
                'tasks_completed': member[12],
                'full_name': member[13] or "Неизвестно",
                'username': member[14] or "Неизвестно",
                'level': member[15] or 1,
                'reputation': member[16] or 50,
                'total_exp': member[17] or 0
            })
        return result
    
    def get_pending_applications(self, org_id):
        """Получение заявок в организацию"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT oa.*, u.full_name, u.username, u.education, u.reputation, u.level 
                     FROM organization_applications oa
                     LEFT JOIN users u ON oa.user_id = u.user_id
                     WHERE oa.org_id = ? AND oa.status = 'pending'
                     ORDER BY oa.applied_date DESC''', (org_id,))
        applications = c.fetchall()
        conn.close()
        
        result = []
        for app in applications:
            result.append({
                'id': app[0],
                'org_id': app[1],
                'user_id': app[2],
                'application_text': app[3],
                'status': app[4],
                'applied_date': app[5],
                'reviewed_by': app[6],
                'reviewed_date': app[7],
                'notes': app[8],
                'full_name': app[9] or "Неизвестно",
                'username': app[10] or "Неизвестно",
                'education': app[11] or 1,
                'reputation': app[12] or 50,
                'level': app[13] or 1
            })
        return result
    
    def apply_to_organization(self, user_id, org_id, application_text):
        """Подача заявки в организацию"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем, не подана ли уже заявка
        c.execute('''SELECT id FROM organization_applications 
                     WHERE user_id = ? AND org_id = ? AND status = 'pending' ''', 
                 (user_id, org_id))
        
        if c.fetchone():
            conn.close()
            return False, "📭 Вы уже подали заявку в эту организацию!"
        
        # Проверяем, не является ли уже членом
        c.execute('SELECT id FROM organization_members WHERE user_id = ? AND org_id = ?', 
                 (user_id, org_id))
        
        if c.fetchone():
            conn.close()
            return False, "👥 Вы уже являетесь членом этой организации!"
        
        # Проверяем требования
        org = self.get_organization_by_id(org_id)
        user = self.get_user(user_id)
        
        if not org or not user:
            conn.close()
            return False, "❌ Ошибка данных!"
        
        # Проверяем требования к образованию
        if 'Образование' in org['requirements']:
            import re
            edu_match = re.search(r'Образование (\d+)\+', org['requirements'])
            if edu_match:
                required_edu = int(edu_match.group(1))
                if user.get('education', 1) < required_edu:
                    conn.close()
                    return False, f"❌ Недостаточное образование! Требуется: {required_edu}+, у вас: {user.get('education', 1)}"
        
        # Проверяем требования к репутации
        if 'Репутация' in org['requirements']:
            rep_match = re.search(r'Репутация (\d+)\+', org['requirements'])
            if rep_match:
                required_rep = int(rep_match.group(1))
                if user.get('reputation', 50) < required_rep:
                    conn.close()
                    return False, f"❌ Недостаточная репутация! Требуется: {required_rep}+, у вас: {user.get('reputation', 50)}"
        
        # Проверяем состояние для полиции (без механики здоровья)
        if org['name'] == 'Полиция' and user.get('life_state', 'alive') != 'alive':
            conn.close()
            return False, "❌ Нельзя вступить в полицию в состоянии травмы. Сначала восстановитесь."

        # Создаем заявку
        c.execute('''INSERT INTO organization_applications 
                    (org_id, user_id, application_text, applied_date, status)
                    VALUES (?, ?, ?, ?, ?)''',
                 (org_id, user_id, application_text, datetime.now().isoformat(), 'pending'))
        
        conn.commit()
        conn.close()
        return True, "✅ Заявка успешно подана на рассмотрение!"
    
    def process_application(self, application_id, reviewer_id, decision, notes=None):
        """Обработка заявки в организацию"""
        conn = get_conn()
        c = conn.cursor()
        
        # Получаем информацию о заявке
        c.execute('SELECT org_id, user_id FROM organization_applications WHERE id = ?', (application_id,))
        app = c.fetchone()
        
        if not app:
            conn.close()
            return False, "❌ Заявка не найдена!"
        
        org_id, user_id = app
        
        if decision == 'approve':
            # Проверяем, не стал ли уже членом
            c.execute('SELECT id FROM organization_members WHERE user_id = ? AND org_id = ?', (user_id, org_id))
            if c.fetchone():
                conn.close()
                return False, "👥 Пользователь уже является членом организации!"
            
            org = self.get_organization_by_id(org_id)
            
            # Определяем начальную роль в зависимости от организации
            role_mapping = {
                'Правительство': 'Ассистент',
                'Полиция': 'Офицер',
                'Больница': 'Врач',
                'Суд': 'Секретарь',
                'Банк': 'Кассир',
                'Университет': 'Преподаватель',
                'ФБР': 'Агент',
                'Налоговая служба': 'Инспектор'
            }
            
            initial_role = role_mapping.get(org['name'], 'Новичок')
            
            # Определяем начальную зарплату
            salary_mapping = {
                'Правительство': 1500,
                'Полиция': 1200,
                'Больница': 1400,
                'Суд': 1300,
                'Банк': 1600,
                'Университет': 1100,
                'ФБР': 1700,
                'Налоговая служба': 1650
            }
            
            initial_salary = salary_mapping.get(org['name'], 500)
            
            # Добавляем в члены
            c.execute('''INSERT INTO organization_members 
                        (org_id, user_id, role, salary, join_date, performance)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (org_id, user_id, initial_role, initial_salary, datetime.now().isoformat(), 100))
            
            # Обновляем счетчик членов
            c.execute('UPDATE organizations SET members = members + 1 WHERE id = ?', (org_id,))
            
            # Обновляем заявку
            c.execute('''UPDATE organization_applications 
                        SET status = "approved", reviewed_by = ?, reviewed_date = ?, notes = ?
                        WHERE id = ?''',
                     (reviewer_id, datetime.now().isoformat(), notes or 'Заявка одобрена', application_id))
            
            conn.commit()
            conn.close()

            # Обновляем организацию у пользователя
            self.update_user(user_id, organization=org['name'], role=initial_role)
            
            # Отправляем уведомление пользователю
            self.send_notification(
                user_id, 
                reviewer_id, 
                f"🎉 Ваша заявка в {org['name']} одобрена!",
                f"Вы приняты в {org['name']} на должность {initial_role} с зарплатой ${initial_salary}/месяц."
            )
            
            return True, f"✅ Заявка одобрена! Пользователь принят в {org['name']} как {initial_role}"
        
        else:  # reject
            c.execute('''UPDATE organization_applications 
                        SET status = "rejected", reviewed_by = ?, reviewed_date = ?, notes = ?
                        WHERE id = ?''',
                     (reviewer_id, datetime.now().isoformat(), notes or 'Заявка отклонена', application_id))
            
            conn.commit()
            conn.close()
            
            # Отправляем уведомление
            self.send_notification(
                user_id, 
                reviewer_id,
                f"😔 Ваша заявка в {self.get_organization_by_id(org_id)['name']} отклонена",
                notes or 'Ваша заявка была отклонена.'
            )
            
            return True, "❌ Заявка отклонена."

    # ==================== БИЗНЕСЫ ====================

    def get_owned_properties(self, owner_id, only_free=False, commercial_only=False):
        conn = get_conn()
        c = conn.cursor()
        query = '''
            SELECT p.id, p.name, p.price, p.rent, p.location, p.category,
                   COALESCE(p.condition, 100), COALESCE(p.maintenance_daily, 0),
                   pf.facility_type
            FROM property_ownership po
            JOIN properties p ON p.id = po.property_id
            LEFT JOIN property_facilities pf ON pf.property_id = p.id
            WHERE po.owner_id = ?
        '''
        if commercial_only:
            query += " AND p.category = 'commercial'"
        if only_free:
            query += " AND pf.property_id IS NULL"
        query += " ORDER BY p.id ASC"
        c.execute(query, (owner_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'name': r[1],
            'price': r[2],
            'rent': r[3],
            'location': r[4],
            'category': r[5],
            'condition': r[6],
            'maintenance_daily': r[7],
            'facility_type': r[8]
        } for r in rows]

    def _property_available_for_facility(self, owner_id, property_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT p.id, p.category
                     FROM property_ownership po
                     JOIN properties p ON p.id = po.property_id
                     WHERE po.owner_id = ? AND po.property_id = ?''', (owner_id, property_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ У вас нет такого здания."

        _, category = row
        if category != 'commercial':
            conn.close()
            return False, "❌ Для бизнеса/организации нужно коммерческое здание."

        c.execute('SELECT id FROM property_facilities WHERE property_id = ?', (property_id,))
        busy = c.fetchone()
        conn.close()
        if busy:
            return False, "❌ Это здание уже занято."
        return True, "ok"

    def create_business(self, owner_id, name, business_type, description, property_id, equipment_level=1):
        conn = get_conn()
        c = conn.cursor()

        c.execute('SELECT id FROM businesses WHERE name = ?', (name,))
        if c.fetchone():
            conn.close()
            return False, "❌ Бизнес с таким названием уже существует!", None

        ok, msg = self._property_available_for_facility(owner_id, property_id)
        if not ok:
            conn.close()
            return False, msg, None

        owner = self.get_user(owner_id) or {}
        equipment_level = max(1, min(5, int(equipment_level or 1)))
        setup_cost = BUSINESS_EQUIP_BASE_COST * equipment_level
        if owner.get('balance', 0) < setup_cost:
            conn.close()
            return False, f"❌ Недостаточно средств на оборудование. Нужно ${setup_cost:,.0f}.", None

        prop = self.get_property(property_id) or {}
        c.execute('''INSERT INTO businesses
                    (name, owner_id, type, description, location, created_date, property_id, equipment_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (name, owner_id, business_type, description, prop.get('location'), datetime.now().isoformat(),
                  property_id, equipment_level))
        business_id = c.lastrowid

        c.execute('''INSERT INTO business_employees
                    (business_id, user_id, role, salary, join_date)
                    VALUES (?, ?, ?, ?, ?)''',
                 (business_id, owner_id, 'Владелец', 0, datetime.now().isoformat()))

        c.execute('''INSERT INTO property_facilities
                    (property_id, facility_type, facility_id, owner_id, setup_cost, setup_level, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (property_id, 'business', business_id, owner_id, setup_cost, equipment_level, datetime.now().isoformat()))

        conn.commit()
        conn.close()
        self.update_user(owner_id, business_owner=1, balance=owner.get('balance', 0) - setup_cost)
        self.adjust_reputation(owner_id, 1.0, "Запуск бизнеса")
        return True, f"✅ Бизнес создан в здании #{property_id}. Оборудование: ${setup_cost:,.0f}.", business_id

    def _get_system_value(self, cursor, key):
        cursor.execute('SELECT value FROM system_state WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def _set_system_value(self, cursor, key, value):
        cursor.execute('''INSERT INTO system_state (key, value)
                          VALUES (?, ?)
                          ON CONFLICT(key) DO UPDATE SET value = excluded.value''',
                       (key, str(value)))

    def adjust_reputation(self, user_id, delta, reason):
        user = self.get_user(user_id)
        if not user:
            return
        old_rep = float(user.get('reputation', 50) or 50)
        new_rep = max(0.0, min(100.0, old_rep + float(delta)))
        self.update_user(user_id, reputation=new_rep)

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO reputation_logs (user_id, delta, reason, created_at)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, float(delta), reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def run_daily_economy_cycle(self):
        """Глобальный дневной цикл: налоги, выплаты по кредитам, базовые санкции/бонусы."""
        today = datetime.now().date()
        conn = get_conn()
        c = conn.cursor()

        last_cycle_raw = self._get_system_value(c, "daily_cycle_date")
        if not last_cycle_raw:
            self._set_system_value(c, "daily_cycle_date", today.isoformat())
            c.execute('''UPDATE users
                         SET last_economy_update = ?
                         WHERE last_economy_update IS NULL''', (today.isoformat(),))
            conn.commit()
            conn.close()
            return

        try:
            last_cycle = datetime.fromisoformat(last_cycle_raw).date()
        except ValueError:
            last_cycle = today

        if last_cycle >= today:
            conn.close()
            return

        days = (today - last_cycle).days
        # Ограничиваем catch-up, чтобы не блокировать бота после долгого оффлайна.
        days = min(days, 14)
        start_day = today - timedelta(days=days - 1)

        for step in range(days):
            cycle_day = start_day + timedelta(days=step)
            self._apply_daily_cycle_for_day(c, cycle_day)

        self._set_system_value(c, "daily_cycle_date", today.isoformat())
        conn.commit()
        conn.close()

    def _apply_daily_cycle_for_day(self, cursor, cycle_day):
        cycle_date = cycle_day.isoformat()

        cursor.execute('SELECT id FROM organizations WHERE name = ?', ('Налоговая служба',))
        tax_org_row = cursor.fetchone()
        tax_org_id = tax_org_row[0] if tax_org_row else None
        total_collected = 0.0

        cursor.execute('''SELECT user_id, balance, reputation, salary, citizen_salary,
                                 tax_debt, total_tax_paid
                          FROM users''')
        users = cursor.fetchall()

        for row in users:
            user_id = row[0]
            balance = float(row[1] or 0)
            reputation = float(row[2] or 50)
            org_salary = float(row[3] or 0)
            citizen_salary = float(row[4] or 0)
            tax_debt = float(row[5] or 0)
            total_tax_paid = float(row[6] or 0)

            # Дневной оклад (организация + гражданская работа)
            daily_salary = max(0.0, org_salary + citizen_salary) / 30.0
            if daily_salary > 0:
                balance += daily_salary

            # Налоги и обслуживание собственности
            cursor.execute('''SELECT COALESCE(SUM(p.price), 0), COALESCE(SUM(p.maintenance_daily), 0)
                              FROM property_ownership po
                              JOIN properties p ON p.id = po.property_id
                              WHERE po.owner_id = ?''', (user_id,))
            prop_value, maintenance_total = cursor.fetchone()
            prop_value = float(prop_value or 0)
            maintenance_total = float(maintenance_total or 0)

            cursor.execute('''SELECT COALESCE(SUM(budget), 0)
                              FROM businesses WHERE owner_id = ?''', (user_id,))
            biz_budget = float((cursor.fetchone() or [0])[0] or 0)

            cursor.execute('''SELECT COALESCE(SUM(budget), 0)
                              FROM private_orgs WHERE leader_id = ?''', (user_id,))
            org_budget = float((cursor.fetchone() or [0])[0] or 0)

            citizen_tax = max(DAILY_MIN_CITIZEN_TAX, balance * DAILY_CITIZEN_TAX_RATE)
            property_tax = prop_value * DAILY_PROPERTY_TAX_RATE
            business_tax = biz_budget * DAILY_BUSINESS_TAX_RATE
            org_tax = org_budget * DAILY_PRIVATE_ORG_TAX_RATE
            due_total = citizen_tax + property_tax + business_tax + org_tax + maintenance_total

            paid_total = min(balance, due_total) if due_total > 0 else 0.0
            debt_today = max(0.0, due_total - paid_total)
            balance -= paid_total
            total_collected += paid_total
            total_tax_paid += paid_total
            tax_debt += debt_today

            # Дневной платёж по кредитам
            rep_delta = 0.0
            cursor.execute('''SELECT id, remaining_balance, monthly_payment, daily_payment
                              FROM loans
                              WHERE applicant_id = ? AND status IN ("approved", "active")''', (user_id,))
            loans = cursor.fetchall()
            defaults_inc = 0

            for loan in loans:
                loan_id, remaining_balance, monthly_payment, daily_payment = loan
                remaining_balance = float(remaining_balance or 0)
                if remaining_balance <= 0:
                    cursor.execute('''UPDATE loans
                                      SET remaining_balance = 0, status = "paid", last_payment_date = ?
                                      WHERE id = ?''', (cycle_date, loan_id))
                    continue

                due = float(daily_payment or 0)
                if due <= 0:
                    due = float(monthly_payment or 0) / 30.0

                effective_due = min(due, remaining_balance)
                paid_loan = min(balance, effective_due)
                balance -= paid_loan
                remaining_balance -= paid_loan

                if paid_loan + 1e-9 < effective_due:
                    unpaid = effective_due - paid_loan
                    remaining_balance += unpaid * DAILY_LOAN_PENALTY_RATE
                    defaults_inc += 1
                    rep_delta -= 0.2

                if remaining_balance <= 0.01:
                    remaining_balance = 0.0
                    status = "paid"
                    rep_delta += 0.25
                else:
                    status = "active"

                cursor.execute('''UPDATE loans
                                  SET remaining_balance = ?, status = ?, last_payment_date = ?
                                  WHERE id = ?''',
                               (remaining_balance, status, cycle_date, loan_id))

            # Репутация: поощрение за дисциплину / штраф за долги
            if debt_today > 0:
                rep_delta -= min(1.2, 0.35 + debt_today / 3500.0)
            else:
                rep_delta += 0.15

            reputation = max(0.0, min(100.0, reputation + rep_delta))

            cursor.execute('''UPDATE users
                              SET balance = ?, reputation = ?, tax_debt = ?, total_tax_paid = ?,
                                  last_economy_update = ?, loan_defaults = COALESCE(loan_defaults, 0) + ?
                              WHERE user_id = ?''',
                           (balance, reputation, tax_debt, total_tax_paid, cycle_date, defaults_inc, user_id))

            cursor.execute('''INSERT INTO tax_logs
                              (user_id, cycle_date, citizen_tax, property_tax, business_tax, org_tax,
                               paid_total, debt_total, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (user_id, cycle_date, citizen_tax, property_tax + maintenance_total,
                            business_tax, org_tax, paid_total, debt_today, datetime.now().isoformat()))

        if tax_org_id and total_collected > 0:
            cursor.execute('UPDATE organizations SET budget = budget + ? WHERE id = ?', (total_collected, tax_org_id))

        self._resolve_expired_protests_cursor(cursor, cycle_date)

        # Проверяем завершенные выборы
        cursor.execute("SELECT id FROM elections WHERE status = 'active' AND end_date <= ?", (f"{cycle_date}T23:59:59",))
        ended_elections = cursor.fetchall()
        for election_row in ended_elections:
            self.tally_election(election_row[0])


    def _resolve_expired_protests_cursor(self, cursor, cycle_date):
        cursor.execute('''SELECT id, creator_id, support_count, against_count
                          FROM protests
                          WHERE status = 'active' AND end_date <= ?''', (f"{cycle_date}T23:59:59",))
        expired = cursor.fetchall()
        if not expired:
            return

        for protest_id, creator_id, support_count, against_count in expired:
            support_count = int(support_count or 0)
            against_count = int(against_count or 0)
            turnout = support_count + against_count

            if turnout >= 15 and support_count > against_count:
                result = "Требования митинга услышаны властями."
                # Небольшой политический эффект на правительство
                cursor.execute('UPDATE organizations SET reputation = MAX(0, reputation - 2) WHERE name = ?', ('Правительство',))
                rep_delta_creator = 2.0
            elif turnout >= 10 and support_count == against_count:
                result = "Митинг вызвал общественный резонанс, решение отложено."
                rep_delta_creator = 0.5
            else:
                result = "Митинг не получил достаточной поддержки."
                rep_delta_creator = -1.0

            cursor.execute('''UPDATE protests
                              SET status = 'closed', result_summary = ?
                              WHERE id = ?''', (result, protest_id))

            # Репутация организатора
            cursor.execute('SELECT reputation FROM users WHERE user_id = ?', (creator_id,))
            creator_row = cursor.fetchone()
            if creator_row:
                new_rep = max(0.0, min(100.0, float(creator_row[0] or 50) + rep_delta_creator))
                cursor.execute('UPDATE users SET reputation = ? WHERE user_id = ?', (new_rep, creator_id))
                cursor.execute('''INSERT INTO reputation_logs (user_id, delta, reason, created_at)
                                  VALUES (?, ?, ?, ?)''',
                               (creator_id, rep_delta_creator, "Итог митинга", datetime.now().isoformat()))
    def list_businesses(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, name, type, budget, status, property_id, equipment_level, location
                     FROM businesses ORDER BY id DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'name': r[1],
            'type': r[2],
            'budget': r[3],
            'status': r[4],
            'property_id': r[5],
            'equipment_level': r[6],
            'location': r[7]
        } for r in rows]

    def get_business(self, business_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM businesses WHERE id = ?', (business_id,))
        row = c.fetchone()
        columns = [col[0] for col in c.description] if c.description else []
        conn.close()
        if not row:
            return None
        data = dict(zip(columns, row))
        return {
            'id': data.get('id'),
            'name': data.get('name'),
            'owner_id': data.get('owner_id'),
            'type': data.get('type'),
            'budget': data.get('budget', 0),
            'description': data.get('description'),
            'status': data.get('status'),
            'location': data.get('location'),
            'created_date': data.get('created_date'),
            'property_id': data.get('property_id'),
            'equipment_level': data.get('equipment_level', 1),
            'income_daily': data.get('income_daily', 800),
            'expense_daily': data.get('expense_daily', 300),
            'last_income_date': data.get('last_income_date')
        }

    def get_business_members(self, business_id, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT be.*, u.full_name
                     FROM business_employees be
                     LEFT JOIN users u ON be.user_id = u.user_id
                     WHERE be.business_id = ?
                     ORDER BY be.id ASC
                     LIMIT ?''', (business_id, limit))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'business_id': r[1],
            'user_id': r[2],
            'role': r[3],
            'salary': r[4],
            'join_date': r[5],
            'full_name': r[6] or "Неизвестно"
        } for r in rows]

    def get_pending_business_applications(self, business_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ba.*, u.full_name
                     FROM business_applications ba
                     LEFT JOIN users u ON ba.user_id = u.user_id
                     WHERE ba.business_id = ? AND ba.status = 'pending'
                     ORDER BY ba.applied_date DESC''', (business_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'business_id': r[1],
            'user_id': r[2],
            'application_text': r[3],
            'status': r[4],
            'applied_date': r[5],
            'full_name': r[8] or "Неизвестно"
        } for r in rows]

    def apply_to_business(self, user_id, business_id, application_text):
        conn = get_conn()
        c = conn.cursor()

        c.execute('''SELECT id FROM business_applications
                     WHERE user_id = ? AND business_id = ? AND status = 'pending' ''',
                 (user_id, business_id))
        if c.fetchone():
            conn.close()
            return False, "📭 Вы уже подали заявку в этот бизнес!", None

        c.execute('SELECT id FROM business_employees WHERE user_id = ? AND business_id = ?',
                 (user_id, business_id))
        if c.fetchone():
            conn.close()
            return False, "👥 Вы уже работаете в этом бизнесе!", None

        c.execute('''INSERT INTO business_applications
                    (business_id, user_id, application_text, applied_date, status)
                    VALUES (?, ?, ?, ?, ?)''',
                 (business_id, user_id, application_text, datetime.now().isoformat(), 'pending'))
        application_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ Заявка в бизнес отправлена!", application_id

    def process_business_application(self, application_id, reviewer_id, decision):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT business_id, user_id FROM business_applications WHERE id = ?', (application_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ Заявка не найдена!", None
        business_id, user_id = row

        if decision == 'approve':
            c.execute('''INSERT INTO business_employees
                        (business_id, user_id, role, salary, join_date)
                        VALUES (?, ?, ?, ?, ?)''',
                     (business_id, user_id, 'Сотрудник', 0, datetime.now().isoformat()))
            c.execute('''UPDATE business_applications
                         SET status = "approved", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            return True, "✅ Заявка одобрена!", user_id
        else:
            c.execute('''UPDATE business_applications
                         SET status = "rejected", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            return True, "❌ Заявка отклонена.", user_id

    # ==================== ЧАСТНЫЕ ОРГАНИЗАЦИИ ====================

    def create_private_org(self, leader_id, name, description, policy, property_id, equipment_level=1):
        conn = get_conn()
        c = conn.cursor()

        c.execute('SELECT id FROM private_orgs WHERE name = ?', (name,))
        if c.fetchone():
            conn.close()
            return False, "❌ Организация с таким названием уже существует!", None

        ok, msg = self._property_available_for_facility(leader_id, property_id)
        if not ok:
            conn.close()
            return False, msg, None

        leader = self.get_user(leader_id) or {}
        equipment_level = max(1, min(5, int(equipment_level or 1)))
        setup_cost = BUSINESS_EQUIP_BASE_COST * PRIVATE_ORG_EQUIP_MULTIPLIER * equipment_level
        if leader.get('balance', 0) < setup_cost:
            conn.close()
            return False, f"❌ Недостаточно средств на запуск организации. Нужно ${setup_cost:,.0f}.", None

        c.execute('''INSERT INTO private_orgs
                    (name, leader_id, description, policy, created_date, property_id, equipment_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (name, leader_id, description, policy, datetime.now().isoformat(), property_id, equipment_level))
        org_id = c.lastrowid

        c.execute('''INSERT INTO private_org_members
                    (org_id, user_id, role, join_date)
                    VALUES (?, ?, ?, ?)''',
                 (org_id, leader_id, 'Лидер', datetime.now().isoformat()))

        c.execute('''INSERT INTO property_facilities
                    (property_id, facility_type, facility_id, owner_id, setup_cost, setup_level, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (property_id, 'private_org', org_id, leader_id, setup_cost, equipment_level, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        self.update_user(leader_id, balance=leader.get('balance', 0) - setup_cost)
        self.adjust_reputation(leader_id, 1.2, "Создание частной организации")
        return True, f"✅ Частная организация создана в здании #{property_id}. Оснащение: ${setup_cost:,.0f}.", org_id

    def list_private_orgs(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, name, budget, status, property_id, equipment_level
                     FROM private_orgs ORDER BY id DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'name': r[1],
            'budget': r[2],
            'status': r[3],
            'property_id': r[4],
            'equipment_level': r[5]
        } for r in rows]

    def get_private_org(self, org_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM private_orgs WHERE id = ?', (org_id,))
        row = c.fetchone()
        columns = [col[0] for col in c.description] if c.description else []
        conn.close()
        if not row:
            return None
        data = dict(zip(columns, row))
        return {
            'id': data.get('id'),
            'name': data.get('name'),
            'leader_id': data.get('leader_id'),
            'budget': data.get('budget', 0),
            'description': data.get('description'),
            'policy': data.get('policy'),
            'status': data.get('status'),
            'created_date': data.get('created_date'),
            'property_id': data.get('property_id'),
            'equipment_level': data.get('equipment_level', 1)
        }

    def apply_to_private_org(self, user_id, org_id, application_text):
        conn = get_conn()
        c = conn.cursor()

        c.execute('''SELECT id FROM private_org_applications
                     WHERE user_id = ? AND org_id = ? AND status = 'pending' ''',
                 (user_id, org_id))
        if c.fetchone():
            conn.close()
            return False, "📭 Вы уже подали заявку в эту организацию!", None

        c.execute('SELECT id FROM private_org_members WHERE user_id = ? AND org_id = ?',
                 (user_id, org_id))
        if c.fetchone():
            conn.close()
            return False, "👥 Вы уже состоите в этой организации!", None

        c.execute('''INSERT INTO private_org_applications
                    (org_id, user_id, application_text, applied_date, status)
                    VALUES (?, ?, ?, ?, ?)''',
                 (org_id, user_id, application_text, datetime.now().isoformat(), 'pending'))
        application_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ Заявка отправлена!", application_id

    def get_pending_private_org_applications(self, org_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT poa.*, u.full_name
                     FROM private_org_applications poa
                     LEFT JOIN users u ON poa.user_id = u.user_id
                     WHERE poa.org_id = ? AND poa.status = 'pending'
                     ORDER BY poa.applied_date DESC''', (org_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'org_id': r[1],
            'user_id': r[2],
            'application_text': r[3],
            'status': r[4],
            'applied_date': r[5],
            'full_name': r[8] or "Неизвестно"
        } for r in rows]

    def process_private_org_application(self, application_id, reviewer_id, decision):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT org_id, user_id FROM private_org_applications WHERE id = ?', (application_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ Заявка не найдена!", None
        org_id, user_id = row

        if decision == 'approve':
            c.execute('''INSERT INTO private_org_members
                        (org_id, user_id, role, join_date)
                        VALUES (?, ?, ?, ?)''',
                     (org_id, user_id, 'Участник', datetime.now().isoformat()))
            c.execute('''UPDATE private_org_applications
                         SET status = "approved", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            return True, "✅ Заявка одобрена!", user_id
        else:
            c.execute('''UPDATE private_org_applications
                         SET status = "rejected", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            return True, "❌ Заявка отклонена.", user_id

    # ==================== БАНДЫ ====================

    def create_gang(self, leader_id, name, territory):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT id FROM gangs WHERE name = ?', (name,))
        if c.fetchone():
            conn.close()
            return False, "❌ Банда с таким названием уже существует!", None

        c.execute('''INSERT INTO gangs
                    (name, leader_id, territory, created_date)
                    VALUES (?, ?, ?, ?)''',
                 (name, leader_id, territory, datetime.now().isoformat()))
        gang_id = c.lastrowid
        c.execute('''INSERT INTO gang_members
                    (gang_id, user_id, role, join_date)
                    VALUES (?, ?, ?, ?)''',
                 (gang_id, leader_id, 'Лидер', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        self.update_user(leader_id, gang_member=1)
        return True, "✅ Банда создана!", gang_id

    def list_gangs(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, name, territory, reputation, status
                     FROM gangs ORDER BY id DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'name': r[1],
            'territory': r[2],
            'reputation': r[3],
            'status': r[4]
        } for r in rows]

    def get_gang(self, gang_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM gangs WHERE id = ?', (gang_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'name': row[1],
            'leader_id': row[2],
            'territory': row[3],
            'reputation': row[4],
            'status': row[5],
            'created_date': row[6]
        }

    def get_user_gang(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT g.*, gm.role
                     FROM gang_members gm
                     JOIN gangs g ON gm.gang_id = g.id
                     WHERE gm.user_id = ?''', (user_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'name': row[1],
            'leader_id': row[2],
            'territory': row[3],
            'reputation': row[4],
            'status': row[5],
            'created_date': row[6],
            'role': row[7]
        }

    def apply_to_gang(self, user_id, gang_id, application_text):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id FROM gang_applications
                     WHERE user_id = ? AND gang_id = ? AND status = 'pending' ''',
                 (user_id, gang_id))
        if c.fetchone():
            conn.close()
            return False, "📭 Вы уже подали заявку в эту банду!", None

        c.execute('SELECT id FROM gang_members WHERE user_id = ? AND gang_id = ?',
                 (user_id, gang_id))
        if c.fetchone():
            conn.close()
            return False, "👥 Вы уже в этой банде!", None

        c.execute('''INSERT INTO gang_applications
                    (gang_id, user_id, application_text, applied_date, status)
                    VALUES (?, ?, ?, ?, ?)''',
                 (gang_id, user_id, application_text, datetime.now().isoformat(), 'pending'))
        application_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ Заявка в банду отправлена!", application_id

    def get_pending_gang_applications(self, gang_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ga.*, u.full_name
                     FROM gang_applications ga
                     LEFT JOIN users u ON ga.user_id = u.user_id
                     WHERE ga.gang_id = ? AND ga.status = 'pending'
                     ORDER BY ga.applied_date DESC''', (gang_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'gang_id': r[1],
            'user_id': r[2],
            'application_text': r[3],
            'status': r[4],
            'applied_date': r[5],
            'full_name': r[8] or "Неизвестно"
        } for r in rows]

    def process_gang_application(self, application_id, reviewer_id, decision):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT gang_id, user_id FROM gang_applications WHERE id = ?', (application_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ Заявка не найдена!", None
        gang_id, user_id = row

        if decision == 'approve':
            c.execute('''INSERT INTO gang_members
                        (gang_id, user_id, role, join_date)
                        VALUES (?, ?, ?, ?)''',
                     (gang_id, user_id, 'Боец', datetime.now().isoformat()))
            c.execute('''UPDATE gang_applications
                         SET status = "approved", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            self.update_user(user_id, gang_member=1)
            return True, "✅ Заявка одобрена!", user_id
        else:
            c.execute('''UPDATE gang_applications
                         SET status = "rejected", reviewed_by = ?, reviewed_date = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), application_id))
            conn.commit()
            conn.close()
            return True, "❌ Заявка отклонена.", user_id

    def gang_attack(self, actor_id, target_id, severity):
        attacker_gang = self.get_user_gang(actor_id)
        if not attacker_gang:
            return False, "❌ Вы не состоите в банде!"

        actor = self.get_user(actor_id)
        target = self.get_user(target_id)
        if not target:
            return False, "❌ Цель не найдена!"
        if target.get('life_state', 'alive') == 'dead':
            return False, "❌ Цель уже мертва."
        if actor and actor.get('life_state', 'alive') != 'alive':
            return False, "❌ Вы в состоянии травмы и не можете атаковать."

        rep = attacker_gang.get('reputation', 50)
        success_chance = max(0.2, min(0.9, 0.6 + (rep - 50) / 200))
        success = random.random() <= success_chance

        result = "failed"
        if success:
            result = "success"
            if severity == 'kill':
                self.update_user(target_id, life_state='dead', injury_severity='fatal', injured_until=None)
            else:
                injury_days = {
                    'light': 1,
                    'medium': 3,
                    'severe': 7,
                    'critical': 14
                }.get(severity, 3)
                injured_until = datetime.now() + timedelta(days=injury_days)
                self.update_user(
                    target_id,
                    life_state='injured',
                    injury_severity=severity,
                    injured_until=injured_until.isoformat()
                )

            self.send_notification(
                target_id,
                actor_id,
                "⚠️ НАПАДЕНИЕ БАНДЫ",
                f"Вы стали целью нападения. Результат: {severity}"
            )

        # Логируем
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO gang_actions
                    (gang_id, actor_id, target_id, action_type, severity, result, action_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (attacker_gang['id'], actor_id, target_id, 'attack', severity, result, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        if not success:
            return False, "❌ Атака не удалась."
        return True, "✅ Атака успешна!"

    # ==================== СУД ====================

    def create_court_case(self, plaintiff_id, defendant_id, description):
        conn = get_conn()
        c = conn.cursor()
        case_number = f"C-{datetime.now():%Y%m%d}-{random.randint(1000,9999)}"
        c.execute('''INSERT INTO court_cases
                    (case_number, plaintiff_id, defendant_id, description, status, opened_date)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (case_number, plaintiff_id, defendant_id, description, 'open', datetime.now().isoformat()))
        case_id = c.lastrowid
        conn.commit()
        conn.close()
        return case_id, case_number

    def get_case(self, case_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM court_cases WHERE id = ?', (case_id,))
        row = c.fetchone()
        conn.close()
        return row

    def list_user_cases(self, user_id, limit=10):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, case_number, status, opened_date
                     FROM court_cases
                     WHERE plaintiff_id = ? OR defendant_id = ?
                     ORDER BY opened_date DESC LIMIT ?''', (user_id, user_id, limit))
        rows = c.fetchall()
        conn.close()
        return rows

    def list_open_court_cases(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, case_number, plaintiff_id, defendant_id, description, opened_date
                     FROM court_cases
                     WHERE status = 'open'
                     ORDER BY opened_date ASC
                     LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': row[0],
            'case_number': row[1],
            'plaintiff_id': row[2],
            'defendant_id': row[3],
            'description': row[4] or '',
            'opened_date': row[5],
        } for row in rows]

    def assign_case(self, case_id, judge_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE court_cases
                     SET judge_id = ?, status = 'in_review'
                     WHERE id = ?''', (judge_id, case_id))
        conn.commit()
        conn.close()

    def close_case(self, case_id, verdict, sentence, fine):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT plaintiff_id, defendant_id, judge_id FROM court_cases WHERE id = ?', (case_id,))
        case_row = c.fetchone()
        if not case_row:
            conn.close()
            return False, "❌ Дело не найдено."
        plaintiff_id, defendant_id, judge_id = case_row
        c.execute('''UPDATE court_cases
                     SET verdict = ?, sentence = ?, fine = ?, status = 'closed', closed_date = ?
                     WHERE id = ?''', (verdict, sentence, fine, datetime.now().isoformat(), case_id))
        conn.commit()
        conn.close()
        fine = max(0.0, min(7000.0, float(fine or 0)))
        lowered = str(verdict or "").lower()

        if fine > 0 and defendant_id:
            defendant = self.get_user(defendant_id) or {}
            current_balance = float(defendant.get('balance', 0) or 0)
            paid = min(current_balance, fine)
            debt_add = max(0.0, fine - paid)
            self.update_user(
                defendant_id,
                balance=current_balance - paid,
                fines_paid=float(defendant.get('fines_paid', 0) or 0) + paid,
                tax_debt=float(defendant.get('tax_debt', 0) or 0) + debt_add,
            )

        if "винов" in lowered:
            if defendant_id:
                self.adjust_reputation(defendant_id, -3.5, "Решение суда")
            if plaintiff_id:
                self.adjust_reputation(plaintiff_id, 0.8, "Участие в судебном процессе")
        elif "отклон" in lowered or "не винов" in lowered:
            if defendant_id:
                self.adjust_reputation(defendant_id, 1.2, "Решение суда")
            if plaintiff_id:
                self.adjust_reputation(plaintiff_id, -0.5, "Необоснованный иск")

        if judge_id:
            self.adjust_reputation(judge_id, 0.6, "Завершение судебного дела")
        return True, "✅ Дело закрыто."

    def add_case_evidence(self, case_id, user_id, evidence_text):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT plaintiff_id, defendant_id, evidence FROM court_cases WHERE id = ?', (case_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ Дело не найдено."

        plaintiff_id, defendant_id, evidence = row
        if user_id not in [plaintiff_id, defendant_id]:
            conn.close()
            return False, "❌ Вы не участник дела."

        updated = (evidence + "\n" if evidence else "") + f"[{datetime.now().strftime('%d.%m.%Y %H:%M')}] {evidence_text}"
        c.execute('UPDATE court_cases SET evidence = ? WHERE id = ?', (updated, case_id))
        conn.commit()
        conn.close()
        return True, "✅ Доказательства добавлены."
    
    def send_notification(self, receiver_id, sender_id, title, message):
        """Отправка уведомления пользователю"""
        try:
            # Сохраняем сообщение в базе данных
            conn = get_conn()
            c = conn.cursor()
            c.execute('''INSERT INTO messages 
                        (sender_id, receiver_id, message_type, subject, content, date, priority)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (sender_id, receiver_id, 'official', title, message, 
                      datetime.now().isoformat(), 3))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")

        # Пытаемся отправить в Telegram, если бот доступен
        if self.bot:
            try:
                text = f"{title}\n\n{message}"
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.bot.send_message(chat_id=receiver_id, text=text))
                except RuntimeError:
                    asyncio.run(self.bot.send_message(chat_id=receiver_id, text=text))
            except Exception as e:
                print(f"Не удалось отправить Telegram-уведомление: {e}")
    
    def arrest_player(self, officer_id, suspect_id, reason, evidence="", fine=0):
        """Арест игрока полицией"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем полномочия офицера
        officer_org = self.get_user_organization(officer_id)
        if not officer_org or officer_org['name'] != 'Полиция':
            conn.close()
            return False, "❌ У вас нет полномочий для ареста!"
        
        # Проверяем, не арестован ли уже
        suspect = self.get_user(suspect_id)
        if suspect and suspect.get('arrested'):
            conn.close()
            return False, "❌ Игрок уже под арестом!"
        
        # Определяем срок ареста
        if fine > 0:
            hours = max(1, min(12, int(fine // 1500)))  # мягче по срокам: 1 час за ~$1500
        else:
            # Зависит от репутации подозреваемого
            suspect_reputation = suspect.get('reputation', 50) if suspect else 50
            if suspect_reputation < 30:
                hours = 12
            elif suspect_reputation < 60:
                hours = 8
            else:
                hours = 4
        
        arrest_until = datetime.now() + timedelta(hours=hours)
        
        # Создаем запись об аресте
        c.execute('''INSERT INTO arrests 
                    (officer_id, suspect_id, reason, evidence, arrest_date, release_date, status, fine, severity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (officer_id, suspect_id, reason, evidence, datetime.now().isoformat(),
                  arrest_until.isoformat(), 'active', fine, 'medium' if hours <= 12 else 'high'))
        
        # Обновляем статистику офицера
        officer = self.get_user(officer_id)
        
        conn.commit()
        conn.close()
        
        # Обновляем статус подозреваемого
        if suspect:
            self.update_user(
                suspect_id,
                arrested=1,
                arrested_until=arrest_until.isoformat()
            )
            self.adjust_reputation(suspect_id, -3, "Арест полицией")
        
        # Обновляем статистику офицера
        if officer:
            self.update_user(
                officer_id,
                arrests_made=officer.get('arrests_made', 0) + 1
            )
            self.adjust_reputation(officer_id, 1, "Служебный арест")
        
        # Отправляем уведомление
        officer_name = officer.get('full_name', 'Офицер') if officer else 'Офицер'
        suspect_name = suspect.get('full_name', 'Подозреваемый') if suspect else 'Подозреваемый'
        
        self.send_notification(
            suspect_id, 
            officer_id,
            "🚨 ВЫ АРЕСТОВАНЫ!",
            f"Офицер: {officer_name}\nПричина: {reason}\nСрок: {hours} часов\nШтраф: ${fine}\nОсвобождение: {arrest_until.strftime('%d.%m.%Y %H:%M')}"
        )
        
        return True, f"✅ Арест произведен! {suspect_name} арестован на {hours} часов. Штраф: ${fine}"
    
    def treat_patient(self, doctor_id, patient_id, diagnosis, treatment, cost):
        """Лечение пациента в больнице"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем полномочия врача
        doctor_org = self.get_user_organization(doctor_id)
        if not doctor_org or doctor_org['name'] != 'Больница':
            conn.close()
            return False, "❌ У вас нет полномочий для лечения!"
        
        # Проверяем пациента
        patient = self.get_user(patient_id)
        if not patient:
            conn.close()
            return False, "❌ Пациент не найден!"

        if patient.get('life_state', 'alive') == 'dead':
            conn.close()
            return False, "❌ Пациент мертв. Лечение невозможно."

        if patient.get('life_state', 'alive') == 'alive' and not patient.get('injury_severity'):
            conn.close()
            return False, "❌ Пациент не имеет травм, лечение не требуется!"
        
        # Проверяем возможность оплаты
        if patient.get('balance', 0) < cost:
            conn.close()
            return False, f"❌ У пациента недостаточно средств! Нужно: ${cost}, есть: ${patient.get('balance', 0)}"
        
        # Определяем длительность лечения по тяжести травмы
        severity = patient.get('injury_severity') or 'light'
        severity_days = {
            'light': 1,
            'medium': 2,
            'severe': 3,
            'critical': 5
        }
        hospital_days = severity_days.get(severity, 2)
        
        hospital_until = datetime.now() + timedelta(days=hospital_days)
        
        # Создаем запись о лечении
        c.execute('''INSERT INTO treatments 
                    (patient_id, doctor_id, diagnosis, treatment, cost, start_date, 
                     end_date, status, result, hospital_days)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (patient_id, doctor_id, diagnosis, treatment, cost,
                  datetime.now().isoformat(), hospital_until.isoformat(),
                  'in_progress', 'Лечение начато', hospital_days))
        
        # Врач получает 70% от стоимости
        doctor_share = int(cost * 0.7)
        doctor_user = self.get_user(doctor_id)
        
        conn.commit()
        conn.close()
        
        # Обновляем состояние пациента
        self.update_user(
            patient_id,
            balance=patient.get('balance', 0) - cost,
            in_hospital=1,
            hospital_until=hospital_until.isoformat(),
            life_state='alive',
            injury_severity=None,
            injured_until=None
        )
        
        if doctor_user:
            self.update_user(
                doctor_id,
                balance=doctor_user.get('balance', 0) + doctor_share,
                patients_treated=doctor_user.get('patients_treated', 0) + 1
            )
            self.adjust_reputation(doctor_id, 1.5, "Успешное лечение")
        
        # Отправляем уведомление пациенту
        doctor_name = doctor_user.get('full_name', 'Врач') if doctor_user else 'Врач'
        
        self.send_notification(
            patient_id, 
            doctor_id,
            "🏥 НАЧАТО ЛЕЧЕНИЕ",
            f"Врач: {doctor_name}\nДиагноз: {diagnosis}\nЛечение: {treatment}\nСтоимость: ${cost}\nГоспитализация: {hospital_days} дней\nВыздоровление: {hospital_until.strftime('%d.%m.%Y %H:%M')}"
        )
        
        return True, f"✅ Лечение начато! Пациент госпитализирован на {hospital_days} дней. Врач получает ${doctor_share}"
    
    def approve_loan(self, officer_id, applicant_id, amount, term_months, purpose):
        """Одобрение кредита в банке"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем полномочия банкира
        officer_org = self.get_user_organization(officer_id)
        if not officer_org or officer_org['name'] != 'Банк':
            conn.close()
            return False, "❌ У вас нет полномочий для одобрения кредитов!"
        
        # Проверяем заявителя
        applicant = self.get_user(applicant_id)
        if not applicant:
            conn.close()
            return False, "❌ Заявитель не найден!"
        
        # Проверяем кредитную историю
        c.execute('SELECT COUNT(*) FROM loans WHERE applicant_id = ? AND status IN ("defaulted", "rejected")', 
                 (applicant_id,))
        bad_loans = c.fetchone()[0]
        
        # Рассчитываем процентную ставку
        base_rate = 0.15  # 15% годовых
        risk_modifier = (100 - applicant.get('reputation', 50)) / 1000  # до 10% за низкую репутацию
        bad_loan_modifier = bad_loans * 0.03  # 3% за каждый плохой кредит
        
        interest_rate = base_rate + risk_modifier + bad_loan_modifier
        interest_rate = min(interest_rate, 0.5)  # Максимум 50%
        
        # Рассчитываем ежемесячный платеж
        monthly_rate = interest_rate / 12
        if monthly_rate == 0:
            monthly_payment = amount / max(1, term_months)
        else:
            monthly_payment = amount * (monthly_rate * (1 + monthly_rate) ** term_months) / ((1 + monthly_rate) ** term_months - 1)
        daily_payment = monthly_payment / 30.0
        now_iso = datetime.now().isoformat()
        
        due_date = datetime.now() + timedelta(days=30 * term_months)
        
        # Создаем кредит
        c.execute('''INSERT INTO loans
                    (applicant_id, bank_officer_id, amount, interest_rate, term_months,
                     monthly_payment, purpose, status, application_date, approval_date,
                     due_date, remaining_balance, credit_score, daily_payment, last_payment_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (applicant_id, officer_id, amount, interest_rate, term_months,
                  monthly_payment, purpose, 'active', now_iso,
                  now_iso, due_date.isoformat(), amount,
                  min(850, applicant.get('reputation', 50) * 8), daily_payment, now_iso))
        
        conn.commit()
        conn.close()
        
        # Выдаем деньги заявителю
        self.update_user(
            applicant_id,
            balance=applicant.get('balance', 0) + amount
        )
        
        # Отправляем уведомление
        applicant_name = applicant.get('full_name', 'Заявитель')
        self.send_notification(
            applicant_id, 
            officer_id,
            "🏦 КРЕДИТ ОДОБРЕН!",
            f"Сумма: ${amount:,.2f}\nСрок: {term_months} месяцев\nСтавка: {interest_rate*100:.1f}%\nЕжемесячный платеж: ${monthly_payment:,.2f}\nЦель: {purpose}"
        )
        
        return True, f"✅ Кредит одобрен! {applicant_name} получил ${amount} под {interest_rate*100:.1f}% годовых"

    def _calculate_loan_terms(self, applicant_id, amount, term_months):
        """Расчет условий кредита"""
        term_months = max(1, int(term_months or 1))
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM loans WHERE applicant_id = ? AND status IN ("defaulted", "rejected")',
                  (applicant_id,))
        bad_loans = c.fetchone()[0]
        conn.close()

        applicant = self.get_user(applicant_id) or {}
        base_rate = 0.15
        risk_modifier = (100 - applicant.get('reputation', 50)) / 1000
        bad_loan_modifier = bad_loans * 0.03
        interest_rate = min(base_rate + risk_modifier + bad_loan_modifier, 0.5)

        monthly_rate = interest_rate / 12
        if monthly_rate == 0:
            monthly_payment = amount / term_months
        else:
            monthly_payment = amount * (monthly_rate * (1 + monthly_rate) ** term_months) / ((1 + monthly_rate) ** term_months - 1)

        due_date = datetime.now() + timedelta(days=30 * term_months)
        return interest_rate, monthly_payment, due_date

    def create_loan_request(self, applicant_id, amount, term_months, purpose):
        """Создание заявки на кредит (ожидает одобрения банка)"""
        conn = get_conn()
        c = conn.cursor()

        applicant = self.get_user(applicant_id)
        if not applicant:
            conn.close()
            return False, "❌ Заявитель не найден!", None

        c.execute('''INSERT INTO loans
                    (applicant_id, amount, term_months, purpose, status, application_date)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (applicant_id, amount, term_months, purpose, 'pending', datetime.now().isoformat()))
        loan_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ Заявка на кредит создана.", loan_id

    def _ensure_column(self, table, column, definition, cursor=None):
        """Добавляет колонку в таблицу, если ее нет."""
        own_conn = None
        c = cursor
        if c is None:
            own_conn = get_conn()
            c = own_conn.cursor()

        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
        exists = c.fetchone()
        if not exists:
            if own_conn:
                own_conn.close()
            return
        c.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in c.fetchall()]
        if column not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        if own_conn:
            own_conn.commit()
            own_conn.close()

    # ==================== СИСТЕМА ПРАВЛЕНИЯ И ЗАКОНЫ ====================

    def get_government_system(self):
        """Получить информацию о текущей системе правления"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM government_system ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'current_type': row[1],
            'current_leader_id': row[2],
            'established_date': row[3],
            'last_changed': row[4],
            'stability': row[5],
            'corruption': row[6],
            'public_satisfaction': row[7]
        }
    
    def change_government_type(self, new_type, new_leader_id=None):
        """Изменить тип правления"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE government_system 
                     SET current_type = ?, current_leader_id = ?, last_changed = ?
                     WHERE id = (SELECT MAX(id) FROM government_system)''',
                 (new_type, new_leader_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    
    def create_government_rule(self, rule_text, created_by, penalty=1000):
        """Президент создает новый закон/правило"""
        conn = get_conn()
        c = conn.cursor()
        rule_num = f"RULE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        c.execute('''INSERT INTO government_rules
                     (rule_number, rule_text, created_by, created_date, status, violation_penalty)
                     VALUES (?, ?, ?, ?, 'active', ?)''',
                 (rule_num, rule_text, created_by, datetime.now().isoformat(), penalty))
        rule_id = c.lastrowid
        conn.commit()
        conn.close()
        return rule_id
    
    def get_active_rules(self):
        """Получить активные правила"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM government_rules WHERE status = ? ORDER BY created_date DESC',
                 ('active',))
        rules = c.fetchall()
        conn.close()
        result = []
        for row in rules:
            result.append({
                'id': row[0],
                'rule_number': row[1],
                'rule_text': row[2],
                'created_by': row[3],
                'created_date': row[4],
                'penalty': row[6],
                'violations_count': row[7]
            })
        return result
    
    def report_rule_violation(self, rule_id, violator_id, officer_id, description=""):
        """Полиция сообщает о нарушении правила"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT violation_penalty FROM government_rules WHERE id = ?', (rule_id,))
        rule = c.fetchone()
        if not rule:
            conn.close()
            return False, "Правило не найдено"
        
        penalty = rule[0]
        c.execute('''INSERT INTO rule_violations
                     (rule_id, violator_id, officer_id, violation_date, description, fine, status)
                     VALUES (?, ?, ?, ?, ?, ?, 'active')''',
                 (rule_id, violator_id, officer_id, datetime.now().isoformat(), description, penalty))
        
        c.execute('UPDATE government_rules SET violations_count = violations_count + 1 WHERE id = ?',
                 (rule_id,))
        
        # Переводим денежный штраф
        self.adjust_balance(violator_id, -penalty, f"Штраф за нарушение правила №{rule_id}")
        
        conn.commit()
        conn.close()
        return True, f"✅ Нарушение зафиксировано. Штраф: ${penalty}"
    
    def get_rule_violations(self, user_id):
        """Получить нарушения пользователя"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT rv.*, gr.rule_text FROM rule_violations rv
                     JOIN government_rules gr ON rv.rule_id = gr.id
                     WHERE rv.violator_id = ? AND rv.status = 'active'
                     ORDER BY rv.violation_date DESC''', (user_id,))
        violations = c.fetchall()
        conn.close()
        return violations
    
    # ==================== ПИСЬМА И СООБЩЕНИЯ ====================
    
    def send_message(self, sender_id, recipient_id, subject, content, msg_type='private'):
        """Отправить письмо/сообщение"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO messages
                     (sender_id, recipient_id, subject, content, created_date, message_type)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                 (sender_id, recipient_id, subject, content, datetime.now().isoformat(), msg_type))
        msg_id = c.lastrowid
        conn.commit()
        conn.close()
        return msg_id
    
    def get_messages(self, user_id, folder='inbox'):
        """Получить письма пользователя"""
        conn = get_conn()
        c = conn.cursor()
        if folder == 'inbox':
            c.execute('''SELECT m.*, u.full_name FROM messages m
                         LEFT JOIN users u ON m.sender_id = u.user_id
                         WHERE m.recipient_id = ? AND m.deleted_by_recipient = 0
                         ORDER BY m.created_date DESC LIMIT 50''', (user_id,))
        else:  # sent
            c.execute('''SELECT m.*, u.full_name FROM messages m
                         LEFT JOIN users u ON m.recipient_id = u.user_id
                         WHERE m.sender_id = ? AND m.deleted_by_sender = 0
                         ORDER BY m.created_date DESC LIMIT 50''', (user_id,))
        
        messages = c.fetchall()
        conn.close()
        result = []
        for row in messages:
            result.append({
                'id': row[0],
                'sender_id': row[1],
                'recipient_id': row[2],
                'subject': row[3],
                'content': row[4],
                'created_date': row[5],
                'read_date': row[6],
                'message_type': row[7],
                'sender_name': row[11] or 'Неизвестно'
            })
        return result
    
    def mark_message_read(self, message_id, user_id):
        """Пометить письмо как прочитанное"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE messages SET read_date = ? 
                     WHERE id = ? AND recipient_id = ?''',
                 (datetime.now().isoformat(), message_id, user_id))
        conn.commit()
        conn.close()
    
    # ==================== ФБР И ПЕРЕХВАТ ====================
    
    def intercept_message(self, message_id, fbi_agent_id):
        """ФБР перехватывает письмо"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO intercepted_messages
                     (original_message_id, intercepted_by_id, intercepted_date, action)
                     VALUES (?, ?, ?, 'logged')''',
                 (message_id, fbi_agent_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_fbi_intercepted_messages(self):
        """Получить все перехванные ФБР письма"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT im.*, m.sender_id, m.recipient_id, m.subject, m.content, m.created_date,
                            u1.full_name as sender_name, u2.full_name as recipient_name
                     FROM intercepted_messages im
                     JOIN messages m ON im.original_message_id = m.id
                     LEFT JOIN users u1 ON m.sender_id = u1.user_id
                     LEFT JOIN users u2 ON m.recipient_id = u2.user_id
                     ORDER BY im.intercepted_date DESC LIMIT 100''')
        intercepts = c.fetchall()
        conn.close()
        result = []
        for row in intercepts:
            result.append({
                'intercept_id': row[0],
                'message_id': row[1],
                'intercepted_by_id': row[2],
                'intercepted_date': row[3],
                'sender_id': row[5],
                'recipient_id': row[6],
                'subject': row[7],
                'content': row[8],
                'created_date': row[9],
                'sender_name': row[10] or 'Неизвестно',
                'recipient_name': row[11] or 'Неизвестно'
            })
        return result
    
    # ==================== РЕВОЛЮЦИИ И ВОССТАНИЯ ====================
    
    def start_revolution(self, organizer_id, target_leader_id, new_gov_type, reason, supporters_needed=100):
        """Начать революцию/восстание"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO revolutions
                     (started_date, organizer_id, target_leader_id, new_government_type, 
                      supporters_count, supporters_needed, status, reason, result)
                     VALUES (?, ?, ?, ?, 0, ?, 'active', ?, 'pending')''',
                 (datetime.now().isoformat(), organizer_id, target_leader_id, new_gov_type, 
                  supporters_needed, reason))
        rev_id = c.lastrowid
        
        # Организатор - первый сторонник
        c.execute('''INSERT INTO revolution_supporters
                     (revolution_id, supporter_id, joined_date)
                     VALUES (?, ?, ?)''',
                 (rev_id, organizer_id, datetime.now().isoformat()))
        
        c.execute('UPDATE revolutions SET supporters_count = 1 WHERE id = ?', (rev_id,))
        conn.commit()
        conn.close()
        return rev_id
    
    def join_revolution(self, revolution_id, supporter_id):
        """Присоединиться к революции"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем, не участвует ли уже
        c.execute('SELECT id FROM revolution_supporters WHERE revolution_id = ? AND supporter_id = ?',
                 (revolution_id, supporter_id))
        if c.fetchone():
            conn.close()
            return False, "Вы уже присоединились к революции"
        
        c.execute('''INSERT INTO revolution_supporters
                     (revolution_id, supporter_id, joined_date)
                     VALUES (?, ?, ?)''',
                 (revolution_id, supporter_id, datetime.now().isoformat()))
        
        c.execute('UPDATE revolutions SET supporters_count = supporters_count + 1 WHERE id = ?',
                 (revolution_id,))
        
        rev = c.execute('SELECT * FROM revolutions WHERE id = ?', (revolution_id,)).fetchone()
        supporters = rev[7]  # supporters_count
        needed = rev[8]      # supporters_needed
        
        conn.commit()
        conn.close()
        
        if supporters >= needed:
            self.finish_revolution(revolution_id, True)
            return True, f"✅ Вы присоединились! Революция успешна! ({supporters}/{needed})"
        
        return True, f"✅ Вы присоединились к революции. ({supporters}/{needed})"
    
    def get_active_revolutions(self):
        """Получить активные революции"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM revolutions WHERE status = ? ORDER BY started_date DESC',
                 ('active',))
        revolutions = c.fetchall()
        conn.close()
        result = []
        for row in revolutions:
            result.append({
                'id': row[0],
                'started_date': row[1],
                'organizer_id': row[3],
                'target_leader_id': row[4],
                'new_type': row[5],
                'supporters': row[6],
                'needed': row[7],
                'reason': row[8]
            })
        return result
    
    def finish_revolution(self, revolution_id, success):
        """Завершить революцию"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT organizer_id, new_government_type FROM revolutions WHERE id = ?',
                 (revolution_id,))
        rev = c.fetchone()
        if not rev:
            conn.close()
            return False
        
        result = "successful" if success else "failed"
        c.execute('''UPDATE revolutions SET status = ?, result = ?, ended_date = ?
                     WHERE id = ?''',
                 ('finished', result, datetime.now().isoformat(), revolution_id))
        
        if success and rev[1]:  # If successful and has new government type
            self.change_government_type(rev[1], rev[0])  # Set organizer as new leader
            
            # Reward supporters
            c.execute('''SELECT supporter_id FROM revolution_supporters WHERE revolution_id = ?''',
                     (revolution_id,))
            supporters = c.fetchall()
            for sup in supporters:
                self.adjust_reputation(sup[0], 20, "Участие в успешной революции")
        
        conn.commit()
        conn.close()
        return True

    def send_org_chat_message(self, org_id, sender_id, content, msg_type='general'):
        """Отправить сообщение в чат организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO org_chat_messages
                     (org_id, sender_id, content, created_date, message_type)
                     VALUES (?, ?, ?, ?, ?)''',
                 (org_id, sender_id, content, datetime.now().isoformat(), msg_type))
        msg_id = c.lastrowid
        conn.commit()
        conn.close()
        return msg_id
    
    def get_org_chat(self, org_id, limit=50):
        """Получить сообщения из чата организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT m.*, u.full_name FROM org_chat_messages m
                     LEFT JOIN users u ON m.sender_id = u.user_id
                     WHERE m.org_id = ?
                     ORDER BY m.created_date DESC
                     LIMIT ?''', (org_id, limit))
        messages = c.fetchall()
        conn.close()
        result = []
        for row in messages:
            result.append({
                'id': row[0],
                'org_id': row[1],
                'sender_id': row[2],
                'content': row[3],
                'created_date': row[4],
                'message_type': row[5],
                'sender_name': row[6] or 'Неизвестно'
            })
        return list(reversed(result))  # Вернуть в правильном порядке (новое внизу)

    # ==================== ВЫБОРЫ ====================

    def create_election(self, creator_id, org_id, position, description, duration_hours=72):
        """Создание выборов в организации"""
        conn = get_conn()
        c = conn.cursor()

        start_date = datetime.now()
        end_date = start_date + timedelta(hours=duration_hours)

        c.execute('''INSERT INTO elections
                    (org_id, position, start_date, end_date, description, status)
                    VALUES (?, ?, ?, ?, ?, 'active')''',
                 (org_id, position, start_date.isoformat(), end_date.isoformat(), description))
        election_id = c.lastrowid
        conn.commit()
        conn.close()
        return election_id

    def get_elections(self, org_id, status='active'):
        """Получение выборов в организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM elections WHERE org_id = ? AND status = ?", (org_id, status))
        elections = c.fetchall()
        conn.close()
        return elections

    def get_election_candidates(self, election_id):
        """Получение кандидатов на выборах"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ec.*, u.full_name
                     FROM election_candidates ec
                     JOIN users u ON ec.candidate_id = u.user_id
                     WHERE ec.election_id = ?''', (election_id,))
        candidates = c.fetchall()
        conn.close()
        result = []
        for cand in candidates:
            result.append({
                'id': cand[0],
                'election_id': cand[1],
                'candidate_id': cand[2],
                'votes': cand[3],
                'program': cand[4],
                'full_name': cand[6]
            })
        return result

    def nominate_candidate(self, election_id, user_id, program):
        """Выдвижение кандидатуры на выборах"""
        conn = get_conn()
        c = conn.cursor()

        # Проверка, не кандидат ли уже
        c.execute("SELECT id FROM election_candidates WHERE election_id = ? AND candidate_id = ?", (election_id, user_id))
        if c.fetchone():
            conn.close()
            return False, "Вы уже являетесь кандидатом на этих выборах."

        c.execute('''INSERT INTO election_candidates
                    (election_id, candidate_id, program)
                    VALUES (?, ?, ?)''', (election_id, user_id, program))
        conn.commit()
        conn.close()
        return True, "Вы успешно выдвинули свою кандидатуру."

    def vote(self, election_id, voter_id, candidate_id):
        """Голосование на выборах"""
        conn = get_conn()
        c = conn.cursor()

        try:
            c.execute('''INSERT INTO election_votes (election_id, voter_id, candidate_id, vote_date)
                         VALUES (?, ?, ?, ?)''', (election_id, voter_id, candidate_id, datetime.now().isoformat()))
            c.execute("UPDATE election_candidates SET votes = votes + 1 WHERE election_id = ? AND candidate_id = ?", (election_id, candidate_id))
            conn.commit()
            conn.close()
            return True, "Ваш голос учтен."
        except sqlite3.IntegrityError:
            conn.close()
            return False, "Вы уже голосовали на этих выборах."

    def get_election(self, election_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM elections WHERE id = ?", (election_id,))
        election = c.fetchone()
        columns = [description[0] for description in c.description]
        conn.close()
        if election:
            return dict(zip(columns, election))
        return None
    
    def start_presidential_election(self, duration_hours=30):
        """Запустить выборы президента (30 часов)"""
        conn = get_conn()
        c = conn.cursor()
        
        # Получаем Правительство
        c.execute('SELECT id FROM organizations WHERE name = ?', ('Правительство',))
        gov = c.fetchone()
        if not gov:
            conn.close()
            return None
        
        gov_id = gov[0]
        
        # Проверяем нет ли уже активных выборов
        c.execute('''SELECT id FROM elections 
                     WHERE org_id = ? AND position = ? AND status = ?''',
                 (gov_id, 'President', 'active'))
        if c.fetchone():
            conn.close()
            return None  # Выборы уже идут
        
        start_date = datetime.now()
        end_date = start_date + timedelta(hours=duration_hours)
        
        c.execute('''INSERT INTO elections
                    (org_id, position, start_date, end_date, status)
                    VALUES (?, ?, ?, ?, 'active')''',
                 (gov_id, 'President', start_date.isoformat(), end_date.isoformat()))
        election_id = c.lastrowid
        conn.commit()
        conn.close()
        return election_id
    
    def check_and_start_initial_election(self):
        """Проверить и запустить инициальные выборы при начале игры"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем, были ли уже выборы президента когда-либо
        c.execute('SELECT COUNT(*) FROM elections WHERE position = ?', ('President',))
        has_elections = c.fetchone()[0] > 0
        conn.close()
        
        if not has_elections:
            # Запускаем первые выборы на 30 часов
            return self.start_presidential_election(duration_hours=30)
        return None
    
    def appoint_to_position(self, president_id, org_id, user_id, position, salary=0):
        """Президент назначает человека на должность"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем, что президент действительно лидер организации
        c.execute('''SELECT role FROM organization_members 
                     WHERE org_id = ?
                     AND user_id = ?''', (org_id, president_id))
        pres = c.fetchone()
        if not pres or pres[0] not in ['President', 'Лидер', 'Президент', 'Глава']:
            conn.close()
            return False, "❌ Только лидер организации может назначать на должности"
        
        # Проверяем, в какой организации уже состоит пользователь
        c.execute('SELECT org_id FROM organization_members WHERE user_id = ?', (user_id,))
        existing = c.fetchone()
        if existing:
            # Удаляем из старой организации
            c.execute('DELETE FROM organization_members WHERE user_id = ?', (user_id,))
        
        # Добавляем в новую организацию
        c.execute('''INSERT INTO organization_members
                     (org_id, user_id, role, salary, join_date, performance, rank)
                     VALUES (?, ?, ?, ?, ?, 100, 1)''',
                 (org_id, user_id, position, salary, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        return True, f"✅ ✨ **{user_id}** назначен на должность **{position}**!"

    def tally_election(self, election_id):
        """Подсчет голосов и завершение выборов"""
        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT * FROM elections WHERE id = ?", (election_id,))
        election = self.get_election(election_id)
        if not election or election['status'] != 'active':
            conn.close()
            return

        # Находим победителя
        c.execute("SELECT * FROM election_candidates WHERE election_id = ? ORDER BY votes DESC LIMIT 1", (election_id,))
        winner = c.fetchone()

        if winner:
            winner_id = winner[2]
            # Обновляем лидера организации
            c.execute("UPDATE organizations SET leader_id = ? WHERE id = ?", (winner_id, election['org_id']))
            c.execute("UPDATE elections SET status = 'finished', winner_id = ? WHERE id = ?", (winner_id, election_id))
            conn.commit()
            conn.close()

            org = self.get_organization_by_id(election['org_id'])
            winner_user = self.get_user(winner_id)
            self.send_notification(winner_id, 0, "Вы победили на выборах!", f"Вы избраны на должность {election['position']} в организации {org['name']}.")
        else:
            # Нет кандидатов или голосов
            c.execute("UPDATE elections SET status = 'finished' WHERE id = ?", (election_id,))
            conn.commit()
            conn.close()


    # ==================== ДОКЛАДЫ И ОТЧЕТЫ ====================

    def submit_report(self, org_id, author_id, content, title="Доклад", report_type="statement"):
        """Подача доклада в организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO organization_reports
                    (org_id, author_id, title, content, report_type, date, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'published')''',
                 (org_id, author_id, title, content, report_type, datetime.now().isoformat()))
        report_id = c.lastrowid
        conn.commit()
        conn.close()
        return report_id

    def get_reports(self, org_id):
        """Получение докладов организации"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT r.id, r.org_id, r.author_id, r.title, r.content, r.report_type, r.date, r.status, u.full_name
                     FROM organization_reports r
                     JOIN users u ON r.author_id = u.user_id
                     WHERE r.org_id = ?
                     ORDER BY r.date DESC''', (org_id,))
        reports = c.fetchall()
        conn.close()
        result = []
        for report in reports:
            result.append({
                'id': report[0],
                'org_id': report[1],
                'author_id': report[2],
                'title': report[3] or 'Доклад',
                'content': report[4],
                'report_type': report[5] or 'statement',
                'date': report[6],
                'status': report[7],
                'author_name': report[8]
            })
        return result



    def approve_loan_request(self, officer_id, loan_id):
        """Одобрение заявки на кредит"""
        conn = get_conn()
        c = conn.cursor()

        c.execute('SELECT * FROM loans WHERE id = ? AND status = "pending"', (loan_id,))
        loan = c.fetchone()
        if not loan:
            conn.close()
            return False, "❌ Заявка не найдена или уже обработана.", None

        applicant_id = loan[1]
        amount = loan[3]
        term_months = loan[5]
        purpose = loan[7]

        officer_org = self.get_user_organization(officer_id)
        if not officer_org or officer_org['name'] != 'Банк':
            conn.close()
            return False, "❌ У вас нет полномочий для одобрения кредитов!", None

        interest_rate, monthly_payment, due_date = self._calculate_loan_terms(applicant_id, amount, term_months)
        daily_payment = monthly_payment / 30.0
        now_iso = datetime.now().isoformat()

        c.execute('''UPDATE loans
                     SET bank_officer_id = ?, interest_rate = ?, monthly_payment = ?,
                         approval_date = ?, due_date = ?, remaining_balance = ?, status = "active",
                         daily_payment = ?, last_payment_date = ?
                     WHERE id = ?''',
                  (officer_id, interest_rate, monthly_payment,
                   now_iso, due_date.isoformat(), amount, daily_payment, now_iso, loan_id))

        applicant = self.get_user(applicant_id)
 
        conn.commit()
        conn.close()
 
        if applicant:
            self.update_user(applicant_id, balance=applicant.get('balance', 0) + amount)

        info = {
            "applicant_id": applicant_id,
            "amount": amount,
            "term_months": term_months,
            "interest_rate": interest_rate,
            "monthly_payment": monthly_payment,
            "purpose": purpose
        }

        return True, "✅ Кредит одобрен.", info

    def reject_loan_request(self, officer_id, loan_id, reason=None):
        """Отклонение заявки на кредит"""
        conn = get_conn()
        c = conn.cursor()

        c.execute('SELECT * FROM loans WHERE id = ? AND status = "pending"', (loan_id,))
        loan = c.fetchone()
        if not loan:
            conn.close()
            return False, "❌ Заявка не найдена или уже обработана.", None

        officer_org = self.get_user_organization(officer_id)
        if not officer_org or officer_org['name'] != 'Банк':
            conn.close()
            return False, "❌ У вас нет полномочий для отклонения кредитов!", None

        applicant_id = loan[1]
        c.execute('''UPDATE loans
                     SET bank_officer_id = ?, status = "rejected"
                     WHERE id = ?''',
                  (officer_id, loan_id))

        conn.commit()
        conn.close()

        return True, reason or "❌ Кредит отклонён.", {"applicant_id": applicant_id}
    
    def create_org_task(self, org_id, creator_id, title, description, reward, deadline_days):
        """Создание задания в организации"""
        conn = get_conn()
        c = conn.cursor()
        
        deadline = datetime.now() + timedelta(days=deadline_days)
        
        c.execute('''INSERT INTO org_tasks 
                    (org_id, creator_id, title, description, reward, deadline, status, created_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (org_id, creator_id, title, description, reward, deadline.isoformat(), 
                  'active', datetime.now().isoformat()))
        
        task_id = c.lastrowid
        
        conn.commit()
        conn.close()
        
        # Уведомляем членов организации
        members = self.get_organization_members(org_id)
        for member in members:
            self.send_notification(
                member['user_id'],
                creator_id,
                "📋 НОВОЕ ЗАДАНИЕ В ОРГАНИЗАЦИИ",
                f"Задание: {title}\nОписание: {description}\nНаграда: ${reward}\nДедлайн: {deadline.strftime('%d.%m.%Y')}"
            )
        
        return True, f"✅ Задание создано! ID задания: {task_id}"
    
    def complete_task(self, task_id, completer_id):
        """Завершение задания"""
        conn = get_conn()
        c = conn.cursor()
        
        # Получаем информацию о задании
        c.execute('SELECT org_id, reward, creator_id FROM org_tasks WHERE id = ? AND status = "active"', (task_id,))
        task = c.fetchone()
        
        if not task:
            conn.close()
            return False, "❌ Задание не найдено или уже завершено!"
        
        org_id, reward, creator_id = task
        
        # Обновляем статус задания
        c.execute('''UPDATE org_tasks 
                    SET status = "completed", assigned_to = ?, completed_date = ?
                    WHERE id = ?''',
                 (completer_id, datetime.now().isoformat(), task_id))
        
        # Обновляем статистику выполнившего
        c.execute('''UPDATE organization_members 
                    SET tasks_completed = tasks_completed + 1, 
                        experience = experience + 10,
                        performance = CASE WHEN performance + 5 > 100 THEN 100 ELSE performance + 5 END
                    WHERE user_id = ? AND org_id = ?''',
                 (completer_id, org_id))
        
        # Выплачиваем награду
        completer = self.get_user(completer_id)
        
        conn.commit()
        conn.close()
        
        if completer:
            self.update_user(
                completer_id,
                balance=completer.get('balance', 0) + reward
            )
        
        # Уведомляем создателя
        self.send_notification(
            creator_id,
            completer_id,
            "✅ ЗАДАНИЕ ВЫПОЛНЕНО",
            f"Задание #{task_id} выполнено пользователем {completer.get('full_name', 'Неизвестно')}"
        )
        
        return True, f"✅ Задание выполнено! Вы получили ${reward} и +10 опыта в организации."

    # ==================== ЗАДАНИЯ ДЛЯ НОВИЧКОВ ====================

    def assign_starter_tasks(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM player_tasks WHERE user_id = ?', (user_id,))
        if c.fetchone()[0] > 0:
            conn.close()
            return

        tasks = [
            ("open_orgs", "Откройте меню организаций", "Посмотрите список гос. организаций", 1, 500),
            ("apply_org", "Подайте заявку в организацию", "Выберите организацию и отправьте заявку", 1, 800),
            ("open_biz", "Откройте список бизнесов", "Посмотрите доступные бизнесы", 1, 400),
            ("loan_request", "Подайте заявку на кредит", "Оформите кредит в банке", 1, 700),
            ("open_priv", "Откройте частные организации", "Посмотрите список частных организаций", 1, 400),
        ]

        for code, title, desc, goal, reward in tasks:
            c.execute('''INSERT INTO player_tasks
                        (user_id, task_code, title, description, goal, reward, assigned_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, code, title, desc, goal, reward, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def list_player_tasks(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT task_code, title, description, status, progress, goal, reward
                     FROM player_tasks WHERE user_id = ? ORDER BY id ASC''', (user_id,))
        rows = c.fetchall()
        conn.close()
        return [{
            'code': r[0],
            'title': r[1],
            'description': r[2],
            'status': r[3],
            'progress': r[4],
            'goal': r[5],
            'reward': r[6]
        } for r in rows]

    def mark_task_progress(self, user_id, task_code, amount=1):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, progress, goal, status, reward
                     FROM player_tasks WHERE user_id = ? AND task_code = ?''',
                  (user_id, task_code))
        row = c.fetchone()
        if not row:
            conn.close()
            return

        task_id, progress, goal, status, reward = row
        if status != 'active':
            conn.close()
            return

        new_progress = progress + amount
        completed = False
        if new_progress >= goal:
            completed = True
            c.execute('''UPDATE player_tasks
                         SET progress = ?, status = 'claimed', completed_date = ?
                         WHERE id = ?''',
                      (goal, datetime.now().isoformat(), task_id))
        else:
            c.execute('''UPDATE player_tasks SET progress = ? WHERE id = ?''',
                      (new_progress, task_id))
 
        conn.commit()
        conn.close()
 
        if completed:
            user = self.get_user(user_id) or {}
            self.update_user(user_id, balance=user.get('balance', 0) + reward)

    # ==================== ЭКОНОМИКА БИЗНЕСОВ ====================

    def collect_business_income(self, business_id, owner_id):
        biz = self.get_business(business_id)
        if not biz or biz['owner_id'] != owner_id:
            return False, "❌ Нет доступа."

        last_date = biz.get('last_income_date')
        today = datetime.now().date().isoformat()
        if last_date == today:
            return False, "⏳ Прибыль уже начислялась сегодня."

        income = biz.get('income_daily', 800)
        expense = biz.get('expense_daily', 300)
        profit = max(0, income - expense)

        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE businesses
                     SET budget = budget + ?, last_income_date = ?
                     WHERE id = ?''', (profit, today, business_id))
        conn.commit()
        conn.close()

        # владельцу бонус 20%
        owner = self.get_user(owner_id) or {}
        self.update_user(owner_id, balance=owner.get('balance', 0) + int(profit * 0.2))
        return True, f"✅ Прибыль начислена. Чистая прибыль: ${profit}. Владелец получил ${int(profit*0.2)}."

    # ==================== НЕДВИЖИМОСТЬ ====================

    def list_properties(self):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT p.id, p.name, p.price, p.rent, p.location,
                            p.category, COALESCE(p.condition, 100), COALESCE(p.maintenance_daily, 0),
                            (SELECT owner_id FROM property_ownership po WHERE po.property_id = p.id) AS owner_id,
                            pf.facility_type, pf.facility_id
                     FROM properties p
                     LEFT JOIN property_facilities pf ON pf.property_id = p.id
                     ORDER BY p.id ASC''')
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'name': r[1],
            'price': r[2],
            'rent': r[3],
            'location': r[4],
            'category': r[5],
            'condition': r[6],
            'maintenance_daily': r[7],
            'owner_id': r[8],
            'facility_type': r[9],
            'facility_id': r[10],
        } for r in rows]

    def get_property(self, property_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT p.id, p.name, p.price, p.rent, p.location,
                            p.category, COALESCE(p.condition, 100), COALESCE(p.maintenance_daily, 0),
                            (SELECT owner_id FROM property_ownership po WHERE po.property_id = p.id) AS owner_id,
                            pf.facility_type, pf.facility_id
                     FROM properties p
                     LEFT JOIN property_facilities pf ON pf.property_id = p.id
                     WHERE p.id = ?''', (property_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'name': row[1],
            'price': row[2],
            'rent': row[3],
            'location': row[4],
            'category': row[5],
            'condition': row[6],
            'maintenance_daily': row[7],
            'owner_id': row[8],
            'facility_type': row[9],
            'facility_id': row[10],
        }

    def buy_property(self, property_id, user_id):
        prop = self.get_property(property_id)
        if not prop:
            return False, "❌ Объект не найден."
        if prop['owner_id']:
            return False, "❌ Объект уже куплен."

        user = self.get_user(user_id) or {}
        if user.get('balance', 0) < prop['price']:
            return False, "❌ Недостаточно средств."

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO property_ownership
                     (property_id, owner_id, acquired_date)
                     VALUES (?, ?, ?)''',
                  (property_id, user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        self.update_user(user_id, balance=user.get('balance', 0) - prop['price'], property_owner=1)
        self.adjust_reputation(user_id, 0.6, "Покупка недвижимости")
        return True, "✅ Недвижимость куплена!"

    def collect_rent(self, property_id, user_id):
        prop = self.get_property(property_id)
        if not prop or prop['owner_id'] != user_id:
            return False, "❌ Нет доступа."

        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT last_rent_claimed FROM property_ownership
                     WHERE property_id = ? AND owner_id = ?''', (property_id, user_id))
        row = c.fetchone()
        last_claim = row[0] if row else None
        today = datetime.now().date().isoformat()
        if last_claim == today:
            conn.close()
            return False, "⏳ Аренда уже получена сегодня."

        c.execute('''UPDATE property_ownership
                     SET last_rent_claimed = ?
                     WHERE property_id = ? AND owner_id = ?''', (today, property_id, user_id))
        conn.commit()
        conn.close()

        user = self.get_user(user_id) or {}
        self.update_user(user_id, balance=user.get('balance', 0) + prop['rent'])
        return True, f"✅ Аренда получена: ${prop['rent']}."

    # ==================== КОНТРАКТЫ ====================

    def create_contract(self, creator_id, title, description, reward, category='general', priority='normal'):
        creator = self.get_user(creator_id) or {}
        reward = float(reward or 0)
        if reward <= 0:
            return False, "❌ Награда должна быть больше 0.", None
        balance = float(creator.get('balance', 0) or 0)
        if balance < reward:
            return False, f"❌ Недостаточно средств для эскроу. Нужно ${reward:,.0f}.", None

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO contracts
                    (creator_id, title, description, reward, status, created_date, escrow_reserved, category, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (creator_id, title, description, reward, 'open', datetime.now().isoformat(), reward, category, priority))
        contract_id = c.lastrowid
        conn.commit()
        conn.close()
        self.update_user(creator_id, balance=balance - reward)
        return True, "✅ Контракт создан, оплата зарезервирована в эскроу.", contract_id

    def list_open_contracts(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, title, reward, status FROM contracts
                     WHERE status = 'open' ORDER BY id DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_contract(self, contract_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM contracts WHERE id = ?', (contract_id,))
        row = c.fetchone()
        conn.close()
        return row

    def accept_contract(self, contract_id, user_id):
        contract = self.get_contract(contract_id)
        if not contract or contract[5] != 'open':
            return False, "❌ Контракт недоступен."
        if contract[1] == user_id:
            return False, "❌ Нельзя принимать собственный контракт."
        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE contracts SET status = 'in_progress', accepted_by = ?
                     WHERE id = ?''', (user_id, contract_id))
        conn.commit()
        conn.close()
        return True, "✅ Контракт принят."

    def complete_contract(self, contract_id, creator_id):
        contract = self.get_contract(contract_id)
        if not contract or contract[5] != 'in_progress' or contract[1] != creator_id:
            return False, "❌ Нельзя завершить этот контракт."

        reward = float(contract[4] or 0)
        accepted_by = contract[6]
        escrow_reserved = float(contract[9] or 0) if len(contract) > 9 else 0
        payout = min(reward, escrow_reserved)
        if payout <= 0:
            return False, "❌ По контракту не зарезервирована оплата."

        worker = self.get_user(accepted_by) or {}
        self.update_user(accepted_by, balance=float(worker.get('balance', 0) or 0) + payout)

        conn = get_conn()
        c = conn.cursor()
        c.execute('''UPDATE contracts
                     SET status = 'completed', completed_date = ?, escrow_reserved = ?
                     WHERE id = ?''', (datetime.now().isoformat(), max(0.0, escrow_reserved - payout), contract_id))
        conn.commit()
        conn.close()
        self.adjust_reputation(accepted_by, 0.7, "Выполнение контракта")
        self.adjust_reputation(creator_id, 0.3, "Закрытие контракта")
        return True, f"✅ Контракт завершен и оплачен: ${payout:,.0f}."

    # ==================== МИТИНГИ ====================

    def create_protest(self, creator_id, title, description, location, duration_hours=24):
        creator = self.get_user(creator_id) or {}
        if float(creator.get('reputation', 50) or 50) < 15:
            return False, "❌ Слишком низкая репутация для организации митинга.", None

        duration_hours = max(4, min(72, int(duration_hours or 24)))
        created_at = datetime.now()
        end_at = created_at + timedelta(hours=duration_hours)

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO protests
                    (creator_id, title, description, location, status, support_count, against_count, created_date, end_date)
                    VALUES (?, ?, ?, ?, 'active', 0, 0, ?, ?)''',
                 (creator_id, title, description, location, created_at.isoformat(), end_at.isoformat()))
        protest_id = c.lastrowid
        c.execute('''INSERT OR IGNORE INTO protest_participants
                     (protest_id, user_id, stance, join_date)
                     VALUES (?, ?, 'support', ?)''',
                  (protest_id, creator_id, created_at.isoformat()))
        c.execute('UPDATE protests SET support_count = support_count + 1 WHERE id = ?', (protest_id,))
        conn.commit()
        conn.close()

        self.adjust_reputation(creator_id, 0.5, "Организация митинга")
        return True, "✅ Митинг создан.", protest_id

    def list_protests(self, status='active', limit=20):
        conn = get_conn()
        c = conn.cursor()
        if status:
            c.execute('''SELECT id, title, location, status, support_count, against_count, end_date
                         FROM protests
                         WHERE status = ?
                         ORDER BY id DESC
                         LIMIT ?''', (status, limit))
        else:
            c.execute('''SELECT id, title, location, status, support_count, against_count, end_date
                         FROM protests
                         ORDER BY id DESC
                         LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            'id': r[0],
            'title': r[1],
            'location': r[2],
            'status': r[3],
            'support_count': r[4],
            'against_count': r[5],
            'end_date': r[6],
        } for r in rows]

    def get_protest(self, protest_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM protests WHERE id = ?', (protest_id,))
        row = c.fetchone()
        columns = [col[0] for col in c.description] if c.description else []
        conn.close()
        if not row:
            return None
        return dict(zip(columns, row))

    def join_protest(self, protest_id, user_id, stance='support'):
        stance = 'against' if str(stance).lower() == 'against' else 'support'
        protest = self.get_protest(protest_id)
        if not protest or protest.get('status') != 'active':
            return False, "❌ Митинг недоступен."

        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO protest_participants
                         (protest_id, user_id, stance, join_date)
                         VALUES (?, ?, ?, ?)''',
                      (protest_id, user_id, stance, datetime.now().isoformat()))
        except sqlite3.IntegrityError:
            conn.close()
            return False, "❌ Вы уже участвуете в этом митинге."

        if stance == 'support':
            c.execute('UPDATE protests SET support_count = support_count + 1 WHERE id = ?', (protest_id,))
            rep_delta = 0.2
        else:
            c.execute('UPDATE protests SET against_count = against_count + 1 WHERE id = ?', (protest_id,))
            rep_delta = -0.1
        conn.commit()
        conn.close()

        self.adjust_reputation(user_id, rep_delta, f"Участие в митинге #{protest_id}")
        return True, "✅ Ваш голос учтен."

    # ==================== ГРАЖДАНСКИЕ РАБОТЫ ====================

    def list_citizen_jobs(self):
        return [
            {'code': 'courier', 'title': 'Курьер', 'salary': 800, 'edu_required': 2, 'rep_required': 35},
            {'code': 'taxi', 'title': 'Таксист', 'salary': 1100, 'edu_required': 3, 'rep_required': 45},
            {'code': 'builder', 'title': 'Строитель', 'salary': 1300, 'edu_required': 3, 'rep_required': 50},
            {'code': 'clerk', 'title': 'Офисный сотрудник', 'salary': 900, 'edu_required': 4, 'rep_required': 60},
            {'code': 'mechanic', 'title': 'Механик', 'salary': 1250, 'edu_required': 5, 'rep_required': 70},
        ]

    def get_citizen_job(self, job_code):
        jobs = {j['code']: j for j in self.list_citizen_jobs()}
        return jobs.get(job_code)

    def is_hr_reviewer(self, user_id):
        user_org = self.get_user_organization(user_id)
        return bool(user_org and user_org.get('name') == 'Правительство')

    def get_user_pending_job_application(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, job_code, job_title, expected_salary, applied_date
                     FROM job_applications
                     WHERE user_id = ? AND status = 'pending'
                     ORDER BY id DESC
                     LIMIT 1''', (user_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'job_code': row[1],
            'job_title': row[2],
            'expected_salary': row[3],
            'applied_date': row[4],
        }

    def apply_for_citizen_job(self, user_id, job_code, application_text):
        job = self.get_citizen_job(job_code)
        if not job:
            return False, "❌ Работа не найдена.", None

        user = self.get_user(user_id) or {}
        if user.get('citizen_job'):
            return False, "❌ У вас уже есть гражданская работа.", None

        pending = self.get_user_pending_job_application(user_id)
        if pending:
            return False, "📭 У вас уже есть активная HR-заявка.", None

        user_edu = int(user.get('education', 1) or 1)
        user_rep = float(user.get('reputation', 50) or 50)
        if user_edu < int(job.get('edu_required', 1)):
            return False, f"❌ Нужно образование {job['edu_required']}+.", None
        if user_rep < float(job.get('rep_required', 0)):
            return False, f"❌ Нужно репутации {int(job['rep_required'])}+.", None

        text = (application_text or "").strip()
        if len(text) < 16:
            return False, "❌ Заявка слишком короткая. Нужна более подробная мотивация (16+).", None

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO job_applications
                     (user_id, job_code, job_title, expected_salary, application_text, status, applied_date)
                     VALUES (?, ?, ?, ?, ?, 'pending', ?)''',
                  (user_id, job['code'], job['title'], float(job['salary']), text, datetime.now().isoformat()))
        app_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ HR-заявка отправлена на проверку кадровому отделу.", app_id

    def get_pending_job_applications(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ja.id, ja.user_id, ja.job_code, ja.job_title, ja.expected_salary,
                            ja.application_text, ja.applied_date, u.full_name, u.education, u.reputation
                     FROM job_applications ja
                     LEFT JOIN users u ON ja.user_id = u.user_id
                     WHERE ja.status = 'pending'
                     ORDER BY ja.applied_date ASC
                     LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_id': row[1],
                'job_code': row[2],
                'job_title': row[3],
                'expected_salary': float(row[4] or 0),
                'application_text': row[5] or '',
                'applied_date': row[6],
                'full_name': row[7] or 'Неизвестно',
                'education': int(row[8] or 1),
                'reputation': float(row[9] or 50),
            })
        return result

    def assign_citizen_job(self, user_id, job_code):
        job = self.get_citizen_job(job_code)
        if not job:
            return False, "❌ Работа не найдена."
        self.update_user(user_id, citizen_job=job['title'], citizen_salary=job['salary'])
        self.adjust_reputation(user_id, 0.3, f"Трудоустройство: {job['title']}")
        return True, f"✅ Вы устроились на работу: {job['title']} (${job['salary']}/мес)."

    def process_job_application(self, application_id, reviewer_id, decision, note=None):
        if not self.is_hr_reviewer(reviewer_id):
            return False, "❌ Нет доступа к кадровым решениям.", None

        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT user_id, job_code, job_title, expected_salary, status
                     FROM job_applications
                     WHERE id = ?''', (application_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ HR-заявка не найдена.", None

        user_id, _job_code, job_title, expected_salary, status = row
        if status != 'pending':
            conn.close()
            return False, "ℹ️ Заявка уже обработана.", user_id

        if decision == 'approve':
            user = self.get_user(user_id) or {}
            if user.get('citizen_job'):
                c.execute('''UPDATE job_applications
                             SET status = 'rejected', reviewed_by = ?, reviewed_date = ?, review_note = ?
                             WHERE id = ?''',
                          (reviewer_id, datetime.now().isoformat(), "У кандидата уже есть работа.", application_id))
                conn.commit()
                conn.close()
                return False, "❌ Кандидат уже трудоустроен.", user_id

            c.execute('''UPDATE users
                         SET citizen_job = ?, citizen_salary = ?
                         WHERE user_id = ?''',
                      (job_title, float(expected_salary or 0), user_id))
            c.execute('''UPDATE job_applications
                         SET status = 'approved', reviewed_by = ?, reviewed_date = ?, review_note = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), note or 'Одобрено отделом кадров', application_id))
            conn.commit()
            conn.close()
            self.adjust_reputation(user_id, 0.3, f"Трудоустройство через HR: {job_title}")
            return True, f"✅ Заявка одобрена. Игрок принят на должность {job_title}.", user_id

        c.execute('''UPDATE job_applications
                     SET status = 'rejected', reviewed_by = ?, reviewed_date = ?, review_note = ?
                     WHERE id = ?''',
                  (reviewer_id, datetime.now().isoformat(), note or 'Отклонено отделом кадров', application_id))
        conn.commit()
        conn.close()
        return True, "❌ Заявка отклонена.", user_id

    def work_citizen_shift(self, user_id):
        user = self.get_user(user_id) or {}
        salary_month = float(user.get('citizen_salary', 0) or 0)
        job_name = user.get('citizen_job')
        if not job_name or salary_month <= 0:
            return False, "❌ У вас нет гражданской работы."

        today = datetime.now().date().isoformat()
        if (user.get('last_job_shift') or '').startswith(today):
            return False, "⏳ Смена на сегодня уже выполнена."

        pay = salary_month / 30.0
        self.update_user(
            user_id,
            balance=float(user.get('balance', 0) or 0) + pay,
            last_job_shift=datetime.now().isoformat()
        )
        self.adjust_reputation(user_id, 0.1, f"Рабочая смена: {job_name}")
        return True, f"✅ Смена отработана. Выплата: ${pay:,.0f}."

    # ==================== ОБРАЗОВАНИЕ ====================

    def list_education_programs(self, only_active=True):
        conn = get_conn()
        c = conn.cursor()
        if only_active:
            c.execute('''SELECT id, name, description, duration_days, tuition_fee, min_education, min_reputation, active
                         FROM education_programs
                         WHERE active = 1
                         ORDER BY id ASC''')
        else:
            c.execute('''SELECT id, name, description, duration_days, tuition_fee, min_education, min_reputation, active
                         FROM education_programs
                         ORDER BY id ASC''')
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'name': row[1],
                'description': row[2] or '',
                'duration_days': int(row[3] or 14),
                'tuition_fee': float(row[4] or 0),
                'min_education': int(row[5] or 1),
                'min_reputation': float(row[6] or 0),
                'active': int(row[7] or 0),
            })
        return result

    def get_education_program(self, program_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT id, name, description, duration_days, tuition_fee, min_education, min_reputation, active
                     FROM education_programs
                     WHERE id = ?''', (program_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'name': row[1],
            'description': row[2] or '',
            'duration_days': int(row[3] or 14),
            'tuition_fee': float(row[4] or 0),
            'min_education': int(row[5] or 1),
            'min_reputation': float(row[6] or 0),
            'active': int(row[7] or 0),
        }

    def is_teacher_reviewer(self, user_id):
        # Check if user is in University organization
        user_org = self.get_user_organization(user_id)
        if user_org and user_org.get('name') == 'Университет':
            return True
        
        # Check if user has approved teacher application
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT id FROM teacher_applications WHERE user_id = ? AND status = ?', (user_id, 'approved'))
        result = c.fetchone()
        conn.close()
        return bool(result)

    def apply_for_teacher_position(self, user_id, application_text):
        """Подать заявку на должность преподавателя"""
        conn = get_conn()
        c = conn.cursor()
        
        # Проверяем, есть ли уже заявка
        c.execute('SELECT id, status FROM teacher_applications WHERE user_id = ?', (user_id,))
        existing = c.fetchone()
        if existing:
            conn.close()
            if existing[1] == 'pending':
                return False, "❌ У вас уже есть активная заявка на должность преподавателя."
            elif existing[1] == 'approved':
                return False, "❌ Вы уже являетесь преподавателем."
        
        user = self.get_user(user_id)
        if not user:
            conn.close()
            return False, "❌ Пользователь не найден."
        
        # Требования: образование 3+, репутация 50+
        user_edu = int(user.get('education', 1) or 1)
        user_rep = float(user.get('reputation', 50) or 50)
        
        if user_edu < 3:
            conn.close()
            return False, "❌ Требуется образование 3+. Вы сможете подать заявку после обучения."
        if user_rep < 50:
            conn.close()
            return False, "❌ Требуется репутация 50+. Улучшите вашу репутацию и попробуйте позже."
        
        text = (application_text or "").strip()
        if len(text) < 15:
            conn.close()
            return False, "❌ Заявка слишком короткая (минимум 15 символов). Опишите ваш опыт и мотивацию."
        
        c.execute('''INSERT INTO teacher_applications
                     (user_id, application_text, status, applied_date)
                     VALUES (?, ?, 'pending', ?)''',
                  (user_id, text, datetime.now().isoformat()))
        c.execute('UPDATE users SET reputation = reputation - 5 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True, "✅ Ваша заявка на должность преподавателя отправлена на рассмотрение старшим преподавателям."
    
    def get_pending_teacher_applications(self, limit=15):
        """Получить ожидающие заявки на должность преподавателя"""
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ta.id, ta.user_id, ta.application_text, ta.applied_date, u.full_name, u.education, u.reputation
                     FROM teacher_applications ta
                     LEFT JOIN users u ON u.user_id = ta.user_id
                     WHERE ta.status = 'pending'
                     ORDER BY ta.applied_date ASC
                     LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_id': row[1],
                'application_text': row[2] or '',
                'applied_date': row[3],
                'full_name': row[4] or 'Неизвестно',
                'education': int(row[5] or 1),
                'reputation': float(row[6] or 50),
            })
        return result
    
    def approve_teacher_application(self, app_id, reviewer_id):
        """Одобрить заявку на преподавателя"""
        if not self.is_teacher_reviewer(reviewer_id):
            return False, "❌ Доступ только преподавателям."
        
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT user_id FROM teacher_applications WHERE id = ? AND status = ?', (app_id, 'pending'))
        app = c.fetchone()
        if not app:
            conn.close()
            return False, "❌ Заявка не найдена или уже обработана."
        
        user_id = app[0]
        c.execute('UPDATE teacher_applications SET status = ?, reviewed_by = ?, reviewed_date = ? WHERE id = ?',
                  ('approved', reviewer_id, datetime.now().isoformat(), app_id))
        c.execute('UPDATE users SET reputation = reputation + 10 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True, f"✅ Заявка одобрена. Пользователь ID {user_id} теперь может проверять студентов."
    
    def reject_teacher_application(self, app_id, reviewer_id, reason=""):
        """Отклонить заявку на преподавателя"""
        if not self.is_teacher_reviewer(reviewer_id):
            return False, "❌ Доступ только преподавателям."
        
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT user_id FROM teacher_applications WHERE id = ? AND status = ?', (app_id, 'pending'))
        app = c.fetchone()
        if not app:
            conn.close()
            return False, "❌ Заявка не найдена или уже обработана."
        
        c.execute('UPDATE teacher_applications SET status = ?, reviewed_by = ?, reviewed_date = ?, review_note = ? WHERE id = ?',
                  ('rejected', reviewer_id, datetime.now().isoformat(), reason, app_id))
        conn.commit()
        conn.close()
        return True, "✅ Заявка отклонена."

    def get_user_pending_education_application(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ea.id, ea.program_id, ep.name, ea.applied_date
                     FROM education_applications ea
                     LEFT JOIN education_programs ep ON ep.id = ea.program_id
                     WHERE ea.user_id = ? AND ea.status = 'pending'
                     ORDER BY ea.id DESC
                     LIMIT 1''', (user_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'program_id': row[1],
            'program_name': row[2] or 'Программа',
            'applied_date': row[3],
        }

    def get_user_active_enrollment(self, user_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ee.id, ee.user_id, ee.program_id, ee.teacher_id, ee.status,
                            ee.start_date, ee.last_study_date, ee.progress_days, ee.completed_date,
                            ep.name, ep.duration_days, ep.tuition_fee
                     FROM education_enrollments ee
                     LEFT JOIN education_programs ep ON ep.id = ee.program_id
                     WHERE ee.user_id = ? AND ee.status = 'active'
                     ORDER BY ee.id DESC
                     LIMIT 1''', (user_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'id': row[0],
            'user_id': row[1],
            'program_id': row[2],
            'teacher_id': row[3],
            'status': row[4],
            'start_date': row[5],
            'last_study_date': row[6],
            'progress_days': int(row[7] or 0),
            'completed_date': row[8],
            'program_name': row[9] or 'Программа',
            'duration_days': int(row[10] or 14),
            'tuition_fee': float(row[11] or 0),
        }

    def apply_for_education(self, user_id, program_id, application_text):
        program = self.get_education_program(program_id)
        if not program or not program.get('active'):
            return False, "❌ Учебная программа недоступна.", None

        user = self.get_user(user_id) or {}
        if self.get_user_active_enrollment(user_id):
            return False, "❌ У вас уже есть активное обучение.", None
        if self.get_user_pending_education_application(user_id):
            return False, "📭 У вас уже есть заявка на обучение.", None
        if float(user.get('tax_debt', 0) or 0) > 5000:
            return False, "❌ Сначала погасите налоговый долг (долг > $5,000).", None

        user_edu = int(user.get('education', 1) or 1)
        user_rep = float(user.get('reputation', 50) or 50)
        if user_edu < int(program.get('min_education', 1)):
            return False, f"❌ Нужно образование {program['min_education']}+.", None
        if user_rep < float(program.get('min_reputation', 0)):
            return False, f"❌ Нужно репутации {int(program['min_reputation'])}+.", None

        text = (application_text or "").strip()
        if len(text) < 16:
            return False, "❌ Заявка слишком короткая. Нужна мотивация минимум 16 символов.", None

        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO education_applications
                     (user_id, program_id, application_text, status, applied_date)
                     VALUES (?, ?, ?, 'pending', ?)''',
                  (user_id, program_id, text, datetime.now().isoformat()))
        app_id = c.lastrowid
        conn.commit()
        conn.close()
        return True, "✅ Заявка на обучение отправлена преподавателям.", app_id

    def get_pending_education_applications(self, limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ea.id, ea.user_id, ea.program_id, ea.application_text, ea.applied_date,
                            ep.name, ep.duration_days, ep.tuition_fee, ep.min_education, ep.min_reputation,
                            u.full_name, u.education, u.reputation, u.balance
                     FROM education_applications ea
                     LEFT JOIN education_programs ep ON ep.id = ea.program_id
                     LEFT JOIN users u ON u.user_id = ea.user_id
                     WHERE ea.status = 'pending'
                     ORDER BY ea.applied_date ASC
                     LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_id': row[1],
                'program_id': row[2],
                'application_text': row[3] or '',
                'applied_date': row[4],
                'program_name': row[5] or 'Программа',
                'duration_days': int(row[6] or 14),
                'tuition_fee': float(row[7] or 0),
                'min_education': int(row[8] or 1),
                'min_reputation': float(row[9] or 0),
                'full_name': row[10] or 'Неизвестно',
                'education': int(row[11] or 1),
                'reputation': float(row[12] or 50),
                'balance': float(row[13] or 0),
            })
        return result

    def get_teacher_students(self, teacher_id, limit=25):
        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ee.id, ee.user_id, ee.status, ee.progress_days, ee.start_date, ee.last_study_date,
                            ep.name, ep.duration_days, u.full_name
                     FROM education_enrollments ee
                     LEFT JOIN education_programs ep ON ep.id = ee.program_id
                     LEFT JOIN users u ON u.user_id = ee.user_id
                     WHERE ee.teacher_id = ?
                     ORDER BY ee.id DESC
                     LIMIT ?''', (teacher_id, limit))
        rows = c.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_id': row[1],
                'status': row[2],
                'progress_days': int(row[3] or 0),
                'start_date': row[4],
                'last_study_date': row[5],
                'program_name': row[6] or 'Программа',
                'duration_days': int(row[7] or 14),
                'full_name': row[8] or 'Неизвестно',
            })
        return result

    def process_education_application(self, application_id, reviewer_id, decision, note=None):
        if not self.is_teacher_reviewer(reviewer_id):
            return False, "❌ Нет прав преподавателя для обработки заявок.", None

        conn = get_conn()
        c = conn.cursor()
        c.execute('''SELECT ea.user_id, ea.program_id, ea.status, ep.name, ep.duration_days, ep.tuition_fee
                     FROM education_applications ea
                     LEFT JOIN education_programs ep ON ep.id = ea.program_id
                     WHERE ea.id = ?''', (application_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "❌ Заявка не найдена.", None

        user_id, program_id, status, program_name, duration_days, tuition_fee = row
        if status != 'pending':
            conn.close()
            return False, "ℹ️ Заявка уже обработана.", user_id

        if decision == 'approve':
            active = self.get_user_active_enrollment(user_id)
            if active:
                c.execute('''UPDATE education_applications
                             SET status = 'rejected', reviewed_by = ?, reviewed_date = ?, review_note = ?
                             WHERE id = ?''',
                          (reviewer_id, datetime.now().isoformat(), 'У кандидата уже есть активное обучение.', application_id))
                conn.commit()
                conn.close()
                return False, "❌ У кандидата уже есть активное обучение.", user_id

            user = self.get_user(user_id) or {}
            balance = float(user.get('balance', 0) or 0)
            tuition_fee = float(tuition_fee or 0)
            if balance < tuition_fee:
                conn.close()
                return False, "❌ Недостаточно средств у кандидата для оплаты обучения.", user_id

            c.execute('''UPDATE users
                         SET balance = ?
                         WHERE user_id = ?''',
                      (balance - tuition_fee, user_id))
            c.execute('''UPDATE organizations
                         SET budget = budget + ?
                         WHERE name = ?''',
                      (tuition_fee, 'Университет'))
            c.execute('''INSERT INTO education_enrollments
                         (user_id, program_id, teacher_id, status, start_date, progress_days)
                         VALUES (?, ?, ?, 'active', ?, 0)''',
                      (user_id, program_id, reviewer_id, datetime.now().isoformat()))
            c.execute('''UPDATE education_applications
                         SET status = 'approved', reviewed_by = ?, reviewed_date = ?, review_note = ?
                         WHERE id = ?''',
                      (reviewer_id, datetime.now().isoformat(), note or 'Одобрено преподавателем', application_id))
            conn.commit()
            conn.close()
            self.adjust_reputation(user_id, 0.4, f"Зачисление на программу: {program_name}")
            return True, f"✅ Заявка одобрена. Кандидат зачислен на '{program_name}'.", user_id

        c.execute('''UPDATE education_applications
                     SET status = 'rejected', reviewed_by = ?, reviewed_date = ?, review_note = ?
                     WHERE id = ?''',
                  (reviewer_id, datetime.now().isoformat(), note or 'Отклонено преподавателем', application_id))
        conn.commit()
        conn.close()
        return True, "❌ Заявка отклонена.", user_id

    def study_education_day(self, user_id, choice='theory'):
        enrollment = self.get_user_active_enrollment(user_id)
        if not enrollment:
            return False, "❌ У вас нет активного обучения."

        today = datetime.now().date().isoformat()
        if (enrollment.get('last_study_date') or '').startswith(today):
            return False, "⏳ Сегодня учебная сессия уже пройдена."

        progress = int(enrollment.get('progress_days', 0) or 0) + 1
        duration = max(1, int(enrollment.get('duration_days', 14) or 14))
        conn = get_conn()
        c = conn.cursor()

        # Different study methods give different messages with emoji
        choice_messages = {
            'theory': ("📚 **Теория** - Изучение концепций и основ", "Прочитано {0} страниц лекций"),
            'practice': ("🔬 **Практика** - Практические упражнения и задачи", "Решено {0} практических заданий"),
            'group': ("👥 **Групповые занятия** - Совместное обучение с коллегами", "Участие в {0} групповых сессиях"),
        }
        choice_emoji = {
            'theory': '📚',
            'practice': '🔬', 
            'group': '👥'
        }
        
        choice_method, choice_detail = choice_messages.get(choice, choice_messages['theory'])
        emoji = choice_emoji.get(choice, '📚')

        if progress >= duration:
            c.execute('''UPDATE education_enrollments
                         SET progress_days = ?, status = 'completed', completed_date = ?, last_study_date = ?, study_choice = ?
                         WHERE id = ?''',
                      (duration, datetime.now().isoformat(), datetime.now().isoformat(), choice, enrollment['id']))
            conn.commit()
            conn.close()

            user = self.get_user(user_id) or {}
            current_edu = int(user.get('education', 1) or 1)
            new_edu = min(10, current_edu + 1)
            self.update_user(user_id, education=new_edu)
            self.adjust_reputation(
                user_id,
                EDUCATION_COMPLETION_REPUTATION_GAIN,
                f"Завершение обучения: {enrollment['program_name']}"
            )
            return True, (
                f"{emoji} **ОБУЧЕНИЕ ЗАВЕРШЕНО**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎓 {enrollment['program_name']}\n"
                f"Метод: {choice_method}\n"
                f"Новый уровень образования: {new_edu}\n"
                f"Репутация +{EDUCATION_COMPLETION_REPUTATION_GAIN}"
            )

        c.execute('''UPDATE education_enrollments
                     SET progress_days = ?, last_study_date = ?, study_choice = ?
                     WHERE id = ?''',
                  (progress, datetime.now().isoformat(), choice, enrollment['id']))
        conn.commit()
        conn.close()
        self.adjust_reputation(
            user_id,
            EDUCATION_DAILY_REPUTATION_GAIN,
            f"Учебная активность: {enrollment['program_name']}"
        )
        return True, (
            f"{emoji} **УЧЕБНАЯ СЕССИЯ ЗАВЕРШЕНА**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📘 {enrollment['program_name']}\n"
            f"Метод: {choice_method}\n"
            f"Результат: {choice_detail.format(progress)}\n"
            f"Прогресс: {progress}/{duration} дней\n"
            f"Репутация +{EDUCATION_DAILY_REPUTATION_GAIN}"
        )

    # ==================== БОНУСЫ И ОБУЧЕНИЕ ====================

    def daily_bonus(self, user_id):
        user = self.get_user(user_id) or {}
        today = datetime.now().date().isoformat()
        if user.get('last_daily_bonus') == today:
            return False, "⏳ Бонус уже получен сегодня."

        bonus = random.randint(200, 700)
        event = random.choice([
            "Город выдал субсидию.",
            "Вы получили подарок от анонимного спонсора.",
            "Удачная сделка на рынке.",
            "Ваше имя упомянули в новостях."
        ])
        self.update_user(user_id, balance=user.get('balance', 0) + bonus, last_daily_bonus=today)
        return True, f"✅ Бонус дня: ${bonus}. {event}"

# Создаем экземпляр системы
org_system = OrganizationSystem()

# ==================== ОБРАБОТЧИКИ ДЛЯ КНОПОК ====================

async def organizations_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню организаций"""
    query = update.callback_query
    
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    org_system.mark_task_progress(user_id, "open_orgs", 1)
    
    user_org = org_system.get_user_organization(user_id)
    
    menu_text = (
        "🏛️ **СИСТЕМА ГОСУДАРСТВЕННЫХ ОРГАНИЗАЦИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    menu_text += "ℹ️ *Все заявки проверяются только людьми и требуют ручного решения.*\n\n"
    
    if user_org:
        menu_text += (
            f"👥 **Ваша организация:** {user_org['name']}\n"
            f"🏷️ **Должность:** {user_org['role']}\n"
            f"💰 **Зарплата:** ${user_org['salary']}/месяц\n"
            f"📊 **Ранг:** {user_org['rank']}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
    
    menu_text += (
        "📋 **ДОСТУПНЫЕ ДЕЙСТВИЯ:**\n\n"
        "• 🏛️ **Организации** - Просмотр всех госорганизаций\n"
        "• 👥 **Моя организация** - Панель управления\n"
        "• 📊 **Статистика** - Общая статистика организаций\n"
        "• 📝 **Задания** - Доступные задания от организаций\n"
        "• 🏆 **Рейтинг** - Рейтинг лучших сотрудников\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏛️ Все организации", callback_data="orgs_list")],
        [InlineKeyboardButton("👥 Моя организация", callback_data="my_org_panel")],
        [InlineKeyboardButton("📊 Статистика", callback_data="orgs_stats")],
        [InlineKeyboardButton("📝 Задания", callback_data="org_tasks")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data="org_rating")],
        [InlineKeyboardButton("💼 Карьера", callback_data="org_career")],
        [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

async def organizations_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех организаций"""
    query = update.callback_query
    await query.answer()
    
    orgs_text = (
        "🏛️ **СПИСОК ГОСУДАРСТВЕННЫХ ОРГАНИЗАЦИЙ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    organizations = [
        ("🏛️ Правительство", "government", "Управление государством"),
        ("🚨 Полиция", "police", "Правопорядок и безопасность"),
        ("🏥 Больница", "hospital", "Медицинские услуги"),
        ("⚖️ Суд", "court", "Судебная система"),
        ("🏦 Банк", "bank", "Финансы и кредиты"),
        ("🎓 Университет", "education", "Образование и наука"),
        ("🕵️ ФБР", "fbi", "Расследования и безопасность"),
        ("🧾 Налоговая служба", "tax", "Сбор налогов и контроль долгов"),
    ]
    
    keyboard = []
    
    for org_name, org_type, org_desc in organizations:
        keyboard.append([
            InlineKeyboardButton(org_name, callback_data=f"org_view_{org_type}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 В меню организаций", callback_data="orgs_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(orgs_text, reply_markup=reply_markup, parse_mode='Markdown')

async def view_organization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр конкретной организации"""
    query = update.callback_query
    await query.answer()
    
    org_type = query.data.replace("org_view_", "")
    
    org_names = {
        'government': 'Правительство',
        'police': 'Полиция',
        'hospital': 'Больница',
        'court': 'Суд',
        'bank': 'Банк',
        'education': 'Университет',
        'fbi': 'ФБР',
        'tax': 'Налоговая служба'
    }
    
    org_name = org_names.get(org_type)
    if not org_name:
        await query.edit_message_text("❌ Организация не найдена!", reply_markup=back_markup("orgs_list", "🔙 К списку"))
        return
    
    org = org_system.get_organization(org_name)
    user_data = org_system.get_user(query.from_user.id)
    
    if not org:
        await query.edit_message_text("❌ Организация не найдена в базе данных!", reply_markup=back_markup("orgs_list", "🔙 К списку"))
        return
    
    # Получаем лидера
    leader_name = "🎭 Вакантно"
    if org['leader_id']:
        leader = org_system.get_user(org['leader_id'])
        if leader:
            leader_name = f"👑 {leader.get('full_name', 'Неизвестно')}"
    
    org_text = (
        f"{'🏛️' if org_name == 'Правительство' else '🚨' if org_name == 'Полиция' else '🏥' if org_name == 'Больница' else '⚖️' if org_name == 'Суд' else '🏦' if org_name == 'Банк' else '🎓' if org_name == 'Университет' else '🕵️' if org_name == 'ФБР' else '🧾' if org_name == 'Налоговая служба' else '🏢'} "
        f"**{org_name}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Описание:** {org['description']}\n\n"
    )
    
    if org_name == 'Университет':
        org_text += (
            "👩‍🏫 **ПРЕПОДАВАТЕЛИ**\n"
            "Члены этой организации являются преподавателями. Они могут:\n"
            "• Рассматривать заявки на обучение.\n"
            "• Управлять своими студентами.\n"
            "• Получать доход от платного обучения.\n\n"
        )

    org_text += (
        f"📊 **Статистика:**\n"
        f"• 👥 Членов: {org['members']}\n"
        f"• 💰 Бюджет: ${org['budget']:,.0f}\n"
        f"• ⭐ Репутация: {org['reputation']}/100\n"
        f"• {leader_name}\n"
        f"• 🏛️ Тип: {org['type']}\n"
        f"• 🗳️ Политика: {org['policy']}\n\n"
        
        f"📋 **Требования для вступления:**\n{org['requirements']}\n\n"
        
        f"💰 **Налоги организации:**\n"
        f"• Подоходный: {org['income_tax']*100}%\n"
        f"• Недвижимость: {org['property_tax']*100}%\n"
        f"• Бизнес: {org['business_tax']*100}%\n"
    )
    
    keyboard = []
    
    # Проверяем, является ли пользователь членом
    user_org = org_system.get_user_organization(query.from_user.id)
    
    if user_org and user_org['name'] == org_name:
        # Пользователь уже в организации
        org_text += f"\n✅ **Вы являетесь членом этой организации**\n👑 **Должность:** {user_org['role']}\n💰 **Зарплата:** ${user_org['salary']}/месяц\n🏢 **Отдел:** {user_org['department'] or 'Общий'}\n📈 **Ранг:** {user_org['rank']}"
        
        keyboard.append([InlineKeyboardButton("👥 Управление", callback_data=f"org_manage_{org_type}")])
        keyboard.append([InlineKeyboardButton("📊 Панель", callback_data=f"org_panel_{org_type}")])
        
        # Разные кнопки для разных должностей
        if user_org['role'] in ['Президент', 'Лидер', 'Директор', 'Шеф', 'Глава']:
            keyboard.append([InlineKeyboardButton("📋 Заявки", callback_data=f"org_applications_{org_type}")])
            keyboard.append([InlineKeyboardButton("👥 Персонал", callback_data=f"org_staff_{org_type}")])
        
        keyboard.append([InlineKeyboardButton("🏃 Выйти", callback_data=f"org_leave_{org_type}")])
    
    else:
        # Проверяем требования
        requirements_met = True
        missing = []
        
        # Простая проверка требований
        if 'Образование' in org['requirements']:
            import re
            edu_match = re.search(r'Образование (\d+)\+', org['requirements'])
            if edu_match:
                required_edu = int(edu_match.group(1))
                if user_data.get('education', 1) < required_edu:
                    requirements_met = False
                    missing.append(f"🎓 Образование {required_edu}+ (у вас {user_data.get('education', 1)})")
        
        if 'Репутация' in org['requirements']:
            rep_match = re.search(r'Репутация (\d+)\+', org['requirements'])
            if rep_match:
                required_rep = int(rep_match.group(1))
                if user_data.get('reputation', 50) < required_rep:
                    requirements_met = False
                    missing.append(f"⭐ Репутация {required_rep}+ (у вас {user_data.get('reputation', 50)})")
        
        if org_name == 'Полиция' and user_data.get('life_state', 'alive') != 'alive':
            requirements_met = False
            missing.append("🚑 Нельзя вступить в полицию в состоянии травмы")
        
        if requirements_met:
            org_text += f"\n✅ **Вы соответствуете требованиям для вступления!**"
            keyboard.append([InlineKeyboardButton("📝 Подать заявку", callback_data=f"org_apply_{org_type}")])
        else:
            org_text += f"\n❌ **Вы не соответствуете требованиям:**\n"
            for req in missing:
                org_text += f"• {req}\n"
    
    keyboard.append([InlineKeyboardButton("👥 Члены", callback_data=f"org_members_{org_type}")])
    keyboard.append([InlineKeyboardButton("🔙 К организациям", callback_data="orgs_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(org_text, reply_markup=reply_markup, parse_mode='Markdown')

async def apply_to_organization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подача заявки в организацию"""
    query = update.callback_query
    await query.answer()
    
    org_type = query.data.replace("org_apply_", "")
    
    org_names = {
        'government': 'Правительство',
        'police': 'Полиция',
        'hospital': 'Больница',
        'court': 'Суд',
        'bank': 'Банк',
        'education': 'Университет',
        'fbi': 'ФБР',
        'tax': 'Налоговая служба'
    }
    
    org_name = org_names.get(org_type)
    if not org_name:
        await query.edit_message_text("❌ Организация не найдена!", reply_markup=back_markup("orgs_list", "🔙 К списку"))
        return
    
    org = org_system.get_organization(org_name)
    
    context.user_data['applying_to_org'] = org['id']
    context.user_data['awaiting_application'] = True
    
    await query.edit_message_text(
        f"📝 **ПОДАЧА ЗАЯВКИ В {org_name.upper()}**\n\n"
        f"Напишите, почему вы хотите вступить в {org_name}:\n\n"
        f"💡 *Пример: \"Имею опыт работы в сфере...\", \"Хочу развивать...\", \"Могу предложить...\"*\n\n"
        f"📌 *Минимум 20 символов, максимум 500*",
        reply_markup=back_markup(f"org_view_{org_type}", "🔙 Отмена")
    )

async def process_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста заявки"""
    if 'awaiting_application' in context.user_data and update.message:
        application_text = update.message.text
        
        if len(application_text) < 20:
            await update.message.reply_text("❌ Заявка слишком короткая! Напишите хотя бы 20 символов.")
            return
        
        if len(application_text) > 500:
            await update.message.reply_text("❌ Заявка слишком длинная! Максимум 500 символов.")
            return
        
        org_id = context.user_data['applying_to_org']
        success, message = org_system.apply_to_organization(update.effective_user.id, org_id, application_text)
        
        if success:
            org = org_system.get_organization_by_id(org_id)
            org_system.mark_task_progress(update.effective_user.id, "apply_org", 1)
            
            await update.message.reply_text(
                f"✅ **ЗАЯВКА ПОДАНА!**\n\n"
                f"🏛️ **Организация:** {org['name']}\n"
                f"📝 **Ваш текст:** {application_text[:100]}...\n\n"
                f"⏳ *Заявка будет рассмотрена руководством в течение 24 часов.*\n"
                f"🔔 *Вы получите уведомление о решении.*\n\n"
                f"📌 *Статус заявки можно проверить в меню организаций*"
            )
        else:
            await update.message.reply_text(f"❌ {message}")
        
        # Очищаем состояние
        if 'awaiting_application' in context.user_data:
            del context.user_data['awaiting_application']
        if 'applying_to_org' in context.user_data:
            del context.user_data['applying_to_org']
        
        # Возвращаем в главное меню
        await organizations_main_menu(update, context)

async def organization_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель организации пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)
    
    if not user_org:
        await query.edit_message_text(
            "❌ Вы не состоите в организации!\n\n"
            "📌 *Выберите организацию и подайте заявку на вступление.*",
            reply_markup=back_markup("orgs_main", "🔙 К организациям")
        )
        return
    
    org = org_system.get_organization(user_org['name'])
    user_data = org_system.get_user(user_id)
    
    panel_text = (
        f"{'🏛️' if org['name'] == 'Правительство' else '🚨' if org['name'] == 'Полиция' else '🏥' if org['name'] == 'Больница' else '⚖️' if org['name'] == 'Суд' else '🏦' if org['name'] == 'Банк' else '🎓' if org['name'] == 'Университет' else '🕵️' if org['name'] == 'ФБР' else '🧾' if org['name'] == 'Налоговая служба' else '🏢'} "
        f"**ПАНЕЛЬ {org['name'].upper()}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"👤 **Ваш статус:**\n"
        f"• 🏷️ Должность: {user_org['role']}\n"
        f"• 💰 Зарплата: ${user_org['salary']}/месяц\n"
        f"• 🏢 Отдел: {user_org['department'] or 'Общий'}\n"
        f"• 📈 Ранг: {user_org['rank']}\n"
        f"• ⭐ Репутация в организации: {user_org.get('reputation', 50)}/100\n\n"
        
        f"📊 **Статистика организации:**\n"
        f"• 👥 Членов: {org['members']}\n"
        f"• 💰 Бюджет: ${org['budget']:,.0f}\n"
        f"• ⭐ Репутация: {org['reputation']}/100\n\n"
        
        f"🎯 **Доступные действия:**\n"
    )
    
    # Разные кнопки для разных организаций
    keyboard = []
    
    if org['name'] == 'Полиция':
        panel_text += "• 🚨 Произвести арест\n• 🕵️ Начать расследование\n• 📋 Проверить список розыска\n"
        keyboard.extend([
            [InlineKeyboardButton("🚨 Арестовать", callback_data="police_arrest")],
            [InlineKeyboardButton("🕵️ Расследование", callback_data="police_investigate")],
            [InlineKeyboardButton("📋 Список розыска", callback_data="police_wanted")]
        ])
    
    elif org['name'] == 'Больница':
        panel_text += "• 🏥 Лечить пациента\n• 📝 Поставить диагноз\n• 💊 Выписать рецепт\n"
        keyboard.extend([
            [InlineKeyboardButton("🏥 Лечить", callback_data="hospital_treat")],
            [InlineKeyboardButton("📝 Диагноз", callback_data="hospital_diagnose")],
            [InlineKeyboardButton("💊 Рецепт", callback_data="hospital_prescribe")]
        ])
    
    elif org['name'] == 'Банк':
        panel_text += "• 💳 Одобрить кредит\n• 💵 Обслужить клиента\n• 🏦 Открыть счет\n"
        keyboard.extend([
            [InlineKeyboardButton("💳 Кредит", callback_data="bank_loan")],
            [InlineKeyboardButton("💵 Обслужить", callback_data="bank_serve")],
            [InlineKeyboardButton("🏦 Счет", callback_data="bank_account")]
        ])
    
    elif org['name'] == 'Правительство':
        panel_text += "• 📜 Принять закон\n• 💰 Управление бюджетом\n• 👥 Назначить министра\n• 🗳️ Провести выборы\n"
        keyboard.extend([
            [InlineKeyboardButton("📜 Законы", callback_data="gov_laws")],
            [InlineKeyboardButton("💰 Бюджет", callback_data="gov_budget")],
            [InlineKeyboardButton("👥 Назначения", callback_data="gov_appointments")],
            [InlineKeyboardButton("🗳️ Провести выборы", callback_data="elections_create")]
        ])
    
    elif org['name'] in ['Полиция', 'Больница', 'Суд', 'Банк', 'Университет', 'ФБР', 'Налоговая служба']:
        is_leader = user_org.get('role') in ORG_MANAGER_ROLES
        if is_leader:
             panel_text += "• 🗳️ Выборы\n"
             keyboard.append([InlineKeyboardButton("🗳️ Выборы", callback_data=f"elections_list_{org['type']}")])


    elif org['name'] == 'Налоговая служба':
        panel_text += "• 🧾 Отчет по долгам\n• 🔄 Запустить налоговый цикл\n"
        keyboard.extend([
            [InlineKeyboardButton("🧾 Долги и сборы", callback_data="tax_report")],
            [InlineKeyboardButton("🔄 Применить цикл", callback_data="tax_cycle")]
        ])
    
    # Общие кнопки для всех организаций
    keyboard.extend([
        [InlineKeyboardButton("📝 Доклады и отчеты", callback_data=f"reports_list_{org['type']}" if user_org.get('role') in ORG_MANAGER_ROLES else "report_create")],
        [InlineKeyboardButton("📝 Задания", callback_data="org_tasks_view")],
        [InlineKeyboardButton("👥 Коллеги", callback_data="org_colleagues")],
        [InlineKeyboardButton("📊 Статистика", callback_data="org_stats_detailed")],
        [InlineKeyboardButton("💼 Карьера", callback_data="org_career_path")],
        [InlineKeyboardButton("🔙 В меню", callback_data="orgs_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(panel_text, reply_markup=reply_markup, parse_mode='Markdown')

ORG_TYPE_NAMES = {
    'government': 'Правительство',
    'police': 'Полиция',
    'hospital': 'Больница',
    'court': 'Суд',
    'bank': 'Банк',
    'education': 'Университет',
    'fbi': 'ФБР',
    'tax': 'Налоговая служба',
}

ORG_MANAGER_ROLES = {'Президент', 'Лидер', 'Директор', 'Шеф', 'Глава', 'Руководитель', 'Заместитель'}


async def organization_manage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    org_type = query.data.replace("org_manage_", "")
    org_name = ORG_TYPE_NAMES.get(org_type)
    user_org = org_system.get_user_organization(query.from_user.id)

    if not org_name or not user_org or user_org['type'] != org_type:
        await query.edit_message_text(
            "❌ Управление доступно только для вашей организации.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")]])
        )
        return

    is_manager = user_org['role'] in ORG_MANAGER_ROLES
    text = (
        f"🛠️ **УПРАВЛЕНИЕ {org_name.upper()}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Ваша роль: {user_org['role']}\n"
        f"📈 Ранг: {user_org['rank']}\n"
        f"💰 Зарплата: ${user_org['salary']}/месяц\n\n"
    )
    if is_manager:
        text += "✅ У вас есть права управления заявками и персоналом."
    else:
        text += "ℹ️ Расширенное управление доступно руководящим ролям."

    keyboard = []
    if is_manager:
        keyboard.append([InlineKeyboardButton("📋 Заявки", callback_data=f"org_applications_{org_type}")])
    keyboard.extend([
        [InlineKeyboardButton("👥 Персонал", callback_data=f"org_staff_{org_type}")],
        [InlineKeyboardButton("📊 Панель", callback_data=f"org_panel_{org_type}")],
        [InlineKeyboardButton("🔙 К организации", callback_data=f"org_view_{org_type}")],
    ])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def organization_panel_by_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Используем общую панель, но поддерживаем callback вида org_panel_<type>.
    await organization_panel(update, context)


async def organization_applications_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    org_type = query.data.replace("org_applications_", "")
    user_org = org_system.get_user_organization(query.from_user.id)

    if not user_org or user_org['type'] != org_type or user_org['role'] not in ORG_MANAGER_ROLES:
        await query.edit_message_text(
            "❌ Недостаточно прав для просмотра заявок.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=f"org_manage_{org_type}")]])
        )
        return

    applications = org_system.get_pending_applications(user_org['id'])
    text = f"📋 **ЗАЯВКИ В {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []

    if not applications:
        text += "Пока нет новых заявок."
    else:
        for app in applications[:10]:
            text += (
                f"🆔 #{app['id']} | 👤 {app['full_name']}\n"
                f"🎓 Образование: {app['education']} | ⭐ Репутация: {app['reputation']}\n"
                f"📝 {app['application_text'][:120]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([
                InlineKeyboardButton("🟢 Одобрить", callback_data=f"org_app_approve_{app['id']}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"org_app_reject_{app['id']}"),
            ])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"org_manage_{org_type}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def organization_application_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    if len(parts) < 4:
        await query.edit_message_text("❌ Некорректные данные заявки.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    decision = parts[2]
    app_id = int(parts[3])
    reviewer_id = query.from_user.id
    reviewer_org = org_system.get_user_organization(reviewer_id)

    if not reviewer_org or reviewer_org['role'] not in ORG_MANAGER_ROLES:
        await query.edit_message_text("❌ У вас нет прав для обработки заявки.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT org_id, status FROM organization_applications WHERE id = ?', (app_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await query.edit_message_text("❌ Заявка не найдена.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    app_org_id, app_status = row
    if app_org_id != reviewer_org['id']:
        await query.edit_message_text("❌ Нельзя обрабатывать заявки другой организации.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return
    if app_status != 'pending':
        await query.edit_message_text("ℹ️ Эта заявка уже обработана.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    success, message = org_system.process_application(app_id, reviewer_id, decision)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 К заявкам", callback_data=f"org_applications_{reviewer_org['type']}")],
        [InlineKeyboardButton("🔙 В управление", callback_data=f"org_manage_{reviewer_org['type']}")],
    ])
    await query.edit_message_text(message, reply_markup=keyboard)


async def organization_staff_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    org_type = query.data.replace("org_staff_", "")
    user_org = org_system.get_user_organization(query.from_user.id)

    if not user_org or user_org['type'] != org_type:
        await query.edit_message_text(
            "❌ Персонал доступен только для вашей организации.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")]])
        )
        return

    members = org_system.get_organization_members(user_org['id'], limit=30)
    text = f"👥 **ПЕРСОНАЛ {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not members:
        text += "В организации пока нет сотрудников."
    else:
        for idx, member in enumerate(members, 1):
            text += (
                f"{idx}. **{member['full_name']}**\n"
                f"   🏷️ {member['role']} | 📈 Ранг {member['rank']}\n"
                f"   ✅ Заданий: {member['tasks_completed']} | ⭐ {member['reputation']}/100\n"
            )
            if idx < len(members):
                text += "━━━━━━━━━━━━━━━━━━━━\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 В управление", callback_data=f"org_manage_{org_type}")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def organization_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT u.full_name, o.name, om.role, om.tasks_completed, om.rank, om.experience
                 FROM organization_members om
                 LEFT JOIN users u ON om.user_id = u.user_id
                 LEFT JOIN organizations o ON om.org_id = o.id
                 ORDER BY om.tasks_completed DESC, om.rank DESC, om.experience DESC
                 LIMIT 15''')
    rows = c.fetchall()
    conn.close()

    text = "🏆 **РЕЙТИНГ СОТРУДНИКОВ ОРГАНИЗАЦИЙ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "Пока нет данных для рейтинга."
    else:
        for idx, row in enumerate(rows, 1):
            full_name = row[0] or "Неизвестно"
            org_name = row[1] or "Организация"
            role = row[2] or "Сотрудник"
            tasks_completed = row[3] or 0
            rank = row[4] or 1
            exp = row[5] or 0
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏅"
            text += (
                f"{medal} **{idx}. {full_name}**\n"
                f"   🏛️ {org_name} | 🏷️ {role}\n"
                f"   ✅ {tasks_completed} заданий | 📈 Ранг {rank} | XP {exp}\n"
            )
            if idx < len(rows):
                text += "━━━━━━━━━━━━━━━━━━━━\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")]]),
        parse_mode='Markdown'
    )


async def organization_career(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)

    text = "💼 **КАРЬЕРА В ОРГАНИЗАЦИЯХ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not user_org:
        text += (
            "Вы пока не состоите в организации.\n\n"
            "Как начать:\n"
            "1. Откройте список организаций.\n"
            "2. Подайте заявку в подходящую структуру.\n"
            "3. Выполняйте задания для роста ранга и зарплаты."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ К организациям", callback_data="orgs_list")],
            [InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")],
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        return

    text += (
        f"🏛️ Текущая организация: {user_org['name']}\n"
        f"🏷️ Роль: {user_org['role']}\n"
        f"📈 Ранг: {user_org['rank']}\n"
        f"💰 Зарплата: ${user_org['salary']}/месяц\n\n"
        "Что влияет на рост:\n"
        "• выполнение заданий организации\n"
        "• стабильная активность\n"
        "• качество работы (performance)\n"
        "• доверие руководства\n"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Мой путь роста", callback_data="org_career_path")],
        [InlineKeyboardButton("🔙 Назад", callback_data="orgs_main")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def organization_career_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)

    if not user_org:
        await query.edit_message_text(
            "❌ Сначала вступите в организацию.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏛️ К организациям", callback_data="orgs_list")]])
        )
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT tasks_completed, experience, performance
                 FROM organization_members
                 WHERE user_id = ? AND org_id = ?''', (query.from_user.id, user_org['id']))
    member_stats = c.fetchone()
    conn.close()

    tasks_completed = member_stats[0] if member_stats else 0
    exp = member_stats[1] if member_stats else 0
    perf = member_stats[2] if member_stats else 100
    next_rank = user_org['rank'] + 1
    recommended_tasks = max(0, next_rank * 2 - tasks_completed)

    text = (
        "📈 **ПУТЬ КАРЬЕРНОГО РОСТА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏛️ Организация: {user_org['name']}\n"
        f"🏷️ Текущая роль: {user_org['role']}\n"
        f"📈 Текущий ранг: {user_org['rank']}\n"
        f"✅ Выполнено заданий: {tasks_completed}\n"
        f"⭐ Производительность: {perf}/100\n"
        f"🧠 Опыт в организации: {exp}\n\n"
        "Чтобы повыситься:\n"
        f"• доведите количество закрытых задач минимум до ~{next_rank * 2}\n"
        "• удерживайте производительность выше 80\n"
        "• регулярно участвуйте в жизни организации\n\n"
        f"🎯 Сейчас ориентир: выполнить ещё примерно {recommended_tasks} задач."
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def organization_colleagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)

    if not user_org:
        await query.edit_message_text("❌ Вы не состоите в организации.", reply_markup=back_markup("orgs_main", "🔙 К организациям"))
        return

    members = org_system.get_organization_members(user_org['id'], limit=20)
    text = f"👥 **КОЛЛЕГИ: {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not members:
        text += "Коллеги пока не найдены."
    else:
        for idx, member in enumerate(members, 1):
            text += f"{idx}. **{member['full_name']}** — {member['role']} (ранг {member['rank']})\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def organization_stats_detailed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)

    if not user_org:
        await query.edit_message_text("❌ Вы не состоите в организации.", reply_markup=back_markup("orgs_main", "🔙 К организациям"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT tasks_completed, experience, performance, join_date
                 FROM organization_members
                 WHERE user_id = ? AND org_id = ?''', (user_id, user_org['id']))
    member = c.fetchone()
    conn.close()

    tasks_completed = member[0] if member else 0
    exp = member[1] if member else 0
    performance = member[2] if member else 100
    join_date = member[3] if member else None

    if join_date:
        try:
            join_date = datetime.fromisoformat(join_date).strftime('%d.%m.%Y')
        except ValueError:
            join_date = join_date[:10]
    else:
        join_date = "—"

    text = (
        f"📊 **ДЕТАЛЬНАЯ СТАТИСТИКА: {user_org['name'].upper()}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏷️ Роль: {user_org['role']}\n"
        f"📈 Ранг: {user_org['rank']}\n"
        f"💰 Зарплата: ${user_org['salary']}/месяц\n"
        f"✅ Выполнено заданий: {tasks_completed}\n"
        f"🧠 Опыт в организации: {exp}\n"
        f"⭐ Производительность: {performance}/100\n"
        f"📅 Вступили: {join_date}\n\n"
        f"🏛️ Членов в организации: {user_org['members']}\n"
        f"💵 Бюджет организации: ${user_org['budget']:,.0f}\n"
        f"🌟 Репутация организации: {user_org['reputation']}/100"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def police_investigation_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org['name'] != 'Полиция':
        await query.edit_message_text("❌ Доступно только сотрудникам полиции.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT suspect_id, reason, status, arrest_date
                 FROM arrests
                 WHERE officer_id = ?
                 ORDER BY arrest_date DESC
                 LIMIT 10''', (query.from_user.id,))
    rows = c.fetchall()
    conn.close()

    text = "🕵️ **РАССЛЕДОВАНИЯ ПОЛИЦИИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "У вас пока нет завершённых или активных расследований/арестов."
    else:
        text += "Последние действия:\n"
        for row in rows:
            text += f"• Подозреваемый ID {row[0]} | {row[2]} | {row[1][:40]}\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Арестовать", callback_data="police_arrest")],
        [InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def police_wanted_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT a.suspect_id, u.full_name, a.reason, a.fine
                 FROM arrests a
                 LEFT JOIN users u ON a.suspect_id = u.user_id
                 WHERE a.status = 'active'
                 ORDER BY a.arrest_date DESC
                 LIMIT 20''')
    wanted = c.fetchall()
    conn.close()

    text = "📋 **АКТИВНЫЙ СПИСОК РОЗЫСКА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not wanted:
        text += "Список пуст. Активных арестов нет."
    else:
        for idx, row in enumerate(wanted, 1):
            suspect_name = row[1] or "Неизвестно"
            text += f"{idx}. {suspect_name} (ID {row[0]})\n"
            text += f"   Причина: {row[2]}\n"
            text += f"   Штраф: ${row[3]:,.0f}\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def hospital_diagnose_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_treatment(update, context)


async def hospital_prescribe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_treatment(update, context)


async def bank_service_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org['name'] != 'Банк':
        await query.edit_message_text("❌ Доступно только сотрудникам банка.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT status, COUNT(*) FROM loans GROUP BY status')
    rows = c.fetchall()
    conn.close()
    stats = {row[0]: row[1] for row in rows}

    text = (
        "💵 **БАНКОВСКОЕ ОБСЛУЖИВАНИЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 Ожидают решения: {stats.get('pending', 0)}\n"
        f"✅ Одобрено: {stats.get('active', 0)}\n"
        f"❌ Отклонено: {stats.get('rejected', 0)}\n\n"
        "Для выдачи кредита перейдите в режим одобрения."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Одобрение кредита", callback_data="bank_loan")],
        [InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')


async def bank_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = org_system.get_user(query.from_user.id) or {}
    text = (
        "🏦 **СЧЕТА И БАЛАНСЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Наличные: ${user.get('cash', 0):,.0f}\n"
        f"💳 Банк: ${user.get('bank', 0):,.0f}\n"
        f"💰 Общий баланс: ${user.get('balance', 0):,.0f}\n"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def government_laws_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT law_number, title, status, votes_for, votes_against
                 FROM laws
                 ORDER BY proposed_date DESC
                 LIMIT 10''')
    laws = c.fetchall()
    conn.close()

    text = "📜 **ЗАКОНЫ ГОСУДАРСТВА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not laws:
        text += "Пока нет внесённых законопроектов."
    else:
        for law in laws:
            text += (
                f"• **{law[0]}** — {law[1]}\n"
                f"  Статус: {law[2]} | 👍 {law[3]} / 👎 {law[4]}\n"
            )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def government_budget_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    government = org_system.get_organization('Правительство')
    if not government:
        await query.edit_message_text("❌ Правительство не найдено в базе.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users_count = c.fetchone()[0]
    c.execute('SELECT SUM(balance) FROM users')
    economy = c.fetchone()[0] or 0
    conn.close()

    text = (
        "💰 **ГОСУДАРСТВЕННЫЙ БЮДЖЕТ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏛️ Бюджет правительства: ${government['budget']:,.0f}\n"
        f"👥 Активных игроков: {users_count}\n"
        f"🌐 Объем экономики: ${economy:,.0f}\n\n"
        "Налоговые ставки:\n"
        f"• Подоходный: {government['income_tax']*100:.1f}%\n"
        f"• На недвижимость: {government['property_tax']*100:.1f}%\n"
        f"• На бизнес: {government['business_tax']*100:.1f}%"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )


async def government_appointments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT name, leader_id, deputy_id FROM organizations ORDER BY name ASC')
    rows = c.fetchall()
    conn.close()

    text = "👥 **НАЗНАЧЕНИЯ ПО ОРГАНИЗАЦИЯМ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for row in rows:
        org_name, leader_id, deputy_id = row
        leader = org_system.get_user(leader_id) if leader_id else None
        deputy = org_system.get_user(deputy_id) if deputy_id else None
        leader_name = leader.get('full_name', f"ID {leader_id}") if leader else "Вакантно"
        deputy_name = deputy.get('full_name', f"ID {deputy_id}") if deputy else "Вакантно"
        text += (
            f"🏛️ **{org_name}**\n"
            f"   👑 Руководитель: {leader_name}\n"
            f"   🤝 Заместитель: {deputy_name}\n"
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]]),
        parse_mode='Markdown'
    )

async def tax_report_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org['name'] != 'Налоговая служба':
        await query.edit_message_text("❌ Доступно только сотрудникам налоговой службы.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT user_id, full_name, balance, tax_debt, total_tax_paid
                 FROM users
                 ORDER BY tax_debt DESC, total_tax_paid DESC
                 LIMIT 10''')
    rows = c.fetchall()
    c.execute('''SELECT COALESCE(SUM(paid_total), 0), COALESCE(SUM(debt_total), 0)
                 FROM tax_logs
                 WHERE cycle_date = ?''', (datetime.now().date().isoformat(),))
    today_paid, today_debt = c.fetchone()
    conn.close()

    text = (
        "🧾 **НАЛОГОВАЯ СВОДКА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Собрано за сегодня: ${float(today_paid or 0):,.0f}\n"
        f"Начислено долга за сегодня: ${float(today_debt or 0):,.0f}\n\n"
        "Топ должников:\n"
    )
    if not rows:
        text += "Нет данных."
    else:
        for idx, row in enumerate(rows, 1):
            user_id, full_name, balance, tax_debt, total_tax_paid = row
            text += (
                f"{idx}. {full_name or 'Неизвестно'} (ID {user_id})\n"
                f"   Баланс: ${float(balance or 0):,.0f}\n"
                f"   Долг: ${float(tax_debt or 0):,.0f}\n"
                f"   Уплачено: ${float(total_tax_paid or 0):,.0f}\n"
            )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Применить цикл", callback_data="tax_cycle")],
            [InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")],
        ]),
        parse_mode='Markdown'
    )

async def tax_cycle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org['name'] != 'Налоговая служба':
        await query.edit_message_text("❌ Доступно только сотрудникам налоговой службы.", reply_markup=back_markup("orgs_main", "🔙 В меню"))
        return
    org_system.run_daily_economy_cycle()
    await query.edit_message_text(
        "✅ Налоговый/кредитный дневной цикл применен (если был пропуск по датам).",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 Отчет", callback_data="tax_report")],
            [InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")],
        ])
    )


async def take_task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)

    if not user_org:
        await query.edit_message_text("❌ Вы не состоите в организации.", reply_markup=back_markup("orgs_main", "🔙 К организациям"))
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT COUNT(*) FROM org_tasks
                 WHERE org_id = ? AND status = 'active' ''', (user_org['id'],))
    active_count = c.fetchone()[0]
    conn.close()

    if active_count == 0:
        await query.edit_message_text(
            "ℹ️ Активных заданий пока нет.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К заданиям", callback_data="org_tasks")]])
        )
        return

    context.user_data['awaiting_take_task_id'] = True
    await query.edit_message_text(
        "🎯 **ВЗЯТЬ ЗАДАНИЕ**\n\n"
        "Введите ID задания из списка, которое хотите закрыть:\n"
        "Пример: `12`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К заданиям", callback_data="org_tasks")]]),
        parse_mode='Markdown'
    )


async def handle_take_task_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_take_task_id' not in context.user_data or not update.message:
        return

    try:
        task_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите числовой ID задания.")
        return

    user_id = update.effective_user.id
    user_org = org_system.get_user_organization(user_id)
    if not user_org:
        del context.user_data['awaiting_take_task_id']
        await update.message.reply_text("❌ Вы не состоите в организации.")
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT org_id, title, status FROM org_tasks WHERE id = ?', (task_id,))
    task = c.fetchone()
    conn.close()

    if not task:
        await update.message.reply_text("❌ Задание не найдено.")
        return

    if task[2] != 'active':
        await update.message.reply_text("ℹ️ Это задание уже завершено.")
        return

    if task[0] != user_org['id']:
        await update.message.reply_text("❌ Это задание относится к другой организации.")
        return

    success, message = org_system.complete_task(task_id, user_id)
    await update.message.reply_text(message)
    if success:
        del context.user_data['awaiting_take_task_id']

async def start_arrest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса ареста"""
    query = update.callback_query
    await query.answer()
    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text(
            "❌ Нет доступных игроков для выбора.",
            reply_markup=back_markup("my_org_panel", "🔙 В панель")
        )
        return

    if 'awaiting_arrest_target' in context.user_data:
        del context.user_data['awaiting_arrest_target']

    await query.edit_message_text(
        "🚨 **ПРОИЗВЕДЕНИЕ АРЕСТА**\n\nВыберите игрока:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_arrest_", "my_org_panel", "🔙 В панель")
    )


async def select_arrest_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.replace("pick_arrest_", "", 1))
    officer_id = query.from_user.id

    target = org_system.get_user(target_id)
    if not target:
        await query.edit_message_text("❌ Игрок не найден.", reply_markup=back_markup("police_arrest", "🔙 К выбору"))
        return
    if target_id == officer_id:
        await query.edit_message_text("❌ Нельзя арестовать себя.", reply_markup=back_markup("police_arrest", "🔙 К выбору"))
        return
    if target.get('arrested'):
        await query.edit_message_text("❌ Этот игрок уже под арестом.", reply_markup=back_markup("police_arrest", "🔙 К выбору"))
        return

    context.user_data['arrest_target_id'] = target_id
    context.user_data['awaiting_arrest_reason'] = True

    await query.edit_message_text(
        f"🎯 **Цель:** {target.get('full_name', 'Неизвестно')}\n"
        f"⭐ Репутация: {target.get('reputation', 50):.0f}\n"
        f"💵 Баланс: ${target.get('balance', 0):,.0f}\n\n"
        "Введите причину ареста:",
        parse_mode='Markdown',
        reply_markup=back_markup("my_org_panel", "🔙 В панель")
    )

async def start_treatment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса лечения"""
    query = update.callback_query
    await query.answer()

    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text(
            "❌ Нет доступных пациентов для выбора.",
            reply_markup=back_markup("my_org_panel", "🔙 В панель")
        )
        return

    if 'awaiting_treatment_target' in context.user_data:
        del context.user_data['awaiting_treatment_target']

    await query.edit_message_text(
        "🏥 **ЛЕЧЕНИЕ ПАЦИЕНТА**\n\nВыберите пациента:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_treat_", "my_org_panel", "🔙 В панель")
    )


async def select_treatment_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    patient_id = int(query.data.replace("pick_treat_", "", 1))
    doctor_id = query.from_user.id

    patient = org_system.get_user(patient_id)
    if not patient:
        await query.edit_message_text("❌ Пациент не найден.", reply_markup=back_markup("hospital_treat", "🔙 К выбору"))
        return
    if patient_id == doctor_id:
        await query.edit_message_text("❌ Нельзя лечить себя.", reply_markup=back_markup("hospital_treat", "🔙 К выбору"))
        return
    if patient.get('life_state', 'alive') == 'dead':
        await query.edit_message_text("❌ Пациент мертв. Лечение невозможно.", reply_markup=back_markup("hospital_treat", "🔙 К выбору"))
        return
    if patient.get('life_state', 'alive') == 'alive' and not patient.get('injury_severity'):
        await query.edit_message_text("❌ У пациента нет травм, лечение не требуется.", reply_markup=back_markup("hospital_treat", "🔙 К выбору"))
        return

    context.user_data['treatment_patient_id'] = patient_id
    context.user_data['awaiting_diagnosis'] = True

    await query.edit_message_text(
        f"🏥 **Пациент:** {patient.get('full_name', 'Неизвестно')}\n"
        f"💔 Состояние: {patient.get('life_state', 'alive')}\n"
        f"🩹 Травма: {patient.get('injury_severity') or 'нет'}\n"
        f"💰 Баланс: ${patient.get('balance', 0):,.0f}\n\n"
        "Введите диагноз пациента:",
        parse_mode='Markdown',
        reply_markup=back_markup("my_org_panel", "🔙 В панель")
    )

async def start_loan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса выдачи кредита"""
    query = update.callback_query
    await query.answer()

    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text(
            "❌ Нет игроков для выбора заявителя.",
            reply_markup=back_markup("my_org_panel", "🔙 В панель")
        )
        return

    if 'awaiting_loan_applicant' in context.user_data:
        del context.user_data['awaiting_loan_applicant']

    await query.edit_message_text(
        "🏦 **ОДОБРЕНИЕ КРЕДИТА**\n\nВыберите заявителя:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_loanapp_", "my_org_panel", "🔙 В панель")
    )


async def select_loan_applicant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    applicant_id = int(query.data.replace("pick_loanapp_", "", 1))

    applicant = org_system.get_user(applicant_id)
    if not applicant:
        await query.edit_message_text("❌ Заявитель не найден.", reply_markup=back_markup("bank_loan", "🔙 К выбору"))
        return

    context.user_data['loan_applicant_id'] = applicant_id
    context.user_data['awaiting_loan_amount'] = True

    await query.edit_message_text(
        f"👤 **Заявитель:** {applicant.get('full_name', 'Неизвестно')}\n"
        f"⭐ Репутация: {applicant.get('reputation', 50):.0f}\n"
        f"💰 Баланс: ${applicant.get('balance', 0):,.0f}\n"
        f"🏠 Недвижимость: {'Есть' if applicant.get('property_owner') else 'Нет'}\n\n"
        f"Введите сумму кредита:\n"
        f"💡 Максимум: ${min(100000, applicant.get('reputation', 50) * 700):,.0f}",
        parse_mode='Markdown',
        reply_markup=back_markup("my_org_panel", "🔙 В панель")
    )

async def start_loan_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подача заявки на кредит пользователем"""
    query = update.callback_query
    if update.effective_chat and update.effective_chat.type != "private":
        if query:
            await query.answer()
            await query.edit_message_text(
                "🏦 Заявка на кредит принимается только в личных сообщениях с ботом.",
                reply_markup=back_markup("back_to_main", "🔙 В меню")
            )
        else:
            await update.message.reply_text(
                "🏦 Заявка на кредит принимается только в личных сообщениях с ботом."
            )
        return

    org_system.ensure_user(update.effective_user)

    if query:
        await query.answer()
        await query.edit_message_text(
            "🏦 **ЗАЯВКА НА КРЕДИТ**\n\n"
            "Введите сумму кредита (минимум 100, максимум 1 000 000):",
            parse_mode='Markdown',
            reply_markup=back_markup("back_to_main", "🔙 Отмена")
        )
    else:
        await update.message.reply_text(
            "🏦 **ЗАЯВКА НА КРЕДИТ**\n\n"
            "Введите сумму кредита (минимум 100, максимум 1 000 000):",
            parse_mode='Markdown'
        )
    context.user_data['awaiting_loan_request_amount'] = True

async def view_organization_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр членов организации"""
    query = update.callback_query
    await query.answer()
    
    org_type = query.data.replace("org_members_", "")
    
    org_names = {
        'government': 'Правительство',
        'police': 'Полиция',
        'hospital': 'Больница',
        'court': 'Суд',
        'bank': 'Банк',
        'education': 'Университет',
        'fbi': 'ФБР',
        'tax': 'Налоговая служба'
    }
    
    org_name = org_names.get(org_type)
    if not org_name:
        await query.edit_message_text("❌ Организация не найдена!", reply_markup=back_markup("orgs_list", "🔙 К списку"))
        return
    
    org = org_system.get_organization(org_name)
    members = org_system.get_organization_members(org['id'], limit=10)
    
    if not members:
        members_text = f"👥 **ЧЛЕНЫ {org_name.upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        members_text += "Пока нет членов в организации.\n"
    else:
        members_text = f"👥 **ТОП-10 ЧЛЕНОВ {org_name.upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, member in enumerate(members, 1):
            rank_emoji = "👑" if member['role'] in ['Президент', 'Лидер', 'Директор'] else "⭐" if member['rank'] > 5 else "🔹"
            members_text += f"{rank_emoji} **{member['full_name']}**\n"
            members_text += f"   🏷️ {member['role']} | 📈 Ранг: {member['rank']}\n"
            members_text += f"   💰 ${member['salary']}/месяц | ⭐ {member['reputation']}/100\n"
            members_text += f"   🏢 {member['department'] or 'Общий'} | 📊 Опыт: {member['total_exp']}\n"
            
            if i < len(members):
                members_text += "━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 К организации", callback_data=f"org_view_{org_type}")],
        [InlineKeyboardButton("🔙 В меню", callback_data="orgs_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(members_text, reply_markup=reply_markup, parse_mode='Markdown')

async def leave_organization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из организации"""
    query = update.callback_query
    await query.answer()
    
    org_type = query.data.replace("org_leave_", "")
    
    org_names = {
        'government': 'Правительство',
        'police': 'Полиция',
        'hospital': 'Больница',
        'court': 'Суд',
        'bank': 'Банк',
        'education': 'Университет',
        'fbi': 'ФБР',
        'tax': 'Налоговая служба'
    }
    
    org_name = org_names.get(org_type)
    user_id = query.from_user.id
    
    conn = get_conn()
    c = conn.cursor()
    
    # Получаем организацию
    org = org_system.get_organization(org_name)
    if not org:
        conn.close()
        await query.edit_message_text("❌ Организация не найдена!", reply_markup=back_markup("orgs_list", "🔙 К списку"))
        return
    
    # Удаляем из членов
    c.execute('DELETE FROM organization_members WHERE user_id = ? AND org_id = ?', (user_id, org['id']))
    
    # Обновляем счетчик членов
    c.execute('UPDATE organizations SET members = members - 1 WHERE id = ?', (org['id'],))
    
    conn.commit()
    conn.close()
    
    # Обновляем пользователя
    org_system.update_user(user_id, organization=None, role=None)
    
    await query.edit_message_text(
        f"🏃 **ВЫ ПОКИНУЛИ ОРГАНИЗАЦИЮ**\n\n"
        f"🏛️ **Организация:** {org_name}\n"
        f"👋 **Статус:** Бывший член\n\n"
        f"💡 *Вы можете подать заявку в другую организацию или создать свою.*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ К организациям", callback_data="orgs_list")],
            [InlineKeyboardButton("🔙 В меню", callback_data="orgs_main")]
        ])
    )

async def handle_arrest_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цели для ареста"""
    if 'awaiting_arrest_target' in context.user_data and update.message:
        try:
            target_id = int(update.message.text)
            officer_id = update.effective_user.id
            
            # Проверяем, существует ли цель
            target = org_system.get_user(target_id)
            if not target:
                await update.message.reply_text("❌ Игрок не найден!")
                return
            
            # Проверяем, не пытается ли арестовать себя
            if target_id == officer_id:
                await update.message.reply_text("❌ Нельзя арестовать себя!")
                return
            
            # Проверяем, не арестован ли уже
            if target.get('arrested'):
                await update.message.reply_text("❌ Этот игрок уже под арестом!")
                return
            
            # Сохраняем ID цели
            context.user_data['arrest_target_id'] = target_id
            context.user_data['awaiting_arrest_reason'] = True
            del context.user_data['awaiting_arrest_target']
            
            await update.message.reply_text(
                f"🎯 **Цель:** {target.get('full_name', 'Неизвестно')}\n"
                f"⭐ **Репутация:** {target.get('reputation', 50)}/100\n"
                f"💵 **Баланс:** ${target.get('balance', 0):,.0f}\n\n"
                f"Введите причину ареста:\n"
                f"💡 *Пример: \"Кража имущества\", \"Нападение на гражданина\", \"Мошенничество\"*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID игрока!")

async def handle_arrest_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка причины ареста"""
    if 'awaiting_arrest_reason' in context.user_data and update.message:
        reason = update.message.text
        target_id = context.user_data['arrest_target_id']
        officer_id = update.effective_user.id
        
        if len(reason) < 5:
            await update.message.reply_text("❌ Причина слишком короткая! Минимум 5 символов.")
            return
        
        context.user_data['awaiting_arrest_fine'] = True
        context.user_data['arrest_reason'] = reason
        del context.user_data['awaiting_arrest_reason']
        
        await update.message.reply_text(
            f"📜 **Причина:** {reason}\n\n"
            f"Введите сумму штрафа (0 если без штрафа):\n"
            f"💡 *Рекомендуется: $100-5000*\n"
            f"⚠️ *Слишком большой штраф может быть оспорен в суде*"
        )

async def handle_arrest_fine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка штрафа при аресте"""
    if 'awaiting_arrest_fine' in context.user_data and update.message:
        try:
            fine = float(update.message.text)
            target_id = context.user_data['arrest_target_id']
            officer_id = update.effective_user.id
            reason = context.user_data['arrest_reason']
            
            if fine < 0:
                await update.message.reply_text("❌ Штраф не может быть отрицательным!")
                return
            
            if fine > 7000:
                await update.message.reply_text("⚠️ Штраф слишком большой! Максимум $7,000.")
                fine = 7000
            
            # Производим арест
            success, message = org_system.arrest_player(officer_id, target_id, reason, "", fine)
            
            await update.message.reply_text(message)
            
            # Очищаем состояние
            del context.user_data['arrest_target_id']
            del context.user_data['arrest_reason']
            del context.user_data['awaiting_arrest_fine']
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму!")

async def handle_treatment_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цели для лечения"""
    if 'awaiting_treatment_target' in context.user_data and update.message:
        try:
            patient_id = int(update.message.text)
            doctor_id = update.effective_user.id
            
            # Проверяем, существует ли пациент
            patient = org_system.get_user(patient_id)
            if not patient:
                await update.message.reply_text("❌ Пациент не найден!")
                return
            
            # Проверяем, не пытается ли лечить себя
            if patient_id == doctor_id:
                await update.message.reply_text("❌ Нельзя лечить себя! Обратитесь к другому врачу.")
                return
            
            # Проверяем, нуждается ли в лечении
            if patient.get('life_state', 'alive') == 'dead':
                await update.message.reply_text("❌ Пациент мертв. Лечение невозможно.")
                return
            if patient.get('life_state', 'alive') == 'alive' and not patient.get('injury_severity'):
                await update.message.reply_text("❌ У пациента нет травм, лечение не требуется.")
                return
            
            # Сохраняем ID пациента
            context.user_data['treatment_patient_id'] = patient_id
            context.user_data['awaiting_diagnosis'] = True
            del context.user_data['awaiting_treatment_target']
            
            await update.message.reply_text(
                f"🏥 **ПАЦИЕНТ:** {patient.get('full_name', 'Неизвестно')}\n"
                f"💔 **Состояние:** {patient.get('life_state', 'alive')}\n"
                f"🩹 **Травма:** {patient.get('injury_severity') or 'нет'}\n"
                f"💰 **Баланс:** ${patient.get('balance', 0):,.0f}\n\n"
                f"Введите диагноз пациента:\n"
                f"💡 *Пример: \"Перелом руки\", \"Травма головы\"*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID пациента!")

async def handle_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка диагноза"""
    if 'awaiting_diagnosis' in context.user_data and update.message:
        diagnosis = update.message.text
        patient_id = context.user_data['treatment_patient_id']
        
        if len(diagnosis) < 3:
            await update.message.reply_text("❌ Диагноз слишком короткий!")
            return
        
        context.user_data['awaiting_treatment'] = True
        context.user_data['diagnosis'] = diagnosis
        del context.user_data['awaiting_diagnosis']
        
        await update.message.reply_text(
            f"📝 **Диагноз:** {diagnosis}\n\n"
            f"Введите план лечения:\n"
            f"💡 *Пример: \"Гипс на 2 недели\", \"Постельный режим\", \"Операция\"*"
        )

async def handle_treatment_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка плана лечения"""
    if 'awaiting_treatment' in context.user_data and update.message:
        treatment = update.message.text
        patient_id = context.user_data['treatment_patient_id']
        doctor_id = update.effective_user.id
        diagnosis = context.user_data['diagnosis']
        
        if len(treatment) < 3:
            await update.message.reply_text("❌ План лечения слишком короткий!")
            return
        
        # Получаем данные пациента
        patient = org_system.get_user(patient_id)
        
        # Расчет стоимости лечения по тяжести травмы
        severity = patient.get('injury_severity') or 'light'
        severity_costs = {
            'light': 500,
            'medium': 1500,
            'severe': 3000,
            'critical': 6000
        }
        base_cost = severity_costs.get(severity, 1000)
        
        # Скидка за квалификацию врача
        doctor_level = org_system.get_user(doctor_id).get('education', 1)
        discount = min(0.4, doctor_level * 0.05)  # до 40% скидки
        final_cost = int(base_cost * (1 - discount))
        
        # Проверяем возможность оплаты
        if patient.get('balance', 0) < final_cost:
            await update.message.reply_text(
                f"❌ У пациента недостаточно средств!\n"
                f"💰 Нужно: ${final_cost:,.0f}\n"
                f"💵 У пациента: ${patient.get('balance', 0):,.0f}\n\n"
                f"Можете предложить лечение за другую цену или отменить."
            )
            
            context.user_data['awaiting_cost'] = True
            context.user_data['treatment'] = treatment
            if 'awaiting_treatment' in context.user_data:
                del context.user_data['awaiting_treatment']
            return
        
        # Производим лечение
        success, message = org_system.treat_patient(doctor_id, patient_id, diagnosis, treatment, final_cost)
        
        await update.message.reply_text(message)
        
        # Очищаем состояние
        if 'treatment_patient_id' in context.user_data:
            del context.user_data['treatment_patient_id']
        if 'diagnosis' in context.user_data:
            del context.user_data['diagnosis']
        if 'awaiting_treatment' in context.user_data:
            del context.user_data['awaiting_treatment']

async def handle_treatment_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка стоимости лечения"""
    if 'awaiting_cost' in context.user_data and update.message:
        try:
            cost = float(update.message.text)
            patient_id = context.user_data['treatment_patient_id']
            doctor_id = update.effective_user.id
            diagnosis = context.user_data['diagnosis']
            treatment = context.user_data['treatment']
            
            if cost < 0:
                await update.message.reply_text("❌ Стоимость не может быть отрицательной!")
                return
            
            # Проверяем возможность оплаты
            patient = org_system.get_user(patient_id)
            if patient.get('balance', 0) < cost:
                await update.message.reply_text(
                    f"❌ У пациента все равно недостаточно средств!\n"
                    f"💰 Нужно: ${cost:,.0f}\n"
                    f"💵 У пациента: ${patient.get('balance', 0):,.0f}"
                )
                return
            
            # Производим лечение
            success, message = org_system.treat_patient(doctor_id, patient_id, diagnosis, treatment, cost)
            
            await update.message.reply_text(message)
            
            # Очищаем состояние
            if 'treatment_patient_id' in context.user_data:
                del context.user_data['treatment_patient_id']
            if 'diagnosis' in context.user_data:
                del context.user_data['diagnosis']
            if 'treatment' in context.user_data:
                del context.user_data['treatment']
            if 'awaiting_cost' in context.user_data:
                del context.user_data['awaiting_cost']
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму!")

async def handle_loan_applicant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка заявителя на кредит"""
    if 'awaiting_loan_applicant' in context.user_data and update.message:
        try:
            applicant_id = int(update.message.text)
            officer_id = update.effective_user.id
            
            # Проверяем, существует ли заявитель
            applicant = org_system.get_user(applicant_id)
            if not applicant:
                await update.message.reply_text("❌ Заявитель не найден!")
                return
            
            # Сохраняем ID заявителя
            context.user_data['loan_applicant_id'] = applicant_id
            context.user_data['awaiting_loan_amount'] = True
            del context.user_data['awaiting_loan_applicant']
            
            await update.message.reply_text(
                f"👤 **Заявитель:** {applicant.get('full_name', 'Неизвестно')}\n"
                f"⭐ **Репутация:** {applicant.get('reputation', 50)}/100\n"
                f"💰 **Баланс:** ${applicant.get('balance', 0):,.0f}\n"
                f"🏠 **Недвижимость:** {'Есть' if applicant.get('property_owner') else 'Нет'}\n\n"
                f"Введите сумму кредита:\n"
                f"💡 *Максимум: ${min(100000, applicant.get('reputation', 50) * 700):,.0f}*\n"
                f"⚠️ *Учитывайте платежеспособность заявителя*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID!")

async def handle_loan_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка суммы кредита"""
    if 'awaiting_loan_amount' in context.user_data and update.message:
        try:
            amount = float(update.message.text)
            applicant_id = context.user_data['loan_applicant_id']
            officer_id = update.effective_user.id
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            # Проверяем максимальную сумму
            applicant = org_system.get_user(applicant_id)
            max_amount = min(100000, applicant.get('reputation', 50) * 700)
            
            if amount > max_amount:
                await update.message.reply_text(
                    f"⚠️ Сумма слишком большая!\n"
                    f"💰 Максимум для этого заявителя: ${max_amount:,.0f}\n"
                    f"⭐ Основано на репутации: {applicant.get('reputation', 50)}"
                )
                return
            
            context.user_data['loan_amount'] = amount
            context.user_data['awaiting_loan_term'] = True
            del context.user_data['awaiting_loan_amount']
            
            await update.message.reply_text(
                f"💰 **Сумма:** ${amount:,.0f}\n\n"
                f"Введите срок кредита в месяцах:\n"
                f"💡 *Рекомендуется: 6-60 месяцев*\n"
                f"⚠️ *Чем больше срок, тем больше переплата*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму!")

async def handle_loan_term(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка срока кредита"""
    if 'awaiting_loan_term' in context.user_data and update.message:
        try:
            term = int(update.message.text)
            applicant_id = context.user_data['loan_applicant_id']
            officer_id = update.effective_user.id
            amount = context.user_data['loan_amount']
            
            if term < 1 or term > 120:
                await update.message.reply_text("❌ Срок должен быть от 1 до 120 месяцев!")
                return
            
            context.user_data['loan_term'] = term
            context.user_data['awaiting_loan_purpose'] = True
            del context.user_data['awaiting_loan_term']
            
            await update.message.reply_text(
                f"⏳ **Срок:** {term} месяцев\n\n"
                f"Введите цель кредита:\n"
                f"💡 *Пример: \"Покупка недвижимости\", \"Развитие бизнеса\", \"Лечение\"*\n"
                f"📝 *Будет записано в кредитную историю*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число!")

async def handle_loan_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цели кредита"""
    if 'awaiting_loan_purpose' in context.user_data and update.message:
        purpose = update.message.text
        applicant_id = context.user_data['loan_applicant_id']
        officer_id = update.effective_user.id
        amount = context.user_data['loan_amount']
        term = context.user_data['loan_term']
        
        if len(purpose) < 3:
            await update.message.reply_text("❌ Цель слишком короткая!")
            return
        
        # Одобряем кредит
        success, message = org_system.approve_loan(officer_id, applicant_id, amount, term, purpose)
        
        await update.message.reply_text(message)
        
        # Очищаем состояние
        if 'loan_applicant_id' in context.user_data:
            del context.user_data['loan_applicant_id']
        if 'loan_amount' in context.user_data:
            del context.user_data['loan_amount']
        if 'loan_term' in context.user_data:
            del context.user_data['loan_term']
        if 'awaiting_loan_purpose' in context.user_data:
            del context.user_data['awaiting_loan_purpose']

# ==================== ВЫБОРЫ UI ====================

async def elections_list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    org_type = query.data.replace("elections_list_", "")
    org_name = ORG_TYPE_NAMES.get(org_type)
    org = org_system.get_organization(org_name)

    if not org:
        await query.edit_message_text("❌ Организация не найдена.", reply_markup=back_markup("orgs_main"))
        return

    elections = org_system.get_elections(org['id'], status='active')
    text = f"🗳️ **ВЫБОРЫ В {org_name.upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []

    if not elections:
        text += "Нет активных выборов."
    else:
        for election in elections:
            election_id, _, position, _, end_date, _, _, _ = election
            end_date_str = datetime.fromisoformat(end_date).strftime('%d.%m.%Y')
            text += f"• **Выборы на должность:** {position}\n"
            text += f"  До {end_date_str}\n"
            keyboard.append([InlineKeyboardButton(f"ℹ️ Подробнее (ID: {election_id})", callback_data=f"election_view_{election_id}")])

    keyboard.append([InlineKeyboardButton("🔙 В панель", callback_data=f"org_panel_{org_type}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def elections_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    election_id = int(query.data.replace("election_view_", ""))
    election = org_system.get_election(election_id)

    if not election:
        await query.edit_message_text("❌ Выборы не найдены.", reply_markup=back_markup("orgs_main"))
        return

    candidates = org_system.get_election_candidates(election_id)
    org = org_system.get_organization_by_id(election['org_id'])

    text = f"🗳️ **Выборы в {org['name']}**\n"
    text += f"**Должность:** {election['position']}\n"
    text += f"**Описание:** {election.get('description', 'Нет')}\n"
    text += f"**Завершение:** {datetime.fromisoformat(election['end_date']).strftime('%d.%m.%Y %H:%M')}\n\n"
    text += "**Кандидаты:**\n"

    keyboard = []
    if not candidates:
        text += "Еще нет кандидатов.\n"
    else:
        for candidate in candidates:
            text += f"👤 **{candidate['full_name']}** (голосов: {candidate['votes']})\n"
            text += f"   Программа: {candidate['program']}\n"
            keyboard.append([InlineKeyboardButton(f"✅ Голосовать за {candidate['full_name']}", callback_data=f"election_vote_{election_id}_{candidate['id']}")])

    keyboard.append([InlineKeyboardButton("🙋 Выдвинуть кандидатуру", callback_data=f"nominate_start_{election_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"elections_list_{org['type']}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def elections_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org['name'] != 'Правительство':
        await query.edit_message_text("❌ Только правительство может инициировать выборы.", reply_markup=back_markup("orgs_main"))
        return

    orgs = org_system.list_organizations() # This function needs to be created
    keyboard = []
    for org in orgs:
        keyboard.append([InlineKeyboardButton(org['name'], callback_data=f"election_set_org_{org['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="my_org_panel")])
    await query.edit_message_text("Выберите организацию для проведения выборов:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_election_org(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_id = int(query.data.replace("election_set_org_", ""))
    context.user_data['election_creation'] = {'org_id': org_id}
    await query.edit_message_text("Введите название должности:", reply_markup=back_markup("elections_create", "🔙 Отмена"))
    context.user_data['awaiting_election_position'] = True

async def handle_election_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_election_position' not in context.user_data or not update.message:
        return
    position = update.message.text
    context.user_data['election_creation']['position'] = position
    await update.message.reply_text("Введите описание выборов:")
    context.user_data['awaiting_election_description'] = True
    del context.user_data['awaiting_election_position']

async def handle_election_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_election_description' not in context.user_data or not update.message:
        return
    description = update.message.text
    creator_id = update.effective_user.id
    data = context.user_data['election_creation']
    election_id = org_system.create_election(creator_id, data['org_id'], data['position'], description)
    await update.message.reply_text(f"✅ Выборы на должность {data['position']} в организации #{data['org_id']} созданы. ID выборов: {election_id}")
    del context.user_data['awaiting_election_description']
    del context.user_data['election_creation']

async def nominate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    election_id = int(query.data.replace("nominate_start_", ""))
    context.user_data['awaiting_nomination_program'] = election_id
    await query.edit_message_text("Введите свою предвыборную программу:", reply_markup=back_markup(f"election_view_{election_id}", "🔙 Отмена"))

async def handle_nomination_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_nomination_program' not in context.user_data or not update.message:
        return
    program = update.message.text
    election_id = context.user_data['awaiting_nomination_program']
    user_id = update.effective_user.id
    success, message = org_system.nominate_candidate(election_id, user_id, program)
    await update.message.reply_text(message)
    del context.user_data['awaiting_nomination_program']

async def election_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, election_id, candidate_id = query.data.split("_")
    election_id = int(election_id)
    candidate_id = int(candidate_id)
    voter_id = query.from_user.id

    success, message = org_system.vote(election_id, voter_id, candidate_id)
    await query.edit_message_text(message, reply_markup=back_markup(f"election_view_{election_id}", "🔙 К выборам"))

# ==================== ДОКЛАДЫ UI ====================

# ==================== ДОКЛАДЫ UI ====================

async def reports_list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)

    if not user_org or user_org['role'] not in ORG_MANAGER_ROLES:
        await query.edit_message_text("❌ Доступно только руководству.", reply_markup=back_markup("my_org_panel"))
        return

    reports = org_system.get_reports(user_org['id'])
    text = f"📬 **ДОКЛАДЫ И ВЫСТУПЛЕНИЯ: {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not reports:
        text += "Нет докладов и выступлений."
    else:
        type_emoji = {'statement': '📋', 'presentation': '📊', 'report': '📈', 'announcement': '📢'}
        for idx, report in enumerate(reports, 1):
            emoji = type_emoji.get(report['report_type'], '📋')
            text += (
                f"{idx}. {emoji} **{report['title']}** ({report['report_type']})\n"
                f"👤 От: {report['author_name']}\n"
                f"📅 Дата: {report['date'][:10]}\n"
                f"📝 Содержание: {report['content'][:150]}...\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
    
    keyboard = [
        [InlineKeyboardButton("➕ Новый доклад", callback_data="report_create")],
        [InlineKeyboardButton("🔙 К панели", callback_data="my_org_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def report_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org:
        await query.edit_message_text("❌ Вы не состоите в организации.", reply_markup=back_markup("my_org_panel"))
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Заявление", callback_data="report_type_statement")],
        [InlineKeyboardButton("📊 Презентация", callback_data="report_type_presentation")],
        [InlineKeyboardButton("📈 Отчет", callback_data="report_type_report")],
        [InlineKeyboardButton("📢 Объявление", callback_data="report_type_announcement")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="reports_list_" + str(user_org['id']))]
    ]
    
    text = (
        "📝 **СОЗДАТЬ ДОКЛАД ИЛИ ВЫСТУПЛЕНИЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите тип документа:\n\n"
        "📋 **Заявление** - Официальная позиция или требование\n"
        "📊 **Презентация** - Демонстрация результатов или проекта\n"
        "📈 **Отчет** - Отчет о проделанной работе\n"
        "📢 **Объявление** - Важная информация для персонала"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def report_type_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    report_type = query.data.split("_")[-1]  # statement, presentation, report, announcement
    user_org = org_system.get_user_organization(query.from_user.id)
    
    if not user_org:
        await query.edit_message_text("❌ Ошибка доступа.", reply_markup=back_markup("my_org_panel"))
        return
    
    context.user_data['awaiting_report_title'] = True
    context.user_data['report_org_id'] = user_org['id']
    context.user_data['report_type'] = report_type
    
    type_names = {
        'statement': 'Заявление',
        'presentation': 'Презентация',
        'report': 'Отчет',
        'announcement': 'Объявление'
    }
    
    text = f"Введите название {type_names.get(report_type, 'документа')} (макс. 100 символов):"
    await query.edit_message_text(text, reply_markup=back_markup("report_create"))

async def handle_report_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_report_title' not in context.user_data or not update.message:
        return
    
    title = update.message.text.strip()[:100]
    if len(title) < 3:
        await update.message.reply_text("❌ Название слишком короткое (мин. 3 символа).")
        return
    
    context.user_data['report_title'] = title
    context.user_data['awaiting_report_title'] = False
    context.user_data['awaiting_report_text'] = True
    
    report_type = context.user_data.get('report_type', 'statement')
    type_names = {
        'statement': 'Заявления',
        'presentation': 'Презентации',
        'report': 'Отчета',
        'announcement': 'Объявления'
    }
    
    await update.message.reply_text(
        f"📝 Теперь введите полный текст {type_names.get(report_type, 'документа')} (дается развёрнуто):",
        reply_markup=back_markup("report_create", "🔙 Отмена")
    )

async def handle_report_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_report_text' not in context.user_data or not update.message:
        return
    
    content = update.message.text.strip()
    if len(content) < 10:
        await update.message.reply_text("❌ Текст слишком короткий (мин. 10 символов).")
        return
    
    org_id = context.user_data.get('report_org_id')
    title = context.user_data.get('report_title', 'Доклад')
    report_type = context.user_data.get('report_type', 'statement')
    author_id = update.effective_user.id

    report_id = org_system.submit_report(org_id, author_id, content, title, report_type)

    org = org_system.get_organization_by_id(org_id)
    
    # Clean up user data
    for key in ['awaiting_report_text', 'awaiting_report_title', 'report_org_id', 'report_type', 'report_title']:
        if key in context.user_data:
            del context.user_data[key]
    
    type_emoji = {'statement': '📋', 'presentation': '📊', 'report': '📈', 'announcement': '📢'}
    emoji = type_emoji.get(report_type, '📋')
    
    text = (
        f"{emoji} **ДОКЛАД ОПУБЛИКОВАН**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Название: {title}\n"
        f"ID: #{report_id}\n"
        f"Организация: {org['name'] if org else 'Неизвестна'}\n"
        f"Статус: Опубликовано\n\n"
        "Доклад доступен для просмотра руководством организации."
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def report_create_start_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org:
        await query.edit_message_text("❌ Вы не состоите в организации.", reply_markup=back_markup("my_org_panel"))
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Заявление", callback_data="report_type_statement")],
        [InlineKeyboardButton("📊 Презентация", callback_data="report_type_presentation")],
        [InlineKeyboardButton("📈 Отчет", callback_data="report_type_report")],
        [InlineKeyboardButton("📢 Объявление", callback_data="report_type_announcement")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="reports_list_" + str(user_org['id']))]
    ]
    
    text = (
        "📝 **СОЗДАТЬ ДОКЛАД ИЛИ ВЫСТУПЛЕНИЕ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите тип документа:\n\n"
        "📋 **Заявление** - Официальная позиция или требование\n"
        "📊 **Презентация** - Демонстрация результатов или проекта\n"
        "📈 **Отчет** - Отчет о проделанной работе\n"
        "📢 **Объявление** - Важная информация для персонала"
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_report_text_legacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_report_text' not in context.user_data or not update.message:
        return
    
    content = update.message.text
    org_id = context.user_data['report_org_id']
    author_id = update.effective_user.id

    report_id = org_system.submit_report(org_id, author_id, content)

    org = org_system.get_organization_by_id(org_id)
    if org and org.get('leader_id'):
        org_system.send_notification(
            org['leader_id'],
            author_id,
            "Новый доклад",
            f"Поступил новый доклад #{report_id} в организации {org['name']}:\n\n{content[:200]}"
        )

    await update.message.reply_text("✅ Ваш доклад отправлен руководству.")
    del context.user_data['awaiting_report_text']
    del context.user_data['report_org_id']




async def handle_loan_request_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка суммы кредита (заявка пользователя)"""
    if 'awaiting_loan_request_amount' in context.user_data and update.message:
        try:
            amount = float(update.message.text)
            user_id = update.effective_user.id
            user = org_system.get_user(user_id) or {}

            if amount < 100 or amount > 1_000_000:
                await update.message.reply_text("❌ Сумма должна быть от 100 до 1 000 000.")
                return

            max_amount = min(1_000_000, (user.get('reputation', 50) or 50) * 700)
            if amount > max_amount:
                await update.message.reply_text(
                    f"⚠️ Максимум для вашей репутации: ${max_amount:,.0f}"
                )
                return

            context.user_data['loan_request_amount'] = amount
            context.user_data['awaiting_loan_request_term'] = True
            del context.user_data['awaiting_loan_request_amount']

            await update.message.reply_text(
                f"💰 **Сумма:** ${amount:,.0f}\n\n"
                "Введите срок кредита в месяцах (1-120):"
            )
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму.")

async def handle_loan_request_term(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка срока кредита (заявка пользователя)"""
    if 'awaiting_loan_request_term' in context.user_data and update.message:
        try:
            term = int(update.message.text)
            if term < 1 or term > 120:
                await update.message.reply_text("❌ Срок должен быть от 1 до 120 месяцев.")
                return

            context.user_data['loan_request_term'] = term
            context.user_data['awaiting_loan_request_purpose'] = True
            del context.user_data['awaiting_loan_request_term']

            await update.message.reply_text(
                f"⏳ **Срок:** {term} месяцев\n\n"
                "Введите цель кредита:"
            )
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число.")

async def handle_loan_request_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цели кредита (заявка пользователя)"""
    if 'awaiting_loan_request_purpose' in context.user_data and update.message:
        purpose = update.message.text
        user_id = update.effective_user.id
        amount = context.user_data['loan_request_amount']
        term = context.user_data['loan_request_term']

        if len(purpose) < 3:
            await update.message.reply_text("❌ Цель слишком короткая.")
            return

        success, message, loan_id = org_system.create_loan_request(user_id, amount, term, purpose)
        if not success:
            await update.message.reply_text(message)
        else:
            org_system.mark_task_progress(user_id, "loan_request", 1)
            bank = org_system.get_organization('Банк')
            members = org_system.get_organization_members(bank['id'], limit=50) if bank else []

            if members:
                for member in members:
                    try:
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("🟢 Одобрить", callback_data=f"loan_approve_{loan_id}"),
                            InlineKeyboardButton("🔴 Отклонить", callback_data=f"loan_reject_{loan_id}")
                        ]])
                        await context.bot.send_message(
                            chat_id=member['user_id'],
                            text=(
                                "🏦 **НОВАЯ ЗАЯВКА НА КРЕДИТ**\n\n"
                                f"👤 Заявитель ID: {user_id}\n"
                                f"💰 Сумма: ${amount:,.0f}\n"
                                f"⏳ Срок: {term} месяцев\n"
                                f"📝 Цель: {purpose}"
                            ),
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        pass

                await update.message.reply_text(
                    "✅ Заявка отправлена в банк. Ожидайте решения сотрудника."
                )
            else:
                await update.message.reply_text(
                    "ℹ️ В банке пока нет сотрудников. Заявка сохранена и будет ожидать ручной проверки."
                )

        # Очищаем состояние
        for key in ['loan_request_amount', 'loan_request_term', 'awaiting_loan_request_amount',
                    'awaiting_loan_request_term', 'awaiting_loan_request_purpose']:
            if key in context.user_data:
                del context.user_data[key]

async def loan_request_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Одобрение/отклонение заявки на кредит"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    data = query.data
    is_approve = data.startswith("loan_approve_")
    loan_id = int(data.split("_")[-1])

    if is_approve:
        success, message, info = org_system.approve_loan_request(user_id, loan_id)
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 В панель", callback_data="my_org_panel")],
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
            ])
        )
        if success and info:
            try:
                await context.bot.send_message(
                    chat_id=info['applicant_id'],
                    text=(
                        "🏦 **КРЕДИТ ОДОБРЕН**\n\n"
                        f"💰 Сумма: ${info['amount']:,.0f}\n"
                        f"⏳ Срок: {info['term_months']} месяцев\n"
                        f"📉 Ставка: {info['interest_rate']*100:.1f}%\n"
                        f"💵 Ежемесячный платеж: ${info['monthly_payment']:,.2f}\n"
                        f"📝 Цель: {info['purpose']}"
                    ),
                    parse_mode='Markdown'
                )
            except Exception:
                pass
    else:
        success, message, info = org_system.reject_loan_request(user_id, loan_id)
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 В панель", callback_data="my_org_panel")],
                [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
            ])
        )
        if success and info:
            try:
                await context.bot.send_message(
                    chat_id=info['applicant_id'],
                    text="🏦 **КРЕДИТ ОТКЛОНЕН**\n\nПричина: решением банка.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass

async def view_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр заданий организации"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)
    
    if not user_org:
        await query.edit_message_text(
            "❌ Вы не состоите в организации!",
            reply_markup=back_markup("orgs_main", "🔙 К организациям")
        )
        return
    
    conn = get_conn()
    c = conn.cursor()
    
    # Получаем задания организации
    c.execute('''SELECT * FROM org_tasks 
                WHERE org_id = ? AND status = 'active'
                ORDER BY created_date DESC LIMIT 10''', (user_org['id'],))
    tasks = c.fetchall()
    
    conn.close()
    
    if not tasks:
        tasks_text = f"📋 **ЗАДАНИЯ {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        tasks_text += "Пока нет активных заданий.\n\n"
        tasks_text += "💡 *Создайте задание, если у вас есть права руководителя.*"
    else:
        tasks_text = f"📋 **АКТИВНЫЕ ЗАДАНИЯ {user_org['name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for task in tasks:
            tasks_text += f"📌 **Задание #{task[0]}**\n"
            tasks_text += f"🏷️ **{task[3]}**\n"
            tasks_text += f"📝 {task[4]}\n"
            tasks_text += f"💰 Награда: ${task[5]}\n"
            tasks_text += f"⏳ Дедлайн: {datetime.fromisoformat(task[6]).strftime('%d.%m.%Y')}\n"
            tasks_text += f"━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = [
        [InlineKeyboardButton("🎯 Взять задание", callback_data="take_task")],
        [InlineKeyboardButton("📝 Создать задание", callback_data="create_task")],
        [InlineKeyboardButton("🔙 В панель", callback_data="my_org_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(tasks_text, reply_markup=reply_markup, parse_mode='Markdown')

async def create_task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню создания задания"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)
    
    if not user_org:
        await query.edit_message_text(
            "❌ Вы не состоите в организации!",
            reply_markup=back_markup("orgs_main", "🔙 К организациям")
        )
        return
    
    # Проверяем права
    if user_org['role'] not in ['Президент', 'Лидер', 'Директор', 'Шеф', 'Глава', 'Руководитель', 'Заместитель']:
        await query.edit_message_text(
            "❌ У вас недостаточно прав для создания заданий!",
            reply_markup=back_markup("org_tasks", "🔙 К заданиям")
        )
        return
    
    await query.edit_message_text(
        f"📝 **СОЗДАНИЕ ЗАДАНИЯ**\n\n"
        f"Введите название задания:\n\n"
        f"💡 *Пример: \"Провести патруль\", \"Вылечить 5 пациентов\", \"Одобрить 3 кредита\"*",
        reply_markup=back_markup("org_tasks", "🔙 Отмена")
    )
    
    context.user_data['awaiting_task_title'] = True
    context.user_data['task_org_id'] = user_org['id']
    context.user_data['task_creator_id'] = user_id

async def handle_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка названия задания"""
    if 'awaiting_task_title' in context.user_data and update.message:
        title = update.message.text
        
        if len(title) < 3:
            await update.message.reply_text("❌ Название слишком короткое!")
            return
        
        context.user_data['task_title'] = title
        context.user_data['awaiting_task_description'] = True
        del context.user_data['awaiting_task_title']
        
        await update.message.reply_text(
            f"🏷️ **Название:** {title}\n\n"
            f"Введите описание задания:\n\n"
            f"💡 *Подробно опишите, что нужно сделать*"
        )

async def handle_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания задания"""
    if 'awaiting_task_description' in context.user_data and update.message:
        description = update.message.text
        
        if len(description) < 10:
            await update.message.reply_text("❌ Описание слишком короткое!")
            return
        
        context.user_data['task_description'] = description
        context.user_data['awaiting_task_reward'] = True
        del context.user_data['awaiting_task_description']
        
        await update.message.reply_text(
            f"📝 **Описание:** {description}\n\n"
            f"Введите награду за выполнение задания ($):\n\n"
            f"💡 *Рекомендуется: $100-5000*"
        )

async def handle_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка награды за задание"""
    if 'awaiting_task_reward' in context.user_data and update.message:
        try:
            reward = float(update.message.text)
            
            if reward < 0:
                await update.message.reply_text("❌ Награда не может быть отрицательной!")
                return
            
            if reward > 10000:
                await update.message.reply_text("⚠️ Награда слишком большая! Максимум $10,000.")
                reward = 10000
            
            context.user_data['task_reward'] = reward
            context.user_data['awaiting_task_deadline'] = True
            del context.user_data['awaiting_task_reward']
            
            await update.message.reply_text(
                f"💰 **Награда:** ${reward}\n\n"
                f"Введите срок выполнения задания в днях:\n\n"
                f"💡 *Рекомендуется: 1-30 дней*"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму!")

async def handle_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка срока задания"""
    if 'awaiting_task_deadline' in context.user_data and update.message:
        try:
            deadline_days = int(update.message.text)
            
            if deadline_days < 1 or deadline_days > 30:
                await update.message.reply_text("❌ Срок должен быть от 1 до 30 дней!")
                return
            
            # Создаем задание
            org_id = context.user_data['task_org_id']
            creator_id = context.user_data['task_creator_id']
            title = context.user_data['task_title']
            description = context.user_data['task_description']
            reward = context.user_data['task_reward']
            
            success, message = org_system.create_org_task(org_id, creator_id, title, description, reward, deadline_days)
            
            await update.message.reply_text(message)
            
            # Очищаем состояние
            keys_to_delete = [
                'task_org_id', 'task_creator_id', 'task_title', 
                'task_description', 'task_reward', 'awaiting_task_deadline'
            ]
            for key in keys_to_delete:
                if key in context.user_data:
                    del context.user_data[key]
            
        except ValueError:
            await update.message.reply_text("❌ Введите корректное число!")

async def view_organization_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика организаций"""
    query = update.callback_query
    await query.answer()
    
    conn = get_conn()
    c = conn.cursor()
    
    # Получаем статистику всех организаций
    c.execute('''SELECT name, members, budget, reputation, type FROM organizations 
                ORDER BY members DESC, budget DESC''')
    orgs = c.fetchall()
    
    conn.close()
    
    stats_text = "📊 **СТАТИСТИКА ОРГАНИЗАЦИЙ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for org in orgs:
        name, members, budget, reputation, org_type = org
        emoji = {
            'government': '🏛️',
            'police': '🚨',
            'hospital': '🏥',
            'court': '⚖️',
            'bank': '🏦',
            'education': '🎓',
            'fbi': '🕵️',
            'tax': '🧾',
        }.get(org_type, '🏢')
        
        stats_text += f"{emoji} **{name}**\n"
        stats_text += f"   👥 {members} членов | 💰 ${budget:,.0f}\n"
        stats_text += f"   ⭐ {reputation}/100 репутация\n"
        stats_text += "━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data="orgs_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

# ==================== БИЗНЕСЫ ====================

async def businesses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        org_system.mark_task_progress(query.from_user.id, "open_biz", 1)
    text = (
        "🏪 **БИЗНЕСЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Список бизнесов", callback_data="biz_list")],
        [InlineKeyboardButton("➕ Создать бизнес", callback_data="biz_create")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def businesses_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_system.mark_task_progress(query.from_user.id, "open_biz", 1)
    businesses = org_system.list_businesses()
    text = "🏪 **СПИСОК БИЗНЕСОВ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not businesses:
        text += "Пока нет ни одного бизнеса."
    else:
        for biz in businesses:
            pid = biz.get('property_id')
            tag = f" | здание #{pid}" if pid else ""
            keyboard.append([InlineKeyboardButton(f"{biz['name']} ({biz['type']}{tag})", callback_data=f"biz_view_{biz['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="biz_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def business_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    biz_id = int(query.data.split("_")[-1])
    biz = org_system.get_business(biz_id)
    if not biz:
        await query.edit_message_text("❌ Бизнес не найден!", reply_markup=back_markup("biz_list", "🔙 К списку"))
        return

    members = org_system.get_business_members(biz_id, limit=200)
    user_id = query.from_user.id
    is_member = any(m['user_id'] == user_id for m in members)
    is_owner = biz['owner_id'] == user_id

    text = (
        f"🏪 **{biz['name']}**\n"
        f"Тип: {biz['type']}\n"
        f"Бюджет: ${biz['budget']:,.0f}\n"
        f"Здание: #{biz.get('property_id') or '—'}\n"
        f"Оснащение: {biz.get('equipment_level', 1)}/5\n"
        f"Локация: {biz['location'] or 'не указана'}\n"
        f"Статус: {biz['status']}\n\n"
        f"{biz['description'] or ''}"
    )

    keyboard = []
    if is_owner:
        keyboard.append([InlineKeyboardButton("📋 Заявки", callback_data=f"biz_apps_{biz_id}")])
        keyboard.append([InlineKeyboardButton("💵 Собрать прибыль", callback_data=f"biz_collect_{biz_id}")])
    elif not is_member:
        keyboard.append([InlineKeyboardButton("📝 Подать заявку", callback_data=f"biz_apply_{biz_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="biz_list")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def business_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_business_name'] = True
    await query.edit_message_text(
        "➕ **СОЗДАНИЕ БИЗНЕСА**\n\n"
        "Важно: сначала должно быть куплено свободное коммерческое здание.\n\n"
        "Введите название бизнеса:",
        parse_mode='Markdown',
        reply_markup=back_markup("biz_menu", "🔙 Отмена")
    )

async def handle_business_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_name' in context.user_data and update.message:
        name = update.message.text.strip()
        if len(name) < 3:
            await update.message.reply_text("❌ Слишком короткое название.")
            return
        context.user_data['business_name'] = name
        context.user_data['awaiting_business_type'] = True
        del context.user_data['awaiting_business_name']
        await update.message.reply_text("Введите тип бизнеса (например: магазин, кафе, логистика):")

async def handle_business_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_type' in context.user_data and update.message:
        btype = update.message.text.strip()
        if len(btype) < 3:
            await update.message.reply_text("❌ Тип слишком короткий.")
            return
        context.user_data['business_type'] = btype
        context.user_data['awaiting_business_desc'] = True
        del context.user_data['awaiting_business_type']
        await update.message.reply_text("Введите описание бизнеса:")

async def handle_business_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_desc' in context.user_data and update.message:
        desc = update.message.text.strip()
        if len(desc) < 10:
            await update.message.reply_text("❌ Описание слишком короткое.")
            return
        context.user_data['business_desc'] = desc
        context.user_data['awaiting_business_property'] = True
        del context.user_data['awaiting_business_desc']

        props = org_system.get_owned_properties(update.effective_user.id, only_free=True, commercial_only=True)
        if not props:
            await update.message.reply_text(
                "❌ У вас нет свободного коммерческого здания. Сначала купите его в разделе недвижимости.",
                reply_markup=back_markup("prop_menu", "🏠 В недвижимость")
            )
            for key in ['business_name', 'business_type', 'business_desc', 'awaiting_business_property']:
                if key in context.user_data:
                    del context.user_data[key]
            return

        lines = ["🏢 Выберите ID здания для бизнеса (только ваши свободные коммерческие объекты):"]
        for p in props[:15]:
            lines.append(f"• ID {p['id']} — {p['name']} ({p['location']})")
        await update.message.reply_text("\n".join(lines))

async def handle_business_property(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_property' not in context.user_data or not update.message:
        return
    try:
        property_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите числовой ID здания.")
        return

    ok, msg = org_system._property_available_for_facility(update.effective_user.id, property_id)
    if not ok:
        await update.message.reply_text(msg)
        return

    context.user_data['business_property_id'] = property_id
    context.user_data['awaiting_business_equipment'] = True
    del context.user_data['awaiting_business_property']
    await update.message.reply_text(
        "Введите уровень оснащения 1-5 (чем выше, тем дороже запуск):\n"
        "1 = базовый, 5 = премиум."
    )

async def handle_business_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_equipment' not in context.user_data or not update.message:
        return
    try:
        equipment_level = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число от 1 до 5.")
        return

    equipment_level = max(1, min(5, equipment_level))
    user_id = update.effective_user.id
    name = context.user_data.get('business_name')
    btype = context.user_data.get('business_type')
    desc = context.user_data.get('business_desc')
    property_id = context.user_data.get('business_property_id')
    success, message, _biz_id = org_system.create_business(
        user_id, name, btype, desc, property_id, equipment_level=equipment_level
    )
    await update.message.reply_text(message)
    for key in [
        'business_name', 'business_type', 'business_desc', 'business_property_id',
        'awaiting_business_equipment', 'awaiting_business_property'
    ]:
        if key in context.user_data:
            del context.user_data[key]

async def business_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    biz_id = int(query.data.split("_")[-1])
    context.user_data['business_apply_id'] = biz_id
    context.user_data['awaiting_business_application_text'] = True
    await query.edit_message_text(
        "📝 Введите текст заявки на работу в бизнесе:",
        reply_markup=back_markup(f"biz_view_{biz_id}", "🔙 Отмена")
    )

async def handle_business_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_business_application_text' in context.user_data and update.message:
        text = update.message.text.strip()
        biz_id = context.user_data['business_apply_id']
        user_id = update.effective_user.id
        success, message, app_id = org_system.apply_to_business(user_id, biz_id, text)
        await update.message.reply_text(message)

        if success and app_id:
            biz = org_system.get_business(biz_id)
            if biz and biz['owner_id']:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🟢 Одобрить", callback_data=f"biz_app_{app_id}_approve"),
                    InlineKeyboardButton("🔴 Отклонить", callback_data=f"biz_app_{app_id}_reject")
                ]])
                try:
                    await context.bot.send_message(
                        chat_id=biz['owner_id'],
                        text=f"🏪 Новая заявка в {biz['name']}:\n{text}",
                        reply_markup=keyboard
                    )
                except Exception:
                    pass

        if 'awaiting_business_application_text' in context.user_data:
            del context.user_data['awaiting_business_application_text']
        if 'business_apply_id' in context.user_data:
            del context.user_data['business_apply_id']

async def business_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    biz_id = int(query.data.split("_")[-1])
    biz = org_system.get_business(biz_id)
    if not biz or biz['owner_id'] != query.from_user.id:
        await query.edit_message_text("❌ Нет доступа.", reply_markup=back_markup("biz_menu", "🔙 В бизнесы"))
        return

    apps = org_system.get_pending_business_applications(biz_id)
    if not apps:
        await query.edit_message_text("📭 Заявок нет.", reply_markup=back_markup(f"biz_view_{biz_id}", "🔙 К бизнесу"))
        return

    await query.edit_message_text("📋 Заявки отправлены в этот чат.", reply_markup=back_markup(f"biz_view_{biz_id}", "🔙 К бизнесу"))
    for app in apps:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🟢 Одобрить", callback_data=f"biz_app_{app['id']}_approve"),
            InlineKeyboardButton("🔴 Отклонить", callback_data=f"biz_app_{app['id']}_reject")
        ]])
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"Заявка от {app['full_name']}:\n{app['application_text']}",
            reply_markup=keyboard
        )

async def business_application_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    app_id = int(parts[2])
    decision = 'approve' if parts[3] == 'approve' else 'reject'
    success, message, user_id = org_system.process_business_application(app_id, query.from_user.id, decision)
    await query.edit_message_text(message, reply_markup=back_markup("biz_menu", "🔙 В бизнесы"))
    if success and user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🏪 Ваша заявка в бизнес рассмотрена: {message}"
            )
        except Exception:
            pass

async def business_collect_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    biz_id = int(query.data.split("_")[-1])
    success, message = org_system.collect_business_income(biz_id, query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup(f"biz_view_{biz_id}", "🔙 К бизнесу"))

# ==================== ЧАСТНЫЕ ОРГАНИЗАЦИИ ====================

async def private_orgs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        org_system.mark_task_progress(query.from_user.id, "open_priv", 1)
    text = (
        "🏢 **ЧАСТНЫЕ ОРГАНИЗАЦИИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Список", callback_data="priv_list")],
        [InlineKeyboardButton("➕ Создать", callback_data="priv_create")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def private_orgs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_system.mark_task_progress(query.from_user.id, "open_priv", 1)
    orgs = org_system.list_private_orgs()
    text = "🏢 **СПИСОК ЧАСТНЫХ ОРГАНИЗАЦИЙ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not orgs:
        text += "Пока нет организаций."
    else:
        for org in orgs:
            pid = org.get('property_id')
            tag = f" | здание #{pid}" if pid else ""
            keyboard.append([InlineKeyboardButton(f"{org['name']}{tag}", callback_data=f"priv_view_{org['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="priv_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def private_org_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_id = int(query.data.split("_")[-1])
    org = org_system.get_private_org(org_id)
    if not org:
        await query.edit_message_text("❌ Организация не найдена!", reply_markup=back_markup("priv_list", "🔙 К списку"))
        return

    user_id = query.from_user.id
    text = (
        f"🏢 **{org['name']}**\n"
        f"Бюджет: ${org['budget']:,.0f}\n"
        f"Здание: #{org.get('property_id') or '—'}\n"
        f"Оснащение: {org.get('equipment_level', 1)}/5\n"
        f"Политика: {org['policy'] or 'не указана'}\n\n"
        f"{org['description'] or ''}"
    )
    keyboard = []
    if org['leader_id'] == user_id:
        keyboard.append([InlineKeyboardButton("📋 Заявки", callback_data=f"priv_apps_{org_id}")])
    else:
        keyboard.append([InlineKeyboardButton("📝 Подать заявку", callback_data=f"priv_apply_{org_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="priv_list")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def private_org_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_priv_name'] = True
    await query.edit_message_text(
        "➕ **СОЗДАНИЕ ОРГАНИЗАЦИИ**\n\n"
        "Важно: нужна свободная коммерческая недвижимость.\n"
        "Запуск организации стоит в 5 раз дороже бизнеса.\n\n"
        "Введите название:",
        parse_mode='Markdown',
        reply_markup=back_markup("priv_menu", "🔙 Отмена")
    )

async def handle_private_org_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_name' in context.user_data and update.message:
        name = update.message.text.strip()
        if len(name) < 3:
            await update.message.reply_text("❌ Название слишком короткое.")
            return
        context.user_data['priv_name'] = name
        context.user_data['awaiting_priv_policy'] = True
        del context.user_data['awaiting_priv_name']
        await update.message.reply_text("Введите политику/миссию организации:")

async def handle_private_org_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_policy' in context.user_data and update.message:
        policy = update.message.text.strip()
        context.user_data['priv_policy'] = policy
        context.user_data['awaiting_priv_desc'] = True
        del context.user_data['awaiting_priv_policy']
        await update.message.reply_text("Введите описание организации:")

async def handle_private_org_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_desc' in context.user_data and update.message:
        desc = update.message.text.strip()
        if len(desc) < 10:
            await update.message.reply_text("❌ Описание слишком короткое.")
            return
        context.user_data['priv_desc'] = desc
        context.user_data['awaiting_priv_property'] = True
        del context.user_data['awaiting_priv_desc']

        props = org_system.get_owned_properties(update.effective_user.id, only_free=True, commercial_only=True)
        if not props:
            await update.message.reply_text(
                "❌ У вас нет свободного коммерческого здания. Сначала купите его в разделе недвижимости.",
                reply_markup=back_markup("prop_menu", "🏠 В недвижимость")
            )
            for key in ['priv_name', 'priv_policy', 'priv_desc', 'awaiting_priv_property']:
                if key in context.user_data:
                    del context.user_data[key]
            return

        lines = ["🏢 Выберите ID здания для организации (ваши свободные коммерческие объекты):"]
        for p in props[:15]:
            lines.append(f"• ID {p['id']} — {p['name']} ({p['location']})")
        await update.message.reply_text("\n".join(lines))

async def handle_private_org_property(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_property' not in context.user_data or not update.message:
        return
    try:
        property_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите числовой ID здания.")
        return

    ok, msg = org_system._property_available_for_facility(update.effective_user.id, property_id)
    if not ok:
        await update.message.reply_text(msg)
        return

    context.user_data['priv_property_id'] = property_id
    context.user_data['awaiting_priv_equipment'] = True
    del context.user_data['awaiting_priv_property']
    await update.message.reply_text(
        "Введите уровень оснащения 1-5 (для организации стоимость = x5 от бизнеса):"
    )

async def handle_private_org_equipment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_equipment' not in context.user_data or not update.message:
        return
    try:
        equipment_level = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число от 1 до 5.")
        return
    equipment_level = max(1, min(5, equipment_level))

    user_id = update.effective_user.id
    success, message, _org_id = org_system.create_private_org(
        user_id,
        context.user_data.get('priv_name'),
        context.user_data.get('priv_desc'),
        context.user_data.get('priv_policy'),
        context.user_data.get('priv_property_id'),
        equipment_level=equipment_level
    )
    await update.message.reply_text(message)
    for key in [
        'priv_name', 'priv_policy', 'priv_desc', 'priv_property_id',
        'awaiting_priv_equipment', 'awaiting_priv_property'
    ]:
        if key in context.user_data:
            del context.user_data[key]

async def private_org_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_id = int(query.data.split("_")[-1])
    context.user_data['priv_apply_id'] = org_id
    context.user_data['awaiting_priv_application'] = True
    await query.edit_message_text(
        "📝 Введите текст заявки:",
        reply_markup=back_markup(f"priv_view_{org_id}", "🔙 Отмена")
    )

async def handle_private_org_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_priv_application' in context.user_data and update.message:
        text = update.message.text.strip()
        org_id = context.user_data['priv_apply_id']
        user_id = update.effective_user.id
        success, message, app_id = org_system.apply_to_private_org(user_id, org_id, text)
        await update.message.reply_text(message)

        if success and app_id:
            org = org_system.get_private_org(org_id)
            if org and org['leader_id']:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🟢 Одобрить", callback_data=f"priv_app_{app_id}_approve"),
                    InlineKeyboardButton("🔴 Отклонить", callback_data=f"priv_app_{app_id}_reject")
                ]])
                try:
                    await context.bot.send_message(
                        chat_id=org['leader_id'],
                        text=f"🏢 Новая заявка в {org['name']}:\n{text}",
                        reply_markup=keyboard
                    )
                except Exception:
                    pass

        for key in ['awaiting_priv_application', 'priv_apply_id']:
            if key in context.user_data:
                del context.user_data[key]

async def private_org_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    org_id = int(query.data.split("_")[-1])
    org = org_system.get_private_org(org_id)
    if not org or org['leader_id'] != query.from_user.id:
        await query.edit_message_text("❌ Нет доступа.", reply_markup=back_markup("priv_menu", "🔙 К организациям"))
        return
    apps = org_system.get_pending_private_org_applications(org_id)
    if not apps:
        await query.edit_message_text("📭 Заявок нет.", reply_markup=back_markup(f"priv_view_{org_id}", "🔙 К организации"))
        return
    await query.edit_message_text("📋 Заявки отправлены в чат.", reply_markup=back_markup(f"priv_view_{org_id}", "🔙 К организации"))
    for app in apps:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🟢 Одобрить", callback_data=f"priv_app_{app['id']}_approve"),
            InlineKeyboardButton("🔴 Отклонить", callback_data=f"priv_app_{app['id']}_reject")
        ]])
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"Заявка от {app['full_name']}:\n{app['application_text']}",
            reply_markup=keyboard
        )

async def private_org_application_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    app_id = int(parts[2])
    decision = 'approve' if parts[3] == 'approve' else 'reject'
    success, message, user_id = org_system.process_private_org_application(app_id, query.from_user.id, decision)
    await query.edit_message_text(message, reply_markup=back_markup("priv_menu", "🔙 К организациям"))
    if success and user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🏢 Ваша заявка рассмотрена: {message}"
            )
        except Exception:
            pass

# ==================== БАНДЫ ====================

async def gangs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    text = (
        "🕶️ **БАНДЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Список банд", callback_data="gang_list")],
        [InlineKeyboardButton("➕ Создать банду", callback_data="gang_create")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def gangs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gangs = org_system.list_gangs()
    text = "🕶️ **СПИСОК БАНД**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not gangs:
        text += "Пока нет банд."
    else:
        for gang in gangs:
            keyboard.append([InlineKeyboardButton(gang['name'], callback_data=f"gang_view_{gang['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="gang_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def gang_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gang_id = int(query.data.split("_")[-1])
    gang = org_system.get_gang(gang_id)
    if not gang:
        await query.edit_message_text("❌ Банда не найдена!", reply_markup=back_markup("gang_list", "🔙 К списку"))
        return
    user_id = query.from_user.id
    user_gang = org_system.get_user_gang(user_id)
    is_member = user_gang and user_gang['id'] == gang_id
    text = (
        f"🕶️ **{gang['name']}**\n"
        f"Территория: {gang['territory'] or 'не указана'}\n"
        f"Репутация: {gang['reputation']}\n"
        f"Статус: {gang['status']}"
    )
    keyboard = []
    if is_member:
        keyboard.append([InlineKeyboardButton("⚔️ Нападение", callback_data="gang_attack")])
    else:
        keyboard.append([InlineKeyboardButton("📝 Подать заявку", callback_data=f"gang_apply_{gang_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="gang_list")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def gang_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_gang_name'] = True
    await query.edit_message_text(
        "➕ **СОЗДАНИЕ БАНДЫ**\n\nВведите название:",
        parse_mode='Markdown',
        reply_markup=back_markup("gang_menu", "🔙 Отмена")
    )

async def handle_gang_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_gang_name' in context.user_data and update.message:
        name = update.message.text.strip()
        if len(name) < 3:
            await update.message.reply_text("❌ Название слишком короткое.")
            return
        context.user_data['gang_name'] = name
        context.user_data['awaiting_gang_territory'] = True
        del context.user_data['awaiting_gang_name']
        await update.message.reply_text("Введите территорию банды:")

async def handle_gang_territory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_gang_territory' in context.user_data and update.message:
        territory = update.message.text.strip()
        user_id = update.effective_user.id
        success, message, gang_id = org_system.create_gang(user_id, context.user_data['gang_name'], territory)
        await update.message.reply_text(message)
        for key in ['gang_name', 'awaiting_gang_territory']:
            if key in context.user_data:
                del context.user_data[key]

async def gang_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gang_id = int(query.data.split("_")[-1])
    context.user_data['gang_apply_id'] = gang_id
    context.user_data['awaiting_gang_application'] = True
    await query.edit_message_text(
        "📝 Введите текст заявки в банду:",
        reply_markup=back_markup(f"gang_view_{gang_id}", "🔙 Отмена")
    )

async def handle_gang_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_gang_application' in context.user_data and update.message:
        text = update.message.text.strip()
        gang_id = context.user_data['gang_apply_id']
        user_id = update.effective_user.id
        success, message, app_id = org_system.apply_to_gang(user_id, gang_id, text)
        await update.message.reply_text(message)

        if success and app_id:
            gang = org_system.get_gang(gang_id)
            if gang and gang['leader_id']:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🟢 Одобрить", callback_data=f"gang_app_{app_id}_approve"),
                    InlineKeyboardButton("🔴 Отклонить", callback_data=f"gang_app_{app_id}_reject")
                ]])
                try:
                    await context.bot.send_message(
                        chat_id=gang['leader_id'],
                        text=f"🕶️ Новая заявка в {gang['name']}:\n{text}",
                        reply_markup=keyboard
                    )
                except Exception:
                    pass

        for key in ['awaiting_gang_application', 'gang_apply_id']:
            if key in context.user_data:
                del context.user_data[key]

async def gang_application_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    app_id = int(parts[2])
    decision = 'approve' if parts[3] == 'approve' else 'reject'
    success, message, user_id = org_system.process_gang_application(app_id, query.from_user.id, decision)
    await query.edit_message_text(message, reply_markup=back_markup("gang_menu", "🔙 К бандам"))
    if success and user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🕶️ Ваша заявка рассмотрена: {message}"
            )
        except Exception:
            pass

async def gang_attack_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text(
            "❌ Нет доступных целей.",
            reply_markup=back_markup("gang_menu", "🔙 К бандам")
        )
        return
    if 'awaiting_gang_attack_target' in context.user_data:
        del context.user_data['awaiting_gang_attack_target']
    await query.edit_message_text(
        "⚔️ **НАПАДЕНИЕ БАНДЫ**\n\nВыберите цель:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_gangatk_", "gang_menu", "🔙 К бандам")
    )


async def select_gang_attack_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.replace("pick_gangatk_", "", 1))
    target = org_system.get_user(target_id)
    if not target:
        await query.edit_message_text("❌ Цель не найдена.", reply_markup=back_markup("gang_attack", "🔙 К выбору"))
        return
    if target_id == query.from_user.id:
        await query.edit_message_text("❌ Нельзя выбрать себя.", reply_markup=back_markup("gang_attack", "🔙 К выбору"))
        return
    context.user_data['gang_attack_target'] = target_id
    context.user_data['awaiting_gang_attack_severity'] = True
    await query.edit_message_text(
        f"🎯 Цель: {target.get('full_name', 'Игрок')}\n\n"
        "Укажите тяжесть: `light` / `medium` / `severe` / `critical` / `kill`",
        parse_mode='Markdown',
        reply_markup=back_markup("gang_menu", "🔙 К бандам")
    )

async def handle_gang_attack_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_gang_attack_target' in context.user_data and update.message:
        try:
            target_id = int(update.message.text.strip())
            context.user_data['gang_attack_target'] = target_id
            context.user_data['awaiting_gang_attack_severity'] = True
            del context.user_data['awaiting_gang_attack_target']
            await update.message.reply_text("Укажите тяжесть: light / medium / severe / critical / kill")
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID.")

async def handle_gang_attack_severity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_gang_attack_severity' in context.user_data and update.message:
        severity_raw = update.message.text.strip().lower()
        mapping = {
            'легкая': 'light', 'light': 'light',
            'средняя': 'medium', 'medium': 'medium',
            'тяжелая': 'severe', 'severe': 'severe',
            'критическая': 'critical', 'critical': 'critical',
            'убить': 'kill', 'kill': 'kill'
        }
        severity = mapping.get(severity_raw)
        if not severity:
            await update.message.reply_text("❌ Укажите: light/medium/severe/critical/kill.")
            return

        target_id = context.user_data['gang_attack_target']
        success, message = org_system.gang_attack(update.effective_user.id, target_id, severity)
        await update.message.reply_text(message)

        for key in ['gang_attack_target', 'awaiting_gang_attack_severity']:
            if key in context.user_data:
                del context.user_data[key]

# ==================== СУД ====================

async def court_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    text = (
        "⚖️ **СУД**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("📝 Подать иск", callback_data="court_create")],
        [InlineKeyboardButton("📂 Мои дела", callback_data="court_list")],
        [InlineKeyboardButton("🏛 Очередь суда", callback_data="court_queue")],
        [InlineKeyboardButton("📎 Доказательства", callback_data="court_evidence")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def court_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text(
            "❌ Нет доступных ответчиков.",
            reply_markup=back_markup("court_menu", "🔙 В суд")
        )
        return
    if 'awaiting_court_defendant' in context.user_data:
        del context.user_data['awaiting_court_defendant']
    await query.edit_message_text(
        "📝 **ПОДАТЬ ИСК**\n\nВыберите ответчика:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_courtdef_", "court_menu", "🔙 В суд")
    )


async def select_court_defendant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    defendant_id = int(query.data.replace("pick_courtdef_", "", 1))
    if defendant_id == query.from_user.id:
        await query.edit_message_text("❌ Нельзя подать иск на себя.", reply_markup=back_markup("court_create", "🔙 К выбору"))
        return
    defendant = org_system.get_user(defendant_id)
    if not defendant:
        await query.edit_message_text("❌ Игрок не найден.", reply_markup=back_markup("court_create", "🔙 К выбору"))
        return
    context.user_data['court_defendant_id'] = defendant_id
    context.user_data['awaiting_court_description'] = True
    await query.edit_message_text(
        f"⚖️ Ответчик: {defendant.get('full_name', 'Игрок')}\n\n"
        "Опишите суть иска:",
        reply_markup=back_markup("court_menu", "🔙 В суд")
    )

async def handle_court_defendant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_court_defendant' in context.user_data and update.message:
        try:
            defendant_id = int(update.message.text.strip())
            context.user_data['court_defendant_id'] = defendant_id
            context.user_data['awaiting_court_description'] = True
            del context.user_data['awaiting_court_defendant']
            await update.message.reply_text("Опишите суть иска:")
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID.")

async def handle_court_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_court_description' in context.user_data and update.message:
        description = update.message.text.strip()
        plaintiff_id = update.effective_user.id
        defendant_id = context.user_data['court_defendant_id']
        case_id, case_number = org_system.create_court_case(plaintiff_id, defendant_id, description)

        court_org = org_system.get_organization('Суд')
        members = org_system.get_organization_members(court_org['id'], limit=50) if court_org else []

        if members:
            for member in members:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🟢 Принять", callback_data=f"court_accept_{case_id}"),
                    InlineKeyboardButton("🔴 Отклонить", callback_data=f"court_reject_{case_id}")
                ]])
                try:
                    await context.bot.send_message(
                        chat_id=member['user_id'],
                        text=f"⚖️ Новое дело {case_number}\nИстец: {plaintiff_id}\nОтветчик: {defendant_id}\n\n{description}",
                        reply_markup=keyboard
                    )
                except Exception:
                    pass
            await update.message.reply_text("✅ Иск подан. Ожидайте решения суда.")
        else:
            await update.message.reply_text(
                "ℹ️ Сейчас нет доступных судей. Дело сохранено и ждет ручного решения."
            )

        for key in ['court_defendant_id', 'awaiting_court_description']:
            if key in context.user_data:
                del context.user_data[key]

async def court_list_cases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cases = org_system.list_user_cases(query.from_user.id)
    text = "⚖️ **МОИ ДЕЛА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not cases:
        text += "Пока нет дел."
    else:
        for c in cases:
            text += f"#{c[1]} — {c[2]} ({c[3][:10]})\n"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="court_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def court_review_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_org = org_system.get_user_organization(query.from_user.id)
    if not user_org or user_org.get('name') != 'Суд':
        await query.edit_message_text(
            "❌ Очередь суда доступна только сотрудникам суда.",
            reply_markup=back_markup("court_menu", "🔙 В суд")
        )
        return

    cases = org_system.list_open_court_cases(limit=20)
    text = "🏛 **ОЧЕРЕДЬ СУДА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not cases:
        text += "📭 Открытых дел нет."
    else:
        for case in cases[:10]:
            text += (
                f"#{case['id']} {case['case_number']}\n"
                f"Истец: {case['plaintiff_id']} | Ответчик: {case['defendant_id']}\n"
                f"{case['description'][:120]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([
                InlineKeyboardButton("🟢 Принять", callback_data=f"court_accept_{case['id']}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"court_reject_{case['id']}")
            ])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="court_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def court_evidence_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cases = org_system.list_user_cases(query.from_user.id, limit=20)
    if not cases:
        await query.edit_message_text(
            "📭 У вас нет дел для добавления доказательств.",
            reply_markup=back_markup("court_menu", "🔙 В суд")
        )
        return

    if 'awaiting_court_evidence_case' in context.user_data:
        del context.user_data['awaiting_court_evidence_case']

    text = "📎 **ВЫБЕРИТЕ ДЕЛО**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for case in cases[:12]:
        case_id, case_number, status, opened_date = case
        text += f"• {case_number} ({status})\n"
        keyboard.append([InlineKeyboardButton(f"📎 {case_number}", callback_data=f"pick_cevid_{case_id}")])
    keyboard.append([InlineKeyboardButton("🔙 В суд", callback_data="court_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def select_court_evidence_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    case_id = int(query.data.replace("pick_cevid_", "", 1))
    context.user_data['court_evidence_case_id'] = case_id
    context.user_data['awaiting_court_evidence_text'] = True
    await query.edit_message_text(
        "Введите текст доказательств:",
        reply_markup=back_markup("court_menu", "🔙 В суд")
    )

async def handle_court_evidence_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_court_evidence_case' in context.user_data and update.message:
        try:
            case_id = int(update.message.text.strip())
            context.user_data['court_evidence_case_id'] = case_id
            context.user_data['awaiting_court_evidence_text'] = True
            del context.user_data['awaiting_court_evidence_case']
            await update.message.reply_text("Введите текст доказательств:")
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID дела.")

async def handle_court_evidence_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_court_evidence_text' in context.user_data and update.message:
        case_id = context.user_data['court_evidence_case_id']
        text = update.message.text.strip()
        success, message = org_system.add_case_evidence(case_id, update.effective_user.id, text)
        await update.message.reply_text(message)
        for key in ['court_evidence_case_id', 'awaiting_court_evidence_text']:
            if key in context.user_data:
                del context.user_data[key]

async def court_case_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    case_id = int(parts[2])
    if parts[1] == "accept":
        org_system.assign_case(case_id, query.from_user.id)
        context.user_data['awaiting_court_verdict'] = case_id
        await query.edit_message_text(
            "Введите вердикт и штраф через | (пример: Виновен | 5000)",
            reply_markup=back_markup("court_menu", "🔙 В суд")
        )
    else:
        org_system.close_case(case_id, "Отклонено", "Суд отклонил дело", 0)
        await query.edit_message_text("❌ Дело отклонено.", reply_markup=back_markup("court_menu", "🔙 В суд"))

async def handle_court_verdict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_court_verdict' in context.user_data and update.message:
        case_id = context.user_data['awaiting_court_verdict']
        parts = [p.strip() for p in update.message.text.split("|")]
        verdict = parts[0] if parts else "Решение суда"
        fine = 0
        if len(parts) > 1:
            try:
                fine = float(parts[1])
            except ValueError:
                fine = 0
        org_system.close_case(case_id, verdict, "Приговор вынесен", fine)
        await update.message.reply_text("✅ Вердикт вынесен.")
        del context.user_data['awaiting_court_verdict']

# ==================== ЗАПРОС ЛЕЧЕНИЯ ====================

async def request_treatment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    user = org_system.get_user(user_id) or {}

    async def respond(text: str, reply_markup=None):
        if query:
            if reply_markup is None:
                reply_markup = back_markup("back_to_main", "🔙 В меню")
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, reply_markup=reply_markup)

    if user.get('life_state', 'alive') == 'dead':
        await respond("❌ Вы мертвы. Лечение невозможно.")
        return
    if user.get('life_state', 'alive') == 'alive' and not user.get('injury_severity'):
        await respond("✅ Вам не требуется лечение.")
        return

    hospital = org_system.get_organization('Больница')
    doctors = org_system.get_organization_members(hospital['id'], limit=50) if hospital else []

    if doctors:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🟢 Принять", callback_data=f"treat_accept_{user_id}"),
            InlineKeyboardButton("🔴 Отказать", callback_data=f"treat_reject_{user_id}")
        ]])
        for doctor in doctors:
            try:
                await context.bot.send_message(
                    chat_id=doctor['user_id'],
                    text=f"🏥 Запрос на лечение от игрока {user_id}. Травма: {user.get('injury_severity')}",
                    reply_markup=keyboard
                )
            except Exception:
                pass
        await respond("✅ Запрос отправлен врачам. Ожидайте ответа.")
    else:
        await respond("ℹ️ Сейчас нет врачей. Попробуйте отправить запрос позже для ручного рассмотрения.")

async def treatment_request_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    patient_id = int(parts[2])
    if parts[1] == "accept":
        context.user_data['treatment_patient_id'] = patient_id
        context.user_data['awaiting_diagnosis'] = True
        await query.edit_message_text(
            "✅ Запрос принят. Введите диагноз пациента.",
            reply_markup=back_markup("my_org_panel", "🔙 В панель")
        )
    else:
        await query.edit_message_text("❌ Запрос отклонен.", reply_markup=back_markup("my_org_panel", "🔙 В панель"))

# ==================== ОБУЧЕНИЕ И ЗАДАНИЯ ====================

TUTORIAL_STEPS = [
    {
        "title": "Добро пожаловать!",
        "text": "Это симуляция государства, где решения принимают игроки. Начнем с основ.",
        "button": ("🏛️ Организации", "orgs_main")
    },
    {
        "title": "Организации",
        "text": "Вступайте в гос. организации, чтобы влиять на мир: банк, полиция, суд и т.д.",
        "button": ("🏛️ Открыть организации", "orgs_main")
    },
    {
        "title": "Экономика",
        "text": "Вы можете открыть бизнес, вступить в частную организацию или покупать недвижимость.",
        "button": ("🏪 Бизнесы", "biz_menu")
    },
    {
        "title": "Финансы",
        "text": "Банк выдает кредиты. Все заявки рассматривают реальные игроки.",
        "button": ("🏦 Заявка на кредит", "loan_request")
    },
    {
        "title": "Безопасность",
        "text": "Полиция, суд и банды влияют на порядок. В банде можно ранить или убить.",
        "button": ("🕶️ Банды", "gang_menu")
    },
    {
        "title": "Готово!",
        "text": "Вы прошли обучение. Забирайте награду и выполняйте задания новичка.",
        "button": ("🧾 Мои задания", "player_tasks")
    }
]

def _tutorial_keyboard(step_index):
    keyboard = []
    step = TUTORIAL_STEPS[step_index]
    if step.get("button"):
        label, callback = step["button"]
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    if step_index < len(TUTORIAL_STEPS) - 1:
        keyboard.append([InlineKeyboardButton("➡️ Дальше", callback_data="tutorial_next")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Завершить", callback_data="tutorial_finish")])
    keyboard.append([InlineKeyboardButton("⏭️ Пропустить обучение", callback_data="tutorial_skip")])
    return InlineKeyboardMarkup(keyboard)

async def tutorial_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    org_system.update_user(user_id, tutorial_step=0, tutorial_completed=0)
    step = 0
    text = f"🎓 **ОБУЧЕНИЕ**\n\n**{TUTORIAL_STEPS[step]['title']}**\n{TUTORIAL_STEPS[step]['text']}"
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=_tutorial_keyboard(step), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=_tutorial_keyboard(step), parse_mode='Markdown')

async def tutorial_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = org_system.get_user(query.from_user.id) or {}
    step = int(user.get('tutorial_step', 0)) + 1
    if step >= len(TUTORIAL_STEPS):
        step = len(TUTORIAL_STEPS) - 1
    org_system.update_user(query.from_user.id, tutorial_step=step)
    text = f"🎓 **ОБУЧЕНИЕ**\n\n**{TUTORIAL_STEPS[step]['title']}**\n{TUTORIAL_STEPS[step]['text']}"
    await query.edit_message_text(text, reply_markup=_tutorial_keyboard(step), parse_mode='Markdown')

async def tutorial_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = org_system.get_user(user_id) or {}
    if not user.get('tutorial_completed'):
        org_system.update_user(user_id, tutorial_completed=1)
        org_system.update_user(user_id, balance=user.get('balance', 0) + 2000, reputation=min(100, user.get('reputation', 50) + 5))
    await query.edit_message_text(
        "✅ Обучение завершено! Вы получили $2000 и +5 репутации.\n\nОткройте задания новичка.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧾 Мои задания", callback_data="player_tasks")]])
    )

async def tutorial_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    org_system.update_user(user_id, tutorial_completed=1)
    await query.edit_message_text(
        "Обучение пропущено. Вы всегда можете вернуться из меню.",
        reply_markup=back_markup("back_to_main", "🔙 В меню")
    )

async def player_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = query.from_user.id if query else update.effective_user.id
    tasks = org_system.list_player_tasks(user_id)
    text = "🧾 **МОИ ЗАДАНИЯ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not tasks:
        text += "Пока нет заданий."
    else:
        for t in tasks:
            status = "✅" if t['status'] == 'claimed' else "⏳"
            text += f"{status} **{t['title']}**\n{t['description']}\nПрогресс: {t['progress']}/{t['goal']} | Награда: ${t['reward']}\n\n"
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = query.from_user.id if query else update.effective_user.id
    user = org_system.get_user(user_id) or {}
    text = (
        "👤 **ПРОФИЛЬ ИГРОКА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"ID: {user_id}\n"
        f"Имя: {user.get('full_name', 'Неизвестно')}\n"
        f"Баланс: ${user.get('balance', 0):,.0f}\n"
        f"Репутация: {user.get('reputation', 50)}\n"
        f"Состояние: {user.get('life_state', 'alive')}\n"
        f"Травма: {user.get('injury_severity') or 'нет'}\n"
        f"Организация: {user.get('organization') or 'нет'}\n"
        f"Должность: {user.get('role') or 'нет'}"
    )
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== РАБОТА И МИТИНГИ ====================

async def citizen_work_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = query.from_user.id if query else update.effective_user.id
    user = org_system.get_user(user_id) or {}
    pending = org_system.get_user_pending_job_application(user_id)

    pending_text = ""
    if pending:
        pending_text = (
            "\n"
            f"📨 HR-заявка: #{pending['id']} ({pending['job_title']})\n"
            "Статус: на ручной проверке\n"
        )

    text = (
        "💼 **ГРАЖДАНСКАЯ РАБОТА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Текущая работа: {user.get('citizen_job') or 'нет'}\n"
        f"Оклад: ${float(user.get('citizen_salary', 0) or 0):,.0f}/мес\n"
        f"Последняя смена: {(user.get('last_job_shift') or '—')[:10]}\n\n"
        f"{pending_text}"
        "Выберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Вакансии", callback_data="work_jobs")],
        [InlineKeyboardButton("🧾 Отдел кадров", callback_data="work_hr")],
        [InlineKeyboardButton("🎓 Учёба", callback_data="edu_menu")],
        [InlineKeyboardButton("🛠 Отработать смену", callback_data="work_shift")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
    ]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def citizen_work_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    jobs = org_system.list_citizen_jobs()
    text = "📋 **ВАКАНСИИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for job in jobs:
        text += (
            f"• **{job['title']}** — ${job['salary']}/мес\n"
            f"  Требования: 🎓 {job['edu_required']}+ | ⭐ {int(job['rep_required'])}+\n"
        )
        keyboard.append([InlineKeyboardButton(f"📨 Подать заявку: {job['title']}", callback_data=f"work_take_{job['code']}")])
    text += "\nℹ️ Все заявки принимает кадровый отдел (игроки)."
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="work_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def citizen_take_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job_code = query.data.replace("work_take_", "", 1)
    job = org_system.get_citizen_job(job_code)
    if not job:
        await query.edit_message_text("❌ Вакансия не найдена.", reply_markup=back_markup("work_jobs", "🔙 К вакансиям"))
        return

    context.user_data['work_apply_job_code'] = job_code
    context.user_data['awaiting_job_application_text'] = True
    await query.edit_message_text(
        (
            f"📨 **HR-заявка: {job['title']}**\n\n"
            "Напишите мотивацию для отдела кадров (минимум 8 символов):"
        ),
        parse_mode='Markdown',
        reply_markup=back_markup("work_jobs", "🔙 Отмена")
    )

async def handle_job_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_job_application_text' not in context.user_data or not update.message:
        return

    job_code = context.user_data.get('work_apply_job_code')
    text = update.message.text.strip()
    user_id = update.effective_user.id
    success, message, app_id = org_system.apply_for_citizen_job(user_id, job_code, text)

    for key in ['awaiting_job_application_text', 'work_apply_job_code']:
        if key in context.user_data:
            del context.user_data[key]

    if not success:
        await update.message.reply_text(message)
        return

    hr_org = org_system.get_organization('Правительство')
    hr_members = org_system.get_organization_members(hr_org['id'], limit=50) if hr_org else []
    notified = 0

    job = org_system.get_citizen_job(job_code) or {}
    for hr in hr_members:
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🟢 Одобрить", callback_data=f"work_hr_approve_{app_id}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"work_hr_reject_{app_id}")
            ]])
            await context.bot.send_message(
                chat_id=hr['user_id'],
                text=(
                    "🧾 **НОВАЯ HR-ЗАЯВКА**\n\n"
                    f"👤 Кандидат ID: {user_id}\n"
                    f"💼 Вакансия: {job.get('title', job_code)}\n"
                    f"💰 Оклад: ${float(job.get('salary', 0) or 0):,.0f}/мес\n"
                    f"📝 Мотивация: {text[:500]}"
                ),
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            notified += 1
        except Exception:
            pass

    if notified:
        await update.message.reply_text("✅ HR-заявка отправлена. Ожидайте решения отдела кадров.")
    else:
        await update.message.reply_text(
            "ℹ️ HR-заявка сохранена. Сейчас нет кадровиков онлайн, заявка останется в очереди."
        )

async def work_hr_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not org_system.is_hr_reviewer(user_id):
        await query.edit_message_text(
            "❌ Доступ только сотрудникам Правительства (отдел кадров).",
            reply_markup=back_markup("work_menu", "🔙 К работе")
        )
        return

    apps = org_system.get_pending_job_applications(limit=20)
    text = "🧾 **ОТДЕЛ КАДРОВ — ЗАЯВКИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not apps:
        text += "📭 Нет заявок на трудоустройство."
    else:
        for app in apps[:10]:
            text += (
                f"#{app['id']} | 👤 {app['full_name']} (ID {app['user_id']})\n"
                f"💼 {app['job_title']} | 💰 ${app['expected_salary']:,.0f}/мес\n"
                f"🎓 {app['education']} | ⭐ {int(app['reputation'])}\n"
                f"📝 {app['application_text'][:120]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([
                InlineKeyboardButton("🟢 Одобрить", callback_data=f"work_hr_approve_{app['id']}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"work_hr_reject_{app['id']}")
            ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="work_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def work_hr_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    if len(parts) != 4:
        await query.edit_message_text(
            "❌ Некорректные данные HR-заявки.",
            reply_markup=back_markup("work_hr", "🔙 К заявкам")
        )
        return

    decision = 'approve' if parts[2] == 'approve' else 'reject'
    app_id = int(parts[3])
    success, message, target_user_id = org_system.process_job_application(app_id, query.from_user.id, decision)
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 К HR-заявкам", callback_data="work_hr")],
            [InlineKeyboardButton("🔙 К работе", callback_data="work_menu")]
        ])
    )
    if target_user_id:
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"💼 Решение по вашей HR-заявке: {message}"
            )
        except Exception:
            pass

async def citizen_work_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    success, message = org_system.work_citizen_shift(query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup("work_menu", "🔙 К работе"))

async def education_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = query.from_user.id if query else update.effective_user.id
    user = org_system.get_user(user_id) or {}
    active = org_system.get_user_active_enrollment(user_id)
    pending = org_system.get_user_pending_education_application(user_id)
    is_teacher = org_system.is_teacher_reviewer(user_id)

    # Check teacher application status
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT status FROM teacher_applications WHERE user_id = ?', (user_id,))
    teacher_app = c.fetchone()
    conn.close()
    teacher_app_status = teacher_app[0] if teacher_app else None

    text = (
        "🎓 **ОБРАЗОВАНИЕ И УЧЕБА**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ваш уровень образования: {int(user.get('education', 1) or 1)}\n"
        f"Репутация: {float(user.get('reputation', 50) or 50):.1f}\n\n"
    )
    if active:
        text += (
            f"📘 Активная программа: {active['program_name']}\n"
            f"Прогресс: {active['progress_days']}/{active['duration_days']} дней\n"
            f"Последняя учеба: {(active.get('last_study_date') or '—')[:10]}\n\n"
        )
    elif pending:
        text += f"📨 Заявка в обработке: #{pending['id']} ({pending['program_name']})\n\n"
    else:
        text += "📭 Активных программ нет.\n\n"

    if is_teacher:
        text += "👨‍🏫 **Вы преподаватель!** Можете проверять работы студентов.\n\n"
    else:
        text += "📌 *Преподавателем вас может назначить только президент через систему назначения.*\n\n"

    keyboard = [
        [InlineKeyboardButton("📚 Программы", callback_data="edu_programs")],
        [InlineKeyboardButton("📖 Учиться сегодня", callback_data="edu_study")],
    ]
    
    # Кнопка для применения на должность преподавателя удалена
    # Теперь преподавателем назначает только президент через систему назначения
    keyboard.append([InlineKeyboardButton("ℹ️ Как стать преподавателем?", callback_data="edu_how_to_teach")])
    
    if is_teacher:
        keyboard.append([InlineKeyboardButton("📋 Учительская", callback_data="edu_teacher")])
    
    keyboard.extend([
        [InlineKeyboardButton("🔙 К работе", callback_data="work_menu")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def education_programs_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    programs = org_system.list_education_programs(only_active=True)
    text = "📚 **УЧЕБНЫЕ ПРОГРАММЫ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not programs:
        text += "Сейчас нет открытых программ."
    else:
        for p in programs:
            text += (
                f"#{p['id']} **{p['name']}**\n"
                f"⏳ Длительность: {p['duration_days']} дней\n"
                f"💰 Стоимость: ${p['tuition_fee']:,.0f}\n"
                f"🎓 Мин. образование: {p['min_education']}+\n"
                f"⭐ Мин. репутация: {int(p['min_reputation'])}+\n"
                f"📝 {p['description'][:120]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([InlineKeyboardButton(f"📨 Подать заявку: {p['name']}", callback_data=f"edu_apply_{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def education_apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    program_id = int(query.data.split("_")[-1])
    program = org_system.get_education_program(program_id)
    if not program:
        await query.edit_message_text("❌ Программа не найдена.", reply_markup=back_markup("edu_programs", "🔙 К программам"))
        return

    context.user_data['edu_apply_program_id'] = program_id
    context.user_data['awaiting_education_application_text'] = True
    await query.edit_message_text(
        (
            f"📨 **Заявка на программу: {program['name']}**\n\n"
            "Напишите, почему вы хотите учиться (минимум 8 символов):"
        ),
        parse_mode='Markdown',
        reply_markup=back_markup("edu_programs", "🔙 Отмена")
    )

async def handle_education_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_education_application_text' not in context.user_data or not update.message:
        return

    program_id = int(context.user_data.get('edu_apply_program_id'))
    text = update.message.text.strip()
    user_id = update.effective_user.id
    success, message, app_id = org_system.apply_for_education(user_id, program_id, text)

    for key in ['awaiting_education_application_text', 'edu_apply_program_id']:
        if key in context.user_data:
            del context.user_data[key]

    if not success:
        await update.message.reply_text(message)
        return

    university = org_system.get_organization('Университет')
    teachers = org_system.get_organization_members(university['id'], limit=50) if university else []
    notified = 0
    program = org_system.get_education_program(program_id) or {}
    for teacher in teachers:
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🟢 Одобрить", callback_data=f"edu_app_approve_{app_id}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"edu_app_reject_{app_id}")
            ]])
            await context.bot.send_message(
                chat_id=teacher['user_id'],
                text=(
                    "👩‍🏫 **НОВАЯ ЗАЯВКА НА ОБУЧЕНИЕ**\n\n"
                    f"👤 Кандидат ID: {user_id}\n"
                    f"📚 Программа: {program.get('name', program_id)}\n"
                    f"📝 Мотивация: {text[:500]}"
                ),
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            notified += 1
        except Exception:
            pass

    if notified:
        await update.message.reply_text("✅ Заявка на учебу отправлена преподавателям.")
    else:
        await update.message.reply_text("ℹ️ Заявка сохранена. Сейчас нет преподавателей для ручной проверки.")

async def education_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    teacher_id = query.from_user.id
    if not org_system.is_teacher_reviewer(teacher_id):
        await query.edit_message_text(
            "❌ Доступ только сотрудникам Университета.",
            reply_markup=back_markup("edu_menu", "🔙 К учебе")
        )
        return

    apps = org_system.get_pending_education_applications(limit=20)
    students = org_system.get_teacher_students(teacher_id, limit=10)
    text = "👩‍🏫 **УЧИТЕЛЬСКАЯ ПАНЕЛЬ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []

    text += "📨 **Новые заявки:**\n"
    if not apps:
        text += "Нет заявок.\n"
    else:
        for app in apps[:8]:
            text += (
                f"#{app['id']} | 👤 {app['full_name']} (ID {app['user_id']})\n"
                f"📚 {app['program_name']} | 💰 ${app['tuition_fee']:,.0f}\n"
                f"🎓 {app['education']} | ⭐ {int(app['reputation'])} | Баланс ${app['balance']:,.0f}\n"
                f"📝 {app['application_text'][:120]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([
                InlineKeyboardButton("🟢 Одобрить", callback_data=f"edu_app_approve_{app['id']}"),
                InlineKeyboardButton("🔴 Отклонить", callback_data=f"edu_app_reject_{app['id']}")
            ])

    text += "\n📘 **Ваши студенты:**\n"
    if not students:
        text += "Пока нет закрепленных студентов."
    else:
        for s in students:
            text += (
                f"• {s['full_name']} ({s['program_name']}) "
                f"{s['progress_days']}/{s['duration_days']} [{s['status']}]\n"
            )

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def education_application_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    if len(parts) != 4:
        await query.edit_message_text("❌ Некорректные данные заявки.", reply_markup=back_markup("edu_teacher", "🔙 К учительской"))
        return
    decision = 'approve' if parts[2] == 'approve' else 'reject'
    app_id = int(parts[3])
    success, message, target_user_id = org_system.process_education_application(app_id, query.from_user.id, decision)
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👩‍🏫 К учительской", callback_data="edu_teacher")],
            [InlineKeyboardButton("🔙 К учебе", callback_data="edu_menu")]
        ])
    )
    if target_user_id:
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎓 Решение по вашей учебной заявке: {message}"
            )
        except Exception:
            pass

async def education_study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    active = org_system.get_user_active_enrollment(user_id)
    
    if not active:
        await query.edit_message_text("❌ У вас нет активной программы обучения.", reply_markup=back_markup("edu_menu", "🔙 К учебе"))
        return
    
    # Show choice menu for study method
    text = (
        f"📖 **СПОСОБ ОБУЧЕНИЯ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📘 Программа: {active['program_name']}\n"
        f"⏳ Прогресс: {active['progress_days']}/{active['duration_days']} дней\n\n"
        "Выберите способ обучения сегодня:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📚 Теория", callback_data="edu_study_theory")],
        [InlineKeyboardButton("🔬 Практика", callback_data="edu_study_practice")],
        [InlineKeyboardButton("👥 Групповые занятия", callback_data="edu_study_group")],
        [InlineKeyboardButton("🔙 Обратно", callback_data="edu_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def education_study_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data.split("_")[-1]  # 'theory', 'practice', or 'group'
    
    success, message = org_system.study_education_day(user_id, choice)
    
    keyboard = [
        [InlineKeyboardButton("📖 Учиться еще", callback_data="edu_study")],
        [InlineKeyboardButton("🔙 К учебе", callback_data="edu_menu")]
    ]
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def education_apply_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = org_system.get_user(user_id) or {}
    user_edu = int(user.get('education', 1) or 1)
    user_rep = float(user.get('reputation', 50) or 50)
    
    text = (
        "👩‍🏫 **ЗАЯВКА НА ДОЛЖНОСТЬ ПРЕПОДАВАТЕЛЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Требования:**\n"
        "• Образование: 3+\n"
        "• Репутация: 50+\n\n"
        f"**Ваши показатели:**\n"
        f"• Образование: {user_edu} {'✅' if user_edu >= 3 else '❌'}\n"
        f"• Репутация: {user_rep:.1f} {'✅' if user_rep >= 50 else '❌'}\n\n"
    )
    
    if user_edu < 3 or user_rep < 50:
        text += "❌ Вы не соответствуете требованиям. Повысьте образование и репутацию."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")]]
    else:
        text += "Напишите, почему вы хотите быть преподавателем (минимум 15 символов):"
        context.user_data['awaiting_teacher_application_text'] = True
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="edu_menu")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_teacher_application_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_teacher_application_text' not in context.user_data or not update.message:
        return
    
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    success, message = org_system.apply_for_teacher_position(user_id, text)
    
    if 'awaiting_teacher_application_text' in context.user_data:
        del context.user_data['awaiting_teacher_application_text']
    
    keyboard = [
        [InlineKeyboardButton("🔙 К учебе", callback_data="edu_menu")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # Notify existing teachers
    if success:
        university = org_system.get_organization('Университет')
        teachers = org_system.get_organization_members(university['id'], limit=50) if university else []
        notified = 0
        for teacher in teachers:
            try:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🟢 Одобрить", callback_data=f"edu_teacher_approve_{user_id}"),
                    InlineKeyboardButton("🔴 Отклонить", callback_data=f"edu_teacher_reject_{user_id}")
                ]])
                user = org_system.get_user(user_id) or {}
                await context.bot.send_message(
                    chat_id=teacher['user_id'],
                    text=(
                        "👩‍🏫 **НОВАЯ ЗАЯВКА НА ПРЕПОДАВАТЕЛЯ**\n\n"
                        f"👤 Кандидат ID: {user_id}\n"
                        f"📝 Мотивация: {text[:500]}\n"
                        f"🎓 Образование: {int(user.get('education', 1))}\n"
                        f"⭐ Репутация: {float(user.get('reputation', 50)):.1f}"
                    ),
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                notified += 1
            except Exception:
                pass

async def education_teacher_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    teacher_id = query.from_user.id
    if not org_system.is_teacher_reviewer(teacher_id):
        await query.edit_message_text("❌ Доступ только преподавателям.", reply_markup=back_markup("edu_menu", "🔙 К учебе"))
        return
    
    applications = org_system.get_pending_teacher_applications(limit=10)
    text = "👩‍🏫 **ЗАЯВКИ НА ПРЕПОДАВАТЕЛЯ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    
    if not applications:
        text += "Нет ожидающих заявок."
    else:
        for app in applications:
            text += (
                f"#{app['id']} **{app['full_name']}** (ID: {app['user_id']})\n"
                f"Образование: {app['education']}, Репутация: {app['reputation']:.1f}\n"
                f"Мотивация: {app['application_text'][:80]}...\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([InlineKeyboardButton(f"Рассмотреть #{app['id']}", callback_data=f"edu_teacher_app_view_{app['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 К учительской", callback_data="edu_teacher")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def education_teacher_app_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    teacher_id = query.from_user.id
    if not org_system.is_teacher_reviewer(teacher_id):
        await query.edit_message_text("❌ Доступ только преподавателям.", reply_markup=back_markup("edu_teacher", "🔙 К учительской"))
        return
    
    parts = query.data.split("_")
    if len(parts) < 5:
        return
    
    decision = parts[3]  # 'approve' or 'reject'
    user_id = int(parts[4])
    
    if decision == 'approve':
        success, message = org_system.approve_teacher_application(user_id, teacher_id)
    else:
        success, message = org_system.reject_teacher_application(user_id, teacher_id)
    
    keyboard = [
        [InlineKeyboardButton("📋 Другие заявки", callback_data="edu_teacher_applications")],
        [InlineKeyboardButton("🔙 К учительской", callback_data="edu_teacher")]
    ]
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    if success:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"👩‍🏫 {message}"
            )
        except Exception:
            pass

async def education_how_to_teach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = (
        "🤔 **КАК СТАТЬ ПРЕПОДАВАТЕЛЕМ?**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Есть два пути стать преподавателем:\n\n"
        "**Путь 1️⃣ - Прямое назначение**\n"
        "Вступите в организацию 'Университет' мембером. Требования:\n"
        "• Образование 5+\n"
        "• Репутация 85+\n"
        "• Научные публикации\n\n"
        "**Путь 2️⃣ - Заявка на преподавателя (новое!)**\n"
        "Подайте заявку, и существующие преподаватели рассмотрят её.\n"
        "Требования для заявки:\n"
        "• Образование 3+\n"
        "• Репутация 50+\n\n"
        "✅ При одобрении вы сможете:\n"
        "• Проверять заявки студентов\n"
        "• Управлять программами\n"
        "• Воспитывать будущее поколение"
    )

    keyboard = [
        [InlineKeyboardButton("📝 Подать заявку", callback_data="edu_apply_teacher")],
        [InlineKeyboardButton("🎓 К 'Университету'", callback_data="org_view_education")],
        [InlineKeyboardButton("🔙 Назад", callback_data="edu_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ==================== СИСТЕМА ПРАВЛЕНИЯ ====================

async def government_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню правительства"""
    query = update.callback_query
    if query:
        await query.answer()
    
    gov_system = org_system.get_government_system()
    user_id = query.from_user.id if query else update.effective_user.id
    user_org = org_system.get_user_organization(user_id)
    
    text = (
        "🏛️ **СИСТЕМА ПРАВЛЕНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 **Текущий тип правления:** {gov_system['current_type'].capitalize()}\n"
        f"🏛️ **Установлена:** {gov_system['established_date'][:10]}\n"
        f"🛡️ **Стабильность:** {gov_system['stability']}/100\n"
        f"😈 **Коррупция:** {gov_system['corruption']}/100\n"
        f"😊 **Удовлетворение:** {gov_system['public_satisfaction']}/100\n\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🗳️ ВЫБОРЫ ПРЕЗИДЕНТА", callback_data="elections_vote")],
        [InlineKeyboardButton("📣 Активные революции", callback_data="revolutions_list")],
        [InlineKeyboardButton("🚩 Начать восстание", callback_data="start_revolution")],
    ]
    
    # Если это президент
    if user_org and user_org['role'] in ['Президент', 'Лидер', 'Глава']:
        keyboard.insert(0, [InlineKeyboardButton("📋 Создать закон", callback_data="create_rule")])
        keyboard.insert(1, [InlineKeyboardButton("📜 Мои законы", callback_data="my_rules")])
        keyboard.insert(2, [InlineKeyboardButton("👷‍♂️ Назначить на должность", callback_data="appoint_menu")])
    
    keyboard.extend([
        [InlineKeyboardButton("📨 Письма", callback_data="messages_menu")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def create_rule_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await government_laws_menu(update, context)


async def my_rules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT law_number, title, status, votes_for, votes_against, proposed_date
                 FROM laws
                 WHERE proposed_by = ?
                 ORDER BY proposed_date DESC
                 LIMIT 20''', (user_id,))
    rows = c.fetchall()
    conn.close()
    text = "📜 **МОИ ЗАКОНЫ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "Пока нет созданных законопроектов."
    else:
        for law in rows:
            text += (
                f"• **{law[0]}** — {law[1]}\n"
                f"  Статус: {law[2]} | 👍 {law[3]} / 👎 {law[4]}\n"
                f"  Дата: {(law[5] or '')[:10]}\n"
            )
    keyboard = [
        [InlineKeyboardButton("📋 К законам", callback_data="gov_laws")],
        [InlineKeyboardButton("🔙 В правление", callback_data="government_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def elections_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню голосования на выборах"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    # Получаем Правительство
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id FROM organizations WHERE name = ?', ('Правительство',))
    gov = c.fetchone()
    
    if not gov:
        conn.close()
        await query.edit_message_text("❌ Правительство не найдено!")
        return
    
    gov_id = gov[0]
    c.execute("SELECT * FROM elections WHERE org_id = ? AND status = ?", (gov_id, 'active'))
    elections = c.fetchall()
    
    if not elections or len(elections) == 0:
        conn.close()
        text = "🗳️ **ВЫБОРЫ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "❌ Активных выборов нет."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="government_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Показываем список активных выборов (берем первые активные выборы)
    election = elections[0]
    election_id = election[0]
    
    text = (
        "🗳️ **ПРЕЗИДЕНТСКИЕ ВЫБОРЫ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Получаем кандидатов
    c.execute('''SELECT ec.id, ec.election_id, ec.candidate_id, ec.votes, ec.program, u.full_name
                 FROM election_candidates ec
                 JOIN users u ON ec.candidate_id = u.user_id
                 WHERE ec.election_id = ?
                 ORDER BY ec.votes DESC''', (election_id,))
    candidates = c.fetchall()
    conn.close()
    
    keyboard = []
    
    if not candidates or len(candidates) == 0:
        text += "📋 **Кандидатов пока нет.**\n\n"
    else:
        text += f"📋 **Кандидаты:** ({len(candidates)})\n\n"
        for idx, cand in enumerate(candidates):
            candidate_id = cand[2]
            votes = cand[3]
            full_name = cand[5]
            
            text += f"#{idx+1} **{full_name}** — {votes} голос{'ов' if votes != 1 else 'а'}\n"
            keyboard.append([InlineKeyboardButton(f"🗳️ {full_name} ({votes})", 
                                                  callback_data=f"vote_for_{candidate_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="government_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def vote_for_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Голосование за кандидата"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    candidate_id = int(query.data.split("_")[2])
    
    # Проверяем, что пользователь существует
    user = org_system.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Пользователь не найден!")
        return
    
    # Добавляем голос за кандидата
    conn = get_conn()
    c = conn.cursor()
    
    # Проверяем, голосовал ли уже
    c.execute('''SELECT id FROM election_votes 
                 WHERE election_id IN (
                     SELECT id FROM elections WHERE org_id = (
                         SELECT id FROM organizations WHERE name = ?
                     ) AND status = ?
                 )
                 AND voter_id = ?''', ('Правительство', 'active', user_id))
    
    if c.fetchone():
        conn.close()
        await query.edit_message_text("❌ Вы уже проголосовали на этих выборах!")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="elections_vote")]]
        await query.edit_message_text("❌ Вы уже проголосовали на этих выборах!", 
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Получаем текущие выборы
    c.execute('''SELECT id FROM elections 
                 WHERE org_id = (SELECT id FROM organizations WHERE name = ?)
                 AND status = ?''', ('Правительство', 'active'))
    election = c.fetchone()
    
    if not election:
        conn.close()
        await query.edit_message_text("❌ Выборы не найдены!")
        return
    
    election_id = election[0]
    
    # Добавляем голос
    c.execute('''INSERT INTO election_votes (election_id, voter_id, candidate_id)
                 VALUES (?, ?, ?)''', (election_id, user_id, candidate_id))
    
    # Увеличиваем количество голосов для кандидата
    c.execute('''UPDATE election_candidates SET votes = votes + 1
                 WHERE election_id = ? AND candidate_id = ?''', (election_id, candidate_id))
    
    conn.commit()
    conn.close()
    
    # Получаем данные кандидата
    candidate = org_system.get_user(candidate_id)
    candidate_name = candidate.get('full_name', 'Неизвестно') if candidate else 'Неизвестно'
    
    text = (
        f"✅ **ВЫ ПРОГОЛОСОВАЛИ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Вы отдали свой голос кандидату:\n"
        f"👤 **{candidate_name}**\n\n"
        f"Спасибо за участие в выборах!"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 К выборам", callback_data="elections_vote")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def revolutions_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список активных революций"""
    query = update.callback_query
    await query.answer()
    
    revolutions = org_system.get_active_revolutions()
    text = "🚩 **АКТИВНЫЕ РЕВОЛЮЦИИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    keyboard = []
    
    if not revolutions:
        text += "Активных революций нет."
    else:
        for rev in revolutions:
            organizer = org_system.get_user(rev['organizer_id'])
            org_name = organizer.get('full_name', 'Неизвестно') if organizer else 'Неизвестно'
            
            text += (
                f"#{rev['id']} **{org_name}** требует перемен\n"
                f"📌 Причина: {rev['reason'][:100]}\n"
                f"👥 Поддержка: {rev['supporters']}/{rev['needed']}\n"
                f"🎯 Намерение: {rev['new_type'].capitalize()}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
            keyboard.append([InlineKeyboardButton(f"🎯 {rev['supporters']}/{rev['needed']} #{rev['id']}", 
                                                  callback_data=f"join_revolution_{rev['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="government_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def start_revolution_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню начала революции"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = org_system.get_user(user_id)
    
    text = (
        "🚩 **НАЧАТЬ РЕВОЛЮЦИЮ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите тип нового правления после революции:\n\n"
        "👑 **Монархия** - Власть одного правителя\n"
        "🗳️ **Демократия** - Власть народа через выборы\n"
        "🎯 **Диктатура** - Неограниченная личная власть\n"
        "⚔️ **Анархия** - Отсутствие центральной власти\n"
        "🏛️ **Аристократия** - Власть избранных"
    )
    
    keyboard = [
        [InlineKeyboardButton("👑 Монархия", callback_data="start_rev_monarchy"),
         InlineKeyboardButton("🗳️ Демократия", callback_data="start_rev_democracy")],
        [InlineKeyboardButton("🎯 Диктатура", callback_data="start_rev_dictatorship"),
         InlineKeyboardButton("⚔️ Анархия", callback_data="start_rev_anarchy")],
        [InlineKeyboardButton("🏛️ Аристократия", callback_data="start_rev_aristocracy")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="government_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_revolution_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gov_type = query.data.replace("start_rev_", "", 1)
    readable = {
        'monarchy': 'Монархия',
        'democracy': 'Демократия',
        'dictatorship': 'Диктатура',
        'anarchy': 'Анархия',
        'aristocracy': 'Аристократия',
    }.get(gov_type, gov_type)
    context.user_data['revolution_new_type'] = gov_type
    context.user_data['awaiting_revolution_reason'] = True
    await query.edit_message_text(
        f"🚩 **НОВОЕ ПРАВЛЕНИЕ: {readable}**\n\n"
        "Опишите причину восстания (минимум 16 символов):",
        parse_mode='Markdown',
        reply_markup=back_markup("government_menu", "🔙 В правление")
    )


async def handle_revolution_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_revolution_reason' not in context.user_data or not update.message:
        return
    reason = update.message.text.strip()
    if len(reason) < 16:
        await update.message.reply_text("❌ Причина слишком короткая. Опишите подробнее (16+).")
        return

    user_id = update.effective_user.id
    new_type = context.user_data.get('revolution_new_type', 'democracy')
    gov = org_system.get_organization('Правительство') or {}
    target_leader_id = gov.get('leader_id') or 0
    supporters_needed = 120  # игра сложнее: нужно больше поддержки

    success, message = org_system.start_revolution(
        user_id,
        target_leader_id,
        new_type,
        reason,
        supporters_needed=supporters_needed
    )

    await update.message.reply_text(message)
    for key in ['awaiting_revolution_reason', 'revolution_new_type']:
        if key in context.user_data:
            del context.user_data[key]

async def join_revolution_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединиться к революции"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    rev_id = int(parts[2])
    user_id = query.from_user.id
    
    success, message = org_system.join_revolution(rev_id, user_id)
    
    keyboard = [
        [InlineKeyboardButton("📋 Другие революции", callback_data="revolutions_list")],
        [InlineKeyboardButton("🔙 В меню", callback_data="government_menu")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== НАЗНАЧЕНИЕ НА ДОЛЖНОСТЬ ====================

async def appoint_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню назначения на должность (для президента)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = org_system.get_user(user_id)
    
    # Проверяем, что это президент
    user_org = org_system.get_user_organization(user_id)
    if not user_org or user_org['role'] not in ['Президент', 'Лидер', 'Глава']:
        await query.edit_message_text("❌ Только президент может назначать на должности!", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="government_menu")]]))
        return
    
    # Получаем список всех пользователей
    all_users = org_system.get_all_users()
    
    text = "👷‍♂️ **НАЗНАЧЕНИЕ НА ДОЛЖНОСТЬ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Выберите игрока для назначения:\n\n"
    
    keyboard = []
    for user_item in all_users:
        if user_item['id'] != user_id:  # Исключаем самого себя
            keyboard.append([InlineKeyboardButton(f"👤 {user_item['full_name']}", 
                                                  callback_data=f"appoint_user_{user_item['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="government_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def appoint_select_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор должности для назначения"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    target_user_id = int(parts[2])
    president_id = query.from_user.id
    
    target_user = org_system.get_user(target_user_id)
    if not target_user:
        await query.edit_message_text("❌ Пользователь не найден!")
        return
    
    # Получаем доступные организации и должности
    positions = ['Министр', 'Судья', 'Полицейский', 'Генерал', 'Священник', 'Учитель']
    
    text = f"👷‍♂️ **НАЗНАЧИТЬ {target_user['full_name'].upper()}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "Выберите должность:\n\n"
    
    keyboard = []
    for idx, position in enumerate(positions):
        keyboard.append([InlineKeyboardButton(f"📋 {position}", 
                                              callback_data=f"appoint_confirm_{target_user_id}_{idx}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="appoint_menu")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def appoint_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение назначения"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    target_user_id = int(parts[2])
    position_idx = int(parts[3])
    
    # Получаем должность по индексу
    positions = ['Министр', 'Судья', 'Полицейский', 'Генерал', 'Священник', 'Учитель']
    if position_idx < 0 or position_idx >= len(positions):
        await query.edit_message_text("❌ Неверная должность!")
        return
    
    position = positions[position_idx]
    
    president_id = query.from_user.id
    user_org = org_system.get_user_organization(president_id)
    
    if not user_org or user_org['role'] not in ['Президент', 'Лидер', 'Глава']:
        await query.edit_message_text("❌ Только президент может назначать!")
        return
    
    # Вызываем функцию назначения
    success, message = org_system.appoint_to_position(president_id, user_org['org_id'], target_user_id, position, salary=100)
    
    keyboard = [
        [InlineKeyboardButton("👷‍♂️ Ещё назначение", callback_data="appoint_menu")],
        [InlineKeyboardButton("🔙 В меню", callback_data="government_menu")]
    ]
    
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ==================== ПИСЬМА И СООБЩЕНИЯ ====================

async def messages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню писем"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = org_system.get_user(user_id)
    
    inbox_msgs = org_system.get_messages(user_id, 'inbox')
    unread_count = sum(1 for m in inbox_msgs if not m['read_date'])
    
    text = (
        "📨 **ПИСЬМА И СООБЩЕНИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 Входящие: {len(inbox_msgs)} (📭 Не прочитано: {unread_count})\n"
        f"📤 Отправленные: ?\n\n"
        "Выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"📥 Входящие ({unread_count} 🆕)", callback_data="view_inbox")],
        [InlineKeyboardButton("📤 Отправленные", callback_data="view_sent")],
        [InlineKeyboardButton("✉️ Написать письмо", callback_data="compose_message")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def view_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    inbox = org_system.get_messages(user_id, 'inbox')

    text = "📥 **ВХОДЯЩИЕ ПИСЬМА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not inbox:
        text += "📭 Входящих сообщений нет."
    else:
        for msg in inbox[:15]:
            mark = "🆕" if not msg.get('read_date') else "✅"
            text += (
                f"{mark} **{msg.get('subject') or 'Без темы'}**\n"
                f"От: {msg.get('sender_name') or 'Неизвестно'}\n"
                f"Дата: {(msg.get('created_date') or '')[:16]}\n"
                f"{(msg.get('content') or '')[:140]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )
            if not msg.get('read_date'):
                org_system.mark_message_read(msg['id'], user_id)

    keyboard = [
        [InlineKeyboardButton("✉️ Написать", callback_data="compose_message")],
        [InlineKeyboardButton("🔙 К письмам", callback_data="messages_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def view_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    sent = org_system.get_messages(user_id, 'sent')

    text = "📤 **ОТПРАВЛЕННЫЕ ПИСЬМА**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not sent:
        text += "📭 Отправленных сообщений нет."
    else:
        for msg in sent[:15]:
            text += (
                f"✅ **{msg.get('subject') or 'Без темы'}**\n"
                f"Кому: {msg.get('sender_name') or 'Неизвестно'}\n"
                f"Дата: {(msg.get('created_date') or '')[:16]}\n"
                f"{(msg.get('content') or '')[:140]}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )

    keyboard = [
        [InlineKeyboardButton("✉️ Написать", callback_data="compose_message")],
        [InlineKeyboardButton("🔙 К письмам", callback_data="messages_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def compose_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    players = org_system.list_recent_players(exclude_user_id=query.from_user.id, limit=20)
    if not players:
        await query.edit_message_text("❌ Нет получателей для выбора.", reply_markup=back_markup("messages_menu", "🔙 К письмам"))
        return
    await query.edit_message_text(
        "✉️ **НОВОЕ ПИСЬМО**\n\nВыберите получателя:",
        parse_mode='Markdown',
        reply_markup=player_picker_markup(players, "pick_msgto_", "messages_menu", "🔙 К письмам")
    )


async def select_message_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    recipient_id = int(query.data.replace("pick_msgto_", "", 1))
    recipient = org_system.get_user(recipient_id)
    if not recipient:
        await query.edit_message_text("❌ Получатель не найден.", reply_markup=back_markup("compose_message", "🔙 К выбору"))
        return
    context.user_data['message_recipient_id'] = recipient_id
    context.user_data['awaiting_message_subject'] = True
    await query.edit_message_text(
        f"📨 Получатель: {recipient.get('full_name', 'Игрок')}\n\nВведите тему письма:",
        reply_markup=back_markup("messages_menu", "🔙 К письмам")
    )


async def handle_message_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_message_subject' not in context.user_data or not update.message:
        return
    subject = update.message.text.strip()
    if len(subject) < 3:
        await update.message.reply_text("❌ Тема слишком короткая.")
        return
    context.user_data['message_subject'] = subject[:120]
    context.user_data['awaiting_message_content'] = True
    del context.user_data['awaiting_message_subject']
    await update.message.reply_text("Введите текст письма:")


async def handle_message_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_message_content' not in context.user_data or not update.message:
        return
    content = update.message.text.strip()
    if len(content) < 5:
        await update.message.reply_text("❌ Текст письма слишком короткий.")
        return
    sender_id = update.effective_user.id
    recipient_id = context.user_data.get('message_recipient_id')
    subject = context.user_data.get('message_subject', 'Без темы')
    msg_id = org_system.send_message(sender_id, recipient_id, subject, content[:2000], msg_type='private')
    await update.message.reply_text("✅ Письмо отправлено.")
    for key in ['awaiting_message_content', 'message_recipient_id', 'message_subject']:
        if key in context.user_data:
            del context.user_data[key]

# ==================== ФБР ФУНКЦИИ ====================

async def fbi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ФБР меню для читания писем"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_org = org_system.get_user_organization(user_id)
    
    if not user_org or user_org['name'] != 'ФБР':
        await query.edit_message_text("❌ Доступ только ФБР", reply_markup=back_markup("my_org_panel"))
        return
    
    intercepts = org_system.get_fbi_intercepted_messages()
    
    text = (
        "🕵️ **ФБР - ПЕРЕХВАЧЕННАЯ КОРРЕСПОНДЕНЦИЯ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Всего перехвачено: {len(intercepts)}\n\n"
    )
    
    keyboard = []
    for msg in intercepts[:15]:  # Show 15 most recent
        preview = msg['subject'][:30] if msg['subject'] else msg['content'][:30]
        keyboard.append([InlineKeyboardButton(
            f"📧 {msg['sender_name']} → {msg['recipient_name']}: {preview}...",
            callback_data=f"fbi_read_msg_{msg['message_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 К панели ФБР", callback_data="org_panel_fbi")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def protests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    text = (
        "📣 **МИТИНГИ**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Создавайте общественные инициативы и голосуйте за/против."
    )
    keyboard = [
        [InlineKeyboardButton("📋 Активные митинги", callback_data="protest_list")],
        [InlineKeyboardButton("➕ Создать митинг", callback_data="protest_create")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")],
    ]
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def protests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    protests = org_system.list_protests(status='active', limit=20)
    text = "📋 **АКТИВНЫЕ МИТИНГИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not protests:
        text += "Сейчас нет активных митингов."
    else:
        for p in protests:
            keyboard.append([InlineKeyboardButton(f"{p['title']} ({p['support_count']}/{p['against_count']})", callback_data=f"protest_view_{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="protest_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def protest_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    protest_id = int(query.data.split("_")[-1])
    protest = org_system.get_protest(protest_id)
    if not protest:
        await query.edit_message_text("❌ Митинг не найден.", reply_markup=back_markup("protest_list", "🔙 К списку"))
        return
    text = (
        f"📣 **{protest.get('title', 'Митинг')}**\n"
        f"Локация: {protest.get('location') or 'не указана'}\n"
        f"Статус: {protest.get('status')}\n"
        f"Поддержали: {protest.get('support_count', 0)}\n"
        f"Против: {protest.get('against_count', 0)}\n"
        f"Завершение: {(protest.get('end_date') or '')[:16]}\n\n"
        f"{protest.get('description') or ''}"
    )
    keyboard = []
    if protest.get('status') == 'active':
        keyboard.extend([
            [InlineKeyboardButton("👍 Поддержать", callback_data=f"protest_support_{protest_id}")],
            [InlineKeyboardButton("👎 Против", callback_data=f"protest_against_{protest_id}")],
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="protest_list")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def protest_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_protest_title'] = True
    await query.edit_message_text(
        "➕ **СОЗДАНИЕ МИТИНГА**\n\nВведите краткий заголовок:",
        parse_mode='Markdown',
        reply_markup=back_markup("protest_menu", "🔙 Отмена")
    )

async def handle_protest_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_protest_title' not in context.user_data or not update.message:
        return
    title = update.message.text.strip()
    if len(title) < 4:
        await update.message.reply_text("❌ Слишком короткий заголовок.")
        return
    context.user_data['protest_title'] = title
    context.user_data['awaiting_protest_desc'] = True
    del context.user_data['awaiting_protest_title']
    await update.message.reply_text("Введите описание митинга:")

async def handle_protest_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_protest_desc' not in context.user_data or not update.message:
        return
    desc = update.message.text.strip()
    if len(desc) < 10:
        await update.message.reply_text("❌ Описание слишком короткое.")
        return
    context.user_data['protest_desc'] = desc
    context.user_data['awaiting_protest_location'] = True
    del context.user_data['awaiting_protest_desc']
    await update.message.reply_text("Введите локацию митинга:")

async def handle_protest_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_protest_location' not in context.user_data or not update.message:
        return
    location = update.message.text.strip()
    if len(location) < 2:
        await update.message.reply_text("❌ Слишком короткая локация.")
        return
    success, message, protest_id = org_system.create_protest(
        update.effective_user.id,
        context.user_data.get('protest_title'),
        context.user_data.get('protest_desc'),
        location
    )
    if success:
        await update.message.reply_text(f"{message}\nID: {protest_id}")
    else:
        await update.message.reply_text(message)
    for key in ['protest_title', 'protest_desc', 'awaiting_protest_location']:
        if key in context.user_data:
            del context.user_data[key]

async def protest_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    stance = parts[1]
    protest_id = int(parts[2])
    success, message = org_system.join_protest(protest_id, query.from_user.id, stance=stance)
    await query.edit_message_text(message, reply_markup=back_markup(f"protest_view_{protest_id}", "🔙 К митингу"))

# ==================== НЕДВИЖИМОСТЬ ====================

async def property_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "🏠 **НЕДВИЖИМОСТЬ**\n━━━━━━━━━━━━━━━━━━━━\n\nВыберите действие:"
    keyboard = [
        [InlineKeyboardButton("🏘️ Список объектов", callback_data="prop_list")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def property_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    props = org_system.list_properties()
    text = "🏠 **ОБЪЕКТЫ НЕДВИЖИМОСТИ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not props:
        text += "Пока нет объектов."
    else:
        for p in props:
            status = "✅ свободен" if not p['owner_id'] else "🔒 продан"
            kind = "🏢 комм." if p.get('category') == 'commercial' else "🏠 жил."
            keyboard.append([InlineKeyboardButton(f"{p['name']} ({kind}, {status})", callback_data=f"prop_view_{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="prop_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def property_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[-1])
    prop = org_system.get_property(prop_id)
    if not prop:
        await query.edit_message_text("❌ Объект не найден!", reply_markup=back_markup("prop_list", "🔙 К объектам"))
        return
    text = (
        f"🏠 **{prop['name']}**\n"
        f"Категория: {'Коммерческая' if prop.get('category') == 'commercial' else 'Жилая'}\n"
        f"Цена: ${prop['price']:,.0f}\n"
        f"Аренда: ${prop['rent']:,.0f}/день\n"
        f"Обслуживание: ${prop.get('maintenance_daily', 0):,.0f}/день\n"
        f"Состояние: {prop.get('condition', 100)}%\n"
        f"Локация: {prop['location']}\n"
        f"Статус: {'свободен' if not prop['owner_id'] else 'продан'}"
    )
    if prop.get('facility_type'):
        text += f"\nЗанято под: {prop['facility_type']} #{prop.get('facility_id')}"
    keyboard = []
    if not prop['owner_id']:
        keyboard.append([InlineKeyboardButton("🛒 Купить", callback_data=f"prop_buy_{prop['id']}")])
    elif prop['owner_id'] == query.from_user.id:
        keyboard.append([InlineKeyboardButton("💰 Собрать аренду", callback_data=f"prop_rent_{prop['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="prop_list")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def property_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[-1])
    success, message = org_system.buy_property(prop_id, query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup("prop_list", "🔙 К объектам"))

async def property_rent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[-1])
    success, message = org_system.collect_rent(prop_id, query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup(f"prop_view_{prop_id}", "🔙 К объекту"))

# ==================== КОНТРАКТНАЯ БИРЖА ====================

async def market_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = "📣 **КОНТРАКТНАЯ БИРЖА**\n━━━━━━━━━━━━━━━━━━━━\n\nВыберите действие:"
    keyboard = [
        [InlineKeyboardButton("📋 Контракты", callback_data="market_list")],
        [InlineKeyboardButton("➕ Создать контракт", callback_data="market_create")],
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def market_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contracts = org_system.list_open_contracts()
    text = "📣 **ОТКРЫТЫЕ КОНТРАКТЫ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    if not contracts:
        text += "Нет активных контрактов."
    else:
        for c in contracts:
            keyboard.append([InlineKeyboardButton(f"{c[1]} (${c[2]:,.0f})", callback_data=f"market_view_{c[0]}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="market_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def market_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contract_id = int(query.data.split("_")[-1])
    c = org_system.get_contract(contract_id)
    if not c:
        await query.edit_message_text("❌ Контракт не найден.", reply_markup=back_markup("market_list", "🔙 К контрактам"))
        return
    text = (
        f"📣 **{c[2]}**\n"
        f"Награда: ${c[4]:,.0f}\n"
        f"Статус: {c[5]}\n\n"
        f"{c[3]}"
    )
    keyboard = []
    if c[5] == 'open' and c[1] != query.from_user.id:
        keyboard.append([InlineKeyboardButton("🟢 Принять", callback_data=f"market_accept_{contract_id}")])
    if c[5] == 'in_progress' and c[1] == query.from_user.id:
        keyboard.append([InlineKeyboardButton("✅ Завершить", callback_data=f"market_complete_{contract_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="market_list")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def market_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['awaiting_contract_title'] = True
    await query.edit_message_text(
        "➕ **СОЗДАНИЕ КОНТРАКТА**\n\nВведите название:",
        parse_mode='Markdown',
        reply_markup=back_markup("market_menu", "🔙 Отмена")
    )

async def handle_contract_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_contract_title' in context.user_data and update.message:
        title = update.message.text.strip()
        if len(title) < 3:
            await update.message.reply_text("❌ Слишком короткое название.")
            return
        context.user_data['contract_title'] = title
        context.user_data['awaiting_contract_desc'] = True
        del context.user_data['awaiting_contract_title']
        await update.message.reply_text("Введите описание контракта:")

async def handle_contract_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_contract_desc' in context.user_data and update.message:
        desc = update.message.text.strip()
        if len(desc) < 10:
            await update.message.reply_text("❌ Описание слишком короткое.")
            return
        context.user_data['contract_desc'] = desc
        context.user_data['awaiting_contract_reward'] = True
        del context.user_data['awaiting_contract_desc']
        await update.message.reply_text("Введите награду ($):")

async def handle_contract_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_contract_reward' in context.user_data and update.message:
        try:
            reward = float(update.message.text)
            if reward <= 0:
                await update.message.reply_text("❌ Награда должна быть больше 0.")
                return
            user_id = update.effective_user.id
            success, message, contract_id = org_system.create_contract(
                user_id,
                context.user_data['contract_title'],
                context.user_data['contract_desc'],
                reward
            )
            if success:
                await update.message.reply_text(f"{message}\nID: {contract_id}")
                for key in ['contract_title', 'contract_desc', 'awaiting_contract_reward']:
                    if key in context.user_data:
                        del context.user_data[key]
            else:
                await update.message.reply_text(message)
        except ValueError:
            await update.message.reply_text("❌ Введите корректную сумму.")

async def market_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contract_id = int(query.data.split("_")[-1])
    contract = org_system.get_contract(contract_id)
    success, message = org_system.accept_contract(contract_id, query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup("market_list", "🔙 К контрактам"))
    if success and contract:
        try:
            await context.bot.send_message(
                chat_id=contract[1],
                text=f"📣 Ваш контракт принят игроком {query.from_user.id}."
            )
        except Exception:
            pass

async def market_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contract_id = int(query.data.split("_")[-1])
    contract = org_system.get_contract(contract_id)
    success, message = org_system.complete_contract(contract_id, query.from_user.id)
    await query.edit_message_text(message, reply_markup=back_markup("market_list", "🔙 К контрактам"))
    if success and contract and contract[6]:
        try:
            await context.bot.send_message(
                chat_id=contract[6],
                text=f"✅ Контракт #{contract_id} завершен и оплачен."
            )
        except Exception:
            pass

# ==================== БОНУС ДНЯ ====================

async def daily_bonus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    success, message = org_system.daily_bonus(user_id)
    if query:
        await query.answer()
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]]))
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="back_to_main")]]))

async def private_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state_handlers = [
        ("awaiting_application", process_application_text),
        ("awaiting_arrest_target", handle_arrest_target),
        ("awaiting_arrest_reason", handle_arrest_reason),
        ("awaiting_arrest_fine", handle_arrest_fine),
        ("awaiting_treatment_target", handle_treatment_target),
        ("awaiting_diagnosis", handle_diagnosis),
        ("awaiting_treatment", handle_treatment_plan),
        ("awaiting_cost", handle_treatment_cost),
        ("awaiting_loan_applicant", handle_loan_applicant),
        ("awaiting_loan_amount", handle_loan_amount),
        ("awaiting_loan_term", handle_loan_term),
        ("awaiting_loan_purpose", handle_loan_purpose),
        ("awaiting_loan_request_amount", handle_loan_request_amount),
        ("awaiting_loan_request_term", handle_loan_request_term),
        ("awaiting_loan_request_purpose", handle_loan_request_purpose),
        ("awaiting_election_position", handle_election_position),
        ("awaiting_election_description", handle_election_description),
        ("awaiting_nomination_program", handle_nomination_program),
        ("awaiting_report_text", handle_report_text),
        ("awaiting_business_name", handle_business_name),
        ("awaiting_business_type", handle_business_type),
        ("awaiting_business_desc", handle_business_description),
        ("awaiting_business_property", handle_business_property),
        ("awaiting_business_equipment", handle_business_equipment),
        ("awaiting_business_application_text", handle_business_application_text),
        ("awaiting_priv_name", handle_private_org_name),
        ("awaiting_priv_policy", handle_private_org_policy),
        ("awaiting_priv_desc", handle_private_org_desc),
        ("awaiting_priv_property", handle_private_org_property),
        ("awaiting_priv_equipment", handle_private_org_equipment),
        ("awaiting_priv_application", handle_private_org_application_text),
        ("awaiting_gang_name", handle_gang_name),
        ("awaiting_gang_territory", handle_gang_territory),
        ("awaiting_gang_application", handle_gang_application_text),
        ("awaiting_gang_attack_target", handle_gang_attack_target),
        ("awaiting_gang_attack_severity", handle_gang_attack_severity),
        ("awaiting_court_defendant", handle_court_defendant),
        ("awaiting_court_description", handle_court_description),
        ("awaiting_court_verdict", handle_court_verdict),
        ("awaiting_court_evidence_case", handle_court_evidence_case),
        ("awaiting_court_evidence_text", handle_court_evidence_text),
        ("awaiting_contract_title", handle_contract_title),
        ("awaiting_contract_desc", handle_contract_desc),
        ("awaiting_contract_reward", handle_contract_reward),
        ("awaiting_protest_title", handle_protest_title),
        ("awaiting_protest_desc", handle_protest_desc),
        ("awaiting_protest_location", handle_protest_location),
        ("awaiting_task_title", handle_task_title),
        ("awaiting_task_description", handle_task_description),
        ("awaiting_task_reward", handle_task_reward),
        ("awaiting_task_deadline", handle_task_deadline),
        ("awaiting_take_task_id", handle_take_task_id),
        ("awaiting_job_application_text", handle_job_application_text),
        ("awaiting_education_application_text", handle_education_application_text),
        ("awaiting_teacher_application_text", handle_teacher_application_text),
        ("awaiting_revolution_reason", handle_revolution_reason),
        ("awaiting_message_subject", handle_message_subject),
        ("awaiting_message_content", handle_message_content),
        ("awaiting_report_title", handle_report_title),
        ("awaiting_report_text", handle_report_text),
    ]

    for state_key, state_handler in state_handlers:
        if state_key in context.user_data:
            await state_handler(update, context)
            return

# ==================== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ====================

def register_org_handlers(application):
    """Регистрация всех обработчиков организаций"""
    
    # Основные меню
    application.add_handler(CallbackQueryHandler(organizations_main_menu, pattern="^orgs_main$"))
    application.add_handler(CallbackQueryHandler(organizations_list, pattern="^orgs_list$"))
    application.add_handler(CallbackQueryHandler(organization_panel, pattern="^my_org_panel$"))
    application.add_handler(CallbackQueryHandler(view_organization_stats, pattern="^orgs_stats$"))
    
    # Просмотр организаций
    application.add_handler(CallbackQueryHandler(view_organization, pattern="^org_view_"))
    application.add_handler(CallbackQueryHandler(apply_to_organization, pattern="^org_apply_"))
    application.add_handler(CallbackQueryHandler(view_organization_members, pattern="^org_members_"))
    application.add_handler(CallbackQueryHandler(leave_organization, pattern="^org_leave_"))
    application.add_handler(CallbackQueryHandler(organization_manage_menu, pattern="^org_manage_"))
    application.add_handler(CallbackQueryHandler(organization_panel_by_type, pattern="^org_panel_"))
    application.add_handler(CallbackQueryHandler(organization_applications_menu, pattern="^org_applications_"))
    application.add_handler(CallbackQueryHandler(organization_application_decision, pattern="^org_app_(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(organization_staff_menu, pattern="^org_staff_"))
    application.add_handler(CallbackQueryHandler(organization_rating, pattern="^org_rating$"))
    application.add_handler(CallbackQueryHandler(organization_career, pattern="^org_career$"))
    application.add_handler(CallbackQueryHandler(organization_career_path, pattern="^org_career_path$"))
    application.add_handler(CallbackQueryHandler(organization_colleagues, pattern="^org_colleagues$"))
    application.add_handler(CallbackQueryHandler(organization_stats_detailed, pattern="^org_stats_detailed$"))
    
    # Действия в организациях
    application.add_handler(CallbackQueryHandler(start_arrest, pattern="^police_arrest$"))
    application.add_handler(CallbackQueryHandler(select_arrest_target, pattern="^pick_arrest_"))
    application.add_handler(CallbackQueryHandler(police_investigation_menu, pattern="^police_investigate$"))
    application.add_handler(CallbackQueryHandler(police_wanted_menu, pattern="^police_wanted$"))
    application.add_handler(CallbackQueryHandler(start_treatment, pattern="^hospital_treat$"))
    application.add_handler(CallbackQueryHandler(select_treatment_target, pattern="^pick_treat_"))
    application.add_handler(CallbackQueryHandler(hospital_diagnose_menu, pattern="^hospital_diagnose$"))
    application.add_handler(CallbackQueryHandler(hospital_prescribe_menu, pattern="^hospital_prescribe$"))
    application.add_handler(CallbackQueryHandler(start_loan, pattern="^bank_loan$"))
    application.add_handler(CallbackQueryHandler(select_loan_applicant, pattern="^pick_loanapp_"))
    application.add_handler(CallbackQueryHandler(bank_service_menu, pattern="^bank_serve$"))
    application.add_handler(CallbackQueryHandler(bank_account_menu, pattern="^bank_account$"))
    application.add_handler(CallbackQueryHandler(government_laws_menu, pattern="^gov_laws$"))
    application.add_handler(CallbackQueryHandler(create_rule_redirect, pattern="^create_rule$"))
    application.add_handler(CallbackQueryHandler(my_rules_menu, pattern="^my_rules$"))
    application.add_handler(CallbackQueryHandler(government_budget_menu, pattern="^gov_budget$"))
    application.add_handler(CallbackQueryHandler(government_appointments_menu, pattern="^gov_appointments$"))
    application.add_handler(CallbackQueryHandler(tax_report_menu, pattern="^tax_report$"))
    application.add_handler(CallbackQueryHandler(tax_cycle_menu, pattern="^tax_cycle$"))
    application.add_handler(CallbackQueryHandler(loan_request_decision, pattern="^loan_(approve|reject)_"))

    # Выборы
    application.add_handler(CallbackQueryHandler(elections_list_menu, pattern="^elections_list_"))
    application.add_handler(CallbackQueryHandler(elections_view, pattern="^election_view_"))
    application.add_handler(CallbackQueryHandler(elections_create_start, pattern="^elections_create$"))
    application.add_handler(CallbackQueryHandler(handle_election_org, pattern="^election_set_org_"))
    application.add_handler(CallbackQueryHandler(nominate_start, pattern="^nominate_start_"))
    application.add_handler(CallbackQueryHandler(election_vote, pattern="^election_vote_"))

    # Доклады
    application.add_handler(CallbackQueryHandler(reports_list_menu, pattern="^reports_list_"))
    application.add_handler(CallbackQueryHandler(report_create_start, pattern="^report_create$"))
    application.add_handler(CallbackQueryHandler(report_type_select, pattern="^report_type_"))
    
    # Задания
    application.add_handler(CallbackQueryHandler(view_tasks, pattern="^org_tasks$|^org_tasks_view$"))
    application.add_handler(CallbackQueryHandler(take_task_menu, pattern="^take_task$"))
    application.add_handler(CallbackQueryHandler(create_task_menu, pattern="^create_task$"))

    # Бизнесы
    application.add_handler(CallbackQueryHandler(businesses_menu, pattern="^biz_menu$"))
    application.add_handler(CallbackQueryHandler(businesses_list, pattern="^biz_list$"))
    application.add_handler(CallbackQueryHandler(business_view, pattern="^biz_view_"))
    application.add_handler(CallbackQueryHandler(business_create_start, pattern="^biz_create$"))
    application.add_handler(CallbackQueryHandler(business_apply, pattern="^biz_apply_"))
    application.add_handler(CallbackQueryHandler(business_applications, pattern="^biz_apps_"))
    application.add_handler(CallbackQueryHandler(business_application_decision, pattern="^biz_app_"))
    application.add_handler(CallbackQueryHandler(business_collect_income, pattern="^biz_collect_"))

    # Частные организации
    application.add_handler(CallbackQueryHandler(private_orgs_menu, pattern="^priv_menu$"))
    application.add_handler(CallbackQueryHandler(private_orgs_list, pattern="^priv_list$"))
    application.add_handler(CallbackQueryHandler(private_org_view, pattern="^priv_view_"))
    application.add_handler(CallbackQueryHandler(private_org_create_start, pattern="^priv_create$"))
    application.add_handler(CallbackQueryHandler(private_org_apply, pattern="^priv_apply_"))
    application.add_handler(CallbackQueryHandler(private_org_applications, pattern="^priv_apps_"))
    application.add_handler(CallbackQueryHandler(private_org_application_decision, pattern="^priv_app_"))

    # Банды
    application.add_handler(CallbackQueryHandler(gangs_menu, pattern="^gang_menu$"))
    application.add_handler(CallbackQueryHandler(gangs_list, pattern="^gang_list$"))
    application.add_handler(CallbackQueryHandler(gang_view, pattern="^gang_view_"))
    application.add_handler(CallbackQueryHandler(gang_create_start, pattern="^gang_create$"))
    application.add_handler(CallbackQueryHandler(gang_apply, pattern="^gang_apply_"))
    application.add_handler(CallbackQueryHandler(gang_application_decision, pattern="^gang_app_"))
    application.add_handler(CallbackQueryHandler(gang_attack_start, pattern="^gang_attack$"))
    application.add_handler(CallbackQueryHandler(select_gang_attack_target, pattern="^pick_gangatk_"))

    # Суд
    application.add_handler(CallbackQueryHandler(court_menu, pattern="^court_menu$"))
    application.add_handler(CallbackQueryHandler(court_create_start, pattern="^court_create$"))
    application.add_handler(CallbackQueryHandler(select_court_defendant, pattern="^pick_courtdef_"))
    application.add_handler(CallbackQueryHandler(court_list_cases, pattern="^court_list$"))
    application.add_handler(CallbackQueryHandler(court_review_queue, pattern="^court_queue$"))
    application.add_handler(CallbackQueryHandler(court_evidence_start, pattern="^court_evidence$"))
    application.add_handler(CallbackQueryHandler(select_court_evidence_case, pattern="^pick_cevid_"))
    application.add_handler(CallbackQueryHandler(court_case_decision, pattern="^court_(accept|reject)_"))

    # Запрос лечения
    application.add_handler(CallbackQueryHandler(treatment_request_decision, pattern="^treat_(accept|reject)_"))

    # Обучение, профиль, задания
    application.add_handler(CallbackQueryHandler(tutorial_start, pattern="^tutorial_start$"))
    application.add_handler(CallbackQueryHandler(tutorial_next, pattern="^tutorial_next$"))
    application.add_handler(CallbackQueryHandler(tutorial_finish, pattern="^tutorial_finish$"))
    application.add_handler(CallbackQueryHandler(tutorial_skip, pattern="^tutorial_skip$"))
    application.add_handler(CallbackQueryHandler(player_tasks_menu, pattern="^player_tasks$"))
    application.add_handler(CallbackQueryHandler(profile_menu, pattern="^profile_menu$"))

    # Недвижимость
    application.add_handler(CallbackQueryHandler(property_menu, pattern="^prop_menu$"))
    application.add_handler(CallbackQueryHandler(property_list, pattern="^prop_list$"))
    application.add_handler(CallbackQueryHandler(property_view, pattern="^prop_view_"))
    application.add_handler(CallbackQueryHandler(property_buy, pattern="^prop_buy_"))
    application.add_handler(CallbackQueryHandler(property_rent, pattern="^prop_rent_"))

    # Контракты
    application.add_handler(CallbackQueryHandler(market_menu, pattern="^market_menu$"))
    application.add_handler(CallbackQueryHandler(market_list, pattern="^market_list$"))
    application.add_handler(CallbackQueryHandler(market_view, pattern="^market_view_"))
    application.add_handler(CallbackQueryHandler(market_create_start, pattern="^market_create$"))
    application.add_handler(CallbackQueryHandler(market_accept, pattern="^market_accept_"))
    application.add_handler(CallbackQueryHandler(market_complete, pattern="^market_complete_"))

    # Гражданская работа
    application.add_handler(CallbackQueryHandler(citizen_work_menu, pattern="^work_menu$"))
    application.add_handler(CallbackQueryHandler(citizen_work_jobs, pattern="^work_jobs$"))
    application.add_handler(CallbackQueryHandler(citizen_take_job, pattern="^work_take_"))
    application.add_handler(CallbackQueryHandler(work_hr_menu, pattern="^work_hr$"))
    application.add_handler(CallbackQueryHandler(work_hr_decision, pattern="^work_hr_(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(citizen_work_shift, pattern="^work_shift$"))

    # Образование
    application.add_handler(CallbackQueryHandler(education_menu, pattern="^edu_menu$"))
    application.add_handler(CallbackQueryHandler(education_programs_menu, pattern="^edu_programs$"))
    application.add_handler(CallbackQueryHandler(education_apply_start, pattern="^edu_apply_"))
    application.add_handler(CallbackQueryHandler(education_apply_teacher, pattern="^edu_apply_teacher$"))
    application.add_handler(CallbackQueryHandler(education_teacher_menu, pattern="^edu_teacher$"))
    application.add_handler(CallbackQueryHandler(education_teacher_applications, pattern="^edu_teacher_applications$"))
    application.add_handler(CallbackQueryHandler(education_teacher_app_decision, pattern="^edu_teacher_(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(education_how_to_teach, pattern="^edu_how_to_teach$"))
    application.add_handler(CallbackQueryHandler(education_application_decision, pattern="^edu_app_(approve|reject)_"))
    application.add_handler(CallbackQueryHandler(education_study, pattern="^edu_study$"))
    application.add_handler(CallbackQueryHandler(education_study_choice, pattern="^edu_study_(theory|practice|group)$"))

    # Митинги
    application.add_handler(CallbackQueryHandler(protests_menu, pattern="^protest_menu$"))
    application.add_handler(CallbackQueryHandler(protests_list, pattern="^protest_list$"))
    application.add_handler(CallbackQueryHandler(protest_view, pattern="^protest_view_"))
    application.add_handler(CallbackQueryHandler(protest_create_start, pattern="^protest_create$"))
    application.add_handler(CallbackQueryHandler(protest_vote, pattern="^protest_(support|against)_"))

    # Система правления и революции
    # Система правления и революции
    application.add_handler(CallbackQueryHandler(government_menu, pattern="^government_menu$"))
    
    # Выборы
    application.add_handler(CallbackQueryHandler(elections_vote, pattern="^elections_vote$"))
    application.add_handler(CallbackQueryHandler(vote_for_candidate, pattern="^vote_for_"))
    
    application.add_handler(CallbackQueryHandler(revolutions_list, pattern="^revolutions_list$"))
    application.add_handler(CallbackQueryHandler(start_revolution_menu, pattern="^start_revolution$"))
    application.add_handler(CallbackQueryHandler(start_revolution_type, pattern="^start_rev_"))
    application.add_handler(CallbackQueryHandler(join_revolution_action, pattern="^join_revolution_"))
    
    # Назначение на должность
    application.add_handler(CallbackQueryHandler(appoint_menu, pattern="^appoint_menu$"))
    application.add_handler(CallbackQueryHandler(appoint_select_position, pattern="^appoint_user_"))
    application.add_handler(CallbackQueryHandler(appoint_confirm, pattern="^appoint_confirm_"))
    
    # Письма и сообщения
    application.add_handler(CallbackQueryHandler(messages_menu, pattern="^messages_menu$"))
    application.add_handler(CallbackQueryHandler(view_inbox, pattern="^view_inbox$"))
    application.add_handler(CallbackQueryHandler(view_sent, pattern="^view_sent$"))
    application.add_handler(CallbackQueryHandler(compose_message_start, pattern="^compose_message$"))
    application.add_handler(CallbackQueryHandler(select_message_recipient, pattern="^pick_msgto_"))
    
    # ФБР
    application.add_handler(CallbackQueryHandler(fbi_menu, pattern="^fbi_menu$"))

    # Бонус дня
    application.add_handler(CallbackQueryHandler(daily_bonus_menu, pattern="^daily_bonus$"))
    
    # Обработчики текстовых сообщений
    private_text = filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND
    application.add_handler(MessageHandler(private_text, private_text_router))
    
    print("Система организаций загружена.")

# Для запуска в групповом чате
def setup_group_handlers(application):
    """Настройка обработчиков для группового чата"""
    
    # Команды, доступные в группе
    from telegram.ext import CommandHandler
    
    async def org_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для вызова меню организаций в группе"""
        await update.message.reply_text(
            "🏛️ **Система государственных организаций**\n\n"
            "Для работы с организациями перейдите в личные сообщения с ботом:\n"
            "@@mirnastanbot\n\n"
            "Или используйте команды:\n"
            "/orgs - Информация об организациях\n"
            "/myorg - Ваша организация\n"
            "/tasks - Задания организаций\n"
            "/loan - Заявка на кредит\n"
            "/biz - Бизнесы\n"
            "/priv - Частные организации\n"
            "/gang - Банды\n"
            "/court - Суд\n"
            "/med - Лечение\n"
            "/prop - Недвижимость\n"
            "/market - Контракты\n"
            "/work - Работа\n"
            "/edu - Учеба\n"
            "/protest - Митинги\n"
            "/daily - Бонус дня\n"
            "/profile - Профиль\n"
            "/tutorial - Обучение"
        )
    
    application.add_handler(CommandHandler("orgs", org_group_command))
    application.add_handler(CommandHandler("myorg", org_group_command))
    application.add_handler(CommandHandler("tasks", org_group_command))
    application.add_handler(CommandHandler("loan", org_group_command))
    application.add_handler(CommandHandler("biz", org_group_command))
    application.add_handler(CommandHandler("priv", org_group_command))
    application.add_handler(CommandHandler("gang", org_group_command))
    application.add_handler(CommandHandler("court", org_group_command))
    application.add_handler(CommandHandler("med", org_group_command))
    application.add_handler(CommandHandler("prop", org_group_command))
    application.add_handler(CommandHandler("market", org_group_command))
    application.add_handler(CommandHandler("work", org_group_command))
    application.add_handler(CommandHandler("edu", org_group_command))
    application.add_handler(CommandHandler("protest", org_group_command))
    application.add_handler(CommandHandler("daily", org_group_command))
    application.add_handler(CommandHandler("profile", org_group_command))
    application.add_handler(CommandHandler("tutorial", org_group_command))
    
    # Регистрируем обычные обработчики (они будут работать в ЛС)
    register_org_handlers(application)
