from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Jadwal,
    Ruangan,
    MataKuliah,
    KRS,
    KRSDetail,
    Applicant,
    User,
    KRSNotification,
)

from app.services.notification_manager import NotificationManager


class ScheduleService:

    def __init__(self, db: Session):
        self.db = db
        self.notification_manager = NotificationManager()

    # =========================
    # CEK KAPASITAS RUANGAN
    # =========================
    def check_capacity(self, ruangan_id, jumlah_peserta):
        ruangan = self.db.query(Ruangan).filter(
            Ruangan.id == ruangan_id
        ).first()

        if not ruangan:
            return False, "Ruangan tidak ditemukan"

        if jumlah_peserta < 0:
            return False, "Jumlah peserta tidak boleh negatif"

        if jumlah_peserta > ruangan.kapasitas:
            return False, (
                f"Kapasitas ruangan {ruangan.kode_ruangan} "
                f"hanya {ruangan.kapasitas} orang"
            )

        return True, "Kapasitas ruangan mencukupi"

    # =========================
    # DETEKSI KONFLIK JADWAL
    # =========================
    def detect_conflicts(
        self,
        hari,
        jam_mulai,
        jam_selesai,
        ruangan_id,
        dosen,
        exclude_id=None
    ):
        query = self.db.query(Jadwal).filter(
            Jadwal.hari == hari,
            Jadwal.jam_mulai < jam_selesai,
            Jadwal.jam_selesai > jam_mulai
        )

        if exclude_id is not None:
            query = query.filter(Jadwal.id != exclude_id)

        existing_schedules = query.all()
        conflicts = []

        for jadwal in existing_schedules:
            conflict_types = ["time_overlap"]

            if jadwal.ruangan_id == ruangan_id:
                conflict_types.append("room_conflict")

            if jadwal.dosen.casefold() == dosen.casefold():
                conflict_types.append("lecturer_conflict")

            if len(conflict_types) > 1:
                conflicts.append({
                    "type": conflict_types,
                    "schedule_id": jadwal.id,
                    "message": (
                        "Jadwal memiliki konflik waktu, "
                        "ruangan, atau dosen"
                    )
                })

        return conflicts

    # =========================
    # VALIDASI MATA KULIAH
    # =========================
    def check_course(self, kode_mk):
        mata_kuliah = self.db.query(MataKuliah).filter(
            MataKuliah.kode_mk == kode_mk
        ).first()

        if not mata_kuliah:
            return False, "Mata kuliah tidak ditemukan"

        return True, "Mata kuliah ditemukan"

    # =========================
    # DATA UNTUK NOTIFIKASI
    # =========================
    def _schedule_data(self, jadwal):
        return {
            "schedule_id": jadwal.id,
            "kode_mk": jadwal.kode_mk,
            "ruangan_id": jadwal.ruangan_id,
            "dosen": jadwal.dosen,
            "hari": jadwal.hari,
            "jam_mulai": str(jadwal.jam_mulai),
            "jam_selesai": str(jadwal.jam_selesai),
            "jumlah_peserta": jadwal.jumlah_peserta
        }

    # =========================
    # INTEGRASI DAN NOTIFIKASI KRS
    # =========================
    
    def _notify_affected_krs(self, kode_mk, action):
        if not kode_mk:
            return

        daftar_krs = self.db.query(KRS).join(
            KRSDetail,
            KRSDetail.krs_id == KRS.id
        ).filter(
            KRSDetail.kode_mk == kode_mk
        ).all()

        if not daftar_krs:
            return

        try:
            for krs in daftar_krs:
                # Tandai KRS agar perlu ditinjau ulang
                krs.needs_review = True

                message = (
                    f"Jadwal mata kuliah {kode_mk} mengalami perubahan "
                    f"(aksi: {action}). Silakan periksa kembali KRS Anda."
                )

                penerima = set()

                # Notifikasi mahasiswa
                mahasiswa = self.db.query(Applicant).filter(
                    Applicant.nim == krs.nim
                ).first()

                if mahasiswa:
                    penerima.add(mahasiswa.user_id)

                # Notifikasi dosen PA
                if krs.dosen_pa:
                    try:
                        dosen_id = int(krs.dosen_pa)

                        dosen = self.db.query(User).filter(
                            User.id == dosen_id,
                            User.role == "dosen_pa"
                        ).first()

                        if dosen:
                            penerima.add(dosen.id)

                    except (ValueError, TypeError):
                        pass

                # Simpan notifikasi
                for recipient_id in penerima:
                    self.db.add(
                        KRSNotification(
                            krs_id=krs.id,
                            recipient_id=recipient_id,
                            message=message
                        )
                    )

            self.db.commit()

            print(
                f"[KRS REVIEW] {len(daftar_krs)} KRS "
                f"ditandai perlu ditinjau untuk {kode_mk}"
            )

        except Exception as error:
            self.db.rollback()
            print(
                f"[KRS NOTIFICATION ERROR] "
                f"Gagal memproses KRS: {error}"
            )

    # =========================
    # MENGHITUNG GANGGUAN KRS
    # =========================
    def _count_student_disruptions(
        self,
        kode_mk,
        hari,
        jam_mulai,
        jam_selesai
    ):
        krs_aktif = self.db.query(KRS.id).filter(
            KRS.status.in_(["submitted", "approved"])
        ).all()

        krs_ids = [item[0] for item in krs_aktif]

        if not krs_ids:
            return 0

        jumlah = self.db.query(
            KRSDetail.krs_id
        ).join(
            Jadwal,
            Jadwal.kode_mk == KRSDetail.kode_mk
        ).filter(
            KRSDetail.krs_id.in_(krs_ids),
            KRSDetail.kode_mk != kode_mk,
            Jadwal.hari == hari,
            Jadwal.jam_mulai < jam_selesai,
            Jadwal.jam_selesai > jam_mulai
        ).distinct().count()

        return jumlah

    # =========================
    # REKOMENDASI 3 ALTERNATIF
    # =========================
    def recommend_alternatives(self, schedule_id):
        jadwal = self.get_schedule(schedule_id)

        if not jadwal:
            return {
                "success": False,
                "message": "Jadwal tidak ditemukan",
                "alternatives": []
            }

        # Mempertahankan durasi jadwal yang lama
        awal = datetime.combine(date.today(), jadwal.jam_mulai)
        akhir = datetime.combine(date.today(), jadwal.jam_selesai)
        durasi = akhir - awal

        ruangan_list = self.db.query(Ruangan).order_by(
            Ruangan.kapasitas
        ).all()

        alternatives = []

        # Slot waktu yang diperiksa: 08.00 sampai 18.00
        jam_awal = datetime.combine(date.today(), time(8, 0))
        batas_akhir = datetime.combine(date.today(), time(18, 0))

        # Periksa enam hari perkuliahan
        for hari in range(1, 7):
            waktu_mulai = jam_awal

            while waktu_mulai + durasi <= batas_akhir:
                waktu_selesai = waktu_mulai + durasi

                for ruangan in ruangan_list:

                    # Kapasitas ruangan harus mencukupi
                    if ruangan.kapasitas < jadwal.jumlah_peserta:
                        continue

                    # Periksa konflik ruangan dan dosen
                    conflicts = self.detect_conflicts(
                        hari=hari,
                        jam_mulai=waktu_mulai.time(),
                        jam_selesai=waktu_selesai.time(),
                        ruangan_id=ruangan.id,
                        dosen=jadwal.dosen,
                        exclude_id=jadwal.id
                    )

                    if conflicts:
                        continue

                    # Hitung mahasiswa yang berpotensi terganggu
                    disruptions = self._count_student_disruptions(
                        kode_mk=jadwal.kode_mk,
                        hari=hari,
                        jam_mulai=waktu_mulai.time(),
                        jam_selesai=waktu_selesai.time()
                    )

                    alternatives.append({
                        "hari": hari,
                        "jam_mulai": waktu_mulai.strftime("%H:%M:%S"),
                        "jam_selesai": waktu_selesai.strftime("%H:%M:%S"),
                        "ruangan_id": ruangan.id,
                        "nama_ruangan": ruangan.nama_ruangan,
                        "kapasitas": ruangan.kapasitas,
                        "jumlah_peserta": jadwal.jumlah_peserta,
                        "student_disruptions": disruptions,
                        "score": disruptions
                    })

                waktu_mulai += timedelta(minutes=30)

        # Prioritaskan pilihan dengan gangguan KRS paling sedikit
        alternatives.sort(
            key=lambda item: (
                item["score"],
                item["hari"],
                item["jam_mulai"],
                item["kapasitas"]
            )
        )

        return {
            "success": True,
            "message": "Rekomendasi alternatif berhasil dibuat",
            "schedule_id": jadwal.id,
            "kode_mk": jadwal.kode_mk,
            "method": "Rule-based scheduling heuristic",
            "alternatives": alternatives[:3]
        }

    # =========================
    # MEMBUAT JADWAL
    # =========================
    def create_schedule(
        self,
        kode_mk,
        ruangan_id,
        dosen,
        hari,
        jam_mulai,
        jam_selesai,
        jumlah_peserta
    ):
        if hari < 1 or hari > 6:
            return {
                "success": False,
                "message": "Hari harus berada antara 1 sampai 6",
                "conflicts": []
            }

        if jam_mulai >= jam_selesai:
            return {
                "success": False,
                "message": "Jam mulai harus sebelum jam selesai",
                "conflicts": []
            }

        course_ok, course_message = self.check_course(kode_mk)

        if not course_ok:
            return {
                "success": False,
                "message": course_message,
                "conflicts": []
            }

        conflicts = self.detect_conflicts(
            hari,
            jam_mulai,
            jam_selesai,
            ruangan_id,
            dosen
        )

        if conflicts:
            return {
                "success": False,
                "message": "Jadwal memiliki konflik",
                "conflicts": conflicts
            }

        capacity_ok, capacity_message = self.check_capacity(
            ruangan_id,
            jumlah_peserta
        )

        if not capacity_ok:
            return {
                "success": False,
                "message": capacity_message,
                "conflicts": []
            }

        jadwal = Jadwal(
            kode_mk=kode_mk,
            ruangan_id=ruangan_id,
            dosen=dosen,
            hari=hari,
            jam_mulai=jam_mulai,
            jam_selesai=jam_selesai,
            jumlah_peserta=jumlah_peserta
        )

        try:
            self.db.add(jadwal)
            self.db.commit()
            self.db.refresh(jadwal)

            self.notification_manager.notify_schedule_changed(
                "SCHEDULE_CHANGED",
                {
                    "action": "created",
                    **self._schedule_data(jadwal)
                }
            )

            self._notify_affected_krs(kode_mk, "created")

            return {
                "success": True,
                "message": "Jadwal berhasil dibuat",
                "schedule_id": jadwal.id,
                "conflicts": []
            }

        except Exception:
            self.db.rollback()
            raise

    # =========================
    # MENGAMBIL SEMUA JADWAL
    # =========================
    def get_schedules(self):
        return self.db.query(Jadwal).order_by(
            Jadwal.hari,
            Jadwal.jam_mulai
        ).all()

    # =========================
    # MENGAMBIL JADWAL BERDASARKAN ID
    # =========================
    def get_schedule(self, schedule_id):
        return self.db.query(Jadwal).filter(
            Jadwal.id == schedule_id
        ).first()

    # =========================
    # MEMPERBARUI JADWAL
    # =========================
    def update_schedule(
        self,
        schedule_id,
        kode_mk,
        ruangan_id,
        dosen,
        hari,
        jam_mulai,
        jam_selesai,
        jumlah_peserta
    ):
        jadwal = self.get_schedule(schedule_id)

        if not jadwal:
            return {
                "success": False,
                "message": "Jadwal tidak ditemukan"
            }

        kode_mk_lama = jadwal.kode_mk

        if hari < 1 or hari > 6:
            return {
                "success": False,
                "message": "Hari harus berada antara 1 sampai 6",
                "conflicts": []
            }

        if jam_mulai >= jam_selesai:
            return {
                "success": False,
                "message": "Jam mulai harus sebelum jam selesai",
                "conflicts": []
            }

        course_ok, course_message = self.check_course(kode_mk)

        if not course_ok:
            return {
                "success": False,
                "message": course_message,
                "conflicts": []
            }

        conflicts = self.detect_conflicts(
            hari,
            jam_mulai,
            jam_selesai,
            ruangan_id,
            dosen,
            exclude_id=schedule_id
        )

        if conflicts:
            return {
                "success": False,
                "message": "Perubahan jadwal memiliki konflik",
                "conflicts": conflicts
            }

        capacity_ok, capacity_message = self.check_capacity(
            ruangan_id,
            jumlah_peserta
        )

        if not capacity_ok:
            return {
                "success": False,
                "message": capacity_message,
                "conflicts": []
            }

        jadwal.kode_mk = kode_mk
        jadwal.ruangan_id = ruangan_id
        jadwal.dosen = dosen
        jadwal.hari = hari
        jadwal.jam_mulai = jam_mulai
        jadwal.jam_selesai = jam_selesai
        jadwal.jumlah_peserta = jumlah_peserta

        try:
            self.db.commit()
            self.db.refresh(jadwal)

            self.notification_manager.notify_schedule_changed(
                "SCHEDULE_CHANGED",
                {
                    "action": "updated",
                    **self._schedule_data(jadwal)
                }
            )

            self._notify_affected_krs(kode_mk_lama, "updated")

            if kode_mk != kode_mk_lama:
                self._notify_affected_krs(kode_mk, "updated")

            return {
                "success": True,
                "message": "Jadwal berhasil diperbarui",
                "schedule_id": jadwal.id,
                "conflicts": []
            }

        except Exception:
            self.db.rollback()
            raise

    # =========================
    # MENGHAPUS JADWAL
    # =========================
    def delete_schedule(self, schedule_id):
        jadwal = self.get_schedule(schedule_id)

        if not jadwal:
            return {
                "success": False,
                "message": "Jadwal tidak ditemukan"
            }

        data_jadwal = self._schedule_data(jadwal)
        kode_mk = jadwal.kode_mk

        try:
            self.db.delete(jadwal)
            self.db.commit()

            self.notification_manager.notify_schedule_changed(
                "SCHEDULE_CHANGED",
                {
                    "action": "deleted",
                    **data_jadwal
                }
            )

            self._notify_affected_krs(kode_mk, "deleted")

            return {
                "success": True,
                "message": "Jadwal berhasil dihapus"
            }

        except Exception:
            self.db.rollback()
            raise