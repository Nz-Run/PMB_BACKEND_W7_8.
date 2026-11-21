
from datetime import date, time
from pydantic import BaseModel, EmailStr, ConfigDict, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    tanggal_lahir: date
    alamat: str = Field(min_length=5, max_length=255)
    program_studi: str = Field(min_length=2, max_length=100)


class RegisterResponse(BaseModel):
    message: str
    user_id: int
    applicant_id: int
    registration_id: int
    email: EmailStr
    status_pendaftaran: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    message: str
    user_id: int
    name: str
    email: EmailStr
    access_token: str
    token_type: str
# =========================
# SCHEMA KRS WEEK 6
# =========================

class KRSAddCourseRequest(BaseModel):
    kode_mk: str = Field(min_length=1, max_length=20)


class KRSRevisionRequest(BaseModel):
    catatan: str = Field(min_length=5, max_length=500)


class KRSAdvisorAssignmentRequest(BaseModel):
    dosen_pa_id: int = Field(gt=0)

# =========================
# SCHEMA JADWAL WEEK 7-8
# =========================

class RuanganCreateRequest(BaseModel):
    kode_ruangan: str = Field(min_length=1, max_length=20)
    nama_ruangan: str = Field(min_length=2, max_length=100)
    kapasitas: int = Field(gt=0)


class JadwalCreateRequest(BaseModel):
    kode_mk: str = Field(min_length=1, max_length=20)
    ruangan_id: int = Field(gt=0)
    dosen: str = Field(min_length=2, max_length=100)
    hari: int = Field(ge=1, le=6)
    jam_mulai: time
    jam_selesai: time
    jumlah_peserta: int = Field(default=0, ge=0)


class JadwalUpdateRequest(BaseModel):
    kode_mk: str | None = Field(default=None, min_length=1, max_length=20)
    ruangan_id: int | None = Field(default=None, gt=0)
    dosen: str | None = Field(default=None, min_length=2, max_length=100)
    hari: int | None = Field(default=None, ge=1, le=6)
    jam_mulai: time | None = None
    jam_selesai: time | None = None
    jumlah_peserta: int | None = Field(default=None, ge=0)


class JadwalResponse(BaseModel):
    id: int
    kode_mk: str
    ruangan_id: int
    dosen: str
    hari: int
    jam_mulai: time
    jam_selesai: time
    jumlah_peserta: int

    model_config = ConfigDict(from_attributes=True)

# =========================
# SCHEMA NILAI & TRANSKRIP
# WEEK 9-10
# =========================

class InputNilaiRequest(BaseModel):
    nilai: str = Field(pattern=r"^(A|B|C|D|E)$")


class KehadiranRequest(BaseModel):
    total_pertemuan: int = Field(ge=1)
    jumlah_hadir: int = Field(ge=0)


class NilaiResponse(BaseModel):
    nim: str
    kode_mk: str
    nama_mk: str
    sks: int
    nilai: str | None
    bobot: float | None
    persentase_kehadiran: float | None


class TranskripResponse(BaseModel):
    nim: str
    nama: str
    total_sks: int
    ip_semester: float
    ipk: float
    mata_kuliah: list[NilaiResponse]
    ipk: float
    mata_kuliah: list[NilaiResponse]

# =========================
    ip_semester: float
    ipk: float
    mata_kuliah: list[NilaiResponse]# =========================
# SCHEMA KEUANGAN
# WEEK 9-10
# =========================

from datetime import date
from pydantic import BaseModel, Field


class BillingGenerateRequest(BaseModel):
    semester: str = Field(min_length=5, max_length=5)
    tanggal_mulai: date


class PaymentCreateRequest(BaseModel):
    billing_id: int = Field(gt=0)
    payment_method_id: int = Field(gt=0)
    amount: int = Field(gt=0)
    transaction_id: str | None = Field(
        default=None,
        max_length=100
    )