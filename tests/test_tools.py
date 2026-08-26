from game.models import Character, GameState
from chain.tools import create_kp_tools


def test_create_kp_tools():
    character = Character(name="测试", strength=14)
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    names = {tool.name for tool in tools}
    assert names == {
        "roll_dice",
        "ability_check",
        "update_scene",
        "record_npc",
        "update_quest",
        "start_combat",
        "player_attack",
        "end_combat",
        "update_inventory",
        "record_memory_fact",
    }


def test_ability_check_tool():
    character = Character(name="测试", intelligence=12)
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    check_tool = next(t for t in tools if t.name == "ability_check")
    result = check_tool.invoke({"ability": "int", "dc": 10})
    assert "智力检定" in result
    assert "DC 10" in result


def test_roll_dice_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    dice_tool = next(t for t in tools if t.name == "roll_dice")
    result = dice_tool.invoke({"notation": "d6"})
    assert "d6" in result


def test_update_scene_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    scene_tool = next(t for t in tools if t.name == "update_scene")
    result = scene_tool.invoke({"scene_id": "harbor_dock", "scene_name": "灰港码头"})
    assert "灰港码头" in result
    assert game_state.scene_id == "harbor_dock"


def test_record_npc_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    npc_tool = next(t for t in tools if t.name == "record_npc")
    npc_tool.invoke({"name": "老水手", "attitude": "neutral", "notes": "知道雾夜秘密"})
    assert len(game_state.npcs) == 1
    assert game_state.npcs[0].name == "老水手"


def test_update_inventory_tool():
    character = Character(name="测试")
    game_state = GameState()
    tools = create_kp_tools(character, game_state)
    inv_tool = next(t for t in tools if t.name == "update_inventory")
    assert character.inventory == []

    add_result = inv_tool.invoke({"action": "add", "item": "手机"})
    assert "手机" in add_result
    assert character.inventory == ["手机"]

    remove_result = inv_tool.invoke({"action": "remove", "item": "手机"})
    assert "移除" in remove_result
    assert character.inventory == []


def test_character_starts_with_empty_inventory():
    character = Character(name="测试")
    assert character.inventory == []
    assert "空" in character.format_inventory()
