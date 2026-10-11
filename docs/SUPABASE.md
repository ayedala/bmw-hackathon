# Shared team database

The local Next.js and Streamlit apps can use one shared Supabase PostgreSQL database.
The advisor, research prompts, evidence filters and financial calculations remain the same.
SQLite remains available for offline work and tests. Application tables live in the private
`bmw_pm` schema; the browser never receives the database connection string.

## 1. Create and configure the project

1. Create a Supabase project and save its database password.
2. Open **Connect → Connection string → Session pooler**. Use the actual hostname shown there,
   port **5432**, and the username `postgres.PROJECT_REF`. Transaction pooling on port 6543 is
   intentionally rejected because this application uses session settings.
3. Put the connection string in the repository-root, Git-ignored `.env.local`. The tracked `.env` is a blank setup template:

   ```dotenv
   DATABASE_URL="postgresql://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@YOUR_POOLER_HOST:5432/postgres?sslmode=require"
   ```

   Replace the values and remove placeholder brackets. URL-encode special password characters.
   Keep `OPENAI_API_KEY` in the same file. Never put database credentials in a `NEXT_PUBLIC_` variable.
   Remote connections require encrypted transport. To verify the server identity too, use the
   Supabase CA certificate with `sslmode=verify-full&sslrootcert=PATH_TO_CERTIFICATE`.

4. Install the driver:

   ```powershell
   .venv\Scripts\python.exe -m pip install -e ".[ai,postgres]"
   ```

An explicit CLI `--db` path uses SQLite. Without one, process environment settings take precedence
over `.env.local`, which takes precedence over `.env`: `DATABASE_URL`, then `BMW_PM_DB_PATH`. An invalid shared connection fails visibly;
it does not silently switch to a local dataset.

## 2. Migrate the existing dataset once

Run these owner operations using the project administrator's database credentials:

```powershell
.venv\Scripts\python.exe -m bmw_pm.storage.supabase migrate --source data/processed/bmw_pm.db --source-files data/raw/provided
.venv\Scripts\python.exe -m bmw_pm.storage.supabase verify --expect-supplied-shape
.venv\Scripts\python.exe -m bmw_pm.storage.supabase status
```

The migration uses the project's direct PostgreSQL endpoint for its large transfer, while the apps
continue to use the configured Session pooler. Direct migration requires IPv6 connectivity from
the computer running the command. The migration creates the schema, takes a consistent SQLite
backup including committed WAL data,
and copies the original tables using 500-record PostgreSQL COPY batches in one transaction. It verifies every table's row count and
content hash before committing. The original insertion order of scores, decisions and priority
assessments is preserved. Audit history and original JSON are retained; one migration audit event
and a receipt are added. A repeat of the same snapshot is a no-op. A different snapshot is refused
if the target already contains application data. There is no destructive replace option.

The source SQLite database and files remain local and unchanged. Unsupported source tables or
columns stop the copy. Any failure during data transfer rolls back the whole data transaction;
the initialized empty schema may remain.

`--source-files` stores the selected original documents privately in `bmw_pm.shared_source_files`,
with their exact bytes, relative paths and SHA-256 hashes. This initial setup uses PostgreSQL binary
storage for the small source-document collection. It needs no Storage API credential. Large future
collections can move to private object storage without changing evidence identifiers. Only supported
document extensions under the selected directory are included (50 MB/file, 250 MB/batch).

In Supabase **Table Editor**, choose the **bmw_pm** schema to inspect the shared tables.

## 3. Invite collaborators to the Supabase dashboard

For a link that lets a teammate open and manage the shared dataset in Supabase:

1. Open the organization (**bmw-hackathon**) from the top-left organization selector.
2. Open **Team**, choose **Invite member**, enter their email and select **Developer**.
3. Supabase sends an invitation link to that address. They accept it with their own
   Supabase account; invitations expire after 24 hours.
4. They open **bmw-decision-lab → Table Editor** and select the **bmw_pm** schema.

Developer access includes project data tools but cannot change project settings. On the Free
plan, the invitation grants access across the organization; project-specific roles require
Team or Enterprise. Keep this organization dedicated to the collaborators' shared projects.
The normal database triggers still protect immutable source/revision history. Use the app's
versioned updates when changing audited decisions rather than modifying old audit records.

Dashboard membership and a local app's PostgreSQL login are separate. The invitation is enough
to collaborate in the dashboard; running the app against this database also requires a connection
in the collaborator's local `.env.local`, as below.

## 4. Connect a collaborator's local app

Create an individual database login instead of distributing the project administrator password:

```powershell
.venv\Scripts\python.exe -m bmw_pm.storage.supabase create-user bmw_user_alice --access writer
.venv\Scripts\python.exe -m bmw_pm.storage.supabase create-user bmw_user_bob --access reader
```

Each command generates a strong password and writes a new Git-ignored `.env.bmw_user_NAME` file
in the repository root. It does not print credentials, overwrite existing files or reset existing
users. Share that file privately with its named collaborator. They copy its `DATABASE_URL` line
into their own root `.env.local`, add their own AI credentials, install the `ai,postgres` extras, and run:

```powershell
cd web
npm ci --ignore-scripts
npm run dev
```

The research form displays **Connected to the shared team dataset**. Dataset updates and transcript
memories are shared; the current Next.js decision report state remains local to each browser.
The older planning demo pages still contain labelled example data and browser-local review actions.

| Access | Allowed |
|---|---|
| Reader | Inspect the shared dataset and download stored source documents |
| Writer | Read and append evidence, transcripts, audit events and versioned reviews through the app |
| Project administrator | Initialize/migrate the schema, create/revoke logins and manage the project |

Use **writer** for the complete local app: saved-research synchronization and audited actions write
records. Writers cannot update/delete existing rows or alter the schema. Immutability triggers and
serialized audited writes preserve the existing application invariants. These are trusted team
database accounts, not per-customer web accounts or a tamper-proof audit system. A project owner can
still change database policy. Revoking a collaborator is an owner operation, for example `ALTER ROLE
bmw_user_alice NOLOGIN`; end existing sessions as well when immediate revocation is required.

Anonymous Supabase API roles receive no access. The private schema has row policies for the named
team roles only. Keep the schema out of the public Data API. Do not share the owner `.env.local` file.

Download an original by its source hash to a new local filename:

```powershell
.venv\Scripts\python.exe -m bmw_pm.storage.supabase download-source SOURCE_SHA256 --output source.pdf
```

## Testing and limits

PostgreSQL integration tests require an explicit `BMW_TEST_POSTGRES_DSN` pointing to a disposable
localhost database whose name starts with `bmw_test`. They create and remove isolated test databases;
they refuse hosted targets. They cover migration/parity, whole-transaction rollback, immutable rows,
concurrent audit writes, distinct collaborator permissions, transcript sharing and revision replay.

The existing SQLite regression suite remains applicable. A database migration does not establish
LLM accuracy, financial forecast quality or live AI quota. The shared database alone does not publish
a public website; collaborators run the app locally. Existing SQLite-only hosting snapshot utilities
continue to operate on explicit local files.

References: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Team invitations and access](https://supabase.com/docs/guides/platform/access-control),
[Postgres roles](https://supabase.com/docs/guides/database/postgres/roles),
[Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html).
