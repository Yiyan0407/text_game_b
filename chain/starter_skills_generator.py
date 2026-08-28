from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.skills import coerce_skill_list
from prompts.templates import load_world_prompt


class StarterSkillsGenerationError(ValueError):
    pass


class StarterSkillsGenerator:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.3)
        system_prompt = (PROMPTS_DIR / "starter_skills_generator.txt").read_text(
            encoding="utf-8"
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                (
                    "human",
                    "【世界观规则】\n{world_rules}\n\n"
                    "【世界观包】\n{world_id}\n\n"
                    "【角色背景（已审核通过）】\n{background}\n\n"
                    "请输出 skills JSON：",
                ),
            ]
        )

    def generate(self, background: str, *, world_id: str) -> list[str]:
        text = background.strip()
        if not text:
            raise StarterSkillsGenerationError("背景为空，无法生成初始技能。")

        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "world_rules": load_world_prompt(world_id),
                "world_id": world_id,
                "background": text,
            }
        )
        skills = self._parse_response((response.content or "").strip())
        if not skills:
            raise StarterSkillsGenerationError(
                "AI 未返回有效技能，请稍后再试或微调背景。"
            )
        return skills[:3]

    @staticmethod
    def _parse_response(text: str) -> list[str]:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return []
        return coerce_skill_list(data.get("skills"))
