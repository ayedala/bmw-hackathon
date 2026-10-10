"""Local app credentials; never execute dotenv content or include keys in repr."""
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProjectCredentials:
    api_key: str = field(repr=False)
    project_id: str | None = None
    origin: str = ""

    def fingerprint(self, model_id: str) -> str:
        return hashlib.sha256(json.dumps([self.api_key, self.project_id, model_id]).encode()).hexdigest()


def environment_credentials() -> ProjectCredentials | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return ProjectCredentials(key, os.getenv("OPENAI_PROJECT_ID") or None, "Server environment") if key else None


def save_project_credentials(credentials: ProjectCredentials, root: Path = ROOT) -> None:
    """Atomically save the dedicated, Git-ignored app file without changing .env."""
    values = [credentials.api_key, credentials.project_id or ""]
    if not values[0] or any(value and not all(c.isalnum() or c in "_-" for c in value) for value in values):
        raise ValueError("Enter a valid API key and optional project ID without spaces or extra characters.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root,
                                         prefix=".env.advisor-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(f"OPENAI_API_KEY={values[0]}\nOPENAI_PROJECT_ID={values[1]}\n")
        temporary.replace(root / ".env.advisor")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def project_credentials(root: Path = ROOT) -> ProjectCredentials | None:
    for relative in (".env.advisor", ".env", "src/bmw_pm/data_pipeline/youtube_research/.env", "youtube_research_agent/.env"):
        path = root / relative
        if not path.is_file():
            continue
        values = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() not in {"OPENAI_API_KEY", "OPENAI_PROJECT_ID", "OPENAI_PROJECT"}:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[name.strip()] = value
        if values.get("OPENAI_API_KEY"):
            return ProjectCredentials(api_key=values["OPENAI_API_KEY"],
                                      project_id=values.get("OPENAI_PROJECT_ID") or values.get("OPENAI_PROJECT"),
                                      origin=relative)
    return None
