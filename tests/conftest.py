import os
import re

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.section import Section
from app.models.student import Student
from app.models.user import Role, User
from app.security import hash_password

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seed_users(db_session):
    admin = User(
        email="admin@test.local",
        full_name="Test Admin",
        password_hash=hash_password("admin-secret-pw-123"),
        role=Role.admin,
        is_active=True,
    )
    faculty_a = User(
        email="facultya@test.local",
        full_name="Faculty A",
        password_hash=hash_password("faculty-secret-pw-1"),
        role=Role.faculty,
        is_active=True,
    )
    faculty_b = User(
        email="facultyb@test.local",
        full_name="Faculty B",
        password_hash=hash_password("faculty-secret-pw-2"),
        role=Role.faculty,
        is_active=True,
    )
    inactive = User(
        email="inactive@test.local",
        full_name="Inactive User",
        password_hash=hash_password("inactive-secret-pw"),
        role=Role.faculty,
        is_active=False,
    )
    db_session.add_all([admin, faculty_a, faculty_b, inactive])
    db_session.commit()
    return {"admin": admin, "faculty_a": faculty_a, "faculty_b": faculty_b, "inactive": inactive}


def login(client: TestClient, email: str, password: str) -> None:
    token = csrf_from(client)
    resp = client.post(
        "/login",
        data={"email": email, "password": password, "_csrf": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text


def csrf_from(client: TestClient, path: str = "/login") -> str:
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    match = re.search(r'name="_csrf" value="([^"]+)"', resp.text)
    assert match, "csrf token not found in page"
    return match.group(1)


def make_section(db_session, *, name="Section A", year_level=1, created_by=1, active=True) -> Section:
    section = Section(name=name, year_level=year_level, is_active=active, created_by=created_by)
    db_session.add(section)
    db_session.commit()
    db_session.refresh(section)
    return section


def make_student(
    db_session,
    *,
    first_name="Juan",
    last_name="Dela Cruz",
    section_id: int,
    created_by: int,
    deleted_at=None,
    created_at=None,
) -> Student:
    student = Student(
        first_name=first_name,
        last_name=last_name,
        section_id=section_id,
        created_by=created_by,
        deleted_at=deleted_at,
    )
    if created_at is not None:
        student.created_at = created_at
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student
