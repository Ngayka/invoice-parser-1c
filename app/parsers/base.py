from abc import ABC, abstractmethod

from app.schemas.invoice import InvoiceData


class BaseInvoiceParser(ABC):
    @abstractmethod
    def matches(self, text: str) -> bool:
        """
        Визначає, чи підходить цей парсер
        для конкретного PDF.
        """

    @abstractmethod
    def parse(self, text: str) -> InvoiceData:
        """
        Витягує дані з тексту рахунку.
        """