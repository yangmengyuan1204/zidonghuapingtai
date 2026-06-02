from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), nullable=False, unique=True)
    password = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False)
    create_time = Column(DateTime, nullable=False)


class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    desc = Column("desc", Text, nullable=True)
    create_time = Column(DateTime, nullable=False)


class Env(Base):
    __tablename__ = "env"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False)
    env_name = Column(String(120), nullable=False)
    base_url = Column(String(500), nullable=False)
    global_headers = Column(Text, nullable=True)
    global_vars = Column(Text, nullable=True)
    timeout = Column(Integer, nullable=True)


class ApiCase(Base):
    __tablename__ = "api_case"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False)
    env_id = Column(Integer, nullable=False)
    case_name = Column(String(160), nullable=False)
    method = Column(String(16), nullable=False)
    url = Column(String(500), nullable=False)
    headers = Column(Text, nullable=True)
    params = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    assert_rule = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    create_time = Column(DateTime, nullable=False)


class UiCase(Base):
    __tablename__ = "ui_case"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False)
    case_name = Column(String(160), nullable=False)
    page_url = Column(String(500), nullable=False)
    steps = Column(Text, nullable=True)
    timeout = Column(Integer, nullable=True)
    status = Column(String(32), nullable=True)
    create_time = Column(DateTime, nullable=False)


class TestRecord(Base):
    __tablename__ = "test_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_type = Column(String(16), nullable=False)
    case_id = Column(Integer, nullable=False)
    result = Column(String(32), nullable=False)
    log = Column(Text, nullable=True)
    screenshot = Column(String(500), nullable=True)
    report_path = Column(String(500), nullable=True)
    execute_time = Column(DateTime, nullable=False)
