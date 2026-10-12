# Original PDF fixtures

Original invoices are stored here without changing their PDF text layers:

- `marchuk_thousands_separator.pdf`: ФОП Марчук, one item, price and total 1 414,35.
- `cms_multiple_multiline_items.pdf`: СІ ЕМ ЕС, two multiline items priced
  320.10 and 197.40; net 517.50, VAT 103.50, gross 621.00.

- `Рахунок_0299-065459_від_07_09_2026.pdf`: VIATEC 99-65459, code 99-00022220.
- `viatec_99-63381.pdf`: VIATEC 99-63381, code 99-00014826.
- `cms_177559.pdf`: CMS 177559, article cell `LW-WPKJL-SC/APC-2-1port імпорт`.
- `etna_2285.pdf`: ETNA 2285, code `KF 09050_UVFA`, wrapped customs code.
- `2257.pdf`: ETNA 2257, code `2332/LPE-1_F50DU`.

The article/name expectation for ETNA 2257 now separates the supplier code
from the name. Existing numeric and supplier expectations are unchanged.
Missing files intentionally fail; there are no skips or xfails.

Run from the repository root:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
```
