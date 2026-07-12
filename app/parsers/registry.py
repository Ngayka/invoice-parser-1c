from app.parsers.base import BaseInvoiceParser
from app.parsers.suppliers.supplier_a import (
    SupplierAInvoiceParser,
)
from app.pdf.exceptions import UnsupportedInvoiceError


class InvoiceParserRegistry:
    def __init__(self) -> None:
        self.parsers: list[BaseInvoiceParser] = [
            SupplierAInvoiceParser(),
        ]

    def get_parser(self, text: str) -> BaseInvoiceParser:
        matched_parsers = [
            parser
            for parser in self.parsers
            if parser.matches(text)
        ]

        if not matched_parsers:
            raise UnsupportedInvoiceError(
                "Шаблон рахунку не розпізнаний"
            )

        if len(matched_parsers) > 1:
            raise UnsupportedInvoiceError(
                "Для рахунку знайдено кілька можливих парсерів"
            )

        return matched_parsers[0]