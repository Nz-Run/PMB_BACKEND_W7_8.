import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import jwt
import qrcode

from sqlalchemy.orm import Session

from app.auth import SECRET_KEY, ALGORITHM
from app.models import Jadwal, PresensiSesi


class AttendanceQRService:

    @staticmethod
    def generate_attendance_qr(
        db: Session,
        schedule_id: int,
        valid_minutes: int = 15
    ):
        if valid_minutes != 15:
            raise ValueError("QR hanya boleh berlaku selama 15 menit.")

        jadwal = db.query(Jadwal).filter(
            Jadwal.id == schedule_id
        ).first()

        if jadwal is None:
            raise ValueError("Jadwal tidak ditemukan.")

        jakarta = ZoneInfo("Asia/Jakarta")
        now_local = datetime.now(jakarta)
        now_utc = datetime.now(timezone.utc)

        waktu_mulai = datetime.combine(
            now_local.date(),
            jadwal.jam_mulai
        )

        sessions = db.query(PresensiSesi).filter(
            PresensiSesi.jadwal_id == schedule_id
        ).all()

        sesi = next(
            (
                item for item in sessions
                if item.waktu_mulai.date() == now_local.date()
            ),
            None
        )

        token_jti = secrets.token_urlsafe(24)
        token_expiry = now_utc + timedelta(minutes=valid_minutes)

        payload = {
            "schedule_id": schedule_id,
            "jti": token_jti,
            "iat": now_utc,
            "exp": token_expiry
        }

        token = jwt.encode(
            payload,
            SECRET_KEY,
            algorithm=ALGORITHM
        )

        if sesi is None:
            sesi = PresensiSesi(
                jadwal_id=schedule_id,
                token_jti=token_jti,
                waktu_mulai=waktu_mulai,
                waktu_kedaluwarsa=(
                    now_local + timedelta(minutes=valid_minutes)
                ),
                valid_minutes=valid_minutes
            )
            db.add(sesi)
        else:
            sesi.token_jti = token_jti
            sesi.waktu_kedaluwarsa = (
                now_local + timedelta(minutes=valid_minutes)
            )
            sesi.valid_minutes = valid_minutes

        db.commit()
        db.refresh(sesi)

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4
        )
        qr.add_data(token)
        qr.make(fit=True)

        image = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        return {
            "session_id": sesi.id,
            "schedule_id": schedule_id,
            "token": token,
            "qr_image": buffer.getvalue(),
            "expires_at": sesi.waktu_kedaluwarsa
        }
