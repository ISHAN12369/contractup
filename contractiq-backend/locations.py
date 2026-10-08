"""Character offsets always index canonical extracted text, not PDF byte offsets."""

from audit_schemas import Location
from schemas import Chunk


def normalized_map(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    indices: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                indices.append(index)
        else:
            for folded in char.casefold():
                chars.append(folded)
                indices.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        indices.pop()
    return "".join(chars), indices


def quote_span(text: str, quote: str) -> tuple[int, int] | None:
    normalized, indices = normalized_map(text)
    needle, _ = normalized_map(quote)
    if not needle:
        return None
    index = normalized.find(needle)
    if index < 0:
        return None
    return indices[index], indices[index + len(needle) - 1] + 1


def locate(chunk: Chunk, quote: str) -> Location | None:
    span = quote_span(chunk.text, quote)
    if span is None:
        return None
    start, end = span
    return Location(
        chunk_id=chunk.id, page=chunk.page, section_id=chunk.section_id,
        start=chunk.start + start, end=chunk.start + end,
        page_start=chunk.page_start + start, page_end=chunk.page_start + end, ocr=chunk.ocr,
    )
