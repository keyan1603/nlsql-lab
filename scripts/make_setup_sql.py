"""Create the local credentials and the one-time MySQL setup script.

    python scripts/make_setup_sql.py

Writes .env (random passwords, never committed) and setup/setup_mysql.sql (also never committed). A person with MySQL
administrator rights runs the SQL file once; nothing in this repo ever sees the administrator's password. The script creates:

  * the database nlsql_lab
  * nlsql_admin  - all privileges on that database only; used by the loader
  * nlsql_reader - SELECT only, a handful of connections; used by everything that runs generated SQL
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
SETUP = ROOT / "setup" / "setup_mysql.sql"


def main() -> int:
    if ENV.exists() and "--force" not in sys.argv:
        print(".env already exists; keeping it (use --force to regenerate, which also needs the SQL re-run)")
        values = dict(line.split("=", 1) for line in ENV.read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
    else:
        values = {"MYSQL_HOST": "127.0.0.1", "MYSQL_PORT": "3306", "MYSQL_DB": "nlsql_lab",
                  "NLSQL_ADMIN_USER": "nlsql_admin", "NLSQL_ADMIN_PASSWORD": secrets.token_urlsafe(18),
                  "NLSQL_READER_USER": "nlsql_reader", "NLSQL_READER_PASSWORD": secrets.token_urlsafe(18)}
        ENV.write_text("# local lab credentials, generated; do not commit\n" + "\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
        print("wrote .env")
    db = values["MYSQL_DB"]
    sql = f"""-- Run once as a MySQL administrator (for example: mysql -u root -p). Generated; contains passwords; not committed.
CREATE DATABASE IF NOT EXISTS {db} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS '{values["NLSQL_ADMIN_USER"]}'@'localhost' IDENTIFIED BY '{values["NLSQL_ADMIN_PASSWORD"]}';
ALTER USER '{values["NLSQL_ADMIN_USER"]}'@'localhost' IDENTIFIED BY '{values["NLSQL_ADMIN_PASSWORD"]}';
GRANT ALL PRIVILEGES ON {db}.* TO '{values["NLSQL_ADMIN_USER"]}'@'localhost';

CREATE USER IF NOT EXISTS '{values["NLSQL_READER_USER"]}'@'localhost' IDENTIFIED BY '{values["NLSQL_READER_PASSWORD"]}' WITH MAX_USER_CONNECTIONS 4;
ALTER USER '{values["NLSQL_READER_USER"]}'@'localhost' IDENTIFIED BY '{values["NLSQL_READER_PASSWORD"]}' WITH MAX_USER_CONNECTIONS 4;
GRANT SELECT ON {db}.* TO '{values["NLSQL_READER_USER"]}'@'localhost';

FLUSH PRIVILEGES;
"""
    SETUP.parent.mkdir(exist_ok=True)
    SETUP.write_text(sql, encoding="utf-8")
    print(f"wrote {SETUP.relative_to(ROOT)} (contains passwords; gitignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
