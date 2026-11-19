
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, Applicant, Registration, Billing
from app.services.billing_service import BillingService


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def accepted_student(db):
    user = User(
        name="Mahasiswa Test",
        email="billing_test@example.com",
        password="password_test",
        role="mahasiswa"
    )

    db.add(user)
    db.flush()

    applicant = Applicant(
        user_id=user.id,
        nim="26164001",
        tanggal_lahir=date(2005, 5, 10),
        alamat="Jakarta Selatan"
    )

    db.add(applicant)
    db.flush()

    registration = Registration(
        applicant_id=applicant.id,
        program_studi="Teknik Informatika",
        status_pendaftaran="diterima"
    )

    db.add(registration)
    db.commit()

    return applicant


def test_get_tarif_teknik():
    assert BillingService.get_tarif(
        "Teknik Informatika"
    ) == 5_000_000


def test_get_tarif_ekonomi():
    assert BillingService.get_tarif(
        "Ekonomi"
    ) == 4_000_000


def test_get_tarif_unknown():
    with pytest.raises(ValueError):
        BillingService.get_tarif("Kedokteran")


def test_generate_billing_success(db, accepted_student):
    tanggal_mulai = date.today()

    result = BillingService.generate_billing(
        db=db,
        semester="20261",
        tanggal_mulai=tanggal_mulai
    )

    billing = db.scalar(
        select(Billing).where(
            Billing.nim == accepted_student.nim
        )
    )

    assert billing is not None
    assert billing.total_amount == 5_000_000
    assert billing.status == "unpaid"
    assert billing.due_date == tanggal_mulai + timedelta(days=14)
    assert result["total_tagihan_dibuat"] == 1


def test_generate_billing_prevents_duplicate(
    db,
    accepted_student
):
    for _ in range(2):
        BillingService.generate_billing(
            db=db,
            semester="20261",
            tanggal_mulai=date.today()
        )

    total = db.scalar(
        select(func.count()).select_from(Billing)
    )

    assert total == 1


def test_calculate_late_fee():
    billing = Billing(
        nim="26164001",
        semester="20261",
        total_amount=5_000_000,
        paid_amount=0,
        fine_amount=0,
        due_date=date(2026, 11, 10),
        status="unpaid"
    )

    result = BillingService.calculate_late_fee(
        billing,
        date(2026, 11, 13)
    )

    assert result == 30_000


def test_update_billing_status_overdue(db, accepted_student):
    billing = Billing(
        nim=accepted_student.nim,
        semester="20261",
        total_amount=5_000_000,
        paid_amount=0,
        fine_amount=0,
        due_date=date.today() - timedelta(days=3),
        status="unpaid"
    )

    db.add(billing)
    db.commit()
    db.refresh(billing)

    result = BillingService.update_billing_status(
        db=db,
        billing_id=billing.id
    )

    assert result.status == "overdue"
    assert result.fine_amount == 30_000
