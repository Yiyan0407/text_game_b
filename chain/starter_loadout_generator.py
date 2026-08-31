from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from config.settings import PROMPTS_DIR
from game.starter_loadout import (
    StarterLoadout,
    StarterLoadoutGenerationError,
    parse_starter_loadout_dict,
)
from prompts.templates import load_world_prompt


class StarterLoadoutGenerator:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.3)
        system_prompt = (PROMPTS_DIR / "starter_loadout_generator.txt").read_text(
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
                    "请输出创角初始行囊 JSON：",
                ),
            ]
        )

    def generate(self, background: str, *, world_id: str) -> StarterLoadout:
        text = background.strip()
        if not text:
            raise StarterLoadoutGenerationError("背景为空，无法生成初始行囊。")

        chain = self.prompt | self.llm
        response = chain.invoke(
            {
                "world_rules": load_world_prompt(world_id),
                "world_id": world_id,
                "background": text,
            }
        )
        loadout = self._parse_response((response.content or "").strip())
        if not loadout.skills and not loadout.inventory:
            raise StarterLoadoutGenerationError(
                "AI 未返回有效初始技能或物品，请稍后再试或微调背景。"
            )
        return loadout

    @staticmethod
    def _parse_response(text: str) -> StarterLoadout:
        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return StarterLoadout()
        return parse_starter_loadout_dict(data)
