"""
FSM-состояния для aiogram 3.x
Используются для отслеживания состояний в диалоговых потоках
"""

from aiogram.fsm.state import State, StatesGroup


class MainStates(StatesGroup):
    """Основные состояния бота"""
    main_menu = State()
    waiting_choice = State()
    setting_nickname = State()
    sending_gov_radio = State()
    sending_president_appeal = State()
    charity_custom_amount = State()


class ElectionStates(StatesGroup):
    """Состояния выборов президента"""
    global_lock = State()  # Режим глобальной блокировки (только выборы)
    voting_menu = State()  # Меню голосования
    party_creation = State()  # Создание партии
    party_name_input = State()  # Ввод названия партии
    candidate_registration = State()  # Регистрация кандидата
    campaign = State()  # Кампания
    debate_message = State()  # Кампания


class PresidentStates(StatesGroup):
    """Состояния для админ-панели президента"""
    admin_panel = State()
    appointing_position = State()  # Назначение на должность
    selecting_player = State()  # Выбор игрока
    setting_salary = State()  # Установка зарплаты
    renaming_position = State()  # Переименование должности
    creating_position = State()  # Создание новой должности
    creating_rule = State()  # Создание закона
    rule_text = State()
    rule_penalty = State()
    changing_government = State()  # Смена формы правления


class OrganizationStates(StatesGroup):
    """Состояния для работы с организациями"""
    org_menu = State()
    viewing_org = State()
    applying_to_org = State()  # Подача заявки
    application_text = State()  # Текст заявки
    managing_org = State()  # Управление организацией
    reviewing_applications = State()  # Рассмотрение заявок
    approving_member = State()  # Одобрение члена
    setting_position = State()  # Установка должности
    org_chat_message = State()  # Установка должности
    org_news_draft = State()  # Черновик новости организации


class BusinessStates(StatesGroup):
    """Состояния для бизнеса"""
    business_menu = State()
    creating_business = State()  # Создание бизнеса
    business_name = State()
    business_type = State()
    business_location = State()
    managing_business = State()
    creating_task = State()  # Создание задания для сотрудников
    task_title = State()
    task_description = State()
    task_reward = State()


class EducationStates(StatesGroup):
    """Состояния образования"""
    education_menu = State()
    browsing_programs = State()  # Просмотр программ
    applying_program = State()  # Подача заявки на программу
    studying = State()  # Обучение
    teaching = State()  # Преподавание
    applying_teacher = State()  # Заявка на преподавателя
    teacher_application_text = State()


class PoliceStates(StatesGroup):
    """Состояния полиции"""
    police_menu = State()
    arresting = State()  # Арест
    selecting_suspect = State()
    arrest_reason = State()
    investigating = State()  # Расследование


class FBIStates(StatesGroup):
    """Состояния ФБР"""
    fbi_menu = State()
    intercepting = State()  # Перехват сообщений
    viewing_intercepts = State()


class CitizenStates(StatesGroup):
    """Состояния гражданской работы"""
    job_menu = State()
    applying_job = State()  # Подача заявки на работу
    job_application_text = State()


class BankStates(StatesGroup):
    """Состояния банка"""
    bank_menu = State()
    approving_loan = State()  # Рассмотрение кредитов
    loan_review = State()
    loan_amount = State()
    loan_term = State()


class RevolutionStates(StatesGroup):
    """Состояния революций"""
    revolution_menu = State()
    starting_revolution = State()  # Запуск революции
    revolution_reason = State()
    selecting_government_type = State()
    joining_revolution = State()  # Присоединение к революции


class PropertyStates(StatesGroup):
    """Состояния недвижимости"""
    property_menu = State()
    buying_property = State()


class CourtStates(StatesGroup):
    """Состояния суда"""
    court_menu = State()
    creating_case = State()  # Создание дела
    case_defendant = State()
    case_description = State()
    reviewing_case = State()
    adding_evidence = State()  # Добавление доказательств


class MessageStates(StatesGroup):
    """Состояния сообщений"""
    messaging = State()
    sending_message = State()  # Отправка письма
    message_recipient = State()
    message_subject = State()
    message_content = State()


class ProtestStates(StatesGroup):
    """Состояния протестов/митингов"""
    protest_menu = State()
    creating_protest = State()  # Организация митинга
    protest_title = State()
    protest_description = State()
    protest_location = State()
    joining_protest = State()


class TaxStates(StatesGroup):
    """Состояния налоговой службы"""
    tax_menu = State()
    tax_enforcement = State()  # Взыскание налогов
    checking_debts = State()


class HospitalStates(StatesGroup):
    """Состояния больницы"""
    hospital_menu = State()
    treating_patient = State()  # Лечение
    patient_selection = State()
    diagnosis = State()
    treatment = State()
    cost = State()
