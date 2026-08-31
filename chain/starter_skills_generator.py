from game.starter_loadout import StarterLoadoutGenerationError


class StarterSkillsGenerationError(StarterLoadoutGenerationError):
    pass


class StarterSkillsGenerator:
    """兼容旧接口：仅返回 skills 列表。"""

    def __init__(self):
        self._loadout = None

    def _generator(self):
        from chain.starter_loadout_generator import StarterLoadoutGenerator

        if self._loadout is None:
            self._loadout = StarterLoadoutGenerator()
        return self._loadout

    def generate(self, background: str, *, world_id: str) -> list[str]:
        return self._generator().generate(background, world_id=world_id).skills[:3]

    @staticmethod
    def _parse_response(text: str) -> list[str]:
        from chain.json_utils import extract_json_dict
        from game.starter_loadout import parse_starter_loadout_dict

        data = extract_json_dict(text)
        if not isinstance(data, dict):
            return []
        return parse_starter_loadout_dict(data).skills


def generate_starter_loadout(background: str, *, world_id: str):
    from chain.starter_loadout_generator import StarterLoadoutGenerator
    from game.starter_loadout import StarterLoadout

    return StarterLoadoutGenerator().generate(background, world_id=world_id)
