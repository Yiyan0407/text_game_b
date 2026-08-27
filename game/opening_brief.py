from pydantic import BaseModel, Field


class OpeningBrief(BaseModel):
    role_in_story: str = ""
    why_at_scene: str = ""
    hook_alignment: str = ""
    public_setup: str = ""
    secrets_from_npcs: list[str] = Field(default_factory=list)
    narrative_constraints: list[str] = Field(default_factory=list)
    starter_skills: list[str] = Field(default_factory=list)

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
        if self.starter_skills:
            lines.append(
                f"背景隐含技能（系统将在开局同步，KP 勿重复 add）：{'、'.join(self.starter_skills)}"
            )
        return "\n".join(lines)

    @classmethod
    def fallback(cls, character_name: str, character_background: str, scenario) -> "OpeningBrief":
        bg = character_background.strip() or "普通冒险者"
        opening = scenario.opening_prompt.strip() or scenario.description.strip()
        secrets: list[str] = []
        constraints = [
            "不得将玩家写成与背景明显矛盾的身份，除非明确伪装/隐姓埋名且开篇点明",
            "不得否定玩家背景中的关键事实",
        ]
        public_setup = ""
        bg_lower = bg.lower()
        if any(k in bg for k in ("黑客", "hacker", "暗网", "匿名", "octopus")) or "octopus" in bg_lower:
            secrets.extend(
                [
                    "NPC 不知道玩家就是匿名投递者/线人代号背后的人",
                    "若线索经加密通道或代号送达，NPC 只能看到匿名包本身，不能开场指认玩家为发信人",
                ]
            )
            constraints.append(
                "禁止在同一场景里既写「匿名代号投递」又写「NPC 已确认是玩家所发」"
            )
            public_setup = (
                "匿名压缩包已出现在编辑部系统中；玩家若在场，须有与投递身份隔离的表面理由"
                "（如外包顾问、修网络），NPC 对其真实身份起疑可以，但不能已确知"
            )
        return cls(
            role_in_story=f"{character_name}（背景：{bg}）",
            why_at_scene=f"按模组开场进入「{scenario.opening_scene_name}」，动机须与背景一致。",
            hook_alignment=f"模组钩子：{opening}。请解释该角色为何在此，而非套用与背景冲突的默认职业。",
            public_setup=public_setup,
            secrets_from_npcs=secrets,
            narrative_constraints=constraints,
        )
