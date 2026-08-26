from chain.memory import ConversationWindowMemory
from chain.summarizer import StorySummarizer
from config.settings import get_settings
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

    def process_after_turn(self, game_state: GameState, history: list[ChatMessage]) -> None:
        if game_state.turn_count <= 0:
            return

        if self._should_summarize(game_state):
            self._run_periodic_summary(game_state, history)

        if self._should_chapter(game_state):
            self._run_chapter_summary(game_state, history)

        if len(game_state.story_summary) > self.max_story_summary_chars:
            game_state.story_summary = self.summarizer.compress_summary(
                game_state.story_summary,
                self.max_story_summary_chars,
            )

    def _should_summarize(self, game_state: GameState) -> bool:
        return (
            game_state.turn_count - game_state.last_summarized_turn
            >= self.summary_interval
        )

    def _should_chapter(self, game_state: GameState) -> bool:
        return (
            game_state.turn_count - game_state.last_chapter_turn
            >= self.chapter_interval
        )

    def _run_periodic_summary(
        self,
        game_state: GameState,
        history: list[ChatMessage],
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
        game_state.last_summarized_turn = game_state.turn_count

    def _run_chapter_summary(
        self,
        game_state: GameState,
        history: list[ChatMessage],
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
        game_state.last_chapter_turn = game_state.turn_count
