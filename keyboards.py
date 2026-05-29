"""
Набор клавиатур для aiogram 3.x.
"""

from typing import List, Optional

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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


def get_main_menu_keyboard(
    is_new_player: bool = False,
    has_elections: bool = False,
    election_id: int = -1,
) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []

    if has_elections:
        buttons = [
            [InlineKeyboardButton(text="🟢 Создать партию", callback_data=ElectionCallback(action="create_party", election_id=election_id).pack())],
            [InlineKeyboardButton(text="🗳️ Голосовать", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📋 Моя партия", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📝 Выдвинуться", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
            [InlineKeyboardButton(text="📋 Кандидаты", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton(text="🎮 Развлечения", callback_data="menu_section_fun"),
                InlineKeyboardButton(text="💼 Карьера", callback_data="menu_section_career"),
            ],
            [
                InlineKeyboardButton(text="💰 Экономика", callback_data="menu_section_economy"),
                InlineKeyboardButton(text="🏛️ Государство", callback_data="menu_section_state"),
            ],
            [
                InlineKeyboardButton(text="🎓 Обучение", callback_data="edu_menu"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu"),
            ],
            [
                InlineKeyboardButton(text="💎 Донат", callback_data="donation_menu"),
                InlineKeyboardButton(text="🎟️ Промокоды", callback_data="promo_menu"),
            ],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")],
        ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_button(text: str = "🔙 Назад", callback: str = "back_to_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback)]])


def get_organization_list_keyboard(organizations: Optional[List[dict]] = None) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []

    if organizations:
        for org in organizations:
            org_id = int(org.get("id") or 0)
            if org_id <= 0:
                continue
            org_name = str(org.get("name") or f"Организация #{org_id}")
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🏛️ {org_name}",
                        callback_data=f"view_org_{org_id}",
                    )
                ]
            )
    else:
        fallback_names = [
            "Правительство",
            "Полиция",
            "Больница",
            "Суд",
            "Банк",
            "Университет",
            "ФБР",
            "Налоговая служба",
        ]
        for name in fallback_names:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🏛️ {name}",
                        callback_data=OrgCallback(action="view", org_id=-1, org_name=name).pack(),
                    )
                ]
            )

    buttons.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_organization_view_keyboard(org_id: int, is_member: bool = False, can_apply: bool = True) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    if is_member:
        buttons.extend(
            [
                [InlineKeyboardButton(text="👥 Управление", callback_data="manage_organization")],
                [InlineKeyboardButton(text="💬 Панель/чат", callback_data=f"org_chat_{org_id}")],
                [InlineKeyboardButton(text="🚪 Покинуть", callback_data=f"leave_org_{org_id}")],
            ]
        )
    elif can_apply:
        buttons.append([InlineKeyboardButton(text="📝 Подать заявку", callback_data=f"apply_org_{org_id}")])

    buttons.extend(
        [
            [InlineKeyboardButton(text="👥 Члены", callback_data=f"org_members_{org_id}")],
            [InlineKeyboardButton(text="🔙 К списку", callback_data="orgs_main")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_election_menu_keyboard(election_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟢 Основать партию", callback_data=ElectionCallback(action="create_party", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📜 Список партий", callback_data=ElectionCallback(action="list_parties", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🗳️ Голосовать", callback_data=ElectionCallback(action="vote_menu", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📋 Моя партия", callback_data=ElectionCallback(action="view_party", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📝 Выдвинуться", callback_data=ElectionCallback(action="nominate", election_id=election_id).pack())],
        [InlineKeyboardButton(text="📋 Кандидаты", callback_data=ElectionCallback(action="view_candidates", election_id=election_id).pack())],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_candidates_keyboard(candidates: List, election_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for cand in candidates:
        display_name = (
            cand.get("nickname")
            or cand.get("full_name")
            or (f"@{str(cand.get('username') or '').lstrip('@')}" if cand.get("username") else f"ID {cand.get('candidate_id')}")
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📊 {display_name} — {cand.get('votes', 0)} гол.",
                    callback_data=ElectionCallback(
                        action="vote",
                        election_id=election_id,
                        candidate_id=cand["candidate_id"],
                    ).pack(),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_president_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✨ Назначить", callback_data="pres_appoint")],
        [InlineKeyboardButton(text="📝 Переименовать роль", callback_data="pres_rename_pos")],
        [InlineKeyboardButton(text="🧑 Новый президент", callback_data="pres_appoint_president")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_fbi_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚨 Перехват", callback_data="fbi_intercept_messages")],
        [InlineKeyboardButton(text="🔍 Расследование", callback_data="fbi_track_player")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_police_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚨 Арест", callback_data="police_search_suspects")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_hospital_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏥 Лечить", callback_data="hospital_appointment")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_education_menu_keyboard(is_student: bool = False, is_teacher: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📚 Программы", callback_data="view_education_programs")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_work_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Работы", callback_data="view_citizen_jobs")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_bank_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💰 Кредиты", callback_data="loan_request")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_business_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Список", callback_data="fp_business_my")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_revolution_menu_keyboard(has_active_revolution: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏛️ Революции", callback_data="view_active_revolutions")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_property_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏠 Купить", callback_data="property_catalog")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_protest_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📣 Митинги", callback_data="revolution_menu")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_contracts_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Контракты", callback_data="view_contracts")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_menu")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_players_keyboard(
    players: List,
    max_per_page: int = 10,
    page: int = 0,
    callback_prefix: str = "select_player",
    back_callback: str = "back_to_main",
) -> InlineKeyboardMarkup:
    """Клавиатура для выбора игрока из списка."""
    buttons: List[List[InlineKeyboardButton]] = []
    invisible_chars = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2060", "\u00ad")

    def _clean_name(value: object, max_len: int = 32) -> str:
        name = str(value or "")
        for token in invisible_chars:
            name = name.replace(token, "")
        name = " ".join(name.split()).strip()
        return name[:max_len] if max_len > 0 else name

    start_idx = max(0, int(page) * int(max_per_page))
    end_idx = start_idx + int(max_per_page)
    page_players = players[start_idx:end_idx]

    for player in page_players:
        nickname = _clean_name(player.get("nickname"))
        full_name = _clean_name(player.get("full_name"))
        username = _clean_name(player.get("username")).lstrip("@")
        user_id = int(player.get("user_id") or 0)

        if nickname:
            name = nickname
        elif full_name:
            name = full_name
        elif username:
            name = f"@{username}"
        elif user_id > 0:
            name = f"ID {user_id}"
        else:
            name = "Неизвестно"

        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"{callback_prefix}_{user_id}")])

    nav_buttons: List[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{callback_prefix}_{page - 1}"))
    if len(players) > end_idx:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{callback_prefix}_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

