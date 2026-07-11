# Singapore receipt & invoice formats

Reference for SplitLeh OCR and parse logic. Receipts vary by POS vendor, but Singapore F&B bills follow recurring patterns driven by [IRAS GST rules](https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/specific-business-sectors/hotel-and-food-beverage).

## What a compliant receipt usually contains

| Section | Typical content |
|---|---|
| Header | Business name, address, **GST Reg No.** (e.g. `201630159R`, `200711627G`), table/cover, cashier |
| Line items | Qty, optional PLU code, description, line total |
| Footer | Subtotal → discounts → **10% service charge** → **9% GST** → rounding → **total** |
| Payment | VISA, NETS, PayNow, Kris+, cash - **not food items** |
| IRAS line | *"Price payable includes GST"* on serialised receipts |

Dine-in F&B may show **GST-exclusive menu prices**; the printed bill adds service charge and GST at the bottom. Takeaway / no-service-charge outlets often skip the 10% line.

## Standard charge order (IRAS)

Most full-service restaurants:

```
items sum
  → item / promo discounts (often negative or in parentheses)
  → SUBTOTAL
  → 10% service charge (on net food amount - POS vendors differ on before/after discount)
  → 9% GST on (net subtotal + service charge)
  → rounding (sometimes to nearest $0.05 for cash)
  → TOTAL
  → payment tender (same amount as total)
```

Two GST calculation methods are both IRAS-acceptable: per-line GST summed, or GST on the bill total. EPOS and similar systems often use per-line rounding, so totals may differ by a few cents from naïve `9% × subtotal`.

## Label variants we see in the wild

| Charge | OCR / POS labels |
|---|---|
| Subtotal | `SUBTOTAL`, `Sub Total`, `SUBTTL`, `CUBTOTA` (garbled) |
| Discount | `ITEM DISC 30%`, `%DISC 10% (STAFF DISC)`, `Member Discount`, `($136.80)` |
| Service | `10% Svr Chrg`, `SERVICE CHARGE 10%`, `SERVICE CHA`, `S/C`, `Sur Chirge` |
| GST | `9% GST`, `GST 9%`, `8% GST` (legacy), `96ST` (garbled) |
| Total | `TOTAL`, `Grand Total`, `Nett Total`, `Bill Total` |
| Payment | `VISA`, `NETS`, `KRISPLUS`, `PayNow`, `Cash`, `Change` |

## Layout patterns in our samples

### A - Single-column POS (Natureland-style)

```
1 (Promo) Guinness      $13.00
2 Ki No Bi Btl         $456.00
ITEM DISC 30%          ($136.80)
SUBTOTAL               $371.80
10% Svr Chrg            $37.18
9% GST                  $36.81
TOTAL                  $445.79
VISA                   $445.79
```

Fixture: `lite/core/tests/fixtures/receipts/pos_natureland.txt`  
Image: `samples/sample.jpg` (local, gitignored)

### B - Qty-first with SUBTTL (Tsuta / Jewel)

```
3      SLICE BEEF PHO                    44 40
SUBTTL                             226.50
%DISC 10.00% (STAFF _DISC) STAFF      -22.65
SERVICE CHARGE 10%                   20.39
GST 9%                      (garbled)
TOTAL          244.42
KRISPLUS                             244.42
```

Notes: spaced decimals (`44 40` → $44.40), staff discount **before** service charge, payment line must not become an item.

Fixture: `lite/core/tests/fixtures/receipts/tsuta.txt`  
Source OCR: `samples/sample2-ocr.txt`

### C - PLU code column (Sanook / mall POS)

```
Qty         Items
2             6657 Honey Butterfly
...
1            6302 Deep-fried Chicken                   990 |
239.10
Sub Total
SERVICE CHA
GST 9%
Total
VISA
```

Notes: item name and price often on **separate lines**; implicit decimals (`990` → $9.90); footer amounts may appear **above** the label row; heavy OCR noise on modifiers.

Fixture: `lite/core/tests/fixtures/receipts/sanook.txt`  
Source OCR: `samples/sample3-ocr.txt`

### D - Hawker / simple (no service charge)

```
Wonton Soup         5.50
Subtotal            9.50
GST 9%              0.86
Total              10.36
```

Fixture: `lite/core/tests/fixtures/receipts/noisy.txt`

## What SplitLeh does with this

| Layer | Role |
|---|---|
| `splitleh/sg_receipt.py` | SG rates, footer detection, net-subtotal math |
| `splitleh/parse_receipt.py` | Line-by-line item/charge heuristics + noise filter |
| `splitleh/repair_receipt.py` | Infer missing S/C + GST; accept gross **or** net 10% |
| `splitleh_ocr/normalize.py` | Textract structured fields → items/charges |
| `splitleh_ocr/pick_parse.py` | Score multiple parse strategies; pick best |

## Adding more samples

1. Drop raw OCR `.txt` into repo-root `samples/` (gitignored photos OK).
2. Copy normalised `.txt` into `lite/core/tests/fixtures/receipts/`.
3. Add pytest in `cloud/api/tests/splitleh/test_sg_receipts.py`.
4. Run `npm test` (Vitest) and `uv run pytest` for parity.

## References

- [IRAS - Hotel and F&B GST](https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/specific-business-sectors/hotel-and-food-beverage)
- [IRAS - Displaying and quoting prices](https://www.iras.gov.sg/taxes/goods-services-tax-(gst)/basics-of-gst/invoicing-price-display-and-record-keeping/displaying-and-quoting-prices)
- [EPOS - GST calculation methods](https://www.epos.com.sg/knowledge-base-gst-calculation-in-epos/)
- [AWS Textract AnalyzeExpense](https://docs.aws.amazon.com/textract/latest/dg/invoices-receipts.html)
