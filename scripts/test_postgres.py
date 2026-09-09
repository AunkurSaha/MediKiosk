import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
url = make_url(dotenv_values(root / "backend/.env")["DATABASE_URL"])
if url.database != "medikiosk":
    raise RuntimeError("This helper only targets the local medikiosk_test database.")
env = dict(os.environ)
env["TEST_DATABASE_URL"] = url.set(database="medikiosk_test").render_as_string(hide_password=False)
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=root / "backend", env=env))

