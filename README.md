# PDF Invoice Parser for 1C

A FastAPI application for parsing supplier invoices in PDF format and exporting structured invoice data to JSON for subsequent import into 1C.

The project was developed to automate the processing of supplier invoices and reduce manual data entry into the ERP system.

---

## Features

- Upload PDF invoices through a web interface
- Parse invoice metadata:
  - invoice number
  - invoice date
  - supplier
- Parse product lines:
  - product name
  - unit of measure
  - quantity
  - price
  - total
- Detect VAT information
- Export parsed data to JSON
- Store JSON files for subsequent import into 1C

---

## Workflow

```text
PDF Invoice
      │
      ▼
FastAPI Parser
      │
      ▼
JSON
      │
      ▼
exports/
      │
      ▼
1C External Processing (.epf)
      │
      ▼
ПоступлениеТоваровУслуг
      │
      ▼
Accountant verification
      │
      ▼
processed/
```

---

## Technology Stack

- Python 3.12
- FastAPI
- Uvicorn
- PyMuPDF
- Jinja2

---

## Project Structure

```text
pdf_parsing_project/
│
├── app/
│   ├── main.py
│   ├── parsers/
│   ├── templates/
│   └── static/
│
├── exports/
├── processed/
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Installation

Clone the repository

```bash
git clone https://github.com/<your_username>/pdf_parsing_project.git
```

Go to the project

```bash
cd pdf_parsing_project
```

Create a virtual environment

```bash
python -m venv .venv
```

Activate it

Windows

```cmd
.venv\Scripts\activate
```

Linux

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run

```bash
python -m uvicorn app.main:app --reload
```

Application:

```
http://127.0.0.1:8000
```

Swagger documentation:

```
http://127.0.0.1:8000/docs
```

---

## API

### Parse invoice

```
POST /api/invoices/parse
```

Returns parsed invoice as JSON.

### Parse and save invoice

```
POST /api/invoices/parse-and-save
```

Parses the invoice and saves the resulting JSON file into the **exports** directory.

---

## Integration with 1C

The application does **not** communicate directly with 1C.

Integration is file-based:

```
PDF → FastAPI → JSON → 1C External Processing → Accountant
```

The external 1C processing:

- reads the JSON file;
- finds the corresponding supplier and products;
- creates a **ПоступлениеТоваровУслуг** document;
- opens the document for verification before posting.

---

## Notes

- Only text-based PDF invoices are currently supported.
- Scanned documents without a text layer are not supported.
- The parser currently supports several supplier invoice layouts.
- New supplier formats can be added by extending the parser.

---

## Future Improvements

- OCR support for scanned invoices
- Additional supplier layouts
- Automatic validation of parsed data
- Windows Service deployment
- Direct ERP integrations

---

## License

This project is intended for educational and internal business automation purposes.