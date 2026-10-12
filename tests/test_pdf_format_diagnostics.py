"""Real-PDF metadata and totals checks through the complete service path."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.invoice_service import InvoiceService


FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = [
    ("Рахунок_на_оплату_№_УТ_3422_від_02_10_2026.pdf", "УТ-3422",
     'ТОВ "ЕТІКОМ ЕНЕРГО"', "45494295", "UA643052990000026005050586613",
     "exclusive", ("2419.53", "483.91", "2903.44")),
    ("Рахунок_на_оплату_№_УТ_3411_від_02_10_2026_1.pdf", "УТ-3411",
     'ТОВ "ЕТІКОМ ЕНЕРГО"', "45494295", "UA643052990000026005050586613",
     "exclusive", ("6724.00", "1344.80", "8068.80")),
    ("150.pdf", "СФ-0000150", "ФОП ВІТЕР ВАЛЕРІЙ ВІТАЛІЙОВИЧ",
     "2282324137", "UA343052990000026007040153571",
     "none", ("2059.96", "0.00", "2059.96")),
]


@pytest.mark.parametrize("case", CASES, ids=[case[1] for case in CASES])
def test_real_pdf_metadata_diagnostic(case):
    filename, number, name, code, iban, mode, _ = case
    service = InvoiceService()
    invoice = service.parse_pdf((FIXTURES / filename).read_bytes())
    supplier = invoice.supplier
    actual = {
        "number": invoice.number,
        "date": invoice.date,
        "supplier.name": supplier.name,
        "supplier.tax_code": supplier.tax_code,
        "supplier.iban": supplier.iban,
        "vat_mode": invoice.vat_mode,
    }
    expected = dict(zip(actual, (number, date(2026, 10, 2), name, code, iban, mode)))
    differences = [
        f"{field}: expected {expected[field]!r}, actual {value!r}"
        for field, value in actual.items() if value != expected[field]
    ]
    assert not differences, "\n".join(differences)


@pytest.mark.parametrize("case", CASES, ids=[case[1] for case in CASES])
def test_real_pdf_totals_diagnostic(case):
    service = InvoiceService()
    invoice = service.parse_pdf((FIXTURES / case[0]).read_bytes())
    actual = (invoice.total_net, invoice.vat_total, invoice.total_gross)
    expected = tuple(Decimal(value).quantize(Decimal("0.01")) for value in case[6])
    assert actual == expected
