import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

root = Path(__file__).resolve().parents[1]
url = make_url(dotenv_values(root / "backend/.env")["DATABASE_URL"])
if url.database != "medikiosk":
    raise RuntimeError("This helper only targets the local medikiosk_test database.")
test_url = url.set(database="medikiosk_test").update_query_dict({"connect_timeout": "3"})
engine = create_engine(test_url)
try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
except SQLAlchemyError:
    print(
        "PostgreSQL acceptance database is unavailable; no tests were started. "
        "Start the project-local database and retry.",
        file=sys.stderr,
    )
    raise SystemExit(2) from None
finally:
    engine.dispose()

env = dict(os.environ)
env["TEST_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=root / "backend", env=env))
