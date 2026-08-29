"""场景地图：已访问地点记录与 JSON 拓扑图（Cytoscape 渲染）。"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from game.models import GameState
    from game.scenario import Scenario

MapNodeStatus = Literal["current", "visited", "unknown"]
MapEdgeKind = Literal["known", "suspected"]


class SceneRecord(BaseModel):
    scene_id: str
    scene_name: str
    first_seen_turn: int = 0
    notes: str = ""

    @field_validator("scene_id", "scene_name", "notes", mode="before")
    @classmethod
    def _coerce_str(cls, value):
        if value is None:
            return ""
        return str(value).strip()


class MapNode(BaseModel):
    id: str
    label: str
    status: MapNodeStatus = "unknown"

    @field_validator("id", "label", mode="before")
    @classmethod
    def _coerce_required(cls, value):
        return str(value or "").strip()

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value):
        cleaned = str(value or "unknown").strip().lower()
        if cleaned in ("current", "visited", "unknown"):
            return cleaned
        return "unknown"


class MapEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    kind: MapEdgeKind = "known"

    @field_validator("source", "target", mode="before")
    @classmethod
    def _coerce_endpoint(cls, value):
        return str(value or "").strip()

    @field_validator("label", mode="before")
    @classmethod
    def _coerce_label(cls, value):
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, value):
        cleaned = str(value or "known").strip().lower()
        if cleaned in ("known", "suspected"):
            return cleaned
        return "known"


class WorldMapGraph(BaseModel):
    nodes: list[MapNode] = Field(default_factory=list)
    edges: list[MapEdge] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.nodes


def graph_node_id(scene_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", scene_id.strip())
    if not cleaned:
        return "scene_unknown"
    if cleaned[0].isdigit():
        return f"s_{cleaned}"
    return cleaned


def graph_node_id(scene_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", scene_id.strip())
    if not cleaned:
        return "scene_unknown"
    if cleaned[0].isdigit():
        return f"s_{cleaned}"
    return cleaned


def scene_scope(scene_id: str) -> str:
    """`scope/local/...` 的第一段；无 `/` 的旧 id 视为单区模组（空 scope）。"""
    sid = scene_id.strip()
    if "/" in sid:
        return sid.split("/", 1)[0].strip()
    return ""


def scope_display_label(scope: str, scenario: Scenario | None = None) -> str:
    if not scope:
        return "本区"
    if scenario is not None:
        for node in scenario.key_nodes:
            nid = node.id.strip()
            if nid == scope or nid.startswith(f"{scope}/"):
                title = node.title.strip()
                if title:
                    return title
    return scope


def group_visited_by_scope(
    records: list[SceneRecord],
) -> list[tuple[str, list[SceneRecord]]]:
    """按 scope 分组，保持首次出现的 scope 顺序。"""
    buckets: dict[str, list[SceneRecord]] = {}
    order: list[str] = []
    for record in records:
        key = scene_scope(record.scene_id) or "\0local"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(record)
    grouped: list[tuple[str, list[SceneRecord]]] = []
    for key in order:
        grouped.append(("" if key == "\0local" else key, buckets[key]))
    return grouped


def find_scene_record(game_state: GameState, scene_id: str) -> SceneRecord | None:
    target = scene_id.strip()
    if not target:
        return None
    for record in game_state.visited_scenes:
        if record.scene_id == target:
            return record
    return None


def record_scene_visit(
    game_state: GameState,
    scene_id: str,
    scene_name: str,
    *,
    turn_count: int,
) -> bool:
    sid = scene_id.strip()
    name = scene_name.strip()
    if not sid or not name:
        return False
    existing = find_scene_record(game_state, sid)
    if existing:
        if name and existing.scene_name != name:
            existing.scene_name = name
        return False
    game_state.visited_scenes.append(
        SceneRecord(scene_id=sid, scene_name=name, first_seen_turn=turn_count)
    )
    return True


def apply_scene_change(
    game_state: GameState,
    scene_id: str,
    scene_name: str,
    *,
    turn_count: int,
) -> bool:
    sid = scene_id.strip()
    name = scene_name.strip()
    if not sid or not name:
        return False
    previous_id = game_state.scene_id.strip()
    changed = game_state.scene_id != sid or game_state.current_scene != name
    record_turn = max(0, int(turn_count))
    is_new = record_scene_visit(game_state, sid, name, turn_count=record_turn)
    if changed and previous_id and previous_id != sid:
        game_state.map_travel_from = previous_id
    game_state.scene_id = sid
    game_state.current_scene = name
    game_state.scene_image_url = ""
    return changed or is_new


def normalize_world_map_graph(value) -> WorldMapGraph | None:
    if value is None:
        return None
    if isinstance(value, WorldMapGraph):
        return value
    if isinstance(value, dict):
        try:
            return WorldMapGraph.model_validate(value)
        except Exception:
            return None
    return None


def _scenario_scene_ids(scenario: Scenario) -> set[str]:
    ids = {scenario.opening_scene_id.strip()}
    ids.update(node.id.strip() for node in scenario.key_nodes if node.id.strip())
    return {item for item in ids if item}


def _graph_scene_ids(game_state: GameState) -> set[str]:
    graph = normalize_world_map_graph(game_state.world_map_graph)
    if graph is None or graph.is_empty():
        return set()
    return {node.id.strip() for node in graph.nodes if node.id.strip()}


def _first_seen_turn_for_scene(game_state: GameState, scene_id: str) -> int:
    sid = scene_id.strip()
    turns = [
        entry.turn_count
        for entry in game_state.memory_journal
        if str(getattr(entry, "scene_id", "") or "").strip() == sid
    ]
    if turns:
        return min(turns)
    return max(0, int(game_state.turn_count))


def reconcile_visited_scenes(game_state: GameState) -> None:
    """从地图节点与记忆日志补全缺失的 visited_scenes（修复被误删的动态场景）。"""
    graph = normalize_world_map_graph(game_state.world_map_graph)
    if graph and not graph.is_empty():
        for node in graph.nodes:
            sid = node.id.strip()
            if not sid or node.status not in ("visited", "current"):
                continue
            if find_scene_record(game_state, sid):
                continue
            record_scene_visit(
                game_state,
                sid,
                node.label.strip() or sid,
                turn_count=_first_seen_turn_for_scene(game_state, sid),
            )

    for entry in game_state.memory_journal:
        sid = str(getattr(entry, "scene_id", "") or "").strip()
        name = str(getattr(entry, "scene_name", "") or "").strip()
        if not sid or not name or find_scene_record(game_state, sid):
            continue
        record_scene_visit(
            game_state,
            sid,
            name,
            turn_count=_first_seen_turn_for_scene(game_state, sid),
        )

    sid = game_state.scene_id.strip()
    name = game_state.current_scene.strip()
    if sid and name:
        record_scene_visit(
            game_state,
            sid,
            name,
            turn_count=_first_seen_turn_for_scene(game_state, sid),
        )


def _memory_scene_ids(game_state: GameState) -> set[str]:
    ids: set[str] = set()
    for entry in game_state.memory_journal:
        sid = str(getattr(entry, "scene_id", "") or "").strip()
        if sid:
            ids.add(sid)
    return ids


def _relevant_visited_records(
    game_state: GameState,
    scenario: Scenario,
) -> list[SceneRecord]:
    """过滤掉其他模组/默认值污染的旧访问记录；保留探索中动态发现的场景。"""
    allowed = _scenario_scene_ids(scenario)
    current_id = game_state.scene_id.strip()
    travel_from = game_state.map_travel_from.strip()
    on_map = _graph_scene_ids(game_state)
    from_memory = _memory_scene_ids(game_state)
    relevant: list[SceneRecord] = []
    for record in game_state.visited_scenes:
        sid = record.scene_id.strip()
        if not sid:
            continue
        if (
            sid in allowed
            or sid == current_id
            or sid == travel_from
            or sid in on_map
            or sid in from_memory
        ):
            relevant.append(record)
    return relevant


def _visited_ids(game_state: GameState, scenario: Scenario | None = None) -> set[str]:
    if scenario is None:
        return {record.scene_id for record in game_state.visited_scenes if record.scene_id}
    return {record.scene_id for record in _relevant_visited_records(game_state, scenario)}


def reset_scene_map_for_scenario(game_state: GameState) -> None:
    """新开局：清空地图，避免上一局或默认值残留。"""
    game_state.visited_scenes = []
    game_state.world_map_graph = None


def prune_foreign_visited_scenes(game_state: GameState, scenario: Scenario) -> None:
    """补全访问记录，并剔除不属于当前模组的污染数据。"""
    reconcile_visited_scenes(game_state)
    game_state.visited_scenes = _relevant_visited_records(game_state, scenario)


def sync_graph_statuses(
    graph: WorldMapGraph,
    game_state: GameState,
    scenario: Scenario | None = None,
) -> WorldMapGraph:
    """根据 game_state 校正节点 current / visited 状态。"""
    current_id = game_state.scene_id.strip()
    visited = _visited_ids(game_state, scenario)
    nodes: list[MapNode] = []
    seen: set[str] = set()
    for node in graph.nodes:
        nid = node.id.strip()
        if not nid or nid in seen:
            continue
        seen.add(nid)
        if nid == current_id:
            status: MapNodeStatus = "current"
        elif nid in visited:
            status = "visited"
        else:
            status = node.status if node.status != "current" else "unknown"
        nodes.append(MapNode(id=nid, label=node.label or nid, status=status))

    if current_id and current_id not in seen:
        nodes.append(
            MapNode(id=current_id, label=game_state.current_scene or current_id, status="current")
        )

    node_ids = {node.id for node in nodes}
    edges: list[MapEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        source = edge.source.strip()
        target = edge.target.strip()
        if not source or not target or source not in node_ids or target not in node_ids:
            continue
        key = (source, target, edge.kind)
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append(
            MapEdge(source=source, target=target, label=edge.label, kind=edge.kind)
        )

    return WorldMapGraph(nodes=nodes[:15], edges=edges[:30])


def build_skeleton_graph(scenario: Scenario | None, game_state: GameState) -> WorldMapGraph:
    """探索式地图：仅包含已访问地点与当前位置，不预置未到达节点。"""
    current_id = game_state.scene_id.strip()
    visited = _visited_ids(game_state, scenario)
    records = (
        _relevant_visited_records(game_state, scenario)
        if scenario is not None
        else game_state.visited_scenes
    )

    labels: dict[str, str] = {}
    for record in records:
        sid = record.scene_id.strip()
        if sid:
            labels[sid] = record.scene_name.strip() or sid
    if current_id:
        labels[current_id] = game_state.current_scene.strip() or labels.get(current_id, current_id)

    nodes = [
        MapNode(
            id=sid,
            label=labels[sid],
            status=(
                "current"
                if sid == current_id
                else "visited" if sid in visited else "unknown"
            ),
        )
        for sid in labels
    ]
    return WorldMapGraph(nodes=nodes, edges=[])


def bootstrap_scene_map(game_state: GameState, scenario: Scenario, *, reset: bool = False) -> None:
    if reset:
        reset_scene_map_for_scenario(game_state)
    prune_foreign_visited_scenes(game_state, scenario)
    record_scene_visit(
        game_state,
        game_state.scene_id,
        game_state.current_scene,
        turn_count=game_state.turn_count,
    )
    if game_state.world_map_graph is None or game_state.world_map_graph.is_empty():
        game_state.world_map_graph = build_skeleton_graph(scenario, game_state)


def _graph_node_ids(graph: WorldMapGraph) -> set[str]:
    return {node.id.strip() for node in graph.nodes if node.id.strip()}


def _resolve_node_label(scene_id: str, game_state: GameState, scenario: Scenario) -> str:
    sid = scene_id.strip()
    for kn in scenario.key_nodes:
        if kn.id.strip() == sid and kn.title.strip():
            return kn.title.strip()
    for record in game_state.visited_scenes:
        if record.scene_id.strip() == sid and record.scene_name.strip():
            return record.scene_name.strip()
    if sid == game_state.scene_id.strip() and game_state.current_scene.strip():
        return game_state.current_scene.strip()
    return sid


def ensure_travel_edge(
    graph: WorldMapGraph,
    source_id: str,
    target_id: str,
    *,
    kind: MapEdgeKind = "known",
    label: str = "",
) -> None:
    """玩家从 source 移动到 target 时，确保两节点之间有连通边。"""
    source = source_id.strip()
    target = target_id.strip()
    if not source or not target or source == target:
        return
    node_ids = _graph_node_ids(graph)
    if source not in node_ids or target not in node_ids:
        return
    for edge in graph.edges:
        if edge.source.strip() == source and edge.target.strip() == target:
            if kind == "known" and edge.kind == "suspected":
                edge.kind = "known"
            return
    graph.edges.append(
        MapEdge(source=source, target=target, label=label, kind=kind)
    )


def sync_map_to_current_scene(game_state: GameState, scenario: Scenario | None = None) -> None:
    """校正节点 current/visited；新节点与连边由 Map Agent 维护。"""
    if scenario is None:
        return
    prune_foreign_visited_scenes(game_state, scenario)
    if game_state.world_map_graph is None or game_state.world_map_graph.is_empty():
        bootstrap_scene_map(game_state, scenario)
        return

    graph = game_state.world_map_graph
    if graph is None or graph.is_empty():
        return

    game_state.world_map_graph = sync_graph_statuses(graph, game_state, scenario)


def _map_connected_components(graph: WorldMapGraph) -> list[set[str]]:
    node_ids = {node.id.strip() for node in graph.nodes if node.id.strip()}
    adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for edge in graph.edges:
        source = edge.source.strip()
        target = edge.target.strip()
        if source in node_ids and target in node_ids:
            adjacency[source].add(target)
            adjacency[target].add(source)

    visited: set[str] = set()
    components: list[set[str]] = []
    for nid in node_ids:
        if nid in visited:
            continue
        stack = [nid]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(adjacency[current] - visited)
        components.append(component)
    return components


def _node_label(graph: WorldMapGraph, node_id: str) -> str:
    for node in graph.nodes:
        if node.id.strip() == node_id:
            return node.label.strip() or node_id
    return node_id


def format_topology_correction_hints(
    graph: WorldMapGraph,
    current_id: str,
) -> list[str]:
    """列出孤立节点与断裂簇，供手动刷新时 Map Agent 整改。"""
    if graph.is_empty():
        return []

    node_ids = {node.id.strip() for node in graph.nodes if node.id.strip()}
    if len(node_ids) <= 1:
        return []

    hints: list[str] = []
    isolated = [
        node.id.strip()
        for node in graph.nodes
        if node.id.strip()
        and not any(
            edge.source.strip() == node.id.strip() or edge.target.strip() == node.id.strip()
            for edge in graph.edges
        )
    ]
    if isolated:
        labels = "；".join(f"{_node_label(graph, nid)}（{nid}）" for nid in isolated)
        hints.append(f"- 无任何连边的孤立节点：{labels}")

    components = _map_connected_components(graph)
    if len(components) > 1:
        current = current_id.strip()
        main = next((comp for comp in components if current in comp), None)
        if main is None:
            main = max(components, key=len)
        hints.append(
            f"- 全图共 {len(components)} 个互不连通的节点簇；"
            f"当前位置所在簇含 {len(main)} 个节点"
        )
        for comp in components:
            if comp == main:
                continue
            labels = "；".join(f"{_node_label(graph, nid)}（{nid}）" for nid in sorted(comp))
            hints.append(f"- 与当前位置不连通的节点簇：{labels}")

    if hints:
        hints.append(
            "- 请结合到达顺序与对话中的交通/穿越方式尽量补连边；"
            "同 scope 内补 hub 邻接，跨 scope 经 macro；无法推断的可保留孤立"
        )
    return hints


def format_visit_order_hints(game_state: GameState) -> list[str]:
    """按首次到达顺序列出相邻访问，供整改时推断连边。"""
    ordered = sorted(game_state.visited_scenes, key=lambda record: record.first_seen_turn)
    if len(ordered) < 2:
        return []
    lines: list[str] = []
    for index in range(1, len(ordered)):
        previous = ordered[index - 1]
        current = ordered[index]
        turn = (
            f"第{current.first_seen_turn}回合"
            if current.first_seen_turn
            else "未知回合"
        )
        lines.append(
            f"- {previous.scene_name}（{previous.scene_id}）"
            f" → {current.scene_name}（{current.scene_id}）· {turn}"
        )
    return lines


def format_map_context(
    game_state: GameState,
    scenario: Scenario,
    *,
    travel_from: str = "",
    reconcile: bool = False,
) -> str:
    lines = [
        f"当前位置：{game_state.current_scene}（{game_state.scene_id}）",
        f"回合：{game_state.turn_count}",
    ]
    current_scope = scene_scope(game_state.scene_id)
    if current_scope:
        lines.append(f"当前区域 scope：{current_scope}")
    lines.append(
        "scene_id 约定：`scope/局部/id`（scope=时代/城市/大楼等）；"
        "单区模组可无 scope 前缀；跨区只经 macro 通道边连接。"
    )
    origin = (travel_from or game_state.map_travel_from).strip()
    if origin and origin != game_state.scene_id.strip():
        lines.append(f"本轮移动：自 {origin} 到达当前位置")
    prune_foreign_visited_scenes(game_state, scenario)
    if game_state.visited_scenes:
        lines.append("已访问地点：")
        for record in game_state.visited_scenes:
            turn = f"第{record.first_seen_turn}回合" if record.first_seen_turn else "未知回合"
            lines.append(f"- {record.scene_name}（{record.scene_id}）· {turn}")
    if scenario.key_nodes:
        lines.append("模组关键地点（名称参考，id 由 Agent 生成）：")
        for node in scenario.key_nodes:
            visited = "已到达" if find_scene_record(game_state, node.id) else "未探索"
            desc = node.description.strip()
            extra = f" — {desc}" if desc else ""
            lines.append(f"- {node.title}（{visited}）{extra}")
    graph = effective_map_graph(game_state, scenario)
    if reconcile:
        if visit_order := format_visit_order_hints(game_state):
            lines.append("到达顺序参考（推断连边，非强制链式连接）：")
            lines.extend(visit_order)
        if graph and not graph.is_empty():
            if hints := format_topology_correction_hints(graph, game_state.scene_id):
                lines.append("【拓扑待整改】（玩家手动刷新，请尽量修正）")
                lines.extend(hints)
    if graph and not graph.is_empty():
        lines.append("当前 JSON 地图（可在其上增量修订）：")
        lines.append(json.dumps(graph.model_dump(), ensure_ascii=False, indent=2))
    return "\n".join(lines)


def apply_map_update(game_state: GameState, data: dict, scenario: Scenario | None = None) -> bool:
    """写入 AI 生成的 JSON 地图；incoming 为完整修订结果（非增量合并）。"""
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return False
    try:
        incoming = WorldMapGraph.model_validate(
            {
                "nodes": raw_nodes,
                "edges": data.get("edges") if isinstance(data.get("edges"), list) else [],
            }
        )
    except Exception:
        return False
    synced = sync_graph_statuses(incoming, game_state, scenario)
    if synced.is_empty():
        return False
    game_state.world_map_graph = synced
    if scenario is not None:
        sync_map_to_current_scene(game_state, scenario)
    return True


def prepare_map_display(
    game_state: GameState,
    scenario: Scenario,
) -> tuple[WorldMapGraph | None, list[SceneRecord]]:
    """UI 展示：补全访问记录，返回拓扑图与已访问列表（不破坏性 prune）。"""
    reconcile_visited_scenes(game_state)
    visited_records = _relevant_visited_records(game_state, scenario)
    stored = normalize_world_map_graph(game_state.world_map_graph)
    if stored and not stored.is_empty():
        graph = sync_graph_statuses(stored, game_state, scenario)
    else:
        graph = build_skeleton_graph(scenario, game_state)
    return graph, visited_records


def effective_map_graph(
    game_state: GameState,
    scenario: Scenario | None = None,
) -> WorldMapGraph | None:
    stored = normalize_world_map_graph(game_state.world_map_graph)
    if stored and not stored.is_empty():
        return sync_graph_statuses(stored, game_state, scenario)
    if scenario is not None:
        return build_skeleton_graph(scenario, game_state)
    return None


def render_cytoscape_html(graph: WorldMapGraph, *, height: int = 420) -> str:
    """嵌入 Cytoscape.js 的 HTML 片段。"""
    payload = {
        "nodes": [
            {
                "id": node.id,
                "label": node.label or node.id,
                "status": node.status,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "label": edge.label,
                "kind": edge.kind,
            }
            for edge in graph.edges
        ],
    }
    graph_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{ margin: 0; padding: 0; background: transparent; }}
  #cy {{ width: 100%; height: {height}px; background: #0f172a; border-radius: 8px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
</head>
<body>
<div id="cy"></div>
<script>
  const graph = {graph_json};
  const elements = [];
  for (const n of graph.nodes) {{
    elements.push({{ data: {{ id: n.id, label: n.label, status: n.status }} }});
  }}
  for (const e of graph.edges) {{
    elements.push({{
      data: {{
        id: e.source + "__" + e.target + "__" + (e.label || e.kind),
        source: e.source,
        target: e.target,
        label: e.label || "",
        kind: e.kind || "known"
      }}
    }});
  }}
  cytoscape({{
    container: document.getElementById("cy"),
    elements,
    wheelSensitivity: 0.25,
    minZoom: 0.35,
    maxZoom: 2.5,
    style: [
      {{
        selector: "node",
        style: {{
          "label": "data(label)",
          "text-wrap": "wrap",
          "text-max-width": 96,
          "font-size": 11,
          "color": "#e2e8f0",
          "text-valign": "center",
          "text-halign": "center",
          "width": 72,
          "height": 44,
          "shape": "round-rectangle",
          "background-color": "#475569",
          "border-width": 2,
          "border-color": "#64748b"
        }}
      }},
      {{
        selector: 'node[status = "current"]',
        style: {{
          "background-color": "#2563eb",
          "border-color": "#93c5fd",
          "color": "#ffffff",
          "width": 84,
          "height": 48,
          "font-weight": "bold"
        }}
      }},
      {{
        selector: 'node[status = "visited"]',
        style: {{
          "background-color": "#334155",
          "border-color": "#94a3b8"
        }}
      }},
      {{
        selector: 'node[status = "unknown"]',
        style: {{
          "background-color": "#1e293b",
          "border-color": "#475569",
          "border-style": "dashed",
          "color": "#94a3b8"
        }}
      }},
      {{
        selector: "edge",
        style: {{
          "width": 2,
          "line-color": "#64748b",
          "target-arrow-color": "#64748b",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "label": "data(label)",
          "font-size": 9,
          "color": "#cbd5e1",
          "text-background-opacity": 1,
          "text-background-color": "#0f172a",
          "text-background-padding": 2
        }}
      }},
      {{
        selector: 'edge[kind = "suspected"]',
        style: {{
          "line-style": "dashed",
          "line-color": "#475569",
          "target-arrow-color": "#475569"
        }}
      }}
    ],
    layout: {{
      name: "cose",
      animate: false,
      padding: 24,
      nodeRepulsion: 8000,
      idealEdgeLength: 90
    }}
  }});
</script>
</body>
</html>"""
