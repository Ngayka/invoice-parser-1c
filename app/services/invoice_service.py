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