from game.models import GameState, NPCRelation
from game.npc_merge import (
    dedupe_npc_list,
    find_npc_by_name,
    merge_npc_notes,
    npc_names_same_person,
    preferred_npc_name,
)


def test_upsert_npc_merges_role_and_full_name():
    state = GameState()
    state.upsert_npc("出租车司机", "neutral", "对大火知情但刻意压制。")
    state.upsert_npc(
        "出租车司机周师傅",
        "neutral",
        "对仁和医院大火知情但刻意压制，已驾车离开。",
    )
    assert len(state.npcs) == 1
    assert state.npcs[0].name == "出租车司机周师傅"
    assert "大火" in state.npcs[0].notes


def test_different_taxi_drivers_stay_separate():
    state = GameState()
    state.upsert_npc("出租车司机张师傅", "neutral", "张师傅，调度台名片。")
    state.upsert_npc("出租车司机王师傅", "neutral", "另一位司机。")
    state.upsert_npc("出租车司机刘师傅", "neutral", "第三位司机。")
    assert len(state.npcs) == 3
    names = {npc.name for npc in state.npcs}
    assert names == {"出租车司机张师傅", "出租车司机王师傅", "出租车司机刘师傅"}


def test_generic_taxi_not_merged_when_multiple_drivers_exist():
    state = GameState()
    state.upsert_npc("出租车司机张师傅", "neutral", "第一位。")
    state.upsert_npc("出租车司机王师傅", "neutral", "第二位。")
    state.upsert_npc("出租车司机", "neutral", "不应误合并到某一位。")
    assert len(state.npcs) == 3


def test_dedupe_npc_list_merges_existing_duplicates():
    npcs = [
        NPCRelation(
            name="出租车司机",
            attitude="neutral",
            notes="表现出愧疚。",
        ),
        NPCRelation(
            name="出租车司机周师傅",
            attitude="neutral",
            notes="已驾车离开。",
        ),
    ]
    merged = dedupe_npc_list(npcs)
    assert len(merged) == 1
    assert merged[0].name == "出租车司机周师傅"


def test_npc_names_same_person_rejects_conflicting_surnames():
    assert not npc_names_same_person("出租车司机张师傅", "出租车司机王师傅")
    assert npc_names_same_person("出租车司机", "出租车司机周师傅")
    assert npc_names_same_person("周师傅", "出租车司机周师傅")


def test_find_npc_by_name_uses_surname():
    npcs = [
        NPCRelation(name="出租车司机张师傅", attitude="neutral"),
        NPCRelation(name="出租车司机王师傅", attitude="neutral"),
    ]
    assert find_npc_by_name(npcs, "王师傅").name == "出租车司机王师傅"


def test_preferred_npc_name_keeps_longer_specific_name():
    assert preferred_npc_name("出租车司机", "出租车司机周师傅") == "出租车司机周师傅"


def test_merge_npc_notes_avoids_duplication():
    old = "对大火知情但刻意压制。"
    new = "对仁和医院大火知情但刻意压制，已驾车离开。"
    assert merge_npc_notes(old, new) == new
