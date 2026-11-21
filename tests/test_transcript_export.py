
import pytest
from datetime import date, time

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
    KRS,
    KRSDetail,
    SkalaNilai,
)
from app.security import hash_password


@pytest.fixture
def transcript_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    mahasiswa = User(
        name="Mahasiswa Transcript",
        email="transcript_test@example.com",
        password=hash_password("Mahasiswa123"),
        role="mahasiswa"
    )

    admin = User(
        name="Admin Transcript",
        email="admin_transcript@example.com",
        password=hash_password("Admin123"),
        role="admin"
    )

    db.add_all([mahasiswa, admin])
    db.flush()

    applicant = Applicant(
        user_id=mahasiswa.id,
        nim="261649998",
        tanggal_lahir=date(2005, 5, 10),
        alamat="Jakarta Selatan"
    )

    db.add(applicant)
    db.flush()

    # Pastikan mahasiswa memiliki pendaftaran yang sudah diterima
    registration = Registration(
    applicant_id=applicant.id,
    program_studi="Teknik Informatika",
    status_pendaftaran="diterima"
)
    db.add(registration)

    mk = MataKuliah(
        kode_mk="TST201",
        nama_mk="Pengujian Sistem",
        sks=3,
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0)
    )

    db.add(mk)

    db.add_all([
        SkalaNilai(nilai="A", bobot=4),
        SkalaNilai(nilai="B", bobot=3),
        SkalaNilai(nilai="C", bobot=2),
        SkalaNilai(nilai="D", bobot=1),
        SkalaNilai(nilai="E", bobot=0),
    ])

    db.flush()

    krs = KRS(
        nim=applicant.nim,
        semester="20261",
        status="approved"
    )

    db.add(krs)
    db.flush()

    detail = KRSDetail(
        krs_id=krs.id,
        kode_mk="TST201"
    )

    db.add(detail)
    db.commit()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            admin_response = client.post(
                "/login",
                json={
                    "email": "admin_transcript@example.com",
                    "password": "Admin123"
                }
            )

            mahasiswa_response = client.post(
                "/login",
                json={
                    "email": "transcript_test@example.com",
                    "password": "Mahasiswa123"
                }
            )

            assert admin_response.status_code == 200, admin_response.text
            assert mahasiswa_response.status_code == 200, mahasiswa_response.text

            admin_token = admin_response.json()["access_token"]
            mahasiswa_token = mahasiswa_response.json()["access_token"]

            yield {
                "client": client,
                "admin_headers": {
                    "Authorization": f"Bearer {admin_token}"
                },
                "mahasiswa_headers": {
                    "Authorization": f"Bearer {mahasiswa_token}"
                },
                "detail_id": detail.id
            }

    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_transcript_end_to_end(transcript_client):
    client = transcript_client["client"]
    admin_headers = transcript_client["admin_headers"]
    mahasiswa_headers = transcript_client["mahasiswa_headers"]
    detail_id = transcript_client["detail_id"]

    # 1. Input kehadiran
    response = client.post(
        f"/admin/kehadiran/{detail_id}",
        json={
            "total_pertemuan": 14,
            "jumlah_hadir": 12
        },
        headers=admin_headers
    )
    assert response.status_code == 200, response.text

    # 2. Input nilai
    response = client.post(
        f"/admin/nilai/{detail_id}",
        json={"nilai": "A"},
        headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["nilai"] == "A"

    # 3. Mahasiswa melihat nilai
    response = client.get(
        "/mahasiswa/nilai",
        headers=mahasiswa_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_mata_kuliah"] == 1

    # 4. Mahasiswa melihat transkrip
    response = client.get(
        "/mahasiswa/transkrip?semester=20261",
        headers=mahasiswa_headers
    )
    assert response.status_code == 200, response.text

    transcript = response.json()

    assert transcript["total_sks"] == 3
    assert transcript["ip_semester"] == 4.0
    assert transcript["ipk"] == 4.0
    assert transcript["mata_kuliah"][0]["nilai"] == "A"

    # 5. Ekspor transkrip CSV
    response = client.get(
        "/mahasiswa/transkrip/csv?semester=20261",
        headers=mahasiswa_headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "TST201" in response.text

    # 6. Ekspor transkrip PDF
    response = client.get(
        "/mahasiswa/transkrip/pdf?semester=20261",
        headers=mahasiswa_headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
