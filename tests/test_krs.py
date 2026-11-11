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


def test_submit_creates_log_and_pa_notification(db):
    from app.models import KRSLog, KRSNotification

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
    from app.models import KRSLog, KRSNotification

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
    from app.models import KRSLog, KRSNotification

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
