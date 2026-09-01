from game.combat_grid import (
    distance_m,
    layout_start_positions,
    migrate_positions_from_distances,
    move_toward_m,
    render_tactical_map,
    render_tactical_map_html,
    square_view_ranges,
    tactical_view_ranges,
    build_tactical_map_view,
)
from game.models import CombatAlly, CombatEnemy, CombatState


def test_distance_m_euclidean():
    assert distance_m((0, 0), (3, 4)) == 5
    assert distance_m((0, 0), (120, 0)) == 120


def test_move_toward_m_caps_at_target():
    assert move_toward_m((0, 0), (10, 0), 6) == (6, 0)
    assert move_toward_m((0, 0), (10, 0), 20) == (10, 0)


def test_layout_start_positions_spreads_enemies():
    enemies = [
        CombatEnemy(name="A", hp=10, max_hp=10, ac=10, start_distance_m=20),
        CombatEnemy(name="B", hp=10, max_hp=10, ac=10, start_distance_m=20),
    ]
    positions = layout_start_positions(enemies, [])
    assert positions["player"] == (0, 0)
    assert positions["A"][0] == 20
    assert positions["B"][0] == 20
    assert positions["A"][1] != positions["B"][1]


def test_migrate_from_enemy_distances():
    combat = CombatState(
        active=True,
        enemies=[
            CombatEnemy(name="拾荒者", hp=10, max_hp=10, ac=10, start_distance_m=25),
        ],
        enemy_distances={"拾荒者": 25},
    )
    positions = migrate_positions_from_distances(combat)
    assert positions["player"] == (0, 0)
    assert positions["拾荒者"] == (25, 0)


def test_combat_state_migrates_legacy_distances():
    combat = CombatState(
        active=True,
        enemies=[
            CombatEnemy(name="拾荒者", hp=10, max_hp=10, ac=10, start_distance_m=30),
        ],
        enemy_distances={"拾荒者": 30},
    )
    assert combat.get_position("拾荒者") == (30, 0)
    assert combat.distance_between("player", "拾荒者") == 30


def test_render_tactical_map_includes_units():
    combat = CombatState(
        active=True,
        unit_positions_m={
            "player": (0, 0),
            "狙击手": (120, 0),
        },
        enemies=[
            CombatEnemy(name="狙击手", hp=10, max_hp=10, ac=12, start_distance_m=120),
        ],
    )
    text = render_tactical_map(combat)
    assert "战术图" in text
    assert "x" in text or "@" in text


def test_render_tactical_map_html_includes_units():
    combat = CombatState(
        active=True,
        unit_positions_m={
            "player": (0, 0),
            "长矛手": (15, 0),
        },
        enemies=[
            CombatEnemy(name="长矛手", hp=10, max_hp=10, ac=11, start_distance_m=15),
        ],
        turn_order=["player"],
        turn_index=0,
    )
    html = render_tactical_map_html(combat)
    assert "长矛手" in html
    assert "svg" in html
    assert "#2563eb" in html


def test_render_tactical_map_html_shows_move_cells_when_requested():
    combat = CombatState(
        active=True,
        unit_positions_m={"player": (0, 0), "长矛手": (15, 0)},
        enemies=[
            CombatEnemy(name="长矛手", hp=10, max_hp=10, ac=11, start_distance_m=15),
        ],
        turn_order=["player"],
        turn_index=0,
        movement_remaining_m=6,
    )
    html = render_tactical_map_html(combat, show_move_targets=True)
    assert html.count('fill="rgba(148,163,184,0.25)"') > 0


def test_square_view_ranges_equalizes_narrow_layout():
    x_range, y_range = square_view_ranges([10, 10, 10], [-2, 0, 2])
    assert abs((x_range[1] - x_range[0]) - (y_range[1] - y_range[0])) < 0.01


def test_tactical_view_ranges_matches_grid_extent():
    combat = CombatState(
        active=True,
        unit_positions_m={"player": (0, 0), "长矛手": (10, 0)},
        enemies=[
            CombatEnemy(name="长矛手", hp=10, max_hp=10, ac=11, start_distance_m=10),
        ],
    )
    view = build_tactical_map_view(combat)
    x_range, y_range = tactical_view_ranges(view)
    assert abs((x_range[1] - x_range[0]) - (y_range[1] - y_range[0])) < 0.01
    assert y_range[0] > -20
    assert y_range[1] < 20


def test_build_tactical_map_figure_uses_square_viewport():
    pytest = __import__("pytest")
    pytest.importorskip("plotly")
    from game.combat_grid import build_tactical_map_figure

    combat = CombatState(
        active=True,
        unit_positions_m={
            "player": (0, 0),
            "A": (12, -2),
            "B": (12, 0),
            "C": (12, 2),
        },
        enemies=[
            CombatEnemy(name="A", hp=10, max_hp=10, ac=11, start_distance_m=12),
            CombatEnemy(name="B", hp=10, max_hp=10, ac=11, start_distance_m=12),
            CombatEnemy(name="C", hp=10, max_hp=10, ac=11, start_distance_m=12),
        ],
        turn_order=["player"],
        turn_index=0,
    )
    fig = build_tactical_map_figure(combat)
    x_span = fig.layout.xaxis.range[1] - fig.layout.xaxis.range[0]
    y_span = fig.layout.yaxis.range[1] - fig.layout.yaxis.range[0]
    assert abs(x_span - y_span) < 0.01


def test_build_tactical_map_figure_includes_traces():
    pytest = __import__("pytest")
    pytest.importorskip("plotly")
    from game.combat_grid import build_tactical_map_figure

    combat = CombatState(
        active=True,
        unit_positions_m={"player": (0, 0), "长矛手": (15, 0)},
        enemies=[
            CombatEnemy(name="长矛手", hp=10, max_hp=10, ac=11, start_distance_m=15),
        ],
        turn_order=["player"],
        turn_index=0,
    )
    fig = build_tactical_map_figure(combat, show_move_targets=True)
    names = [trace.name for trace in fig.data]
    assert "你" in names
    assert "敌人" in names
    assert "点击移动" in names
