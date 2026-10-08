"""Bounded format validation and extraction; never trust a browser MIME type."""

import io
import zipfile
from pathlib import Path

from defusedxml import ElementTree
from pypdf import PdfReader

from chunking import split_pages
from config import Settings
from errors import InvalidDocument, ServiceError
from ocr import recognize_page
from schemas import Chunk, PageText

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


def extract_document(filename: str, content: bytes, settings: Settings) -> list[PageText]:
    ext = validate_upload(filename, content, settings)
    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 60:
                raise InvalidDocument("Encrypted PDFs or PDFs above 60 pages are unsupported.")
            pages: list[PageText] = []
            total = 0
            ocr_count = 0
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                extracted = PageText(page=number, text=text)
                if not text.strip():
                    ocr_count += 1
                    if ocr_count > settings.max_ocr_pages:
                        raise InvalidDocument("The document exceeds the configured OCR page limit.")
                    extracted = recognize_page(content, number, settings)
                    text = extracted.text
                total += len(text)
                if total > settings.max_text_chars:
                    raise InvalidDocument("Extracted text exceeds the configured character limit.")
                pages.append(extracted)
        elif ext == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                text = "\n".join(
                    "".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t"))
                    for paragraph in root.iter(f"{WORD_NS}p")
                )
            pages = [PageText(page=None, text=text)]
        else:
            pages = [PageText(page=None, text=content.decode("utf-8-sig"))]
    except ServiceError:
        raise
    except Exception as exc:
        raise InvalidDocument() from exc
    if sum(len(page.text) for page in pages) > settings.max_text_chars:
        raise InvalidDocument("Extracted text exceeds the configured character limit.")
    if not any(page.text.strip() for page in pages):
        raise InvalidDocument("No text was found, including by OCR. Try a clearer document.")
    offset = 0
    for extracted_page in pages:
        extracted_page.start = offset
        offset += len(extracted_page.text) + 2  # Canonical pages joined with two newline characters.
    return pages


def chunk_pages(pages: list[tuple[int | None, str]], settings: Settings) -> list[Chunk]:
    converted: list[PageText] = []
    offset = 0
    for page, text in pages:
        converted.append(PageText(page=page, text=text, start=offset))
        offset += len(text) + 2
    return split_pages(converted, settings)


def extract_pages(filename: str, content: bytes, settings: Settings) -> list[tuple[int | None, str]]:
    """Compatibility helper for integrations using Phase 0's text-only parser interface."""
    return [(page.page, page.text) for page in extract_document(filename, content, settings)]
