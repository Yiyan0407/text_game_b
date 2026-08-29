from pydantic import BaseModel, Field


class OpeningBrief(BaseModel):
    role_in_story: str = ""
    why_at_scene: str = ""
    hook_alignment: str = ""
    public_setup: str = ""
    secrets_from_npcs: list[str] = Field(default_factory=list)
    narrative_constraints: list[str] = Field(default_factory=list)

    def format_for_kp(self) -> str:
        lines = [
            "【开场入场逻辑】",
            f"在本模组中的身份/定位：{self.role_in_story or '与玩家背景一致的入场身份'}",
            f"为何在此场景：{self.why_at_scene or '结合模组开场与玩家背景自然说明'}",
            f"与模组默认开场的关系：{self.hook_alignment or '保留模组核心任务与场景，调整人物身份表述'}",
        ]
        if self.public_setup.strip():
            lines.append(f"场景公开事实：{self.public_setup.strip()}")
        if self.secrets_from_npcs:
            lines.append("NPC 此时还不应知道（不得开场泄露）：")
            for item in self.secrets_from_npcs:
                lines.append(f"- {item}")
        if self.narrative_constraints:
            lines.append("叙事禁止（不可违背）：")
            for item in self.narrative_constraints:
                lines.append(f"- {item}")
        return "\n".join(lines)
