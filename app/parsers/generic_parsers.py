import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    SupplierRaw,
)


UKRAINIAN_MONTHS = {
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
}


class GenericInvoiceParser:
    def parse(self, text: str) -> InvoiceData:
        return InvoiceData(
            number=self._parse_number(text),
            date=self._parse_date(text),
            supplier=self._parse_supplier(text),
            items=self._parse_items(text),
            # unit=self._parse_units_of_measure(text),
            # quantity=self._parse_quantity(text),
            total=self._parse_total(text),
        )

    def _parse_number(self, text: str) -> str | None:
        patterns = [
            re.compile(
                r"(?:рахунок(?:-фактура)?(?:\s+на\s+оплату)?"
                r"|видаткова\s+накладна)"
                r"\s*№\s*"
                r"([A-Za-zА-Яа-яІіЇїЄєҐґ0-9/_-]+)"
                r"\s+від\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"invoice\s*(?:№|No\.?|number)\s*"
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
        numeric_pattern = re.compile(
            r"(?:рахунок(?:-фактура)?(?:\s+на\s+оплату)?"
            r"|видаткова\s+накладна)"
            r"\s*№\s*[A-Za-zА-Яа-яІіЇїЄєҐґ0-9/_-]+"
            r"\s+від\s+"
            r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
            re.IGNORECASE,
        )

        match = numeric_pattern.search(text)

        if match:
            raw_date = match.group(1)

            for date_format in ("%d.%m.%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(
                        raw_date,
                        date_format,
                    ).date()
                except ValueError:
                    continue

        text_date_pattern = re.compile(
            r"(?:рахунок(?:-фактура)?(?:\s+на\s+оплату)?"
            r"|видаткова\s+накладна)"
            r"\s*№\s*[A-Za-zА-Яа-яІіЇїЄєҐґ0-9/_-]+"
            r"\s+від\s+"
            r"(\d{1,2})\s+"
            r"(січня|лютого|березня|квітня|травня|червня|"
            r"липня|серпня|вересня|жовтня|листопада|грудня)"
            r"\s+(\d{4})",
            re.IGNORECASE,
        )

        match = text_date_pattern.search(text)

        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))

        return date(
            year=year,
            month=UKRAINIAN_MONTHS[month_name],
            day=day,
        )

    def _parse_supplier(self, text: str) -> SupplierRaw:
        return SupplierRaw(
            name=self._find_supplier_name(text),
            tax_code=self._find_tax_code(text),
            iban=self._find_iban(text),
        )

    def _parse_items(self, text: str) -> list[InvoiceItem]:
        patterns = [
            {
                "pattern": re.compile(
                    r"(?m)^\s*"
                    r"\d+\s+"  # номер рядка
                    r"\S+\s+"  # код / артикул
                    r"(.+?)\s+"  # назва
                    r"(\d+(?:[,.]\d+)?)\s+"  # quantity
                    r"([A-Za-zА-Яа-яІіЇїЄєҐґ.]+)\s+"  # unit
                    r"([\d\s\u00a0]+[,.]\d{2})\s+"  # price
                    r"([\d\s\u00a0]+[,.]\d{2})"  # total
                    r"\s*$"
                ),
                "name_group": 1,
                "quantity_group": 2,
                "unit_group": 3,
                "price_group": 4,
                "total_group": 5,
            },
            {
                "pattern": re.compile(
                    r"(?m)^\s*"
                    r"\d+\s+"
                    r"\S+\s+"
                    r"(.+?)\s+"
                    r"([A-Za-zА-Яа-яІіЇїЄєҐґ.]+)\s+"  # unit
                    r"(\d+(?:[,.]\d+)?)\s+"  # quantity
                    r"([\d\s\u00a0]+[,.]\d{2})\s+"
                    r"([\d\s\u00a0]+[,.]\d{2})"
                    r"\s*$"
                ),
                "name_group": 1,
                "unit_group": 2,
                "quantity_group": 3,
                "price_group": 4,
                "total_group": 5,
            },
        ]

        items: list[InvoiceItem] = []

        for config in patterns:
            pattern = config["pattern"]

            for match in pattern.finditer(text):
                item = InvoiceItem(
                    name=match.group(config["name_group"]).strip(),
                    unit=match.group(config["unit_group"]).strip(),
                    quantity=self._to_decimal(
                        match.group(config["quantity_group"])
                    ),
                    price=self._to_decimal(
                        match.group(config["price_group"])
                    ),
                    total=self._to_decimal(
                        match.group(config["total_group"])
                    ),
                )

                items.append(item)

            if items:
                break

        return items

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
                r"\b((?:ТОВ|ПП|ФОП|АТ|ПрАТ|ПАТ|товариство з обмеженою відповідальністю|приватне підприємство|фізична особа підприємець)"
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
                r"(?:код\s+єдрпоу|єдрпоу|дрфо)"
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
