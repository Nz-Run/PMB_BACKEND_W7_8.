
from sqlalchemy import (
    String, Integer, Date, DateTime,
    ForeignKey, UniqueConstraint, CheckConstraint,
    func
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
        String(20),
        default="mahasiswa",
        nullable=False
    )
    applicant: Mapped["Applicant"] = relationship(
        back_populates="user",
        uselist=False
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
        back_populates="applicant",
        uselist=False
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
        String(20),
        default="menunggu",
        nullable=False
    )

    applicant: Mapped["Applicant"] = relationship(
        back_populates="registration"
    )
class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    jti: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    expires_at: Mapped[DateTime] = mapped_column(
        DateTime,
        nullable=False
    )