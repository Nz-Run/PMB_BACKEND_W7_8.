
import hashlib
import hmac
import logging


logger = logging.getLogger(__name__)


class PaymentWebhookService:

    @staticmethod
    def verify_signature(
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """
        Memverifikasi signature webhook menggunakan HMAC SHA-256.
        """

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
        """
        Simulasi pengiriman bukti pembayaran melalui email.
        """

        logger.info(
            "[EMAIL BUKTI PEMBAYARAN] "
            "NIM: %s | Payment ID: %s | "
            "Jumlah: Rp%s | Status: berhasil",
            payment_result.get("nim"),
            payment_result.get("payment_id"),
            payment_result.get(
                "jumlah_pembayaran",
                payment_result.get("jumlah_bayar")
            )
        )

        return {
            "message": "Simulasi pengiriman bukti pembayaran berhasil"
        }
