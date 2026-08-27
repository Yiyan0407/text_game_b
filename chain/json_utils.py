import json
import re

from json_repair import loads as repair_json_loads


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _find_balanced_json(text: str, open_char: str, close_char: str) -> str | None:
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _json_candidates(text: str) -> list[str]:
    cleaned = strip_code_fence(text)
    if not cleaned:
        return []
    candidates: list[str] = [cleaned]
    for open_char, close_char in (("{", "}"), ("[", "]")):
        matched = _find_balanced_json(cleaned, open_char, close_char)
        if matched and matched not in candidates:
            candidates.append(matched)
    greedy_object = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if greedy_object and greedy_object.group() not in candidates:
        candidates.append(greedy_object.group())
    greedy_array = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if greedy_array and greedy_array.group() not in candidates:
        candidates.append(greedy_array.group())
    return candidates


def _loads_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "{" not in text and "[" not in text:
            raise
        data = repair_json_loads(text)
        if data == "":
            raise json.JSONDecodeError("empty repair result", text, 0)
        if isinstance(data, str):
            raise json.JSONDecodeError("repaired to plain string", text, 0)
        return data


def extract_json(text: str):
    for candidate in _json_candidates(text):
        try:
            return _loads_json(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    cleaned = strip_code_fence(text)
    if cleaned:
        try:
            return _loads_json(cleaned)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def extract_json_dict(text: str) -> dict | None:
    data = extract_json(text)
    return data if isinstance(data, dict) else None


def extract_json_list(text: str) -> list | None:
    data = extract_json(text)
    return data if isinstance(data, list) else None
