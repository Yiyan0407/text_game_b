import pytest

from game.background_validator import validate_background_quick


@pytest.mark.parametrize(
    "background",
    [
        "前海军斥候，为还债来到灰港做佣兵。",
        "炼气三层散修，资质平平，只为寻失踪师兄。",
        "梦想有朝一日成为剑仙的普通外门弟子。",
        "听闻仙帝传说，立志修行的炼气弟子。",
        "地下小有名气的黑客，接私活维生。",
        "某科技公司 CEO，业余研究网络安全。",
        "曾是金丹修士，遭伏击后修为尽失，如今从头修炼。",
    ],
)
def test_quick_validate_allows_reasonable_backgrounds(background):
    result = validate_background_quick(background, world_id="xianxia")
    assert result.approved is True


@pytest.mark.parametrize(
    "background",
    [
        "我是化神期大能，弹指可灭国。",
        "自带混沌至宝与万亿灵石，开局无敌。",
        "全属性99，HP无限，系统满级全开。",
        "我是仙帝转世，拥有仙尊传承。",
        "齐天大圣附身于我，一念灭世。",
    ],
)
def test_quick_validate_rejects_overpowered(background):
    result = validate_background_quick(background, world_id="xianxia")
    assert result.approved is False
    assert result.rejection_reason


def test_quick_validate_rejects_too_long_background():
    result = validate_background_quick("a" * 501)
    assert result.approved is False
    assert "500" in result.rejection_reason


def test_quick_validate_allows_hacker_background():
    result = validate_background_quick(
        "地下有名的黑客，擅长渗透与数据恢复。",
        world_id="modern",
    )
    assert result.approved is True


def test_background_validator_parse():
    from chain.background_validator import BackgroundValidator

    ok = BackgroundValidator._parse_response('{"approved": true, "rejection_reason": ""}')
    assert ok.approved is True

    bad = BackgroundValidator._parse_response(
        '{"approved": false, "rejection_reason": "请从凡人写起。"}'
    )
    assert bad.approved is False
    assert "凡人" in bad.rejection_reason
