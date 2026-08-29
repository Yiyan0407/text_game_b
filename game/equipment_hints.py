"""装备同步提示：供 ItemSync 参考。"""

from __future__ import annotations

from game.models import Character, ChatMessage


def format_equipment_sync_hint(
    character: Character,
    user_input: str,
    history: list[ChatMessage],
    *,
    kp_narrative: str = "",
) -> str:
    """提醒 ItemSync Agent 须结合上下文自行裁定是否 equip。"""
    return "\n".join(
        [
            "须结合【最近对话】【玩家行动】【机械结算】【背包/装备现状】【角色背景】自行判断：",
            "- item 只写可持有物件的短名称；人物、同伴、动作、环境描写不是物品",
            "- 叙事上该物件已穿在身上、拿在手里或装配完成 → 须 inventory add（如需，**description 必填**）并 **equipment equip**",
            "- 盘点/检查已有装备：KP 确认某物件正在穿戴或持用、背包/装备栏尚无 → **仍须**首次登记，不可因「只是检查」而跳过",
            "- 纯观察/询问且**叙事未引入新物件、装备栏已完整同步** → 输出空 JSON（无 inventory/equipment 变更）",
            "- **禁止**只写 memory_facts 而不入库、不进装备栏",
            "勿依赖玩家是否说了「都装上」等字眼；以情境为准。",
        ]
    )
