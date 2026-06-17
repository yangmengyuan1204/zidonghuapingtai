import os
import time

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./auto_test_platform.db")

connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# SQLite "database is locked" 重试配置
SQLITE_LOCKED_RETRIES = 3
SQLITE_LOCKED_DELAY = 0.5  # 秒


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def safe_commit(db_session, max_retries: int = SQLITE_LOCKED_RETRIES) -> None:
    """提交事务，遇到 SQLite database is locked 时自动重试。"""
    last_error = None
    for attempt in range(max_retries):
        try:
            db_session.commit()
            return
        except OperationalError as exc:
            last_error = exc
            if "database is locked" not in str(exc).lower():
                raise
            if attempt < max_retries - 1:
                time.sleep(SQLITE_LOCKED_DELAY * (attempt + 1))
    raise last_error  # type: ignore[misc]


def safe_flush(db_session, max_retries: int = SQLITE_LOCKED_RETRIES) -> None:
    """Flush 事务，遇到 SQLite database is locked 时自动重试。"""
    last_error = None
    for attempt in range(max_retries):
        try:
            db_session.flush()
            return
        except OperationalError as exc:
            last_error = exc
            if "database is locked" not in str(exc).lower():
                raise
            if attempt < max_retries - 1:
                time.sleep(SQLITE_LOCKED_DELAY * (attempt + 1))
    raise last_error  # type: ignore[misc]
