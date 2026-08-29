from pydantic import BaseModel, Field, field_validator

from game.models import GameState, Quest


def _coerce_optional_str(value) -> str:
    if value is None:
        return ""
    return str(value)


class ScenarioNode(BaseModel):
    id: str
    title: str
    description: str = ""

    @field_validator("description", mode="before")
    @classmethod
    def _coerce_description(cls, value):
        return _coerce_optional_str(value)


class ScenarioEnding(BaseModel):
    id: str
    title: str
    condition: str = ""

    @field_validator("condition", mode="before")
    @classmethod
    def _coerce_condition(cls, value):
        return _coerce_optional_str(value)


class Scenario(BaseModel):
    id: str
    title: str
    description: str = ""
    world_id: str = "fantasy"
    world: str = ""
    tone: str = ""
    opening_scene_id: str = "start"
    opening_scene_name: str = "起点"
    opening_prompt: str = ""
    initial_quests: list[Quest] = Field(default_factory=list)
    key_nodes: list[ScenarioNode] = Field(default_factory=list)
    endings: list[ScenarioEnding] = Field(default_factory=list)
    custom_world_overlay: str = ""
    is_generated: bool = False

    @field_validator(
        "description",
        "world",
        "tone",
        "opening_prompt",
        "custom_world_overlay",
        mode="before",
    )
    @classmethod
    def _coerce_optional_strings(cls, value):
        return _coerce_optional_str(value)

    @field_validator("initial_quests", "key_nodes", "endings", mode="before")
    @classmethod
    def _coerce_optional_lists(cls, value):
        return [] if value is None else value

    def format_for_prompt(self) -> str:
        lines = [
            f"模组：{self.title}",
            f"世界观：{self.world}（规则包：{self.world_id}）",
            f"基调：{self.tone}",
            "说明：简介与开场是任务/场景钩子，不是对玩家身份的强制设定；以【玩家角色】与【开场入场逻辑】为准。",
            f"简介：{self.description}",
        ]
        if self.custom_world_overlay:
            lines.append(f"世界观扩展设定：\n{self.custom_world_overlay}")
        lines.append(f"开场：{self.opening_prompt}")
        if self.key_nodes:
            lines.append("关键节点（供 KP 参考推进；地点名即可，scene_id 由状态/地图 Agent 生成，勿一次性剧透）：")
            for node in self.key_nodes:
                lines.append(f"- {node.title}：{node.description}")
        if self.endings:
            lines.append("可能结局：")
            for ending in self.endings:
                lines.append(f"- [{ending.id}] {ending.title}：{ending.condition}")
        return "\n".join(lines)

    def apply_to_game_state(self, game_state: GameState) -> None:
        from game.narrative_time import initialize_story_clock_from_scenario
        from game.scene_map import bootstrap_scene_map

        game_state.scenario_id = self.id
        game_state.scene_id = self.opening_scene_id
        game_state.current_scene = self.opening_scene_name
        if self.initial_quests:
            game_state.active_quests = list(self.initial_quests)
        initialize_story_clock_from_scenario(game_state, self)
        bootstrap_scene_map(game_state, self, reset=True)
