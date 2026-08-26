from game.dice import roll
from game.models import Character, CombatEnemy, CombatState, GameState


def parse_enemies(spec: str) -> list[CombatEnemy]:
    """解析敌人描述，格式：名字:HP:AC，多个用逗号分隔。"""
    enemies: list[CombatEnemy] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = [t.strip() for t in part.split(":")]
        if len(tokens) < 2:
            raise ValueError(f"无效的敌人格式: {part}，请用 名字:HP:AC")
        name = tokens[0]
        hp = int(tokens[1])
        ac = int(tokens[2]) if len(tokens) > 2 else 12
        enemies.append(CombatEnemy(name=name, hp=hp, max_hp=hp, ac=ac))
    if not enemies:
        raise ValueError("至少需要一个敌人")
    return enemies


def start_combat(
    character: Character,
    game_state: GameState,
    enemies_spec: str,
) -> str:
    enemies = parse_enemies(enemies_spec)
    dex_mod = character.modifier("dex")
    player_init = roll(f"1d20{dex_mod:+d}").total

    for enemy in enemies:
        enemy.initiative = roll("1d20").total

    order = sorted(
        [("player", player_init)] + [(e.name, e.initiative) for e in enemies],
        key=lambda x: x[1],
        reverse=True,
    )
    turn_order = [name for name, _ in order]

    game_state.combat = CombatState(
        active=True,
        round=1,
        enemies=enemies,
        player_initiative=player_init,
        turn_order=turn_order,
    )
    order_text = " → ".join(
        character.name if n == "player" else n for n in turn_order
    )
    return (
        f"战斗开始！先攻顺序：{order_text}。"
        f"玩家先攻 {player_init}。"
        + " ".join(f"{e.name} 先攻 {e.initiative}" for e in enemies)
    )


def player_attack(
    character: Character,
    game_state: GameState,
    target_name: str,
    use_dex: bool = False,
) -> str:
    combat = game_state.combat
    if not combat or not combat.active:
        return "当前不在战斗中。"

    enemy = combat.get_enemy(target_name)
    if not enemy or enemy.hp <= 0:
        return f"找不到存活的敌人：{target_name}"

    attr = "dex" if use_dex else "str"
    mod = character.modifier(attr)
    attack = roll(f"1d20{mod:+d}")
    hit = attack.total >= enemy.ac

    if not hit:
        return (
            f"攻击 {enemy.name}：1d20[{attack.rolls[0]}]{mod:+d}={attack.total} "
            f"vs AC {enemy.ac} → 未命中"
        )

    damage = roll(f"1d6{mod:+d}")
    enemy.hp = max(0, enemy.hp - damage.total)
    result = (
        f"攻击 {enemy.name}：命中！伤害 {damage.describe()}。"
        f"{enemy.name} 剩余 HP {enemy.hp}/{enemy.max_hp}"
    )
    if enemy.hp <= 0:
        result += f" {enemy.name} 被击倒！"
    if not combat.living_enemies():
        result += " 所有敌人已倒下，可调用 end_combat 结束战斗。"
    return result


def end_combat(game_state: GameState) -> str:
    if not game_state.combat or not game_state.combat.active:
        return "当前没有进行中的战斗。"
    game_state.combat.active = False
    game_state.combat = None
    return "战斗结束。"
