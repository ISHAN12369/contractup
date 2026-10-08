"""Extract only a JSON answer prefix for explicitly unverified live drafts."""

import json
import re


def answer_prefix(buffer: str) -> str:
    # Require answer to be the first property; never render reasoning or arbitrary JSON fields.
    match = re.match(r'^\s*\{\s*"answer"\s*:\s*"', buffer)
    if not match:
        return ""
    text = buffer[match.end():]
    end = 0
    while end < len(text):
        char = text[end]
        if char == '"':
            break
        if char == "\\":
            if end + 1 >= len(text):
                break
            count = 6 if text[end + 1] == "u" else 2
            if end + count > len(text):
                break
            end += count
        else:
            end += 1
    try:
        value = json.loads('"' + text[:end] + '"')
        return str(value)[:6000]
    except (ValueError, UnicodeError):
        return ""
