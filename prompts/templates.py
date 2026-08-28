from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config.settings import PROMPTS_DIR

from config.worlds import DEFAULT_WORLD_ID


def load_kp_base_prompt() -> str:
    return (PROMPTS_DIR / "kp_base.txt").read_text(encoding="utf-8")


def load_world_prompt(world_id: str) -> str:
    path = PROMPTS_DIR / "worlds" / f"{world_id}.txt"
    if not path.exists():
        path = PROMPTS_DIR / "worlds" / f"{DEFAULT_WORLD_ID}.txt"
    return path.read_text(encoding="utf-8")


def load_kp_system_prompt(world_id: str = DEFAULT_WORLD_ID) -> str:
    return f"{load_kp_base_prompt()}\n\n{load_world_prompt(world_id)}"


def build_kp_prompt(world_id: str = DEFAULT_WORLD_ID) -> ChatPromptTemplate:
    system = load_kp_system_prompt(world_id)
    return ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "system",
                "当前玩家角色：\n"
                "姓名：{character_name}\n"
                "背景：{character_background}\n"
                "属性：{character_abilities}\n"
                "生命：HP {hp}/{max_hp}\n"
                "背包：{character_inventory}\n"
                "装备：{character_equipment}\n"
                "技能：{character_skills}",
            ),
            (
                "system",
                "【模组信息 — 不可与叙事矛盾】\n{scenario_context}",
            ),
            (
                "system",
                "【游戏状态 — 不可与叙事矛盾】\n{game_state_context}",
            ),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        ]
    )


def build_narrative_prompt(world_id: str = DEFAULT_WORLD_ID) -> ChatPromptTemplate:
    """纯叙事 KP 使用的 Prompt。"""
    return build_kp_prompt(world_id)
