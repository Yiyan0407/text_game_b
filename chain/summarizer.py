import re

from langchain_core.prompts import ChatPromptTemplate

from chain.json_utils import extract_json_dict
from chain.llm import create_chat_llm
from game.memory_journal import MemoryEntry, entry_from_text, format_entries_for_compress


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
                    "从对话中提取 0-2 条「必须长期记住的关键事实」，每条一行，格式：- 事实内容。"
                    "仅写：重大真相、关键承诺、NPC 核心秘密、未解悬念、区域/安保规则。"
                    "不要写：日常观察、检定成败、临时状态、已在 NPC/任务/背包中登记的信息。"
                    "若近期对话无新的关键情报，输出「（无）」；不要重复已有事实列表中的内容。",
                ),
                (
                    "human",
                    "已有事实：\n{existing_facts}\n\n近期对话：\n{recent}\n\n新事实：",
                ),
            ]
        )

        self.journal_compress_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是跑团「关键记忆」整理员。将多条按主题分组的事实**合并压缩**为更少条目。"
                    "规则："
                    "1. 同一主题内语义重复或可合并的条目须合成一条；"
                    "2. 不同主题、不同 NPC、不同线索须分开保留，不可丢关键人名/数字/承诺；"
                    "3. 输出 JSON：`{{\"entries\": [{{\"topic\": \"主题\", \"text\": \"合并后事实\"}}]}}`；"
                    "4. 总条数不超过 target_count；text 每条 15-80 字；topic 复用输入中的主题名。",
                ),
                (
                    "human",
                    "目标条数上限：{target_count}\n\n待整理记忆：\n{blob}\n\n请输出 JSON：",
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
        from game.memory_journal import is_trivial_memory

        facts = _parse_fact_lines(response.content or "")
        return [fact for fact in facts if fact != "（无）" and not is_trivial_memory(f)][:2]

    def compress_memory_entries(
        self,
        entries: list[MemoryEntry],
        *,
        target_count: int,
    ) -> list[MemoryEntry]:
        if not entries or len(entries) <= target_count:
            return list(entries)
        chain = self.journal_compress_prompt | self.llm
        response = chain.invoke(
            {
                "target_count": max(1, target_count),
                "blob": format_entries_for_compress(entries),
            }
        )
        return _parse_compressed_entries(response.content or "")

    async def acompress_memory_entries(
        self,
        entries: list[MemoryEntry],
        *,
        target_count: int,
    ) -> list[MemoryEntry]:
        if not entries or len(entries) <= target_count:
            return list(entries)
        chain = self.journal_compress_prompt | self.llm
        response = await chain.ainvoke(
            {
                "target_count": max(1, target_count),
                "blob": format_entries_for_compress(entries),
            }
        )
        return _parse_compressed_entries(response.content or "")

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
        from game.memory_journal import is_trivial_memory

        facts = _parse_fact_lines(response.content or "")
        return [fact for fact in facts if fact != "（无）" and not is_trivial_memory(fact)][:2]


def _parse_fact_lines(text: str) -> list[str]:
    facts: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^[-*•\d.)\s]+", "", line.strip())
        if cleaned and len(cleaned) >= 4:
            facts.append(cleaned)
    return facts


def _parse_compressed_entries(text: str) -> list[MemoryEntry]:
    data = extract_json_dict(text)
    if data is None:
        return []
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        return []
    parsed: list[MemoryEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        fact_text = str(item.get("text") or item.get("fact") or "").strip()
        if not fact_text:
            continue
        topic = str(item.get("topic") or item.get("category") or "").strip() or None
        parsed.append(entry_from_text(fact_text, topic=topic))
    return parsed
