# PMB Backend API - Week 6

Backend API untuk Penerimaan Mahasiswa Baru (PMB) dan pengelolaan Kartu Rencana Studi (KRS).

## Teknologi
- Python 3.11
- FastAPI
- SQLAlchemy
- SQLite
- Alembic
- JWT Authentication
- Pytest
- Hypothesis

## Instalasi

Buat virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Pasang dependensi:

```powershell
python -m pip install -r requirements.txt
```

## Konfigurasi JWT

Aplikasi membutuhkan environment variable PMB_SECRET_KEY.

Buat secret acak:

```powershell
$secret = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:PMB_SECRET_KEY = $secret
setx PMB_SECRET_KEY "$secret"
```

Jangan membagikan secret atau mengunggahnya ke repository.

## Migrasi Database

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Database pengembangan menggunakan SQLite.

## Menjalankan Server

```powershell
python -m uvicorn app.main:app --reload
```

Alamat API: http://127.0.0.1:8000

Dokumentasi Swagger: http://127.0.0.1:8000/docs

## Fitur PMB
- Registrasi calon mahasiswa.
- Login dan logout menggunakan JWT.
- Melihat profil pengguna.
- Pengelolaan pendaftaran oleh admin.
- Penerimaan dan penolakan pendaftaran.
- Pembuatan NIM.
- Statistik pendaftaran.

## Fitur KRS

KRSManager menyediakan:
- add_course
- remove_course
- validate_krs
- submit_krs
- approve_krs
- revise_krs

Validasi menggunakan Chain of Responsibility:
1. DuplicateValidator
2. SKSValidator
3. PrerequisiteValidator
4. ConflictValidator

Aturan KRS:
- Mata kuliah tidak boleh duplikat.
- Maksimal 24 SKS.
- Prasyarat harus lulus dengan nilai minimal C dari KRS sebelumnya yang sudah disetujui.
- Jadwal mata kuliah tidak boleh bentrok.

## State Machine

Status KRS:
- draft
- submitted
- approved
- revision

Perubahan status dilakukan melalui metode KRS.transition().

## Log, Notifikasi, dan Concurrency

- KRSLog mencatat aktivitas KRS.
- KRSNotification menyimpan notifikasi pengguna.
- Submit, approve, dan revise menyimpan perubahan status, log, dan notifikasi dalam satu transaksi.
- version_id digunakan untuk optimistic locking.
- SQLite tidak menerapkan row-level locking melalui with_for_update().

Pengiriman email otomatis belum diintegrasikan.

## Pengujian

Jalankan:

```powershell
python -m pytest -q
```

Hasil pengujian terakhir:
59 passed, 1 warning.

Pengujian mencakup fitur PMB, validasi KRS, State Machine, Property-Based Testing, log, notifikasi, dan integrasi API.

## Dokumentasi
- ADR.md
- AI_Usage_Log.md
- OPAR.md
- .github/PULL_REQUEST_TEMPLATE.md

## Catatan
Week 6 merupakan pengembangan lanjutan dari PMB Backend. Fitur PMB lama tetap dipertahankan.
