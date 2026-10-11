"""Read-only, bounded data bridge for the local Next.js planning workbench.

Emits no credentials and never creates or mutates a database. The output is
served only by the loopback-bound local app; do not publish it as a static file.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]

# One manually checked, model-specific source span per theme. These are
# examples to inspect, not proof that a proposed feature would solve the issue.
THEME_EXAMPLES = {
    "F70": {
        "controls_usability": "F70-1617",
        "software_reliability": "F70-1715",
        "ride_and_comfort": "F70-0384",
        "noise_and_refinement": "F70-1448",
        "driver_assistance": "F70-0196",
        "storage_and_practicality": "F70-0186",
    },
    "G70": {
        "software_reliability": "G70-2394",
        "ride_and_comfort": "G70-0474",
        "controls_usability": "G70-1833",
        "charging_and_range": "G70-3857",
        "driver_assistance": "G70-1224",
        "noise_and_refinement": "G70-3828",
        "storage_and_practicality": "G70-0898",
    },
}


def verified_payload(row) -> dict:
    payload = json.loads(row[0])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != row[1]:
        raise ValueError("Database payload hash mismatch")
    return payload


def setting(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name].strip()
    for file in (ROOT / ".env.local", ROOT / ".env"):
        if not file.is_file():
            continue
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip().strip("\"'")
    return None


def snapshot() -> dict:
    target = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("BMW_PM_DB_PATH")
        or os.environ.get("BMW_PM_DATABASE")
        or setting("DATABASE_URL")
        or setting("BMW_PM_DB_PATH")
        or setting("BMW_PM_DATABASE")
    )
    if not target:
        target = str(ROOT / "data" / "processed" / "bmw_pm.db")
    if target.startswith(("postgresql://", "postgres://")):
        import psycopg

        connection = psycopg.connect(target, connect_timeout=10, sslmode="require")
        connection.read_only = True
        connection.execute("SET search_path = bmw_pm, pg_catalog")
        backend = "postgres"
    else:
        file = Path(target).resolve()
        if not file.is_file():
            return {"available": False, "reason": "No imported evidence database is configured."}
        connection = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        backend = "sqlite"
    try:
        proposals = json.loads((ROOT / "configs" / "successor_proposals_v1.json").read_text(encoding="utf-8"))
        anchor_ids = {anchor for proposal in proposals["proposals"] for anchor in proposal["anchor_ids"]}
        eligible = connection.execute(
            "SELECT count(*) FROM feedback_records WHERE model_code='G60' AND country='US'"
        ).fetchone()[0]
        bind = "%s" if backend == "postgres" else "?"
        feedback = (
            connection.execute(
                "SELECT payload_json,payload_hash FROM feedback_records WHERE model_code='G60' AND country='US' "
                f"AND source_record_id IN ({','.join([bind] * len(anchor_ids))}) ORDER BY record_id",
                tuple(sorted(anchor_ids)),
            ).fetchall()
            if anchor_ids else []
        )
        records = [verified_payload(row) for row in feedback]
        source_hashes = dict(connection.execute("SELECT source_id, sha256 FROM sources").fetchall())
        records = [
            item for item in records
            if item.get("row_locators")
            and all(
                locator.get("source_id") == item.get("source_id")
                and locator.get("source_hash") == source_hashes.get(item.get("source_id"))
                for locator in item["row_locators"]
            )
        ]
        signals = connection.execute(
            "SELECT s.payload_json,s.payload_hash FROM signals s JOIN feedback_records f ON f.record_id=s.feedback_record_id "
            "WHERE f.model_code='G60' AND f.country='US' ORDER BY s.signal_id"
        ).fetchall()
        example_ids = [source_id for domains in THEME_EXAMPLES.values() for source_id in domains.values()]
        sample_rows = connection.execute(
            "SELECT f.model_code,s.need_domain,s.payload_json,s.payload_hash,f.source_record_id,f.country "
            "FROM signals s JOIN feedback_records f ON f.record_id=s.feedback_record_id "
            f"WHERE f.source_record_id IN ({','.join([bind] * len(example_ids))}) "
            "AND s.polarity IN ('complaint','aspiration') ORDER BY s.signal_id",
            tuple(example_ids),
        ).fetchall()
        samples_by_theme = {}
        for row in sample_rows:
            if THEME_EXAMPLES.get(row[0], {}).get(row[1]) == row[4]:
                samples_by_theme.setdefault((row[0], row[1]), []).append(row)
        model_coverage = []
        for model in ("F70", "G70"):
            market_rows = connection.execute(
                "SELECT country, count(*) FROM feedback_records WHERE model_code=" + bind +
                " GROUP BY country ORDER BY count(*) DESC, country", (model,)
            ).fetchall()
            theme_rows = connection.execute(
                "SELECT s.need_domain, count(*), count(DISTINCT s.feedback_record_id), "
                "sum(CASE WHEN s.polarity IN ('complaint','aspiration') THEN 1 ELSE 0 END) "
                "FROM signals s JOIN feedback_records f ON f.record_id=s.feedback_record_id "
                "WHERE f.model_code=" + bind + " GROUP BY s.need_domain ORDER BY count(*) DESC, s.need_domain",
                (model,),
            ).fetchall()
            signal_markets = connection.execute(
                "SELECT f.country, count(*) FROM signals s JOIN feedback_records f ON f.record_id=s.feedback_record_id "
                "WHERE f.model_code=" + bind + " GROUP BY f.country ORDER BY count(*) DESC, f.country",
                (model,),
            ).fetchall()
            themes = []
            for domain, signal_count, feedback_count, concern_count in theme_rows:
                examples = []
                used_ids = set()
                for row in samples_by_theme.get((model, domain), []):
                    payload = verified_payload((row[2], row[3]))
                    spans = payload.get("evidence_spans") or []
                    excerpt = str(spans[0].get("text", "")).strip() if spans else ""
                    if len(excerpt) < 18 or row[4] in used_ids:
                        continue
                    used_ids.add(row[4])
                    locator = spans[0].get("locator") or {}
                    examples.append({
                        "source_record_id": row[4], "country": row[5],
                        "excerpt": excerpt[:240],
                        "locator": "!".join(str(locator.get(k, "")) for k in ("sheet", "cell_range") if locator.get(k)),
                    })
                    if len(examples) == 1:
                        break
                themes.append({"domain": domain, "signal_count": signal_count,
                               "feedback_count": feedback_count, "concern_count": concern_count,
                               "examples": examples})
            model_coverage.append({
                "model_code": model,
                "feedback_records": sum(count for _, count in market_rows),
                "markets": [{"country": country, "records": count} for country, count in market_rows],
                "signal_markets": [{"country": country, "signals": count} for country, count in signal_markets],
                "signal_count": sum(theme["signal_count"] for theme in themes),
                "themes": themes,
            })
        return {
            "available": True,
            "backend": backend,
            "eligible_feedback_records": eligible,
            "feedback": [
                {
                    "record_id": item["record_id"],
                    "source_record_id": item["source_record_id"],
                    "redacted_text": item["redacted_text"],
                    "powertrain": item.get("powertrain"),
                    "row_locators": item.get("row_locators", []),
                }
                for item in records if item["source_record_id"] in anchor_ids
            ],
            "signals": [verified_payload(row) for row in signals],
            "model_coverage": model_coverage,
        }
    finally:
        connection.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")))
    except Exception as error:
        if os.environ.get("BMW_PM_DEBUG_SNAPSHOT") == "1":
            print(type(error).__name__, file=sys.stderr)
        print(json.dumps({"available": False, "reason": "The evidence database could not be read. Check the local database connection and schema."}))
        sys.exit(1)
