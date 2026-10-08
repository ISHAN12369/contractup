"""Heading-aware chunks with exact canonical/global and page character offsets."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings
from errors import InvalidDocument
from schemas import Chunk, PageText

HEADING = re.compile(
    r"(?im)^[ \t]*(?P<id>(?:ARTICLE\s+[IVXLC\d]+|SECTION\s+\d+(?:\.\d+)*|"
    r"\d{1,3}(?:\.\d+)*[.)]))(?:[ \t]+[^\n]{0,120})?\s*$"
)


def split_pages(pages: list[PageText], settings: Settings) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=150, add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[Chunk] = []
    section = "unsectioned"
    for page in pages:
        headings = list(HEADING.finditer(page.text)) if settings.chunking_strategy == "clause" else []
        starts = [0] + [match.start() for match in headings if match.start() != 0]
        identifiers = {match.start(): match.group("id").strip() for match in headings}
        for index, start in enumerate(starts):
            if start in identifiers:
                section = identifiers[start]
            end = starts[index + 1] if index + 1 < len(starts) else len(page.text)
            for document in splitter.create_documents([page.text[start:end]]):
                local = start + int(document.metadata["start_index"])
                text = document.page_content
                if local < start or page.text[local:local + len(text)] != text:
                    raise InvalidDocument("Could not preserve document source offsets.")
                chunks.append(Chunk(
                    id=f"c{len(chunks):05d}", text=text, page=page.page,
                    section_id=section, start=page.start + local, end=page.start + local + len(text),
                    page_start=local, page_end=local + len(text), ocr=page.ocr,
                ))
    if len(chunks) > settings.max_chunks:
        raise InvalidDocument("The document exceeds the configured chunk limit. Split it into smaller files.")
    if not chunks:
        raise InvalidDocument("No text could be indexed.")
    return chunks
