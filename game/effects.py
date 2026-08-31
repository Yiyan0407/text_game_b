"""实体效果：三通道（被动/攻击/使用）+ StatForge 标记。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class EntityEffects(BaseModel):
    # --- 被动：装备时生效 ---
    sp: int = Field(default=0, ge=0)
    sp_max: int = Field(default=0, ge=0)
    ac_bonus: int = 0
    max_hp_bonus: int = 0
    # 被动技能：相关检定加值（可为负；0=由系统按祝福/诅咒推断 ±2）
    check_bonus: int = 0

    # --- 攻击：attack 动作、手持武器 ---
    attack_damage: str = ""
    attack_bonus: int = 0
    use_dex: bool = False

    # --- 使用：use_item 动作 ---
    heal_dice: str = ""
    use_damage: str = ""
    use_auto_hit: bool = True
    use_aoe: bool = False
    use_tag: str = ""
    consumes_on_use: bool | None = None
    gear_slot: str = ""

    # 被动技能：相关属性检定自动 +2（由 skill_check 读取）
    related_abilities: list[str] = Field(default_factory=list)

    forged: bool = False

    @field_validator("related_abilities", mode="before")
    @classmethod
    def _coerce_related_abilities(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator(
        "attack_damage", "heal_dice", "use_damage", "use_tag", "gear_slot", mode="before"
    )
    @classmethod
    def _strip_text_fields(cls, value) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _sync_sp_max(self) -> EntityEffects:
        if self.sp_max <= 0 and self.sp > 0:
            object.__setattr__(self, "sp_max", self.sp)
        if self.sp_max > 0 and self.sp > self.sp_max:
            object.__setattr__(self, "sp", self.sp_max)
        return self

    def format_summary(self) -> str:
        parts: list[str] = []

        def _signed(label: str, value: int) -> str:
            sign = "+" if value > 0 else ""
            return f"{label}{sign}{value}"

        if self.attack_damage:
            parts.append(f"伤害 {self.attack_damage}")
        if self.use_damage:
            parts.append(f"使用伤 {self.use_damage}" + ("·范围" if self.use_aoe else ""))
        if self.sp_max > 0 or self.sp > 0:
            max_sp = self.sp_max or self.sp
            parts.append(f"SP {self.sp}/{max_sp}")
        if self.ac_bonus:
            parts.append(_signed("AC", self.ac_bonus))
        if self.max_hp_bonus:
            parts.append(_signed("HP", self.max_hp_bonus))
        if self.check_bonus:
            parts.append(_signed("检定", self.check_bonus))
        if self.heal_dice:
            parts.append(f"治疗 {self.heal_dice}")
        if self.use_tag:
            parts.append(f"用途 {self.use_tag}")
        return " · ".join(parts)

    def has_passive_stats(self) -> bool:
        return bool(
            self.sp > 0
            or self.sp_max > 0
            or self.ac_bonus != 0
            or self.max_hp_bonus != 0
            or self.check_bonus != 0
        )

    def has_attack_profile(self) -> bool:
        return bool(self.attack_damage)

    def has_use_effect(self) -> bool:
        return bool(self.heal_dice or self.use_damage or self.use_tag)

    def has_combat_stats(self) -> bool:
        return (
            self.has_passive_stats()
            or self.has_attack_profile()
            or bool(self.use_damage)
            or self.attack_bonus != 0
        )

    def has_mechanical_effect(self) -> bool:
        return self.has_combat_stats() or self.has_use_effect()

    def heals_on_use(self) -> bool:
        return bool(self.heal_dice)

    def damages_on_use(self) -> bool:
        return bool(self.use_damage)

    def consumes_when_used(self) -> bool:
        if self.consumes_on_use is not None:
            return self.consumes_on_use
        return self.has_use_effect()

    def inferred_gear_slot(self) -> str | None:
        """StatForge 裁定的手持用途：weapon / light / tool。"""
        slot = self.gear_slot.strip().lower()
        if slot in ("weapon", "light", "tool"):
            return slot
        if self.has_attack_profile():
            return "weapon"
        return None

    @classmethod
    def coerce(cls, value) -> EntityEffects | None:
        if value is None:
            return None
        if isinstance(value, EntityEffects):
            return value
        if isinstance(value, dict):
            forged = bool(value.get("forged"))
            has_stats = any(
                value.get(key)
                for key in (
                    "attack_damage",
                    "use_damage",
                    "sp",
                    "sp_max",
                    "ac_bonus",
                    "max_hp_bonus",
                    "check_bonus",
                    "attack_bonus",
                    "heal_dice",
                    "use_tag",
                )
            )
            if not forged and not has_stats:
                return None
            return cls.model_validate(value)
        return None


def is_forge_pending(effects: EntityEffects | None) -> bool:
    """尚未经 StatForge 裁定（无 effects，或旧存档未标记 forged）。"""
    return effects is None or not effects.forged
