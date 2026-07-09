import atexit
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text


TEST_DB = Path(__file__).resolve().parent / "test_platform_suite.db"


def _remove_sqlite_files(path: Path) -> None:
    for suffix in ("", "-shm", "-wal"):
        try:
            Path(f"{path}{suffix}").unlink(missing_ok=True)
        except PermissionError:
            pass


_remove_sqlite_files(TEST_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "admin123"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ALLOW_DEFAULT_ADMIN_PASSWORD"] = "1"

from app.core.utils import init_app  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def _reset_route_contract_cache() -> None:
    for module_name in ("test_route_contracts", "tests.test_route_contracts"):
        module = sys.modules.get(module_name)
        if module is not None:
            module.ADMIN_HEADERS = None
            module.USER_HEADERS = None


def _clear_database() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))


@pytest.fixture(autouse=True)
def isolated_app_database():
    app.dependency_overrides.clear()
    _reset_route_contract_cache()
    _clear_database()
    init_app()
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _cleanup() -> None:
    engine.dispose()
    _remove_sqlite_files(TEST_DB)


atexit.register(_cleanup)
