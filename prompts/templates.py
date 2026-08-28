from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config.settings import PROMPTS_DIR
from config.worlds import DEFAULT_WORLD_ID
from game.game_config import KpGuidance


def load_kp_base_prompt() -> str:
    return (PROMPTS_DIR / "kp_base.txt").read_text(encoding="utf-8")


def load_world_prompt(world_id: str) -> str:
    path = PROMPTS_DIR / "worlds" / f"{world_id}.txt"
    if not path.exists():
        path = PROMPTS_DIR / "worlds" / f"{DEFAULT_WORLD_ID}.txt"
    return path.read_text(encoding="utf-8")


def load_kp_guidance_mode_prompt(kp_guidance: KpGuidance = "balanced") -> str:
    modes = (PROMPTS_DIR / "kp_guidance_modes.txt").read_text(encoding="utf-8")
    section_map = {
        "freeform": "### 自由即兴",
        "balanced": "### 平衡引导",
        "script_guided": "### 按剧本推进",
    }
    marker = section_map.get(kp_guidance, section_map["balanced"])
    start = modes.find(marker)
    if start < 0:
        return ""
    rest = modes[start + len(marker) :]
    next_heading = rest.find("\n### ")
    body = rest[:next_heading].strip() if next_heading >= 0 else rest.strip()
    return f"## 本局 KP 引导模式\n{body}" if body else ""


def load_kp_system_prompt(
    world_id: str = DEFAULT_WORLD_ID,
    kp_guidance: KpGuidance = "balanced",
) -> str:
    parts = [load_kp_base_prompt(), load_world_prompt(world_id)]
    mode_prompt = load_kp_guidance_mode_prompt(kp_guidance)
    if mode_prompt:
        parts.append(mode_prompt)
    return "\n\n".join(parts)


def build_kp_prompt(
    world_id: str = DEFAULT_WORLD_ID,
    kp_guidance: KpGuidance = "balanced",
) -> ChatPromptTemplate:
    system = load_kp_system_prompt(world_id, kp_guidance=kp_guidance)
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


def build_narrative_prompt(
    world_id: str = DEFAULT_WORLD_ID,
    kp_guidance: KpGuidance = "balanced",
) -> ChatPromptTemplate:
    """纯叙事 KP 使用的 Prompt。"""
    return build_kp_prompt(world_id, kp_guidance=kp_guidance)
