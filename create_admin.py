from getpass import getpass

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


db = SessionLocal()

try:
    email = input("Masukkan email admin: ").strip()
    name = input("Masukkan nama admin: ").strip()

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        print("Email sudah terdaftar!")
    else:
       password = getpass("Masukkan password admin: ")

        admin = User(
            name=name,
            email=email,
            password=hash_password(password),
            role="admin"
        )

        db.add(admin)
        db.commit()

        print("Akun admin berhasil dibuat!")

finally:
    db.close()