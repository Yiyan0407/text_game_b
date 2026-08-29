import json
import re
import uuid
from pathlib import Path

from config.settings import SCENARIOS_DIR
from game.scenario import Scenario

GENERATED_DIR = SCENARIOS_DIR / "generated"


def slugify_scenario_id(title: str, *, prefix: str = "manual") -> str:
    cleaned = re.sub(r"[^\w\s-]", "", title.lower())
    cleaned = re.sub(r"[\s_-]+", "_", cleaned).strip("_")
    slug = cleaned[:24] or "adventure"
    return f"{prefix}_{slug}_{uuid.uuid4().hex[:6]}"


def slugify_entity_id(label: str, *, prefix: str = "loc", existing: set[str] | None = None) -> str:
    """从中文/英文标题生成稳定内部 id（供系统用，不展示给玩家编辑）。"""
    text = (label or "").strip()
    ascii_part = re.sub(r"[^\w\s-]", "", text.lower())
    ascii_part = re.sub(r"[\s_-]+", "_", ascii_part).strip("_")
    if ascii_part:
        base = ascii_part[:40]
    else:
        base = f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, text).hex[:8]}"
    if base[0].isdigit():
        base = f"{prefix}_{base}"
    used = existing or set()
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def blank_scenario_template(world_id: str = "fantasy") -> Scenario:
    return Scenario(
        id="draft_manual",
        title="",
        description="",
        world_id=world_id,
        world="",
        tone="",
        opening_scene_id="start",
        opening_scene_name="起点",
        opening_prompt="",
        custom_world_overlay="",
        initial_quests=[],
        key_nodes=[],
        endings=[],
        is_generated=True,
    )


class ScenarioNotFoundError(FileNotFoundError):
    pass


def _scenario_path(scenario_id: str) -> Path | None:
    for directory in (SCENARIOS_DIR, GENERATED_DIR):
        path = directory / f"{scenario_id}.json"
        if path.exists():
            return path
    return None


def list_scenarios(include_generated: bool = True) -> list[Scenario]:
    scenarios: list[Scenario] = []
    if SCENARIOS_DIR.exists():
        for path in sorted(SCENARIOS_DIR.glob("*.json")):
            scenarios.append(load_scenario(path.stem))
    if include_generated and GENERATED_DIR.exists():
        for path in sorted(GENERATED_DIR.glob("*.json")):
            scenarios.append(load_scenario(path.stem))
    return scenarios


def load_scenario(scenario_id: str) -> Scenario:
    path = _scenario_path(scenario_id)
    if not path:
        raise ScenarioNotFoundError(f"模组不存在: {scenario_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario.model_validate(data)


def save_scenario(scenario: Scenario, generated: bool = True) -> Path:
    directory = GENERATED_DIR if generated else SCENARIOS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    payload = scenario.model_copy(update={"is_generated": generated})
    path = directory / f"{payload.id}.json"
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return path


def can_delete_scenario(scenario_id: str) -> bool:
    return (GENERATED_DIR / f"{scenario_id}.json").exists()


def delete_generated_scenario(scenario_id: str) -> bool:
    path = GENERATED_DIR / f"{scenario_id}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def get_scenario_or_default(scenario_id: str | None) -> Scenario:
    if scenario_id:
        try:
            return load_scenario(scenario_id)
        except ScenarioNotFoundError:
            pass
    scenarios = list_scenarios()
    if scenarios:
        return scenarios[0]
    raise ScenarioNotFoundError("没有可用的模组")
