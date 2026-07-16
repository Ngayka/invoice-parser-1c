import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.vat_service import VatMode, detect_vat_mode

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    SupplierRaw,
)
from app.services.vat_service import VatMode

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
        vat_mode = detect_vat_mode(text)

        total_net, vat_total, total_gross = self._parse_invoice_totals(
            text,
            vat_mode,
        )
        return InvoiceData(
            number=self._parse_number(text),
            date=self._parse_date(text),
            supplier=self._parse_supplier(text),
            items=self._parse_items(text),
            vat_mode=vat_mode,
            total_net=total_net,
            vat_total=vat_total,
            total_gross=total_gross,
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
        items: list[InvoiceItem] = []

        # Вирізаємо лише частину документа з товарами.
        table_match = re.search(
            r"Сума без ПДВ\s*\n(?P<table>.*?)\nВсього:",
            text,
            flags=re.DOTALL,
        )

        if table_match:
            table_text = table_match.group("table")

            vertical_pattern = re.compile(
                r"(?ms)"
                r"^\s*\d+\s*\n"  # номер рядка
                r"(?P<name>.+?)\n"  # назва, може займати кілька рядків
                r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
                r"(?P<unit>[A-Za-zА-Яа-яІіЇїЄєҐґ.]+)\s*\n"
                r"(?P<price>[\d\s\u00a0]+[,.]\d{2})\s*\n"
                r"(?P<total>[\d\s\u00a0]+[,.]\d{2})"
                r"(?=\s*(?:\n\d+\s*\n|\Z))"
            )

            for match in vertical_pattern.finditer(table_text):
                # Назва може містити кілька рядків — об'єднуємо їх.
                name = " ".join(
                    line.strip()
                    for line in match.group("name").splitlines()
                    if line.strip()
                )

                items.append(
                    InvoiceItem(
                        name=name,
                        unit=match.group("unit").strip(),
                        quantity=self._to_decimal(
                            match.group("quantity")
                        ),
                        source_price=self._to_decimal(
                            match.group("price")
                        ),
                        source_total=self._to_decimal(
                            match.group("total")
                        ),
                    )
                )

        if items:
            return items

        patterns = [
            {
                "pattern": re.compile(
                    r"(?m)^\s*"
                    r"\d+\s+"  # номер рядка
                    r"(?P<name>.+?)\s+"  # назва товару
                    r"\d{4}(?:\s+\d{2}){2,3}\s*[A-Za-zА-Яа-яІіЇїЄєҐґ]?\s+"  # УКТЗЕД
                    r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
                    r"(?P<unit>[A-Za-zА-Яа-яІіЇїЄєҐґ.]+)\s+"
                    r"(?P<price>[\d\s\u00a0]+[,.]\d{2})\s+"
                    r"(?P<total>[\d\s\u00a0]+[,.]\d{2})"
                    r"\s*$"
                ),
                "named_groups": True,
            },
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
            matched_items: list[InvoiceItem] = []

            for match in config["pattern"].finditer(text):
                if config.get("named_groups"):
                    item = InvoiceItem(
                        name=match.group("name").strip(),
                        unit=match.group("unit").strip(),
                        quantity=self._to_decimal(
                            match.group("quantity")
                        ),
                        source_price=self._to_decimal(
                            match.group("price")
                        ),
                        source_total=self._to_decimal(
                            match.group("total")
                        ),
                    )
                else:
                    item = InvoiceItem(
                        name=match.group(
                            config["name_group"]
                        ).strip(),
                        unit=match.group(
                            config["unit_group"]
                        ).strip(),
                        quantity=self._to_decimal(
                            match.group(
                                config["quantity_group"]
                            )
                        ),
                        source_price=self._to_decimal(
                            match.group(
                                config["price_group"]
                            )
                        ),
                        source_total=self._to_decimal(
                            match.group(
                                config["total_group"]
                            )
                        ),
                    )

                matched_items.append(item)

            # Щойно один із форматів спрацював,
            # повертаємо результат і не перевіряємо інші патерни.
            if matched_items:
                return matched_items

        return []

    def _parse_invoice_totals(
            self,
            text: str,
            vat_mode: VatMode,
    ) -> tuple[Decimal | None, Decimal | None, Decimal]:
        normalized = text.replace("\u00a0", " ")

        gross_patterns = (
            r"(?:Всього|Усього|Разом)\s+"
            r"(?:із|з)\s+ПДВ\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",

            r"(?:Итого|Всего)\s+с\s+НДС\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",
        )

        vat_patterns = (
            r"Сума\s+ПДВ\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",

            r"У\s*т\.?\s*ч\.?\s*ПДВ"
            r"(?:\s*\(\d+%\))?\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",

            r"В\s*т\.?\s*ч\.?\s*НДС"
            r"(?:\s*\(\d+%\))?\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",
        )

        base_patterns = (
            r"(?:Всього|Усього|Разом)\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",

            r"(?:Итого|Всего)\s*:?\s*"
            r"([\d\s\u00a0]+[,.]\d{2})",
        )

        gross = self._find_decimal(normalized, gross_patterns)
        vat = self._find_decimal(normalized, vat_patterns)
        base = self._find_decimal(normalized, base_patterns)

        if vat_mode == VatMode.EXCLUSIVE:
            net = base

            if gross is None and net is not None and vat is not None:
                gross = net + vat

        elif vat_mode == VatMode.INCLUSIVE:
            gross = gross or base
            net = gross - vat if gross is not None and vat is not None else None

        elif vat_mode == VatMode.NONE:
            gross = base
            net = base
            vat = Decimal("0.00")

        else:
            gross = gross or base
            net = None

        if gross is None:
            raise ValueError("Не вдалося визначити підсумкову суму рахунку")

        return net, vat, gross

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
            patterns: tuple[str, ...],
    ) -> Decimal | None:
        for pattern in patterns:
            matches = list(
                re.finditer(
                    pattern,
                    text,
                    flags=re.IGNORECASE,
                )
            )

            if not matches:
                continue

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
