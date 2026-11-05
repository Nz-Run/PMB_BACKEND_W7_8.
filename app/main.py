from datetime import datetime, timezone

from app.auth import (
    create_access_token,
    get_current_user,
    get_current_token_payload,
    get_current_admin
)

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import User, Applicant, Registration, RevokedToken
from sqlalchemy import func

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

    registration.status_pendaftaran = status
    db.commit()
    db.refresh(registration)

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