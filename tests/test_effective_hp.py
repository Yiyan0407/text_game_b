from unittest.mock import MagicMock

from chain.kp_meta_agent import KpMetaResult
from game.check_reroll import apply_reroll_patch
from game.effects import EntityEffects
from game.models import Character, GameState, LastAbilityCheckRecord
from game.orchestrator import GameOrchestrator
from game.results import RerollPatch


def _character_with_hp_armor(*, hp: int = 10, max_hp: int = 10, bonus: int = 10) -> Character:
    character = Character(name="测试", hp=hp, max_hp=max_hp)
    character.add_inventory_item("皮下装甲", quantity=1, unit="套", description="测试护甲。")
    armor = character.find_inventory_item("皮下装甲")
    assert armor is not None
    armor.effects = EntityEffects(max_hp_bonus=bonus, forged=True)
    character.equip_item("皮下装甲", slot="body")
    assert character.effective_max_hp() == max_hp + bonus
    return character


def test_unequip_clamps_hp_to_effective_max():
    character = _character_with_hp_armor(hp=20, max_hp=10, bonus=10)
    ok, _ = character.unequip_item("皮下装甲")
    assert ok
    assert character.hp == 10
    assert character.effective_max_hp() == 10


def test_reroll_overturn_respects_equipment_hp_cap():
    character = _character_with_hp_armor(hp=12, max_hp=10, bonus=10)
    game_state = GameState(
        last_ability_check=LastAbilityCheckRecord(
            ability="dex",
            dc=18,
            check_total=12,
            roll_total=10,
            success=False,
            action_intent="潜入",
            hp_before=20,
            hp_after=12,
        )
    )
    apply_reroll_patch(
        RerollPatch(overturn_failure=True),
        character,
        game_state,
    )
    assert character.hp == 20


def test_kp_meta_hp_correction_respects_equipment_cap():
    character = _character_with_hp_armor(hp=10, max_hp=10, bonus=10)
    orchestrator = GameOrchestrator(kp_meta_agent=MagicMock())
    result = KpMetaResult(response="补满。", character_hp=20)
    events, _ = orchestrator._apply_kp_meta_result(result, character, GameState())
    assert character.hp == 20
    assert any("20/20" in event for event in events)
