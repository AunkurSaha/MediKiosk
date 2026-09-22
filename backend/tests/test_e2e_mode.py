import os
import subprocess
import sys
from pathlib import Path


def _probe(url: str, app_env: str = "e2e") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from app.database import engine; print(engine.url)"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "APP_ENV": app_env, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_e2e_accepts_only_dedicated_local_sqlite_file():
    root = Path(__file__).resolve().parents[2]
    expected = (root / ".runtime" / "e2e.sqlite").as_posix()
    accepted = _probe(f"sqlite:///{expected}")
    assert accepted.returncode == 0, accepted.stderr
    assert expected in accepted.stdout
    rejected = _probe(f"sqlite:///{(root / '.runtime' / 'other.sqlite').as_posix()}")
    assert rejected.returncode != 0
    assert "dedicated local" in rejected.stderr


def test_e2e_rejects_remote_database_url_without_connecting():
    rejected = _probe("postgresql+psycopg://user:pass@remote.supabase.com/postgres")
    assert rejected.returncode != 0
    assert "dedicated local" in rejected.stderr


def test_normal_runtime_still_rejects_local_sqlite():
    root = Path(__file__).resolve().parents[2]
    rejected = _probe(f"sqlite:///{(root / '.runtime' / 'e2e.sqlite').as_posix()}", "development")
    assert rejected.returncode != 0
    assert "Supabase PostgreSQL" in rejected.stderr
