import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.schemas.invoice import (
    InvoiceData,
    InvoiceItem,
    SupplierRaw,
)
from app.services.vat_service import VatMode, detect_vat_mode


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

# Суми рахунку та суми товарних рядків завжди мають 2 знаки.
AMOUNT_PATTERN = r"\d[\d \t\u00a0]*(?:[,.]\d{2})"

# Ціна товару іноді містить 3–4 знаки після коми.
PRICE_PATTERN = r"\d[\d \t\u00a0]*(?:[,.]\d{2,4})"

QUANTITY_PATTERN = r"\d+(?:[,.]\d+)?"

UNIT_PATTERN = (
    r"(?:"
    r"пог\.?\s*м\.?|"
    r"компл\.?|"
    r"упак\.?|"
    r"шт\.?|"
    r"уп\.?|"
    r"кг\.?|"
    r"г\.?|"
    r"л\.?|"
    r"м2|м²|"
    r"м3|м³|"
    r"од\.?|"
    r"м\.?"
    r")"
)


class GenericInvoiceParser:
    def parse(self, text: str) -> InvoiceData:
        text = self._normalize_pdf_text(text)
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

    def _parse_items(self, text: str) -> list[InvoiceItem]:
        normalized_text = self._normalize_pdf_text(text)
        table_text = self._extract_items_table(normalized_text)

        parsers = (
            self._parse_common_row_items,
            self._parse_cms_items,
            self._parse_etna_items,
            self._parse_common_columnar_items,
        )

        for parser in parsers:
            items = parser(table_text)
            if self._items_are_valid(items, normalized_text):
                return items

        raise ValueError(
            "Не вдалося надійно розпізнати товарні позиції: "
            "жоден структурний парсер не дав повного результату."
        )

    def _parse_common_row_items(self, table_text: str) -> list[InvoiceItem]:
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?P<number>\d{{1,3}})
            [ \t]+
            (?P<body>.+?)
            [ \t]+
            (?P<quantity>{QUANTITY_PATTERN})
            [ \t]+
            (?P<unit>{UNIT_PATTERN})
            [ \t]+
            (?P<price>{PRICE_PATTERN})
            [ \t]+
            (?P<total>{AMOUNT_PATTERN})
            [ \t]*$
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        items: list[InvoiceItem] = []
        for raw_line in table_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if match is None:
                continue
            item = self._create_invoice_item(match)
            if item is not None:
                items.append(item)
        return items

    def _parse_cms_items(self, table_text: str) -> list[InvoiceItem]:
        pattern = re.compile(
            rf"""
            ^[ \t]*
            (?P<number>\d{{1,3}})
            [ \t]+
            (?P<body>.+?)
            [ \t]+
            (?P<unit>{UNIT_PATTERN})
            [ \t]+
            (?P<quantity>{QUANTITY_PATTERN})
            [ \t]+
            (?P<price>{PRICE_PATTERN})
            [ \t]+
            (?P<total>{AMOUNT_PATTERN})
            [ \t]*$
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        items: list[InvoiceItem] = []
        for raw_line in table_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if match is None:
                continue
            item = self._create_invoice_item(match)
            if item is not None:
                items.append(item)

        if items:
            return items

        lines = [line.strip() for line in table_text.splitlines() if line.strip()]
        item_start_pattern = re.compile(r"^\d{1,3}$")
        starts = [
            index
            for index, line in enumerate(lines)
            if item_start_pattern.fullmatch(line)
        ] or [0]
        boundaries = starts + [len(lines)]
        quantity_unit_pattern = re.compile(
            rf"^{QUANTITY_PATTERN}[ \t]+{UNIT_PATTERN}$",
            flags=re.IGNORECASE,
        )

        for start, end in zip(boundaries, boundaries[1:]):
            # Preserve the quantity + unit row boundary before joining columns.
            if end - start >= 3 and quantity_unit_pattern.fullmatch(lines[end - 3]):
                continue
            joined = " ".join(lines[start:end])
            match = pattern.match(joined)
            if match is None:
                continue
            item = self._create_invoice_item(match)
            if item is not None:
                items.append(item)
        return items

    def _parse_etna_items(self, table_text: str) -> list[InvoiceItem]:
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]

        item_start_pattern = re.compile(r"^\d{1,3}$")
        quantity_unit_pattern = re.compile(
            rf"^(?P<quantity>{QUANTITY_PATTERN})[ \t]+(?P<unit>{UNIT_PATTERN})$",
            flags=re.IGNORECASE,
        )
        price_pattern = re.compile(rf"^(?P<price>{PRICE_PATTERN})$")
        total_pattern = re.compile(rf"^(?P<total>{AMOUNT_PATTERN})$")

        items: list[InvoiceItem] = []
        index = 0

        while index < len(lines):
            if not item_start_pattern.fullmatch(lines[index]):
                index += 1
                continue

            start = index
            cursor = index + 1
            quantity_match = None

            while cursor < len(lines):
                if cursor > start + 1 and item_start_pattern.fullmatch(lines[cursor]):
                    break
                quantity_match = quantity_unit_pattern.fullmatch(lines[cursor])
                if quantity_match is not None:
                    break
                cursor += 1

            if quantity_match is None or cursor + 2 >= len(lines):
                index += 1
                continue

            price_match = price_pattern.fullmatch(lines[cursor + 1])
            total_match = total_pattern.fullmatch(lines[cursor + 2])
            if price_match is None or total_match is None:
                index += 1
                continue

            body = " ".join(lines[start + 1:cursor])
            item = self._build_item_from_parts(
                body=body,
                quantity=quantity_match.group("quantity"),
                unit=quantity_match.group("unit"),
                price=price_match.group("price"),
                total=total_match.group("total"),
            )
            if item is not None:
                items.append(item)

            index = cursor + 3

        return items

    def _parse_common_columnar_items(self, table_text: str) -> list[InvoiceItem]:
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]

        description_pattern = re.compile(
            r"^(?P<number>\d{1,3})[ \t]+(?P<body>.+)$",
            flags=re.IGNORECASE,
        )
        quantity_pattern = re.compile(rf"^(?P<quantity>{QUANTITY_PATTERN})$")
        unit_pattern = re.compile(rf"^(?P<unit>{UNIT_PATTERN})$", flags=re.IGNORECASE)
        quantity_unit_pattern = re.compile(
            rf"^(?P<quantity>{QUANTITY_PATTERN})[ \t]+(?P<unit>{UNIT_PATTERN})$",
            flags=re.IGNORECASE,
        )
        price_pattern = re.compile(rf"^(?P<price>{PRICE_PATTERN})$")
        total_pattern = re.compile(rf"^(?P<total>{AMOUNT_PATTERN})$")

        items: list[InvoiceItem] = []
        index = 0

        while index < len(lines):
            description_match = description_pattern.fullmatch(lines[index])
            if description_match is None:
                index += 1
                continue

            body = description_match.group("body")

            if index + 3 < len(lines):
                quantity_unit_match = quantity_unit_pattern.fullmatch(lines[index + 1])
                price_match = price_pattern.fullmatch(lines[index + 2])
                total_match = total_pattern.fullmatch(lines[index + 3])
                if quantity_unit_match and price_match and total_match:
                    item = self._build_item_from_parts(
                        body=body,
                        quantity=quantity_unit_match.group("quantity"),
                        unit=quantity_unit_match.group("unit"),
                        price=price_match.group("price"),
                        total=total_match.group("total"),
                    )
                    if item is not None:
                        items.append(item)
                    index += 4
                    continue

            if index + 4 < len(lines):
                quantity_match = quantity_pattern.fullmatch(lines[index + 1])
                unit_match = unit_pattern.fullmatch(lines[index + 2])
                price_match = price_pattern.fullmatch(lines[index + 3])
                total_match = total_pattern.fullmatch(lines[index + 4])
                if quantity_match and unit_match and price_match and total_match:
                    item = self._build_item_from_parts(
                        body=body,
                        quantity=quantity_match.group("quantity"),
                        unit=unit_match.group("unit"),
                        price=price_match.group("price"),
                        total=total_match.group("total"),
                    )
                    if item is not None:
                        items.append(item)
                    index += 5
                    continue

            index += 1

        return items

    def _build_item_from_parts(
            self,
            *,
            body: str,
            quantity: str,
            unit: str,
            price: str,
            total: str,
    ) -> InvoiceItem | None:
        name = self._clean_item_body(body)
        quantity_value = self._to_decimal(quantity)
        price_value = self._to_decimal(price)
        total_value = self._to_decimal(total)

        if not name or quantity_value is None or price_value is None or total_value is None:
            return None

        return InvoiceItem(
            name=name,
            unit=self._normalize_unit(unit),
            quantity=quantity_value,
            source_price=price_value,
            source_total=total_value,
        )

    def _items_are_valid(self, items: list[InvoiceItem], invoice_text: str) -> bool:
        if not items:
            return False

        expected_count = self._parse_expected_items_count(invoice_text)
        if expected_count is not None and len(items) != expected_count:
            return False

        expected_total = self._parse_expected_items_total(invoice_text)
        if expected_total is None:
            return all(
                item.quantity > 0
                and item.source_price >= 0
                and item.source_total >= 0
                for item in items
            )

        actual_total = sum(
            (item.source_total for item in items),
            start=Decimal("0.00"),
        )
        return abs(actual_total - expected_total) <= Decimal("0.01")

    def _parse_expected_items_count(self, text: str) -> int | None:
        match = re.search(
            r"Всього[ \t]+найменувань[ \t]+(?P<count>\d+)",
            text,
            flags=re.IGNORECASE,
        )
        return int(match.group("count")) if match else None

    def _parse_expected_items_total(self, text: str) -> Decimal | None:
        normalized = self._normalize_pdf_text(text)
        amount = AMOUNT_PATTERN

        explicit_net_patterns = (
            rf"(?mi)^\s*(?:Всього|Усього|Разом)\s+без\s+ПДВ\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Итого|Всего)\s+без\s+НДС\s*:?\s*({amount})\s*$",
        )

        for pattern in explicit_net_patterns:
            matches = list(re.finditer(pattern, normalized))
            if matches:
                return self._to_decimal(matches[-1].group(1))

        vat_marker = re.search(r"(?mi)^\s*(?:Сума\s+ПДВ|ПДВ)\s*: ?", normalized)
        if vat_marker is not None:
            before_vat = normalized[:vat_marker.start()]
            matches = list(
                re.finditer(
                    rf"(?mi)^\s*(?:Всього|Усього|Разом)\s*:?\s*({amount})\s*$",
                    before_vat,
                )
            )
            if matches:
                return self._to_decimal(matches[-1].group(1))

        common_patterns = (
            rf"(?mi)^\s*(?:Всього|Усього|Разом)\s+(?:із|з)\s+ПДВ\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Всього|Усього|Разом)\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Итого|Всего)\s*:?\s*({amount})\s*$",
        )

        for pattern in common_patterns:
            matches = list(re.finditer(pattern, normalized))
            if matches:
                return self._to_decimal(matches[-1].group(1))

        return None

    def _create_invoice_item(
        self,
        match: re.Match[str],
    ) -> InvoiceItem | None:
        name = self._clean_item_body(match.group("body"))
        quantity = self._to_decimal(match.group("quantity"))
        price = self._to_decimal(match.group("price"))
        total = self._to_decimal(match.group("total"))

        if not name:
            return None

        if quantity is None or price is None or total is None:
            return None

        return InvoiceItem(
            name=name,
            unit=self._normalize_unit(match.group("unit")),
            quantity=quantity,
            source_price=price,
            source_total=total,
        )

    @staticmethod
    def _clean_item_body(body: str) -> str:
        value = " ".join(
            part.strip()
            for part in body.splitlines()
            if part.strip()
        )

        # Видаляємо напис УКТЗЕД разом із кодом.
        value = re.sub(
            r"""
            \bУКТ[ \t]*ЗЕД[ \t]*:?
            [ \t]*
            \d{4}
            (?:[ \t]+\d{2}){0,4}
            (?:[ \t]*(?:Укр|Імп|[хx]))?
            """,
            " ",
            value,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        # Видаляємо код УКТЗЕД без напису:
        # 3925 90 80 00 х
        value = re.sub(
            r"""
            \b
            \d{4}
            (?:[ \t]+\d{2}){1,4}
            (?:[ \t]*[хx])?
            \b
            """,
            " ",
            value,
            flags=re.VERBOSE,
        )

        value = re.sub(r"\s{2,}", " ", value).strip()

        # Видаляємо артикул на початку, лише якщо він явно схожий на код.
        parts = value.split(maxsplit=1)

        if len(parts) == 2:
            possible_article, possible_name = parts

            article_looks_like_code = (
                any(char.isdigit() for char in possible_article)
                and (
                    "-" in possible_article
                    or "_" in possible_article
                    or "/" in possible_article
                    or possible_article.upper().startswith("CMS")
                )
            )

            if article_looks_like_code:
                value = possible_name.strip()

        return value

    @staticmethod
    def _normalize_unit(unit: str) -> str:
        normalized = re.sub(r"\s+", "", unit.lower())

        aliases = {
            "шт.": "шт",
            "пог.м.": "пог.м",
            "погм": "пог.м",
            "м.": "м",
            "од.": "од",
            "компл.": "компл",
            "уп.": "уп",
            "упак.": "упак",
            "кг.": "кг",
            "г.": "г",
            "л.": "л",
        }

        return aliases.get(normalized, normalized)

    @staticmethod
    def _normalize_pdf_text(text: str) -> str:
        text = (
            text
            .replace("\u00a0", " ")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("’", "'")
            .replace("ʼ", "'")
        )

        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def _find_supplier_name(text: str) -> str | None:
        patterns = (
            re.compile(
                r"(?mi)^\s*Постачальник\s*:\s*(.+?)\s*$"
            ),
            re.compile(
                r"(?mi)^\s*Поставщик\s*:\s*(.+?)\s*$"
            ),
            re.compile(
                r"(?mi)^\s*Supplier\s*:\s*(.+?)\s*$"
            ),
        )

        for pattern in patterns:
            match = pattern.search(text)

            if match:
                return re.sub(
                    r"\s{2,}",
                    " ",
                    match.group(1),
                ).strip()

        return None

    def _extract_items_table(self, text: str) -> str:
        normalized = self._normalize_pdf_text(text)

        header_patterns = (
            # СТБ.
            r"Сума\s+без\s+ПДВ\s*\n",

            # Таблиці з ціною з ПДВ.
            r"Сума\s+з\s+ПДВ\s*\n",

            # Марчук та прості рахунки.
            r"\bСума\s*\n",

            # Додаткові варіанти заголовків таблиць.
            r"Сума\s+без\s+ПДВ\s*(?=\d+[ \t]+)",
            r"\bСума\s*(?=\d+[ \t]+)",
        )

        totals_start_pattern = (
            r"(?m)^\s*"
            r"(?:"
            r"Всього\s+без\s+ПДВ|"
            r"Всього\s+(?:із|з)\s+ПДВ|"
            r"Усього\s+(?:із|з)\s+ПДВ|"
            r"Разом\s+(?:із|з)\s+ПДВ|"
            r"Всього|"
            r"Усього|"
            r"Разом|"
            r"Итого|"
            r"Всего"
            r")\s*:"
        )

        for header_pattern in header_patterns:
            header_match = re.search(
                header_pattern,
                normalized,
                flags=re.IGNORECASE,
            )

            if not header_match:
                continue

            table_start = header_match.end()

            totals_match = re.search(
                totals_start_pattern,
                normalized[table_start:],
                flags=re.IGNORECASE,
            )

            if totals_match:
                table_end = table_start + totals_match.start()
                return normalized[table_start:table_end].strip()

            return normalized[table_start:].strip()

        # Якщо заголовок таблиці не знайдено, беремо ділянку
        # від першої товарної позиції до підсумків.
        first_item = re.search(
            r"(?m)^[ \t]*1[ \t]+",
            normalized,
        )

        if first_item:
            table_start = first_item.start()

            totals_match = re.search(
                totals_start_pattern,
                normalized[table_start:],
                flags=re.IGNORECASE,
            )

            if totals_match:
                table_end = table_start + totals_match.start()
                return normalized[table_start:table_end].strip()

        return normalized

    def _parse_number(self, text: str) -> str | None:
        normalized = self._normalize_pdf_text(text)

        patterns = (
            re.compile(
                r"""
                (?:рахунок(?:-фактура)?
                    (?:[ \t\r\n]+на[ \t\r\n]+оплату)?
                |
                    видаткова[ \t\r\n]+накладна
                )
                [ \t\r\n]{0,20}
                (?:№|N(?:o)?\.?)
                [ \t\r\n]*
                (?P<number>
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9]
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9._/\-]*
                )
                """,
                flags=re.IGNORECASE | re.VERBOSE,
            ),
            re.compile(
                r"""
                (?:рахунок(?:-фактура)?
                    (?:[ \t\r\n]+на[ \t\r\n]+оплату)?
                |
                    видаткова[ \t\r\n]+накладна
                )
                [\s\S]{0,200}?
                (?:№|N(?:o)?\.?)
                [ \t\r\n]*
                (?P<number>
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9]
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9._/\-]*
                )
                """,
                flags=re.IGNORECASE | re.VERBOSE,
            ),
            re.compile(
                r"""
                invoice
                [\s\S]{0,50}?
                (?:№|No\.?|number)
                [ \t\r\n]*
                (?P<number>[A-Za-z0-9][A-Za-z0-9._/\-]*)
                """,
                flags=re.IGNORECASE | re.VERBOSE,
            ),
            re.compile(
                r"""
                (?:^|\n)
                [ \t]*
                (?:№|N(?:o)?\.?)
                [ \t]*
                (?P<number>
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9]
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9._/\-]*
                )
                """,
                flags=re.IGNORECASE | re.MULTILINE | re.VERBOSE,
            ),
        )

        for pattern in patterns:
            match = pattern.search(normalized)

            if not match:
                continue

            number = match.group("number").strip(" \t.,:;")

            if number:
                return number

        return None

    def _parse_date(self, text: str) -> date | None:
        normalized = self._normalize_pdf_text(text)

        numeric_patterns = (
            re.compile(
                r"""
                \bвід
                [ \t\r\n]*
                (?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{4})
                """,
                flags=re.IGNORECASE | re.VERBOSE,
            ),
            re.compile(
                r"""
                \bдата
                [ \t]*:?
                [ \t\r\n]*
                (?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{4})
                """,
                flags=re.IGNORECASE | re.VERBOSE,
            ),
            re.compile(
                r"""
                (?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{4})
                """,
                flags=re.VERBOSE,
            ),
            re.compile(
                r"""
                (?P<date>\d{4}-\d{1,2}-\d{1,2})
                """,
                flags=re.VERBOSE,
            ),
        )

        for pattern in numeric_patterns:
            match = pattern.search(normalized)

            if not match:
                continue

            raw_date = match.group("date")

            for date_format in (
                "%d.%m.%Y",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
            ):
                try:
                    return datetime.strptime(
                        raw_date,
                        date_format,
                    ).date()
                except ValueError:
                    continue

        text_date_pattern = re.compile(
            r"""
            (?P<day>\d{1,2})
            [ \t]+
            (?P<month>
                січня|лютого|березня|квітня|травня|червня|
                липня|серпня|вересня|жовтня|листопада|грудня
            )
            [ \t]+
            (?P<year>\d{4})
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        match = text_date_pattern.search(normalized)

        if not match:
            return None

        return date(
            year=int(match.group("year")),
            month=UKRAINIAN_MONTHS[match.group("month").lower()],
            day=int(match.group("day")),
        )

    def _parse_supplier(self, text: str) -> SupplierRaw:
        return SupplierRaw(
            name=self._find_supplier_name(text),
            tax_code=self._find_tax_code(text),
            iban=self._find_iban(text),
        )

    def _parse_invoice_totals(
        self,
        text: str,
        vat_mode: VatMode,
    ) -> tuple[Decimal | None, Decimal | None, Decimal]:
        normalized = self._normalize_pdf_text(text)
        amount = AMOUNT_PATTERN

        net_patterns = (
            rf"(?mi)^\s*(?:Всього|Усього|Разом)"
            rf"\s+без\s+ПДВ\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Итого|Всего)"
            rf"\s+без\s+НДС\s*:?\s*({amount})\s*$",
        )

        vat_patterns = (
            rf"(?mi)^\s*Сума\s+ПДВ\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*ПДВ"
            rf"(?:\s+\d+(?:[,.]\d+)?\s*%)?"
            rf"\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*У\s*"
            rf"(?:т\.?\s*ч\.?|тому\s+числі)"
            rf"\s*ПДВ"
            rf"(?:\s*\(\s*\d+(?:[,.]\d+)?\s*%\s*\))?"
            rf"\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*Сумма\s+НДС\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*В\s*"
            rf"(?:т\.?\s*ч\.?|том\s+числе)"
            rf"\s*НДС"
            rf"(?:\s*\(\s*\d+(?:[,.]\d+)?\s*%\s*\))?"
            rf"\s*:?\s*({amount})\s*$",
        )

        gross_patterns = (
            rf"(?mi)^\s*(?:Всього|Усього|Разом)"
            rf"\s+(?:із|з)\s+ПДВ"
            rf"\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Итого|Всего)"
            rf"\s+с\s+НДС"
            rf"\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:До\s+сплати|К\s+оплате)"
            rf"\s*:?\s*({amount})\s*$",
        )

        common_total_patterns = (
            rf"(?mi)^\s*(?:Всього|Усього|Разом)"
            rf"\s*:?\s*({amount})\s*$",
            rf"(?mi)^\s*(?:Итого|Всего)"
            rf"\s*:?\s*({amount})\s*$",
        )

        net = self._find_decimal(normalized, net_patterns)
        vat = self._find_decimal(normalized, vat_patterns)
        gross = self._find_decimal(normalized, gross_patterns)
        common_total = self._find_decimal(
            normalized,
            common_total_patterns,
        )

        if vat_mode == VatMode.EXCLUSIVE:
            if net is None:
                net = common_total

            if gross is None and net is not None and vat is not None:
                gross = net + vat

            if net is None and gross is not None and vat is not None:
                net = gross - vat

            if vat is None and net is not None and gross is not None:
                vat = gross - net

        elif vat_mode == VatMode.INCLUSIVE:
            gross = gross or common_total

            if gross is not None and vat is not None:
                net = gross - vat
            else:
                net = None

        elif vat_mode == VatMode.NONE:
            gross = gross or common_total or net
            net = gross
            vat = Decimal("0.00")

        else:
            gross = gross or common_total

            if gross is not None and vat is not None:
                net = gross - vat
            else:
                net = None

        if gross is None:
            raise ValueError(
                "Не вдалося визначити підсумкову суму рахунку. "
                f"vat_mode={vat_mode.value}, "
                f"net={net}, vat={vat}, gross={gross}, "
                f"common_total={common_total}"
            )

        return (
            net.quantize(Decimal("0.01"))
            if net is not None
            else None,
            vat.quantize(Decimal("0.01"))
            if vat is not None
            else None,
            gross.quantize(Decimal("0.01")),
        )

    @staticmethod
    def _find_tax_code(text: str) -> str | None:
        patterns = (
            re.compile(
                r"(?:код\s+єдрпоу|код\s+за\s+єдрпоу|єдрпоу|дрфо)"
                r"\s*[:№]?\s*(\d{8,10})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:іпн|рнокпп)"
                r"\s*[:№]?\s*(\d{10,12})",
                re.IGNORECASE,
            ),
        )

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
            matches = list(re.finditer(pattern, text))

            if not matches:
                continue

            return self._to_decimal(matches[-1].group(1))

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