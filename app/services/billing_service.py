
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Applicant, Registration, Billing


class BillingService:

    TARIF_SPP = {
        "teknik": 5_000_000,
        "ekonomi": 4_000_000,
    }

    DENDA_PER_HARI = 10_000

    @staticmethod
    def get_tarif(program_studi: str) -> int:
        program = program_studi.lower()

        for kategori, tarif in BillingService.TARIF_SPP.items():
            if kategori in program:
                return tarif

        raise ValueError(
            f"Tarif untuk program studi '{program_studi}' belum tersedia"
        )

    @staticmethod
    def calculate_late_fee(
        billing: Billing,
        tanggal_hari_ini: date | None = None
    ) -> int:
        if tanggal_hari_ini is None:
            tanggal_hari_ini = date.today()

        if tanggal_hari_ini <= billing.due_date:
            return 0

        if billing.paid_amount >= billing.total_amount:
            return 0

        hari_terlambat = (
            tanggal_hari_ini - billing.due_date
        ).days

        return hari_terlambat * BillingService.DENDA_PER_HARI

    @staticmethod
    def generate_billing(
        db: Session,
        semester: str,
        tanggal_mulai: date
    ):
        tanggal_jatuh_tempo = tanggal_mulai + timedelta(days=14)

        mahasiswa_diterima = db.execute(
            select(Applicant, Registration)
            .join(
                Registration,
                Registration.applicant_id == Applicant.id
            )
            .where(
                Registration.status_pendaftaran == "diterima",
                Applicant.nim.is_not(None)
            )
        ).all()

        berhasil = []
        dilewati = []

        try:
            for applicant, registration in mahasiswa_diterima:

                if not applicant.nim:
                    continue

                tagihan_lama = db.scalar(
                    select(Billing).where(
                        Billing.nim == applicant.nim,
                        Billing.semester == semester
                    )
                )

                if tagihan_lama:
                    dilewati.append({
                        "nim": applicant.nim,
                        "alasan": "Tagihan semester ini sudah tersedia"
                    })
                    continue

                try:
                    tarif = BillingService.get_tarif(
                        registration.program_studi
                    )
                except ValueError as error:
                    dilewati.append({
                        "nim": applicant.nim,
                        "alasan": str(error)
                    })
                    continue

                billing = Billing(
                    nim=applicant.nim,
                    semester=semester,
                    total_amount=tarif,
                    paid_amount=0,
                    fine_amount=0,
                    due_date=tanggal_jatuh_tempo,
                    status="unpaid"
                )

                db.add(billing)

                berhasil.append({
                    "nim": applicant.nim,
                    "program_studi": registration.program_studi,
                    "total_tagihan": tarif,
                    "jatuh_tempo": tanggal_jatuh_tempo.isoformat()
                })

            db.commit()

        except Exception:
            db.rollback()
            raise

        return {
            "total_mahasiswa_diterima": len(mahasiswa_diterima),
            "total_tagihan_dibuat": len(berhasil),
            "total_dilewati": len(dilewati),
            "tagihan_dibuat": berhasil,
            "mahasiswa_dilewati": dilewati
        }

    @staticmethod
    def update_billing_status(
        db: Session,
        billing_id: int,
        tanggal_sekarang: date | None = None
    ):
        billing = db.get(Billing, billing_id)

        if not billing:
            return None

        if tanggal_sekarang is None:
            tanggal_sekarang = date.today()

        billing.fine_amount = BillingService.calculate_late_fee(
            billing,
            tanggal_sekarang
        )

        total_kewajiban = (
            billing.total_amount + billing.fine_amount
        )

        if billing.paid_amount >= total_kewajiban:
            billing.status = "paid"
        elif billing.paid_amount > 0:
            billing.status = "partial"
        elif tanggal_sekarang > billing.due_date:
            billing.status = "overdue"
        else:
            billing.status = "unpaid"

        try:
            db.commit()
            db.refresh(billing)
        except Exception:
            db.rollback()
            raise

        return billing
