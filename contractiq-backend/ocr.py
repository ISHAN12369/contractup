"""Bounded local Tesseract OCR, invoked only for pages without extracted text."""

import math
import threading

from config import Settings
from errors import InvalidDocument, ServiceError
from schemas import OcrWord, PageText

PDFIUM_LOCK = threading.Lock()  # PDFium forbids simultaneous calls, even for different PDFs.


def recognize_page(content: bytes, number: int, settings: Settings) -> PageText:
    import pypdfium2 as pdfium
    import pytesseract

    if not settings.ocr_enabled:
        raise InvalidDocument("This page needs OCR. Enable OCR_ENABLED and install Tesseract.")
    try:
        with PDFIUM_LOCK, pdfium.PdfDocument(content) as document:
            page = document[number - 1]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                raise InvalidDocument("Invalid PDF page dimensions.")
            scale = min(2.0, math.sqrt(4_000_000 / (width * height)))
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                try:
                    data = pytesseract.image_to_data(
                        image, lang=settings.ocr_language, output_type=pytesseract.Output.DICT,
                        timeout=settings.ocr_timeout_seconds,
                    )
                    image_width, image_height = image.size
                finally:
                    image.close()
            finally:
                bitmap.close()
                page.close()
        text = ""
        words: list[OcrWord] = []
        previous_line: tuple[int, int, int] | None = None
        for index, raw in enumerate(data["text"]):
            word = str(raw).strip()
            if not word:
                continue
            line = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            if text:
                text += "\n" if line != previous_line else " "
            start = len(text)
            text += word
            if len(text) > settings.max_text_chars:
                raise InvalidDocument("OCR text exceeds the configured character limit.")
            left, top = data["left"][index], data["top"][index]
            words.append(OcrWord(start=start, end=len(text), box=(
                left / image_width, top / image_height,
                data["width"][index] / image_width, data["height"][index] / image_height,
            )))
            previous_line = line
        return PageText(page=number, text=text, ocr=True, words=words)
    except ServiceError:
        raise
    except pytesseract.TesseractNotFoundError as exc:
        raise ServiceError(503, "OCR needs the Tesseract executable on the server.") from exc
    except RuntimeError as exc:
        raise ServiceError(504, "OCR exceeded its time budget or failed. Try fewer pages.") from exc
    except Exception as exc:
        raise InvalidDocument("OCR could not read this PDF page safely.") from exc
