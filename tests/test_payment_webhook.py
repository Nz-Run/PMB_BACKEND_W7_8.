
import hashlib
import hmac

from app.services.payment_webhook_service import PaymentWebhookService


SECRET = "webhook_test_secret"
PAYLOAD = b'{"transaction_id":"TRX-001","amount":100000}'


def create_signature(payload, secret):
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()


def test_verify_signature_valid():
    signature = create_signature(PAYLOAD, SECRET)

    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        signature,
        SECRET
    )

    assert result is True


def test_verify_signature_valid_with_prefix():
    signature = create_signature(PAYLOAD, SECRET)

    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        "sha256=" + signature,
        SECRET
    )

    assert result is True


def test_verify_signature_invalid():
    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        "signature_salah",
        SECRET
    )

    assert result is False


def test_verify_signature_empty_payload():
    result = PaymentWebhookService.verify_signature(
        b"",
        "signature",
        SECRET
    )

    assert result is False


def test_verify_signature_empty_signature():
    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        "",
        SECRET
    )

    assert result is False


def test_verify_signature_empty_secret():
    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        "signature",
        ""
    )

    assert result is False


def test_verify_signature_with_whitespace():
    signature = create_signature(PAYLOAD, SECRET)

    result = PaymentWebhookService.verify_signature(
        PAYLOAD,
        "  " + signature + "  ",
        SECRET
    )

    assert result is True


def test_send_receipt():
    payment_result = {
        "payment_id": 1,
        "nim": "26164002",
        "jumlah_bayar": 100000,
        "status_tagihan": "partial"
    }

    result = PaymentWebhookService.send_receipt(
        payment_result
    )

    assert result == {
        "message": "Simulasi pengiriman bukti pembayaran berhasil"
    }
