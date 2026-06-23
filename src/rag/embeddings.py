from __future__ import annotations

from collections import Counter
import hashlib
import math
import re
import unicodedata
from typing import Any

from nlp.keyword_extractor import CONCEPT_SYNONYMS, STOPWORDS


DEFAULT_EMBEDDING_MODEL = "local-hash-v1"
DEFAULT_DIMENSIONS = 384

QUERY_ALIASES = {
    "airport": ["aeroport", "aeroports", "flux au sol"],
    "ground flow": ["flux au sol", "trafic au sol", "flux aeroport", "trafic aeroportuaire"],
    "supplier": ["fournisseur", "fournisseurs", "selection de fournisseurs"],
    "supplier selection": ["selection de fournisseurs", "selection fournisseurs"],
    "multi criteria": ["multicritere", "multicriteres", "optimisation multicriteres"],
    "multicriteria": ["multicritere", "multicriteres", "optimisation multicriteres"],
    "iot": ["iot", "io t", "objets connectes", "internet des objets"],
    "stream": ["flux", "flux de donnees", "streaming", "temps reel"],
    "real time": ["temps reel", "temps reela", "flux de donnees"],
    "ddos": ["ddos", "deni de service", "attaques par deni de service"],
    "rnn": ["reseaux neuronaux recurrents", "recurrent neural networks"],
    "ensemble methods": ["methodes d ensemble", "methodes ensemble", "random forest", "xgboost"],
    "insurance": ["assurance", "fraude assurance", "fraude a l assurance"],
    "credit card": ["carte bancaire", "carte de credit", "credit card"],
    "imbalanced data": ["donnees desequilibrees", "desequilibre classes", "donnees fortement nonbalancees"],
    "compares techniques": ["comparaison de techniques", "comparaison techniques", "approche hybride"],
    "plagiarism": ["plagiat", "detection de plagiat", "detecter le plagiat"],
    "c code": ["code c", "langage c", "plagiat de code c"],
    "connected vehicles": ["vehicules connectes", "vehicule connecte", "failles de securite vehicules connectes"],
    "vehicle": ["vehicule", "vehicules"],
    "transfer learning": ["transfer learning", "apprentissage par transfert"],
    "sign language": ["langage des signes", "reconnaissance du langage des signes"],
    "movie": ["film", "films", "cinema", "cinematographique", "recommandation de films"],
    "movie recommendation": ["recommandation de films", "systeme de recommandation de films"],
    "recommendation": ["recommandation", "systeme de recommandation"],
    "green machine learning": ["green machine learning", "green ml", "efficacite energetique", "state of the art and new trends"],
    "green": [
        "energie",
        "energetique",
        "energetiquement",
        "efficacite energetique",
        "durabilite",
        "environnement",
        "environnemental",
        "impact environnemental",
    ],
    "sustainability": ["durabilite", "logiciels durables", "efficacite energetique"],
    "moore": ["moore", "loi de moore"],
    "quantum": ["quantique", "informatique quantique"],
    "diabetes": ["diabete", "prediction du diabete", "detection du diabete"],
    "federated learning": ["apprentissage federe", "federated learning", "systeme d apprentissage federe"],
    "non iid": ["non-iid", "non iid", "heterogenes", "donnees non iid", "donnees non identiquement distribue"],
    "microservices": ["micro services", "microservices"],
    "microservice": ["micro service", "microservice"],
    "deployment": ["deploiement", "deploiement automatique", "generation et deploiement"],
    "automatic deployment": ["deploiement automatique", "generation et deploiement automatique"],
    "quality control": ["controle qualite", "controle de qualite", "controle qualite logiciels"],
    "software quality": ["qualite logiciels", "qualite des logiciels", "controle qualite logiciels"],
    "software quality control": ["controle qualite logiciels", "processus controle qualite"],
    "processes": ["processus"],
    "variable selection": ["selection de variables", "selection variables"],
    "hyperparameter": ["hyperparametre", "hyperparametres", "optimisation des hyperparametres"],
    "hyperparameters": ["hyperparametres", "optimisation des hyperparametres"],
    "breast cancer": ["cancer du sein", "classification cancer du sein", "detection precoce du cancer du sein"],
    "mammography": ["mammographie", "mammographies"],
    "vision language models": ["vision language models", "modeles vision langage", "modeles de vision langage", "vlm"],
    "phishing": ["hameconnage", "phishing"],
    "prompt attacks": ["attaques prompt", "attaques par prompt", "prompt injection"],
    "vulnerabilities": ["vulnerabilites", "failles", "securite"],
    "llm security": ["securite des llm", "vulnerabilites llm", "large language models cybersecurite"],
    "generative ai": ["ia generatives", "iag", "intelligence artificielle generative", "large language models"],
    "software development": ["developpement logiciel", "projets de developpement", "generation code", "correction bugs"],
    "rbac": ["rbac", "role based access control", "controle d acces base sur les roles"],
    "privilege escalation": ["escalade de privileges", "elevation de privileges", "privilege escalation"],
    "fraud": ["fraude", "detection de fraude", "fraud detection", "risque financier"],
    "cybersecurity": ["cybersecurite", "securite", "detection d'attaques", "intrusion"],
    "security": ["cybersecurite", "securite"],
    "health": ["sante", "medical", "diagnostic", "imagerie medicale"],
    "medical": ["sante", "diagnostic", "imagerie medicale"],
    "fake news": ["fausses informations", "detection de desinformation"],
    "misinformation": ["fausses informations", "detection de desinformation"],
    "graph": ["graphe", "graphes", "analyse de graphes"],
    "scheduling": ["planification", "ordonnancement"],
    "forecasting": ["prediction", "prevision"],
    "customer": ["client", "satisfaction client", "commerce"],
    "database": ["base de donnees", "data warehouse", "data lake"],
    "software": ["developpement logiciel", "devops", "architecture logicielle", "logiciel", "logiciels", "qualite logiciels"],
    "anomaly detection": ["detection anomalies", "detection d anomalies", "detection d anomalie"],
    "blockchain": ["blockchain", "ethereum", "transactions blockchain", "consensus"],
    "scalper bots": ["scalper bots", "anti bots", "e commerce"],
    "energy": ["energie", "environnement", "durabilite", "efficacite energetique", "green machine learning"],
    "finance": ["finance", "marche crypto", "risque financier"],
    "ai": ["intelligence artificielle", "ia", "artificial intelligence"],
}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("'", " ").replace("’", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def semantic_expansions(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = normalized.split()
    compact_windows = {
        "".join(tokens[index:index + size])
        for size in (1, 2, 3)
        for index in range(0, max(0, len(tokens) - size + 1))
    }
    expansions: list[str] = []
    for source, canonical in CONCEPT_SYNONYMS.items():
        source_norm = normalize_text(source)
        if not source_norm:
            continue
        source_compact = source_norm.replace(" ", "")
        if (
            (source_norm in tokens if " " not in source_norm else source_norm in normalized)
            or source_compact in compact_windows
        ):
            for item in [canonical, source]:
                if item not in expansions:
                    expansions.append(item)
    for source, aliases in QUERY_ALIASES.items():
        source_norm = normalize_text(source)
        source_compact = source_norm.replace(" ", "")
        if source_norm and (
            (source_norm in tokens if " " not in source_norm else source_norm in normalized)
            or source_compact in compact_windows
        ):
            for item in aliases:
                if item not in expansions:
                    expansions.append(item)
    return expansions


def split_terms(value: Any) -> list[str]:
    terms = []
    for item in re.split(r"[;\n,]+", str(value or "")):
        item = item.strip()
        if item and item not in terms:
            terms.append(item)
    return terms


def weighted_sections(row: dict[str, Any]) -> list[tuple[str, float]]:
    return [
        (f"title {row.get('title', '')}", 4.0),
        (f"concepts {' '.join(split_terms(row.get('concepts')))}", 4.0),
        (f"keywords {' '.join(split_terms(row.get('keywords')))}", 3.0),
        (f"use case {row.get('use_case', '')}", 3.0),
        (f"methodology {row.get('methodology', '')}", 2.0),
        (f"year {row.get('year', '')}", 0.6),
        (f"master level {row.get('master_level', '')}", 0.6),
        (f"track {row.get('track', '')}", 0.6),
        (f"abstract {row.get('abstract', '')}", 1.2),
        (f"introduction {row.get('introduction', '')}", 0.8),
        (f"conclusion {row.get('conclusion', '')}", 0.8),
    ]


def build_embedding_text(row: dict[str, Any]) -> str:
    parts = []
    for text, _weight in weighted_sections(row):
        if str(text).strip():
            parts.append(text)
    expansions = semantic_expansions(" ".join(parts))
    if expansions:
        parts.append("semantic aliases " + " ".join(expansions))
    return "\n".join(parts)


def feature_counts(text: str, weight: float = 1.0) -> Counter[str]:
    normalized = normalize_text(text)
    tokens = [
        token
        for token in normalized.split()
        if len(token) >= 2 and token not in STOPWORDS
    ]
    counts: Counter[str] = Counter()
    for token in tokens:
        counts[f"tok:{token}"] += weight
    for n in (2, 3):
        for index in range(0, max(0, len(tokens) - n + 1)):
            counts[f"ng{n}:{' '.join(tokens[index:index + n])}"] += weight * (1.2 if n == 2 else 1.35)
    for token in tokens:
        if len(token) >= 5:
            for index in range(0, len(token) - 3):
                counts[f"ch:{token[index:index + 4]}"] += weight * 0.3
    for expansion in semantic_expansions(text):
        expansion_norm = normalize_text(expansion)
        if expansion_norm:
            counts[f"alias:{expansion_norm}"] += weight * 2.0
    return counts


def row_feature_counts(row: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text, weight in weighted_sections(row):
        counts.update(feature_counts(text, weight=weight))
    embedding_text = build_embedding_text(row)
    for expansion in semantic_expansions(embedding_text):
        counts.update(feature_counts(expansion, weight=2.0))
    return counts


def vector_from_features(features: Counter[str], dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for feature, value in features.items():
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        bucket = raw % dimensions
        sign = 1.0 if (raw >> 8) & 1 else -1.0
        vector[bucket] += sign * float(value)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def embed_text(text: str, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    expanded = " ".join([text] + semantic_expansions(text))
    return vector_from_features(feature_counts(expanded, weight=1.0), dimensions=dimensions)


def embed_document(row: dict[str, Any], dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    return vector_from_features(row_feature_counts(row), dimensions=dimensions)


def embedding_hash(text: str, model: str, dimensions: int) -> str:
    payload = f"{model}|{dimensions}|{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
