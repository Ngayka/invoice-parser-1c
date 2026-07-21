import re


def _extract_items_table(self, text: str) -> str:
    normalized = self._normalize_pdf_text(text)

    header_patterns = (
        # Сума без ПДВ
        r"Сума\s+без\s+ПДВ\s*\n",

        # Сума з ПДВ
        r"Сума\s+з\s+ПДВ\s*\n",

        # Просто Сума
        r"\bСума\s*\n",
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

    return normalized
