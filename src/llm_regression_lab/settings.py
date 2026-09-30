import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
SCOPES = frozenset({"versions:read", "versions:write", "jobs:read", "jobs:write", "reports:read"})


@dataclass(frozen=True)
class Identity:
    project_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class Settings:
    database_url: str
    artifact_root: Path
    tokens: dict[str, Identity]
    max_body_bytes: int = 1048576

    @classmethod
    def from_env(cls):
        if os.environ.get("LAB_LOCAL_ONLY") != "1":
            raise RuntimeError(
                "This implementation requires explicit LAB_LOCAL_ONLY=1; production mode is unavailable."
            )
        entries = json.loads(os.environ["LAB_LOCAL_TOKENS"])
        if not isinstance(entries, dict) or not entries:
            raise ValueError("Configure at least one local bearer token")
        tokens = {}
        for token, item in entries.items():
            if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
                raise ValueError("Local tokens must contain at least 32 non-whitespace ASCII characters")
            scopes = frozenset(item["scopes"])
            if not scopes <= SCOPES:
                raise ValueError("Unknown local token scope")
            tokens[token] = Identity(str(UUID(item["project_id"])), scopes)
        database_url = os.environ.get("DATABASE_URL")
        if database_url is None:
            password = quote(os.environ["LAB_DATABASE_PASSWORD"], safe="")
            database_url = f"postgresql://lab:{password}@{os.environ['LAB_DATABASE_HOST']}:5432/lab"
        return cls(database_url, Path(os.environ.get("LAB_ARTIFACT_ROOT", ROOT / "artifacts")), tokens)
