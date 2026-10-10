"""Read existing project credentials without executing dotenv content."""
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProjectCredentials:
    api_key: str = field(repr=False)
    project_id: str | None = None
    origin: str = ""


def project_credentials(root: Path = ROOT) -> ProjectCredentials | None:
    for relative in (".env", "youtube_research_agent/.env"):
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
