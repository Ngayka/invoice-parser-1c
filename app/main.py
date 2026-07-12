from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request


app = FastAPI()
from fastapi import FastAPI

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
