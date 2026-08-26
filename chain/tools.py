from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool

from game.combat import end_combat, player_attack, start_combat
from game.dice import roll
from game.models import ABILITY_FIELDS, Character, GameState
from game.rules import ability_check, format_check_for_kp

AbilityKey = Literal["str", "dex", "con", "int", "wis", "cha"]
_ABILITY_HINT = " / ".join(ABILITY_FIELDS)


def create_kp_tools(character: Character, game_state: GameState) -> list[BaseTool]:
    """为当前角色与游戏状态创建 KP 可用的 LangChain Tools。"""

    def roll_dice(notation: str) -> str:
        """掷骰子。用于伤害、随机事件、非战斗掷骰。notation 示例: d20, 2d6, 1d20+3"""
        return roll(notation).describe()

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
        """记录或更新 NPC 信息。遇到新 NPC 或关系变化时调用。"""
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
    ) -> str:
        """玩家获得或失去物品时调用。物品名称须符合当前世界观与模组设定。"""
        cleaned = item.strip()
        if not cleaned:
            return "物品名称不能为空。"
        if action == "add":
            if character.add_inventory_item(cleaned):
                return f"背包新增：{cleaned}。当前：{character.format_inventory()}"
            if cleaned in character.inventory:
                return f"背包中已有：{cleaned}"
            return "添加失败。"
        if character.remove_inventory_item(cleaned):
            return f"背包移除：{cleaned}。当前：{character.format_inventory()}"
        return f"背包中没有：{cleaned}"

    def record_memory_fact(fact: str) -> str:
        """当发生必须长期记住的事件时调用（获得关键物品、重要承诺、重大真相、NPC 秘密等）。"""
        from config.settings import get_settings

        settings = get_settings()
        game_state.add_memory_facts([fact.strip()], settings.max_memory_facts)
        return f"已记录关键事实：{fact.strip()}"

    return [
        StructuredTool.from_function(
            func=roll_dice,
            name="roll_dice",
            description=(
                "掷骰子。凡需要随机结果时（伤害、遭遇、随机事件等）必须调用，"
                "不要自行编造骰点。notation 示例: d20, 2d6, 1d6+2"
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
            description="遇到新 NPC 或 NPC 关系/信息变化时调用，记录姓名、态度与备注。",
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
                "更新玩家背包。获得物品时 action=add，失去/消耗/丢弃时 action=remove。"
                "物品名称须符合当前世界观（现代勿给短剑金币，赛博勿给火把等）。"
                "重要物品可同时调用 record_memory_fact。"
            ),
        ),
        StructuredTool.from_function(
            func=record_memory_fact,
            name="record_memory_fact",
            description="记录必须长期记住的事实：关键物品、承诺、真相、NPC 秘密、玩家目标等。",
        ),
    ]
