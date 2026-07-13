from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierRaw(BaseModel):
    name: str | None = None
    tax_code: str | None = None
    iban: str | None = None


class InvoiceItem(BaseModel):
    name: str
    unit: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)


class InvoiceData(BaseModel):
    number: str | None = None
    date: Date | None = None
    supplier: SupplierRaw
    items: list[InvoiceItem] = []
    total: Decimal | None = None
