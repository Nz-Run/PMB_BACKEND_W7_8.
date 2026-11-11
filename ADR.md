# Architecture Decision Record (ADR)

**Proyek:** PMB Backend API  
**Modul:** Kartu Rencana Studi (KRS)  
**Tanggal:** 9 November 2026

---

# ADR-001: Penggunaan Chain of Responsibility untuk Validasi KRS

## Status
Accepted (Diterima)

## Konteks
Sistem KRS membutuhkan beberapa aturan validasi sebelum mahasiswa dapat mengambil mata kuliah. Aturan tersebut meliputi:
1. Pemeriksaan mata kuliah duplikat.
2. Batas maksimal 24 SKS.
3. Pemenuhan prasyarat dengan nilai minimal C.
4. Pemeriksaan bentrok jadwal.

Jika seluruh aturan dimasukkan dalam satu fungsi, kode akan lebih sulit dikembangkan dan dipelihara.

## Keputusan
Menggunakan pola desain Chain of Responsibility untuk memisahkan aturan validasi ke dalam kelas validator.

Urutan validator:
1. DuplicateValidator
2. SKSValidator
3. PrerequisiteValidator
4. ConflictValidator

Setiap validator menjalankan pemeriksaan sesuai tanggung jawabnya. Jika pemeriksaan gagal, proses diteruskan sebagai hasil validasi gagal dan rantai dihentikan.

## Alasan
- Memisahkan setiap aturan validasi.
- Memudahkan penambahan aturan baru.
- Membuat kode lebih modular.
- Mempermudah pengujian setiap validator.

## Konsekuensi

**Kelebihan:**
- Kode lebih terstruktur.
- Validator dapat diuji secara terpisah.
- Pemeliharaan menjadi lebih mudah.

**Kekurangan:**
- Membutuhkan beberapa kelas tambahan.
- Urutan validator harus diatur dengan benar.

## Alternatif
Validasi langsung dalam satu fungsi KRSManager. Alternatif ini tidak dipilih karena dapat membuat fungsi terlalu panjang dan sulit dipelihara.

---

# ADR-002: Penggunaan Optimistic Locking untuk Data KRS

## Status
Accepted (Diterima)

## Konteks
Beberapa mahasiswa atau proses aplikasi dapat mencoba mengubah data KRS dalam waktu berdekatan. Sistem perlu mendeteksi perubahan data yang dilakukan oleh proses lain agar perubahan tidak saling menimpa.

## Keputusan
Menggunakan optimistic locking melalui kolom `version_id` pada tabel KRS.

Implementasi meliputi:
- Kolom `version_id` pada model KRS.
- `version_id_col` pada konfigurasi mapper SQLAlchemy.
- Pemeriksaan versi sebelum perubahan detail KRS melalui `_bump_version()`.
- Penanganan konflik menggunakan StaleDataError.

Metode `with_for_update()` tetap digunakan sebagai persiapan untuk database yang mendukung row-level locking.

## Alasan
- Perubahan data dapat dideteksi melalui nomor versi.
- Mendukung penggunaan SQLite selama pengembangan.
- Mengurangi risiko perubahan data yang saling menimpa.
- Tidak memerlukan penguncian baris secara terus-menerus.

## Konsekuensi
- Setiap perubahan data yang dilindungi harus memperhatikan nomor versi.
- Konflik perubahan perlu ditangani dengan rollback.
- SQLite tidak menerapkan row-level locking melalui `with_for_update()`.
- Pengujian konkurensi secara paralel belum dilakukan secara khusus.

## Alternatif
Menggunakan pessimistic locking melalui database yang mendukung `SELECT FOR UPDATE`, seperti PostgreSQL atau MySQL.

## Kesimpulan
Optimistic locking dipilih agar aplikasi dapat mendeteksi perubahan versi KRS, termasuk selama pengembangan menggunakan SQLite.

---

# ADR-003: State Machine untuk Perubahan Status KRS

## Status
Accepted (Diterima)

## Konteks
KRS membutuhkan alur perubahan status yang terkontrol agar mahasiswa dan dosen PA hanya dapat melakukan tindakan sesuai kewenangannya.

## Keputusan
Menggunakan metode `KRS.transition()` sebagai mekanisme perubahan status.

Status KRS:
- draft
- submitted
- approved
- revision

Transisi yang diperbolehkan:

| Status awal | Aktor | Status tujuan |
|---|---|---|
| draft | mahasiswa | submitted |
| submitted | dosen_pa | approved |
| submitted | dosen_pa | revision |
| revision | mahasiswa | submitted |

Transisi selain kombinasi tersebut ditolak.

## Konsekuensi
- Perubahan status lebih terkontrol.
- Aturan transisi dapat diuji menggunakan pengujian parameterized.
- Terdapat 28 kombinasi transisi ilegal yang diuji.
- Perubahan status tidak dilakukan langsung di luar metode transition().

## Kesimpulan
State Machine digunakan untuk menjaga alur KRS agar mengikuti aturan akademik dan pembagian kewenangan pengguna.
---

# ADR-004: Penggunaan Observer Pattern untuk Notifikasi Perubahan Jadwal

## Status
Accepted (Diterima)

## Konteks
Sistem manajemen jadwal membutuhkan mekanisme pemberitahuan ketika jadwal perkuliahan dibuat, diperbarui, atau dihapus.

Perubahan jadwal dapat berdampak pada mahasiswa, dosen, dan admin akademik. Sistem perlu memberitahukan perubahan tersebut kepada pihak-pihak terkait.

## Keputusan
Menggunakan Observer Pattern untuk memisahkan proses perubahan jadwal dengan proses pengiriman notifikasi.

Implementasi terdiri dari:
1. ScheduleSubject sebagai pengelola observer.
2. StudentObserver untuk notifikasi mahasiswa.
3. LecturerObserver untuk notifikasi dosen.
4. AcademicAdminObserver untuk notifikasi admin akademik.

Ketika terjadi perubahan jadwal, sistem memanggil:
`notify('SCHEDULE_CHANGED', data)`

Notifikasi disimulasikan menggunakan logging:
- Email untuk mahasiswa.
- SMS untuk dosen.
- Push notification untuk admin akademik.

## Alasan
- Memisahkan proses pengelolaan jadwal dan notifikasi.
- Memudahkan penambahan observer baru.
- Memungkinkan observer ditambahkan atau dilepas.
- Membuat sistem lebih modular dan mudah diuji.

## Konsekuensi

**Kelebihan:**
- Komponen notifikasi tidak bergantung langsung pada proses CRUD jadwal.
- Beberapa pihak dapat menerima pemberitahuan dari satu event.
- Observer dapat dikembangkan secara terpisah.

**Kekurangan:**
- Membutuhkan kelas tambahan untuk setiap observer.
- Notifikasi masih berupa simulasi logging.
- Pengiriman email, SMS, dan push notification nyata belum diintegrasikan.

## Alternatif
Memanggil fungsi notifikasi secara langsung di setiap proses CRUD jadwal. Alternatif ini tidak dipilih karena dapat membuat kode pengelolaan jadwal lebih bergantung pada implementasi notifikasi.

## Kesimpulan
Observer Pattern dipilih agar pemberitahuan perubahan jadwal dapat dikelola secara modular dan mudah dikembangkan.

---

# ADR-005: Penggunaan Rule-Based Heuristic untuk Rekomendasi Alternatif Jadwal

## Status
Accepted (Diterima)

## Konteks
Sistem membutuhkan fitur Conflict Resolver untuk membantu admin menemukan alternatif jadwal ketika terjadi konflik perkuliahan.

Rekomendasi harus mempertimbangkan ketersediaan ruangan, kapasitas ruangan, ketersediaan dosen, benturan waktu, dan gangguan terhadap jadwal mahasiswa.

## Keputusan
Menggunakan pendekatan rule-based scheduling heuristic untuk menghasilkan tiga rekomendasi alternatif jadwal.

Sistem melakukan:
1. Mempertahankan durasi jadwal awal.
2. Memeriksa ketersediaan ruangan.
3. Memeriksa kapasitas ruangan.
4. Memeriksa benturan waktu dan jadwal dosen.
5. Menghitung potensi gangguan terhadap jadwal mahasiswa.
6. Mengurutkan alternatif berdasarkan skor dan memilih tiga rekomendasi terbaik.

Metode rekomendasi ditampilkan sebagai:
`Rule-based scheduling heuristic`

## Alasan
- Dapat diterapkan tanpa membutuhkan dataset pelatihan.
- Aturan rekomendasi dapat dijelaskan dan diperiksa.
- Mempertimbangkan beberapa faktor dalam pemilihan jadwal.
- Lebih sederhana untuk diterapkan dan diuji pada proyek ini.

## Konsekuensi

**Kelebihan:**
- Rekomendasi dihasilkan berdasarkan aturan yang jelas.
- Tidak membutuhkan model machine learning terlatih.
- Hasil rekomendasi dapat diuji secara otomatis.

**Kekurangan:**
- Kualitas rekomendasi bergantung pada aturan dan skor yang digunakan.
- Belum menggunakan model AI atau machine learning terlatih.
- Rekomendasi tetap perlu diperiksa oleh admin akademik.

## Alternatif
Menggunakan model machine learning untuk optimasi jadwal. Alternatif ini belum dipilih karena membutuhkan dataset, proses pelatihan, dan evaluasi model tambahan.

## Kesimpulan
Rule-Based Heuristic dipilih sebagai pendekatan Conflict Resolver karena sesuai dengan kebutuhan proyek dan dapat memberikan tiga alternatif jadwal berdasarkan aturan yang transparan.