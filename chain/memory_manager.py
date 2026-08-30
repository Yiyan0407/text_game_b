from chain.memory import ConversationWindowMemory
from chain.summarizer import StorySummarizer
from config.settings import get_settings
from game.memory_journal import (
    journal_total_chars,
    merge_compressed_entries,
    trim_memory_journal_with_archive,
)
from game.models import ChatMessage, GameState


class LongTermMemoryManager:
    """分层长期记忆：滚动摘要 + 章节 + 事实库 + 自动压缩。"""

    def __init__(self, summarizer: StorySummarizer | None = None):
        self.summarizer = summarizer or StorySummarizer()
        settings = get_settings()
        self.summary_interval = settings.summary_interval
        self.chapter_interval = settings.chapter_interval
        self.max_story_summary_chars = settings.max_story_summary_chars
        self.max_memory_facts = settings.max_memory_facts
        self.max_chapters_kept = settings.max_chapters_kept
        self.memory_journal_compress_at = settings.memory_journal_compress_at
        self.memory_journal_max_chars = settings.memory_journal_max_chars

    def process_after_turn(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        *,
        at_turn: int | None = None,
    ) -> None:
        turn = at_turn if at_turn is not None else game_state.turn_count
        if turn <= 0:
            return

        if self._should_summarize(game_state, turn):
            self._run_periodic_summary(game_state, history, turn)

        if self._should_chapter(game_state, turn):
            self._run_chapter_summary(game_state, history, turn)

        if len(game_state.story_summary) > self.max_story_summary_chars:
            game_state.story_summary = self.summarizer.compress_summary(
                game_state.story_summary,
                self.max_story_summary_chars,
            )

        if self._should_compress_journal(game_state):
            self._compress_journal(game_state)

    async def process_after_turn_async(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        *,
        at_turn: int | None = None,
    ) -> None:
        turn = at_turn if at_turn is not None else game_state.turn_count
        if turn <= 0:
            return

        if self._should_summarize(game_state, turn):
            await self._run_periodic_summary_async(game_state, history, turn)

        if self._should_chapter(game_state, turn):
            await self._run_chapter_summary_async(game_state, history, turn)

        if len(game_state.story_summary) > self.max_story_summary_chars:
            game_state.story_summary = await self.summarizer.acompress_summary(
                game_state.story_summary,
                self.max_story_summary_chars,
            )

        if self._should_compress_journal(game_state):
            await self._compress_journal_async(game_state)

    def _should_summarize(self, game_state: GameState, turn: int) -> bool:
        return turn - game_state.last_summarized_turn >= self.summary_interval

    def _should_chapter(self, game_state: GameState, turn: int) -> bool:
        return turn - game_state.last_chapter_turn >= self.chapter_interval

    def _should_compress_journal(self, game_state: GameState) -> bool:
        unpinned = [entry for entry in game_state.memory_journal if not entry.pinned]
        if not unpinned:
            return False
        if len(game_state.memory_journal) >= self.memory_journal_compress_at:
            return True
        return journal_total_chars(unpinned) >= self.memory_journal_max_chars

    def _compress_journal(self, game_state: GameState) -> None:
        pinned = [entry for entry in game_state.memory_journal if entry.pinned]
        unpinned = [entry for entry in game_state.memory_journal if not entry.pinned]
        target_count = max(1, self.max_memory_facts - len(pinned))
        compressed = self.summarizer.compress_memory_entries(
            unpinned,
            target_count=min(target_count, max(1, len(unpinned) // 2)),
        )
        if not compressed:
            kept, dropped = trim_memory_journal_with_archive(
                game_state.memory_journal,
                self.max_memory_facts,
            )
            game_state.memory_journal_archive.extend(dropped)
            game_state.memory_journal = kept
            return
        game_state.memory_journal_archive.extend(unpinned)
        merged = merge_compressed_entries(unpinned, compressed)
        kept, dropped = trim_memory_journal_with_archive(
            pinned + merged,
            self.max_memory_facts,
        )
        game_state.memory_journal_archive.extend(dropped)
        game_state.memory_journal = kept

    async def _compress_journal_async(self, game_state: GameState) -> None:
        pinned = [entry for entry in game_state.memory_journal if entry.pinned]
        unpinned = [entry for entry in game_state.memory_journal if not entry.pinned]
        target_count = max(1, self.max_memory_facts - len(pinned))
        compressed = await self.summarizer.acompress_memory_entries(
            unpinned,
            target_count=min(target_count, max(1, len(unpinned) // 2)),
        )
        if not compressed:
            kept, dropped = trim_memory_journal_with_archive(
                game_state.memory_journal,
                self.max_memory_facts,
            )
            game_state.memory_journal_archive.extend(dropped)
            game_state.memory_journal = kept
            return
        game_state.memory_journal_archive.extend(unpinned)
        merged = merge_compressed_entries(unpinned, compressed)
        kept, dropped = trim_memory_journal_with_archive(
            pinned + merged,
            self.max_memory_facts,
        )
        game_state.memory_journal_archive.extend(dropped)
        game_state.memory_journal = kept

    def _run_periodic_summary(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        turn: int,
    ) -> None:
        recent = ConversationWindowMemory.format_for_summary(
            history,
            max_messages=self.summary_interval * 4,
        )
        game_state.story_summary = self.summarizer.merge_summary(
            game_state.story_summary,
            recent,
            self.max_story_summary_chars,
        )
        new_facts = self.summarizer.extract_facts(game_state.memory_facts, recent)
        game_state.add_memory_facts(new_facts, self.max_memory_facts)
        game_state.last_summarized_turn = turn

    async def _run_periodic_summary_async(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        turn: int,
    ) -> None:
        recent = ConversationWindowMemory.format_for_summary(
            history,
            max_messages=self.summary_interval * 4,
        )
        game_state.story_summary = await self.summarizer.amerge_summary(
            game_state.story_summary,
            recent,
            self.max_story_summary_chars,
        )
        new_facts = await self.summarizer.aextract_facts(game_state.memory_facts, recent)
        game_state.add_memory_facts(new_facts, self.max_memory_facts)
        game_state.last_summarized_turn = turn

    def _run_chapter_summary(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        turn: int,
    ) -> None:
        chapter_num = len(game_state.chapter_summaries) + 1
        recent = ConversationWindowMemory.format_for_summary(
            history,
            max_messages=self.chapter_interval * 3,
        )
        chapter_text = self.summarizer.summarize_chapter(
            chapter_num=chapter_num,
            scene=game_state.current_scene,
            summary=game_state.story_summary,
            recent_dialogue=recent,
        )
        game_state.chapter_summaries.append(chapter_text)
        if len(game_state.chapter_summaries) > self.max_chapters_kept:
            overflow = game_state.chapter_summaries[: -self.max_chapters_kept]
            game_state.chapter_summaries = game_state.chapter_summaries[
                -self.max_chapters_kept :
            ]
            merged = "\n".join(overflow)
            game_state.story_summary = self.summarizer.merge_summary(
                game_state.story_summary,
                f"【较早章节归档】\n{merged}",
                self.max_story_summary_chars,
            )
        game_state.last_chapter_turn = turn

    async def _run_chapter_summary_async(
        self,
        game_state: GameState,
        history: list[ChatMessage],
        turn: int,
    ) -> None:
        chapter_num = len(game_state.chapter_summaries) + 1
        recent = ConversationWindowMemory.format_for_summary(
            history,
            max_messages=self.chapter_interval * 3,
        )
        chapter_text = await self.summarizer.asummarize_chapter(
            chapter_num=chapter_num,
            scene=game_state.current_scene,
            summary=game_state.story_summary,
            recent_dialogue=recent,
        )
        game_state.chapter_summaries.append(chapter_text)
        if len(game_state.chapter_summaries) > self.max_chapters_kept:
            overflow = game_state.chapter_summaries[: -self.max_chapters_kept]
            game_state.chapter_summaries = game_state.chapter_summaries[
                -self.max_chapters_kept :
            ]
            merged = "\n".join(overflow)
            game_state.story_summary = await self.summarizer.amerge_summary(
                game_state.story_summary,
                f"【较早章节归档】\n{merged}",
                self.max_story_summary_chars,
            )
        game_state.last_chapter_turn = turn
