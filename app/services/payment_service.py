
import logging
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.models import Billing, Payment, PaymentMethod
from app.services.billing_service import BillingService


logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    def record_payment(
        db: Session,
        billing_id: int,
        payment_method_id: int,
        amount: int,
        transaction_id: str | None = None
    ):
        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Jumlah pembayaran harus lebih dari 0"
            )

        try:
            billing = db.scalar(
                select(Billing)
                .where(Billing.id == billing_id)
                .with_for_update()
            )

            if not billing:
                raise HTTPException(
                    status_code=404,
                    detail="Tagihan tidak ditemukan"
                )

            payment_method = db.get(
                PaymentMethod,
                payment_method_id
            )

            if not payment_method or not payment_method.is_active:
                raise HTTPException(
                    status_code=400,
                    detail="Metode pembayaran tidak tersedia"
                )

            # Hitung denda sebelum menentukan sisa tagihan.
            billing.fine_amount = BillingService.calculate_late_fee(
                billing,
                date.today()
            )

            total_kewajiban = (
                billing.total_amount + billing.fine_amount
            )

            sisa_tagihan = max(
                total_kewajiban - billing.paid_amount,
                0
            )

            if amount > sisa_tagihan:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Pembayaran melebihi sisa tagihan "
                        f"Rp{sisa_tagihan:,}"
                    )
                )

            payment = Payment(
                billing_id=billing.id,
                payment_method_id=payment_method.id,
                amount=amount,
                transaction_id=transaction_id,
                status="success"
            )

            db.add(payment)
            billing.paid_amount += amount
            db.flush()

            if billing.paid_amount >= total_kewajiban:
                billing.status = "paid"
            elif billing.paid_amount > 0:
                billing.status = "partial"
            else:
                billing.status = "unpaid"

            db.commit()
            db.refresh(payment)
            db.refresh(billing)

            logger.info(
                "[SIMULASI EMAIL] Bukti pembayaran berhasil "
                "untuk NIM %s sebesar Rp%s",
                billing.nim,
                amount
            )

            sisa_setelah_bayar = max(
                total_kewajiban - billing.paid_amount,
                0
            )

            return {
                "pesan": "Pembayaran berhasil dicatat",
                "message": "Pembayaran berhasil dicatat",
                "payment_id": payment.id,
                "nim": billing.nim,
                "jumlah_bayar": payment.amount,
                "jumlah_pembayaran": payment.amount,
                "total_dibayar": billing.paid_amount,
                "total_terbayar": billing.paid_amount,
                "sisa_tagihan": sisa_setelah_bayar,
                "status_tagihan": billing.status
            }

        except HTTPException:
            db.rollback()
            raise

        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="ID transaksi sudah pernah digunakan"
            )

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_payment_history(
        db: Session,
        billing_id: int
    ):
        billing = db.get(Billing, billing_id)

        if not billing:
            raise HTTPException(
                status_code=404,
                detail="Tagihan tidak ditemukan"
            )

        payments = db.scalars(
            select(Payment)
            .where(Payment.billing_id == billing_id)
            .order_by(Payment.paid_at.desc())
        ).all()

        return payments
