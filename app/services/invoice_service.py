import re
from pathlib import Path

from app.parsers.generic_parsers import GenericInvoiceParser
from app.pdf.reader import PdfReader
from app.schemas.invoice import InvoiceData


class InvoiceService:
    def __init__(self):
        self.pdf_reader = PdfReader()
        self.parser = GenericInvoiceParser()

    def parse_pdf(
        self,
        content: bytes,
    ) -> InvoiceData:

        text = self.pdf_reader.extract_text(content)

        return self.parser.parse(text)

    def save_json(self, invoice: InvoiceData) -> Path:
        directory = Path("exports")
        directory.mkdir(exist_ok=True)

        safe_number = re.sub(r'[\\/:*?"<>|]', "_", invoice.number)
        filename = f"{safe_number}_{invoice.date}.json"

        path = directory / filename

        path.write_text(
            invoice.model_dump_json(indent=4),
            encoding="utf-8",
        )

        return path
