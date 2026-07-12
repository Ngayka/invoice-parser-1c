import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    SupplierRaw,
)


class GenericInvoiceParser:
    def parse(self, text: str) -> InvoiceData:
        return InvoiceData(
            number=self._parse_number(text),
            date=self._parse_date(text),
            supplier=self._parse_supplier(text),
            items=self._parse_items(text),
            subtotal=self._parse_subtotal(text),
            vat=self._parse_vat(text),
            total=self._parse_total(text),
        )

    def _parse_number(self, text: str) -> str | None:
        patterns = [
            re.compile(
                r"(?:рахунок(?:-фактура)?|рахунок на оплату)"
                r"\s*(?:№|N)?\s*"
                r"([A-Za-zА-Яа-яІіЇїЄєҐґ0-9/_-]+)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:invoice)"
                r"\s*(?:№|No\.?|number)?\s*"
                r"([A-Za-z0-9/_-]+)",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)

            if match:
                return match.group(1).strip()

        return None

    def _parse_date(self, text: str) -> date | None:
        patterns = [
            (
                re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b"),
                "%d.%m.%Y",
            ),
            (
                re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"),
                "%d/%m/%Y",
            ),
            (
                re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
                "%Y-%m-%d",
            ),
        ]

        for pattern, date_format in patterns:
            match = pattern.search(text)

            if not match:
                continue

            try:
                return datetime.strptime(
                    match.group(1),
                    date_format,
                ).date()
            except ValueError:
                continue

        return None

    def _parse_supplier(self, text: str) -> SupplierRaw:
        return SupplierRaw(
            name=self._find_supplier_name(text),
            tax_code=self._find_tax_code(text),
            iban=self._find_iban(text),
        )

    def _parse_items(self, text: str) -> list[InvoiceItem]:
        """
        Таблична частина залежить не від постачальника,
        а від того, як PDF віддає текст.

        Поки повертаємо порожній список.
        Після аналізу реальних PDF сюди додається
        універсальна логіка пошуку рядків таблиці.
        """
        return []

    def _parse_subtotal(self, text: str) -> Decimal | None:
        patterns = [
            re.compile(
                r"(?:сума без пдв|всього без пдв|разом без пдв)"
                r"\s*[:\-]?\s*"
                r"([\d\s\u00a0]+[,.]\d{2})",
                re.IGNORECASE,
            ),
        ]

        return self._find_decimal(text, patterns)

    def _parse_vat(self, text: str) -> Decimal | None:
        patterns = [
            re.compile(
                r"(?:пдв(?:\s*\d{1,2}\s*%)?)"
                r"\s*[:\-]?\s*"
                r"([\d\s\u00a0]+[,.]\d{2})",
                re.IGNORECASE,
            ),
        ]

        return self._find_decimal(text, patterns)

    def _parse_total(self, text: str) -> Decimal | None:
        patterns = [
            re.compile(
                r"(?:всього до сплати|разом до сплати|"
                r"всього|разом|total)"
                r"\s*[:\-]?\s*"
                r"([\d\s\u00a0]+[,.]\d{2})",
                re.IGNORECASE,
            ),
        ]

        return self._find_decimal(text, patterns)

    @staticmethod
    def _find_supplier_name(text: str) -> str | None:
        patterns = [
            re.compile(
                r"(?:постачальник|виконавець|продавець)"
                r"\s*[:\-]\s*(.+)",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b((?:ТОВ|ПП|ФОП|АТ|ПрАТ|ПАТ)"
                r"\s*[«\"']?[^,\n]{2,100}[»\"']?)",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)

            if match:
                return match.group(1).strip()

        return None

    @staticmethod
    def _find_tax_code(text: str) -> str | None:
        patterns = [
            re.compile(
                r"(?:код\s+єдрпоу|єдрпоу)"
                r"\s*[:№]?\s*(\d{8})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:іпн|рнокпп)"
                r"\s*[:№]?\s*(\d{10,12})",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.search(text)

            if match:
                return match.group(1)

        return None

    @staticmethod
    def _find_iban(text: str) -> str | None:
        match = re.search(
            r"\bUA(?:\s*\d){27}\b",
            text,
            re.IGNORECASE,
        )

        if not match:
            return None

        return re.sub(
            r"\s+",
            "",
            match.group(0),
        ).upper()

    def _find_decimal(
        self,
        text: str,
        patterns: list[re.Pattern[str]],
    ) -> Decimal | None:
        for pattern in patterns:
            matches = list(pattern.finditer(text))

            if not matches:
                continue

            # Для підсумків часто безпечніше брати останній збіг.
            value = matches[-1].group(1)

            parsed_value = self._to_decimal(value)

            if parsed_value is not None:
                return parsed_value

        return None

    @staticmethod
    def _to_decimal(value: str) -> Decimal | None:
        normalized = (
            value
            .replace("\u00a0", "")
            .replace(" ", "")
            .strip()
        )

        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = (
                    normalized
                    .replace(".", "")
                    .replace(",", ".")
                )
            else:
                normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(",", ".")

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None