# Original PDF fixtures

Place the original invoices here without changing their PDF text layers:

- `marchuk_thousands_separator.pdf`: ФОП Марчук, one item, price and total 1 414,35.
- `cms_multiple_multiline_items.pdf`: СІ ЕМ ЕС, two multiline items priced
  320.10 and 197.40; net 517.50, VAT 103.50, gross 621.00.

These source PDFs were not present in the repository or its ZIP archive when
the tests were added. They must be supplied before parsing regressions can be
verified. Missing files intentionally fail; there are no skips or xfails.

Run from the repository root:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
```
