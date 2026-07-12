class PdfParsingError(Exception):
    """PDF неможливо прочитати або в ньому немає тексту."""


class UnsupportedInvoiceError(Exception):
    """Для цього рахунку не знайдений відповідний парсер."""


class InvoiceValidationError(Exception):
    """Результат парсингу не пройшов перевірку."""