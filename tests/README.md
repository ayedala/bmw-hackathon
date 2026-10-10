# Core software checks

Run `uv run pytest` from the repository root. Tests cover source provenance, record deduplication, score intervals and deterministic ranking, immutable PM revisions, audit verification, foreign workspace import and hosted setup. Fixtures are synthetic; passing tests does not establish model accuracy or customer representativeness.

The optional YouTube collector retains its own tests. After installing its local requirements and pytest, run from its directory with `PYTHONPATH=. python -m pytest tests`. The web collector has no dedicated regression suite yet; its offline plan can be checked with `python main.py --dry-run --no-search`.
