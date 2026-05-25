from extraction.field_extractor import classify_use_case, extract_master_level, extract_title, extract_track, is_valid_title


def test_extract_title_before_realise_par():
    cover_text = """
Processus de verification de la qualite des
donnees au sein d'une persistance
polyglotte.

Realise par :
Sylia RAHMANI

Memoire presente en vue de l'obtention du MASTER MIAGE
"""

    assert extract_title(cover_text) == (
        "Processus de verification de la qualite des donnees au sein d'une persistance polyglotte."
    )


def test_extract_title_after_realise_par():
    cover_text = """
Maitre d'apprentissage :
Frederic Chauvet
Tutrice Enseignante :
Marie-Pierre Gervais

Realise par Assane Sakho
La protection des systemes RBAC contre
l'elevation des privileges
Universite Paris Nanterre
Memoire de 2eme annee
Master MIAGE
"""

    assert extract_title(cover_text) == "La protection des systemes RBAC contre l'elevation des privileges"


def test_extract_title_after_memoire_master_marker():
    cover_text = """
Universite Paris Nanterre

Memoire MASTER M2 :
Exploration de voisinage
pour la selection de
variables, pour la prevision
des couts

Annee Universitaire 2023-2024
"""

    assert extract_title(cover_text) == (
        "Exploration de voisinage pour la selection de variables, pour la prevision des couts"
    )


def test_extract_title_before_memoire_master_marker():
    cover_text = """
Les reseaux de capteurs sans fil en environnement industriel
Memoire de Master 2 MIAGE
ASSEM AOUSSAR
Tuteur Enseignant : Reda Bendraou
"""

    assert extract_title(cover_text) == "Les reseaux de capteurs sans fil en environnement industriel"


def test_extract_title_same_line_after_miage_track():
    cover_text = """
Memoire de M1 Master MIAGE (apprentissage) Gestion des Fuites de Donnees dans l'Application Collector+ : Approche Axee sur la mise en place d'un puit de donnees Entreprise d'accueil : SNCF Voyageurs
"""

    assert extract_title(cover_text) == (
        "Gestion des Fuites de Donnees dans l'Application Collector+ : Approche Axee sur la mise en place d'un puit de donnees"
    )


def test_extract_title_same_line_after_master_miage_mixte():
    cover_text = """
Memoire de M1 Master MIAGE Mixte Etat de l'art : Analyse des outils et algorithmes pour la prediction de parties dans le jeu League of Legends presente et soutenu par Ronan BESNARD
"""

    assert extract_title(cover_text) == (
        "Etat de l'art : Analyse des outils et algorithmes pour la prediction de parties dans le jeu League of Legends"
    )


def test_extract_title_same_line_without_track_parenthesis():
    cover_text = """
Memoire de M1 Master MIAGE Conception d'un algorithme d'approximation pour le probleme du vertex cover utilisant l'apprentissage machine comme heuristique Entreprise d'accueil : Agence Nationale de la Recherche
"""

    assert extract_title(cover_text) == (
        "Conception d'un algorithme d'approximation pour le probleme du vertex cover utilisant l'apprentissage machine comme heuristique"
    )


def test_extract_title_after_academic_year():
    cover_text = """
Realise par Nassim Medjnoun
Memoire de 2eme annee
Master MIAGE
Annee Universitaire 2021-2022
Optimisation multicriteres appliquee a un probleme
de selection de fournisseurs
Universite Paris Nanterre
"""

    assert extract_title(cover_text) == (
        "Optimisation multicriteres appliquee a un probleme de selection de fournisseurs"
    )


def test_extract_title_after_stage_report_prefix():
    cover_text = """
MASTER MIAGE Rapport de stage M2 MIAGE, parcours classique Algorithmes de Clustering et leur application dans les TCG Entreprise d'accueil : CAP GEMINI
"""

    assert extract_title(cover_text) == "Algorithmes de Clustering et leur application dans les TCG"


def test_title_skips_program_speciality_line():
    cover_text = """
Master MIAGE
« Systemes d'information fiables et intelligence des donnees »
Memoire de 2eme annee Master 2 MIAGE APP
A la recherche du graphe de Conway : comparaison et evaluation de trois algorithmes.
presente et soutenu par Noufeine AHMED
"""

    assert extract_title(cover_text) == (
        "A la recherche du graphe de Conway : comparaison et evaluation de trois algorithmes."
    )


def test_title_stops_before_lowercase_duplicate_fragment():
    cover_text = """
Memoire
Master 2 MIAGE
Modelisation evolutive des donnees au sein d'un Data
Warehouse
isation
evolutive des
donnees au
sein d'un Data
Realise par Ilhame Mouzouri
"""

    assert extract_title(cover_text) == "Modelisation evolutive des donnees au sein d'un Data Warehouse"


def test_extract_glued_title_before_university_marker():
    cover_text = (
        "Integrationdel'IntelligenceArtificielledanslesProcessusdeControledeQualitedesLogiciels "
        "NejmaSMATTIUniversiteParisNanterreMasterMIAGE2023-2024"
    )

    assert extract_title(cover_text) == (
        "Integration de l'Intelligence Artificielle dans les Processus de Controle de Qualite des Logiciels"
    )


def test_reject_table_of_contents_as_title():
    assert not is_valid_title(
        "Introduction....................................................................3 Contexte general.....3"
    )


def test_use_case_prefers_olap_over_company_finance_context():
    text = (
        "Proposition d'une architecture pour faire de l'analyse BI augmentee sur des cubes OLAP. "
        "Natixis Trade Finance utilise des outils de reporting et un entrepot de donnees."
    )

    assert classify_use_case(text) == "gestion des donnees / data platform"


def test_use_case_microservice_traces_are_devops_not_finance():
    text = (
        "L'analyse automatisee des traces dans une architecture orientee micro-services "
        "a l'aide du machine learning pour le monitoring et l'observabilite."
    )

    assert classify_use_case(text) == "developpement logiciel / devops"


def test_use_case_specific_domains():
    assert classify_use_case("Detection de fake news avec BERT et SVM") == "medias / detection de desinformation"
    assert classify_use_case("Analyse des sentiments pour predire le Bitcoin") == "finance / marche crypto"
    assert classify_use_case("Influence des reseaux de neurones sur les traitements de graphe") == "analyse de graphes / reseaux"
    assert classify_use_case("Detection de Data Poisoning pour le Federated Learning") == "cybersecurite / detection d'attaques"
    assert classify_use_case("Loi de Moore et informatique quantique") == "informatique quantique / calcul"
    assert classify_use_case("data warehouse contenant des informations clients") == "gestion des donnees / data platform"


def test_track_and_master_fallbacks():
    assert extract_track("Memoire de 2eme annee Master 2 MIAGE APP") == "apprentissage"
    assert extract_track("Rapport de stage M2 MIAGE, parcours classique") == "mixte"
    assert extract_master_level("Memoire de fin de cycle en vue d'obtention du diplome de Master MIAGE") == "M2"


def test_title_continues_when_line_ends_with_article():
    cover_text = """
Memoire de M2 Master MIAGE
Le challenge de l'application du Transfer Learning sur la reconnaissance du langage des
signes
Entreprise d'accueil : Credit Agricole
"""

    assert extract_title(cover_text) == (
        "Le challenge de l'application du Transfer Learning sur la reconnaissance du langage des signes"
    )


def test_title_rejects_program_marker_candidate():
    cover_text = """
M emoire de M1
Master MIAGE
L'evaluation comparative des methodes d'orchestration de conteneurs dans un contexte cloud
Entreprise d'accueil : Matmut
"""

    assert extract_title(cover_text) == (
        "L'evaluation comparative des methodes d'orchestration de conteneurs dans un contexte cloud"
    )
