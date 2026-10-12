"""Real-PDF acceptance contracts for additional supported formats.

Run from invoice-parser-1c with pytest tests/test_additional_pdf_formats.py.
No parsing mocks or expected-failure markers are used.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.invoice_service import InvoiceService


FIXTURES = Path(__file__).resolve().parent / "fixtures"
HOLDER = "Тримач EFH 10 2P 25A 1000V DC"
FUSE = "Запобіжник CH 10x38 gPV 20A 1000V (30kA)"
CASES = [
    dict(filename="Рахунок_на_оплату_№_УТ_3422_від_02_10_2026.pdf",
         number="УТ-3422", supplier='ТОВ "ЕТІКОМ ЕНЕРГО"', code="45494295",
         iban="UA643052990000026005050586613", mode="exclusive",
         totals=("2419.53", "483.91", "2903.44"),
         rows=[(HOLDER, "2540203", "шт", "3", "242.96", "728.88"),
               (FUSE, "2625085", "шт", "3", "114.18", "342.54"),
               ("Авт. вимикач ETIMAT 10 DC 2p C 25A (6 kA)", "2138718", "шт", "3", "449.37", "1348.11")]),
    dict(filename="Рахунок_на_оплату_№_УТ_3411_від_02_10_2026_1.pdf",
         number="УТ-3411", supplier='ТОВ "ЕТІКОМ ЕНЕРГО"', code="45494295",
         iban="UA643052990000026005050586613", mode="exclusive",
         totals=("6724.00", "1344.80", "8068.80"),
         rows=[("Щит зовнішн. розподільний ECT 12PT (12мод.проз.дверцята)", "1101001", "шт", "1", "478.00", "478.00"),
               (HOLDER, "2540203", "шт", "2", "243.00", "486.00"),
               (FUSE, "2625085", "шт", "4", "114.00", "456.00"),
               ("VAL-SPP-T2-1000DC-PV2+V-UT: ПЗІП тип 2/клас II, для 2-провод. фотогальв. систем до 1000 В=, 3-пол", "PCA 1", "шт", "2", "2652.00", "5304.00")]),
    dict(filename="150.pdf", number="СФ-0000150",
         supplier="ФОП ВІТЕР ВАЛЕРІЙ ВІТАЛІЙОВИЧ", code="2282324137",
         iban="UA343052990000026007040153571", mode="none",
         totals=("2059.96", "0.00", "2059.96"),
         rows=[("Профіль монтажний універсальний 41 L=3,0 м(толщ. 1,50 мм)", None, "м", "9", "140.00", "1260.04"),
               ("Притиск міжпанельний довжиною 40 мм (30-35) НАБОР", None, "шт", "16", "40.00", "639.94"),
               ("Притиск кінцевий 30мм НАБОР", None, "шт", "4", "40.00", "159.98")]),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["number"])
def test_pdf_document_contract(case):
    invoice = InvoiceService().parse_pdf((FIXTURES / case["filename"]).read_bytes())
    errors = []

    def equal(field, actual, expected):
        if actual != expected:
            errors.append(f"{field}: expected {expected!r}, actual {actual!r}")

    equal("number", invoice.number, case["number"])
    equal("date", invoice.date, date(2026, 10, 2))
    equal("supplier.name", invoice.supplier.name, case["supplier"])
    equal("supplier.tax_code", invoice.supplier.tax_code, case["code"])
    equal("supplier.iban", invoice.supplier.iban, case["iban"])
    equal("vat_mode", invoice.vat_mode, case["mode"])
    for field, expected in zip(("total_net", "vat_total", "total_gross"), case["totals"]):
        # Same cent quantization and Decimal context as the project; exact equality
        # additionally ensures unexpected fractional cents are not hidden.
        equal(field, getattr(invoice, field), Decimal(expected).quantize(Decimal("0.01")))
    equal("items.count", len(invoice.items), len(case["rows"]))
    for index, (item, row) in enumerate(zip(invoice.items, case["rows"]), 1):
        for field, expected in zip(("name", "product_code", "unit", "quantity", "source_price", "source_total"), row):
            if field in ("quantity", "source_price", "source_total"):
                expected = Decimal(expected)
            equal(f"items[{index}].{field}", getattr(item, field), expected)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["number"])
def test_pdf_preserves_document_amounts(case):
    invoice = InvoiceService().parse_pdf((FIXTURES / case["filename"]).read_bytes())
    assert len(invoice.items) == len(case["rows"])
    expected_differences = [
        Decimal(row[5]) - Decimal(row[3]) * Decimal(row[4])
        for row in case["rows"]
    ]
    assert [item.source_total - item.quantity * item.source_price
            for item in invoice.items] == expected_differences
    assert sum((item.source_total for item in invoice.items), Decimal("0.00")) == invoice.total_net
