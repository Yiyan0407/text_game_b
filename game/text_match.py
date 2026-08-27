import re


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def fuzzy_match_name(ref: str, candidate: str) -> bool:
    ref_norm = normalize_name(ref)
    candidate_norm = normalize_name(candidate)
    if not ref_norm or not candidate_norm:
        return False
    return (
        ref_norm == candidate_norm
        or ref_norm in candidate_norm
        or candidate_norm in ref_norm
    )


def fuzzy_in_list(name: str, items: list[str]) -> bool:
    return any(fuzzy_match_name(name, item) for item in items)


def resolve_fuzzy_name(name: str, items: list[str]) -> str | None:
    for item in items:
        if fuzzy_match_name(name, item):
            return item
    return None
