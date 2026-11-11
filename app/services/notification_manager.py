
import logging
from abc import ABC, abstractmethod


# =========================
# KONFIGURASI LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# =========================
# OBSERVER INTERFACE
# =========================

class ScheduleObserver(ABC):

    @abstractmethod
    def update(self, event, data):
        pass


# =========================
# STUDENT OBSERVER
# =========================

class StudentObserver(ScheduleObserver):

    def update(self, event, data):
        logger.info(
            "[EMAIL MAHASISWA] "
            "Perubahan jadwal: %s | Data: %s",
            event,
            data
        )


# =========================
# LECTURER OBSERVER
# =========================

class LecturerObserver(ScheduleObserver):

    def update(self, event, data):
        logger.info(
            "[SMS DOSEN] "
            "Perubahan jadwal: %s | Data: %s",
            event,
            data
        )


# =========================
# ACADEMIC ADMIN OBSERVER
# =========================

class AcademicAdminObserver(ScheduleObserver):

    def update(self, event, data):
        logger.info(
            "[PUSH NOTIFICATION ADMIN] "
            "Perubahan jadwal: %s | Data: %s",
            event,
            data
        )


# =========================
# SCHEDULE SUBJECT
# =========================

class ScheduleSubject:

    def __init__(self):
        self._observers = []

    def attach(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer):
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self, event, data):
        for observer in self._observers:
            observer.update(event, data)


# =========================
# NOTIFICATION MANAGER
# =========================

class NotificationManager:

    def __init__(self):
        self.subject = ScheduleSubject()

        self.subject.attach(StudentObserver())
        self.subject.attach(LecturerObserver())
        self.subject.attach(AcademicAdminObserver())

    def notify_schedule_changed(self, event, data):
        self.subject.notify(event, data)
