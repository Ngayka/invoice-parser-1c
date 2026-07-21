from pathlib import Path
import json

from app.schemas.invoice import InvoiceData


def save_json(invoice: InvoiceData) -> Path:
    directory = Path("exports")
    directory.mkdir(exist_ok=True)

    filename = f"{invoice.number}_{invoice.date}.json"

    path = directory / filename

    path.write_text(
        invoice.model_dump_json(indent=4),
        encoding="utf-8",
    )

    return path
