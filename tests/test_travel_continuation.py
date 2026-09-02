from game.models import ChatMessage, GameState
from game.narrative_brief import build_narrative_brief, merge_narrative_brief_with_state
from game.results import ActionRouteResult
from game.travel_continuation import (
    is_continuation_input,
    resolve_travel_continuation,
)
from game.models import Character


def test_is_continuation_input():
    assert is_continuation_input("继续")
    assert is_continuation_input("接着走")
    assert not is_continuation_input("去修车厂")


def test_resolve_travel_continuation_from_recent_goal_and_mid_travel_kp():
    history = [
        ChatMessage(
            role="user",
            content="我需要找个修车厂，现在的车况不能保证万无一失，得准备好了再去，另外，我还需要升级一下我的武器",
        ),
        ChatMessage(
            role="assistant",
            content=(
                "老水说收费站废墟那边有个汽车旅馆，带修车棚的。"
                "矮胖男人说到了那儿可以停。"
                "你踩了脚油门，皮卡继续往西北方向颠簸。"
            ),
        ),
        ChatMessage(
            role="user",
            content="继续",
        ),
        ChatMessage(
            role="assistant",
            content=(
                "皮卡又往前颠簸了几十米，然后引擎彻底掉了下来。"
                "收费站就在前面——大概还有两三公里！"
                "你把车滑到路边残骸阴影里。"
            ),
        ),
    ]
    state = GameState(
        memory_facts=[
            "收费站废墟附近有汽车旅馆带修车棚，棚子塌了一半但举升机钢架还在，可遮风挡沙作临时维修点。"
        ]
    )
    result = resolve_travel_continuation("继续", history=history, game_state=state)
    assert result is not None
    assert result.must_arrive is True
    assert "修车棚" in result.destination or "收费站" in result.destination
    assert "抵达" in result.resolved_intent


def test_travel_time_spent_forces_arrival():
    history = [
        ChatMessage(role="user", content="开车去收费站废墟修车"),
        ChatMessage(
            role="assistant",
            content="你们沿公路残骸往西北开，热浪里能看见远处建筑的残影。",
        ),
    ]
    state = GameState(
        memory_facts=["收费站废墟附近有汽车旅馆带修车棚。"],
        current_scene="旧公路残骸",
    )
    result = resolve_travel_continuation(
        "继续",
        history=history,
        game_state=state,
        state_events=["[时间] 第1天 10:35（+40 分） — 驾驶皮卡前往骸骨走廊入口的收费站废墟"],
    )
    assert result is not None
    assert result.must_arrive is True


def test_narrative_brief_injects_travel_continuation_block():
    history = [
        ChatMessage(
            role="user",
            content="我需要找个修车厂，还得升级一下我的武器",
        ),
        ChatMessage(
            role="assistant",
            content="还有大概两三公里就到收费站废墟的汽车旅馆修车棚了。",
        ),
    ]
    text = build_narrative_brief(
        "继续",
        ActionRouteResult(approved=True),
        [],
        Character(name="测试"),
        GameState(memory_facts=["收费站废墟附近有汽车旅馆带修车棚。"]),
        history=history,
    )
    assert "【在途旅行 — 叙事硬约束】" in text
    assert "本回合须写抵达" in text
    assert "尚差数公里" in text


def test_non_travel_continue_returns_none():
    history = [
        ChatMessage(role="user", content="查看文件"),
        ChatMessage(role="assistant", content="你翻开文件，第一页写着代号。"),
    ]
    assert resolve_travel_continuation("继续", history=history) is None


def test_merge_brief_skips_travel_block_for_non_continue():
    text = merge_narrative_brief_with_state(
        "【叙事简报】\n【玩家输入】\n搜索房间",
        Character(name="测试"),
        GameState(),
    )
    assert "【在途旅行" not in text
