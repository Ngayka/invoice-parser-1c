from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

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
    assert item.product_code == "2332/LPE-1_F50DU"
    assert item.name == "Труба гофрована електромонтажна з протяжкою,УФ-стійка, 320 N/5см; Ø32мм; ПЕ; чорна; Бухта 50 м, UA"
    assert item.unit == "м"
    assert item.quantity == Decimal("50")
    assert item.source_price == Decimal("17.96")
    assert item.source_total == Decimal("898.00")
    assert invoice.total_net == Decimal("898.00")
    assert invoice.vat_total == Decimal("179.60")
    assert invoice.total_gross == Decimal("1077.60")


@pytest.mark.parametrize("filename,number,code,name,quantity,price,total", [
    ("Рахунок_0299-065459_від_07_09_2026.pdf", "99-65459", "99-00022220",
     "Мудуль SFP EW-SFP-GE-T1310 / EW-SFP-GE-R1550", "1", "929.88", "929.88"),
    ("viatec_99-63381.pdf", "99-63381", "99-00014826",
     "Відеокамера телевізійна Dahua DH-HAC-HDW1500TP-IL-A", "2", "1575.00", "3150.00"),
    ("cms_177559.pdf", "177559", "LW-WPKJL-SC/APC-2-1port",
     "Водонепроникний вуличний оптоволоконний з'єднувач SC-Simplex IP68", "30", "170.60", "5118.00"),
    ("etna_2285.pdf", "2285", "KF 09050_UVFA",
     "Труба гофрована гнучка; УФ-стійка; двошарова Копофлекс, чорна, протяжка,з муфтою; Ø50мм; HDPE; Бухта 50 м", "50", "28.95", "1447.50"),
    ("marchuk_thousands_separator.pdf", "580", None,
     "Акумуляторна батарея 12V20Ah/20Hr TRINIX SUPER CHARGE", "1", "1414.35", "1414.35"),
])
def test_supplier_product_codes(filename, number, code, name, quantity, price, total):
    invoice = InvoiceService().parse_pdf((FIXTURES_DIR / filename).read_bytes())
    assert invoice.number == number
    assert len(invoice.items) == 1
    item = invoice.items[0]
    assert item.product_code == code
    assert item.name == name
    assert item.quantity == Decimal(quantity)
    assert item.source_price == Decimal(price)
    assert item.source_total == Decimal(total)


@pytest.mark.parametrize("body", [
    "12V20Ah/20Hr TRINIX SUPER CHARGE",
    "99-00022220 Модуль SFP",
    "3925908000 Коробка",
])
def test_no_product_code_without_article_column(body):
    parser = InvoiceService().parser
    item = parser._build_item_from_parts(
        body=body, quantity="1", unit="шт", price="1.00", total="1.00",
    )
    assert item.product_code is None
    assert item.name == body


def test_cms_177559_normalized_product_code():
    invoice = InvoiceService().parse_pdf((FIXTURES_DIR / "cms_177559.pdf").read_bytes())
    item, = invoice.items
    assert item.product_code == "LW-WPKJL-SC/APC-2-1port"
    assert item.name == "Водонепроникний вуличний оптоволоконний з'єднувач SC-Simplex IP68"


@pytest.mark.parametrize("article,expected", [
    ("SKU-123 імпорт", "SKU-123"),
    ("SKU-123 импорт", "SKU-123"),
    ("SKU-123 ІМПОРТ", "SKU-123"),
    ("SKU-123", "SKU-123"),
    ("SKU-123-імпорт", "SKU-123-імпорт"),
    ("SKU-123 імпортний", "SKU-123 імпортний"),
    ("імпорт SKU-123", "імпорт SKU-123"),
])
def test_cms_removes_only_separate_trailing_import_word(article, expected):
    code, name = InvoiceService().parser._split_item_body(
        f"{article} УКТЗЕД: 3925908000 Назва товару", "cms",
    )
    assert code == expected
    assert name == "Назва товару"


@pytest.mark.parametrize("strategy,table", [
    ("_parse_common_row_items", "1 99-00022220 Модуль 1 шт 1.00 1.00"),
    ("_parse_cms_items", "1 99-00022220 Модуль шт 1 1.00 1.00"),
    ("_parse_etna_items", "1\n99-00022220 Модуль\n1 шт\n1.00\n1.00"),
    ("_parse_common_columnar_items", "1 99-00022220 Модуль\n1\nшт\n1.00\n1.00"),
])
def test_code_context_reaches_all_strategies(strategy, table):
    parser = InvoiceService().parser
    item, = getattr(parser, strategy)(table, code_column="code")
    assert item.product_code == "99-00022220"
    assert item.name == "Модуль"
