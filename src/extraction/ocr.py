from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

from common.paths import cache_dir
from extraction.text_utils import compact_whitespace


@dataclass
class OcrPageResult:
    page_index: int
    text: str
    confidence: float
    engine: str
    cached: bool = False


def rapidocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True
    except Exception:
        return False


def page_needs_ocr(pdf_path: Path, page_index: int, existing_text: str, min_text_chars: int = 40) -> bool:
    if len(compact_whitespace(existing_text)) >= min_text_chars:
        return False
    try:
        import fitz

        doc = fitz.open(pdf_path)
        page = doc.load_page(page_index)
        has_text = bool(page.get_text("text").strip())
        has_images = bool(page.get_images(full=True))
        doc.close()
        return not has_text and has_images
    except Exception:
        return False


def render_page_image(pdf_path: Path, page_index: int, zoom: float = 2.2) -> Path:
    import fitz

    out_dir = cache_dir() / "ocr_pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / f"{pdf_path.stem}_page_{page_index + 1:03d}.png"
    if image_path.exists():
        return image_path

    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(image_path)
    doc.close()
    return image_path


def _cache_path(pdf_path: Path, page_index: int) -> Path:
    out_dir = cache_dir() / "ocr_text"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{pdf_path.stem}_page_{page_index + 1:03d}.json"


def _clean_ocr_text(text: str) -> str:
    replacements = [
        (r"\bMlAGE\b", "MIAGE"),
        (r"\bMiAGE\b", "MIAGE"),
        (r"\bUniversite\b", "Université"),
        (r"\bMemoire\b", "Mémoire"),
        (r"\bRealisepar\b", "Réalisé par "),
        (r"\bRealise par\b", "Réalisé par"),
        (r"\bMaitre\b", "Maître"),
        (r"\bI(?=')", "l"),
        (r"\bBl\b", "BI"),
        (r"\ba I'aide\b", "à l'aide"),
        (r"\ba l'aide\b", "à l'aide"),
        (r"\bgenération\b", "génération"),
        (r"\bgeneration\b", "génération"),
        (r"\bmodele\b", "modèle"),
        (r"\bautomatisee\b", "automatisée"),
        (r"\borientee\b", "orientée"),
        (r"\balgorithmesévolutionnaires\b", "algorithmes évolutionnaires"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("UniversitéParis", "Université Paris")
    text = text.replace("ParisNanterre", "Paris Nanterre")
    text = text.replace("anneeMaster", "annee Master")
    return compact_whitespace(text)


def _serialize_result(result: OcrPageResult) -> dict[str, Any]:
    return {
        "page_index": result.page_index,
        "text": result.text,
        "confidence": result.confidence,
        "engine": result.engine,
    }


def ocr_pdf_page(pdf_path: Path, page_index: int, use_cache: bool = True) -> OcrPageResult | None:
    cache_path = _cache_path(pdf_path, page_index)
    if use_cache and cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return OcrPageResult(
            page_index=page_index,
            text=data.get("text", ""),
            confidence=float(data.get("confidence") or 0),
            engine=data.get("engine", "rapidocr-onnxruntime"),
            cached=True,
        )

    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None

    image_path = render_page_image(pdf_path, page_index)
    engine = RapidOCR()
    raw_result, _ = engine(str(image_path))
    if not raw_result:
        return None

    lines: list[str] = []
    scores: list[float] = []
    for item in raw_result:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        lines.append(text)
        try:
            scores.append(float(item[2]))
        except (TypeError, ValueError):
            pass

    text = _clean_ocr_text("\n".join(lines))
    confidence = round(sum(scores) / len(scores), 3) if scores else 0.0
    result = OcrPageResult(
        page_index=page_index,
        text=text,
        confidence=confidence,
        engine="rapidocr-onnxruntime",
    )
    cache_path.write_text(json.dumps(_serialize_result(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
