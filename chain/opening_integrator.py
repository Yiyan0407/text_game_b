from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.models import Character
from game.opening_brief import OpeningBrief
from game.scenario import Scenario


class OpeningIntegrator:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.2)
        system_prompt = (PROMPTS_DIR / "opening_integrator.txt").read_text(encoding="utf-8")
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【玩家角色】\n"
                    "姓名：{character_name}\n"
                    "背景：{character_background}\n\n"
                    "【模组信息】\n{scenario_context}\n\n"
                    "请输出入场逻辑 JSON：",
                ),
            ]
        )

    def generate(self, character: Character, scenario: Scenario) -> OpeningBrief:
        try:
            chain = self.prompt | self.llm
            response = chain.invoke(
                {
                    "character_name": character.name,
                    "character_background": character.background,
                    "scenario_context": scenario.format_for_prompt(),
                }
            )
            brief = self._parse_response((response.content or "").strip())
            if brief.role_in_story.strip():
                return brief
        except Exception:
            pass
        return OpeningBrief.fallback(character.name, character.background, scenario)

    @staticmethod
    def _parse_response(text: str) -> OpeningBrief:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return OpeningBrief()
        constraints = data.get("narrative_constraints", [])
        if not isinstance(constraints, list):
            constraints = []
        secrets = data.get("secrets_from_npcs", [])
        if not isinstance(secrets, list):
            secrets = []
        return OpeningBrief(
            role_in_story=str(data.get("role_in_story", "")).strip(),
            why_at_scene=str(data.get("why_at_scene", "")).strip(),
            hook_alignment=str(data.get("hook_alignment", "")).strip(),
            public_setup=str(data.get("public_setup", "")).strip(),
            secrets_from_npcs=[str(item).strip() for item in secrets if str(item).strip()],
            narrative_constraints=[
                str(item).strip() for item in constraints if str(item).strip()
            ],
            starter_skills=_coerce_skill_list(data.get("starter_skills")),
        )


def _coerce_skill_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        skills: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                desc = str(item.get("description", "")).strip()
                if name:
                    skills.append(f"{name}（{desc}）" if desc else name)
            else:
                stripped = str(item).strip()
                if stripped:
                    skills.append(stripped)
        return skills
    return []
