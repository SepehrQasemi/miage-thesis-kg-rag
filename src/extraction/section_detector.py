from dataclasses import dataclass
import re

from extraction.text_utils import normalize_for_match, repair_display_text


@dataclass
class Heading:
    kind: str
    start: int
    end: int


HEADING_KINDS = {
    "abstract": {"resume", "abstract", "summary"},
    "keywords": {"motscles", "motsclefs", "keywords", "keyword"},
    "introduction": {"introduction", "introductiongenerale"},
    "conclusion": {"conclusion", "conclusiongenerale"},
    "methodology": {
        "methodologie",
        "methodology",
        "methodes",
        "methodesutilisees",
        "approchemethodologique",
    },
    "toc": {"tabledesmatieres", "sommaire", "contents"},
    "references": {"bibliographie", "references"},
    "thanks": {"remerciements"},
}


def _heading_kind(line: str) -> str | None:
    if len(line.strip()) > 120:
        return None
    _, compact = normalize_for_match(line)
    compact = re.sub(r"^[0-9]+", "", compact)
    compact = re.sub(r"[0-9]+$", "", compact)
    for kind, names in HEADING_KINDS.items():
        if compact in names:
            return kind
    return None


def find_headings(text: str) -> list[Heading]:
    headings: list[Heading] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        kind = _heading_kind(line)
        if kind:
            headings.append(Heading(kind=kind, start=offset, end=offset + len(line)))
        offset += len(line)
    return headings


def _extract_after_heading(text: str, headings: list[Heading], kind: str, min_chars: int = 120) -> str:
    candidates = [heading for heading in headings if heading.kind == kind]
    stop_kinds = {"abstract", "keywords", "introduction", "conclusion", "methodology", "toc", "references", "thanks"}
    for candidate in candidates:
        stop = len(text)
        for next_heading in headings:
            if next_heading.start > candidate.end and next_heading.kind in stop_kinds:
                stop = next_heading.start
                break
        content = text[candidate.end:stop].strip()
        content = re.sub(r"\n{3,}", "\n\n", content)
        if len(content) >= min_chars:
            return repair_display_text(content)
    return ""


def extract_sections(full_text: str) -> dict:
    headings = find_headings(full_text)
    return {
        "abstract": _extract_after_heading(full_text, headings, "abstract", min_chars=120),
        "introduction": _extract_after_heading(full_text, headings, "introduction", min_chars=250),
        "conclusion": _extract_after_heading(full_text, headings, "conclusion", min_chars=200),
    }
