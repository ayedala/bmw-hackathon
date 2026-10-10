# Hosted decision workbench

Status: deployment code and private snapshot prepared; no cloud service has been created yet.

The existing Python/Streamlit application runs as one Docker service with SQLite on a persistent filesystem. `render.yaml` selects Frankfurt, one `1c-2g` compute instance and a 1 GB disk mounted at `/var/data`. Persistent disks require a paid Render service. Confirm the current compute/disk charge in Render before creating the service; this preparation does not incur charges. The larger memory choice accommodates the approximately 185 MiB snapshot upload and canonical validation. No load-test result is claimed.

## Deploy

1. Connect the Render account, then deploy a Blueprint from this repository's hosting branch (`codex/hosted-app`). Review the plan/region before provisioning. The Blueprint generates distinct team and setup passwords as service secrets. Auto-deploy is off.
2. Use the SHA-256 in the local `exports/hosted/bmw_pm.manifest.json` as `BMW_PM_BOOTSTRAP_SHA256`. This approves one exact private snapshot, without giving it a public URL.
3. Open the returned HTTPS service URL. Sign in with the generated `BMW_PM_APP_PASSWORD` from the Render service's secret settings.
4. Upload the local `exports/hosted/bmw_pm.db` and enter the separate `BMW_PM_ADMIN_PASSWORD` in initial setup. Restore verifies the byte hash before opening SQLite, checks integrity/references, reconciles all supplied counts/citations and verifies the audit chain. It records restore provenance and atomically installs the snapshot on the disk. A second restore cannot overwrite existing history.
5. Share the app URL and team password with authorized teammates using the team's private channel. Keep the setup password with the service owner. Never paste passwords or the raw database into public issues or Git.

The Render connection allows service provisioning; database upload remains through the authenticated app unless an authorized private file-transfer capability is available. The app does not fetch customer material from a public GitHub URL.

## Snapshot and persistence

Prepare a new, consistent snapshot locally:

```powershell
$env:PYTHONPATH = "src"
python scripts/prepare_hosted_database.py --output exports/hosted/bmw_pm.db
```

The script validates canonical data, records an export audit event and uses SQLite's backup API so committed WAL changes are included. Choose a new output filename for later snapshots; existing files are never silently replaced. Database payloads, manifests, source workbooks and exports remain excluded from Git and Docker build context. The container copies only application code/configuration. Source hashes and original locators remain in the uploaded database; original PDF/workbook bytes stay in the authorized local archive.

`BMW_PM_DB_PATH` is fixed by the host, and visitors cannot choose arbitrary filesystem paths. Hosted context selectors exclude the foreign raw customer-quote locator table. Existing signal views display locally redacted spans; heuristic redaction is not a guarantee of anonymity. The backing database contains private evidence and must remain access-controlled. Uploaded databases are not served as static files. Startup with missing/short/identical secrets fails closed before opening any database.

Shared password access is a bounded prototype control, not verified individual identity or enterprise authentication. Sessions expire after 30 minutes and password rotation invalidates them. Repeated failures have a per-session cooldown; this is not global brute-force protection. PM actor IDs remain declared IDs. Authenticated workbench reads, context reads, setup/export and PM writes produce audit events. For broader rollout, replace shared team access with organization sign-in and reviewed authorization.

Run a single service instance. Keep the disk attached across redeploys. Do not initialize a new database on ephemeral container storage. Use the provider's private disk backups for hosted changes; a local upload snapshot does not capture later PM decisions. Restore of an established service is an owner operation after stopping writes, not a user-facing overwrite button.

## Verification and limits

Software tests cover fail-closed access, incorrect/non-ASCII passwords, denied/tampered/noncanonical uploads, preserving existing history, and login-before-database access. The full private snapshot was restored to a local test path, passed reconciliation/citation/audit checks and rendered through authenticated Streamlit AppTest. Customer material is not used in committed tests. Docker build and real HTTPS/disk-redeploy tests remain unrun until a Docker engine and hosting account are available. No live model inference, model accuracy or cloud-load measurement is claimed.

Provider references: [Render Docker](https://render.com/docs/docker), [persistent disks](https://render.com/docs/disks), [Blueprint specification](https://render.com/docs/blueprint-spec), [current pricing](https://render.com/pricing), and [Streamlit Docker deployment](https://docs.streamlit.io/deploy/tutorials/docker).
