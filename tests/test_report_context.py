import json
from pathlib import Path

import pytest

from bmw_pm.contracts import RequirementRevision, RequirementScope
from bmw_pm.storage import Database, WorkflowError


DOCUMENT = Path(__file__).resolve().parents[1] / "configs" / "bmw_group_report_2025_context.json"


def _requirement(title: str, powertrains: list[str]) -> RequirementRevision:
    return RequirementRevision.model_construct(
        title=title,
        scope=RequirementScope(models=["G60"], countries=["US"], powertrains=powertrains),
    )


def test_report_context_is_scoped_immutable_and_does_not_create_scores(tmp_path):
    database = Database(tmp_path / "context.db")
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))

    assert database.sync_report_context(document) == 5
    assert database.sync_report_context(document) == 0
    assert len(database.report_context_for_requirement(_requirement("Charging And Range", ["BEV"]))) == 5
    assert len(database.report_context_for_requirement(_requirement("Ride And Comfort", ["ICE"]))) == 3
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM score_snapshots").fetchone()[0] == 0
    assert database.verify_audit_chain()[0]

    changed = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    changed["items"][0]["fact"] = "changed after publication"
    with pytest.raises(WorkflowError):
        database.sync_report_context(changed)
