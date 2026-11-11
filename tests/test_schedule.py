
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
    Ruangan,
    Jadwal,
    KRS,
    KRSDetail,
    KRSNotification,
)
from app.services.schedule_service import ScheduleService


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

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def setup_data(db):
    mahasiswa = User(
        name="Mahasiswa Test",
        email="mahasiswa@test.com",
        password="password-test",
        role="mahasiswa",
    )

    dosen = User(
        name="Dosen Test",
        email="dosen@test.com",
        password="password-test",
        role="dosen_pa",
    )

    db.add_all([mahasiswa, dosen])
    db.flush()

    applicant = Applicant(
        user_id=mahasiswa.id,
        nim="261640001",
        tanggal_lahir=date(2005, 1, 1),
        alamat="Jakarta",
    )

    db.add(applicant)

    db.add_all([
        MataKuliah(
            kode_mk="IF101",
            nama_mk="Algoritma",
            sks=3,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
        ),
        MataKuliah(
            kode_mk="IF102",
            nama_mk="Basis Data",
            sks=3,
            hari=2,
            jam_mulai=time(10, 0),
            jam_selesai=time(12, 0),
        ),
    ])

    ruangan = Ruangan(
        kode_ruangan="R101",
        nama_ruangan="Ruang 101",
        kapasitas=40,
    )

    db.add(ruangan)
    db.commit()

    return mahasiswa, dosen, applicant, ruangan


def buat_service(db):
    service = ScheduleService(db)

    # Menghindari pengiriman notifikasi eksternal selama pengujian.
    service.notification_manager.notify_schedule_changed = (
        lambda event, data: None
    )

    return service


def test_check_capacity_success(db):
    _, _, _, ruangan = setup_data(db)
    service = buat_service(db)

    result = service.check_capacity(ruangan.id, 30)

    assert result[0] is True


def test_check_capacity_exceeded(db):
    _, _, _, ruangan = setup_data(db)
    service = buat_service(db)

    result = service.check_capacity(ruangan.id, 50)

    assert result[0] is False
    assert "Kapasitas" in result[1]


def test_create_schedule_success(db):
    _, _, _, ruangan = setup_data(db)
    service = buat_service(db)

    result = service.create_schedule(
        kode_mk="IF101",
        ruangan_id=ruangan.id,
        dosen="Dosen A",
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0),
        jumlah_peserta=30,
    )

    assert result["success"] is True

    jadwal = db.query(Jadwal).filter_by(
        kode_mk="IF101"
    ).first()

    assert jadwal is not None


def test_create_schedule_conflict(db):
    _, _, _, ruangan = setup_data(db)
    service = buat_service(db)

    service.create_schedule(
        kode_mk="IF101",
        ruangan_id=ruangan.id,
        dosen="Dosen A",
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0),
        jumlah_peserta=30,
    )

    result = service.create_schedule(
        kode_mk="IF102",
        ruangan_id=ruangan.id,
        dosen="Dosen B",
        hari=1,
        jam_mulai=time(9, 0),
        jam_selesai=time(11, 0),
        jumlah_peserta=20,
    )

    assert result["success"] is False
    assert result["message"] == "Jadwal memiliki konflik"


def test_schedule_change_marks_krs_for_review(db):
    mahasiswa, dosen, _, ruangan = setup_data(db)

    krs = KRS(
        nim="261640001",
        semester="20261",
        status="approved",
        dosen_pa=str(dosen.id),
    )

    db.add(krs)
    db.flush()

    db.add(
        KRSDetail(
            krs_id=krs.id,
            kode_mk="IF101",
        )
    )

    db.commit()

    service = buat_service(db)

    service._notify_affected_krs("IF101", "updated")

    db.refresh(krs)

    assert krs.needs_review is True

    notifications = db.query(KRSNotification).filter_by(
        krs_id=krs.id
    ).all()

    recipient_ids = {
        notification.recipient_id
        for notification in notifications
    }

    assert mahasiswa.id in recipient_ids
    assert dosen.id in recipient_ids


def test_recommend_alternatives_success(db):
    _, _, _, ruangan = setup_data(db)
    service = buat_service(db)

    result = service.create_schedule(
        kode_mk="IF101",
        ruangan_id=ruangan.id,
        dosen="Dosen A",
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0),
        jumlah_peserta=30,
    )

    schedule_id = result["schedule_id"]

    alternatives = service.recommend_alternatives(schedule_id)

    assert alternatives["success"] is True
    assert alternatives["method"] == (
        "Rule-based scheduling heuristic"
    )
    assert len(alternatives["alternatives"]) == 3

    for alternative in alternatives["alternatives"]:
        assert alternative["kapasitas"] >= 30
        assert alternative["score"] >= 0
