from scripts.validate_dataset import validate_rows


def test_validate_dataset_reports_unreadable_exported_csv(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "theses.csv").write_bytes(b"\xff\xfe")
    monkeypatch.setenv("MIAGE_PROCESSED_DIR", str(processed))
    monkeypatch.setenv("MIAGE_RAW_PDF_DIR", str(tmp_path / "raw"))

    issues, summary = validate_rows(
        [
            {
                "thesis_id": "thesis_0001",
                "file_name": "thesis_0001.pdf",
                "title": "Valid title",
                "year": "2026",
                "master_level": "M2",
                "track": "classique",
                "keywords": "machine learning",
                "concepts": "machine learning",
                "use_case": "sante",
                "methodology": "classification",
                "needs_review": False,
            }
        ],
        allow_subset=True,
    )

    assert summary["errors"] == 1
    assert any(item["problem"] == "exported_csv_unreadable" for item in issues)
