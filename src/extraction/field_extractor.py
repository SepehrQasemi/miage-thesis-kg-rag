import re
from datetime import datetime

from extraction.text_utils import has_any, lines, normalize_for_match, repair_display_text


CURRENT_YEAR = datetime.now().year


TITLE_STOP_MARKERS = [
    "entreprisedaccueil",
    "memoirerealise",
    "memoirepresente",
    "presenteenvue",
    "present",
    "soutenupar",
    "soutenuepar",
    "soutenuaparis",
    "realisepar",
    "universiteparisnanterre",
    "maitredapprentissage",
    "maitredestage",
    "souslasupervision",
    "jury",
    "tuteur",
    "tutrice",
    "anneeuniversitaire",
]

TITLE_BAD_MARKERS = [
    "remerciements",
    "remercie",
    "tabledesmatieres",
    "tabledesmatire",
    "sommaire",
    "bibliographie",
    "avantdedebuter",
    "famille",
    "collegues",
    "souslasupervision",
    "maitredapprentissage",
    "maitredestage",
    "tuteur",
    "tutrice",
    "soutenuaparis",
    "universiteparisnanterre",
    "memoirepresenteenvuedelobtention",
    "memoiredem1",
    "memoiredem2",
    "emoiredem1",
    "emoiredem2",
    "mastermiage",
    "systemesdinformationfiables",
]

TITLE_GENERIC_MARKERS = [
    "ufr",
    "scienceseconomiques",
    "gestionmathematiques",
    "universiteparisnanterre",
    "memoirede",
    "memoiremaster",
    "mastermiage",
    "systemesdinformationfiables",
    "m1miage",
    "m2miage",
    "rapportdestage",
    "parcoursclassique",
    "anneeuniversitaire",
    "maitredapprentissage",
    "maitredestage",
    "tutriceenseignante",
    "tuteurenseignant",
    "soutenu",
]


def extract_master_level(cover_text: str) -> str:
    if has_any(cover_text, ["memoire de m1", "master 1", "master m1", "m1 miage", "m1a", "1ere annee", "1re annee"]):
        return "M1"
    if has_any(cover_text, ["memoire de m2", "master 2", "master m2", "m2 miage", "m2a", "2eme annee", "2e annee", "2nde annee", "fin de cycle", "obtention du diplome de master"]):
        return "M2"
    return ""


def extract_track(cover_text: str) -> str:
    # Track must come from the program line, not from title phrases like
    # "apprentissage automatique".
    for line in lines(cover_text)[:12]:
        spaced, compact = normalize_for_match(line)
        if "mastermiage" in compact or "miage" in spaced:
            if "apprentissage" in spaced:
                return "apprentissage"
            if "mixte" in spaced:
                return "mixte"
    if has_any("\n".join(lines(cover_text)[:12]), ["apprentissage"]):
        return "apprentissage"
    if has_any("\n".join(lines(cover_text)[:12]), ["mixte"]):
        return "mixte"
    spaced, compact = normalize_for_match(cover_text)
    if "miageapp" in compact or "m2miageapp" in compact or "maitredapprentissage" in compact or "maitredapprentissage" in spaced:
        return "apprentissage"
    if "parcoursclassique" in compact:
        return "mixte"
    return ""


def extract_year(cover_text: str) -> int | None:
    # Prefer defense date such as "le 10 juin 2025".
    defense_matches = re.findall(
        r"\ble\s+\d{1,2}\s+[A-Za-z\u00c0-\u017f]+(?:\s+\d{1,2})?\s+(20[0-3][0-9])",
        cover_text,
        flags=re.IGNORECASE,
    )
    if defense_matches:
        return int(defense_matches[-1])

    # Academic year, e.g. 2021-2022.
    academic_matches = re.findall(r"(20[0-3][0-9])\s*[-/]\s*(20[0-3][0-9])", cover_text)
    if academic_matches:
        return int(academic_matches[-1][1])

    years = [int(year) for year in re.findall(r"\b(20[0-3][0-9])\b", cover_text)]
    years = [year for year in years if 2000 <= year <= CURRENT_YEAR + 1]
    return max(years) if years else None


def _is_program_marker(line: str) -> bool:
    spaced, compact = normalize_for_match(line)
    return any(
        marker in compact
        for marker in [
            "memoiredem1",
            "memoiredem2",
            "memoirederecherche",
            "memoiremaster",
            "mastermiage",
            "master1miage",
            "master2miage",
            "miageapprentissage",
        ]
    ) or ("memoire" in spaced and ("master" in spaced or "miage" in spaced))


def _is_stop_line(line: str) -> bool:
    _, compact = normalize_for_match(line)
    return any(marker in compact for marker in TITLE_STOP_MARKERS)


def _is_generic_title_line(line: str) -> bool:
    spaced, compact = normalize_for_match(line)
    if compact.isdigit() or len(spaced) < 4:
        return True
    return any(marker in compact for marker in TITLE_GENERIC_MARKERS)


def _looks_like_person_name(text: str) -> bool:
    words = [word for word in re.split(r"\s+", text.strip()) if word]
    if not 1 <= len(words) <= 4:
        return False
    spaced, compact = normalize_for_match(text)
    name_stopwords = {"de", "des", "du", "la", "le", "les", "pour", "avec", "contre", "dans", "et", "au", "aux"}
    if any(word in name_stopwords for word in spaced.split()):
        return False
    letters = re.sub(r"[^A-Za-z\u00c0-\u017f]", "", text)
    if not letters:
        return False
    uppercase = sum(1 for char in letters if char.isupper())
    return uppercase / len(letters) > 0.45 or all(word[:1].isupper() for word in words if word[:1].isalpha())


def _clean_title_candidate(parts: list[str]) -> str:
    title = " ".join(part.strip(" :-") for part in parts if part.strip(" :-"))
    title = _repair_glued_title_spacing(title)
    title = re.sub(r"\s+", " ", title).strip(" :-")
    return repair_display_text(title)


def _title_needs_next_line(parts: list[str]) -> bool:
    if not parts:
        return False
    words = re.findall(r"[A-Za-z\u00c0-\u017f']+", parts[-1].lower())
    return bool(words and words[-1] in {"de", "du", "des", "le", "la", "les", "pour", "avec", "dans", "sur", "et", "a", "à", "l"})


def _repair_glued_title_spacing(title: str) -> str:
    title = title.replace("\ufb01", "fi").replace("\ufb02", "fl")
    title = re.sub(r"(?<=[a-z\u00e0-\u017f])(?=[A-Z])", " ", title)
    replacements = [
        (r"Integrationde", "Integration de"),
        (r"Intégrationde", "Intégration de"),
        (r"Artificielledans", "Artificielle dans"),
        (r"dansl[’']", "dans l'"),
        (r"del'\s*", "de l'"),
        (r"dansles", "dans les"),
        (r"Processusde", "Processus de"),
        (r"Controlede", "Controle de"),
        (r"Contrôlede", "Contrôle de"),
        (r"Qualitedes", "Qualite des"),
        (r"Qualitédes", "Qualité des"),
        (r"desLogiciels", "des Logiciels"),
    ]
    for pattern, replacement in replacements:
        title = re.sub(pattern, replacement, title)
    return title


def is_valid_title(title: str) -> bool:
    title = _clean_title_candidate([title])
    if len(title) < 12 or len(title) > 260:
        return False
    if not re.search(r"[A-Za-z\u00c0-\u017f]", title):
        return False
    if re.search(r"\.{3,}", title):
        return False
    if _looks_like_person_name(title):
        return False
    words = re.findall(r"[A-Za-z\u00c0-\u017f']+", title.lower())
    if words and words[-1] in {"de", "du", "des", "le", "la", "les", "pour", "avec", "dans", "sur", "et", "a", "à", "l"}:
        return False
    spaced, compact = normalize_for_match(title)
    if any(marker in compact or marker in spaced for marker in TITLE_BAD_MARKERS):
        return False
    if compact.startswith("introduction") and any(marker in compact for marker in ["contexte", "objectif", "methodologie"]):
        return False
    if sum(char.isdigit() for char in title) > 12 and any(marker in compact for marker in ["partie", "chapitre", "introduction"]):
        return False
    return True


def _append_title_candidate(candidates: list[str], parts: list[str]) -> None:
    candidate = _clean_title_candidate(parts)
    if not is_valid_title(candidate):
        return
    if candidate not in candidates:
        candidates.append(candidate)


def _title_parts_after_marker(cover_lines: list[str], marker_index: int) -> list[str]:
    parts: list[str] = []
    marker_line = cover_lines[marker_index]
    _, marker_compact = normalize_for_match(marker_line)
    if "presenteenvue" in marker_compact or "obtention" in marker_compact:
        return []
    inline_title = _inline_title_after_master_miage(marker_line)
    if inline_title:
        return [inline_title]
    has_track_parenthesis = ")" in marker_line and any(track in marker_compact for track in ["apprentissage", "mixte"])
    if "mastermiage" in marker_compact and has_track_parenthesis:
        after_program = marker_line.split(")", 1)[1].strip()
        after_program = re.split(r"\bEntreprise\b|\bMemoire\b|\bM\W*emoire\b", after_program, maxsplit=1, flags=re.IGNORECASE)[0]
        if after_program and not _is_generic_title_line(after_program):
            parts.append(after_program)
            return parts
    if ":" in marker_line:
        after_colon = marker_line.split(":", 1)[1].strip()
        if after_colon and not _is_generic_title_line(after_colon):
            parts.append(after_colon)
    for line in cover_lines[marker_index + 1 : marker_index + 9]:
        if _is_stop_line(line) or _is_program_marker(line):
            break
        if _is_generic_title_line(line):
            if parts:
                break
            continue
        if parts and len(line.split()) == 1 and line[:1].islower() and not _title_needs_next_line(parts):
            break
        if _looks_like_person_name(line):
            if parts and (_title_needs_next_line(parts) or len(line.split()) == 1):
                parts.append(line)
                continue
            if parts:
                break
            continue
        parts.append(line)
        if len(parts) >= 6:
            break
    return parts


def _inline_title_after_master_miage(line: str) -> str:
    match = re.search(r"master\s+miage\b", line, flags=re.IGNORECASE)
    if not match:
        return ""
    remainder = line[match.end() :].strip(" :-,")
    if not remainder:
        return ""
    remainder = re.sub(r"^\([^)]*\)\s*", "", remainder)
    remainder = re.sub(r"^(mixte|apprentissage|classique)\b\s*", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"^rapport\s+de\s+stage\s+M[12]\s+MIAGE,?\s*", "", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"^parcours\s+\w+,?\s*", "", remainder, flags=re.IGNORECASE)
    remainder = re.split(
        r"\bEntreprise\b|\bM\W*emoire\s+r\W*ealis|\bStage\s+r\W*ealis|\bpresent\W*e\b|\bpr\W*esent\W*e\b",
        remainder,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return remainder.strip(" :-,")


def _title_parts_after_academic_year(cover_lines: list[str], marker_index: int) -> list[str]:
    parts: list[str] = []
    line = cover_lines[marker_index]
    # Some covers place the title on the same line immediately after the academic year.
    inline = re.split(r"20[0-3][0-9]\s*[-/]\s*20[0-3][0-9]", line, maxsplit=1)
    if len(inline) == 2 and inline[1].strip():
        candidate = re.split(r"\bR\W*ealis\W*e\b|\bUniversit", inline[1], maxsplit=1, flags=re.IGNORECASE)[0]
        if candidate.strip():
            return [candidate.strip()]
    for following in cover_lines[marker_index + 1 : marker_index + 8]:
        if _is_stop_line(following) or _is_program_marker(following):
            break
        if _is_generic_title_line(following):
            if parts:
                break
            continue
        if parts and len(following.split()) == 1 and following[:1].islower() and not _title_needs_next_line(parts):
            break
        if _looks_like_person_name(following):
            if parts and (_title_needs_next_line(parts) or len(following.split()) == 1):
                parts.append(following)
                continue
            if parts:
                break
            continue
        parts.append(following)
        if len(parts) >= 5:
            break
    return parts


def extract_title_candidates(cover_text: str) -> list[str]:
    cover_lines = lines(cover_text)
    candidates: list[str] = []

    for index, line in enumerate(cover_lines[:60]):
        if _is_program_marker(line):
            before: list[str] = []
            for previous in reversed(cover_lines[max(0, index - 6) : index]):
                if _is_stop_line(previous) or _is_program_marker(previous):
                    break
                if _is_generic_title_line(previous) or _looks_like_person_name(previous):
                    if before:
                        break
                    continue
                before.insert(0, previous)
            _append_title_candidate(candidates, before)
            _append_title_candidate(candidates, _title_parts_after_marker(cover_lines, index))
        _, compact = normalize_for_match(line)
        if "anneeuniversitaire" in compact:
            _append_title_candidate(candidates, _title_parts_after_academic_year(cover_lines, index))

    for index, line in enumerate(cover_lines[:60]):
        _, compact = normalize_for_match(line)
        if "realisepar" not in compact:
            continue

        before: list[str] = []
        for previous in reversed(cover_lines[max(0, index - 7) : index]):
            if _is_stop_line(previous) or _is_program_marker(previous):
                break
            if _is_generic_title_line(previous) or _looks_like_person_name(previous):
                if before:
                    break
                continue
            before.insert(0, previous)
        _append_title_candidate(candidates, before)

        after: list[str] = []
        for following in cover_lines[index + 1 : index + 9]:
            if _is_stop_line(following) or _is_program_marker(following):
                break
            if _is_generic_title_line(following) or _looks_like_person_name(following):
                if after:
                    break
                continue
            after.append(following)
            if len(after) >= 6:
                break
        _append_title_candidate(candidates, after)

    for index, line in enumerate(cover_lines[:10]):
        probes = [line]
        if index + 1 < len(cover_lines):
            probes.append(f"{line} {cover_lines[index + 1]}")
        for probe in probes:
            spaced, compact = normalize_for_match(probe)
            if "universiteparisnanterre" not in compact or "mastermiage" not in compact:
                continue
            match = re.search(r"Universit[e\u00e9]\s*Paris\s*Nanterre|Universit[e\u00e9]ParisNanterre", probe, flags=re.IGNORECASE)
            if not match:
                continue
            prefix = probe[: match.start()].strip()
            # Common OCR/PDF case: title is glued to the author, e.g. "...Logiciels NejmaSMATTIUniversite..."
            prefix = re.sub(r"\s*[A-Z\u00c0-\u017f][a-z\u00e0-\u017f]+[A-Z\u00c0-\u017f]{2,}\s*$", "", prefix).strip()
            _append_title_candidate(candidates, [prefix])

    return candidates


def extract_title(cover_text: str) -> str:
    candidates = extract_title_candidates(cover_text)
    return candidates[0] if candidates else ""


def _matches(spaced: str, compact: str, pattern: str) -> bool:
    pattern_spaced, pattern_compact = normalize_for_match(pattern)
    if " " in pattern_spaced:
        return pattern_compact in compact
    if len(pattern_spaced) <= 5:
        return re.search(rf"\b{re.escape(pattern_spaced)}\b", spaced) is not None
    return pattern_spaced in spaced or pattern_compact in compact


def _matches_any(spaced: str, compact: str, patterns: list[str]) -> bool:
    return any(_matches(spaced, compact, pattern) for pattern in patterns)


def classify_methodology(text: str) -> str:
    spaced, compact = normalize_for_match(text)
    checks = [
        ("revue de litterature / etat de l'art", ["revuesystematique", "etatdelart", "cartographie", "literaturereview", "survey"]),
        ("comparaison experimentale", ["comparaison", "comparative", "evaluation", "experimentation", "benchmark"]),
        ("etude de cas", ["etudedecas", "casdetude", "case study"]),
        ("experimentation machine learning", ["dataset", "entrainement", "classification", "prediction", "modele", "reseauxdeneurones", "deeplearning"]),
        ("conception et evaluation algorithmique", ["algorithme", "heuristique", "optimisation", "programmationlineaire", "metaheuristique"]),
        ("analyse de donnees", ["analysededonnees", "datamining", "businessintelligence", "tableaudebord"]),
    ]
    for label, patterns in checks:
        if _matches_any(spaced, compact, patterns):
            return label
    return ""


def classify_use_case(text: str) -> str:
    spaced, compact = normalize_for_match(text)
    checks = [
        ("cybersecurite / detection d'attaques", ["cybersecurite", "attaque", "securite", "ddos", "intrusion", "vulnerabilite", "promptinjection", "datapoisoning", "federatedlearning"]),
        ("informatique quantique / calcul", ["informatiquequantique", "quantique", "loidemore"]),
        ("sante / aide au diagnostic", ["sante", "medical", "cancer", "diabete", "alzheimer", "imagerie", "patient"]),
        ("detection de fraude / risque financier", ["fraude", "subprime", "transactionfrauduleuse", "cartebancaire"]),
        ("finance / marche crypto", ["bitcoin", "crypto", "cryptomonnaie", "marchecrypto"]),
        ("medias / detection de desinformation", ["fakenews", "faussesinformations"]),
        ("analyse de graphes / reseaux", ["traitementsdegraphe", "graphe", "graphes", "reseauxdeneurones"]),
        ("optimisation operationnelle", ["optimisation", "planification", "ordonnancement", "flux", "rendezvous", "usine", "placement3d", "modeleusine"]),
        ("gestion des donnees / data platform", ["datalake", "datawarehouse", "donneesnonstructurees", "metadata", "referentiel", "businessintelligence", "olap", "cubeolap", "reporting", "entrepotdedonnees"]),
        ("analyse client / commerce", ["client", "ecommerce", "achat", "satisfaction", "immobilier"]),
        ("developpement logiciel / devops", ["devops", "microservice", "testslogiciel", "architecturelogicielle", "documentation", "observabilite", "traces", "logs", "monitoring", "codesource", "algorithme", "algorithmes", "deploiement", "variabilitelogicielle", "lignesdeproduits"]),
        ("education / apprentissage", ["education", "apprentissage autodidacte", "etudiant"]),
        ("energie / environnement", ["energie", "energetique", "environnement", "inondation", "productionelectrique"]),
    ]
    for label, patterns in checks:
        if _matches_any(spaced, compact, patterns):
            return label
    return ""


def confidence_score(fields: dict) -> float:
    score = 0.0
    if fields.get("title"):
        score += 0.25
    if fields.get("year"):
        score += 0.15
    if fields.get("master_level"):
        score += 0.15
    if fields.get("track"):
        score += 0.05
    if fields.get("keywords"):
        score += 0.15
    if fields.get("methodology"):
        score += 0.10
    if fields.get("use_case"):
        score += 0.15
    return round(min(score, 1.0), 3)
