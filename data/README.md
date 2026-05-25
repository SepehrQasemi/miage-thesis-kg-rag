# Local Data Directory

This directory is intentionally local-only.

The repository does not include thesis PDFs, SQLite databases, extracted CSV files,
OCR cache files, staging uploads, or generated graph outputs.

Run the setup script after cloning to recreate the local runtime structure:

```powershell
python scripts/setup_project.py
```

Then add PDFs from the web app's `Import PDF` screen.
