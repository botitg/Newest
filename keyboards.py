"""
ИСПРАВЛЕННЫЙ keyboards.py
1. Добавлены все недостающие функции (get_players_keyboard и др.)
2. Исправлены ошибки TypeError (теперь только именованные аргументы в CallbackData)
3. Полная совместимость с aiogram 3.x
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from typing import List, Optional

# ==================== CALLBACK DATA FACTORIES ====================

class OrgCallback(CallbackData, prefix="org"):
    action: str
    org_id: Optional[int] = -1
    org_name: Optional[str] = "none"

class ElectionCallback(CallbackData, prefix="election"):
    action: str
    election_id: Optional[int] = -1
    candidate_id: Optional[int] = -1

class PartyCallback(CallbackData, prefix="party"):
    action: str
    party_id: Optional[int] = -1
    election_id: Optional[int] = -1
    invited_user_id: Optional[int] = -1
    decision: Optional[int] = -1

class PositionCallback(CallbackData, prefix="position"):
    action: str
    position_name: Optional[str] = "none"
    player_id: Optional[int] = -1

class MenuCallback(CallbackData, prefix="menu"):
    action: str

class PlayerCallback(CallbackData, prefix="plr"):
    action: str
    player_id: int
    page: int = 0

# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu_keyboard(is_new_player: bool = False, has_elections: bool = False, election_id: int = -1) -> InlineKeyboardMarkup:
    buttons = []
    
    if has_elections:
        buttons = [
            [InlineKeyboardButton(text="🟢 ОСНОВАТЬ ПАРТИЮ", callback_data=ElectionCallback(action="create_party", election_id=election_id).pack())],
            [InlineKeyboardButton(text="🗳️ ГОЛОСОВАТЬ", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📋 МОЯ ПАРТИЯ", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📝 ВЫДВИНУТЬСЯ", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📋 КАНДИДАТЫ", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(text="🏛️ Организации", callback_data="orgs_main"),
                InlineKeyboardButton(text="🏛️ Правление", callback_data="president_admin_panel"),
            ],
            [
                InlineKeyboardButton(text="🏪 Бизнесы", callback_data="biz_menu"),
                InlineKeyboardButton(text="🏢 Частные организации", callback_data="private_org_list"),
            ],
            [
                InlineKeyboardButton(text="🕶️ Банды", callback_data="gang_list"),
                InlineKeyboardButton(text="⚖️ Суд", callback_data="court_menu"),
            ],
            [
                InlineKeyboardButton(text="💼 Работа", callback_data="work_menu"),
                InlineKeyboardButton(text="🎓 Учеба", callback_data="edu_menu"),
            ],
            [
                InlineKeyboardButton(text="🏠 Недвижимость", callback_data="prop_menu"),
                InlineKeyboardButton(text="📣 Контракты", callback_data="market_menu"),
            ],
            [
                InlineKeyboardButton(text="📣 Митинги", callback_data="revolution_menu"),
                InlineKeyboardButton(text="📊 Финансы", callback_data="bank_menu"),
            ],
            [
                InlineKeyboardButton(text="🏦 Кредит", callback_data="bank_menu"),
                InlineKeyboardButton(text="🏥 Лечение", callback_data="hospital_menu"),
            ],
            [
                InlineKeyboardButton(text="🎁 Бонус дня", callback_data="daily_bonus"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu"),
            ],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help_menu")],
        ]
        
        if is_new_player:
            buttons.insert(0, [InlineKeyboardButton(text="🎓 ОБУЧЕНИЕ", callback_data="tutorial_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_button(text: str = "🔙 Назад", callback: str = "back_to_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback)]])

# ==================== ОРГАНИЗАЦИИ ====================

def get_organization_list_keyboard() -> InlineKeyboardMarkup:
    org_names = ["Правительство", "Полиция", "Больница", "Суд", "Банк", "Университет", "ФБР", "Налоговая служба"]
    buttons = []
    for name in org_names:
        buttons.append([InlineKeyboardButton(text=f"🏛️ {name}", callback_data=OrgCallback(action="view_org", org_name=name).pack())])
    
    buttons.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_organization_view_keyboard(org_id: int, is_member: bool = False, can_apply: bool = True) -> InlineKeyboardMarkup:
    buttons = []
    if is_member:
        buttons.extend([
            [InlineKeyboardButton(text="👥 Управление", callback_data=f"org_manage_{org_id}")],
            [InlineKeyboardButton(text="📊 Панель", callback_data=f"org_panel_{org_id}")],
            [InlineKeyboardButton(text="💼 Покинуть", callback_data=f"org_leave_{org_id}")],
        ])
    elif can_apply:
        buttons.append([InlineKeyboardButton(text="📝 Подать заявку", callback_data=f"org_apply_{org_id}")])
    
    buttons.extend([
        [InlineKeyboardButton(text="👥 Члены", callback_data=f"org_members_{org_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="orgs_main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ВЫБОРЫ ====================

def get_election_menu_keyboard(election_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟢 ОСНОВАТЬ ПАРТИЮ", callback_data=ElectionCallback(action="create_party", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📜 СПИСОК ПАРТИЙ", callback_data=ElectionCallback(action="list_parties", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🗳️ ГОЛОСОВАТЬ", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📋 МОЯ ПАРТИЯ", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📝 ВЫДВИНУТЬСЯ", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📋 КАНДИДАТЫ", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_candidates_keyboard(candidates: List, election_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for cand in candidates:
        buttons.append([InlineKeyboardButton(
            text=f"📊 {cand.get('full_name')} — {cand.get('votes', 0)} гол.",
            callback_data=ElectionCallback(action="vote", election_id=election_id, candidate_id=cand['candidate_id']).pack()
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ПРОФИЛЬНЫЕ МЕНЮ ====================

def get_president_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✨ Назначить", callback_data="pres_appoint")],
        [InlineKeyboardButton(text="📝 Переименовать роль", callback_data="pres_rename_pos")],
        [InlineKeyboardButton(text="👑 Новый президент", callback_data="pres_appoint_president")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_fbi_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚨 Перехват", callback_data="fbi_intercept")],
        [InlineKeyboardButton(text="🔍 Расследование", callback_data="fbi_investigate")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_police_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🚨 АРЕСТ", callback_data="police_arrest")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_hospital_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🏥 ЛЕЧИТЬ", callback_data="hospital_treat")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_education_menu_keyboard(is_student: bool = False, is_teacher: bool = False) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📚 ПРОГРАММЫ", callback_data="edu_browse")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_work_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📋 РАБОТЫ", callback_data="work_browse")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_bank_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="💰 КРЕДИТЫ", callback_data="bank_loans")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_business_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📋 СПИСОК", callback_data="biz_browse")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_revolution_menu_keyboard(has_active_revolution: bool = False) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🏛️ РЕВОЛЮЦИИ", callback_data="rev_list")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_property_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🏠 КУПИТЬ", callback_data="prop_buy")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_protest_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📣 МИТИНГИ", callback_data="protest_list")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_contracts_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📋 КОНТРАКТЫ", callback_data="contract_list")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile_view")], [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ВЫБОР ИГРОКА (ТО, ЧЕГО НЕ ХВАТАЛО) ====================

def get_players_keyboard(players: List, max_per_page: int = 10, page: int = 0, callback_prefix: str = "select_player", back_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    """Клавиатура для выбора игрока из списка"""
    buttons = []
    start_idx = page * max_per_page
    end_idx = start_idx + max_per_page
    page_players = players[start_idx:end_idx]
    
    for player in page_players:
        name = player.get('full_name', 'Неизвестно')
        user_id = player.get('user_id', 0)
        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"{callback_prefix}_{user_id}")])
    
    # Пагинация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{callback_prefix}_{page-1}"))
    if len(players) > end_idx:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{callback_prefix}_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
