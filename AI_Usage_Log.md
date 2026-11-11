# AI USAGE LOG

**Nama:** Nazwa Khoirun  
**Proyek:** PMB Backend API  
**Modul:** Kartu Rencana Studi (KRS)  
**Teknologi:** Python, FastAPI, SQLAlchemy, SQLite, Alembic, Pytest, Hypothesis

## 1. Tujuan Penggunaan AI

AI digunakan sebagai alat bantu selama pengembangan PMB Backend, terutama untuk memahami kode, merancang struktur modul KRS, menemukan kesalahan, menyusun pengujian, dan memperbaiki dokumentasi.

AI digunakan sebagai pendamping. Perubahan kode tetap diperiksa dan dijalankan oleh pengguna sebelum dianggap berhasil.

## 2. Aktivitas Penggunaan AI

1. Memahami struktur folder dan file pada proyek FastAPI.
2. Memahami autentikasi dan otorisasi menggunakan JWT.
3. Memahami model database menggunakan SQLAlchemy.
4. Membantu memeriksa dan memperbaiki kesalahan kode.
5. Membantu menyusun migration database menggunakan Alembic.
6. Membantu membuat dan memeriksa endpoint API.
7. Membantu menyusun pengujian unit dan integrasi.
8. Membantu memahami pola desain Chain of Responsibility.
9. Membantu menyusun dokumentasi keputusan arsitektur.

## 3. Aktivitas Pengembangan Modul KRS Week 5

1. Membantu merancang model MataKuliah, KRS, KRSDetail, Prasyarat, dan SkalaNilai.
2. Membantu mengembangkan KRSManager.
3. Membantu menerapkan DuplicateValidator.
4. Membantu menerapkan SKSValidator dengan batas maksimal 24 SKS.
5. Membantu menerapkan PrerequisiteValidator.
6. Membantu menerapkan ConflictValidator.
7. Membantu menyusun Chain of Responsibility.
8. Membantu menyiapkan pengujian dasar modul KRS.

## 4. Aktivitas Pengembangan Modul KRS Week 6

1. Membantu mengembangkan KRSManager untuk tambah, hapus, validasi, submit, approve, dan revise.
2. Membantu menerapkan State Machine untuk empat status KRS.
3. Membantu membatasi transisi status berdasarkan aktor.
4. Membantu menerapkan pemeriksaan role dan kepemilikan KRS pada endpoint.
5. Membantu membuat endpoint penetapan dosen PA.
6. Membantu membuat endpoint submit, approve, dan revise.
7. Membantu menambahkan model KRSLog untuk pencatatan aktivitas.
8. Membantu menambahkan KRSNotification untuk notifikasi pengguna.
9. Membantu menerapkan optimistic locking menggunakan version_id.
10. Membantu membuat migration untuk tabel log, notifikasi, dan kolom version_id.
11. Membantu menyusun pengujian State Machine dan Property-Based Testing menggunakan Hypothesis.
12. Membantu membuat pengujian API menggunakan FastAPI TestClient.

## 5. Best Prompt

"Bantu saya mengembangkan modul KRS pada proyek PMB Backend yang sudah ada. Pertahankan fitur PMB sebelumnya, terapkan aturan bisnis sesuai instruksi tugas, gunakan Chain of Responsibility dan State Machine, serta berikan langkah perbaikan secara bertahap. Setiap perubahan harus dapat diuji menggunakan pytest."

## 6. Hasil Pengujian

Pengujian akhir yang dijalankan menggunakan perintah:

`python -m pytest -q`

Hasil terakhir:

**59 passed, 22 warnings**

Rincian pengujian:
- Fitur PMB sebelumnya: 12 pengujian.
- Aturan dasar KRS dan prasyarat: 9 pengujian.
- State Machine: 33 pengujian.
- Property-Based Testing: 2 pengujian.
- Integrasi API KRS: 3 pengujian.

Property-Based Testing menggunakan Hypothesis dengan pengaturan maksimal 1.000 contoh untuk pengujian batas SKS dan 1.000 contoh untuk pengujian bentrok jadwal.

## 7. Kontribusi AI

AI membantu:
- Menjelaskan struktur dan fungsi kode.
- Memberikan rancangan implementasi.
- Membantu mengidentifikasi kesalahan.
- Menyusun kode pengujian.
- Menjelaskan hasil pengujian.
- Membantu menyusun dokumentasi proyek.

## 8. Kontribusi Pengguna

Pengguna:
- Memeriksa kode dan struktur proyek.
- Menjalankan perintah melalui PowerShell.
- Menerapkan perubahan kode yang diperlukan.
- Menjalankan pengujian dan mengirim hasilnya.
- Memeriksa hasil migration database.
- Memastikan perubahan tidak merusak pengujian fitur PMB sebelumnya.

## 9. Keterbatasan dan Catatan

1. Pengiriman email otomatis belum diintegrasikan.
2. Notifikasi saat ini disimpan dalam database dan dapat dibaca melalui API.
3. SQLite tidak menerapkan row-level locking melalui `with_for_update()`.
4. Optimistic locking menggunakan version_id sudah diterapkan, tetapi pengujian konkurensi paralel secara khusus belum dilakukan.
5. Terdapat peringatan kompatibilitas TestClient/httpx dan panjang secret key JWT pada hasil pengujian terakhir.

## 10. Kesimpulan

Penggunaan AI membantu proses pengembangan dan pemahaman modul KRS Week 5 dan Week 6. AI digunakan sebagai alat bantu, sedangkan penerapan kode, pemeriksaan hasil, dan pengujian dilakukan oleh pengguna.
