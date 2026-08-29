"""时限登记叙事依据校验：防止 Agent 照搬提示词示例或凭空编造倒计时。"""

from __future__ import annotations

from game.results import DeadlinePatch

# 提示词 JSON 示例中的标签；无叙事依据时一律拦截
_PROMPT_TEMPLATE_LABELS = frozenset(
    {
        "炸弹爆炸",
    }
)


def build_deadline_corpus(
    *,
    user_input: str = "",
    memory_facts: list[str] | None = None,
    mechanical_events: list[str] | None = None,
    recent_history: str = "",
) -> str:
    parts: list[str] = []
    if user_input.strip():
        parts.append(user_input.strip())
    if recent_history.strip():
        parts.append(recent_history.strip())
    if memory_facts:
        parts.extend(fact.strip() for fact in memory_facts if fact.strip())
    if mechanical_events:
        parts.extend(event.strip() for event in mechanical_events if event.strip())
    return "\n".join(parts)


def is_deadline_grounded(label: str, corpus: str) -> bool:
    """时限标签须在可用上下文中出现，或至少有一个连续二字片段可匹配。"""
    label = label.strip()
    corpus = corpus.strip()
    if not label:
        return False
    if not corpus:
        return False
    if label in corpus:
        return True
    if len(label) >= 2:
        for index in range(len(label) - 1):
            if label[index : index + 2] in corpus:
                return True
    return False


def filter_deadline_patches(
    deadlines: list[DeadlinePatch],
    corpus: str,
) -> tuple[list[DeadlinePatch], list[str]]:
    kept: list[DeadlinePatch] = []
    events: list[str] = []
    for deadline in deadlines:
        label = deadline.label.strip()
        if not label:
            continue
        if is_deadline_grounded(label, corpus):
            kept.append(deadline)
            continue
        if label in _PROMPT_TEMPLATE_LABELS:
            events.append(f"跳过无依据时限：{label}（提示词示例，叙事未提及）")
        else:
            events.append(f"跳过无依据时限：{label}（上下文未出现该倒计时/威胁）")
    return kept, events
