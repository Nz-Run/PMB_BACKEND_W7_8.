# OPAR - Laporan Pelaksanaan PMB Backend Week 6

**Nama:** Nazwa Khoirun  
**Program Studi:** Teknik Informatika  
**Proyek:** PMB Backend API  
**Modul:** Kartu Rencana Studi (KRS)  
**Tanggal:** 9 November 2026

> Dokumen ini merupakan laporan ringkas pelaksanaan pengembangan Week 6. Jika dosen menyediakan template OPAR dengan susunan atau kepanjangan khusus, sesuaikan struktur dokumen ini dengan template tersebut.

## 1. Ringkasan Proyek

PMB Backend merupakan aplikasi backend untuk proses Penerimaan Mahasiswa Baru. Pada Week 6, proyek dilanjutkan dengan pengembangan modul Kartu Rencana Studi (KRS).

Pengembangan dilakukan pada proyek PMB Backend yang sudah ada, sehingga fitur pendaftaran, autentikasi, dan administrasi tetap dipertahankan.

## 2. Tujuan

Tujuan pengembangan Week 6 adalah:
- Menerapkan alur status KRS menggunakan State Machine.
- Membatasi perubahan status berdasarkan peran pengguna.
- Menyediakan proses pengajuan dan persetujuan KRS.
- Mencatat aktivitas perubahan KRS.
- Menyediakan notifikasi untuk mahasiswa dan dosen PA.
- Menerapkan perlindungan perubahan data menggunakan optimistic locking.
- Menyediakan pengujian sesuai aturan bisnis KRS.

## 3. Proses Pelaksanaan

### 3.1 Pengembangan KRSManager

KRSManager dikembangkan untuk menangani:
- Penambahan mata kuliah.
- Penghapusan mata kuliah.
- Validasi keseluruhan KRS.
- Pengajuan KRS oleh mahasiswa.
- Persetujuan KRS oleh dosen PA.
- Pengembalian KRS untuk revisi.

### 3.2 Penerapan State Machine

KRS memiliki empat status:
- draft
- submitted
- approved
- revision

Perubahan status dilakukan menggunakan metode `KRS.transition()` dan mengikuti aturan aktor yang berwenang.

### 3.3 Penerapan Otorisasi

Pemeriksaan akses diterapkan pada endpoint KRS:
- Mahasiswa mengakses KRS miliknya sendiri.
- Dosen PA hanya memproses KRS mahasiswa bimbingannya.
- Admin menetapkan dosen PA pada KRS.

### 3.4 Pencatatan Aktivitas dan Notifikasi

Tabel KRSLog digunakan untuk mencatat aktivitas dan perubahan status.

Tabel KRSNotification digunakan untuk menyimpan pemberitahuan kepada pengguna. Notifikasi dapat dilihat dan ditandai sudah dibaca melalui endpoint API.

### 3.5 Perlindungan Perubahan Data

Kolom `version_id` digunakan untuk optimistic locking. Pemeriksaan versi diterapkan untuk mendeteksi konflik perubahan data.

### 3.6 Pengujian

Pengujian dilakukan menggunakan pytest, FastAPI TestClient, dan Hypothesis.

## 4. Hasil Pelaksanaan

Hasil implementasi:
- Modul KRS terintegrasi dengan PMB Backend.
- Validasi mata kuliah dan aturan akademik berjalan.
- State Machine memiliki empat transisi yang sah.
- Transisi yang tidak sah berhasil ditolak.
- Log dan notifikasi berhasil disimpan.
- Endpoint mahasiswa, dosen PA, dan admin berhasil diuji.
- Migration database berhasil diterapkan.

## 5. Hasil Pengujian

Hasil pengujian terakhir:

**59 passed, 22 warnings**

| Kelompok pengujian | Jumlah |
|---|---:|
| Pengujian PMB | 12 |
| Pengujian dasar KRS dan prasyarat | 9 |
| State Machine | 33 |
| Property-Based Testing | 2 |
| Integrasi API KRS | 3 |
| **Total** | **59** |

## 6. Keterbatasan

- Pengiriman email otomatis belum diintegrasikan.
- Pengujian konkurensi paralel secara khusus belum dilakukan.
- SQLite tidak menyediakan row-level locking melalui `with_for_update()`.
- Masih terdapat peringatan pada hasil pengujian terkait konfigurasi JWT dan kompatibilitas TestClient/httpx.

## 7. Evaluasi dan Kesimpulan

Pengembangan Week 6 berhasil menambahkan alur pengelolaan KRS, State Machine, otorisasi pengguna, log, notifikasi, dan pengujian integrasi tanpa menyebabkan kegagalan pada pengujian fitur PMB sebelumnya.

Hasil 59 pengujian yang lulus menunjukkan bahwa fitur-fitur yang diuji telah berjalan sesuai dengan skenario pengujiannya. Beberapa keterbatasan tetap perlu diperhatikan dan dapat menjadi pekerjaan lanjutan.
