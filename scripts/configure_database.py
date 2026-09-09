"""Provision the local demo database. Never prints credentials."""
import secrets
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values
from psycopg import sql

root = Path(__file__).resolve().parents[1]
admin_password = (root / ".runtime/postgres-admin.txt").read_text().strip()
env_path = root / "backend/.env"
env = dotenv_values(env_path) if env_path.exists() else {}
if env.get("LOCAL_POSTGRES_CONFIGURED") == "true":
    print("Local database configuration already exists.")
    raise SystemExit(0)
app_password = secrets.token_urlsafe(32)
with psycopg.connect(host="127.0.0.1", port=55432, dbname="postgres",
                     user="medikiosk_admin", password=admin_password, autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'medikiosk'").fetchone():
        raise RuntimeError("App role already exists. Preserve it and inspect existing configuration.")
    conn.execute(sql.SQL("CREATE ROLE medikiosk LOGIN PASSWORD {}").format(sql.Literal(app_password)))
    conn.execute("CREATE DATABASE medikiosk OWNER medikiosk")
    conn.execute("CREATE DATABASE medikiosk_test OWNER medikiosk")
lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
updated = {"DATABASE_URL": f"postgresql+psycopg://medikiosk:{quote(app_password)}@127.0.0.1:55432/medikiosk",
           "APP_ENV": "development", "DEMO_MODE": "true", "LOCAL_POSTGRES_CONFIGURED": "true"}
kept = [line for line in lines if line.split("=", 1)[0].strip() not in updated]
env_path.write_text("\n".join(kept + [f"{key}={value}" for key, value in updated.items()]) + "\n",
                    encoding="utf-8")
print("Application database and separate test database created; backend/.env configured.")

