import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, RevokedToken


SECRET_KEY = os.getenv("PMB_SECRET_KEY", "")

if len(SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError(
        "PMB_SECRET_KEY belum tersedia atau panjangnya kurang dari 32 byte."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = HTTPBearer()


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire,
        "jti": secrets.token_urlsafe(16),
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_access_token(token: str):
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except InvalidTokenError:
        return None


def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
):
    payload = verify_access_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau sudah kedaluwarsa",
        )

    return payload


def get_current_user(
    payload: dict = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
):
    jti = payload.get("jti")

    if not jti:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid",
        )

    revoked = db.query(RevokedToken).filter(
        RevokedToken.jti == jti
    ).first()

    if revoked:
        raise HTTPException(
            status_code=401,
            detail="Token sudah logout",
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid",
        )

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Identitas pengguna pada token tidak valid",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Pengguna tidak ditemukan",
        )

    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak. Khusus admin.",
        )

    return current_user
