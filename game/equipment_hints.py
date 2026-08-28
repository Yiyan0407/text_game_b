"""装备同步提示：供 State Agent 参考。"""

from __future__ import annotations

from game.models import Character, ChatMessage

_IMPLANT_TOPIC_MARKERS = ("义体", "植入", "改造", "体内", "模块")
_IMPLANT_BACKGROUND_MARKERS = ("义体", "植入", "改造", "战斗组", "军用")


def format_equipment_sync_hint(
    character: Character,
    user_input: str,
    history: list[ChatMessage],
    *,
    kp_narrative: str = "",
) -> str:
    """提醒 ItemSync Agent 须结合上下文自行裁定是否 equip。"""
    user_text = user_input.strip()
    background = character.background.strip()
    recent_kp = kp_narrative.strip()
    if not recent_kp:
        for msg in reversed(history[-6:]):
            if msg.role == "assistant":
                recent_kp = msg.content.strip()
                break

    lines = [
        "须结合【最近对话】【玩家行动】【机械结算】【背包/装备现状】自行判断：",
        "- 叙事上已完成穿戴/植入/装配，或体内/背景义体被确认存在且可用 → 须 inventory add（如需）并 **equipment equip**",
        "- 纯观察/盘点/询问且未改变装备状态 → 勿 equip",
        "- **禁止**只写 memory_facts 而不入库、不进装备栏",
        "勿依赖玩家是否说了「都装上」等字眼；以情境为准。",
    ]

    topic_hit = any(marker in user_text for marker in _IMPLANT_TOPIC_MARKERS) or any(
        marker in background for marker in _IMPLANT_BACKGROUND_MARKERS
    )
    if topic_hit and recent_kp and any(
        marker in recent_kp for marker in ("义体", "植入", "芯片", "接口", "模块", "HUD")
    ):
        lines.append(
            "【提示】最近 KP 叙事可能列出了体内模块或已完成装配；请逐项同步到 inventory + body/hand/accessory equip。"
        )

    return "\n".join(lines)
