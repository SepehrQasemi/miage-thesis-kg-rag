from collections import Counter, defaultdict
import math
import re

from extraction.text_utils import normalize_for_match, tokenize


STOPWORDS = {
    "les", "des", "une", "un", "dans", "pour", "avec", "sur", "par", "aux", "est", "sont", "etre",
    "cette", "cet", "ces", "qui", "que", "dont", "leur", "leurs", "plus", "nous", "vous", "notre",
    "votre", "elle", "ils", "elles", "afin", "ainsi", "comme", "entre", "sans", "vers", "mise",
    "place", "cadre", "memoire", "master", "miage", "apprentissage", "mixte", "entreprise",
    "accueil", "realise", "presente", "soutenu", "soutenue", "universite", "paris", "nanterre",
    "annee", "universitaire", "jury", "soutenance", "responsable", "professeur", "maitre",
    "tuteur", "tutrice", "enseignant", "enseignante", "remerciements", "merci", "monsieur",
    "madame", "collègues", "collegues", "famille", "amis", "figure", "tableau", "page",
    "chapitre", "partie", "section", "introduction", "conclusion", "contexte", "problematique",
    "methodologie", "mots", "cles", "systemes", "information", "informations", "fiables",
    "intelligence", "donnees", "afia", "cfa", "logo",
    "this", "that", "with", "from", "into", "using", "used", "such", "their", "these", "those",
    "study", "thesis", "paper", "work", "method", "methods", "approach",
}

BAD_KEYWORD_TOKENS = {
    "remerciements", "merci", "tuteur", "tutrice", "enseignant", "enseignante", "maitre",
    "jury", "soutenance", "responsable", "professeur", "universite", "paris", "nanterre",
    "afia", "cfa", "logo", "figure", "tableau", "page", "chapitre", "introduction",
    "conclusion", "bibliographie", "webographie", "sitographie",
}

BAD_KEYWORD_COMPACT_FRAGMENTS = {
    "nanterre",
    "systemesdinformations",
    "dinformationsfiables",
    "fiablesintelligence",
    "integrationdel",
    "objectifsdumemoire",
    "contextegeneral",
}


CONCEPT_SYNONYMS = {
    "ia": "intelligence artificielle",
    "intelligence artificielle": "intelligence artificielle",
    "artificial intelligence": "intelligence artificielle",
    "machine learning": "machine learning",
    "apprentissage automatique": "machine learning",
    "deep learning": "deep learning",
    "llm": "large language models",
    "large language model": "large language models",
    "modele de langage": "large language models",
    "gpt": "large language models",
    "cybersecurite": "cybersecurite",
    "securite": "cybersecurite",
    "rbac": "cybersecurite",
    "data poisoning": "cybersecurite",
    "blockchain": "blockchain",
    "ethereum": "blockchain",
    "business intelligence": "business intelligence",
    "olap": "business intelligence",
    "reporting": "business intelligence",
    "data lake": "data lake",
    "datalake": "data lake",
    "data warehouse": "data warehouse",
    "cloud": "cloud computing",
    "devops": "devops",
    "mlops": "mlops",
    "process mining": "process mining",
    "optimisation": "optimisation",
    "algorithme genetique": "algorithme genetique",
    "genetic algorithm": "algorithme genetique",
    "classification": "classification",
    "prediction": "prediction",
    "detection": "detection",
    "process mining": "process mining",
    "graph": "graphes",
    "graphe": "graphes",
    "graphes": "graphes",
    "quantique": "informatique quantique",
    "informatique quantique": "informatique quantique",
    "nlp": "traitement du langage naturel",
    "traitement du langage naturel": "traitement du langage naturel",
    "natural language processing": "traitement du langage naturel",
    "sentiment": "analyse de sentiments",
    "analyse des sentiments": "analyse de sentiments",
    "fake news": "detection de desinformation",
    "fausses informations": "detection de desinformation",
    "sante": "sante",
    "finance": "finance",
    "bitcoin": "finance",
    "crypto": "finance",
    "energie": "energie",
}


def _valid_term(term: str) -> bool:
    spaced, compact = normalize_for_match(term)
    if len(compact) < 4 or len(compact) > 80:
        return False
    tokens = spaced.split()
    if not tokens:
        return False
    if any(token in BAD_KEYWORD_TOKENS for token in tokens):
        return False
    if any(fragment in compact for fragment in BAD_KEYWORD_COMPACT_FRAGMENTS):
        return False
    if any(token.startswith(("http", "www")) for token in tokens):
        return False
    if sum(char.isdigit() for char in term) > 4:
        return False
    if len(tokens) >= 3 and all(len(token) <= 3 for token in tokens):
        return False
    return True


def _candidate_terms(text: str) -> Counter:
    tokens = [token for token in tokenize(text) if token not in STOPWORDS and len(token) >= 3]
    counts: Counter = Counter()
    for n in (1, 2, 3):
        for i in range(0, max(0, len(tokens) - n + 1)):
            term_tokens = tokens[i : i + n]
            if any(token in STOPWORDS for token in term_tokens):
                continue
            term = " ".join(term_tokens)
            if _valid_term(term):
                counts[term] += 1
    return counts


def _matched_controlled_terms(text: str) -> list[str]:
    spaced, compact = normalize_for_match(text)
    terms = []
    for synonym, canonical in CONCEPT_SYNONYMS.items():
        synonym_spaced, synonym_compact = normalize_for_match(synonym)
        if " " in synonym_spaced:
            matched = synonym_compact in compact
        elif len(synonym_spaced) <= 5:
            matched = re.search(rf"\b{re.escape(synonym_spaced)}\b", spaced) is not None
        else:
            matched = synonym_spaced in spaced or synonym_compact in compact
        if matched and canonical not in terms:
            terms.append(canonical)
    return terms


def extract_keywords_for_corpus(doc_texts: dict[str, str], limit: int = 10) -> dict[str, list[str]]:
    term_counts_by_doc = {doc_id: _candidate_terms(text) for doc_id, text in doc_texts.items()}
    doc_freq: defaultdict[str, int] = defaultdict(int)
    for counts in term_counts_by_doc.values():
        for term in counts:
            doc_freq[term] += 1

    total_docs = max(1, len(doc_texts))
    result: dict[str, list[str]] = {}
    for doc_id, counts in term_counts_by_doc.items():
        controlled_terms = _matched_controlled_terms(doc_texts.get(doc_id, ""))
        scored = []
        for term, tf in counts.items():
            # Prefer phrases a little, but keep frequent single technical terms.
            phrase_bonus = 1.0 + 0.25 * (len(term.split()) - 1)
            idf = math.log((total_docs + 1) / (doc_freq[term] + 1)) + 1.0
            scored.append((tf * idf * phrase_bonus, term))
        scored.sort(reverse=True)
        keywords = []
        for term in controlled_terms:
            if _valid_term(term):
                keywords.append(term)
            if len(keywords) >= limit:
                break
        for _, term in scored:
            if any(term in existing or existing in term for existing in keywords):
                continue
            keywords.append(term)
            if len(keywords) >= limit:
                break
        result[doc_id] = keywords
    return result


def normalize_concepts(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    concepts = _matched_controlled_terms(" ".join([text] + keywords))
    if concepts:
        return concepts[:limit]
    return [keyword for keyword in keywords if len(keyword.split()) <= 3 and _valid_term(keyword)][:limit]
