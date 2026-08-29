
from game.combat import enemies_from_route_defs
from game.enemy_defaults import apply_world_defaults
from game.models import CombatEnemy
from game.results import EnemyDefPatch


def test_apply_world_defaults_does_not_fill_sp():
    enemy = CombatEnemy(name="变异体", hp=20, max_hp=20, ac=12, sp=0, sp_max=0)
    apply_world_defaults(enemy, "cyberpunk")
    assert enemy.sp == 0
    assert enemy.attack_damage == "2d8"


def test_enemy_defs_preserves_boss_sp():
    enemies = enemies_from_route_defs(
        [
            EnemyDefPatch(
                name="实验体首领",
                hp=100,
                ac=16,
                attack_damage="2d10",
                sp=60,
                sp_max=60,
            )
        ],
        world_id="cyberpunk",
    )
    assert len(enemies) == 1
    assert enemies[0].sp == 60
    assert enemies[0].hp == 100
