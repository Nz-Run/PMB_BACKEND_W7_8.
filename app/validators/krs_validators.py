from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import (
    KRS,
    KRSDetail,
    MataKuliah,
    Prasyarat,
    SkalaNilai,
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str


@dataclass
class ValidationContext:
    nim: str
    semester: str
    current_details: list
    new_course: object
    db: object


class Validator(ABC):
    def __init__(self):
        self._next = None

    def set_next(self, validator):
        self._next = validator
        return validator

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = self.check(context)

        if not result.ok:
            return result

        if self._next:
            return self._next.validate(context)

        return ValidationResult(True, "Validasi berhasil")

    @abstractmethod
    def check(self, context: ValidationContext) -> ValidationResult:
        pass


class DuplicateValidator(Validator):
    def check(self, context: ValidationContext) -> ValidationResult:
        for detail in context.current_details:
            if detail.kode_mk == context.new_course.kode_mk:
                return ValidationResult(
                    False,
                    "Mata kuliah sudah terdaftar dalam KRS",
                )

        return ValidationResult(True, "Tidak ada mata kuliah duplikat")


class SKSValidator(Validator):
    MAX_SKS = 24

    def check(self, context: ValidationContext) -> ValidationResult:
        total_sks = sum(
            detail.mata_kuliah.sks
            for detail in context.current_details
        )
        total_sks += context.new_course.sks

        if total_sks > self.MAX_SKS:
            return ValidationResult(
                False,
                f"Total SKS menjadi {total_sks}. Maksimal 24 SKS.",
            )

        return ValidationResult(True, "Batas SKS terpenuhi")


class PrerequisiteValidator(Validator):
    MINIMUM_GRADE = "C"

    def check(self, context: ValidationContext) -> ValidationResult:
        minimum_weight = (
            context.db.query(SkalaNilai.bobot)
            .filter(SkalaNilai.nilai == self.MINIMUM_GRADE)
            .scalar()
        )

        if minimum_weight is None:
            return ValidationResult(
                False,
                "Skala nilai C belum tersedia dalam database",
            )

        missing = (
            context.db.query(MataKuliah.nama_mk)
            .join(
                Prasyarat,
                MataKuliah.kode_mk == Prasyarat.kode_prasyarat,
            )
            .filter(Prasyarat.kode_mk == context.new_course.kode_mk)
            .filter(
                ~context.db.query(KRSDetail.id)
                .join(KRS, KRSDetail.krs_id == KRS.id)
                .join(SkalaNilai, KRSDetail.nilai == SkalaNilai.nilai)
                .filter(
                    KRSDetail.kode_mk == MataKuliah.kode_mk,
                    KRS.nim == context.nim,
                    KRS.semester < context.semester,
                    KRS.status == "approved",
                    SkalaNilai.bobot >= minimum_weight,
                )
                .exists()
            )
            .all()
        )

        if missing:
            names = [row[0] for row in missing]
            return ValidationResult(
                False,
                "Prasyarat belum lulus: " + ", ".join(names),
            )

        return ValidationResult(True, "Prasyarat terpenuhi")


class ConflictValidator(Validator):
    def check(self, context: ValidationContext) -> ValidationResult:
        new_course = context.new_course

        for detail in context.current_details:
            existing = detail.mata_kuliah

            if existing.hari != new_course.hari:
                continue

            overlap = (
                new_course.jam_mulai < existing.jam_selesai
                and existing.jam_mulai < new_course.jam_selesai
            )

            if overlap:
                return ValidationResult(
                    False,
                    f"Jadwal bentrok dengan {existing.nama_mk}",
                )

        return ValidationResult(True, "Tidak ada jadwal bentrok")


def build_chain(validators):
    if not validators:
        return None

    for current, next_validator in zip(validators, validators[1:]):
        current.set_next(next_validator)

    return validators[0]


def build_default_chain():
    return build_chain([
        DuplicateValidator(),
        SKSValidator(),
        PrerequisiteValidator(),
        ConflictValidator(),
    ])
