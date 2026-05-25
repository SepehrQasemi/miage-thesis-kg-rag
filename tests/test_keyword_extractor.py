from nlp.keyword_extractor import extract_keywords_for_corpus, normalize_concepts


def test_keywords_prioritize_controlled_terms_and_filter_template_noise():
    text = """
    Remerciements Universite Paris Nanterre Tuteur Enseignant.
    Ce memoire porte sur un data warehouse, OLAP, business intelligence et reporting.
    La proposition ameliore l'analyse de donnees dans des cubes OLAP.
    """

    keywords = extract_keywords_for_corpus({"doc": text}, limit=8)["doc"]

    assert "business intelligence" in keywords
    assert "data warehouse" in keywords
    assert "universite" not in keywords
    assert not any("tuteur" in keyword for keyword in keywords)


def test_concepts_use_controlled_vocabulary():
    text = "Detection de fake news avec BERT et SVM pour limiter la desinformation."
    concepts = normalize_concepts(text, [], limit=5)

    assert "detection de desinformation" in concepts


def test_des_informations_does_not_create_desinformation_concept():
    text = "Un data warehouse contient des informations clients et des cubes OLAP."
    concepts = normalize_concepts(text, [], limit=5)

    assert "detection de desinformation" not in concepts
    assert "business intelligence" in concepts
