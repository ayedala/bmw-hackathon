from bmw_pm.contracts import RequirementRevision, RequirementScope
from bmw_pm.storage import Database


def test_review_context_uses_linked_signal_domain_after_display_title_edit(tmp_path):
    database = Database(tmp_path / "context.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute("INSERT INTO sources VALUES (?,?,?,?)", ("source", "0" * 64, "{}", "hash"))
        connection.execute("INSERT INTO feedback_records VALUES (?,?,?,?,?,?,?,?)",
                           ("feedback", "source", "1", "G60", "US", "ICE", "{}", "hash"))
        connection.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?)",
                           ("signal", "feedback", "controls_usability", "complaint", "run", "{}", "hash"))
        connection.commit()
    database.persist_public_evidence([{
        "record_id": "public-1", "logical_key": "public-1",
        "snapshot_at": "2026-10-10T00:00:00Z", "kind": "industry_study_summary",
        "source_url": "https://example.org/synthetic", "market": "US",
        "models": ["G60"], "domains": ["controls_usability"],
        "limitations": "Synthetic test fact", "payload": {"fact": "Synthetic"},
    }])
    database.sync_report_context({
        "schema_version": "1", "status": "company_report_context_not_feature_evidence",
        "source_url": "https://www.bmwgroup.com/synthetic", "report_id": "synthetic",
        "published_on": "2026-10-10", "items": [{
            "id": "controls", "page": 1, "fact": "Synthetic", "consideration": "Review",
            "domains": ["controls_usability"], "powertrains": ["ICE"],
            "kind": "domain_context", "limitation": "Synthetic test fact",
        }],
    })
    requirement = RequirementRevision.model_construct(
        title="Better controls for drivers", supporting_signal_ids=["signal"],
        scope=RequirementScope(models=["G60"], countries=["US"], powertrains=["ICE"]),
    )
    assert len(database.public_evidence_for_requirement(requirement)) == 1
    assert len(database.report_context_for_requirement(requirement)) == 1
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM score_snapshots").fetchone()[0] == 0
