
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    User,
    Applicant,
    Billing,
    Payment,
    PaymentMethod
)
from app.services.payment_service import PaymentService


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
def payment_data(db):
    user = User(
        name="Mahasiswa Payment Test",
        email="payment_test@example.com",
        password="password_test",
        role="mahasiswa"
    )
    db.add(user)
    db.flush()

    applicant = Applicant(
        user_id=user.id,
        nim="26164002",
        tanggal_lahir=date(2005, 5, 10),
        alamat="Jakarta Selatan"
    )
    db.add(applicant)
    db.flush()

    billing = Billing(
        nim=applicant.nim,
        semester="20261",
        total_amount=5_000_000,
        paid_amount=0,
        fine_amount=0,
        due_date=date.today() + timedelta(days=14),
        status="unpaid"
    )

    active_method = PaymentMethod(
        nama_metode="Transfer Test",
        is_active=True
    )

    inactive_method = PaymentMethod(
        nama_metode="Metode Nonaktif Test",
        is_active=False
    )

    db.add_all([billing, active_method, inactive_method])
    db.commit()

    db.refresh(billing)
    db.refresh(active_method)
    db.refresh(inactive_method)

    return {
        "billing": billing,
        "active_method": active_method,
        "inactive_method": inactive_method
    }


def test_record_payment_success(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    result = PaymentService.record_payment(
        db=db,
        billing_id=billing.id,
        payment_method_id=method.id,
        amount=2_000_000,
        transaction_id="TRX-PAYMENT-001"
    )

    assert result["jumlah_bayar"] == 2_000_000
    assert result["total_dibayar"] == 2_000_000
    assert result["sisa_tagihan"] == 3_000_000
    assert result["status_tagihan"] == "partial"


def test_record_payment_full_payment(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    result = PaymentService.record_payment(
        db=db,
        billing_id=billing.id,
        payment_method_id=method.id,
        amount=5_000_000,
        transaction_id="TRX-PAYMENT-002"
    )

    assert result["total_dibayar"] == 5_000_000
    assert result["sisa_tagihan"] == 0
    assert result["status_tagihan"] == "paid"


def test_record_payment_rejects_zero_amount(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=billing.id,
            payment_method_id=method.id,
            amount=0
        )

    assert error.value.status_code == 400


def test_record_payment_rejects_negative_amount(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=billing.id,
            payment_method_id=method.id,
            amount=-1000
        )

    assert error.value.status_code == 400


def test_record_payment_rejects_missing_billing(db, payment_data):
    method = payment_data["active_method"]

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=99999,
            payment_method_id=method.id,
            amount=100_000
        )

    assert error.value.status_code == 404


def test_record_payment_rejects_inactive_method(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["inactive_method"]

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=billing.id,
            payment_method_id=method.id,
            amount=100_000
        )

    assert error.value.status_code == 400


def test_record_payment_rejects_overpayment(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=billing.id,
            payment_method_id=method.id,
            amount=6_000_000
        )

    assert error.value.status_code == 400


def test_record_payment_rejects_duplicate_transaction(db, payment_data):
    billing = payment_data["billing"]
    method = payment_data["active_method"]

    PaymentService.record_payment(
        db=db,
        billing_id=billing.id,
        payment_method_id=method.id,
        amount=1_000_000,
        transaction_id="TRX-DUPLICATE"
    )

    with pytest.raises(HTTPException) as error:
        PaymentService.record_payment(
            db=db,
            billing_id=billing.id,
            payment_method_id=method.id,
            amount=1_000_000,
            transaction_id="TRX-DUPLICATE"
        )

    assert error.value.status_code == 400

    total = db.scalar(
        select(func.count()).select_from(Payment)
    )

    assert total == 1
