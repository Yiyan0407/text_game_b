"""Static checks for Streamlit UI footguns."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_character_selection_passes_game_config_to_creation():
    path = ROOT / "ui" / "character_library.py"
    text = path.read_text(encoding="utf-8")
    assert "render_game_options" in text
    assert "game_config=game_config" in text
    tree = _parse(path)
    selection = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_character_selection"
    )
    calls_creation_with_config = False
    for node in ast.walk(selection):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id == "render_character_creation"
        ):
            continue
        for kw in node.keywords:
            if kw.arg == "game_config":
                calls_creation_with_config = True
    assert calls_creation_with_config, "render_character_selection 必须把 game_config 传给创角"


def test_character_creation_skips_options_when_config_provided():
    path = ROOT / "ui" / "main_menu.py"
    text = path.read_text(encoding="utf-8")
    assert "if game_config is None:" in text
    assert "render_game_options(show_background_validation=True)" in text


def test_game_options_widget_keys_are_distinct():
    from ui.game_options import BG_VALIDATION_KEY, KP_GUIDANCE_KEY

    assert KP_GUIDANCE_KEY != BG_VALIDATION_KEY


def test_risky_action_pending_key_not_button_key():
    from ui.risky_action import CANCEL_BUTTON_KEY, CONFIRM_BUTTON_KEY, SESSION_KEY

    assert SESSION_KEY not in {CONFIRM_BUTTON_KEY, CANCEL_BUTTON_KEY}


def test_game_state_panel_uses_memory_journal_dialog():
    panel = ROOT / "ui" / "game_state_panel.py"
    text = panel.read_text(encoding="utf-8")
    assert "render_memory_journal_entry" in text
    assert "关键记忆" in text
    assert "render_scene_map_entry" in text
    dialog = ROOT / "ui" / "memory_journal_dialog.py"
    dialog_text = dialog.read_text(encoding="utf-8")
    assert "open_memory_journal" in dialog_text
    map_dialog = ROOT / "ui" / "scene_map_dialog.py"
    map_text = map_dialog.read_text(encoding="utf-8")
    assert "open_scene_map" in map_text
    assert "render_cytoscape_html" in map_text
    assert "st.iframe" in map_text
