import enum
from datetime import date, timedelta

class DateRangeEnum(enum.Enum):
    YESTERDAY     = ("Wczoraj", 1)
    WEEK          = ("Tydzień wstecz", 7)
    WEEKS_2       = ("2 tygodnie wstecz", 14)
    WEEKS_3       = ("3 tygodnie wstecz", 21)
    MONTH         = ("Miesiąc wstecz", 30)
    CURRENT_MONTH = ("Bieżący miesiąc", None)  # specjalny przypadek

    def __init__(self, label: str, days: int | None):
        self._label = label
        self._days = days

    @property
    def label(self) -> str:
        """Polska etykieta do UI"""
        return self._label

    @property
    def days(self) -> int | None:
        """Ile dni wstecz (None = specjalne obliczenie)"""
        return self._days

    def compute_range(self, today: date | None = None) -> tuple[date, date]:
        """Zwraca (od, do) jako zakres dat."""
        today = today or date.today()
        if self is DateRangeEnum.CURRENT_MONTH:
            start = today.replace(day=1)
            return start, today
        if self.days is not None:
            start = today - timedelta(days=self.days)
            return start, today
        return today, today  # fallback (nie powinno się zdarzyć)

class JudgementStatusEnum(enum.Enum):
    NO_JUSTIFICATION = 'no_justification'
    PROCESSED = 'processed'
