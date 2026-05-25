import re
import unicodedata


def compact_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_match(text: str) -> tuple[str, str]:
    """Return spaced and compact ASCII-normalized text for robust matching."""
    text = text.lower()
    # Join common LaTeX/PDF accent artifacts before ASCII normalization:
    # "d´ etection" -> "detection", "mod` eles" -> "modeles".
    text = re.sub(r"([a-z])\s*[´`ˆ^]\s*([a-z])", r"\1\2", text)
    replacements = {
        "m´ emoire": "memoire",
        "m´emoire": "memoire",
        "m´ emoires": "memoires",
        "r´ esum´ e": "resume",
        "r´ esume": "resume",
        "r´ esum e": "resume",
        "mots-cl´ es": "mots cles",
        "mots-clés": "mots cles",
        "d’accueil": "d accueil",
        "d' accueil": "d accueil",
        "d’ accueil": "d accueil",
        "d´ accueil": "d accueil",
        "pr´ esent": "present",
        "r´ ealis": "realis",
        "r´ealis": "realis",
        "m´ ethod": "method",
        "m´ethod": "method",
        "´": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    spaced = re.sub(r"\s+", " ", text).strip()
    compact = re.sub(r"\s+", "", spaced)
    return spaced, compact


def repair_display_text(text: str) -> str:
    """Make extracted PDF text more readable without relying on paid services."""
    text = re.sub(r"([A-Za-z])\s*[´`ˆ^]\s*([A-Za-z])", r"\1\2", text)
    text = text.replace("` a", "a").replace("`e", "e")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def has_phrase(text: str, phrase: str) -> bool:
    spaced, compact = normalize_for_match(text)
    phrase_spaced, phrase_compact = normalize_for_match(phrase)
    return phrase_spaced in spaced or phrase_compact in compact


def has_any(text: str, phrases: list[str]) -> bool:
    return any(has_phrase(text, phrase) for phrase in phrases)


def lines(text: str) -> list[str]:
    items = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in items if line]


def tokenize(text: str) -> list[str]:
    spaced, _ = normalize_for_match(text)
    return re.findall(r"[a-z][a-z0-9]{2,}", spaced)
