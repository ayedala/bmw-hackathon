# Local maintenance and diagnostics

Run these utilities from the repository root. They complement the `bmw-pm` CLI.

| Script | Purpose |
|---|---|
| `inspect_supplied_data.py` | Inspect/copy supplied archive files with source hashes |
| `profile_feedback.py` | Descriptive workbook diagnostics; not extraction evaluation |
| `validate_preparation.py` | Historical preparation artifacts, source counts and documentation links; needs the local profile and supplied data |
| `prepare_hosted_database.py` | Build a consistent private database snapshot for hosted setup |

Use `uv run pytest` for core software checks and `uv run bmw-pm validate` for a populated database. The preparation validator is not a replacement for either.
