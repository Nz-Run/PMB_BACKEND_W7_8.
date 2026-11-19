
import hashlib
import hmac
import logging
import os


logger = logging.getLogger(__name__)


class PaymentWebhookService:

    @staticmethod
    def verify_signature(
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        if not payload or not signature or not secret:
            return False

        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()

        received_signature = signature.strip()

        if received_signature.startswith("sha256="):
            received_signature = received_signature[7:]

        return hmac.compare_digest(
            expected_signature,
            received_signature
        )

    @staticmethod
    def send_receipt(payment_result: dict):
        logger.info(
            "[SIMULASI EMAIL] Bukti pembayaran: %s",
            payment_result
        )

        return {
            "message": "Simulasi pengiriman bukti pembayaran berhasil"
        }
