import csv
from io import StringIO, BytesIO

from fastapi.responses import Response

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
import os
from datetime import datetime, timezone

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request
)
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.auth import (
    create_access_token,
    get_current_user,
    get_current_token_payload,
    get_current_admin
)

from app.database import get_db

from app.models import (
    User,
    Applicant,
    Registration,
    RevokedToken,
    KRS,
    KRSDetail,
    KRSNotification,
    Jadwal,
    Ruangan,
    MataKuliah,
    Kehadiran,
    RiwayatNilai,
    SkalaNilai,
    Payment,
    Billing,
    PaymentMethod
)

from app.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    UserResponse,
    KRSAddCourseRequest,
    KRSRevisionRequest,
    KRSAdvisorAssignmentRequest,
    RuanganCreateRequest,
    JadwalCreateRequest,
    JadwalUpdateRequest,
    JadwalResponse,
    InputNilaiRequest,
    KehadiranRequest,
    TranskripResponse,
    BillingGenerateRequest,
    PaymentCreateRequest
)

from app.security import hash_password, verify_password

from app.services.krs_manager import KRSManager
from app.services.schedule_service import ScheduleService
from app.services.grade_service import GradeService
from app.services.payment_service import PaymentService
from app.services.payment_webhook_service import PaymentWebhookService
from app.services.grade_service import GradeService
from app.services.billing_service import BillingService
from app.services.payment_service import PaymentService
from app.services.payment_webhook_service import PaymentWebhookService
app = FastAPI(
    title="PMB Backend API",
    description="API Pendaftaran Mahasiswa Baru",
    version="1.0.0"
)


# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():
    return {
        "message": "PMB Backend API berhasil dijalankan"
    }


# ==========================================
# AUTHENTICATION DAN PENDAFTARAN
# ==========================================

@app.post("/register", response_model=RegisterResponse)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email sudah terdaftar"
        )

    try:
        new_user = User(
            name=data.name,
            email=data.email,
            password=hash_password(data.password)
        )

        db.add(new_user)
        db.flush()

        new_applicant = Applicant(
            user_id=new_user.id,
            tanggal_lahir=data.tanggal_lahir,
            alamat=data.alamat
        )

        db.add(new_applicant)
        db.flush()

        new_registration = Registration(
            applicant_id=new_applicant.id,
            program_studi=data.program_studi
        )

        db.add(new_registration)
        db.commit()

        db.refresh(new_user)
        db.refresh(new_applicant)
        db.refresh(new_registration)

        return {
            "message": "Pendaftaran berhasil",
            "user_id": new_user.id,
            "applicant_id": new_applicant.id,
            "registration_id": new_registration.id,
            "email": new_user.email,
            "status_pendaftaran": new_registration.status_pendaftaran
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Data pendaftaran tidak dapat disimpan karena duplikat"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Terjadi kesalahan pada server"
        )


@app.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == data.email
    ).first()

    if not user or not verify_password(
        data.password,
        user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Email atau password salah"
        )

    access_token = create_access_token(
        {"sub": str(user.id)}
    )

    return {
        "message": "Login berhasil",
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.get("/me", response_model=UserResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


@app.post("/logout")
def logout(
    payload: dict = Depends(get_current_token_payload),
    db: Session = Depends(get_db)
):
    jti = payload.get("jti")

    if not jti:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid"
        )

    existing_token = db.query(RevokedToken).filter(
        RevokedToken.jti == jti
    ).first()

    if not existing_token:
        expires_at = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.utc
        ).replace(tzinfo=None)

        revoked_token = RevokedToken(
            jti=jti,
            expires_at=expires_at
        )

        db.add(revoked_token)
        db.commit()

    return {
        "message": "Logout berhasil"
    }


# ==========================================
# ADMIN PENDAFTARAN
# ==========================================

@app.get("/admin/registrations")
def get_all_registrations(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    return db.query(Registration).all()


@app.put("/admin/registrations/{registration_id}/decision")
def decide_registration(
    registration_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    if status not in ["diterima", "ditolak"]:
        raise HTTPException(
            status_code=400,
            detail="Status harus diterima atau ditolak"
        )

    registration = db.query(Registration).filter(
        Registration.id == registration_id
    ).first()

    if registration is None:
        raise HTTPException(
            status_code=404,
            detail="Data pendaftaran tidak ditemukan"
        )

    if registration.status_pendaftaran != "menunggu":
        raise HTTPException(
            status_code=400,
            detail="Pendaftaran sudah diproses"
        )

    if status == "diterima":
        applicant = registration.applicant

        if applicant.nim is not None:
            raise HTTPException(
                status_code=400,
                detail="Mahasiswa sudah memiliki NIM"
            )

        existing_nims = db.query(Applicant.nim).filter(
            Applicant.nim.like("26164%"),
            Applicant.nim.isnot(None)
        ).all()

        numbers = [
            int(row[0][5:])
            for row in existing_nims
            if row[0][5:].isdigit()
        ]

        next_number = max(numbers, default=0) + 1
        applicant.nim = f"26164{next_number:04d}"

    registration.status_pendaftaran = status

    try:
        db.commit()
        db.refresh(registration)
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Keputusan pendaftaran berhasil disimpan",
        "registration_id": registration.id,
        "status_pendaftaran": registration.status_pendaftaran,
        "nim": registration.applicant.nim
    }


@app.get("/admin/statistics")
def get_registration_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    statistics = db.query(
        Registration.status_pendaftaran,
        func.count(Registration.id).label("jumlah")
    ).group_by(
        Registration.status_pendaftaran
    ).all()

    total = db.query(Registration).count()

    return {
        "total_pendaftar": total,
        "statistik_status": [
            {
                "status": row.status_pendaftaran,
                "jumlah": row.jumlah
            }
            for row in statistics
        ]
    }


# ==========================================
# HELPER MAHASISWA
# ==========================================

def get_mahasiswa_nim(
    db: Session,
    current_user: User
):
    if current_user.role != "mahasiswa":
        raise HTTPException(
            status_code=403,
            detail="Akses khusus mahasiswa"
        )

    applicant = db.query(Applicant).filter(
        Applicant.user_id == current_user.id
    ).first()

    if applicant is None or not applicant.nim:
        raise HTTPException(
            status_code=403,
            detail="Akun belum memiliki NIM"
        )

    registration = db.query(Registration).filter(
        Registration.applicant_id == applicant.id
    ).first()

    if (
        registration is None
        or registration.status_pendaftaran != "diterima"
    ):
        raise HTTPException(
            status_code=403,
            detail="Pendaftaran mahasiswa belum diterima"
        )

    return applicant.nim


# ==========================================
# API KRS WEEK 6
# ==========================================

def check_krs_result(result):
    if result.ok:
        return

    message = result.message
    lower_message = message.lower()

    if "tidak ditemukan" in lower_message:
        status_code = 404
    elif any(word in lower_message for word in [
        "transisi",
        "status",
        "tidak dapat diubah",
        "tidak dapat disetujui",
        "tidak dapat direvisi",
        "draft atau revision",
    ]):
        status_code = 409
    else:
        status_code = 400

    raise HTTPException(
        status_code=status_code,
        detail=message
    )


@app.get("/krs/{semester}")
def get_student_krs(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    krs = db.query(KRS).filter(
        KRS.nim == nim,
        KRS.semester == semester
    ).first()

    if not krs:
        raise HTTPException(
            status_code=404,
            detail="KRS tidak ditemukan"
        )

    return {
        "nim": krs.nim,
        "semester": krs.semester,
        "status": krs.status,
        "dosen_pa": krs.dosen_pa,
        "submitted_at": krs.submitted_at,
        "approved_at": krs.approved_at,
        "revision_note": krs.revision_note,
        "total_sks": sum(
            detail.mata_kuliah.sks
            for detail in krs.details
        ),
        "mata_kuliah": [
            {
                "kode_mk": detail.kode_mk,
                "nama_mk": detail.mata_kuliah.nama_mk,
                "sks": detail.mata_kuliah.sks,
                "hari": detail.mata_kuliah.hari,
                "jam_mulai": str(detail.mata_kuliah.jam_mulai),
                "jam_selesai": str(detail.mata_kuliah.jam_selesai)
            }
            for detail in krs.details
        ]
    }


@app.post("/krs/{semester}/courses")
def add_krs_course(
    semester: str,
    data: KRSAddCourseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    manager = KRSManager(db)
    result = manager.add_course(
        nim,
        semester,
        data.kode_mk
    )

    check_krs_result(result)

    return {
        "message": result.message
    }


@app.delete("/krs/{semester}/courses/{kode_mk}")
def delete_krs_course(
    semester: str,
    kode_mk: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    manager = KRSManager(db)
    result = manager.remove_course(
        nim,
        semester,
        kode_mk
    )

    check_krs_result(result)

    return {
        "message": result.message
    }


@app.post("/krs/{semester}/validate")
def validate_student_krs(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    manager = KRSManager(db)
    results = manager.validate_krs(nim, semester)

    errors = [
        result.message
        for result in results
        if not result.ok
    ]

    if errors:
        raise HTTPException(
            status_code=400,
            detail=errors
        )

    return {
        "valid": True,
        "messages": [
            result.message for result in results
        ]
    }


@app.post("/krs/{semester}/submit")
def submit_student_krs(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    krs = db.query(KRS).filter(
        KRS.nim == nim,
        KRS.semester == semester
    ).first()

    if not krs:
        raise HTTPException(
            status_code=404,
            detail="KRS tidak ditemukan"
        )

    if not krs.dosen_pa:
        raise HTTPException(
            status_code=400,
            detail="Dosen PA belum ditetapkan oleh admin"
        )

    manager = KRSManager(db)
    result = manager.submit_krs(nim, semester)

    check_krs_result(result)

    return {
        "message": result.message
    }


@app.put("/admin/krs/{nim}/{semester}/advisor")
def assign_krs_advisor(
    nim: str,
    semester: str,
    data: KRSAdvisorAssignmentRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    krs = db.query(KRS).filter(
        KRS.nim == nim,
        KRS.semester == semester
    ).first()

    if not krs:
        raise HTTPException(
            status_code=404,
            detail="KRS tidak ditemukan"
        )

    if krs.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Dosen PA hanya dapat ditetapkan saat KRS berstatus draft"
        )

    dosen = db.query(User).filter(
        User.id == data.dosen_pa_id
    ).first()

    if dosen is None or dosen.role != "dosen_pa":
        raise HTTPException(
            status_code=400,
            detail="Akun tujuan bukan dosen PA"
        )

    krs.dosen_pa = str(dosen.id)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Dosen PA berhasil ditetapkan",
        "nim": nim,
        "semester": semester,
        "dosen_pa_id": dosen.id,
        "dosen_pa": dosen.name
    }


@app.post("/dosen-pa/krs/{nim}/{semester}/approve")
def approve_student_krs(
    nim: str,
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "dosen_pa":
        raise HTTPException(
            status_code=403,
            detail="Akses khusus dosen PA"
        )

    krs = db.query(KRS).filter(
        KRS.nim == nim,
        KRS.semester == semester
    ).first()

    if not krs:
        raise HTTPException(
            status_code=404,
            detail="KRS tidak ditemukan"
        )

    if krs.dosen_pa != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="KRS bukan mahasiswa bimbingan Anda"
        )

    manager = KRSManager(db)
    result = manager.approve_krs(
        nim,
        semester,
        str(current_user.id)
    )

    check_krs_result(result)

    return {
        "message": result.message
    }


@app.post("/dosen-pa/krs/{nim}/{semester}/revise")
def revise_student_krs(
    nim: str,
    semester: str,
    data: KRSRevisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "dosen_pa":
        raise HTTPException(
            status_code=403,
            detail="Akses khusus dosen PA"
        )

    krs = db.query(KRS).filter(
        KRS.nim == nim,
        KRS.semester == semester
    ).first()

    if not krs:
        raise HTTPException(
            status_code=404,
            detail="KRS tidak ditemukan"
        )

    if krs.dosen_pa != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="KRS bukan mahasiswa bimbingan Anda"
        )

    manager = KRSManager(db)
    result = manager.revise_krs(
        nim,
        semester,
        str(current_user.id),
        data.catatan
    )

    check_krs_result(result)

    return {
        "message": result.message
    }


# ==========================================
# API NOTIFIKASI KRS
# ==========================================

@app.get("/notifications/me")
def get_my_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notifications = (
        db.query(KRSNotification)
        .filter(
            KRSNotification.recipient_id == current_user.id
        )
        .order_by(KRSNotification.created_at.desc())
        .all()
    )

    return {
        "total": len(notifications),
        "notifications": [
            {
                "id": item.id,
                "krs_id": item.krs_id,
                "message": item.message,
                "is_read": item.is_read,
                "created_at": item.created_at
            }
            for item in notifications
        ]
    }


@app.put("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = db.query(KRSNotification).filter(
        KRSNotification.id == notification_id,
        KRSNotification.recipient_id == current_user.id
    ).first()

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notifikasi tidak ditemukan"
        )

    notification.is_read = True

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Notifikasi berhasil ditandai sudah dibaca",
        "notification_id": notification.id,
        "is_read": notification.is_read
    }


# ==========================================
# API JADWAL DAN RUANGAN WEEK 7-8
# ==========================================

def check_schedule_result(result):
    if result.get("success"):
        return

    message = result.get(
        "message",
        "Terjadi kesalahan"
    )

    if "tidak ditemukan" in message.lower():
        status_code = 404
    elif "konflik" in message.lower():
        status_code = 409
    else:
        status_code = 400

    raise HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "conflicts": result.get("conflicts", [])
        }
    )


# ==========================================
# CRUD RUANGAN
# ==========================================

@app.post("/admin/ruangan")
def create_ruangan(
    data: RuanganCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    ruangan = Ruangan(
        kode_ruangan=data.kode_ruangan,
        nama_ruangan=data.nama_ruangan,
        kapasitas=data.kapasitas
    )

    try:
        db.add(ruangan)
        db.commit()
        db.refresh(ruangan)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Kode ruangan sudah digunakan"
        )

    return {
        "message": "Ruangan berhasil ditambahkan",
        "id": ruangan.id,
        "kode_ruangan": ruangan.kode_ruangan,
        "nama_ruangan": ruangan.nama_ruangan,
        "kapasitas": ruangan.kapasitas
    }


@app.get("/admin/ruangan")
def get_all_ruangan(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    ruangan = db.query(Ruangan).order_by(
        Ruangan.kode_ruangan
    ).all()

    return {
        "total": len(ruangan),
        "ruangan": [
            {
                "id": item.id,
                "kode_ruangan": item.kode_ruangan,
                "nama_ruangan": item.nama_ruangan,
                "kapasitas": item.kapasitas
            }
            for item in ruangan
        ]
    }


@app.delete("/admin/ruangan/{ruangan_id}")
def delete_ruangan(
    ruangan_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    ruangan = db.query(Ruangan).filter(
        Ruangan.id == ruangan_id
    ).first()

    if ruangan is None:
        raise HTTPException(
            status_code=404,
            detail="Ruangan tidak ditemukan"
        )

    jadwal_terpakai = db.query(Jadwal).filter(
        Jadwal.ruangan_id == ruangan_id
    ).first()

    if jadwal_terpakai:
        raise HTTPException(
            status_code=409,
            detail="Ruangan masih digunakan oleh jadwal"
        )

    db.delete(ruangan)
    db.commit()

    return {
        "message": "Ruangan berhasil dihapus"
    }


# ==========================================
# CRUD JADWAL
# ==========================================

@app.post("/admin/jadwal")
def create_jadwal(
    data: JadwalCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    service = ScheduleService(db)

    result = service.create_schedule(
        kode_mk=data.kode_mk,
        ruangan_id=data.ruangan_id,
        dosen=data.dosen,
        hari=data.hari,
        jam_mulai=data.jam_mulai,
        jam_selesai=data.jam_selesai,
        jumlah_peserta=data.jumlah_peserta
    )

    check_schedule_result(result)

    return result


@app.get("/jadwal")
def get_all_jadwal(
    db: Session = Depends(get_db)
):
    service = ScheduleService(db)
    jadwals = service.get_schedules()

    return {
        "total": len(jadwals),
        "jadwal": [
            {
                "id": item.id,
                "kode_mk": item.kode_mk,
                "nama_mk": item.mata_kuliah.nama_mk,
                "ruangan_id": item.ruangan_id,
                "kode_ruangan": item.ruangan.kode_ruangan,
                "nama_ruangan": item.ruangan.nama_ruangan,
                "kapasitas": item.ruangan.kapasitas,
                "dosen": item.dosen,
                "hari": item.hari,
                "jam_mulai": str(item.jam_mulai),
                "jam_selesai": str(item.jam_selesai),
                "jumlah_peserta": item.jumlah_peserta
            }
            for item in jadwals
        ]
    }


@app.get("/jadwal/{schedule_id}")
def get_jadwal_by_id(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    service = ScheduleService(db)
    jadwal = service.get_schedule(schedule_id)

    if jadwal is None:
        raise HTTPException(
            status_code=404,
            detail="Jadwal tidak ditemukan"
        )

    return {
        "id": jadwal.id,
        "kode_mk": jadwal.kode_mk,
        "nama_mk": jadwal.mata_kuliah.nama_mk,
        "ruangan_id": jadwal.ruangan_id,
        "nama_ruangan": jadwal.ruangan.nama_ruangan,
        "dosen": jadwal.dosen,
        "hari": jadwal.hari,
        "jam_mulai": str(jadwal.jam_mulai),
        "jam_selesai": str(jadwal.jam_selesai),
        "jumlah_peserta": jadwal.jumlah_peserta

    }


@app.put("/admin/jadwal/{schedule_id}")
def update_jadwal(
    schedule_id: int,
    data: JadwalUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    service = ScheduleService(db)

    jadwal = service.get_schedule(schedule_id)

    if jadwal is None:
        raise HTTPException(
            status_code=404,
            detail="Jadwal tidak ditemukan"
        )

    changes = data.model_dump(exclude_unset=True)

    result = service.update_schedule(
        schedule_id=schedule_id,
        kode_mk=changes.get("kode_mk", jadwal.kode_mk),
        ruangan_id=changes.get("ruangan_id", jadwal.ruangan_id),
        dosen=changes.get("dosen", jadwal.dosen),
        hari=changes.get("hari", jadwal.hari),
        jam_mulai=changes.get("jam_mulai", jadwal.jam_mulai),
        jam_selesai=changes.get("jam_selesai", jadwal.jam_selesai),
        jumlah_peserta=changes.get(
            "jumlah_peserta",
            jadwal.jumlah_peserta
        )
    )

    check_schedule_result(result)

    return result


@app.delete("/admin/jadwal/{schedule_id}")
def delete_jadwal(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    service = ScheduleService(db)

    result = service.delete_schedule(schedule_id)

    check_schedule_result(result)

    return result


# ==========================================
# DASHBOARD KONFLIK JADWAL
# ==========================================

@app.get("/admin/jadwal/conflicts")
def get_jadwal_conflicts(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    jadwals = db.query(Jadwal).order_by(
        Jadwal.hari,
        Jadwal.jam_mulai
    ).all()

    service = ScheduleService(db)
    all_conflicts = []

    for jadwal in jadwals:
        conflicts = service.detect_conflicts(
            hari=jadwal.hari,
            jam_mulai=jadwal.jam_mulai,
            jam_selesai=jadwal.jam_selesai,
            ruangan_id=jadwal.ruangan_id,
            dosen=jadwal.dosen,
            exclude_id=jadwal.id
        )

        for conflict in conflicts:
            pair = sorted([
                jadwal.id,
                conflict["schedule_id"]
            ])

            if not any(
                sorted([
                    item["schedule_id"],
                    item["conflict_schedule_id"]
                ]) == pair
                for item in all_conflicts
            ):
                all_conflicts.append({
                    "schedule_id": jadwal.id,
                    "conflict_schedule_id": conflict["schedule_id"],
                    "conflict_types": conflict["type"],
                    "message": conflict["message"]
                })

    return {
        "total_conflicts": len(all_conflicts),
        "conflicts": all_conflicts
    }


# ==========================================
# REKOMENDASI ALTERNATIF JADWAL
# ==========================================

@app.get("/admin/jadwal/{schedule_id}/alternatives")
def get_jadwal_alternatives(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    service = ScheduleService(db)

    result = service.recommend_alternatives(schedule_id)

    if not result["success"]:
        raise HTTPException(
            status_code=404,
            detail=result["message"]
        )

    return result


# ==========================================
# API NILAI DAN TRANSKRIP WEEK 9-10
# ==========================================

@app.post("/admin/kehadiran/{detail_id}")
def input_kehadiran(
    detail_id: int,
    data: KehadiranRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    kehadiran = GradeService.input_kehadiran(
        db=db,
        detail_id=detail_id,
        total_pertemuan=data.total_pertemuan,
        jumlah_hadir=data.jumlah_hadir
    )

    return {
        "message": "Data kehadiran berhasil disimpan",
        "krs_detail_id": kehadiran.krs_detail_id,
        "total_pertemuan": kehadiran.total_pertemuan,
        "jumlah_hadir": kehadiran.jumlah_hadir,
        "persentase_kehadiran": round(
            kehadiran.jumlah_hadir /
            kehadiran.total_pertemuan * 100,
            2
        )
    }


@app.post("/admin/nilai/{detail_id}")
def input_nilai(
    detail_id: int,
    data: InputNilaiRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    detail = GradeService.input_nilai(
        db=db,
        detail_id=detail_id,
        nilai=data.nilai,
        admin_id=current_admin.id
    )

    skala = db.get(SkalaNilai, detail.nilai)

    return {
        "message": "Nilai berhasil disimpan",
        "krs_detail_id": detail.id,
        "kode_mk": detail.kode_mk,
        "nilai": detail.nilai,
        "bobot": skala.bobot
    }


@app.get("/mahasiswa/nilai")
def get_my_grades(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    details = (
        db.query(KRSDetail)
        .join(KRS, KRS.id == KRSDetail.krs_id)
        .filter(
            KRS.nim == nim,
            KRS.status == "approved"
        )
        .all()
    )

    hasil = []

    for detail in details:
        skala = (
            db.get(SkalaNilai, detail.nilai)
            if detail.nilai else None
        )

        kehadiran = db.query(Kehadiran).filter(
            Kehadiran.krs_detail_id == detail.id
        ).first()

        persentase = None

        if kehadiran:
            persentase = round(
                kehadiran.jumlah_hadir /
                kehadiran.total_pertemuan * 100,
                2
            )

        hasil.append({
            "nim": nim,
            "kode_mk": detail.kode_mk,
            "nama_mk": detail.mata_kuliah.nama_mk,
            "sks": detail.mata_kuliah.sks,
            "nilai": detail.nilai,
            "bobot": skala.bobot if skala else None,
            "persentase_kehadiran": persentase
        })

    return {
        "nim": nim,
        "total_mata_kuliah": len(hasil),
        "mata_kuliah": hasil
    }



def build_transcript_data(db: Session, nim: str, nama: str, semester: str):
    all_details = (
        db.query(KRSDetail)
        .join(KRS, KRS.id == KRSDetail.krs_id)
        .filter(
            KRS.nim == nim,
            KRS.status == "approved",
            KRSDetail.nilai.isnot(None)
        )
        .all()
    )

    semester_details = [
        detail for detail in all_details
        if detail.krs.semester == semester
    ]

    mata_kuliah = []
    total_sks = 0
    total_bobot_semester = 0

    for detail in semester_details:
        skala = db.get(SkalaNilai, detail.nilai)

        if not skala:
            continue

        sks = detail.mata_kuliah.sks
        bobot = skala.bobot

        total_sks += sks
        total_bobot_semester += bobot * sks

        kehadiran = db.query(Kehadiran).filter(
            Kehadiran.krs_detail_id == detail.id
        ).first()

        persentase = None

        if kehadiran and kehadiran.total_pertemuan > 0:
            persentase = round(
                kehadiran.jumlah_hadir /
                kehadiran.total_pertemuan * 100,
                2
            )

        mata_kuliah.append({
            "nim": nim,
            "kode_mk": detail.kode_mk,
            "nama_mk": detail.mata_kuliah.nama_mk,
            "sks": sks,
            "nilai": detail.nilai,
            "bobot": bobot,
            "persentase_kehadiran": persentase
        })

    ip_semester = (
        round(total_bobot_semester / total_sks, 2)
        if total_sks else 0.0
    )

    total_sks_kumulatif = 0
    total_bobot_kumulatif = 0

    for detail in all_details:
        skala = db.get(SkalaNilai, detail.nilai)

        if not skala:
            continue

        sks = detail.mata_kuliah.sks
        total_sks_kumulatif += sks
        total_bobot_kumulatif += skala.bobot * sks

    ipk = (
        round(total_bobot_kumulatif / total_sks_kumulatif, 2)
        if total_sks_kumulatif else 0.0
    )

    return {
        "nim": nim,
        "nama": nama,
        "total_sks": total_sks,
        "ip_semester": ip_semester,
        "ipk": ipk,
        "mata_kuliah": mata_kuliah
    }


@app.get(
    "/mahasiswa/transkrip",
    response_model=TranskripResponse
)
def get_my_transcript(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    return build_transcript_data(
        db=db,
        nim=nim,
        nama=current_user.name,
        semester=semester
    )


@app.get("/mahasiswa/transkrip/csv")
def export_transcript_csv(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    transcript = build_transcript_data(
        db=db,
        nim=nim,
        nama=current_user.name,
        semester=semester
    )

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "NIM", "Nama", "Semester", "Kode MK",
        "Nama Mata Kuliah", "SKS", "Nilai",
        "Bobot", "Kehadiran (%)"
    ])

    for item in transcript["mata_kuliah"]:
        writer.writerow([
            transcript["nim"],
            transcript["nama"],
            semester,
            item["kode_mk"],
            item["nama_mk"],
            item["sks"],
            item["nilai"],
            item["bobot"],
            item["persentase_kehadiran"]
        ])

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="transkrip_{semester}.csv"'
        }
    )


@app.get("/mahasiswa/transkrip/pdf")
def export_transcript_pdf(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nim = get_mahasiswa_nim(db, current_user)

    transcript = build_transcript_data(
        db=db,
        nim=nim,
        nama=current_user.name,
        semester=semester
    )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph("TRANSKRIP NILAI MAHASISWA", styles["Title"]),
        Spacer(1, 15),
        Paragraph(f"NIM: {transcript['nim']}", styles["Normal"]),
        Paragraph(f"Nama: {transcript['nama']}", styles["Normal"]),
        Paragraph(f"Semester: {semester}", styles["Normal"]),
        Spacer(1, 15)
    ]

    table_data = [[
        "Kode MK", "Mata Kuliah", "SKS", "Nilai", "Bobot"
    ]]

    for item in transcript["mata_kuliah"]:
        table_data.append([
            item["kode_mk"],
            item["nama_mk"],
            str(item["sks"]),
            item["nilai"],
            str(item["bobot"])
        ])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[75, 190, 40, 50, 50]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        f"Total SKS Semester: {transcript['total_sks']}",
        styles["Normal"]
    ))
    elements.append(Paragraph(
        f"IP Semester: {transcript['ip_semester']:.2f}",
        styles["Normal"]
    ))
    elements.append(Paragraph(
        f"IPK: {transcript['ipk']:.2f}",
        styles["Normal"]
    ))

    document.build(elements)

    pdf_content = buffer.getvalue()
    buffer.close()

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="transkrip_{semester}.pdf"'
        }
    )

# ==========================================
# MODUL KEUANGAN
# WEEK 9-10
# ==========================================

@app.post("/admin/billing/generate")
def generate_billing(
    data: BillingGenerateRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    result = BillingService.generate_billing(
        db=db,
        semester=data.semester,
        tanggal_mulai=data.tanggal_mulai
    )

    return {
        "message": "Pembuatan tagihan berhasil",
        "data": result
    }


@app.get("/billing/me")
def get_my_billing(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    applicant = db.query(Applicant).filter(
        Applicant.user_id == current_user.id
    ).first()

    if not applicant or not applicant.nim:
        raise HTTPException(
            status_code=404,
            detail="Data mahasiswa atau NIM tidak ditemukan"
        )

    billings = db.query(Billing).filter(
        Billing.nim == applicant.nim
    ).order_by(Billing.semester.desc()).all()

    return {
        "nim": applicant.nim,
        "total_tagihan": len(billings),
        "data": [
            {
                "id": billing.id,
                "semester": billing.semester,
                "total_amount": billing.total_amount,
                "paid_amount": billing.paid_amount,
                "fine_amount": billing.fine_amount,
                "due_date": billing.due_date,
                "status": billing.status
            }
            for billing in billings
        ]
    }


@app.get("/billing/{billing_id}/payments")
def get_billing_payments(
    billing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    applicant = db.query(Applicant).filter(
        Applicant.user_id == current_user.id
    ).first()

    if not applicant or not applicant.nim:
        raise HTTPException(
            status_code=404,
            detail="Data mahasiswa tidak ditemukan"
        )

    billing = db.query(Billing).filter(
        Billing.id == billing_id,
        Billing.nim == applicant.nim
    ).first()

    if not billing:
        raise HTTPException(
            status_code=404,
            detail="Tagihan tidak ditemukan"
        )

    payments = PaymentService.get_payment_history(
        db=db,
        billing_id=billing_id
    )

    return {
        "billing_id": billing.id,
        "nim": billing.nim,
        "semester": billing.semester,
        "total_pembayaran": len(payments),
        "data": [
            {
                "payment_id": payment.id,
                "metode_pembayaran": payment.payment_method.nama_metode,
                "jumlah": payment.amount,
                "transaction_id": payment.transaction_id,
                "status": payment.status,
                "tanggal_pembayaran": payment.paid_at
            }
            for payment in payments
        ]
    }


@app.post("/admin/billing/{billing_id}/update")
def update_billing(
    billing_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    billing = BillingService.update_billing_status(
        db=db,
        billing_id=billing_id
    )

    return {
        "message": "Status tagihan berhasil diperbarui",
        "data": {
            "id": billing.id,
            "nim": billing.nim,
            "semester": billing.semester,
            "total_amount": billing.total_amount,
            "paid_amount": billing.paid_amount,
            "fine_amount": billing.fine_amount,
            "due_date": billing.due_date,
            "status": billing.status
        }
    }


@app.get("/payment-methods")
def get_payment_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    methods = db.query(PaymentMethod).filter(
        PaymentMethod.is_active == True
    ).order_by(PaymentMethod.id.asc()).all()

    return {
        "total_metode": len(methods),
        "data": [
            {
                "id": method.id,
                "nama_metode": method.nama_metode
            }
            for method in methods
        ]
    }

# ==========================================
# PAYMENT WEBHOOK
# ==========================================

class PaymentWebhookRequest(BaseModel):
    transaction_id: str
    billing_id: int
    payment_method_id: int
    amount: int
    status: str


@app.post("/webhook/payment")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    payload = await request.body()

    signature = request.headers.get(
        "X-Webhook-Signature", ""
    )

    secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")

    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook secret belum dikonfigurasi"
        )

    valid = PaymentWebhookService.verify_signature(
        payload,
        signature,
        secret
    )

    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Signature webhook tidak valid"
        )

    try:
        data = PaymentWebhookRequest.model_validate_json(payload)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Format payload webhook tidak valid"
        )

    if data.status != "success":
        return {
            "message": "Pembayaran belum berhasil",
            "status": data.status
        }

    # Mencegah transaksi yang sama diproses dua kali.
    existing = db.query(Payment).filter(
        Payment.transaction_id == data.transaction_id
    ).first()

    if existing:
        return {
            "message": "Transaksi sudah pernah diproses",
            "payment_id": existing.id
        }

    result = PaymentService.record_payment(
        db=db,
        billing_id=data.billing_id,
        payment_method_id=data.payment_method_id,
        amount=data.amount,
        transaction_id=data.transaction_id
    )

    PaymentWebhookService.send_receipt(result)

    return {
        "message": "Webhook berhasil diproses",
        "payment": result
    }
