"""Extract JSON arrays from LLM text (preamble, markdown fences, etc.)."""

import json


def parse_json_array_from_llm(raw: str | None) -> list:
    """
    Parse a JSON array from an LLM reply. Raises json.JSONDecodeError if none found.
    """
    if raw is None:
        raise json.JSONDecodeError("Empty LLM response", "", 0)
    s = raw.strip()
    if not s:
        raise json.JSONDecodeError("Empty LLM response", "", 0)

    s = _strip_outer_markdown_fence(s)

    for candidate in _json_array_candidates(s):
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, list):
            return result

    raise json.JSONDecodeError("No JSON array found in LLM response", s, 0)


def _strip_outer_markdown_fence(s: str) -> str:
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if len(lines) < 2:
        return s
    rest = "\n".join(lines[1:])
    if "```" in rest:
        rest = rest[: rest.rindex("```")].rstrip()
    return rest.strip()


def _json_array_candidates(s: str):
    yield s
    extracted = _extract_balanced_json_array(s)
    if extracted:
        yield extracted
        inner = _strip_outer_markdown_fence(extracted.strip())
        if inner != extracted:
            yield inner


def _extract_balanced_json_array(s: str) -> str | None:
    start = s.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None
