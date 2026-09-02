"""角色外貌档案：供立绘 prompt 使用。"""

from pydantic import BaseModel, Field

GENDER_OPTIONS: tuple[str, ...] = ("男", "女", "不明确")
AGE_OPTIONS: tuple[str, ...] = ("少年", "青年", "中年", "老年")
DEFAULT_GENDER = "不明确"
DEFAULT_AGE = "青年"


class CharacterAppearance(BaseModel):
    gender: str = Field(default="", description="男 / 女 / 不明确")
    age: str = Field(default="", description="少年 / 青年 / 中年 / 老年，或约略岁数")
    ancestry: str = Field(default="", description="种族、族裔或物种，如人类、精灵、亚裔")
    build: str = Field(default="", description="身高体态，如高挑、魁梧、纤细")
    hair: str = Field(default="", description="发型与发色")
    skin_tone: str = Field(default="", description="肤色")
    distinctive: str = Field(default="", description="其他显著外貌特征")

    def is_empty(self) -> bool:
        return not any(
            (
                self.gender,
                self.age,
                self.ancestry,
                self.build,
                self.hair,
                self.skin_tone,
                self.distinctive,
            )
        )

    def format_for_prompt(self) -> str:
        parts: list[str] = []
        mapping = (
            ("性别", self.gender),
            ("年龄", self.age),
            ("种族/族裔", self.ancestry),
            ("体态", self.build),
            ("发型发色", self.hair),
            ("肤色", self.skin_tone),
            ("显著特征", self.distinctive),
        )
        for label, value in mapping:
            text = (value or "").strip()
            if text:
                parts.append(f"{label}：{text}")
        return "；".join(parts)


def parse_appearance_dict(data: dict | None) -> CharacterAppearance:
    if not isinstance(data, dict):
        return CharacterAppearance()
    return CharacterAppearance(
        gender=str(data.get("gender") or "").strip()[:32],
        age=str(data.get("age") or "").strip()[:48],
        ancestry=str(data.get("ancestry") or "").strip()[:48],
        build=str(data.get("build") or "").strip()[:48],
        hair=str(data.get("hair") or "").strip()[:64],
        skin_tone=str(data.get("skin_tone") or data.get("skin") or "").strip()[:32],
        distinctive=str(data.get("distinctive") or data.get("other") or "").strip()[:120],
    )


def merge_appearance(
    manual: CharacterAppearance,
    inferred: CharacterAppearance,
) -> CharacterAppearance:
    """创角手填的性别/年龄优先；种族等仍以后台推断为准。"""
    return CharacterAppearance(
        gender=(manual.gender or "").strip() or inferred.gender,
        age=(manual.age or "").strip() or inferred.age,
        ancestry=inferred.ancestry or manual.ancestry,
        build=inferred.build or manual.build,
        hair=inferred.hair or manual.hair,
        skin_tone=inferred.skin_tone or manual.skin_tone,
        distinctive=inferred.distinctive or manual.distinctive,
    )
