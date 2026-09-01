import streamlit as st

from game.combat_grid import (
    PLAYER_UNIT_ID,
    build_tactical_map_figure,
    format_unit_positions,
    render_tactical_map,
    render_tactical_map_html,
)
from game.models import Character, GameState

AUTO_COMBAT_PENDING_KEY = "auto_combat_pending"
COMBAT_MOVE_PENDING_KEY = "combat_move_pending"
COMBAT_PANEL_OPEN_KEY = "combat_panel_open"
TACTICAL_MAP_CHART_KEY = "combat_tactical_map"


def _has_dialog() -> bool:
    return hasattr(st, "dialog")

_ACTION_GUIDE = """
**每回合资源（用完输入「结束回合」）**

| 资源 | 消耗 | 典型用途 |
|------|------|----------|
| **移动力** | 免费 | 靠近/远离敌人（`move`）或下方坐标移动 |
| **免费物件互动** | 免费 · 每回合 1 次 | 拾取眼前物品、快速拔/收武器 |
| **主要动作** | 1 次 | 攻击、防御、擒抱、推撞、撤退、疾跑 |
| **附加动作** | 1 次 | 用手雷/药水、收刀威慑（`talk`） |

- 友方 NPC 参战时会**自动**攻击敌人；你只控制自己的角色。
- 攻击已装备武器可直接打；**武器 + 武学/技能**伤害叠加。
- 敌人 **SP** = 装甲，减少每次命中扣血；打不动就换武器或跑。
"""


def _enemy_status(enemy, combat) -> str:
    dist = combat.distance_between(PLAYER_UNIT_ID, enemy.name)
    pos = combat.get_position(enemy.name)
    pos_label = f" · ({pos[0]},{pos[1]})" if pos else ""
    sp_label = ""
    if enemy.sp_max > 0:
        sp_label = f" · SP {enemy.sp}/{enemy.sp_max}"
    elif enemy.sp > 0:
        sp_label = f" · SP {enemy.sp}"
    return (
        f"{enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}"
        f"{sp_label}{pos_label} · {dist}m"
    )


def _ally_status(ally, combat) -> str:
    dist = combat.distance_between(PLAYER_UNIT_ID, ally.name)
    pos = combat.get_position(ally.name)
    pos_label = f" · ({pos[0]},{pos[1]})" if pos else ""
    return f"{ally.name} HP {ally.hp}/{ally.max_hp} AC {ally.ac}{pos_label} · 距你 {dist}m（自动作战）"


def _render_move_controls(combat, *, character: Character | None) -> None:
    if character is None or not combat.is_player_turn() or not combat.has_movement():
        return
    player_pos = combat.get_position(PLAYER_UNIT_ID) or (0, 0)
    st.caption(
        f"移动目标（米坐标，剩余移动力 {combat.movement_remaining_m}m）"
        " · 也可文字指令如「靠近长矛手 6m」"
    )
    col_x, col_y, col_btn = st.columns([1, 1, 1])
    with col_x:
        target_x = st.number_input(
            "X",
            value=int(player_pos[0]),
            step=1,
            key="combat_move_target_x",
            label_visibility="collapsed",
        )
    with col_y:
        target_y = st.number_input(
            "Y",
            value=int(player_pos[1]),
            step=1,
            key="combat_move_target_y",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("移动到此", key="combat_move_submit", use_container_width=True):
            st.session_state[COMBAT_MOVE_PENDING_KEY] = {
                "x_m": int(target_x),
                "y_m": int(target_y),
            }
            st.rerun()

    living_enemies = combat.living_enemy_names()
    if living_enemies:
        quick_col1, quick_col2 = st.columns(2)
        with quick_col1:
            toward = st.selectbox(
                "快速靠近",
                ["—"] + living_enemies,
                key="combat_move_toward_enemy",
                label_visibility="visible",
            )
            if toward != "—" and st.button(
                "执行靠近",
                key="combat_move_toward_btn",
                use_container_width=True,
            ):
                pos = combat.get_position(toward)
                if pos is not None:
                    st.session_state[COMBAT_MOVE_PENDING_KEY] = {
                        "x_m": pos[0],
                        "y_m": pos[1],
                    }
                    st.rerun()
        with quick_col2:
            away = st.selectbox(
                "快速远离",
                ["—"] + living_enemies,
                key="combat_move_away_enemy",
            )
            if away != "—" and st.button(
                "执行远离",
                key="combat_move_away_btn",
                use_container_width=True,
            ):
                pos = combat.get_position(away) or (0, 0)
                player_pos = combat.get_position(PLAYER_UNIT_ID) or (0, 0)
                dx = player_pos[0] - pos[0]
                dy = player_pos[1] - pos[1]
                st.session_state[COMBAT_MOVE_PENDING_KEY] = {
                    "x_m": player_pos[0] + dx,
                    "y_m": player_pos[1] + dy,
                }
                st.rerun()


TACTICAL_MAP_HEIGHT = 400
_PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": True, "responsive": True}


def _apply_plotly_move_selection(event, combat) -> bool:
    if event is None:
        return False
    player_pos = combat.get_position(PLAYER_UNIT_ID)
    points = event.selection.points if event.selection else []
    for pt in points:
        custom = pt.get("customdata") if isinstance(pt, dict) else None
        if not custom or custom[0] != "move":
            continue
        target = (int(custom[1]), int(custom[2]))
        if player_pos == target:
            return False
        st.session_state[COMBAT_MOVE_PENDING_KEY] = {
            "x_m": target[0],
            "y_m": target[1],
        }
        return True
    return False


def apply_combat_move_pending(
    character: Character | None,
    game_state: GameState,
) -> bool:
    """消费待处理移动；成功时返回 True（调用方应 rerun）。"""
    move_target = st.session_state.pop(COMBAT_MOVE_PENDING_KEY, None)
    if not move_target or character is None or not game_state.is_in_combat():
        return False
    from game.combat import player_move_to
    from game.models import ChatMessage
    from game.session import persist_save

    msg = player_move_to(
        character,
        game_state,
        move_target["x_m"],
        move_target["y_m"],
    )
    st.session_state.messages.append(
        ChatMessage(role="system", content=f"⚙️ **移动** — {msg}")
    )
    persist_save()
    return True


def _render_tactical_map(
    combat,
    *,
    character: Character | None,
    game_state: GameState | None = None,
) -> None:
    can_move = (
        character is not None
        and combat.is_player_turn()
        and combat.has_movement()
    )
    if can_move:
        st.caption(
            f"战术平面 · 剩余 {combat.movement_remaining_m}m · 点击浅格移动"
        )
        try:
            fig = build_tactical_map_figure(
                combat,
                show_move_targets=True,
                chart_height=TACTICAL_MAP_HEIGHT,
            )
        except ImportError:
            st.warning("需要 plotly 才能点格移动：`pip install plotly`")
            html = render_tactical_map_html(
                combat,
                height=TACTICAL_MAP_HEIGHT,
                show_move_targets=True,
            )
            st.iframe(html, height=TACTICAL_MAP_HEIGHT + 8)
            return

        player_pos = combat.get_position(PLAYER_UNIT_ID) or (0, 0)
        chart_key = (
            f"{TACTICAL_MAP_CHART_KEY}_{combat.round}_"
            f"{player_pos[0]}_{player_pos[1]}_{combat.movement_remaining_m}"
        )
        event = st.plotly_chart(
            fig,
            key=chart_key,
            on_select="rerun",
            selection_mode="points",
            width="stretch",
            height=TACTICAL_MAP_HEIGHT,
            theme=None,
            config=_PLOTLY_CONFIG,
        )
        applied = _apply_plotly_move_selection(event, combat)
        if applied and game_state is not None and apply_combat_move_pending(character, game_state):
            st.rerun()
        return

    st.caption("战术平面 · 坐标单位：米")
    html = render_tactical_map_html(combat, height=TACTICAL_MAP_HEIGHT)
    st.iframe(html, height=TACTICAL_MAP_HEIGHT + 8)


def render_tactical_map_panel(
    combat,
    *,
    character: Character | None = None,
    game_state: GameState | None = None,
) -> None:
    _render_tactical_map(combat, character=character, game_state=game_state)
    _render_move_controls(combat, character=character)
    with st.expander("ASCII 战术图（供核对）", expanded=False):
        st.code(render_tactical_map(combat), language="text")


def _render_combat_content(game_state: GameState, *, character: Character | None = None) -> None:
    combat = game_state.combat
    if not combat or not combat.active:
        st.info("当前不在战斗中。")
        return

    actor = combat.current_actor()
    actor_label = "你" if actor == "player" else (
        f"友方·{actor}" if combat.get_ally(actor) else actor
    )
    st.caption(f"第 {combat.round} 回合 · 先攻：{' → '.join(combat.turn_order)}")
    st.markdown(f"**当前行动者：{actor_label}**")

    with st.expander("动作说明", expanded=False):
        st.markdown(_ACTION_GUIDE)

    render_tactical_map_panel(combat, character=character, game_state=game_state)

    if combat.is_player_turn():
        st.info(
            f"轮到你了 — {combat.format_action_economy()}。"
            "可在战术图**点击方格**或下方设坐标移动，或文字指令；用完后输入「结束回合」。"
        )
        main = "✓" if combat.has_main_action() else "✗"
        bonus = "✓" if combat.has_bonus_action() else "✗"
        move = "✓" if combat.has_movement() else "✗"
        free = "✓" if combat.has_free_interact() else "✗"
        st.caption(
            f"移动力 {move} ({combat.movement_remaining_m}/{combat.movement_speed_m}m) · "
            f"免费互动 {free} · 主要动作 {main} · 附加动作 {bonus}"
        )
        if st.button(
            "⚡ 自动战斗",
            key="auto_combat_button",
            use_container_width=True,
            help="系统代跑剩余战斗并结算，KP 将根据结果描写整场战斗。",
        ):
            st.session_state[AUTO_COMBAT_PENDING_KEY] = True
            st.session_state[COMBAT_PANEL_OPEN_KEY] = False
            st.rerun()
    else:
        st.warning(f"等待 {actor_label} 的回合（友方/敌人行动已在后台结算）")

    with st.expander("单位坐标", expanded=False):
        for line in format_unit_positions(combat):
            st.caption(line)

    if combat.allies:
        st.markdown("**友方**")
        for ally in combat.allies:
            if ally.hp > 0:
                max_hp = max(1, ally.max_hp)
                hp_ratio = max(0.0, min(1.0, ally.hp / max_hp))
                st.progress(hp_ratio, text=_ally_status(ally, combat))
            else:
                st.caption(f"{ally.name} — 已倒下")

    st.markdown("**敌人**")
    for enemy in combat.enemies:
        if enemy.hp > 0:
            max_hp = max(1, enemy.max_hp)
            hp_ratio = max(0.0, min(1.0, enemy.hp / max_hp))
            st.progress(
                hp_ratio,
                text=_enemy_status(enemy, combat),
            )
        else:
            st.markdown(f"~~{enemy.name}~~ 已倒")


def _open_combat_dialog(game_state: GameState, *, character: Character | None = None) -> None:
    combat = game_state.combat
    title = f"战斗面板 · 第 {combat.round} 回合" if combat else "战斗面板"
    if _has_dialog():

        @st.dialog(title, width="large")
        def _dialog_body() -> None:
            _render_combat_content(game_state, character=character)
            if st.button("关闭", key="combat_panel_close", use_container_width=True):
                st.session_state[COMBAT_PANEL_OPEN_KEY] = False
                st.rerun()

        _dialog_body()
        return

    with st.expander("战斗面板（完整）", expanded=True):
        _render_combat_content(game_state, character=character)
        if st.button("关闭", key="combat_panel_close_fallback", use_container_width=True):
            st.session_state[COMBAT_PANEL_OPEN_KEY] = False
            st.rerun()


def render_combat_entry(game_state: GameState, *, character: Character | None = None) -> None:
    """主界面入口：战斗中显示按钮，点击打开战斗面板弹窗。"""
    combat = game_state.combat
    if not combat or not combat.active:
        st.session_state.pop(COMBAT_PANEL_OPEN_KEY, None)
        return

    living = len(combat.living_enemy_names())
    if combat.is_player_turn():
        turn_hint = "轮到你"
    else:
        actor = combat.current_actor()
        actor_label = "你" if actor == "player" else (
            f"友方·{actor}" if combat.get_ally(actor) else actor
        )
        turn_hint = f"等待 {actor_label}"

    label = f"⚔️ 战斗面板 · 第 {combat.round} 回合 · {turn_hint}"
    if living:
        label += f" · {living} 敌"

    if st.button(label, key="open_combat_panel", use_container_width=True):
        st.session_state[COMBAT_PANEL_OPEN_KEY] = True

    if st.session_state.get(COMBAT_PANEL_OPEN_KEY):
        _open_combat_dialog(game_state, character=character)


def render_combat_panel(game_state: GameState, *, character: Character | None = None) -> None:
    """兼容旧调用：等同 render_combat_entry。"""
    render_combat_entry(game_state, character=character)
