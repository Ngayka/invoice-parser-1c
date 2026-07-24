from fastapi import APIRouter, UploadFile, HTTPException

from app.schemas.invoice import InvoiceData
from app.services.invoice_service import InvoiceService


router = APIRouter()

invoice_service = InvoiceService()


@router.post("/parse", response_model=InvoiceData)
async def parse_invoice(file: UploadFile):

    content = await file.read()

    return invoice_service.parse_pdf(content)


@router.post("/parse-and-save")
async def parse_and_save(file: UploadFile):

    content = await file.read()

    invoice = invoice_service.parse_pdf(content)

    path = invoice_service.save_json(invoice)
    try:
        return {
            "success": True,
            "message": "Документ успішно збережено. Перейдіть до завантаження документа в 1С."
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Не вдалося обробити рахунок: {error}",
        )
