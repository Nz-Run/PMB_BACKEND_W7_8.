
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import (
    User,
    Applicant,
    Billing,
    Payment,
    PaymentMethod
)


SECRET = "webhook_api_test_secret"

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
def client(monkeypatch):
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", SECRET)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def payment_data(client):
    db = TestingSessionLocal()

    user = User(
        name="Webhook Test",
        email="webhook_api_test@example.com",
        password="password_test",
        role="mahasiswa"
    )
    db.add(user)
    db.flush()

    applicant = Applicant(
        user_id=user.id,
        nim="26164003",
        tanggal_lahir=__import__("datetime").date(2005, 5, 10),
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
        due_date=__import__("datetime").date.today(),
        status="unpaid"
    )

    method = PaymentMethod(
        nama_metode="Webhook Test",
        is_active=True
    )

    db.add_all([billing, method])
    db.commit()
    db.refresh(billing)
    db.refresh(method)

    result = {
        "billing_id": billing.id,
        "payment_method_id": method.id
    }

    db.close()
    return result


def make_signature(payload):
    return hmac.new(
        SECRET.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()


def send_webhook(client, payload, signature=None):
    headers = {}

    if signature is not None:
        headers["X-Webhook-Signature"] = signature

    return client.post(
        "/webhook/payment",
        content=payload,
        headers=headers
    )


def test_webhook_secret_not_configured(client, monkeypatch):
    monkeypatch.delenv("PAYMENT_WEBHOOK_SECRET")

    payload = b'{"transaction_id":"TRX-001"}'

    response = send_webhook(client, payload)

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Webhook secret belum dikonfigurasi"
    )


def test_webhook_invalid_signature(client):
    payload = json.dumps({
        "transaction_id": "TRX-002",
        "billing_id": 1,
        "payment_method_id": 1,
        "amount": 100000,
        "status": "success"
    }).encode()

    response = send_webhook(
        client,
        payload,
        "signature_salah"
    )

    assert response.status_code == 401


def test_webhook_invalid_payload(client):
    payload = b"format-json-tidak-valid"

    response = send_webhook(
        client,
        payload,
        make_signature(payload)
    )

    assert response.status_code == 400


def test_webhook_payment_not_success(client, payment_data):
    payload = json.dumps({
        "transaction_id": "TRX-003",
        "billing_id": payment_data["billing_id"],
        "payment_method_id": payment_data["payment_method_id"],
        "amount": 100000,
        "status": "pending"
    }).encode()

    response = send_webhook(
        client,
        payload,
        make_signature(payload)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_webhook_payment_success(client, payment_data):
    payload = json.dumps({
        "transaction_id": "TRX-004",
        "billing_id": payment_data["billing_id"],
        "payment_method_id": payment_data["payment_method_id"],
        "amount": 1_000_000,
        "status": "success"
    }).encode()

    response = send_webhook(
        client,
        payload,
        make_signature(payload)
    )

    assert response.status_code == 200
    assert response.json()["message"] == (
        "Webhook berhasil diproses"
    )
    assert response.json()["payment"]["jumlah_bayar"] == 1_000_000

    db = TestingSessionLocal()
    total = db.scalar(
        select(func.count()).select_from(Payment)
    )
    db.close()

    assert total == 1


def test_webhook_duplicate_transaction(client, payment_data):
    payload = json.dumps({
        "transaction_id": "TRX-005",
        "billing_id": payment_data["billing_id"],
        "payment_method_id": payment_data["payment_method_id"],
        "amount": 1_000_000,
        "status": "success"
    }).encode()

    signature = make_signature(payload)

    first_response = send_webhook(
        client,
        payload,
        signature
    )

    second_response = send_webhook(
        client,
        payload,
        signature
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["message"] == (
        "Transaksi sudah pernah diproses"
    )

    db = TestingSessionLocal()
    total = db.scalar(
        select(func.count()).select_from(Payment)
    )
    db.close()

    assert total == 1
