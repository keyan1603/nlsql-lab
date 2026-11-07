"""Settings from the environment or a local .env file (never committed).

Two database roles, on purpose: the loader needs to write, the question-answering path must not be able to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The dataset's "today". Every date-relative question names this date explicitly instead of using CURDATE(),
# so the gold answers do not change as real time passes.
AS_OF_DATE = "2026-10-31"
AS_OF_TS = "2026-10-31 18:00:00"


def _read_env_file(path: Path) -> dict:
    out: dict = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database: str
    admin_user: str
    admin_password: str
    reader_user: str
    reader_password: str

    def __repr__(self) -> str:                      # never print a password
        return f"Settings(host={self.host!r}, port={self.port}, database={self.database!r}, admin_user={self.admin_user!r}, reader_user={self.reader_user!r}, passwords=***)"

    def credentials(self, role: str) -> tuple[str, str]:
        if role == "admin":
            return self.admin_user, self.admin_password
        if role == "reader":
            return self.reader_user, self.reader_password
        raise ValueError(f"unknown role {role!r}; use 'admin' or 'reader'")


def load_settings(env_path: Path | None = None) -> Settings:
    file_values = _read_env_file(env_path or ROOT / ".env")

    def get(name: str, default: str | None = None) -> str:
        value = os.environ.get(name, file_values.get(name, default))
        if value is None or value == "":
            raise RuntimeError(f"{name} is not set; run scripts/make_setup_sql.py and the root setup step first (see README)")
        return value

    return Settings(host=get("MYSQL_HOST", "127.0.0.1"), port=int(get("MYSQL_PORT", "3306")), database=get("MYSQL_DB", "nlsql_lab"),
                    admin_user=get("NLSQL_ADMIN_USER", "nlsql_admin"), admin_password=get("NLSQL_ADMIN_PASSWORD"),
                    reader_user=get("NLSQL_READER_USER", "nlsql_reader"), reader_password=get("NLSQL_READER_PASSWORD"))
