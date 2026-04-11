"""Extract JSON arrays from LLM text (preamble, markdown fences, wrapped objects, etc.)."""

import json
import re


def _strip_think_blocks(s: str) -> str:
    """Strip reasoning blocks that precede JSON (Qwen / DeepSeek, etc.)."""
    # Escaped XML names — avoids editors rewriting angle-bracket tokens.
    pairs = (
        ("\u003cthink\u003e", "\u003c/redacted_thinking\u003e"),
        (
            "\u003c" + "redacted" + "_" + "thinking" + "\u003e",
            "\u003c/" + "redacted" + "_" + "thinking" + "\u003e",
        ),
    )
    for open_t, close_t in pairs:
        pat = re.escape(open_t) + r"[\s\S]*?" + re.escape(close_t)
        s = re.sub(pat, "", s, flags=re.DOTALL | re.IGNORECASE)
    return s.strip()


def parse_json_array_from_llm(raw: str | None) -> list:
    """
    Parse a JSON array from an LLM reply. Raises json.JSONDecodeError if none found.
    """
    if raw is None:
        raise json.JSONDecodeError("Empty LLM response", "", 0)
    s = raw.strip()
    if not s:
        raise json.JSONDecodeError("Empty LLM response", "", 0)

    s = s.lstrip("\ufeff")
    s = _strip_think_blocks(s)
    s = _strip_outer_markdown_fence(s)

    for candidate in _json_value_candidates(s):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        as_list = _coerce_parsed_to_list(parsed)
        if as_list is not None:
            return as_list

    raise json.JSONDecodeError("No JSON array found in LLM response", s, 0)


def _coerce_parsed_to_list(parsed) -> list | None:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return _array_from_wrapping_object(parsed)
    return None


def _array_from_wrapping_object(obj: dict) -> list | None:
    for key in (
        "findings",
        "results",
        "vulnerabilities",
        "data",
        "items",
        "issues",
        "steps",
        "kill_chain",
        "chain",
        "attack_chain",
    ):
        v = obj.get(key)
        if isinstance(v, list):
            return v
    for v in obj.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v
    for v in obj.values():
        if isinstance(v, dict):
            inner = _array_from_wrapping_object(v)
            if inner is not None:
                return inner
    return None


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


def _json_value_candidates(s: str):
    yield s
    for extractor in (_extract_balanced_json_array, _extract_balanced_json_object):
        extracted = extractor(s)
        if extracted:
            yield extracted
            inner = _strip_outer_markdown_fence(extracted.strip())
            if inner != extracted:
                yield inner


def _extract_balanced_json_array(s: str) -> str | None:
    return _extract_balanced(s, "[", "]")


def _extract_balanced_json_object(s: str) -> str | None:
    return _extract_balanced(s, "{", "}")


def _extract_balanced(s: str, open_ch: str, close_ch: str) -> str | None:
    start = s.find(open_ch)
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
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None
