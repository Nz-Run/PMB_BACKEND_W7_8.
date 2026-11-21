from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException

from app.models import (
    KRS,
    KRSDetail,
    MataKuliah,
    SkalaNilai,
    Kehadiran,
    RiwayatNilai,
)


class GradeService:

    @staticmethod
    def input_nilai(
        db: Session,
        detail_id: int,
        nilai: str,
        admin_id: int
    ):
        # Cari detail KRS
        detail = db.get(KRSDetail, detail_id)

        if not detail:
            raise HTTPException(
                status_code=404,
                detail="Data KRS tidak ditemukan"
            )

        # Pastikan KRS sudah disetujui
        krs = db.get(KRS, detail.krs_id)

        if not krs or krs.status != "approved":
            raise HTTPException(
                status_code=400,
                detail="Nilai hanya dapat diberikan pada KRS yang sudah disetujui"
            )

        # Validasi nilai
        skala = db.get(SkalaNilai, nilai)

        if not skala:
            raise HTTPException(
                status_code=400,
                detail="Skala nilai tidak valid"
            )

        # Validasi kehadiran minimal 75%
        kehadiran = db.scalar(
            select(Kehadiran).where(
                Kehadiran.krs_detail_id == detail_id
            )
        )

        if not kehadiran:
            raise HTTPException(
                status_code=400,
                detail="Data kehadiran belum tersedia"
            )

        persentase = (
            kehadiran.jumlah_hadir / kehadiran.total_pertemuan
        ) * 100

        if persentase < 75:
            raise HTTPException(
                status_code=400,
                detail="Kehadiran kurang dari 75%, nilai belum dapat diberikan"
            )

        # Simpan riwayat perubahan nilai
        riwayat = RiwayatNilai(
            krs_detail_id=detail_id,
            nilai_lama=detail.nilai,
            nilai_baru=nilai,
            changed_by=admin_id
        )

        db.add(riwayat)

        # Simpan nilai terbaru
        detail.nilai = nilai

        db.commit()
        db.refresh(detail)

        return detail

    @staticmethod
    def input_kehadiran(
        db: Session,
        detail_id: int,
        total_pertemuan: int,
        jumlah_hadir: int
    ):
        detail = db.get(KRSDetail, detail_id)

        if not detail:
            raise HTTPException(
                status_code=404,
                detail="Data KRS tidak ditemukan"
            )

        if jumlah_hadir > total_pertemuan:
            raise HTTPException(
                status_code=400,
                detail="Jumlah hadir tidak boleh melebihi total pertemuan"
            )

        if total_pertemuan < 1 or jumlah_hadir < 0:
            raise HTTPException(
                status_code=400,
                detail="Data kehadiran tidak valid"
            )

        kehadiran = db.scalar(
            select(Kehadiran).where(
                Kehadiran.krs_detail_id == detail_id
            )
        )

        if kehadiran:
            kehadiran.total_pertemuan = total_pertemuan
            kehadiran.jumlah_hadir = jumlah_hadir
        else:
            kehadiran = Kehadiran(
                krs_detail_id=detail_id,
                total_pertemuan=total_pertemuan,
                jumlah_hadir=jumlah_hadir
            )
            db.add(kehadiran)

        db.commit()
        db.refresh(kehadiran)

        return kehadiran

    @staticmethod
    def hitung_ipk(db: Session, nim: str):
        hasil = db.execute(
            select(
                KRSDetail.nilai,
                MataKuliah.sks,
                SkalaNilai.bobot
            )
            .join(KRS, KRS.id == KRSDetail.krs_id)
            .join(
                MataKuliah,
                MataKuliah.kode_mk == KRSDetail.kode_mk
            )
            .join(
                SkalaNilai,
                SkalaNilai.nilai == KRSDetail.nilai
            )
            .where(
                KRS.nim == nim,
                KRS.status == "approved",
                KRSDetail.nilai.isnot(None)
            )
        ).all()

        total_sks = sum(row.sks for row in hasil)

        if total_sks == 0:
            return 0.0

        total_bobot = sum(
            row.bobot * row.sks for row in hasil
        )

        return round(total_bobot / total_sks, 2)

    @staticmethod
    def hitung_ip(db: Session, nim: str, semester: str):
        hasil = db.execute(
            select(
                KRSDetail.nilai,
                MataKuliah.sks,
                SkalaNilai.bobot
            )
            .join(KRS, KRS.id == KRSDetail.krs_id)
            .join(
                MataKuliah,
                MataKuliah.kode_mk == KRSDetail.kode_mk
            )
            .join(
                SkalaNilai,
                SkalaNilai.nilai == KRSDetail.nilai
            )
            .where(
                KRS.nim == nim,
                KRS.semester == semester,
                KRS.status == "approved",
                KRSDetail.nilai.isnot(None)
            )
        ).all()

        total_sks = sum(row.sks for row in hasil)

        if total_sks == 0:
            return 0.0

        total_bobot = sum(
            row.bobot * row.sks for row in hasil
        )

        return round(total_bobot / total_sks, 2)
