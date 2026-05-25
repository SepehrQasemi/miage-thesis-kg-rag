from pathlib import Path

from pypdf import PdfReader

from extraction.ocr import ocr_pdf_page, page_needs_ocr, rapidocr_available
from extraction.text_utils import compact_whitespace


def read_pdf_text(pdf_path: Path, cover_pages: int = 3, enable_ocr: bool = True, ocr_pages_limit: int = 5) -> dict:
    reader = PdfReader(str(pdf_path))
    pages_text: list[str] = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            pages_text.append("")

    ocr_results = []
    ocr_notes = []
    if enable_ocr:
        if rapidocr_available():
            max_ocr_pages = min(len(pages_text), max(cover_pages, ocr_pages_limit))
            for page_index in range(max_ocr_pages):
                if not page_needs_ocr(pdf_path, page_index, pages_text[page_index]):
                    continue
                result = ocr_pdf_page(pdf_path, page_index)
                if not result or not result.text:
                    continue
                pages_text[page_index] = result.text
                ocr_results.append(
                    {
                        "page": page_index + 1,
                        "confidence": result.confidence,
                        "engine": result.engine,
                        "cached": result.cached,
                    }
                )
            if ocr_results:
                pages = ",".join(str(item["page"]) for item in ocr_results)
                ocr_notes.append(f"ocr_pages:{pages}")
        else:
            ocr_notes.append("ocr_unavailable")

    full_text = compact_whitespace("\n\n".join(pages_text))
    cover_text = compact_whitespace("\n\n".join(pages_text[:cover_pages]))
    return {
        "pages_count": len(reader.pages),
        "cover_text": cover_text,
        "full_text": full_text,
        "chars_total": len(full_text),
        "ocr_results": ocr_results,
        "ocr_notes": ocr_notes,
    }
