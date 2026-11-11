from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import (
    User,
    Applicant,
    Registration,
    MataKuliah,
    SkalaNilai,
    KRS,
)
from app.security import hash_password


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all([
        SkalaNilai(nilai="A", bobot=4.0),
        SkalaNilai(nilai="B", bobot=3.0),
        SkalaNilai(nilai="C", bobot=2.0),
        SkalaNilai(nilai="D", bobot=1.0),
        SkalaNilai(nilai="E", bobot=0.0),
    ])
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(client):
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def admin_headers(client):
    db = TestingSessionLocal()

    admin = User(
        name="Admin API Test",
        email="adminapi@test.com",
        password=hash_password("AdminTest123"),
        role="admin",
    )
    db.add(admin)
    db.commit()
    db.close()

    response = client.post("/login", json={
        "email": "adminapi@test.com",
        "password": "AdminTest123",
    })

    assert response.status_code == 200

    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


@pytest.fixture
def student_data(client, admin_headers):
    registration = client.post("/register", json={
        "name": "Mahasiswa API Test",
        "email": "mahasiswaapi@test.com",
        "password": "Mahasiswa123",
        "tanggal_lahir": "2005-05-10",
        "alamat": "Jakarta Selatan",
        "program_studi": "Teknik Informatika",
    })

    assert registration.status_code == 200

    registration_id = registration.json()["registration_id"]

    decision = client.put(
        f"/admin/registrations/{registration_id}/decision?status=diterima",
        headers=admin_headers,
    )

    assert decision.status_code == 200

    nim = decision.json()["nim"]

    login = client.post("/login", json={
        "email": "mahasiswaapi@test.com",
        "password": "Mahasiswa123",
    })

    assert login.status_code == 200

    return {
        "nim": nim,
        "headers": {
            "Authorization": f"Bearer {login.json()['access_token']}"
        },
    }


@pytest.fixture
def dosen_data(client, db):
    dosen = User(
        name="Dosen PA API Test",
        email="dosenapi@test.com",
        password=hash_password("DosenTest123"),
        role="dosen_pa",
    )
    db.add(dosen)
    db.commit()
    db.refresh(dosen)

    dosen_id = dosen.id

    login = client.post("/login", json={
        "email": "dosenapi@test.com",
        "password": "DosenTest123",
    })

    assert login.status_code == 200

    return {
        "id": dosen_id,
        "headers": {
            "Authorization": f"Bearer {login.json()['access_token']}"
        },
    }


def test_complete_krs_api_flow(
    client,
    db,
    admin_headers,
    student_data,
    dosen_data,
):
    nim = student_data["nim"]
    student_headers = student_data["headers"]
    dosen_headers = dosen_data["headers"]
    dosen_id = dosen_data["id"]

    course = MataKuliah(
        kode_mk="IF201",
        nama_mk="Pemrograman Lanjut",
        sks=3,
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0),
    )
    db.add(course)
    db.commit()

    # Mahasiswa menambahkan mata kuliah.
    add_response = client.post(
        "/krs/20261/courses",
        json={"kode_mk": "IF201"},
        headers=student_headers,
    )

    assert add_response.status_code == 200

    # Admin menetapkan dosen PA.
    assign_response = client.put(
        f"/admin/krs/{nim}/20261/advisor",
        json={"dosen_pa_id": dosen_id},
        headers=admin_headers,
    )

    assert assign_response.status_code == 200

    # Mahasiswa mengajukan KRS.
    submit_response = client.post(
        "/krs/20261/submit",
        headers=student_headers,
    )

    assert submit_response.status_code == 200

    # Dosen PA menerima notifikasi pengajuan.
    dosen_notifications = client.get(
        "/notifications/me",
        headers=dosen_headers,
    )

    assert dosen_notifications.status_code == 200
    assert dosen_notifications.json()["total"] >= 1

    # Dosen PA menyetujui KRS.
    approve_response = client.post(
        f"/dosen-pa/krs/{nim}/20261/approve",
        headers=dosen_headers,
    )

    assert approve_response.status_code == 200

    # Mahasiswa melihat KRS yang telah disetujui.
    krs_response = client.get(
        "/krs/20261",
        headers=student_headers,
    )

    assert krs_response.status_code == 200
    assert krs_response.json()["status"] == "approved"

    # Mahasiswa menerima notifikasi persetujuan.
    notifications = client.get(
        "/notifications/me",
        headers=student_headers,
    )

    assert notifications.status_code == 200

    approval_notification = next(
        (
            item for item in notifications.json()["notifications"]
            if "disetujui" in item["message"].lower()
        ),
        None,
    )

    assert approval_notification is not None

    # Mahasiswa menandai notifikasi sebagai sudah dibaca.
    read_response = client.put(
        f"/notifications/{approval_notification['id']}/read",
        headers=student_headers,
    )

    assert read_response.status_code == 200
    assert read_response.json()["is_read"] is True


def test_dosen_cannot_access_student_krs(
    client,
    student_data,
    dosen_data,
):
    response = client.get(
        "/krs/20261",
        headers=dosen_data["headers"],
    )

    assert response.status_code == 403


def test_other_dosen_cannot_approve_krs(
    client,
    db,
    admin_headers,
    student_data,
    dosen_data,
):
    nim = student_data["nim"]

    # Buat dosen lain yang bukan pembimbing.
    other_dosen = User(
        name="Dosen Lain",
        email="dosenlain@test.com",
        password=hash_password("DosenTest123"),
        role="dosen_pa",
    )
    db.add(other_dosen)
    db.commit()
    db.refresh(other_dosen)

    other_dosen_id = other_dosen.id

    # Buat KRS mahasiswa.
    krs = KRS(
        nim=nim,
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen_data["id"]),
    )
    db.add(krs)
    db.commit()

    # Dosen lain mencoba menyetujui KRS.
    login = client.post("/login", json={
        "email": "dosenlain@test.com",
        "password": "DosenTest123",
    })

    assert login.status_code == 200

    other_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }

    response = client.post(
        f"/dosen-pa/krs/{nim}/20261/approve",
        headers=other_headers,
    )

    assert response.status_code == 403
