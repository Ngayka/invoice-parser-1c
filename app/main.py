from fastapi import FastAPI, File, UploadFile
from app.routes import router as invoice_router


app = FastAPI(
    title="Invoice Parser API",
    version="0.1.0",
)

app.include_router(
    invoice_router,
    prefix="/api/invoices",
    tags=["Invoices"],
)
