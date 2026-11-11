
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    String, Integer, Date, DateTime, Time, Float, Boolean,
    ForeignKey, UniqueConstraint, CheckConstraint,
    Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(20), default="mahasiswa", nullable=False
    )

    applicant: Mapped["Applicant"] = relationship(
        back_populates="user", uselist=False
    )


class Applicant(Base):
    __tablename__ = "applicants"

    __table_args__ = (
        UniqueConstraint("nim", name="uq_applicants_nim"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )
    nim: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tanggal_lahir: Mapped[Date] = mapped_column(Date, nullable=False)
    alamat: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped["User"] = relationship(back_populates="applicant")

    registration: Mapped["Registration"] = relationship(
        back_populates="applicant", uselist=False
    )


class Registration(Base):
    __tablename__ = "registrations"

    __table_args__ = (
        CheckConstraint(
            "status_pendaftaran IN ('menunggu', 'diterima', 'ditolak')",
            name="ck_registration_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("applicants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )
    program_studi: Mapped[str] = mapped_column(String(100), nullable=False)
    tanggal_daftar: Mapped[DateTime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp()
    )
    status_pendaftaran: Mapped[str] = mapped_column(
        String(20), default="menunggu", nullable=False
    )

    applicant: Mapped["Applicant"] = relationship(
        back_populates="registration"
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    expires_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)


# =========================
# MODEL KRS
# =========================

class MataKuliah(Base):
    __tablename__ = "mata_kuliah"

    __table_args__ = (
        CheckConstraint("sks >= 1 AND sks <= 4", name="ck_mata_kuliah_sks"),
        CheckConstraint("hari >= 1 AND hari <= 6", name="ck_mata_kuliah_hari"),
        CheckConstraint("jam_mulai < jam_selesai", name="ck_mata_kuliah_jam"),
    )

    kode_mk: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama_mk: Mapped[str] = mapped_column(String(150), nullable=False)
    sks: Mapped[int] = mapped_column(Integer, nullable=False)
    hari: Mapped[int] = mapped_column(Integer, nullable=False)
    jam_mulai: Mapped[Time] = mapped_column(Time, nullable=False)
    jam_selesai: Mapped[Time] = mapped_column(Time, nullable=False)

    krs_details: Mapped[list["KRSDetail"]] = relationship(
        back_populates="mata_kuliah",
        cascade="all, delete-orphan"
    )

    prasyarat: Mapped[list["MataKuliah"]] = relationship(
        "MataKuliah",
        secondary="prasyarat",
        primaryjoin="MataKuliah.kode_mk == Prasyarat.kode_mk",
        secondaryjoin="MataKuliah.kode_mk == Prasyarat.kode_prasyarat",
        back_populates="dibutuhkan_oleh"
    )

    dibutuhkan_oleh: Mapped[list["MataKuliah"]] = relationship(
        "MataKuliah",
        secondary="prasyarat",
        primaryjoin="MataKuliah.kode_mk == Prasyarat.kode_prasyarat",
        secondaryjoin="MataKuliah.kode_mk == Prasyarat.kode_mk",
        back_populates="prasyarat"
    )


class KRSStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REVISION = "revision"


KRS_TRANSITIONS = {
    ("draft", "mahasiswa"): {"submitted"},
    ("submitted", "dosen_pa"): {"approved", "revision"},
    ("revision", "mahasiswa"): {"submitted"},
}


class KRS(Base):
    __tablename__ = "krs"

    __table_args__ = (
        UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'revision')",
            name="ck_krs_status"
        ),
        Index("ix_krs_nim", "nim"),
        Index("ix_krs_semester", "semester"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    nim: Mapped[str] = mapped_column(
        ForeignKey("applicants.nim"), nullable=False
    )

    semester: Mapped[str] = mapped_column(String(5), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )

    dosen_pa: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    submitted_at: Mapped[DateTime | None] = mapped_column(
        DateTime, nullable=True
    )

    approved_at: Mapped[DateTime | None] = mapped_column(
        DateTime, nullable=True
    )

    revision_note: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )

    version_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __mapper_args__ = {"version_id_col": version_id}

    details: Mapped[list["KRSDetail"]] = relationship(
        back_populates="krs",
        cascade="all, delete-orphan"
    )

    def can_transition(self, target_status, actor):
        allowed = KRS_TRANSITIONS.get(
            (self.status, actor),
            set()
        )

        target = (
            target_status.value
            if isinstance(target_status, KRSStatus)
            else target_status
        )

        return target in allowed

    def transition(self, target_status, actor):
        target = (
            target_status.value
            if isinstance(target_status, KRSStatus)
            else target_status
        )

        if not self.can_transition(target, actor):
            raise ValueError(
                f"Transisi KRS tidak diizinkan: "
                f"{self.status} ke {target} oleh {actor}"
            )

        self.status = target


class KRSDetail(Base):
    __tablename__ = "krs_detail"

    __table_args__ = (
        UniqueConstraint("krs_id", "kode_mk", name="uq_krs_detail_course"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    krs_id: Mapped[int] = mapped_column(
        ForeignKey("krs.id", ondelete="CASCADE"), nullable=False
    )

    kode_mk: Mapped[str] = mapped_column(
        ForeignKey("mata_kuliah.kode_mk"), nullable=False
    )

    nilai: Mapped[str | None] = mapped_column(String(2), nullable=True)

    krs: Mapped["KRS"] = relationship(back_populates="details")

    mata_kuliah: Mapped["MataKuliah"] = relationship(
        back_populates="krs_details"
    )


class Prasyarat(Base):
    __tablename__ = "prasyarat"

    __table_args__ = (
        Index("ix_prasyarat_kode_prasyarat", "kode_prasyarat"),
    )

    kode_mk: Mapped[str] = mapped_column(
        ForeignKey("mata_kuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True
    )

    kode_prasyarat: Mapped[str] = mapped_column(
        ForeignKey("mata_kuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True
    )


class SkalaNilai(Base):
    __tablename__ = "skala_nilai"

    nilai: Mapped[str] = mapped_column(
        String(2),
        primary_key=True
    )

    bobot: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )


# ==========================================
# MODEL LOG AKTIVITAS KRS
# ==========================================

class KRSLog(Base):
    __tablename__ = "krs_logs"

    __table_args__ = (
        Index("ix_krs_logs_krs_id", "krs_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    krs_id: Mapped[int] = mapped_column(
        ForeignKey("krs.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )


# ==========================================
# MODEL NOTIFIKASI KRS
# ==========================================

class KRSNotification(Base):
    __tablename__ = "krs_notifications"

    __table_args__ = (
        Index("ix_krs_notifications_recipient_id", "recipient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    krs_id: Mapped[int] = mapped_column(
        ForeignKey("krs.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )


# =========================
# MODEL JADWAL & RUANGAN
# =========================

class Ruangan(Base):
    __tablename__ = "ruangan"

    __table_args__ = (
        CheckConstraint(
            "kapasitas > 0",
            name="ck_ruangan_kapasitas"
        ),
        UniqueConstraint(
            "kode_ruangan",
            name="uq_ruangan_kode"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    kode_ruangan: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    nama_ruangan: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    kapasitas: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    jadwals: Mapped[list["Jadwal"]] = relationship(
        back_populates="ruangan"
    )


class Jadwal(Base):
    __tablename__ = "jadwal"

    __table_args__ = (
        CheckConstraint(
            "jam_mulai < jam_selesai",
            name="ck_jadwal_jam"
        ),
        CheckConstraint(
            "hari >= 1 AND hari <= 6",
            name="ck_jadwal_hari"
        ),
        CheckConstraint(
            "jumlah_peserta >= 0",
            name="ck_jadwal_jumlah_peserta"
        ),
        Index("ix_jadwal_hari", "hari"),
        Index("ix_jadwal_kode_mk", "kode_mk"),
        Index("ix_jadwal_ruangan_id", "ruangan_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    kode_mk: Mapped[str] = mapped_column(
        ForeignKey("mata_kuliah.kode_mk"),
        nullable=False
    )

    ruangan_id: Mapped[int] = mapped_column(
        ForeignKey("ruangan.id"),
        nullable=False
    )

    dosen: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    hari: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    jam_mulai: Mapped[Time] = mapped_column(
        Time, nullable=False
    )

    jam_selesai: Mapped[Time] = mapped_column(
        Time, nullable=False
    )

    jumlah_peserta: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    mata_kuliah: Mapped["MataKuliah"] = relationship()

    ruangan: Mapped["Ruangan"] = relationship(
        back_populates="jadwals"
    )
