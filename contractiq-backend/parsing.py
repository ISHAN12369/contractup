"""Bounded format validation and extraction; never trust a browser MIME type."""

import io
import zipfile
from pathlib import Path

from defusedxml import ElementTree
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from config import Settings
from errors import InvalidDocument, ServiceError
from schemas import Chunk

MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def validate_upload(filename: str, content: bytes, settings: Settings) -> str:
    ext = Path(filename).suffix.lower()
    if len(content) > settings.max_upload_bytes:
        raise ServiceError(413, "File exceeds the configured upload limit.")
    if not content:
        raise InvalidDocument("The file is empty.")
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise InvalidDocument("The file does not have a PDF signature.")
    elif ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise InvalidDocument("The file does not have a DOCX signature.")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                names = [item.filename for item in entries]
                if len(names) != len(set(names)):
                    raise InvalidDocument()
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    raise InvalidDocument("The archive is not a Word document.")
                if len(entries) > MAX_ARCHIVE_ENTRIES or sum(
                    entry.file_size for entry in entries
                ) > MAX_ARCHIVE_BYTES:
                    raise InvalidDocument("The DOCX archive expands beyond the safety limit.")
                for entry in entries:
                    if entry.flag_bits & 1 or entry.file_size > max(entry.compress_size, 1) * 200:
                        raise InvalidDocument("Encrypted or excessively compressed DOCX is unsupported.")
                    # Reading with a cap validates declared sizes/CRC before downstream parsing.
                    with archive.open(entry) as stream:
                        if len(stream.read(MAX_ARCHIVE_BYTES + 1)) > MAX_ARCHIVE_BYTES:
                            raise InvalidDocument()
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
            raise InvalidDocument() from exc
    elif ext in {".txt", ".md"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidDocument("Text files must use UTF-8 encoding.") from exc
        if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
            raise InvalidDocument("The text file contains binary control bytes.")
        if content.startswith((b"%PDF-", b"PK\x03\x04", b"MZ", b"\x7fELF")):
            raise InvalidDocument("File contents do not match the text extension.")
    else:
        raise ServiceError(415, "Unsupported file type. Use PDF, DOCX, TXT, or MD.")
    return ext


def extract_pages(filename: str, content: bytes, settings: Settings) -> list[tuple[int | None, str]]:
    ext = validate_upload(filename, content, settings)
    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 60:
                raise InvalidDocument("Encrypted PDFs or PDFs above 60 pages are unsupported.")
            pages: list[tuple[int | None, str]] = []
            total = 0
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                total += len(text)
                if total > settings.max_text_chars:
                    raise InvalidDocument("Extracted text exceeds the configured character limit.")
                pages.append((number, text))
        elif ext == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                text = "\n".join(
                    "".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t"))
                    for paragraph in root.iter(f"{WORD_NS}p")
                )
            pages = [(None, text)]
        else:
            pages = [(None, content.decode("utf-8-sig"))]
    except ServiceError:
        raise
    except Exception as exc:
        raise InvalidDocument() from exc
    if sum(len(text) for _, text in pages) > settings.max_text_chars:
        raise InvalidDocument("Extracted text exceeds the configured character limit.")
    if not any(text.strip() for _, text in pages):
        raise InvalidDocument("No extractable text found. Scanned PDFs need OCR, which is not available yet.")
    return pages


def chunk_pages(pages: list[tuple[int | None, str]], settings: Settings) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=150, separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = [
        Chunk(id=f"c{index:05d}", text=text, page=page)
        for index, (page, text) in enumerate(
            (page, text) for page, full in pages for text in splitter.split_text(full)
        )
    ]
    if len(chunks) > settings.max_chunks:
        raise InvalidDocument("The document exceeds the configured chunk limit. Split it into smaller files.")
    return chunks
