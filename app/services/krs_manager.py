from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm.attributes import set_committed_value

from app.models import (
    KRS,
    KRSDetail,
    MataKuliah,
    Applicant,
    User,
    KRSLog,
    KRSNotification,
)
from app.validators.krs_validators import (
    ValidationContext,
    ValidationResult,
    build_default_chain,
)


class KRSManager:
    def __init__(self, db: Session, validator=None):
        self.db = db
        self.validator = validator or build_default_chain()

    def _get_krs(self, nim, semester):
        return (
            self.db.query(KRS)
            .filter(
                KRS.nim == nim,
                KRS.semester == semester,
            )
            .with_for_update()
            .first()
        )

    def _student_user_id(self, nim):
        applicant = self.db.query(Applicant).filter(
            Applicant.nim == nim
        ).first()
        return applicant.user_id if applicant else None

    def _pa_user_id(self, dosen_pa):
        try:
            user_id = int(dosen_pa)
        except (TypeError, ValueError):
            return None

        dosen = self.db.query(User).filter(
            User.id == user_id,
            User.role == "dosen_pa",
        ).first()

        return dosen.id if dosen else None

    def _add_log(
        self, krs, actor_id, action,
        from_status, to_status, note=None
    ):
        self.db.add(
            KRSLog(
                krs_id=krs.id,
                actor_id=actor_id,
                action=action,
                from_status=from_status,
                to_status=to_status,
                note=note,
            )
        )

    def _add_notification(self, krs, recipient_id, message):
        self.db.add(
            KRSNotification(
                krs_id=krs.id,
                recipient_id=recipient_id,
                message=message,
            )
        )

    def _bump_version(self, krs):
        current_version = krs.version_id or 1

        updated = (
            self.db.query(KRS)
            .filter(
                KRS.id == krs.id,
                KRS.version_id == current_version,
            )
            .update(
                {KRS.version_id: current_version + 1},
                synchronize_session=False,
            )
        )

        if updated != 1:
            raise StaleDataError("Versi KRS sudah berubah")

        set_committed_value(
            krs,
            "version_id",
            current_version + 1,
        )

    def _validate_details(self, krs):
        if not krs.details:
            return [
                ValidationResult(False, "KRS tidak boleh kosong")
            ]

        errors = []

        for detail in krs.details:
            context = ValidationContext(
                nim=krs.nim,
                semester=krs.semester,
                current_details=[
                    item for item in krs.details
                    if item.kode_mk != detail.kode_mk
                ],
                new_course=detail.mata_kuliah,
                db=self.db,
            )

            result = self.validator.validate(context)

            if not result.ok:
                errors.append(result)

        if errors:
            return errors

        return [
            ValidationResult(
                True,
                "Semua mata kuliah dalam KRS valid",
            )
        ]

    def add_course(self, nim, semester, kode_mk):
        try:
            krs = self._get_krs(nim, semester)

            if not krs:
                krs = KRS(
                    nim=nim,
                    semester=semester,
                    status="draft",
                )
                self.db.add(krs)
                self.db.flush()

            if krs.status not in ("draft", "revision"):
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS hanya dapat diubah saat draft atau revision",
                )

            course = self.db.query(MataKuliah).filter(
                MataKuliah.kode_mk == kode_mk
            ).first()

            if not course:
                self.db.rollback()
                return ValidationResult(
                    False, "Mata kuliah tidak ditemukan"
                )

            student_id = self._student_user_id(nim)

            if not student_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun mahasiswa tidak ditemukan"
                )

            context = ValidationContext(
                nim=nim,
                semester=semester,
                current_details=krs.details,
                new_course=course,
                db=self.db,
            )

            result = self.validator.validate(context)

            if not result.ok:
                self.db.rollback()
                return result

            old_status = krs.status
            self._bump_version(krs)

            self.db.add(
                KRSDetail(
                    krs_id=krs.id,
                    kode_mk=kode_mk,
                )
            )

            self._add_log(
                krs,
                student_id,
                "course_added",
                old_status,
                old_status,
                f"Mata kuliah ditambahkan: {kode_mk}",
            )

            self.db.commit()

            return ValidationResult(
                True,
                "Mata kuliah berhasil ditambahkan ke KRS",
            )

        except IntegrityError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Mata kuliah sudah terdaftar dalam KRS",
            )
        except StaleDataError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Konflik versi KRS. Silakan muat ulang.",
            )
        except Exception:
            self.db.rollback()
            raise

    def remove_course(self, nim, semester, kode_mk):
        try:
            krs = self._get_krs(nim, semester)

            if not krs:
                self.db.rollback()
                return ValidationResult(False, "KRS tidak ditemukan")

            if krs.status not in ("draft", "revision"):
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS hanya dapat diubah saat draft atau revision",
                )

            detail = next(
                (
                    item for item in krs.details
                    if item.kode_mk == kode_mk
                ),
                None,
            )

            if not detail:
                self.db.rollback()
                return ValidationResult(
                    False,
                    "Mata kuliah tidak ditemukan dalam KRS",
                )

            student_id = self._student_user_id(nim)

            if not student_id:
                self.db.rollback()
                return ValidationResult(
                    False,
                    "Akun mahasiswa tidak ditemukan",
                )

            old_status = krs.status
            self._bump_version(krs)
            self.db.delete(detail)

            self._add_log(
                krs,
                student_id,
                "course_removed",
                old_status,
                old_status,
                f"Mata kuliah dihapus: {kode_mk}",
            )

            self.db.commit()

            return ValidationResult(
                True,
                "Mata kuliah berhasil dihapus dari KRS",
            )

        except StaleDataError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Konflik versi KRS. Silakan muat ulang.",
            )
        except Exception:
            self.db.rollback()
            raise

    def validate_krs(self, nim, semester):
        krs = self._get_krs(nim, semester)

        if not krs:
            return [
                ValidationResult(False, "KRS tidak ditemukan")
            ]

        return self._validate_details(krs)

    def submit_krs(self, nim, semester):
        try:
            krs = self._get_krs(nim, semester)

            if not krs:
                self.db.rollback()
                return ValidationResult(False, "KRS tidak ditemukan")

            if not krs.can_transition("submitted", "mahasiswa"):
                self.db.rollback()
                return ValidationResult(
                    False, "Transisi KRS tidak diizinkan"
                )

            student_id = self._student_user_id(nim)
            pa_id = self._pa_user_id(krs.dosen_pa)

            if not student_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun mahasiswa tidak ditemukan"
                )

            if not pa_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Dosen PA belum ditetapkan atau tidak valid"
                )

            results = self._validate_details(krs)
            errors = [
                item.message for item in results if not item.ok
            ]

            if errors:
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS belum valid: " + "; ".join(errors),
                )

            old_status = krs.status
            krs.transition("submitted", "mahasiswa")
            krs.submitted_at = datetime.now(timezone.utc)

            self._add_log(
                krs,
                student_id,
                "submit",
                old_status,
                krs.status,
                "Mahasiswa mengajukan KRS",
            )

            self._add_notification(
                krs,
                pa_id,
                f"KRS mahasiswa {nim} semester {semester} "
                "menunggu persetujuan.",
            )

            self.db.commit()

            return ValidationResult(True, "KRS berhasil diajukan")

        except StaleDataError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Konflik versi KRS. Silakan muat ulang.",
            )
        except Exception:
            self.db.rollback()
            raise

    def approve_krs(self, nim, semester, dosen_pa):
        try:
            pa_id = self._pa_user_id(dosen_pa)

            if not pa_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun dosen PA tidak valid"
                )

            krs = (
                self.db.query(KRS)
                .filter(
                    KRS.nim == nim,
                    KRS.semester == semester,
                    KRS.dosen_pa == str(pa_id),
                )
                .with_for_update()
                .first()
            )

            if not krs:
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS tidak ditemukan atau bukan mahasiswa bimbingan dosen ini",
                )

            if not krs.can_transition("approved", "dosen_pa"):
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS belum diajukan atau tidak dapat disetujui",
                )

            student_id = self._student_user_id(nim)

            if not student_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun mahasiswa tidak ditemukan"
                )

            old_status = krs.status
            krs.transition("approved", "dosen_pa")
            krs.approved_at = datetime.now(timezone.utc)
            krs.revision_note = None

            self._add_log(
                krs,
                pa_id,
                "approve",
                old_status,
                krs.status,
                "KRS disetujui dosen PA",
            )

            self._add_notification(
                krs,
                student_id,
                f"KRS semester {semester} telah disetujui oleh dosen PA.",
            )

            self.db.commit()

            return ValidationResult(True, "KRS berhasil disetujui")

        except StaleDataError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Konflik versi KRS. Silakan muat ulang.",
            )
        except Exception:
            self.db.rollback()
            raise

    def revise_krs(self, nim, semester, dosen_pa, catatan):
        try:
            pa_id = self._pa_user_id(dosen_pa)

            if not pa_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun dosen PA tidak valid"
                )

            if not catatan or not catatan.strip():
                self.db.rollback()
                return ValidationResult(
                    False, "Catatan revisi wajib diisi"
                )

            krs = (
                self.db.query(KRS)
                .filter(
                    KRS.nim == nim,
                    KRS.semester == semester,
                    KRS.dosen_pa == str(pa_id),
                )
                .with_for_update()
                .first()
            )

            if not krs:
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS tidak ditemukan atau bukan mahasiswa bimbingan dosen ini",
                )

            if not krs.can_transition("revision", "dosen_pa"):
                self.db.rollback()
                return ValidationResult(
                    False,
                    "KRS belum diajukan atau tidak dapat direvisi",
                )

            student_id = self._student_user_id(nim)

            if not student_id:
                self.db.rollback()
                return ValidationResult(
                    False, "Akun mahasiswa tidak ditemukan"
                )

            old_status = krs.status
            krs.transition("revision", "dosen_pa")
            krs.revision_note = catatan.strip()

            self._add_log(
                krs,
                pa_id,
                "revise",
                old_status,
                krs.status,
                catatan.strip(),
            )

            self._add_notification(
                krs,
                student_id,
                f"KRS semester {semester} perlu diperbaiki. "
                f"Catatan dosen: {catatan.strip()}",
            )

            self.db.commit()

            return ValidationResult(
                True,
                "KRS berhasil dikembalikan untuk revisi",
            )

        except StaleDataError:
            self.db.rollback()
            return ValidationResult(
                False,
                "Konflik versi KRS. Silakan muat ulang.",
            )
        except Exception:
            self.db.rollback()
            raise
