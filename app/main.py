
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
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
    MataKuliah
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
    JadwalResponse
)

from app.security import hash_password, verify_password
from app.services.krs_manager import KRSManager
from app.services.schedule_service import ScheduleService


from app.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    UserResponse
)

from app.security import hash_password, verify_password
app = FastAPI(
    title="PMB Backend API",
    description="API Pendaftaran Mahasiswa Baru",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "PMB Backend API berhasil dijalankan"
    }



@app.post("/register", response_model=RegisterResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(
        User.email == data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email sudah terdaftar"
        )

    try:
        # Simpan data user
        new_user = User(
    name=data.name,
    email=data.email,
    password=hash_password(data.password)
)

        db.add(new_user)
        db.flush()

        # Simpan data calon mahasiswa
        new_applicant = Applicant(
            user_id=new_user.id,
            tanggal_lahir=data.tanggal_lahir,
            alamat=data.alamat
        )

        db.add(new_applicant)
        db.flush()

        # Simpan data pendaftaran
        new_registration = Registration(
            applicant_id=new_applicant.id,
            program_studi=data.program_studi
        )

        db.add(new_registration)
        db.commit()

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
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.password):
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
def get_profile(current_user: User = Depends(get_current_user)):
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


@app.get("/admin/registrations")
def get_all_registrations(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    registrations = db.query(Registration).all()

    return registrations
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

    db.commit()
    db.refresh(registration)

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
# API KRS WEEK 6
# ==========================================

from app.models import KRS, KRSDetail
from app.schemas import (
    KRSAddCourseRequest,
    KRSRevisionRequest,
    KRSAdvisorAssignmentRequest,
)
from app.services.krs_manager import KRSManager


def get_mahasiswa_nim(db: Session, current_user: User):
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

    if registration is None or registration.status_pendaftaran != "diterima":
        raise HTTPException(
            status_code=403,
            detail="Pendaftaran mahasiswa belum diterima"
        )

    return applicant.nim


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
    current_user: User = Depends(get_current_user),
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
                "jam_selesai": str(detail.mata_kuliah.jam_selesai),
            }
            for detail in krs.details
        ]
    }


@app.post("/krs/{semester}/courses")
def add_krs_course(
    semester: str,
    data: KRSAddCourseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nim = get_mahasiswa_nim(db, current_user)

    manager = KRSManager(db)
    result = manager.add_course(
        nim,
        semester,
        data.kode_mk
    )

    check_krs_result(result)

    return {"message": result.message}


@app.delete("/krs/{semester}/courses/{kode_mk}")
def delete_krs_course(
    semester: str,
    kode_mk: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nim = get_mahasiswa_nim(db, current_user)

    manager = KRSManager(db)
    result = manager.remove_course(
        nim,
        semester,
        
        kode_mk
    )

    check_krs_result(result)

    return {"message": result.message}


@app.post("/krs/{semester}/validate")
def validate_student_krs(
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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

    return {"message": result.message}


@app.put("/admin/krs/{nim}/{semester}/advisor")
def assign_krs_advisor(
    nim: str,
    semester: str,
    data: KRSAdvisorAssignmentRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
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
        "dosen_pa": dosen.name,
    }


@app.post("/dosen-pa/krs/{nim}/{semester}/approve")
def approve_student_krs(
    nim: str,
    semester: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    return {"message": result.message}


@app.post("/dosen-pa/krs/{nim}/{semester}/revise")
def revise_student_krs(
    nim: str,
    semester: str,
    data: KRSRevisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    return {"message": result.message}

# ==========================================
# API NOTIFIKASI KRS
# ==========================================

from app.models import KRSNotification


@app.get("/notifications/me")
def get_my_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
                "created_at": item.created_at,
            }
            for item in notifications
        ],
    }


@app.put("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(KRSNotification)
        .filter(
            KRSNotification.id == notification_id,
            KRSNotification.recipient_id == current_user.id,
        )
        .first()
    )

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notifikasi tidak ditemukan",
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
        "is_read": notification.is_read,
    }

# ==========================================
# API JADWAL DAN RUANGAN WEEK 7-8
# ==========================================


# ==========================================
# HELPER VALIDASI JADWAL
# ==========================================

def check_schedule_result(result):
    if result.get("success"):
        return

    message = result.get("message", "Terjadi kesalahan")

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

    if db.query(Jadwal).filter(
        Jadwal.ruangan_id == ruangan_id
    ).first():
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
