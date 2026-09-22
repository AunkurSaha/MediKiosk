from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import APP_ENV, DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure the Supabase connection in backend/.env."
    )

database_url = make_url(DATABASE_URL)
is_sqlite_test = APP_ENV == "test" and database_url.get_backend_name() == "sqlite"
e2e_database = Path(__file__).resolve().parents[2] / ".runtime" / "e2e.sqlite"
is_sqlite_e2e = APP_ENV == "e2e" and database_url.get_backend_name() == "sqlite"
if APP_ENV == "e2e" and (
    not is_sqlite_e2e or Path(database_url.database or "").resolve() != e2e_database.resolve()
):
    raise RuntimeError("E2E mode requires the dedicated local .runtime/e2e.sqlite database.")
if APP_ENV not in {"test", "e2e"} and (
    database_url.get_backend_name() != "postgresql"
    or not database_url.host
    or not database_url.host.endswith(".supabase.com")
):
    raise RuntimeError("Runtime DATABASE_URL must use a Supabase PostgreSQL endpoint.")
if database_url.get_backend_name() == "sqlite" and not (is_sqlite_test or is_sqlite_e2e):
    raise RuntimeError("SQLite is supported only by isolated tests or explicit local E2E mode.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"check_same_thread": False} if is_sqlite_test or is_sqlite_e2e else {},
)
if is_sqlite_test or is_sqlite_e2e:

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        # Historical Alembic revisions use PostgreSQL's now() server default.
        # Test-mode SQLite runs the same migrations, so provide the compatible
        # zero-argument function instead of maintaining a divergent schema path.
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())


SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
