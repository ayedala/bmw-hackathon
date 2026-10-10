import json

from bmw_pm.contracts import RequirementRevision, RequirementScope
from bmw_pm.public_datasets import (
    afdc_records,
    nhtsa_records,
    parse_afdc_counts,
    public_record_applies,
)
from bmw_pm.storage import Database


def _requirement(title, powertrains):
    return RequirementRevision.model_construct(
        title=title,
        scope=RequirementScope(models=["G60"], countries=["US"], powertrains=powertrains),
    )


def test_nhtsa_snapshot_excludes_vin_and_narrative(monkeypatch):
    def fake_get(url):
        if "products/vehicle/models" in url:
            return {"results": [{"model": "530I"}]}, "a" * 64
        if "complaintsByVehicle" in url:
            return {"results": [{"odiNumber": 123, "components": "ELECTRICAL SYSTEM",
                                 "vin": "SECRET", "summary": "private narrative"}]}, "b" * 64
        return {"results": [{"NHTSACampaignNumber": "24V001", "Component": "ELECTRICAL SYSTEM"}]}, "c" * 64

    monkeypatch.setattr("bmw_pm.public_datasets._get_json", fake_get)
    config = {"schema_version": "1", "nhtsa": {
        "model_years": [2024], "model_prefixes": {"G60": ["5"]}
    }}
    records, coverage = nhtsa_records(config)
    assert len(records) == 1
    assert coverage["model_years"]["2024"]["G60"] == ["530I"]
    record = records[0]
    assert record["payload"]["by_domain"]["software_reliability"] == {
        "complaint_ids": ["123"], "campaign_ids": ["24V001"]
    }
    assert "SECRET" not in json.dumps(record)
    assert "private narrative" not in json.dumps(record)
    assert public_record_applies(record, _requirement("Software Reliability", ["ICE"]))
    assert not public_record_applies(record, _requirement("Charging And Range", ["BEV"]))
    assert not public_record_applies(record, _requirement("Storage And Practicality", ["ICE"]))


def test_afdc_table_reconciles_and_database_keeps_scores_separate(tmp_path):
    rows = "".join(
        f"<tr><td>State {number}</td><td>0</td><td>0</td><td>0</td>"
        "<td>1 | 2<br>0 | 1 | 1</td><td>0</td><td>0</td><td>0</td><td>0</td><td>2</td></tr>"
        for number in range(50)
    )
    total = ("<tr><td>Total</td><td>0</td><td>0</td><td>0</td>"
             "<td>50 | 100<br>0 | 50 | 50</td><td>0</td><td>0</td><td>0</td><td>0</td><td>100</td></tr>")
    html = f'<table id="count_table"><tbody>{rows}</tbody><tfoot>{total}</tfoot></table>Data last updated: 10/10/2026'
    as_of, parsed = parse_afdc_counts(html)
    assert as_of == "2026-10-10"
    assert len(parsed) == 51
    assert parsed[-1]["dc_fast_ports"] == 50

    monkeypatch_data = html.encode()
    from unittest.mock import patch
    with patch("bmw_pm.public_datasets._get", return_value=monkeypatch_data):
        records = afdc_records(
            {"afdc": {"url": "https://afdc.energy.gov/stations/states?count=public"}},
            snapshot_root=tmp_path / "snapshots",
        )
    database = Database(tmp_path / "evidence.db")
    assert database.persist_public_evidence(records) == 51
    assert database.persist_public_evidence(records) == 0
    assert len(database.public_evidence_for_requirement(_requirement("Charging And Range", ["BEV"]))) == 1
    assert database.public_evidence_for_requirement(_requirement("Ride And Comfort", ["ICE"])) == []
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM score_snapshots").fetchone()[0] == 0
    assert database.verify_audit_chain()[0]
