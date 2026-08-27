import re

from langchain_core.prompts import ChatPromptTemplate
from chain.llm import create_chat_llm


class StorySummarizer:
    def __init__(self):
        self.llm = create_chat_llm(temperature=0.3)

        self.merge_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是跑团记录员，负责**长期记忆**维护。将近期对话合并进已有摘要。"
                    "必须保留：人名、地名、物品、数字、承诺、未解悬念、玩家重大决策。"
                    "用中文，控制在指定字数内；不得添加对话中不存在的内容；不得丢关键事实。",
                ),
                (
                    "human",
                    "已有摘要：\n{existing}\n\n近期对话：\n{recent}\n\n"
                    "请输出合并后的完整摘要（不超过 {max_chars} 字）：",
                ),
            ]
        )

        self.chapter_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是跑团章节记录员。为本阶段剧情写一段章节摘要（标题+正文）。"
                    "保留关键 NPC、线索、转折；150-250 字。",
                ),
                (
                    "human",
                    "当前章节号：{chapter_num}\n当前场景：{scene}\n\n"
                    "本阶段摘要：\n{summary}\n\n近期对话：\n{recent}\n\n"
                    "格式：\n标题：...\n正文：...",
                ),
            ]
        )

        self.compress_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "压缩跑团总摘要，**保留全部关键事实**（人名/地点/物品/悬念/关系），删除重复修辞。"
                    "用中文条目化或短段落，不超过指定字数。",
                ),
                (
                    "human",
                    "待压缩摘要：\n{text}\n\n请输出压缩版（不超过 {max_chars} 字）：",
                ),
            ]
        )

        self.facts_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "从对话中提取 3-6 条「必须记住的事实」，每条一行，格式：- 事实内容。"
                    "优先：NPC 姓名与关系、获得/失去的物品、重要承诺、未解线索、玩家声明的长期目标。"
                    "不要重复已有事实列表中的内容。",
                ),
                (
                    "human",
                    "已有事实：\n{existing_facts}\n\n近期对话：\n{recent}\n\n新事实：",
                ),
            ]
        )

    def merge_summary(self, existing_summary: str, recent_dialogue: str, max_chars: int) -> str:
        chain = self.merge_prompt | self.llm
        response = chain.invoke(
            {
                "existing": existing_summary or "（尚无摘要）",
                "recent": recent_dialogue,
                "max_chars": max_chars,
            }
        )
        return response.content.strip()

    def summarize_chapter(
        self,
        chapter_num: int,
        scene: str,
        summary: str,
        recent_dialogue: str,
    ) -> str:
        chain = self.chapter_prompt | self.llm
        response = chain.invoke(
            {
                "chapter_num": chapter_num,
                "scene": scene,
                "summary": summary or "（尚无）",
                "recent": recent_dialogue,
            }
        )
        return response.content.strip()

    def compress_summary(self, text: str, max_chars: int) -> str:
        chain = self.compress_prompt | self.llm
        response = chain.invoke({"text": text, "max_chars": max_chars})
        return response.content.strip()

    def extract_facts(self, existing_facts: list[str], recent_dialogue: str) -> list[str]:
        if not recent_dialogue.strip():
            return []
        chain = self.facts_prompt | self.llm
        response = chain.invoke(
            {
                "existing_facts": "\n".join(f"- {f}" for f in existing_facts) or "（无）",
                "recent": recent_dialogue,
            }
        )
        return _parse_fact_lines(response.content or "")

    async def amerge_summary(self, existing_summary: str, recent_dialogue: str, max_chars: int) -> str:
        chain = self.merge_prompt | self.llm
        response = await chain.ainvoke(
            {
                "existing": existing_summary or "（尚无摘要）",
                "recent": recent_dialogue,
                "max_chars": max_chars,
            }
        )
        return response.content.strip()

    async def asummarize_chapter(
        self,
        chapter_num: int,
        scene: str,
        summary: str,
        recent_dialogue: str,
    ) -> str:
        chain = self.chapter_prompt | self.llm
        response = await chain.ainvoke(
            {
                "chapter_num": chapter_num,
                "scene": scene,
                "summary": summary or "（尚无）",
                "recent": recent_dialogue,
            }
        )
        return response.content.strip()

    async def acompress_summary(self, text: str, max_chars: int) -> str:
        chain = self.compress_prompt | self.llm
        response = await chain.ainvoke({"text": text, "max_chars": max_chars})
        return response.content.strip()

    async def aextract_facts(self, existing_facts: list[str], recent_dialogue: str) -> list[str]:
        if not recent_dialogue.strip():
            return []
        chain = self.facts_prompt | self.llm
        response = await chain.ainvoke(
            {
                "existing_facts": "\n".join(f"- {f}" for f in existing_facts) or "（无）",
                "recent": recent_dialogue,
            }
        )
        return _parse_fact_lines(response.content or "")


def _parse_fact_lines(text: str) -> list[str]:
    facts: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^[-*•\d.)\s]+", "", line.strip())
        if cleaned and len(cleaned) >= 4:
            facts.append(cleaned)
    return facts
