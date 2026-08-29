from game.models import GameState
from game.scene_map import (
    MapEdge,
    MapNode,
    SceneRecord,
    WorldMapGraph,
    apply_map_update,
    apply_scene_change,
    bootstrap_scene_map,
    build_skeleton_graph,
    ensure_travel_edge,
    format_map_context,
    group_visited_by_scope,
    record_scene_visit,
    scene_scope,
    scope_display_label,
    sync_graph_statuses,
    sync_map_to_current_scene,
)
from game.scenario import Scenario, ScenarioNode


def _sample_scenario() -> Scenario:
    return Scenario(
        id="test",
        title="测试模组",
        opening_scene_id="tavern",
        opening_scene_name="海鸥尾酒馆",
        key_nodes=[
            ScenarioNode(id="tavern", title="海鸥尾酒馆", description="起点"),
            ScenarioNode(id="dock", title="灰港码头", description="码头"),
            ScenarioNode(id="lighthouse", title="废弃灯塔", description="线索"),
        ],
    )


def test_record_scene_visit_dedupes():
    state = GameState.model_construct(visited_scenes=[])
    assert record_scene_visit(state, "dock", "码头", turn_count=1)
    assert not record_scene_visit(state, "dock", "码头", turn_count=2)
    assert len(state.visited_scenes) == 1


def test_apply_scene_change_updates_current():
    state = GameState(scene_id="tavern", current_scene="酒馆")
    record_scene_visit(state, "tavern", "酒馆", turn_count=1)
    apply_scene_change(state, "dock", "码头", turn_count=3)
    assert state.scene_id == "dock"
    assert state.current_scene == "码头"
    assert len(state.visited_scenes) == 2


def test_bootstrap_builds_single_start_node():
    scenario = _sample_scenario()
    state = GameState(scene_id="tavern", current_scene="海鸥尾酒馆")
    bootstrap_scene_map(state, scenario)
    assert len(state.visited_scenes) == 1
    assert state.world_map_graph is not None
    assert len(state.world_map_graph.nodes) == 1
    assert state.world_map_graph.nodes[0].id == "tavern"
    assert state.world_map_graph.nodes[0].status == "current"
    assert not state.world_map_graph.edges


def test_build_skeleton_only_includes_visited_places():
    scenario = _sample_scenario()
    state = GameState(
        scene_id="dock",
        current_scene="灰港码头",
        visited_scenes=[
            SceneRecord(scene_id="tavern", scene_name="海鸥尾酒馆", first_seen_turn=1),
            SceneRecord(scene_id="dock", scene_name="灰港码头", first_seen_turn=2),
        ],
    )
    graph = build_skeleton_graph(scenario, state)
    node_ids = {node.id for node in graph.nodes}
    assert node_ids == {"tavern", "dock"}
    assert "lighthouse" not in node_ids


def test_apply_map_update_accepts_json_graph():
    state = GameState(
        scene_id="dock",
        current_scene="灰港码头",
        world_map_graph=WorldMapGraph(
            nodes=[MapNode(id="tavern", label="旧酒馆", status="visited")]
        ),
    )
    assert apply_map_update(
        state,
        {
            "nodes": [
                {"id": "tavern", "label": "海鸥尾酒馆", "status": "visited"},
                {"id": "dock", "label": "灰港码头", "status": "current"},
            ],
            "edges": [{"source": "tavern", "target": "dock", "kind": "known"}],
        },
        _sample_scenario(),
    )
    assert state.world_map_graph is not None
    assert len(state.world_map_graph.nodes) == 2
    current = next(n for n in state.world_map_graph.nodes if n.status == "current")
    assert current.id == "dock"


def test_apply_map_update_rejects_invalid():
    state = GameState(
        world_map_graph=WorldMapGraph(
            nodes=[MapNode(id="old", label="旧", status="visited")]
        )
    )
    assert not apply_map_update(state, {"edges": []}, _sample_scenario())
    assert state.world_map_graph.nodes[0].id == "old"


def test_sync_graph_statuses_from_game_state():
    state = GameState(
        scene_id="b",
        current_scene="B区",
        visited_scenes=[],
    )
    state.visited_scenes.append(SceneRecord(scene_id="a", scene_name="A区", first_seen_turn=1))
    graph = WorldMapGraph(
        nodes=[
            MapNode(id="a", label="A", status="unknown"),
            MapNode(id="b", label="B", status="unknown"),
        ]
    )
    synced = sync_graph_statuses(graph, state, None)
    statuses = {n.id: n.status for n in synced.nodes}
    assert statuses["a"] == "visited"
    assert statuses["b"] == "current"


def test_prune_foreign_visited_scenes():
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="正门",
        key_nodes=[ScenarioNode(id="entrance-gate", title="正门")],
    )
    state = GameState(
        scene_id="entrance-gate",
        current_scene="正门",
        visited_scenes=[
            SceneRecord(scene_id="tavern_seagull", scene_name="灰港·海鸥尾酒馆", first_seen_turn=0),
            SceneRecord(scene_id="entrance-gate", scene_name="正门", first_seen_turn=1),
        ],
    )
    graph = build_skeleton_graph(scenario, state)
    node_ids = {node.id for node in graph.nodes}
    assert "tavern_seagull" not in node_ids
    assert node_ids == {"entrance-gate"}


def test_prune_keeps_dynamic_scenes_on_map():
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="正门",
        key_nodes=[ScenarioNode(id="entrance-gate", title="正门")],
    )
    state = GameState(
        scene_id="floor-1-storage",
        current_scene="杂物间",
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="正门", first_seen_turn=0),
            SceneRecord(scene_id="floor-1-storage", scene_name="杂物间", first_seen_turn=4),
        ],
        world_map_graph=WorldMapGraph(
            nodes=[
                MapNode(id="entrance-gate", label="门口", status="visited"),
                MapNode(id="floor-1-hall", label="一楼楼道", status="visited"),
                MapNode(id="floor-1-storage", label="杂物间", status="current"),
            ],
        ),
    )
    from game.scene_map import prune_foreign_visited_scenes

    prune_foreign_visited_scenes(state, scenario)
    ids = {record.scene_id for record in state.visited_scenes}
    assert ids == {"entrance-gate", "floor-1-hall", "floor-1-storage"}


def test_reconcile_visited_scenes_from_graph():
    state = GameState(
        scene_id="floor-1-storage",
        current_scene="杂物间",
        turn_count=4,
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="门口", first_seen_turn=0),
        ],
        world_map_graph=WorldMapGraph(
            nodes=[
                MapNode(id="entrance-gate", label="门口", status="visited"),
                MapNode(id="floor-1-hall", label="一楼楼道", status="visited"),
                MapNode(id="floor-1-storage", label="杂物间", status="current"),
            ],
        ),
        memory_journal=[],
    )
    from game.scene_map import reconcile_visited_scenes

    reconcile_visited_scenes(state)
    ids = {record.scene_id for record in state.visited_scenes}
    assert "floor-1-hall" in ids
    assert "floor-1-storage" in ids


def test_prune_keeps_memory_visited_without_graph():
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="正门",
        key_nodes=[ScenarioNode(id="entrance-gate", title="正门")],
    )
    from game.memory_journal import entry_from_text
    from game.scene_map import prune_foreign_visited_scenes

    state = GameState(
        scene_id="floor-2-hall",
        current_scene="二楼楼道",
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="正门", first_seen_turn=0),
            SceneRecord(scene_id="floor-1-hall", scene_name="一楼楼道", first_seen_turn=1),
            SceneRecord(scene_id="floor-1-storage", scene_name="杂物间", first_seen_turn=4),
            SceneRecord(scene_id="floor-2-hall", scene_name="二楼楼道", first_seen_turn=7),
        ],
        memory_journal=[
            entry_from_text(
                "一楼楼道左侧有杂物间",
                topic="1号空置楼",
                turn_count=1,
                scene_id="floor-1-hall",
                scene_name="一楼楼道",
            ),
            entry_from_text(
                "杂物间内有红绳",
                topic="1号空置楼",
                turn_count=4,
                scene_id="floor-1-storage",
                scene_name="杂物间",
            ),
        ],
    )
    prune_foreign_visited_scenes(state, scenario)
    ids = {record.scene_id for record in state.visited_scenes}
    assert ids == {"entrance-gate", "floor-1-hall", "floor-1-storage", "floor-2-hall"}


def test_prepare_map_display_uses_stored_graph():
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="正门",
        key_nodes=[ScenarioNode(id="entrance-gate", title="正门")],
    )
    state = GameState(
        scene_id="floor-2-hall",
        current_scene="二楼楼道",
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="正门", first_seen_turn=0),
            SceneRecord(scene_id="floor-2-hall", scene_name="二楼楼道", first_seen_turn=7),
        ],
        world_map_graph=WorldMapGraph(
            nodes=[
                MapNode(id="entrance-gate", label="门口", status="visited"),
                MapNode(id="floor-1-hall", label="一楼楼道", status="visited"),
                MapNode(id="floor-1-storage", label="杂物间", status="visited"),
                MapNode(id="floor-2-hall", label="二楼楼道", status="current"),
            ],
            edges=[
                MapEdge(source="entrance-gate", target="floor-1-hall", kind="known"),
                MapEdge(source="floor-1-hall", target="floor-1-storage", kind="known"),
                MapEdge(source="floor-1-hall", target="floor-2-hall", kind="known"),
            ],
        ),
    )
    from game.scene_map import prepare_map_display

    graph, visited = prepare_map_display(state, scenario)
    assert len(graph.nodes) == 4
    assert len(graph.edges) == 3
    assert len(visited) >= 2


def test_effective_map_graph_does_not_prune_visited():
    scenario = _sample_scenario()
    state = GameState(
        scene_id="dock",
        current_scene="码头",
        visited_scenes=[
            SceneRecord(scene_id="tavern", scene_name="酒馆", first_seen_turn=1),
            SceneRecord(scene_id="dock", scene_name="码头", first_seen_turn=2),
        ],
    )
    from game.scene_map import effective_map_graph

    effective_map_graph(state, scenario)
    assert len(state.visited_scenes) == 2


def test_scene_scope_and_group_visited():
    assert scene_scope("2270/portal-lab") == "2270"
    assert scene_scope("2020/senkawa/basement") == "2020"
    assert scene_scope("floor-1-hall") == ""

    records = [
        SceneRecord(scene_id="2270/portal-lab", scene_name="实验室", first_seen_turn=1),
        SceneRecord(scene_id="2020/senkawa/basement", scene_name="地下室", first_seen_turn=5),
        SceneRecord(scene_id="entrance-gate", scene_name="门口", first_seen_turn=0),
    ]
    grouped = {scope: items for scope, items in group_visited_by_scope(records)}
    assert "2270" in grouped
    assert "2020" in grouped
    assert "" in grouped


def test_scope_display_label_from_key_nodes():
    scenario = Scenario(
        id="test",
        title="穿越",
        key_nodes=[ScenarioNode(id="2270", title="2270时间线")],
    )
    assert scope_display_label("2270", scenario) == "2270时间线"


def test_legacy_save_drops_mermaid_field():
    state = GameState.model_validate(
        {
            "scene_id": "gate",
            "current_scene": "正门",
            "world_map_mermaid": "flowchart TD\n  gate",
        }
    )
    assert state.world_map_graph is None
    assert "world_map_mermaid" not in state.model_dump()


def test_legacy_save_migrates_visited_scenes():
    state = GameState.model_validate(
        {
            "scene_id": "gate",
            "current_scene": "正门",
            "turn_count": 5,
        }
    )
    assert len(state.visited_scenes) == 1
    assert state.visited_scenes[0].scene_id == "gate"


def test_sync_map_to_current_scene_reuses_existing_node():
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="单元门口",
        key_nodes=[
            ScenarioNode(id="entrance-gate", title="单元门口"),
            ScenarioNode(id="floor-1-hall", title="一楼楼道"),
        ],
    )
    state = GameState(
        scene_id="floor-1-hall",
        current_scene="1号空置楼·一楼楼道",
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="单元门口", first_seen_turn=1),
            SceneRecord(scene_id="floor-1-hall", scene_name="一楼楼道", first_seen_turn=2),
        ],
        world_map_graph=WorldMapGraph(
            nodes=[
                MapNode(id="entrance-gate", label="单元门口", status="current"),
                MapNode(id="floor-1-hall", label="一楼楼道", status="unknown"),
            ],
            edges=[
                MapEdge(source="entrance-gate", target="floor-1-hall", kind="known"),
            ],
        ),
    )
    sync_map_to_current_scene(state, scenario)
    assert state.world_map_graph is not None
    statuses = {node.id: node.status for node in state.world_map_graph.nodes}
    assert statuses["floor-1-hall"] == "current"
    assert statuses["entrance-gate"] == "visited"
    assert len(state.world_map_graph.nodes) == 2


def test_sync_map_adds_current_node_without_edges():
    """机械层只校正 status；连边留给 Map Agent。"""
    scenario = Scenario(
        id="vacant",
        title="1号空置楼",
        opening_scene_id="entrance-gate",
        opening_scene_name="单元门口",
        key_nodes=[
            ScenarioNode(id="entrance-gate", title="单元门口"),
            ScenarioNode(id="floor-1-hall", title="一楼楼道"),
        ],
    )
    state = GameState(
        scene_id="floor-1-hall",
        current_scene="1号空置楼·一楼楼道",
        map_travel_from="entrance-gate",
        visited_scenes=[
            SceneRecord(scene_id="entrance-gate", scene_name="单元门口", first_seen_turn=1),
            SceneRecord(scene_id="floor-1-hall", scene_name="一楼楼道", first_seen_turn=2),
        ],
        world_map_graph=WorldMapGraph(
            nodes=[MapNode(id="entrance-gate", label="单元门口", status="visited")],
        ),
    )
    sync_map_to_current_scene(state, scenario)
    assert len(state.world_map_graph.nodes) == 2
    assert any(node.id == "floor-1-hall" for node in state.world_map_graph.nodes)
    assert not state.world_map_graph.edges
    assert state.map_travel_from == "entrance-gate"


def test_format_map_context_includes_travel_from():
    scenario = _sample_scenario()
    state = GameState(scene_id="dock", current_scene="灰港码头")
    text = format_map_context(state, scenario, travel_from="tavern")
    assert "本轮移动：自 tavern 到达当前位置" in text


def test_apply_scene_change_sets_map_travel_from():
    state = GameState(scene_id="entrance-gate", current_scene="单元门口")
    record_scene_visit(state, "entrance-gate", "单元门口", turn_count=1)
    apply_scene_change(state, "floor-1-hall", "一楼楼道", turn_count=2)
    assert state.map_travel_from == "entrance-gate"
    assert state.scene_id == "floor-1-hall"


def test_ensure_travel_edge_upgrades_suspected_to_known():
    graph = WorldMapGraph(
        nodes=[
            MapNode(id="a", label="A", status="visited"),
            MapNode(id="b", label="B", status="current"),
        ],
        edges=[MapEdge(source="a", target="b", kind="suspected")],
    )
    ensure_travel_edge(graph, "a", "b", kind="known")
    assert graph.edges[0].kind == "known"


def test_apply_map_update_replaces_graph():
    state = GameState(
        scene_id="dock",
        current_scene="灰港码头",
        world_map_graph=WorldMapGraph(
            nodes=[
                MapNode(id="tavern", label="海鸥尾酒馆", status="visited"),
                MapNode(id="dock", label="灰港码头", status="current"),
                MapNode(id="obsolete", label="应删除", status="visited"),
            ],
            edges=[MapEdge(source="tavern", target="obsolete", kind="known")],
        ),
    )
    assert apply_map_update(
        state,
        {
            "nodes": [
                {"id": "tavern", "label": "海鸥尾酒馆", "status": "visited"},
                {"id": "dock", "label": "灰港码头", "status": "current"},
                {"id": "lighthouse", "label": "废弃灯塔", "status": "unknown"},
            ],
            "edges": [
                {"source": "tavern", "target": "dock", "kind": "known"},
                {"source": "dock", "target": "lighthouse", "kind": "suspected"},
            ],
        },
        _sample_scenario(),
    )
    node_ids = {node.id for node in state.world_map_graph.nodes}
    assert node_ids == {"tavern", "dock", "lighthouse"}
    assert "obsolete" not in node_ids
    assert not any(edge.target == "obsolete" for edge in state.world_map_graph.edges)
