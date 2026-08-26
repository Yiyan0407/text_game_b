import json
import re

from langchain_core.prompts import ChatPromptTemplate
from chain.llm import create_chat_llm


class ActionSuggester:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.7)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是跑团行动建议生成器。根据 KP 最新叙事，为玩家生成 3 个简短可行的行动建议。"
                    "每个建议 8–20 字，动词开头，贴合当前场景，不要剧透。"
                    "只输出 JSON 数组，如：[\"调查吧台\",\"询问酒保\",\"观察门口\"]"
                    "{guidance}",
                ),
                (
                    "human",
                    "场景：{scene}\n\nKP 叙事：\n{narrative}\n\n补充要求：{guidance}\n\n请输出 3 个行动建议 JSON 数组：",
                ),
            ]
        )

    def suggest(self, scene: str, narrative: str, turn_count: int = 0) -> list[str]:
        guidance = ""
        if turn_count <= 3:
            guidance = (
                "玩家处于开局阶段，建议应具体、易上手、动词开头，"
                "帮助玩家知道第一句话可以做什么；避免抽象或需要前置知识的选项。"
            )
        chain = self.prompt | self.llm
        response = chain.invoke(
            {"scene": scene, "narrative": narrative, "guidance": guidance or "无特殊要求。"}
        )
        text = (response.content or "").strip()
        return self._parse_suggestions(text)

    @staticmethod
    def _parse_suggestions(text: str) -> list[str]:
        try:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return [str(item).strip() for item in items[:3] if str(item).strip()]
        except json.JSONDecodeError:
            pass
        lines = [line.strip("-•* ").strip() for line in text.splitlines() if line.strip()]
        return lines[:3]
