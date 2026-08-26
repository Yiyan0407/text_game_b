import json
from pathlib import Path

from config.settings import SCENARIOS_DIR
from game.scenario import Scenario

GENERATED_DIR = SCENARIOS_DIR / "generated"


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
