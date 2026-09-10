from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import APP_ENV, DATABASE_URL

if DATABASE_URL.startswith("sqlite") and APP_ENV != "test":
    raise RuntimeError("SQLite is only supported for tests. Configure PostgreSQL in backend/.env.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
if DATABASE_URL.startswith("sqlite"):

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
