from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.invoice_service import InvoiceService


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_marchuk_price_with_thousands_separator():
    content = (FIXTURES_DIR / "marchuk_thousands_separator.pdf").read_bytes()

    invoice = InvoiceService().parse_pdf(content)

    assert len(invoice.items) == 1
    item = invoice.items[0]
    assert item.quantity == Decimal("1")
    assert item.source_price == Decimal("1414.35")
    assert item.source_total == Decimal("1414.35")
    assert invoice.total_gross == Decimal("1414.35")


def test_cms_multiple_multiline_items():
    content = (FIXTURES_DIR / "cms_multiple_multiline_items.pdf").read_bytes()

    invoice = InvoiceService().parse_pdf(content)

    assert len(invoice.items) == 2
    first, second = invoice.items
    assert first.quantity == Decimal("1")
    assert first.source_price == Decimal("320.10")
    assert first.source_total == Decimal("320.10")
    assert second.quantity == Decimal("1")
    assert second.source_price == Decimal("197.40")
    assert second.source_total == Decimal("197.40")
    assert invoice.total_net == Decimal("517.50")
    assert invoice.vat_total == Decimal("103.50")
    assert invoice.total_gross == Decimal("621.00")


def test_viatec_invoice_with_inclusive_vat():
    content = (FIXTURES_DIR / "Рахунок_0299-065459_від_07_09_2026.pdf").read_bytes()

    invoice = InvoiceService().parse_pdf(content)

    assert invoice.number == "99-65459"
    assert invoice.date == date(2026, 9, 7)
    assert invoice.supplier.name == 'ТОВ "ВІАТЕК"'
    assert invoice.supplier.tax_code == "36413740"
    assert invoice.supplier.iban == "UA983348510000000026003238732"
    assert len(invoice.items) == 1
    item = invoice.items[0]
    assert item.name == "Мудуль SFP EW-SFP-GE-T1310 / EW-SFP-GE-R1550"
    assert item.unit == "шт"
    assert item.quantity == Decimal("1")
    assert item.source_price == Decimal("929.88")
    assert item.source_total == Decimal("929.88")
    assert invoice.vat_mode == "inclusive"
    assert invoice.total_net == Decimal("774.90")
    assert invoice.vat_total == Decimal("154.98")
    assert invoice.total_gross == Decimal("929.88")


def test_etna_invoice():
    content = (FIXTURES_DIR / "2257.pdf").read_bytes()

    invoice = InvoiceService().parse_pdf(content)

    assert invoice.number == "2257"
    assert invoice.date == date(2026, 9, 23)
    assert invoice.supplier.name == 'ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ "ЕТК ЕТНА"'
    assert invoice.supplier.tax_code == "45980145"
    assert invoice.supplier.iban == "UA963052990000026003040147547"
    assert len(invoice.items) == 1
    item = invoice.items[0]
    assert "2332/LPE-1_F50DU Труба гофрована електромонтажна" in " ".join(item.name.split())
    assert item.unit == "м"
    assert item.quantity == Decimal("50")
    assert item.source_price == Decimal("17.96")
    assert item.source_total == Decimal("898.00")
    assert invoice.total_net == Decimal("898.00")
    assert invoice.vat_total == Decimal("179.60")
    assert invoice.total_gross == Decimal("1077.60")
