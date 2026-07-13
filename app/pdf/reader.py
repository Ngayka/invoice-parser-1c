import pymupdf

from app.pdf.exceptions import PdfParsingError


class PdfReader:
    def extract_text(self, content: bytes) -> str:
        try:
            document = pymupdf.open(
                stream=content,
                filetype="pdf",
            )
        except Exception as error:
            raise PdfParsingError(
                "Не вдалося відкрити PDF-файл"
            ) from error

        pages: list[str] = []

        try:
            for page in document:
                page_text = page.get_text("text").strip()

                if page_text:
                    pages.append(page_text)
        finally:
            document.close()

        full_text = "\n".join(pages).strip()

        if not self._has_meaningful_text(full_text):
            raise PdfParsingError(
                "У PDF відсутній текстовий шар. "
                "Документ потрібно обробити вручну."
            )

        return full_text

    @staticmethod
    def _has_meaningful_text(
        text: str,
        minimum_chars: int = 50,
    ) -> bool:
        meaningful_chars = [
            character
            for character in text
            if character.isalnum()
        ]

        return len(meaningful_chars) >= minimum_chars
