import pytest
from datetime import date, time

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    User,
    Applicant,
    MataKuliah,
    KRS,
    KRSDetail,
    SkalaNilai,
    Kehadiran,
    RiwayatNilai,
)
from app.security import hash_password
from app.services.grade_service import GradeService


@pytest.fixture
def grade_data():
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
        name="Mahasiswa Test",
        email="mahasiswa_grade@example.com",
        password=hash_password("Mahasiswa123"),
        role="mahasiswa"
    )
    admin = User(
        name="Admin Grade",
        email="admin_grade@example.com",
        password=hash_password("Admin123"),
        role="admin"
    )

    db.add_all([mahasiswa, admin])
    db.flush()

    applicant = Applicant(
        user_id=mahasiswa.id,
        nim="261649999",
        tanggal_lahir=date(2005, 5, 10),
        alamat="Jakarta Selatan"
    )
    db.add(applicant)
    db.flush()

    mata_kuliah_1 = MataKuliah(
        kode_mk="TST101",
        nama_mk="Pemrograman Test",
        sks=4,
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0)
    )
    mata_kuliah_2 = MataKuliah(
        kode_mk="TST102",
        nama_mk="Basis Data Test",
        sks=3,
        hari=2,
        jam_mulai=time(10, 0),
        jam_selesai=time(12, 0)
    )

    db.add_all([mata_kuliah_1, mata_kuliah_2])

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

    detail_1 = KRSDetail(
        krs_id=krs.id,
        kode_mk="TST101"
    )
    detail_2 = KRSDetail(
        krs_id=krs.id,
        kode_mk="TST102"
    )

    db.add_all([detail_1, detail_2])
    db.commit()

    data = {
        "db": db,
        "admin_id": admin.id,
        "nim": applicant.nim,
        "krs": krs,
        "detail_1": detail_1,
        "detail_2": detail_2,
    }

    yield data

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_input_kehadiran_success(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    hasil = GradeService.input_kehadiran(
        db, detail_id, 14, 12
    )

    assert hasil.total_pertemuan == 14
    assert hasil.jumlah_hadir == 12


def test_input_kehadiran_update(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    GradeService.input_kehadiran(db, detail_id, 14, 10)
    hasil = GradeService.input_kehadiran(db, detail_id, 14, 12)

    assert hasil.total_pertemuan == 14
    assert hasil.jumlah_hadir == 12
    assert db.query(Kehadiran).count() == 1


def test_input_kehadiran_detail_not_found(grade_data):
    with pytest.raises(HTTPException) as exc:
        GradeService.input_kehadiran(
            grade_data["db"], 9999, 14, 12
        )

    assert exc.value.status_code == 404


def test_input_kehadiran_invalid_data(grade_data):
    with pytest.raises(HTTPException) as exc:
        GradeService.input_kehadiran(
            grade_data["db"],
            grade_data["detail_1"].id,
            10,
            12
        )

    assert exc.value.status_code == 400


def test_input_nilai_success(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    GradeService.input_kehadiran(db, detail_id, 14, 12)

    hasil = GradeService.input_nilai(
        db,
        detail_id,
        "A",
        grade_data["admin_id"]
    )

    assert hasil.nilai == "A"

    riwayat = db.query(RiwayatNilai).filter_by(
        krs_detail_id=detail_id
    ).first()

    assert riwayat is not None
    assert riwayat.nilai_lama is None
    assert riwayat.nilai_baru == "A"
    assert riwayat.changed_by == grade_data["admin_id"]


def test_input_nilai_attendance_below_75_percent(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    GradeService.input_kehadiran(db, detail_id, 14, 10)

    with pytest.raises(HTTPException) as exc:
        GradeService.input_nilai(
            db, detail_id, "A", grade_data["admin_id"]
        )

    assert exc.value.status_code == 400
    assert "75%" in exc.value.detail


def test_input_nilai_without_attendance(grade_data):
    with pytest.raises(HTTPException) as exc:
        GradeService.input_nilai(
            grade_data["db"],
            grade_data["detail_1"].id,
            "A",
            grade_data["admin_id"]
        )

    assert exc.value.status_code == 400
    assert "kehadiran" in exc.value.detail.lower()


def test_input_nilai_invalid_scale(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    GradeService.input_kehadiran(db, detail_id, 14, 12)

    with pytest.raises(HTTPException) as exc:
        GradeService.input_nilai(
            db, detail_id, "Z", grade_data["admin_id"]
        )

    assert exc.value.status_code == 400


def test_input_nilai_unapproved_krs(grade_data):
    db = grade_data["db"]
    detail_id = grade_data["detail_1"].id

    grade_data["krs"].status = "draft"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        GradeService.input_nilai(
            db, detail_id, "A", grade_data["admin_id"]
        )

    assert exc.value.status_code == 400


def test_hitung_ipk_success(grade_data):
    db = grade_data["db"]

    GradeService.input_kehadiran(
        db, grade_data["detail_1"].id, 14, 12
    )
    GradeService.input_kehadiran(
        db, grade_data["detail_2"].id, 14, 12
    )

    GradeService.input_nilai(
        db, grade_data["detail_1"].id, "A",
        grade_data["admin_id"]
    )
    GradeService.input_nilai(
        db, grade_data["detail_2"].id, "B",
        grade_data["admin_id"]
    )

    ipk = GradeService.hitung_ipk(
        db, grade_data["nim"]
    )

    assert ipk == 3.57


def test_hitung_ipk_without_grades(grade_data):
    ipk = GradeService.hitung_ipk(
        grade_data["db"], grade_data["nim"]
    )

    assert ipk == 0.0
