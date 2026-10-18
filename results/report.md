# Invoice extraction eval: `gemini-3.5-flash-lite`

- **Field accuracy:** 100.0% (header fields + line items, 30 invoices)
- **Invoices with every field correct:** 30/30 (PDF 20/20, phone photo 10/10)
- **Error detection:** caught 10/10 planted issues, 0 false alarms
- **Line-item count correct:** 30/30
- **Category accuracy (LLM classification, not printed):** 96.7%
- **Avg latency:** 4.6 s per invoice

## Per field

| Field | Correct |
|---|---|
| vendor | 30/30 |
| vendor_address | 30/30 |
| bill_to | 30/30 |
| invoice_number | 30/30 |
| invoice_date | 30/30 |
| due_date | 30/30 |
| currency | 30/30 |
| subtotal | 30/30 |
| tax | 30/30 |
| total | 30/30 |
| tax_rate | 30/30 |
| item.description | 60/60 |
| item.quantity | 60/60 |
| item.unit_price | 60/60 |
| item.amount | 60/60 |

## Misses

None.
