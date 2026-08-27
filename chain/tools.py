from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool

from game.combat import end_combat, player_attack, start_combat
from game.dice import roll
from game.models import ABILITY_FIELDS, Character, GameState
from game.rules import ability_check, format_check_for_kp
from game.inventory import item_name_from_ref
from game.text_match import fuzzy_match_name

AbilityKey = Literal["str", "dex", "con", "int", "wis", "cha"]
_ABILITY_HINT = " / ".join(ABILITY_FIELDS)


NO_TOOL_NEEDED_NAME = "no_tool_needed"


def create_kp_tools(
    character: Character,
    game_state: GameState,
    *,
    exclude_roll_tools: bool = False,
    exclude_combat_tools: bool = False,
    delivered_items: frozenset[str] | None = None,
) -> list[BaseTool]:
    """为当前角色与游戏状态创建 KP 可用的 LangChain Tools。"""
    delivered = delivered_items or frozenset()
    added_this_turn: set[str] = set()

    def roll_dice(notation: str) -> str:
        """掷骰子。用于伤害、随机事件、非战斗掷骰。notation 示例: d20, d100, 2d6, 1d20+3"""
        try:
            return roll(notation).describe()
        except ValueError as exc:
            return (
                f"掷骰失败：{exc}。"
                "请使用标准格式，如 d20、d100、2d6、1d20+3；百分骰写 d100，不要只写 100。"
            )

    def run_ability_check(
        ability: AbilityKey,
        dc: int,
    ) -> str:
        """当玩家行动需要属性检定时调用。ability 为六维属性，dc 为难度值（简单10/中等14/困难18）。"""
        result = ability_check(character, ability, dc)
        return format_check_for_kp(result, character)

    def update_scene(scene_id: str, scene_name: str) -> str:
        """当玩家进入新场景时调用，更新当前场景 ID 与名称。"""
        game_state.scene_id = scene_id
        game_state.current_scene = scene_name
        game_state.scene_image_url = ""
        return f"场景已更新：{scene_name}（{scene_id}）"

    def record_npc(
        name: str,
        attitude: Literal["friendly", "neutral", "hostile", "unknown"],
        notes: str = "",
    ) -> str:
        """记录或更新 NPC 信息。遇到新 NPC、失踪者/嫌疑人被介绍、或关系/情报变化时调用。
        尚未见过面用 attitude=unknown；notes 写一句关键身份或线索。"""
        game_state.upsert_npc(name=name, attitude=attitude, notes=notes)
        return f"已记录 NPC：{name}（{attitude}）"

    def update_quest(
        quest_id: str,
        title: str,
        status: Literal["active", "completed", "failed"],
        description: str = "",
    ) -> str:
        """更新任务状态。任务进展、完成或失败时调用。"""
        game_state.upsert_quest(
            quest_id=quest_id,
            title=title,
            status=status,
            description=description,
        )
        return f"任务已更新：[{quest_id}] {title}（{status}）"

    def run_start_combat(enemies_spec: str) -> str:
        """进入战斗。enemies_spec 格式：名字:HP:AC，多个用逗号分隔，如 守卫:12:12,野狗:8:10"""
        return start_combat(character, game_state, enemies_spec)

    def run_player_attack(target_name: str, use_dex: bool = False) -> str:
        """玩家攻击指定敌人（战斗中进行）。use_dex=True 用敏捷，否则用力量。"""
        return player_attack(character, game_state, target_name, use_dex=use_dex)

    def run_end_combat() -> str:
        """所有敌人被击倒或战斗结束时调用。"""
        return end_combat(game_state)

    def update_inventory(
        action: Literal["add", "remove"],
        item: str,
        quantity: int = 1,
        unit: str = "个",
        description: str = "",
    ) -> str:
        """玩家获得或失去物品时调用。item 为物品名称或完整显示名（如 铜板（97枚））；
        quantity 为数量，unit 为单位（枚/袋/个/把等）；description 为物品说明（用途、特性等）。
        同类物品会自动合并堆叠。"""
        cleaned = item.strip()
        if not cleaned:
            return "物品名称不能为空。"
        if quantity <= 0:
            return "数量必须大于 0。"
        item_name = item_name_from_ref(cleaned) or cleaned
        if action == "add":
            if delivered and any(
                fuzzy_match_name(item_name, delivered_name)
                for delivered_name in delivered
            ):
                return f"跳过重复添加：{item_name}（已在交易结算中交付）。"
            if item_name in added_this_turn:
                existing = character.find_inventory_item(cleaned)
                if existing and description.strip() and not existing.description.strip():
                    existing.description = description.strip()
                    return f"已补充描述：{existing.format_detail()}"
                if quantity == 1 and (not unit or unit == "个"):
                    return f"跳过重复添加：{item_name}（本轮已入库）。"
            if character.add_inventory_item(
                cleaned,
                quantity=quantity,
                unit=unit,
                description=description,
            ):
                added_this_turn.add(item_name)
                matched = character.find_inventory_item(cleaned)
                label = matched.format_detail() if matched else cleaned
                return f"获得：{label}"
            return "添加失败。"
        ok, message = character.consume_inventory_quantity(
            cleaned,
            quantity,
            unit=unit if unit != "个" else None,
        )
        if ok:
            return message
        return message

    def record_memory_fact(fact: str) -> str:
        """当发生必须长期记住的事件时调用（获得关键物品、重要承诺、重大真相、NPC 秘密等）。"""
        from config.settings import get_settings

        settings = get_settings()
        game_state.add_memory_facts([fact.strip()], settings.max_memory_facts)
        return f"已记录关键事实：{fact.strip()}"

    def update_skills(
        action: Literal["add", "remove"],
        skill: str,
        description: str = "",
    ) -> str:
        """玩家学会或失去技能时调用。description 写技能用途或效果简述（1 句）。"""
        cleaned = skill.strip()
        if not cleaned:
            return "技能名称不能为空。"
        if action == "add":
            if character.add_skill(cleaned, description=description):
                matched = character.find_skill(cleaned)
                label = matched.format_detail() if matched else cleaned
                return f"习得技能：{label}"
            if character.has_skill(cleaned):
                return f"已拥有技能：{cleaned}"
            return "添加失败。"
        if character.remove_skill(cleaned):
            return f"失去技能：{cleaned}"
        return f"你没有这项技能：{cleaned}"

    def no_tool_needed(reason: str = "") -> str:
        """本轮不需要调用任何其他工具、可以开始写叙事时调用。"""
        cleaned = reason.strip()
        if cleaned:
            return f"无需其他工具，可以开始叙事。（{cleaned}）"
        return "无需其他工具，可以开始叙事。"

    tools = [
        StructuredTool.from_function(
            func=no_tool_needed,
            name=NO_TOOL_NEEDED_NAME,
            description=(
                "当本轮不需要调用任何其他工具（无场景/背包/技能/任务/NPC/记忆/战斗/掷骰变更）时调用，"
                "表示工具阶段结束、可以输出叙事。若已调用过其他必要工具，最后一轮也须调用本工具再写叙事。"
            ),
        ),
        StructuredTool.from_function(
            func=roll_dice,
            name="roll_dice",
            description=(
                "掷骰子。凡需要随机结果时（伤害、遭遇、随机事件等）必须调用，"
                "不要自行编造骰点。notation 必须用标准格式：d20、d100、2d6、1d20+3；"
                "百分骰写 d100，不要只写数字 100。"
            ),
        ),
        StructuredTool.from_function(
            func=run_ability_check,
            name="ability_check",
            description=(
                "进行属性检定。行动结果不确定时必须调用，不要让玩家自行掷骰。"
                f"ability 为六维属性：{_ABILITY_HINT}；"
                "dc 为难度值，简单 10、中等 14、困难 18。"
            ),
        ),
        StructuredTool.from_function(
            func=update_scene,
            name="update_scene",
            description="玩家进入新地点时调用，更新 scene_id 与 scene_name。",
        ),
        StructuredTool.from_function(
            func=record_npc,
            name="record_npc",
            description=(
                "记录或更新 NPC。玩家本回合获知某有姓名人物的情报时须调用（含当面出场、"
                "他人转述的失踪者/嫌疑人/证人）。尚未见过面用 attitude=unknown；"
                "notes 写一句关键身份或线索。须在写叙事之前调用，每人一次。"
            ),
        ),
        StructuredTool.from_function(
            func=update_quest,
            name="update_quest",
            description="任务状态变化时调用，更新任务 ID、标题、状态与描述。",
        ),
        StructuredTool.from_function(
            func=run_start_combat,
            name="start_combat",
            description="遭遇战开始时调用。enemies_spec 如：守卫:12:12,野狗:8:10",
        ),
        StructuredTool.from_function(
            func=run_player_attack,
            name="player_attack",
            description="战斗中进行攻击检定时调用，指定 target_name 与是否用敏捷。",
        ),
        StructuredTool.from_function(
            func=run_end_combat,
            name="end_combat",
            description="战斗结束、所有敌人被击倒或敌人撤退时调用。",
        ),
        StructuredTool.from_function(
            func=update_inventory,
            name="update_inventory",
            description=(
                "更新玩家背包。玩家在本轮获得、拾取、被给予物品时 action=add；"
                "失去/消耗/丢弃/付款时 action=remove。"
                "参数 item 为名称或完整显示名；quantity 为数量（默认 1）；unit 为单位（默认 个，"
                "货币常用 枚，散装常用 袋）；description 为物品说明（外观/用途/规则，1–2 句）。"
                "同类会自动合并，如 add item=铜板 quantity=97 unit=枚。"
                "购买找零、交易找补也须 add。"
                "若机械结算已扣款交货，勿重复 remove/add 同一物品；只补找零。"
                "须在写叙事之前调用，禁止只写「你获得了 X」而不调用本工具。"
            ),
        ),
        StructuredTool.from_function(
            func=record_memory_fact,
            name="record_memory_fact",
            description="记录必须长期记住的事实：关键物品、承诺、真相、NPC 秘密、玩家目标等。",
        ),
        StructuredTool.from_function(
            func=update_skills,
            name="update_skills",
            description=(
                "更新玩家技能。NPC 传授、训练成功、任务奖励时 action=add；"
                "失去/遗忘时 action=remove。须带 description（技能用途，1 句）。"
                "开局背景技能若已同步则勿重复 add。"
                "须在写叙事之前调用。技能名称须符合当前世界观与模组设定。"
            ),
        ),
    ]
    if exclude_roll_tools:
        tools = [tool for tool in tools if tool.name not in {"roll_dice", "ability_check"}]
    if exclude_combat_tools:
        tools = [tool for tool in tools if tool.name not in {"start_combat", "player_attack"}]
    return tools
