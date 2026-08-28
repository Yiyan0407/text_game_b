"""属性检定难度（DC）的合法范围与情境化 fallback。"""

from __future__ import annotations

DC_MIN = 5
DC_MAX = 30


def clamp_dc(dc: int) -> int:
    return max(DC_MIN, min(DC_MAX, int(dc)))


def is_valid_dc(dc: int) -> bool:
    return DC_MIN <= int(dc) <= DC_MAX


def infer_ability_check_dc(
    *,
    ability: str = "",
    action_intent: str = "",
    user_input: str = "",
    context: str = "",
    in_combat: bool = False,
    combat_action: str = "none",
    proficiency_bonus: bool = False,
) -> int:
    """路由未给出合法 DC 时的情境 fallback（非固定 14）。"""
    text = f"{action_intent} {user_input}".lower()
    ctx = context.lower()
    combined = f"{text} {ctx}"

    base = 12

    if in_combat:
        combat_bases = {
            "grapple": 14,
            "shove": 12,
            "talk": 14,
            "search": 13,
            "interact": 14,
        }
        base = combat_bases.get(combat_action, 13)

    hard_markers = (
        "极难",
        "几乎不可能",
        "不可能",
        "顶级",
        "精英",
        "严密",
        "加密",
        "高手",
        "大师",
        "重重",
        "高度戒备",
    )
    easy_markers = (
        "简单",
        "轻松",
        "容易",
        "初步",
        "粗略",
        "随便",
        "日常",
        "普通",
    )
    security_markers = ("巡逻", "安保", "监控", "门禁", "警报", "重地", "非授权")

    if any(marker in combined for marker in hard_markers):
        base += 4
    elif any(marker in combined for marker in easy_markers):
        base -= 2

    security_hits = sum(1 for marker in security_markers if marker in combined)
    base += min(4, security_hits * 2)

    if proficiency_bonus:
        base -= 1

    ability_key = ability.lower()
    if ability_key in ("str", "dex") and any(
        word in text for word in ("潜行", "潜入", "渗透", "溜进", "避开")
    ):
        base += 1

    if ability_key == "cha" and any(word in text for word in ("说服", "欺骗", "威胁", "谈判")):
        if "hostile" in combined or "敌意" in combined or "愤怒" in combined:
            base += 2

    return clamp_dc(base)


def ensure_ability_check_dc(
    route,
    *,
    user_input: str = "",
    context: str = "",
) -> None:
    """保留 AI 已给出的合法 DC；缺失或越界时用情境 fallback 或 clamp。"""
    if is_valid_dc(route.dc):
        route.dc = clamp_dc(route.dc)
        return

    route.dc = infer_ability_check_dc(
        ability=route.ability,
        action_intent=route.action_intent,
        user_input=user_input,
        context=context,
        in_combat=route.mode == "combat",
        combat_action=route.combat_action,
        proficiency_bonus=route.proficiency_bonus,
    )
