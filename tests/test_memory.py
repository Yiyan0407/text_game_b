from chain.memory import ConversationWindowMemory
from game.models import ChatMessage, GameState, Quest


def _make_messages(count: int) -> list[ChatMessage]:
    messages = []
    for i in range(count):
        messages.append(ChatMessage(role="user", content=f"玩家消息 {i}"))
        messages.append(ChatMessage(role="assistant", content=f"KP 回复 {i}"))
    return messages


def test_window_memory_trims_old_messages():
    memory = ConversationWindowMemory(window_size=4)
    messages = _make_messages(5)
    result = memory.get_history(messages)
    assert len(result) == 4
    assert result[0].content == "玩家消息 3"


def test_window_memory_keeps_all_when_under_limit():
    memory = ConversationWindowMemory(window_size=20)
    messages = _make_messages(3)
    result = memory.get_history(messages)
    assert len(result) == 6


def test_format_for_summary():
    messages = _make_messages(2)
    text = ConversationWindowMemory.format_for_summary(messages)
    assert "【玩家】" in text
    assert "【KP】" in text


def test_game_state_format_for_prompt():
    state = GameState(
        story_summary="玩家接受了委托。",
        active_quests=[
            Quest(
                id="test",
                title="测试任务",
                status="active",
                description="进行中的任务。",
            )
        ],
    )
    text = state.format_for_prompt()
    assert "当前场景" in text
    assert "玩家接受了委托" in text
    assert "测试任务" in text


def test_game_state_upsert_npc():
    state = GameState()
    state.upsert_npc("酒馆老板", "friendly", "雇主")
    state.upsert_npc("酒馆老板", "neutral")
    assert len(state.npcs) == 1
    assert state.npcs[0].attitude == "neutral"


def test_game_state_upsert_npc_merges_fuzzy_names():
    state = GameState()
    state.upsert_npc("清洁工张某", "unknown", "火灾当晚清洁工")
    state.upsert_npc("张某", "unknown", "证词有争议")
    assert len(state.npcs) == 1
    assert state.npcs[0].name == "清洁工张某"


def test_game_state_upsert_quest():
    state = GameState()
    state.upsert_quest("new_quest", "新任务", "active", "描述")
    assert state.get_quest("new_quest") is not None
    state.upsert_quest("new_quest", "新任务", "completed")
    assert state.get_quest("new_quest").status == "completed"
