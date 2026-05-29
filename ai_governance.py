"""
Background AI governance:
- fills vacant high-level organization roles with AI agents;
- yields those roles when a human takes the seat;
- auto-reviews pending organization applications with role-specific policy;
- optionally uses OpenRouter for richer decisions (fallback is deterministic).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import aiosqlite
from aiogram import Bot

from database import db

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(minimum, parsed)


def _env_float(name: str, default: float, minimum: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return max(minimum, parsed)


AI_GOV_ENABLED = _env_flag("AI_GOV_ENABLED", True)
AI_GOV_INTERVAL_SECONDS = _env_int("AI_GOV_INTERVAL_SECONDS", 75, 20)
AI_GOV_REVIEW_LIMIT = _env_int("AI_GOV_REVIEW_LIMIT", 18, 1)
AI_GOV_REVIEW_PER_ORG = _env_int("AI_GOV_REVIEW_PER_ORG", 6, 1)
AI_GOV_GROUP_REPORT_ENABLED = _env_flag("AI_GOV_GROUP_REPORT_ENABLED", True)

OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_MODEL = (os.getenv("OPENROUTER_MODEL") or "openai/gpt-4o-mini").strip()
OPENROUTER_BASE_URL = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1/chat/completions").strip()
OPENROUTER_TIMEOUT_SECONDS = _env_float("OPENROUTER_TIMEOUT_SECONDS", 18.0, 4.0)
OPENROUTER_HTTP_REFERRER = (os.getenv("OPENROUTER_HTTP_REFERRER") or "https://localhost").strip()
OPENROUTER_APP_TITLE = (os.getenv("OPENROUTER_APP_TITLE") or "Mirnastan Governance AI").strip()

try:
    UZBEKISTAN_TZ = ZoneInfo("Asia/Tashkent")
except ZoneInfoNotFoundError:
    UZBEKISTAN_TZ = timezone(timedelta(hours=5), name="UTC+5")


AI_ROLE_SPECS: tuple[Dict[str, Any], ...] = (
    {
        "tag": "ai_vice_president",
        "user_id": 910000001,
        "username": "mirna_ai_vice",
        "full_name": "AI Vice President",
        "org_type": "government",
        "slot": "deputy",
        "role": "Р’РёС†Рµ-РїСЂРµР·РёРґРµРЅС‚",
        "authority": "vice_president",
        "always_active": True,
    },
    {
        "tag": "ai_tax_chief",
        "user_id": 910000002,
        "username": "mirna_ai_tax",
        "full_name": "AI Tax Chief",
        "org_type": "tax",
        "slot": "leader",
        "role": "Р“Р»Р°РІР° РЅР°Р»РѕРіРѕРІРѕР№ СЃР»СѓР¶Р±С‹",
        "authority": "minister",
    },
    {
        "tag": "ai_police_chief",
        "user_id": 910000003,
        "username": "mirna_ai_police",
        "full_name": "AI Police Chief",
        "org_type": "police",
        "slot": "leader",
        "role": "РќР°С‡Р°Р»СЊРЅРёРє РїРѕР»РёС†РёРё",
        "authority": "minister",
    },
    {
        "tag": "ai_fbi_director",
        "user_id": 910000004,
        "username": "mirna_ai_fbi",
        "full_name": "AI FBI Director",
        "org_type": "fbi",
        "slot": "leader",
        "role": "Р”РёСЂРµРєС‚РѕСЂ Р¤Р‘Р ",
        "authority": "minister",
    },
    {
        "tag": "ai_bank_chief",
        "user_id": 910000005,
        "username": "mirna_ai_bank",
        "full_name": "AI Bank Chief",
        "org_type": "bank",
        "slot": "leader",
        "role": "Р“Р»Р°РІР° Р±Р°РЅРєР°",
        "authority": "finance_minister",
    },
    {
        "tag": "ai_court_chief",
        "user_id": 910000006,
        "username": "mirna_ai_court",
        "full_name": "AI Court Chair",
        "org_type": "court",
        "slot": "leader",
        "role": "Р“Р»Р°РІР° СЃСѓРґР°",
        "authority": "minister",
    },
    {
        "tag": "ai_hospital_chief",
        "user_id": 910000007,
        "username": "mirna_ai_med",
        "full_name": "AI Chief Doctor",
        "org_type": "hospital",
        "slot": "leader",
        "role": "Р“Р»Р°РІРІСЂР°С‡",
        "authority": "minister",
    },
    {
        "tag": "ai_education_chief",
        "user_id": 910000008,
        "username": "mirna_ai_edu",
        "full_name": "AI Rector",
        "org_type": "education",
        "slot": "leader",
        "role": "Р РµРєС‚РѕСЂ",
        "authority": "minister",
    },
)


REVIEW_POLICY: Dict[str, Dict[str, Any]] = {
    "tax": {
        "threshold": 4.4,
        "focus": "Tax discipline and clean profile",
        "hard_reject_tax_debt": 3000.0,
        "crime_penalty": 1.3,
    },
    "police": {
        "threshold": 4.8,
        "focus": "Security reliability and no criminal footprint",
        "hard_reject_tax_debt": 6000.0,
        "crime_penalty": 2.0,
    },
    "fbi": {
        "threshold": 5.4,
        "focus": "Top integrity and high education",
        "hard_reject_tax_debt": 4000.0,
        "crime_penalty": 2.6,
    },
    "court": {
        "threshold": 5.0,
        "focus": "Legal integrity and stability",
        "hard_reject_tax_debt": 5000.0,
        "crime_penalty": 2.2,
    },
    "bank": {
        "threshold": 4.6,
        "focus": "Financial reliability",
        "hard_reject_tax_debt": 5000.0,
        "crime_penalty": 1.8,
    },
    "hospital": {
        "threshold": 3.8,
        "focus": "Education and responsibility",
        "hard_reject_tax_debt": 8000.0,
        "crime_penalty": 1.2,
    },
    "education": {
        "threshold": 3.6,
        "focus": "Learning potential and reputation",
        "hard_reject_tax_debt": 9000.0,
        "crime_penalty": 1.0,
    },
    "government": {
        "threshold": 5.2,
        "focus": "National stability and public trust",
        "hard_reject_tax_debt": 2000.0,
        "crime_penalty": 2.8,
    },
    "default": {
        "threshold": 3.2,
        "focus": "General profile quality",
        "hard_reject_tax_debt": 12000.0,
        "crime_penalty": 1.0,
    },
}


def _safe_note(raw: Any, fallback: str) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        return fallback
    return text[:420]


def _parse_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    payload = str(raw_text or "").strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"\{.*\}", payload, flags=re.DOTALL)
    if not match:
        return None
    candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _normalize_approve(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "approve", "approved", "accept", "accepted"}


class OpenRouterReviewer:
    def __init__(self) -> None:
        self.enabled = bool(OPENROUTER_API_KEY and OPENROUTER_MODEL and OPENROUTER_BASE_URL)

    async def review(
        self,
        *,
        org_type: str,
        org_name: str,
        role_label: str,
        application_text: str,
        applicant: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        policy = REVIEW_POLICY.get(org_type, REVIEW_POLICY["default"])
        profile = {
            "education": int(applicant.get("education") or 1),
            "reputation": round(float(applicant.get("reputation") or 0.0), 2),
            "tax_debt": round(float(applicant.get("tax_debt") or 0.0), 2),
            "crimes_committed": int(applicant.get("crimes_committed") or 0),
            "level": int(applicant.get("level") or 1),
            "organization": str(applicant.get("organization") or ""),
            "role": str(applicant.get("role") or ""),
        }

        system_prompt = (
            "You are a strict government HR AI for a role-playing economy game. "
            "Decide if an application should be approved. "
            "Return only JSON: {\"approve\": true|false, \"note\": \"short explanation\"}."
        )
        user_payload = {
            "org_type": org_type,
            "org_name": org_name,
            "reviewer_role": role_label,
            "policy_focus": str(policy.get("focus") or ""),
            "application_text": str(application_text or "")[:1200],
            "applicant_profile": profile,
        }

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": OPENROUTER_HTTP_REFERRER,
            "X-Title": OPENROUTER_APP_TITLE,
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "temperature": 0.2,
            "max_tokens": 220,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }

        try:
            timeout = aiohttp.ClientTimeout(total=max(8.0, OPENROUTER_TIMEOUT_SECONDS))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(OPENROUTER_BASE_URL, headers=headers, json=payload) as response:
                    if response.status >= 400:
                        logger.debug("OpenRouter review skipped (%s): %s", response.status, await response.text())
                        return None
                    data = await response.json(content_type=None)
        except Exception as exc:
            logger.debug("OpenRouter review failed: %s", exc)
            return None

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            return None
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = "".join(
                str(part.get("text") if isinstance(part, dict) else part) for part in content
            )
        parsed = _parse_json_object(str(content or ""))
        if not parsed:
            return None

        approve = _normalize_approve(parsed.get("approve"))
        note = _safe_note(parsed.get("note"), "Р РµС€РµРЅРёРµ РїСЂРёРЅСЏС‚Рѕ РР.")
        return {"approve": approve, "note": note, "source": "openrouter"}


def _fallback_review(
    *,
    org_type: str,
    role_label: str,
    application_text: str,
    applicant: Dict[str, Any],
) -> Dict[str, Any]:
    policy = REVIEW_POLICY.get(org_type, REVIEW_POLICY["default"])
    education = int(applicant.get("education") or 1)
    reputation = float(applicant.get("reputation") or 0.0)
    tax_debt = max(0.0, float(applicant.get("tax_debt") or 0.0))
    crimes = max(0, int(applicant.get("crimes_committed") or 0))
    level = int(applicant.get("level") or 1)
    text_len = len(str(application_text or "").strip())

    score = 0.0
    score += min(6.0, education * 0.65)
    score += min(5.0, reputation / 24.0)
    score += min(2.0, level / 12.0)
    score += min(1.8, text_len / 220.0)
    score -= float(policy.get("crime_penalty") or 1.0) * crimes
    score -= min(4.0, tax_debt / 4500.0)

    hard_reject_debt = float(policy.get("hard_reject_tax_debt") or 9_999_999.0)
    approve = bool(score >= float(policy.get("threshold") or 3.2) and tax_debt <= hard_reject_debt)

    if approve:
        note = f"РР ({role_label}) РѕРґРѕР±СЂРёР» Р·Р°СЏРІРєСѓ: РїСЂРѕС„РёР»СЊ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ С‚СЂРµР±РѕРІР°РЅРёСЏРј."
    elif tax_debt > hard_reject_debt:
        note = f"РР ({role_label}) РѕС‚РєР»РѕРЅРёР» Р·Р°СЏРІРєСѓ: СЃР»РёС€РєРѕРј РІС‹СЃРѕРєРёР№ РЅР°Р»РѕРіРѕРІС‹Р№ РґРѕР»Рі."
    elif crimes > 0 and org_type in {"fbi", "police", "court", "government"}:
        note = f"РР ({role_label}) РѕС‚РєР»РѕРЅРёР» Р·Р°СЏРІРєСѓ: СЂРёСЃРєРё РїРѕ Р±РµР·РѕРїР°СЃРЅРѕСЃС‚Рё/Р·Р°РєРѕРЅСѓ."
    else:
        note = f"РР ({role_label}) РѕС‚РєР»РѕРЅРёР» Р·Р°СЏРІРєСѓ: С‚СЂРµР±СѓРµС‚СЃСЏ СѓСЃРёР»РёС‚СЊ РїСЂРѕС„РёР»СЊ."

    return {"approve": approve, "note": _safe_note(note, "Р РµС€РµРЅРёРµ РїСЂРёРЅСЏС‚Рѕ РР."), "source": "fallback"}


async def _cleanup_stale_ai_agents(active_ai_ids: set[int]) -> int:
    async with db._connect() as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("BEGIN IMMEDIATE")
        async with conn.execute(
            "SELECT user_id FROM users WHERE COALESCE(is_ai_agent, 0) = 1"
        ) as cursor:
            rows = await cursor.fetchall()

        all_ai_ids = [int(row["user_id"] or 0) for row in rows if int(row["user_id"] or 0) > 0]
        stale_ids = [uid for uid in all_ai_ids if uid not in active_ai_ids]
        if not stale_ids:
            await conn.commit()
            return 0

        placeholders = ",".join("?" for _ in stale_ids)
        params = tuple(stale_ids)
        await conn.execute(
            f"DELETE FROM organization_members WHERE user_id IN ({placeholders})",
            params,
        )
        await conn.execute(
            f"""
            UPDATE organizations
            SET leader_id = CASE WHEN leader_id IN ({placeholders}) THEN NULL ELSE leader_id END,
                deputy_id = CASE WHEN deputy_id IN ({placeholders}) THEN NULL ELSE deputy_id END
            """,
            params + params,
        )
        await conn.execute(
            f"""
            UPDATE users
            SET organization = NULL,
                role = NULL,
                salary = 0
            WHERE user_id IN ({placeholders})
            """,
            params,
        )
        try:
            await conn.execute(
                f"UPDATE government_authority_assignments SET is_active = 0 WHERE user_id IN ({placeholders})",
                params,
            )
        except sqlite3.OperationalError:
            pass
        await conn.commit()
        return len(stale_ids)


async def _ensure_ai_staffing() -> Dict[str, int]:
    assigned = 0
    active_ai_ids: set[int] = set()

    for spec in AI_ROLE_SPECS:
        org = await db.get_organization_by_type(str(spec["org_type"]))
        if not org:
            continue

        role_slot = "leader_id" if str(spec.get("slot")) == "leader" else "deputy_id"
        role_holder_id = int(org.get(role_slot) or 0)
        always_active = bool(spec.get("always_active"))

        holder = await db.get_user(role_holder_id) if role_holder_id > 0 else None
        holder_is_human = bool(holder and int(holder.get("is_ai_agent") or 0) == 0)
        if holder_is_human and not always_active:
            continue

        ai_user = await db.ensure_ai_governance_user(
            user_id=int(spec["user_id"]),
            username=str(spec["username"]),
            full_name=str(spec["full_name"]),
            role_tag=str(spec["tag"]),
        )
        if not ai_user:
            continue
        ai_user_id = int(ai_user.get("user_id") or 0)
        if ai_user_id <= 0:
            continue

        if role_holder_id != ai_user_id and not holder_is_human:
            ok, msg = await db.appoint_user_to_organization(
                target_user_id=ai_user_id,
                org_id=int(org["id"]),
                role=str(spec["role"]),
                appointed_by_id=None,
            )
            if ok:
                assigned += 1
            else:
                logger.debug("AI staffing skipped for %s: %s", spec.get("tag"), msg)

        authority = str(spec.get("authority") or "").strip()
        if authority:
            await db.set_government_authority_assignment(
                user_id=ai_user_id,
                authority=authority,
                granted_by=None,
                is_active=True,
            )

        active_ai_ids.add(ai_user_id)

    released = await _cleanup_stale_ai_agents(active_ai_ids)
    return {"assigned": assigned, "released": released, "active": len(active_ai_ids)}


async def _review_pending_org_applications(reviewer: OpenRouterReviewer) -> Dict[str, int]:
    reviewed = 0
    approved = 0
    rejected = 0

    for spec in AI_ROLE_SPECS:
        if reviewed >= AI_GOV_REVIEW_LIMIT:
            break

        org_type = str(spec["org_type"])
        org = await db.get_organization_by_type(org_type)
        if not org:
            continue

        role_slot = "leader_id" if str(spec.get("slot")) == "leader" else "deputy_id"
        reviewer_id = int(org.get(role_slot) or 0)
        if reviewer_id != int(spec["user_id"]):
            continue

        pending = await db.get_organization_applications(
            org_id=int(org["id"]),
            status="pending",
            limit=AI_GOV_REVIEW_PER_ORG,
        )
        for app in pending:
            if reviewed >= AI_GOV_REVIEW_LIMIT:
                break
            app_id = int(app.get("id") or 0)
            applicant_id = int(app.get("user_id") or 0)
            if app_id <= 0 or applicant_id <= 0:
                continue

            applicant = await db.get_user(applicant_id) or {}
            if int(applicant.get("is_ai_agent") or 0) == 1:
                ok, _ = await db.review_organization_application(
                    reviewer_id=reviewer_id,
                    application_id=app_id,
                    approve=False,
                    note="РЎРёСЃС‚РµРјРЅС‹Рµ AI-Р°РєРєР°СѓРЅС‚С‹ РЅРµ РґРѕРїСѓСЃРєР°СЋС‚СЃСЏ.",
                )
                if ok:
                    reviewed += 1
                    rejected += 1
                continue

            decision = await reviewer.review(
                org_type=org_type,
                org_name=str(org.get("name") or ""),
                role_label=str(spec.get("role") or "AI Officer"),
                application_text=str(app.get("application_text") or ""),
                applicant=applicant,
            )
            if decision is None:
                decision = _fallback_review(
                    org_type=org_type,
                    role_label=str(spec.get("role") or "AI Officer"),
                    application_text=str(app.get("application_text") or ""),
                    applicant=applicant,
                )

            ok, _ = await db.review_organization_application(
                reviewer_id=reviewer_id,
                application_id=app_id,
                approve=bool(decision.get("approve")),
                note=_safe_note(
                    decision.get("note"),
                    f"РР ({spec.get('role')}) РїСЂРёРЅСЏР» СЂРµС€РµРЅРёРµ.",
                ),
            )
            if not ok:
                continue

            reviewed += 1
            if bool(decision.get("approve")):
                approved += 1
            else:
                rejected += 1

    return {"reviewed": reviewed, "approved": approved, "rejected": rejected}


def _hour_slot_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H")


async def _broadcast_hourly_report(bot: Bot, text: str) -> Dict[str, int]:
    chats = await db.get_active_group_chats()
    sent = 0
    failed = 0
    for chat in chats:
        chat_id = int(chat.get("chat_id") or 0)
        if chat_id == 0:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
            sent += 1
        except Exception as exc:
            failed += 1
            err = str(exc).lower()
            if any(token in err for token in ("forbidden", "kicked", "chat not found")):
                try:
                    await db.deactivate_bot_chat(chat_id)
                except Exception:
                    pass
    return {"sent": sent, "failed": failed, "total": len(chats)}


async def _run_two_leader_actions(target_count: int = 2) -> list[Dict[str, Any]]:
    count = max(1, int(target_count or 2))
    leader_specs = [
        spec
        for spec in AI_ROLE_SPECS
        if str(spec.get("slot") or "").strip().lower() == "leader"
    ]
    if len(leader_specs) < count:
        used_tags = {str(spec.get("tag") or "") for spec in leader_specs}
        for spec in AI_ROLE_SPECS:
            tag = str(spec.get("tag") or "")
            if tag in used_tags:
                continue
            leader_specs.append(spec)
            used_tags.add(tag)
            if len(leader_specs) >= count:
                break

    random.shuffle(leader_specs)
    selected = leader_specs[:count]
    actions: list[Dict[str, Any]] = []

    for spec in selected:
        actor_id = int(spec.get("user_id") or 0)
        actor_name = str(spec.get("full_name") or "AI Leader")
        org_type = str(spec.get("org_type") or "")
        org = await db.get_organization_by_type(org_type) if org_type else None
        org_id = int((org or {}).get("id") or 0)
        org_name = str((org or {}).get("name") or org_type or "Organization")

        if actor_id > 0 and org_id > 0 and await db.can_manage_organization(actor_id, org_id):
            ok, _, payload = await db.run_org_initiative(actor_id, org_id)
            if ok:
                data = payload or {}
                actions.append(
                    {
                        "kind": "initiative",
                        "actor_id": actor_id,
                        "actor_name": actor_name,
                        "org_id": org_id,
                        "org_name": org_name,
                        "delta_budget": float(data.get("delta_budget") or 0.0),
                        "delta_rep": int(data.get("delta_rep") or 0),
                    }
                )
                continue

        actions.append(
            {
                "kind": "audit",
                "actor_id": actor_id,
                "actor_name": actor_name,
                "org_id": org_id,
                "org_name": org_name,
            }
        )

    return actions


def _format_leader_action_line(action: Dict[str, Any]) -> str:
    actor_name = str(action.get("actor_name") or "AI Leader")
    org_name = str(action.get("org_name") or "Organization")
    if str(action.get("kind") or "") == "initiative":
        delta_budget = float(action.get("delta_budget") or 0.0)
        delta_rep = int(action.get("delta_rep") or 0)
        return f"- {actor_name}: инициатива в {org_name} (+${delta_budget:,.0f}, реп +{delta_rep})"
    return f"- {actor_name}: внутренняя проверка в {org_name}"


async def _run_hourly_public_action(
    bot: Optional[Bot],
    staffing: Dict[str, int],
    reviews: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    if bot is None or not AI_GOV_GROUP_REPORT_ENABLED:
        return None

    now = datetime.now(UZBEKISTAN_TZ)
    slot = _hour_slot_key(now)
    state_key = "ai_governance_hourly_action_slot"
    last_slot = await db.get_system_state(state_key)
    if last_slot == slot:
        return None

    actions = await _run_two_leader_actions(target_count=2)
    action_lines = [_format_leader_action_line(action) for action in actions]
    action_block = "\n".join(action_lines) if action_lines else "- Нет доступных действий"

    text = (
        "🤖 Ежечасный отчет Гос-ИИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Слот: {slot}:00 (Asia/Tashkent)\n"
        "Действия лидеров:\n"
        f"{action_block}\n"
        f"Кадры: активных AI={int(staffing.get('active', 0))}, назначено={int(staffing.get('assigned', 0))}, освобождено={int(staffing.get('released', 0))}\n"
        f"Заявки: обработано={int(reviews.get('reviewed', 0))}, одобрено={int(reviews.get('approved', 0))}, отклонено={int(reviews.get('rejected', 0))}"
    )

    send_stats = await _broadcast_hourly_report(bot, text)
    await db.set_system_state(state_key, slot)
    try:
        await db.create_media_news(
            title="Ежечасный отчет Гос-ИИ",
            body=text[:1100],
            source_user_id=int(AI_ROLE_SPECS[0]["user_id"]),
            severity="normal",
        )
    except Exception:
        pass

    return {
        "slot": slot,
        "actions": actions,
        "actions_done": len(actions),
        "send_stats": send_stats,
    }


async def _run_startup_public_action(
    bot: Optional[Bot],
    staffing: Dict[str, int],
    reviews: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    if bot is None or not AI_GOV_GROUP_REPORT_ENABLED:
        return None

    now = datetime.now(UZBEKISTAN_TZ)
    slot = _hour_slot_key(now)
    actions = await _run_two_leader_actions(target_count=2)
    action_lines = [_format_leader_action_line(action) for action in actions]
    action_block = "\n".join(action_lines) if action_lines else "- Нет доступных действий"

    text = (
        "🤖 Стартовый отчет Гос-ИИ\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"Время запуска: {now.strftime('%Y-%m-%d %H:%M')} (Asia/Tashkent)\n"
        "Действия лидеров:\n"
        f"{action_block}\n"
        f"Кадры: активных AI={int(staffing.get('active', 0))}, назначено={int(staffing.get('assigned', 0))}, освобождено={int(staffing.get('released', 0))}\n"
        f"Заявки: обработано={int(reviews.get('reviewed', 0))}, одобрено={int(reviews.get('approved', 0))}, отклонено={int(reviews.get('rejected', 0))}"
    )

    send_stats = await _broadcast_hourly_report(bot, text)
    try:
        await db.create_media_news(
            title="Стартовый отчет Гос-ИИ",
            body=text[:1100],
            source_user_id=int(AI_ROLE_SPECS[0]["user_id"]),
            severity="normal",
        )
    except Exception:
        pass

    # Startup action already happened in the current hour. Avoid duplicate hourly post.
    await db.set_system_state("ai_governance_hourly_action_slot", slot)

    return {
        "slot": slot,
        "actions": actions,
        "actions_done": len(actions),
        "send_stats": send_stats,
    }


async def run_ai_governance_cycle(bot: Optional[Bot] = None) -> None:
    """
    Persistent governance loop.
    `bot` is reserved for future notifications and kept for integration symmetry.
    """
    if not AI_GOV_ENABLED:
        logger.info("AI governance is disabled (AI_GOV_ENABLED=0).")
        return

    reviewer = OpenRouterReviewer()
    logger.info(
        "AI governance started: interval=%ss, openrouter=%s, model=%s",
        AI_GOV_INTERVAL_SECONDS,
        "on" if reviewer.enabled else "off",
        OPENROUTER_MODEL if reviewer.enabled else "-",
    )

    try:
        staffing = await _ensure_ai_staffing()
        reviews = await _review_pending_org_applications(reviewer)
        startup = await _run_startup_public_action(bot, staffing, reviews)

        if (
            int(staffing.get("assigned", 0)) > 0
            or int(staffing.get("released", 0)) > 0
            or int(reviews.get("reviewed", 0)) > 0
        ):
            logger.info(
                "AI governance startup: active=%s assigned=%s released=%s reviewed=%s approved=%s rejected=%s",
                int(staffing.get("active", 0)),
                int(staffing.get("assigned", 0)),
                int(staffing.get("released", 0)),
                int(reviews.get("reviewed", 0)),
                int(reviews.get("approved", 0)),
                int(reviews.get("rejected", 0)),
            )

        if startup:
            send_stats = startup.get("send_stats") or {}
            logger.info(
                "AI startup action: slot=%s actions=%s groups_sent=%s groups_failed=%s",
                startup.get("slot"),
                int(startup.get("actions_done", 0)),
                int(send_stats.get("sent", 0)),
                int(send_stats.get("failed", 0)),
            )
    except Exception:
        logger.exception("AI governance startup cycle failed")

    while True:
        try:
            staffing = await _ensure_ai_staffing()
            reviews = await _review_pending_org_applications(reviewer)
            hourly = await _run_hourly_public_action(bot, staffing, reviews)

            if (
                int(staffing.get("assigned", 0)) > 0
                or int(staffing.get("released", 0)) > 0
                or int(reviews.get("reviewed", 0)) > 0
            ):
                logger.info(
                    "AI governance cycle: active=%s assigned=%s released=%s reviewed=%s approved=%s rejected=%s",
                    int(staffing.get("active", 0)),
                    int(staffing.get("assigned", 0)),
                    int(staffing.get("released", 0)),
                    int(reviews.get("reviewed", 0)),
                    int(reviews.get("approved", 0)),
                    int(reviews.get("rejected", 0)),
                )

            if hourly:
                send_stats = hourly.get("send_stats") or {}
                logger.info(
                    "AI hourly action: slot=%s actions=%s groups_sent=%s groups_failed=%s",
                    hourly.get("slot"),
                    int(hourly.get("actions_done", 0)),
                    int(send_stats.get("sent", 0)),
                    int(send_stats.get("failed", 0)),
                )
        except Exception:
            logger.exception("AI governance cycle failed")

        await asyncio.sleep(AI_GOV_INTERVAL_SECONDS)
