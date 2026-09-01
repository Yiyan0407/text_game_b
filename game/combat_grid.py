"""战斗 2D 平面坐标（米）与战术地图渲染。"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.models import CombatAlly, CombatEnemy, CombatState

PLAYER_UNIT_ID = "player"
PosM = tuple[int, int]


def distance_m(pos_a: PosM, pos_b: PosM) -> int:
    ax, ay = pos_a
    bx, by = pos_b
    return int(round(math.hypot(ax - bx, ay - by)))


def move_toward_m(from_pos: PosM, to_pos: PosM, meters: int) -> PosM:
    """沿直线靠近 to_pos，最多移动 meters 米（不超过目标点）。"""
    meters = max(0, int(meters))
    if meters <= 0:
        return from_pos
    total = distance_m(from_pos, to_pos)
    if total <= 0:
        return from_pos
    step = min(meters, total)
    fx, fy = from_pos
    tx, ty = to_pos
    nx = fx + int(round((tx - fx) * step / total))
    ny = fy + int(round((ty - fy) * step / total))
    return nx, ny


def move_away_m(from_pos: PosM, anchor_pos: PosM, meters: int) -> PosM:
    """沿远离 anchor 方向移动 meters 米。"""
    meters = max(0, int(meters))
    if meters <= 0:
        return from_pos
    total = distance_m(from_pos, anchor_pos)
    if total <= 0:
        return from_pos[0] + meters, from_pos[1]
    fx, fy = from_pos
    ax, ay = anchor_pos
    nx = fx + int(round((fx - ax) * meters / total))
    ny = fy + int(round((fy - ay) * meters / total))
    return nx, ny


def _has_explicit_coords(start_x_m: int, start_y_m: int) -> bool:
    return start_x_m != 0 or start_y_m != 0


def layout_start_positions(
    enemies: list[CombatEnemy],
    allies: list[CombatAlly],
    *,
    enemy_defs: list | None = None,
    ally_defs: list | None = None,
) -> dict[str, PosM]:
    """生成开战初始坐标。玩家位于原点 (0, 0)。"""
    from game.results import AllyDefPatch, EnemyDefPatch

    positions: dict[str, PosM] = {PLAYER_UNIT_ID: (0, 0)}
    enemy_def_map: dict[str, EnemyDefPatch] = {}
    ally_def_map: dict[str, AllyDefPatch] = {}

    for item in enemy_defs or []:
        if isinstance(item, EnemyDefPatch):
            patch = item
        elif isinstance(item, dict):
            patch = EnemyDefPatch.model_validate(item)
        else:
            continue
        if patch.name.strip():
            enemy_def_map[patch.name.strip()] = patch

    for item in ally_defs or []:
        if isinstance(item, AllyDefPatch):
            patch = item
        elif isinstance(item, dict):
            patch = AllyDefPatch.model_validate(item)
        else:
            continue
        if patch.name.strip():
            ally_def_map[patch.name.strip()] = patch

    for index, enemy in enumerate(enemies):
        patch = enemy_def_map.get(enemy.name)
        if patch and _has_explicit_coords(patch.start_x_m, patch.start_y_m):
            positions[enemy.name] = (patch.start_x_m, patch.start_y_m)
        else:
            y_offset = (index - (len(enemies) - 1) / 2) * 2
            y_offset = int(round(y_offset))
            positions[enemy.name] = (enemy.start_distance_m, y_offset)

    for index, ally in enumerate(allies):
        patch = ally_def_map.get(ally.name)
        if patch and _has_explicit_coords(patch.start_x_m, patch.start_y_m):
            positions[ally.name] = (patch.start_x_m, patch.start_y_m)
        else:
            y_slot = -2 if index % 2 == 0 else 2
            if index > 1:
                y_slot = y_slot * (index // 2 + 1)
            positions[ally.name] = (-2, y_slot)

    return positions


def migrate_positions_from_distances(combat: CombatState) -> dict[str, PosM]:
    """从旧版 enemy_distances 生成 2D 坐标。"""
    positions: dict[str, PosM] = {PLAYER_UNIT_ID: (0, 0)}
    for index, enemy in enumerate(combat.enemies):
        dist = combat.enemy_distances.get(enemy.name, enemy.start_distance_m)
        y_offset = (index - (len(combat.enemies) - 1) / 2) * 2
        y_offset = int(round(y_offset))
        positions[enemy.name] = (dist, y_offset)
    for index, ally in enumerate(combat.allies):
        y_slot = -2 if index % 2 == 0 else 2
        positions[ally.name] = (-2, y_slot)
    return positions


def sync_legacy_distances(combat: CombatState) -> None:
    """将 2D 坐标同步回 enemy_distances（兼容旧读法）。"""
    player_pos = combat.get_position(PLAYER_UNIT_ID)
    for enemy in combat.enemies:
        enemy_pos = combat.get_position(enemy.name)
        if enemy_pos is not None and player_pos is not None:
            combat.enemy_distances[enemy.name] = distance_m(player_pos, enemy_pos)


@dataclass(frozen=True)
class TacticalUnitMarker:
    unit_id: str
    label: str
    x_m: int
    y_m: int
    kind: str
    is_current: bool
    dead: bool = False


@dataclass(frozen=True)
class MapCell:
    symbol: str
    label: str = ""
    unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TacticalMapView:
    cells: list[list[MapCell]]
    meters_per_cell: float
    origin_x_m: float
    origin_y_m: float
    viewport_cells: int


def _collect_unit_entries(combat: CombatState) -> list[tuple[str, PosM, str]]:
    entries: list[tuple[str, PosM, str]] = []
    player_pos = combat.get_position(PLAYER_UNIT_ID)
    if player_pos is not None:
        entries.append((PLAYER_UNIT_ID, player_pos, "player"))
    for ally in combat.allies:
        if ally.hp <= 0:
            continue
        pos = combat.get_position(ally.name)
        if pos is not None:
            entries.append((ally.name, pos, "ally"))
    for enemy in combat.enemies:
        if enemy.hp <= 0:
            continue
        pos = combat.get_position(enemy.name)
        if pos is not None:
            entries.append((enemy.name, pos, "enemy"))
    return entries


def display_scale(entries: list[tuple[str, PosM, str]], *, viewport_cells: int = 9) -> float:
    if not entries:
        return 2.0
    xs = [pos[0] for _, pos, _ in entries]
    ys = [pos[1] for _, pos, _ in entries]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 2)
    return max(2.0, span / max(1, viewport_cells - 1))


def build_tactical_unit_markers(combat: CombatState) -> list[TacticalUnitMarker]:
    current = combat.current_actor()
    markers: list[TacticalUnitMarker] = []
    player_pos = combat.get_position(PLAYER_UNIT_ID)
    if player_pos is not None:
        markers.append(
            TacticalUnitMarker(
                unit_id=PLAYER_UNIT_ID,
                label="你",
                x_m=player_pos[0],
                y_m=player_pos[1],
                kind="player",
                is_current=current == "player",
            )
        )
    for ally in combat.allies:
        pos = combat.get_position(ally.name)
        if pos is None:
            continue
        markers.append(
            TacticalUnitMarker(
                unit_id=ally.name,
                label=ally.name,
                x_m=pos[0],
                y_m=pos[1],
                kind="ally",
                is_current=current == ally.name,
                dead=ally.hp <= 0,
            )
        )
    for enemy in combat.enemies:
        pos = combat.get_position(enemy.name)
        if pos is None:
            continue
        markers.append(
            TacticalUnitMarker(
                unit_id=enemy.name,
                label=enemy.name,
                x_m=pos[0],
                y_m=pos[1],
                kind="enemy",
                is_current=current == enemy.name,
                dead=enemy.hp <= 0 or enemy.surrendered,
            )
        )
    return markers


def _grid_step_m(span_m: float) -> int:
    if span_m <= 20:
        return 2
    if span_m <= 60:
        return 5
    if span_m <= 150:
        return 10
    return 20


def square_view_ranges(
    xs: list[int],
    ys: list[int],
    *,
    min_span: int = 20,
    pad_ratio: float = 0.18,
) -> tuple[list[float], list[float]]:
    """等边视窗：保证 X/Y 数据跨度一致，避免 1:1 比例下战术图过窄。"""
    if not xs or not ys:
        half = max(min_span / 2, 10)
        return [-half, half], [-half, half]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    span = max(max_x - min_x, max_y - min_y, min_span)
    pad = max(4, span * pad_ratio)
    half = span / 2 + pad
    return [cx - half, cx + half], [cy - half, cy + half]


def tactical_view_ranges(
    view: TacticalMapView,
    *,
    pad_cells: float = 0.75,
) -> tuple[list[float], list[float]]:
    """按战术格视窗给出正方形坐标范围（与移动格一致，避免 Y 被拉太长）。"""
    span = view.meters_per_cell * (view.viewport_cells - 1)
    pad = view.meters_per_cell * pad_cells
    cx = view.origin_x_m + span / 2
    cy = view.origin_y_m + span / 2
    half = span / 2 + pad
    return [cx - half, cx + half], [cy - half, cy + half]


def render_tactical_map_html(
    combat: CombatState,
    *,
    width: int = 640,
    height: int = 480,
    show_move_targets: bool = False,
    viewport_cells: int = 9,
) -> str:
    """生成战术平面 SVG（供 Streamlit st.html / iframe 嵌入，风格对齐场景地图）。"""
    markers = [m for m in build_tactical_unit_markers(combat) if not m.dead]
    padding = 36
    inner_w = max(120, width - padding * 2)
    inner_h = max(120, height - padding * 2)

    view = build_tactical_map_view(combat, viewport_cells=viewport_cells) if markers else None
    if view is not None:
        x_range, y_range = tactical_view_ranges(view)
        min_x, max_x = x_range[0], x_range[1]
        min_y, max_y = y_range[0], y_range[1]
    else:
        min_x = min_y = -5
        max_x = max_y = 5

    span_x = max(max_x - min_x, 4)
    span_y = max(max_y - min_y, 4)
    pad_m = max(2, int(math.ceil(max(span_x, span_y) * 0.15)))
    min_x -= pad_m
    max_x += pad_m
    min_y -= pad_m
    max_y += pad_m
    span_x = max(max_x - min_x, 4)
    span_y = max(max_y - min_y, 4)

    def to_sx(x_m: float) -> float:
        return padding + (x_m - min_x) / span_x * inner_w

    def to_sy(y_m: float) -> float:
        return padding + (max_y - y_m) / span_y * inner_h

    grid_step = _grid_step_m(max(span_x, span_y))
    grid_lines: list[str] = []
    start_x = int(math.floor(min_x / grid_step) * grid_step)
    start_y = int(math.floor(min_y / grid_step) * grid_step)
    x = start_x
    while x <= max_x:
        sx = to_sx(x)
        grid_lines.append(
            f'<line x1="{sx:.1f}" y1="{padding}" x2="{sx:.1f}" y2="{padding + inner_h}" '
            f'stroke="#334155" stroke-width="1"/>'
        )
        if min_x <= x <= max_x:
            grid_lines.append(
                f'<text x="{sx:.1f}" y="{height - 8}" fill="#64748b" font-size="9" '
                f'text-anchor="middle">{x}m</text>'
            )
        x += grid_step
    y = start_y
    while y <= max_y:
        sy = to_sy(y)
        grid_lines.append(
            f'<line x1="{padding}" y1="{sy:.1f}" x2="{padding + inner_w}" y2="{sy:.1f}" '
            f'stroke="#334155" stroke-width="1"/>'
        )
        y += grid_step

    if min_x <= 0 <= max_x and min_y <= 0 <= max_y:
        ox, oy = to_sx(0), to_sy(0)
        grid_lines.append(
            f'<line x1="{ox:.1f}" y1="{padding}" x2="{ox:.1f}" y2="{padding + inner_h}" '
            f'stroke="#475569" stroke-width="1.5" stroke-dasharray="4 3"/>'
        )
        grid_lines.append(
            f'<line x1="{padding}" y1="{oy:.1f}" x2="{padding + inner_w}" y2="{oy:.1f}" '
            f'stroke="#475569" stroke-width="1.5" stroke-dasharray="4 3"/>'
        )

    cell_shapes: list[str] = []
    if show_move_targets and view is not None:
        unit_positions = {(m.x_m, m.y_m) for m in markers}
        half_w_px = (view.meters_per_cell / span_x) * inner_w / 2
        half_h_px = (view.meters_per_cell / span_y) * inner_h / 2
        for row in range(view.viewport_cells):
            for col in range(view.viewport_cells):
                x_m, y_m = cell_center_m(view, row, col)
                if (x_m, y_m) in unit_positions:
                    continue
                cx, cy = to_sx(x_m), to_sy(y_m)
                cell_shapes.append(
                    f'<rect x="{cx - half_w_px:.1f}" y="{cy - half_h_px:.1f}" '
                    f'width="{half_w_px * 2:.1f}" height="{half_h_px * 2:.1f}" '
                    f'fill="rgba(148,163,184,0.25)" stroke="rgba(148,163,184,0.55)" '
                    f'stroke-width="1"/>'
                )

    kind_colors = {
        "player": ("#2563eb", "#93c5fd"),
        "ally": ("#15803d", "#86efac"),
        "enemy": ("#b91c1c", "#fca5a5"),
    }
    unit_shapes: list[str] = []
    for marker in markers:
        cx, cy = to_sx(marker.x_m), to_sy(marker.y_m)
        fill, stroke = kind_colors.get(marker.kind, ("#475569", "#94a3b8"))
        radius = 11 if marker.kind == "player" else 9
        if marker.is_current:
            unit_shapes.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius + 5:.1f}" '
                f'fill="none" stroke="#fbbf24" stroke-width="2.5"/>'
            )
        title = html.escape(f"{marker.label} ({marker.x_m},{marker.y_m})m")
        unit_shapes.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2">'
            f"<title>{title}</title></circle>"
        )
        label = html.escape(marker.label[:6])
        unit_shapes.append(
            f'<text x="{cx:.1f}" y="{cy - radius - 4:.1f}" fill="#e2e8f0" font-size="10" '
            f'text-anchor="middle">{label}</text>'
        )

    legend = """
    <g font-size="10" fill="#94a3b8">
      <circle cx="18" cy="16" r="5" fill="#2563eb" stroke="#93c5fd"/>
      <text x="28" y="20">你</text>
      <circle cx="58" cy="16" r="5" fill="#15803d" stroke="#86efac"/>
      <text x="68" y="20">友方</text>
      <circle cx="108" cy="16" r="5" fill="#b91c1c" stroke="#fca5a5"/>
      <text x="118" y="20">敌人</text>
      <text x="168" y="20">黄圈=当前行动者 · 虚线=原点</text>
    </g>
    """
    svg_body = "\n".join(grid_lines + cell_shapes + unit_shapes)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{ margin: 0; padding: 0; background: #0f172a; width: 100%; height: {height}px; }}
  svg {{ display: block; width: 100%; height: {height}px; }}
</style>
</head>
<body>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img"
     aria-label="战斗战术图">
  <rect x="0" y="0" width="{width}" height="{height}" rx="8" fill="#0f172a"/>
  {legend}
  {svg_body}
</svg>
</body>
</html>"""


def build_tactical_map_figure(
    combat: CombatState,
    *,
    show_move_targets: bool = False,
    viewport_cells: int = 9,
    chart_height: int = 420,
):
    """Plotly 战术图：单位散点 + 可选可点击移动格。"""
    import plotly.graph_objects as go

    markers = [m for m in build_tactical_unit_markers(combat) if not m.dead]
    view = build_tactical_map_view(combat, viewport_cells=viewport_cells)
    fig = go.Figure()

    if show_move_targets:
        mx: list[int] = []
        my: list[int] = []
        hover: list[str] = []
        custom: list[list] = []
        unit_positions = {(m.x_m, m.y_m) for m in markers}
        for row in range(view.viewport_cells):
            for col in range(view.viewport_cells):
                x_m, y_m = cell_center_m(view, row, col)
                if (x_m, y_m) in unit_positions:
                    continue
                mx.append(x_m)
                my.append(y_m)
                hover.append(f"移动到 ({x_m}, {y_m}) m")
                custom.append(["move", x_m, y_m])
        if mx:
            fig.add_trace(
                go.Scatter(
                    x=mx,
                    y=my,
                    mode="markers",
                    name="点击移动",
                    marker=dict(
                        size=14,
                        color="rgba(148, 163, 184, 0.25)",
                        line=dict(color="rgba(148, 163, 184, 0.55)", width=1),
                        symbol="square",
                    ),
                    hovertext=hover,
                    hoverinfo="text",
                    customdata=custom,
                )
            )

    kind_style = {
        "player": ("你", "#2563eb", "#93c5fd", 16),
        "ally": ("友方", "#15803d", "#86efac", 13),
        "enemy": ("敌人", "#b91c1c", "#fca5a5", 13),
    }
    for kind, (legend, fill, stroke, size) in kind_style.items():
        group = [m for m in markers if m.kind == kind]
        if not group:
            continue
        fig.add_trace(
            go.Scatter(
                x=[m.x_m for m in group],
                y=[m.y_m for m in group],
                mode="markers+text",
                name=legend,
                text=[m.label[:6] for m in group],
                textposition="top center",
                textfont=dict(size=10, color="#e2e8f0"),
                marker=dict(
                    size=[size + (4 if m.is_current else 0) for m in group],
                    color=fill,
                    line=dict(
                        color="#fbbf24" if any(m.is_current for m in group) else stroke,
                        width=2.5 if any(m.is_current for m in group) else 2,
                    ),
                ),
                hovertext=[
                    f"{m.label} ({m.x_m},{m.y_m}) m"
                    + (" · 行动中" if m.is_current else "")
                    for m in group
                ],
                hoverinfo="text",
                customdata=[["unit", m.unit_id, m.x_m, m.y_m] for m in group],
            )
        )

    if markers:
        x_range, y_range = tactical_view_ranges(view)
    else:
        x_range = [-10, 10]
        y_range = [-10, 10]

    if x_range[0] <= 0 <= x_range[1] and y_range[0] <= 0 <= y_range[1]:
        fig.add_hline(y=0, line=dict(color="#475569", width=1, dash="dot"))
        fig.add_vline(x=0, line=dict(color="#475569", width=1, dash="dot"))

    fig.update_layout(
        autosize=True,
        height=chart_height,
        margin=dict(l=8, r=8, t=32, b=8),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            font=dict(size=10, color="#94a3b8"),
        ),
        xaxis=dict(
            title=dict(text="X (m)", font=dict(color="#94a3b8", size=10)),
            gridcolor="#334155",
            zeroline=False,
            range=x_range,
            domain=[0, 1],
            tickfont=dict(color="#64748b", size=9),
            fixedrange=False,
        ),
        yaxis=dict(
            title=dict(text="Y (m)", font=dict(color="#94a3b8", size=10)),
            gridcolor="#334155",
            zeroline=False,
            range=y_range,
            domain=[0, 1],
            tickfont=dict(color="#64748b", size=9),
            fixedrange=False,
        ),
        hovermode="closest",
        dragmode="pan",
    )
    return fig


def build_tactical_map_view(
    combat: CombatState,
    *,
    viewport_cells: int = 9,
) -> TacticalMapView:
    entries = _collect_unit_entries(combat)
    meters_per_cell = display_scale(entries, viewport_cells=viewport_cells)

    if entries:
        xs = [pos[0] for _, pos, _ in entries]
        ys = [pos[1] for _, pos, _ in entries]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
    else:
        center_x = center_y = 0.0

    half = (viewport_cells - 1) / 2
    origin_x = center_x - half * meters_per_cell
    origin_y = center_y - half * meters_per_cell

    grid: list[list[list[tuple[str, str, str]]]] = [
        [[] for _ in range(viewport_cells)] for _ in range(viewport_cells)
    ]

    for unit_id, pos, kind in entries:
        col_f = (pos[0] - origin_x) / meters_per_cell
        row_f = (pos[1] - origin_y) / meters_per_cell
        col = int(round(col_f))
        row = int(round(row_f))
        if 0 <= col < viewport_cells and 0 <= row < viewport_cells:
            symbol = {"player": "@", "ally": "+", "enemy": "x"}.get(kind, "?")
            grid[row][col].append((unit_id, symbol, kind))
        else:
            edge_col = max(0, min(viewport_cells - 1, col))
            edge_row = max(0, min(viewport_cells - 1, row))
            dist = distance_m(pos, (0, 0))
            symbol = {"player": "@", "ally": "+", "enemy": "x"}.get(kind, "?")
            grid[edge_row][edge_col].append((unit_id, symbol, kind))

    cells: list[list[MapCell]] = []
    current = combat.current_actor()
    for row in range(viewport_cells):
        row_cells: list[MapCell] = []
        for col in range(viewport_cells):
            occupants = grid[row][col]
            if not occupants:
                row_cells.append(MapCell(symbol="·"))
                continue
            symbols: list[str] = []
            labels: list[str] = []
            ids: list[str] = []
            for unit_id, sym, _kind in occupants:
                ids.append(unit_id)
                if unit_id == current or (current == "player" and unit_id == PLAYER_UNIT_ID):
                    sym = sym.upper()
                symbols.append(sym)
                if len(occupants) == 1 and unit_id != PLAYER_UNIT_ID:
                    pos = combat.get_position(unit_id)
                    if pos is not None:
                        dist = distance_m(pos, (0, 0))
                        if dist >= 30:
                            labels.append(f"{dist}m")
            label = labels[0] if labels else ""
            row_cells.append(
                MapCell(symbol="".join(symbols)[:3], label=label, unit_ids=tuple(ids))
            )
        cells.append(row_cells)
    return TacticalMapView(
        cells=cells,
        meters_per_cell=meters_per_cell,
        origin_x_m=origin_x,
        origin_y_m=origin_y,
        viewport_cells=viewport_cells,
    )


def render_tactical_map(combat: CombatState, *, viewport_cells: int = 9) -> str:
    view = build_tactical_map_view(combat, viewport_cells=viewport_cells)
    lines = [f"战术图（约 {view.meters_per_cell:.0f}m/格）"]
    for row in view.cells:
        lines.append(" ".join(cell.symbol.ljust(3) for cell in row))
    return "\n".join(lines)


def cell_center_m(view: TacticalMapView, row: int, col: int) -> PosM:
    x = int(round(view.origin_x_m + col * view.meters_per_cell))
    y = int(round(view.origin_y_m + row * view.meters_per_cell))
    return x, y


def format_unit_positions(combat: CombatState) -> list[str]:
    lines: list[str] = []
    player_pos = combat.get_position(PLAYER_UNIT_ID)
    for ally in combat.allies:
        pos = combat.get_position(ally.name)
        if pos is None:
            continue
        dist = combat.distance_between(PLAYER_UNIT_ID, ally.name)
        status = "已倒" if ally.hp <= 0 else f"HP {ally.hp}/{ally.max_hp}"
        lines.append(f"  · 友方 {ally.name}：{status} · ({pos[0]},{pos[1]})m · 距玩家 {dist}m")
    for enemy in combat.enemies:
        pos = combat.get_position(enemy.name)
        if pos is None:
            continue
        dist = combat.distance_between(PLAYER_UNIT_ID, enemy.name)
        if enemy.hp <= 0:
            status = "已倒"
        elif enemy.surrendered:
            status = "已投降"
        else:
            status = f"HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}"
        lines.append(f"  · {enemy.name}：{status} · ({pos[0]},{pos[1]})m · 距玩家 {dist}m")
    if player_pos is not None:
        lines.insert(0, f"  · 玩家：({player_pos[0]},{player_pos[1]})m")
    return lines
