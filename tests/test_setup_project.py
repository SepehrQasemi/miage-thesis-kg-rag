from scripts import setup_project


def test_prepare_env_generates_password_for_fresh_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_project, "ROOT", tmp_path)
    (tmp_path / ".env.example").write_text(
        "MIAGE_NEO4J_USER=neo4j\nMIAGE_NEO4J_PASSWORD=\n",
        encoding="utf-8",
    )

    assert setup_project.ensure_env_file() is True
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    password_line = next(line for line in content.splitlines() if line.startswith("MIAGE_NEO4J_PASSWORD="))
    assert len(password_line.split("=", 1)[1]) >= 32


def test_prepare_env_preserves_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_project, "ROOT", tmp_path)
    original = "MIAGE_NEO4J_PASSWORD=existing-local-value\n"
    (tmp_path / ".env").write_text(original, encoding="utf-8")
    (tmp_path / ".env.example").write_text("MIAGE_NEO4J_PASSWORD=\n", encoding="utf-8")

    assert setup_project.ensure_env_file() is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == original