"""NPC 名称合并与去重。"""

from __future__ import annotations

import re

from game.models import NPCRelation
from game.text_match import normalize_name

# 常见单姓（用于识别「周师傅」「出租车司机周师傅」等）
_SURNAME_CHARS = (
    "张王李赵刘陈杨黄周吴徐孙马朱胡郭何高林郑梁谢宋唐许韩冯邓曹彭曾肖董袁潘"
    "于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江"
    "尹薛段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤欧阳司马上官"
)
_SHIFU_SUFFIX = re.compile(rf"([{_SURNAME_CHARS}]{{1,2}})师傅")
_ROLE_PREFIXES = (
    "出租车司机",
    "出租车师傅",
    "司机",
    "清洁工",
    "值班护士",
    "护士",
    "店员",
    "老板",
)


def extract_surname_tokens(name: str) -> set[str]:
    """从称呼中提取可区分身份的姓氏/名讳 token。"""
    text = name.strip()
    if not text:
        return set()
    tokens: set[str] = set()
    for match in _SHIFU_SUFFIX.finditer(text):
        tokens.add(match.group(1))
    # 「我姓周」「周记出行」类：仅当 X师傅 未出现时辅助
    if not tokens:
        for match in re.finditer(rf"姓([{_SURNAME_CHARS}])", text):
            tokens.add(match.group(1))
    return tokens


def role_prefix(name: str) -> str | None:
    for prefix in _ROLE_PREFIXES:
        if prefix in name:
            return prefix
    return None


def is_generic_role_name(name: str) -> bool:
    """无姓氏、仅职业/通称（如「出租车司机」）。"""
    cleaned = name.strip()
    if not cleaned or extract_surname_tokens(cleaned):
        return False
    return cleaned in _ROLE_PREFIXES or any(
        cleaned == prefix for prefix in _ROLE_PREFIXES
    )


def npc_names_same_person(left: str, right: str) -> bool:
    """判断两个称呼是否指同一人（保守，避免张/王/刘师傅误合并）。"""
    a = left.strip()
    b = right.strip()
    if not a or not b:
        return False
    if normalize_name(a) == normalize_name(b):
        return True

    sa = extract_surname_tokens(a)
    sb = extract_surname_tokens(b)
    if sa and sb and sa.isdisjoint(sb):
        return False

    if sa & sb:
        return True

    if a in b or b in a:
        return True

    return False


def _count_role_bearers(npcs: list[NPCRelation], role: str) -> int:
    return sum(1 for npc in npcs if role in npc.name)


def find_npc_by_name(npcs: list[NPCRelation], name_ref: str) -> NPCRelation | None:
    ref = name_ref.strip()
    if not ref:
        return None

    ref_surnames = extract_surname_tokens(ref)
    ref_role = role_prefix(ref)

    # 1) 姓氏明确：匹配同姓条目（周师傅 ↔ 出租车司机周师傅）
    if ref_surnames:
        surname_matches = [
            npc
            for npc in npcs
            if extract_surname_tokens(npc.name) & ref_surnames
        ]
        if len(surname_matches) == 1:
            return surname_matches[0]
        if len(surname_matches) > 1:
            for npc in surname_matches:
                if npc_names_same_person(ref, npc.name):
                    return npc
            return None

    # 2) 通称 → 补全姓氏：仅当该职业在列表里只有一人时合并
    if is_generic_role_name(ref) and ref_role:
        if _count_role_bearers(npcs, ref_role) == 1:
            for npc in npcs:
                if ref_role in npc.name and npc_names_same_person(ref, npc.name):
                    return npc
        return None

    # 3) 其它 substring / 完全一致（无姓氏冲突）
    matches = [npc for npc in npcs if npc_names_same_person(ref, npc.name)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        if ref_role:
            role_matches = [npc for npc in matches if ref_role in npc.name]
            if len(role_matches) == 1:
                return role_matches[0]
        return None
    return None


def preferred_npc_name(existing: str, incoming: str) -> str:
    left = existing.strip()
    right = incoming.strip()
    if not left:
        return right
    if not right:
        return left
    if normalize_name(left) == normalize_name(right):
        return left
    if left in right:
        return right
    if right in left:
        return left
    if extract_surname_tokens(right) and not extract_surname_tokens(left):
        return right
    return right if len(right) > len(left) else left


def _notes_similar(left: str, right: str) -> bool:
    a = left.strip()
    b = right.strip()
    if not a or not b:
        return True
    if a in b or b in a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    for size in (6, 5, 4):
        if len(shorter) < size:
            continue
        for i in range(len(shorter) - size + 1):
            if shorter[i : i + size] in longer:
                return True
    return False


def merge_npc_notes(existing: str, incoming: str) -> str:
    old = existing.strip()
    new = incoming.strip()
    if not old:
        return new
    if not new:
        return old
    if old == new:
        return old
    if _notes_similar(old, new):
        return new if len(new) >= len(old) else old
    return f"{old}；{new}"


def dedupe_npc_list(npcs: list[NPCRelation]) -> list[NPCRelation]:
    merged: list[NPCRelation] = []
    for npc in npcs:
        target = find_npc_by_name(merged, npc.name)
        if target is None:
            merged.append(npc.model_copy())
            continue
        target.name = preferred_npc_name(target.name, npc.name)
        target.attitude = npc.attitude or target.attitude
        target.notes = merge_npc_notes(target.notes, npc.notes)
    return merged
