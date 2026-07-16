from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierRaw(BaseModel):
    name: str | None = None
    tax_code: str | None = None
    iban: str | None = None


class InvoiceItem(BaseModel):
    name: str
    unit: str
    quantity: Decimal

    source_price: Decimal
    source_total: Decimal

    price_net: Decimal | None = None
    price_gross: Decimal | None = None

    total_net: Decimal | None = None
    total_gross: Decimal | None = None


class InvoiceData(BaseModel):
    number: str
    date: Date
    supplier: SupplierRaw
    items: list[InvoiceItem]

    vat_mode: str
    vat_rate: Decimal | None = None

    total_net: Decimal | None = None
    vat_total: Decimal | None = None
    total_gross: Decimal
