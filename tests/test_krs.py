from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    User,
    Applicant,
    MataKuliah,
    Prasyarat,
    SkalaNilai,
    KRS,
    KRSDetail,
    KRSLog,
    KRSNotification,
)
from app.services.krs_manager import KRSManager


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSession()

    user = User(
        name="Mahasiswa Test",
        email="mahasiswa@test.com",
        password="password-test",
        role="mahasiswa",
    )
    session.add(user)
    session.flush()

    session.add(
        Applicant(
            user_id=user.id,
            nim="261640001",
            tanggal_lahir=date(2005, 1, 1),
            alamat="Jakarta",
        )
    )

    session.add_all([
        SkalaNilai(nilai="A", bobot=4.0),
        SkalaNilai(nilai="B", bobot=3.0),
        SkalaNilai(nilai="C", bobot=2.0),
        SkalaNilai(nilai="D", bobot=1.0),
        SkalaNilai(nilai="E", bobot=0.0),
    ])
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def tambah_mk(db, kode, nama, sks, hari, mulai, selesai):
    course = MataKuliah(
        kode_mk=kode,
        nama_mk=nama,
        sks=sks,
        hari=hari,
        jam_mulai=time(*mulai),
        jam_selesai=time(*selesai),
    )
    db.add(course)
    db.commit()
    return course


def buat_dosen_pa(db):
    dosen = User(
        name="Dosen PA Test",
        email="dosenpa@test.com",
        password="password-test",
        role="dosen_pa",
    )
    db.add(dosen)
    db.commit()
    return dosen


# ==================================================
# TEST ADD COURSE
# ==================================================

def test_add_course_success(db):
    tambah_mk(db, "IF101", "Algoritma", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    result = manager.add_course("261640001", "20261", "IF101")

    assert result.ok is True

    krs = db.query(KRS).filter_by(
        nim="261640001",
        semester="20261",
    ).first()

    assert krs is not None
    assert len(krs.details) == 1


def test_maximum_sks_24(db):
    manager = KRSManager(db)

    for i in range(6):
        kode = f"IF10{i}"
        tambah_mk(
            db, kode, f"Mata Kuliah {i}",
            4, i + 1, (8, 0), (9, 0),
        )

        result = manager.add_course("261640001", "20261", kode)
        assert result.ok is True

    tambah_mk(
        db, "IF109", "Mata Kuliah Ketujuh",
        4, 1, (10, 0), (11, 0),
    )

    result = manager.add_course("261640001", "20261", "IF109")

    assert result.ok is False
    assert "24" in result.message


def test_schedule_conflict(db):
    tambah_mk(db, "IF101", "Algoritma", 3, 1, (8, 0), (10, 0))
    tambah_mk(db, "IF102", "Basis Data", 3, 1, (9, 0), (11, 0))

    manager = KRSManager(db)

    first = manager.add_course("261640001", "20261", "IF101")
    second = manager.add_course("261640001", "20261", "IF102")

    assert first.ok is True
    assert second.ok is False
    assert "bentrok" in second.message.lower()


# ==================================================
# TEST PREREQUISITE
# ==================================================

def test_prerequisite_not_passed(db):
    tambah_mk(db, "IF101", "Algoritma", 3, 1, (8, 0), (10, 0))
    tambah_mk(db, "IF102", "Struktur Data", 3, 2, (8, 0), (10, 0))

    db.add(Prasyarat(
        kode_mk="IF102",
        kode_prasyarat="IF101",
    ))
    db.commit()

    manager = KRSManager(db)
    result = manager.add_course("261640001", "20261", "IF102")

    assert result.ok is False
    assert "prasyarat" in result.message.lower()


def test_prerequisite_rejected_if_previous_krs_not_approved(db):
    tambah_mk(db, "IF101", "Algoritma", 3, 1, (8, 0), (10, 0))
    tambah_mk(db, "IF102", "Struktur Data", 3, 2, (8, 0), (10, 0))

    db.add(Prasyarat(
        kode_mk="IF102",
        kode_prasyarat="IF101",
    ))

    previous_krs = KRS(
        nim="261640001",
        semester="20260",
        status="draft",
    )
    db.add(previous_krs)
    db.flush()

    db.add(KRSDetail(
        krs_id=previous_krs.id,
        kode_mk="IF101",
        nilai="A",
    ))
    db.commit()

    manager = KRSManager(db)
    result = manager.add_course("261640001", "20261", "IF102")

    assert result.ok is False
    assert "prasyarat" in result.message.lower()


def test_prerequisite_accepted_if_previous_krs_approved(db):
    tambah_mk(db, "IF101", "Algoritma", 3, 1, (8, 0), (10, 0))
    tambah_mk(db, "IF102", "Struktur Data", 3, 2, (8, 0), (10, 0))

    db.add(Prasyarat(
        kode_mk="IF102",
        kode_prasyarat="IF101",
    ))

    previous_krs = KRS(
        nim="261640001",
        semester="20260",
        status="approved",
    )
    db.add(previous_krs)
    db.flush()

    db.add(KRSDetail(
        krs_id=previous_krs.id,
        kode_mk="IF101",
        nilai="C",
    ))
    db.commit()

    manager = KRSManager(db)
    result = manager.add_course("261640001", "20261", "IF102")

    assert result.ok is True


# ==================================================
# TEST SUBMIT, APPROVE, DAN REVISE
# ==================================================

def test_submit_creates_log_and_pa_notification(db):
    tambah_mk(
        db, "IF201", "Pemrograman", 3, 1, (8, 0), (10, 0)
    )
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.flush()

    db.add(KRSDetail(
        krs_id=krs.id,
        kode_mk="IF201",
    ))
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is True

    db.refresh(krs)
    assert krs.status == "submitted"
    assert krs.submitted_at is not None

    log = db.query(KRSLog).filter_by(
        krs_id=krs.id,
        action="submit",
    ).first()

    notification = db.query(KRSNotification).filter_by(
        krs_id=krs.id,
        recipient_id=dosen.id,
    ).first()

    assert log is not None
    assert log.from_status == "draft"
    assert log.to_status == "submitted"
    assert notification is not None


def test_approve_creates_log_and_student_notification(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.approve_krs(
        "261640001",
        "20261",
        str(dosen.id),
    )

    assert result.ok is True

    db.refresh(krs)
    assert krs.status == "approved"
    assert krs.approved_at is not None

    log = db.query(KRSLog).filter_by(
        krs_id=krs.id,
        action="approve",
    ).first()

    notification = db.query(KRSNotification).filter_by(
        krs_id=krs.id,
        recipient_id=1,
    ).first()

    assert log is not None
    assert log.from_status == "submitted"
    assert log.to_status == "approved"
    assert notification is not None
    assert "disetujui" in notification.message.lower()


def test_revise_creates_log_and_student_notification(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    catatan = "Mohon perbaiki mata kuliah yang dipilih."

    result = manager.revise_krs(
        "261640001",
        "20261",
        str(dosen.id),
        catatan,
    )

    assert result.ok is True

    db.refresh(krs)
    assert krs.status == "revision"
    assert krs.revision_note == catatan

    log = db.query(KRSLog).filter_by(
        krs_id=krs.id,
        action="revise",
    ).first()

    notification = db.query(KRSNotification).filter_by(
        krs_id=krs.id,
        recipient_id=1,
    ).first()

    assert log is not None
    assert log.from_status == "submitted"
    assert log.to_status == "revision"
    assert log.note == catatan
    assert notification is not None
    assert catatan in notification.message


# ==================================================
# TEST REMOVE COURSE
# ==================================================

def test_remove_course_success(db):
    tambah_mk(db, "IF301", "Pemrograman", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    added = manager.add_course("261640001", "20261", "IF301")
    assert added.ok is True

    result = manager.remove_course("261640001", "20261", "IF301")

    assert result.ok is True
    assert "berhasil dihapus" in result.message.lower()

    krs = db.query(KRS).filter_by(
        nim="261640001",
        semester="20261",
    ).first()

    assert len(krs.details) == 0


def test_remove_course_krs_not_found(db):
    manager = KRSManager(db)

    result = manager.remove_course("261640001", "20261", "IF301")

    assert result.ok is False
    assert "KRS tidak ditemukan" in result.message


def test_remove_course_rejected_if_status_not_editable(db):
    tambah_mk(db, "IF302", "Basis Data", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    manager.add_course("261640001", "20261", "IF302")

    krs = db.query(KRS).filter_by(
        nim="261640001",
        semester="20261",
    ).first()
    krs.status = "submitted"
    db.commit()

    result = manager.remove_course("261640001", "20261", "IF302")

    assert result.ok is False
    assert "draft atau revision" in result.message


def test_remove_course_not_in_krs(db):
    tambah_mk(db, "IF303", "Jaringan Komputer", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    manager.add_course("261640001", "20261", "IF303")

    result = manager.remove_course("261640001", "20261", "IF999")

    assert result.ok is False
    assert "tidak ditemukan dalam KRS" in result.message


def test_remove_course_student_account_not_found(db):
    tambah_mk(db, "IF304", "Sistem Operasi", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    manager.add_course("261640001", "20261", "IF304")

    applicant = db.query(Applicant).filter_by(
        nim="261640001"
    ).first()
    db.delete(applicant)
    db.commit()

    result = manager.remove_course("261640001", "20261", "IF304")

    assert result.ok is False
    assert "Akun mahasiswa tidak ditemukan" in result.message


# ==================================================
# TEST VALIDATE KRS
# ==================================================

def test_validate_krs_not_found(db):
    manager = KRSManager(db)

    results = manager.validate_krs("261640001", "20261")

    assert len(results) == 1
    assert results[0].ok is False
    assert "KRS tidak ditemukan" in results[0].message


def test_validate_empty_krs(db):
    manager = KRSManager(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
    )
    db.add(krs)
    db.commit()

    results = manager.validate_krs("261640001", "20261")

    assert len(results) == 1
    assert results[0].ok is False
    assert "KRS tidak boleh kosong" in results[0].message


def test_validate_valid_krs(db):
    tambah_mk(db, "IF401", "Algoritma", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    added = manager.add_course("261640001", "20261", "IF401")
    assert added.ok is True

    results = manager.validate_krs("261640001", "20261")

    assert len(results) == 1
    assert results[0].ok is True
    assert "semua mata kuliah" in results[0].message.lower()


def test_validate_krs_with_invalid_course(db):
    tambah_mk(db, "IF401", "Algoritma", 3, 1, (8, 0), (10, 0))
    tambah_mk(db, "IF402", "Basis Data", 3, 2, (8, 0), (10, 0))

    db.add(Prasyarat(
        kode_mk="IF402",
        kode_prasyarat="IF401",
    ))
    db.commit()

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
    )
    db.add(krs)
    db.flush()

    db.add(KRSDetail(
        krs_id=krs.id,
        kode_mk="IF402",
    ))
    db.commit()

    manager = KRSManager(db)
    results = manager.validate_krs("261640001", "20261")

    assert any(result.ok is False for result in results)
    assert any(
        "prasyarat" in result.message.lower()
        for result in results
    )

# ==================================================
# TEST ERROR HANDLING SUBMIT KRS
# ==================================================

def test_submit_krs_not_found(db):
    manager = KRSManager(db)

    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "KRS tidak ditemukan" in result.message


def test_submit_krs_without_valid_pa(db):
    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=None,
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "Dosen PA" in result.message


def test_submit_krs_invalid_course(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.flush()

    # KRS sengaja dibiarkan kosong
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "KRS belum valid" in result.message


# ==================================================
# TEST ERROR HANDLING APPROVE KRS
# ==================================================

def test_approve_krs_invalid_dosen(db):
    manager = KRSManager(db)

    result = manager.approve_krs(
        "261640001",
        "20261",
        "99999",
    )

    assert result.ok is False
    assert "Akun dosen PA tidak valid" in result.message


def test_approve_krs_not_found(db):
    dosen = buat_dosen_pa(db)
    manager = KRSManager(db)

    result = manager.approve_krs(
        "261640001",
        "20261",
        str(dosen.id),
    )

    assert result.ok is False
    assert "KRS tidak ditemukan" in result.message


def test_approve_krs_wrong_status(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.approve_krs(
        "261640001",
        "20261",
        str(dosen.id),
    )

    assert result.ok is False
    assert "belum diajukan" in result.message


# ==================================================
# TEST ERROR HANDLING REVISE KRS
# ==================================================

def test_revise_krs_invalid_dosen(db):
    manager = KRSManager(db)

    result = manager.revise_krs(
        "261640001",
        "20261",
        "99999",
        "Perbaiki KRS",
    )

    assert result.ok is False
    assert "Akun dosen PA tidak valid" in result.message


def test_revise_krs_empty_note(db):
    dosen = buat_dosen_pa(db)
    manager = KRSManager(db)

    result = manager.revise_krs(
        "261640001",
        "20261",
        str(dosen.id),
        "   ",
    )

    assert result.ok is False
    assert "Catatan revisi wajib diisi" in result.message


def test_revise_krs_not_found(db):
    dosen = buat_dosen_pa(db)
    manager = KRSManager(db)

    result = manager.revise_krs(
        "261640001",
        "20261",
        str(dosen.id),
        "Mohon perbaiki KRS",
    )

    assert result.ok is False
    assert "KRS tidak ditemukan" in result.message


def test_revise_krs_wrong_status(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.revise_krs(
        "261640001",
        "20261",
        str(dosen.id),
        "Mohon perbaiki KRS",
    )

    assert result.ok is False
    assert "belum diajukan" in result.message

# ==================================================
# TEST TAMBAHAN ADD COURSE
# ==================================================

def test_add_course_rejected_if_krs_not_editable(db):
    tambah_mk(db, "IF501", "Pemrograman", 3, 1, (8, 0), (10, 0))

    manager = KRSManager(db)
    manager.add_course("261640001", "20261", "IF501")

    krs = db.query(KRS).filter_by(
        nim="261640001",
        semester="20261",
    ).first()

    krs.status = "submitted"
    db.commit()

    result = manager.add_course("261640001", "20261", "IF501")

    assert result.ok is False
    assert "draft atau revision" in result.message


def test_add_course_not_found(db):
    manager = KRSManager(db)

    result = manager.add_course(
        "261640001",
        "20261",
        "IF999",
    )

    assert result.ok is False
    assert "Mata kuliah tidak ditemukan" in result.message


def test_add_course_student_account_not_found(db):
    tambah_mk(db, "IF502", "Basis Data", 3, 1, (8, 0), (10, 0))

    applicant = db.query(Applicant).filter_by(
        nim="261640001"
    ).first()

    db.delete(applicant)
    db.commit()

    manager = KRSManager(db)

    result = manager.add_course(
        "261640001",
        "20261",
        "IF502",
    )

    assert result.ok is False
    assert "Akun mahasiswa tidak ditemukan" in result.message
# ==================================================
# TEST ERROR HANDLING ADD COURSE
# ==================================================

def test_add_course_integrity_error(db, monkeypatch):
    tambah_mk(db, "IF503", "Pemrograman Lanjut", 3, 1, (8, 0), (10, 0))

    def gagal_commit():
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    result = manager.add_course(
        "261640001",
        "20261",
        "IF503",
    )

    assert result.ok is False
    assert "sudah terdaftar" in result.message


def test_add_course_stale_data_error(db, monkeypatch):
    tambah_mk(db, "IF504", "Jaringan Komputer", 3, 1, (8, 0), (10, 0))

    def gagal_commit():
        raise StaleDataError("Konflik versi")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    result = manager.add_course(
        "261640001",
        "20261",
        "IF504",
    )

    assert result.ok is False
    assert "Konflik versi KRS" in result.message


def test_add_course_general_exception(db, monkeypatch):
    tambah_mk(db, "IF505", "Sistem Operasi", 3, 1, (8, 0), (10, 0))

    def gagal_commit():
        raise RuntimeError("Simulasi error")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    with pytest.raises(RuntimeError, match="Simulasi error"):
        manager.add_course(
            "261640001",
            "20261",
            "IF505",
        )
        # ==================================================
# TEST TAMBAHAN SUBMIT KRS
# ==================================================

def test_submit_krs_transition_not_allowed(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "Transisi KRS tidak diizinkan" in result.message


def test_submit_krs_student_account_not_found(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    applicant = db.query(Applicant).filter_by(
        nim="261640001"
    ).first()

    db.delete(applicant)
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "Akun mahasiswa tidak ditemukan" in result.message


def test_submit_krs_pa_not_found(db):
    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa="99999",
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "Dosen PA" in result.message


def test_submit_krs_invalid_details(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "KRS belum valid" in result.message
    # ==================================================
# TEST TAMBAHAN APPROVE KRS
# ==================================================

def test_approve_krs_not_student_of_pa(db):
    dosen = buat_dosen_pa(db)

    dosen_lain = User(
        name="Dosen PA Lain",
        email="dosenlain@test.com",
        password="password-test",
        role="dosen_pa",
    )
    db.add(dosen_lain)
    db.commit()

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)

    result = manager.approve_krs(
        "261640001",
        "20261",
        str(dosen_lain.id),
    )

    assert result.ok is False
    assert "bukan mahasiswa bimbingan" in result.message
def test_revise_krs_student_account_not_found(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261649999",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)

    result = manager.revise_krs(
        "261649999",
        "20261",
        str(dosen.id),
        "Mohon perbaiki mata kuliah",
    )

    assert result.ok is False
    assert "Akun mahasiswa tidak ditemukan" in result.message
def test_submit_krs_stale_data_error(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    tambah_mk(db, "IF901", "Algoritma", 3, 1, (8, 0), (10, 0))

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    db.add(KRSDetail(krs_id=krs.id, kode_mk="IF901"))
    db.commit()

    def gagal_commit():
        raise StaleDataError("Konflik versi")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)
    result = manager.submit_krs("261640001", "20261")

    assert result.ok is False
    assert "Konflik versi KRS" in result.message


def test_submit_krs_general_exception(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    tambah_mk(db, "IF902", "Basis Data", 3, 1, (8, 0), (10, 0))

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    db.add(KRSDetail(krs_id=krs.id, kode_mk="IF902"))
    db.commit()

    def gagal_commit():
        raise RuntimeError("Simulasi submit error")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    with pytest.raises(RuntimeError, match="Simulasi submit error"):
        manager.submit_krs("261640001", "20261")
def test_approve_krs_stale_data_error(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    def gagal_commit():
        raise StaleDataError("Konflik versi")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)
    result = manager.approve_krs(
        "261640001", "20261", str(dosen.id)
    )

    assert result.ok is False
    assert "Konflik versi KRS" in result.message


def test_approve_krs_general_exception(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    def gagal_commit():
        raise RuntimeError("Simulasi approve error")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    with pytest.raises(RuntimeError, match="Simulasi approve error"):
        manager.approve_krs(
            "261640001", "20261", str(dosen.id)
        )
def test_revise_krs_stale_data_error(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    def gagal_commit():
        raise StaleDataError("Konflik versi")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)
    result = manager.revise_krs(
        "261640001",
        "20261",
        str(dosen.id),
        "Perbaiki KRS",
    )

    assert result.ok is False
    assert "Konflik versi KRS" in result.message


def test_revise_krs_general_exception(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    def gagal_commit():
        raise RuntimeError("Simulasi revise error")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    with pytest.raises(RuntimeError, match="Simulasi revise error"):
        manager.revise_krs(
            "261640001",
            "20261",
            str(dosen.id),
            "Perbaiki KRS",
        )
def test_remove_course_stale_data_error(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    tambah_mk(
        db, "IF902", "Basis Data Test", 3,
        1, (8, 0), (10, 0)
    )

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    db.add(KRSDetail(krs_id=krs.id, kode_mk="IF902"))
    db.commit()

    def gagal_commit():
        raise StaleDataError("Konflik versi")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)
    result = manager.remove_course(
        "261640001", "20261", "IF902"
    )

    assert result.ok is False
    assert "Konflik versi KRS" in result.message
def test_remove_course_general_exception(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    tambah_mk(
        db, "IF903", "Pemrograman Test", 3,
        1, (8, 0), (10, 0)
    )

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    db.add(KRSDetail(krs_id=krs.id, kode_mk="IF903"))
    db.commit()

    def gagal_commit():
        raise RuntimeError("Simulasi remove error")

    monkeypatch.setattr(db, "commit", gagal_commit)

    manager = KRSManager(db)

    with pytest.raises(RuntimeError, match="Simulasi remove error"):
        manager.remove_course("261640001", "20261", "IF903")
def test_approve_krs_student_account_not_found(db):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261649998",
        semester="20261",
        status="submitted",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    manager = KRSManager(db)

    result = manager.approve_krs(
        "261649998",
        "20261",
        str(dosen.id),
    )

    assert result.ok is False
    assert "Akun mahasiswa tidak ditemukan" in result.message
def test_bump_version_stale_data_error(db, monkeypatch):
    dosen = buat_dosen_pa(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="draft",
        dosen_pa=str(dosen.id),
    )
    db.add(krs)
    db.commit()

    class QueryPalsu:
        def filter(self, *args):
            return self

        def update(self, *args, **kwargs):
            return 0

    monkeypatch.setattr(
        db,
        "query",
        lambda model: QueryPalsu(),
    )

    manager = KRSManager(db)

    with pytest.raises(
        StaleDataError,
        match="Versi KRS sudah berubah",
    ):
        manager._bump_version(krs)
