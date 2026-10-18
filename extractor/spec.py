"""Single source of truth for the extraction prompt, output schema and validation rules.

The n8n workflow is generated from this file (build_workflow.py), so the prompt and
rules used in production are exactly the ones the eval script measures.
"""

CATEGORIES = [
    "Software & Subscriptions", "Office Supplies", "Equipment", "Travel",
    "Meals & Entertainment", "Advertising & Marketing", "Professional Services",
    "Shipping & Logistics", "Rent & Utilities", "Other",
]

PROMPT = f"""You are an accounts-payable assistant. Extract the data printed on this invoice.

Rules:
- Copy values exactly as printed. Do NOT correct arithmetic, even if the numbers look wrong.
- Dates as YYYY-MM-DD. If a field is not printed (e.g. no due date), return null.
- currency: 3-letter ISO code (USD, EUR, GBP, CAD, ...), inferred from symbols if needed.
- Numbers as plain numbers without currency symbols or thousands separators.
- tax_rate as a decimal (8% -> 0.08). If only a tax amount is printed, return null for tax_rate.
- For each line item, choose the best category from: {", ".join(CATEGORIES)}.
"""

_num = {"type": "NUMBER", "nullable": True}
_str = {"type": "STRING", "nullable": True}

# Gemini responseSchema (OpenAPI subset)
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "vendor": _str,
        "vendor_address": _str,
        "bill_to": _str,
        "invoice_number": _str,
        "invoice_date": _str,
        "due_date": _str,
        "currency": _str,
        "line_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "quantity": _num,
                    "unit_price": _num,
                    "amount": _num,
                    "category": {"type": "STRING", "enum": CATEGORIES},
                },
                "required": ["description", "amount", "category"],
            },
        },
        "subtotal": _num,
        "tax_rate": _num,
        "tax": _num,
        "total": _num,
    },
    "required": ["vendor", "invoice_number", "invoice_date", "currency", "line_items", "total"],
}

TOL = 0.02  # money tolerance for rounding


def validate(inv: dict) -> list[str]:
    """Deterministic checks. Mirrors VALIDATE_JS below; keep both in sync."""
    flags = []
    items = inv.get("line_items") or []
    items_sum = round(sum((it.get("amount") or 0) for it in items), 2)
    subtotal, tax, total = inv.get("subtotal"), inv.get("tax") or 0, inv.get("total")

    if not inv.get("vendor") or not inv.get("invoice_number") or total is None:
        flags.append("missing_required_fields")
    if not inv.get("due_date"):
        flags.append("missing_due_date")
    if subtotal is not None and abs(items_sum - subtotal) > TOL:
        flags.append("items_sum_mismatch")
    # Compare against the line items, so a wrong subtotal is reported once, not twice
    if total is not None and items and abs(items_sum + tax - total) > TOL:
        flags.append("total_mismatch")
    for it in items:
        q, u, a = it.get("quantity"), it.get("unit_price"), it.get("amount")
        if q is not None and u is not None and a is not None and abs(q * u - a) > TOL:
            flags.append("line_amount_mismatch")
            break
    return flags


VALIDATE_JS = r"""
function validate(inv) {
  const TOL = 0.02;
  const flags = [];
  const items = inv.line_items || [];
  const itemsSum = Math.round(items.reduce((s, it) => s + (it.amount || 0), 0) * 100) / 100;
  const subtotal = inv.subtotal, tax = inv.tax || 0, total = inv.total;
  if (!inv.vendor || !inv.invoice_number || total == null) flags.push('missing_required_fields');
  if (!inv.due_date) flags.push('missing_due_date');
  if (subtotal != null && Math.abs(itemsSum - subtotal) > TOL) flags.push('items_sum_mismatch');
  if (total != null && items.length && Math.abs(itemsSum + tax - total) > TOL) flags.push('total_mismatch');
  for (const it of items) {
    if (it.quantity != null && it.unit_price != null && it.amount != null &&
        Math.abs(it.quantity * it.unit_price - it.amount) > TOL) { flags.push('line_amount_mismatch'); break; }
  }
  return flags;
}
"""
