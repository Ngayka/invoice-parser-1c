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

        # 1. Звичайні однорядкові формати.
        parsed_items: list[InvoiceItem] = []

        for line in table_text.splitlines():
            line = line.strip()

            if not line:
                continue

            if not re.match(r"^\d{1,3}[ \t]+", line):
                continue

            item = self._parse_item_line(line)

            if item is not None:
                parsed_items.append(item)

        if parsed_items:
            return parsed_items

        # 2. Колонковий формат PyMuPDF.
        parsed_items = self._parse_columnar_items(table_text)

        if parsed_items:
            return parsed_items

        # 3. Загальний багаторядковий fallback.
        parsed_items = []

        for block in self._split_multiline_item_blocks(table_text):
            item = self._parse_item_block(block)

            if item is not None:
                parsed_items.append(item)
            else:
                print("Не вдалося розпізнати товарний блок:")
                print(repr(block))

        return parsed_items

    def _parse_columnar_items(
        self,
        table_text: str,
    ) -> list[InvoiceItem]:
        lines = [
            line.strip()
            for line in table_text.splitlines()
            if line.strip()
        ]

        # Рядок опису:
        # 1 99-00015445 Назва товару
        description_pattern = re.compile(
            r"""
            ^
            (?P<number>\d{1,3})
            [ \t]+
            (?:
                (?P<article>
                    [A-Za-zА-Яа-яІіЇїЄєҐґ0-9._/\-]+
                )
                [ \t]+
            )?
            (?P<name>.+)
            $
            """,
            flags=re.IGNORECASE | re.VERBOSE,
        )

        quantity_pattern = re.compile(
            rf"^(?P<quantity>{QUANTITY_PATTERN})$"
        )
        unit_pattern = re.compile(
            rf"^(?P<unit>{UNIT_PATTERN})$",
            flags=re.IGNORECASE,
        )
        price_pattern = re.compile(
            rf"^(?P<price>{PRICE_PATTERN})$"
        )
        total_pattern = re.compile(
            rf"^(?P<total>{AMOUNT_PATTERN})$"
        )

        parsed_items: list[InvoiceItem] = []
        index = 0

        while index < len(lines):
            description_match = description_pattern.match(lines[index])

            if not description_match:
                index += 1
                continue

            # Щоб не прийняти звичайний службовий рядок за товар,
            # після опису очікуємо quantity, unit, price, total.
            if index + 4 >= len(lines):
                index += 1
                continue

            quantity_match = quantity_pattern.match(lines[index + 1])
            unit_match = unit_pattern.match(lines[index + 2])
            price_match = price_pattern.match(lines[index + 3])
            total_match = total_pattern.match(lines[index + 4])

            if not (
                quantity_match
                and unit_match
                and price_match
                and total_match
            ):
                index += 1
                continue

            raw_name = description_match.group("name")
            name = self._clean_item_body(raw_name)

            quantity_value = self._to_decimal(
                quantity_match.group("quantity")
            )
            price_value = self._to_decimal(
                price_match.group("price")
            )
            total_value = self._to_decimal(
                total_match.group("total")
            )

            if (
                name
                and quantity_value is not None
                and price_value is not None
                and total_value is not None
            ):
                parsed_items.append(
                    InvoiceItem(
                        name=name,
                        unit=self._normalize_unit(
                            unit_match.group("unit")
                        ),
                        quantity=quantity_value,
                        source_price=price_value,
                        source_total=total_value,
                    )
                )

            index += 5

        return parsed_items

    def _parse_item_line(self, line: str) -> InvoiceItem | None:
        amount = AMOUNT_PATTERN
        price = PRICE_PATTERN
        quantity = QUANTITY_PATTERN
        unit = UNIT_PATTERN

        flags = re.IGNORECASE | re.VERBOSE

        patterns = (
            # СТБ, Марчук та інші:
            # number body quantity unit price total
            re.compile(
                rf"""
                ^[ \t]*
                \d+
                [ \t]+
                (?P<body>.+?)
                [ \t]+
                (?P<quantity>{quantity})
                [ \t]+
                (?P<unit>{unit})
                [ \t]+
                (?P<price>{price})
                [ \t]+
                (?P<total>{amount})
                [ \t]*$
                """,
                flags=flags,
            ),

            # CMS:
            # number body unit quantity price total
            re.compile(
                rf"""
                ^[ \t]*
                \d+
                [ \t]+
                (?P<body>.+?)
                [ \t]+
                (?P<unit>{unit})
                [ \t]+
                (?P<quantity>{quantity})
                [ \t]+
                (?P<price>{price})
                [ \t]+
                (?P<total>{amount})
                [ \t]*$
                """,
                flags=flags,
            ),
        )

        for pattern in patterns:
            match = pattern.match(line)

            if match:
                return self._create_invoice_item(match)

        return None

    def _split_multiline_item_blocks(
            self,
            table_text: str,
    ) -> list[str]:
        normalized = self._normalize_pdf_text(table_text)

        lines = normalized.splitlines()
        blocks: list[list[str]] = []
        current_block: list[str] = []

        for index, line in enumerate(lines):
            stripped = line.strip()

            if not stripped:
                continue

            is_item_start = bool(
                re.match(
                    r"^\d{1,3}(?:[ \t]+.+)?$",
                    stripped,
                )
            )

            # Рядок лише з числом може бути як номером позиції,
            # так і кількістю. Вважаємо його номером позиції,
            # тільки якщо наступний рядок схожий на назву товару.
            if re.fullmatch(r"\d{1,3}", stripped):
                next_line = (
                    lines[index + 1].strip()
                    if index + 1 < len(lines)
                    else ""
                )

                next_is_text = bool(
                    next_line
                    and not re.fullmatch(QUANTITY_PATTERN, next_line)
                    and not re.fullmatch(
                        UNIT_PATTERN,
                        next_line,
                        flags=re.IGNORECASE,
                    )
                    and not re.fullmatch(PRICE_PATTERN, next_line)
                )

                is_item_start = next_is_text

            if is_item_start and current_block:
                blocks.append(current_block)
                current_block = []

            current_block.append(stripped)

        if current_block:
            blocks.append(current_block)

        return [
            "\n".join(block)
            for block in blocks
            if block
        ]

    def _parse_item_block(self, block: str) -> InvoiceItem | None:
        normalized = self._normalize_pdf_text(block)

        amount = AMOUNT_PATTERN
        price = PRICE_PATTERN
        quantity = QUANTITY_PATTERN
        unit = UNIT_PATTERN

        flags = re.IGNORECASE | re.DOTALL | re.VERBOSE

        patterns = (
            # Багаторядковий звичайний формат:
            # number body quantity unit price total
            re.compile(
                rf"""
                ^[ \t]*
                \d+
                [ \t\r\n]+
                (?P<body>.+?)
                [ \t\r\n]+
                (?P<quantity>{quantity})
                [ \t\r\n]+
                (?P<unit>{unit})
                [ \t\r\n]+
                (?P<price>{price})
                [ \t\r\n]+
                (?P<total>{amount})
                [ \t\r\n]*$
                """,
                flags=flags,
            ),

            # Багаторядковий CMS:
            # number body unit quantity price total
            re.compile(
                rf"""
                ^[ \t]*
                \d+
                [ \t\r\n]+
                (?P<body>.+?)
                [ \t\r\n]+
                (?P<unit>{unit})
                [ \t\r\n]+
                (?P<quantity>{quantity})
                [ \t\r\n]+
                (?P<price>{price})
                [ \t\r\n]+
                (?P<total>{amount})
                [ \t\r\n]*$
                """,
                flags=flags,
            ),
        )

        for pattern in patterns:
            match = pattern.match(normalized)

            if match:
                return self._create_invoice_item(match)

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