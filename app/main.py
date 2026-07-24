from fastapi import FastAPI, Request
from app.routes import router as invoice_router
from fastapi.templating import Jinja2Templates


app = FastAPI(
    title="Invoice Parser API",
    version="0.1.0",
)

app.include_router(
    invoice_router,
    prefix="/api/invoices",
    tags=["Invoices"],
)

templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="invoice_parser.html",
        context={}
    )


@app.get("/save")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="invoice_parser_save.html",
        context={}
    )
