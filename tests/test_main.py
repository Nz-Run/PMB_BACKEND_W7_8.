
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import User
from app.security import hash_password


SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_user(client):
    db = TestingSessionLocal()

    admin = User(
        name="Admin Test",
        email="admin_test@example.com",
        password=hash_password("AdminTest123"),
        role="admin"
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)
    db.close()

    return admin


@pytest.fixture
def admin_token(client, admin_user):
    response = client.post("/login", json={
        "email": "admin_test@example.com",
        "password": "AdminTest123"
    })

    assert response.status_code == 200

    return response.json()["access_token"]


def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200


def test_register_success(client):
    response = client.post("/register", json={
        "name": "Mahasiswa Test",
        "email": "test@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    assert response.status_code == 200
    assert response.json()["status_pendaftaran"] == "menunggu"


def test_register_duplicate_email(client):
    data = {
        "name": "Mahasiswa Test",
        "email": "test@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    }

    client.post("/register", json=data)
    response = client.post("/register", json=data)

    assert response.status_code in [400, 409]


def test_login_success(client):
    client.post("/register", json={
        "name": "Mahasiswa Test",
        "email": "test@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    response = client.post("/login", json={
        "email": "test@example.com",
        "password": "Belajar123"
    })

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_invalid_password(client):
    client.post("/register", json={
        "name": "Mahasiswa Test",
        "email": "test@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    response = client.post("/login", json={
        "email": "test@example.com",
        "password": "SalahPassword"
    })

    assert response.status_code == 401


def test_admin_statistics_success(client, admin_token):
    response = client.get(
        "/admin/statistics",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["total_pendaftar"] == 0
    assert response.json()["statistik_status"] == []


def test_logout_success(client):
    client.post("/register", json={
        "name": "Mahasiswa Logout",
        "email": "logout@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    login_response = client.post("/login", json={
        "email": "logout@example.com",
        "password": "Belajar123"
    })

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = client.post("/logout", headers=headers)

    assert logout_response.status_code == 200
    assert logout_response.json()["message"] == "Logout berhasil"

    profile_response = client.get("/me", headers=headers)

    assert profile_response.status_code == 401


def test_get_me_success(client):
    client.post("/register", json={
        "name": "Mahasiswa Profile",
        "email": "profile@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    login_response = client.post("/login", json={
        "email": "profile@example.com",
        "password": "Belajar123"
    })

    token = login_response.json()["access_token"]

    response = client.get(
        "/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "profile@example.com"


def test_admin_statistics_forbidden(client):
    client.post("/register", json={
        "name": "Mahasiswa Biasa",
        "email": "biasa@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    login_response = client.post("/login", json={
        "email": "biasa@example.com",
        "password": "Belajar123"
    })

    token = login_response.json()["access_token"]

    response = client.get(
        "/admin/statistics",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_admin_get_registrations(client, admin_token):
    client.post("/register", json={
        "name": "Pendaftar Test",
        "email": "pendaftar@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    response = client.get(
        "/admin/registrations",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_admin_accept_registration(client, admin_token):
    register_response = client.post("/register", json={
        "name": "Calon Mahasiswa",
        "email": "calon@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    registration_id = register_response.json()["registration_id"]

    response = client.put(
        f"/admin/registrations/{registration_id}/decision?status=diterima",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["status_pendaftaran"] == "diterima"


def test_admin_reject_registration(client, admin_token):
    register_response = client.post("/register", json={
        "name": "Calon Mahasiswa Ditolak",
        "email": "ditolak@example.com",
        "password": "Belajar123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika"
    })

    registration_id = register_response.json()["registration_id"]

    response = client.put(
        f"/admin/registrations/{registration_id}/decision?status=ditolak",
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["status_pendaftaran"] == "ditolak"
