"""Generate a synthetic, labelled invoice test set.

Every company here is fictional. Ground truth is exactly what is printed on each
document, so extraction accuracy can be scored field by field. Some invoices
contain deliberate arithmetic errors, which the validator is expected to flag.

    python testdata/generate.py      ->  testdata/invoices/*  +  testdata/ground_truth.json
"""
import io, json, random
from datetime import date, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter, ImageEnhance
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

random.seed(42)
OUT = Path(__file__).parent / "invoices"
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.iterdir():
    f.unlink()

F = "/usr/share/fonts/truetype/"
pdfmetrics.registerFont(TTFont("Sans", F + "dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("SansB", F + "dejavu/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Serif", F + "dejavu/DejaVuSerif.ttf"))
pdfmetrics.registerFont(TTFont("SerifB", F + "dejavu/DejaVuSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "dejavu/DejaVuSansMono.ttf"))
pdfmetrics.registerFont(TTFont("Lib", F + "liberation/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("LibB", F + "liberation/LiberationSans-Bold.ttf"))

CATEGORIES = ["Software & Subscriptions", "Office Supplies", "Equipment", "Travel",
              "Meals & Entertainment", "Advertising & Marketing", "Professional Services",
              "Shipping & Logistics", "Rent & Utilities", "Other"]

# (vendor, city line, prefix, [(item, category, (min price, max price))])
VENDORS = [
    ("Northwind Supply Co.", "88 Harbor Rd, Portland, OR 97201", "NW", [
        ("Copy paper, A4, 10 reams", "Office Supplies", (38, 52)),
        ("Toner cartridge, black", "Office Supplies", (60, 95)),
        ("27-inch monitor", "Equipment", (210, 340)),
        ("Desk organiser set", "Office Supplies", (18, 30))]),
    ("Acme Cloud Services", "400 Market St, San Francisco, CA 94105", "AC", [
        ("Cloud hosting, monthly", "Software & Subscriptions", (300, 1800)),
        ("Managed database", "Software & Subscriptions", (150, 600)),
        ("Premium support plan", "Software & Subscriptions", (99, 499)),
        ("Onboarding workshop", "Professional Services", (600, 1500))]),
    ("Harbor Print Studio", "12 Dock Ln, Boston, MA 02110", "HP", [
        ("Business cards, 500", "Advertising & Marketing", (60, 140)),
        ("Trade-show banner", "Advertising & Marketing", (380, 720)),
        ("Flyers, A5, 1000", "Advertising & Marketing", (90, 210))]),
    ("Bluebird Logistics", "7 Freight Way, Newark, NJ 07114", "BL", [
        ("Pallet freight, domestic", "Shipping & Logistics", (220, 900)),
        ("Express courier", "Shipping & Logistics", (25, 90)),
        ("Warehouse storage, monthly", "Rent & Utilities", (400, 1100))]),
    ("Greenleaf Office", "55 Elm St, Austin, TX 78701", "GL", [
        ("Ergonomic chair", "Equipment", (180, 420)),
        ("Notebooks, pack of 12", "Office Supplies", (14, 28)),
        ("Whiteboard markers", "Office Supplies", (8, 19))]),
    ("Maple Street Catering", "301 Maple St, Chicago, IL 60607", "MS", [
        ("Team lunch, 20 guests", "Meals & Entertainment", (380, 720)),
        ("Client dinner", "Meals & Entertainment", (240, 610)),
        ("Coffee service", "Meals & Entertainment", (60, 140))]),
    ("Ledgerline Accounting LLP", "9 Fleet St, London EC4Y 1AA", "LL", [
        ("Quarterly bookkeeping", "Professional Services", (900, 2200)),
        ("VAT return filing", "Professional Services", (300, 650)),
        ("Payroll processing", "Professional Services", (150, 420))]),
    ("Kestrel Travel GmbH", "Friedrichstraße 112, 10117 Berlin", "KT", [
        ("Flight BER-LHR return", "Travel", (180, 520)),
        ("Hotel, 3 nights", "Travel", (330, 780)),
        ("Airport transfer", "Travel", (40, 95))]),
    ("Pixelcraft Software", "220 King St W, Toronto, ON M5H 3T4", "PX", [
        ("Design suite licence, annual", "Software & Subscriptions", (480, 1200)),
        ("Additional seat", "Software & Subscriptions", (60, 180)),
        ("Custom template pack", "Advertising & Marketing", (150, 400))]),
    ("Brightwater Utilities", "1 Reservoir Ave, Denver, CO 80202", "BW", [
        ("Electricity, September", "Rent & Utilities", (280, 760)),
        ("Water and sewer", "Rent & Utilities", (60, 190))]),
    ("Oakline Legal Partners", "18 Rue de Rivoli, 75004 Paris", "OL", [
        ("Contract review", "Professional Services", (700, 1900)),
        ("Trademark filing", "Professional Services", (450, 900))]),
    ("Summit Media Group", "640 Peachtree St, Atlanta, GA 30308", "SM", [
        ("Social ads management", "Advertising & Marketing", (800, 2400)),
        ("Video production, 30s", "Advertising & Marketing", (1200, 3600)),
        ("Stock footage licence", "Advertising & Marketing", (70, 210))]),
]
CURRENCIES = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "CA$"}
VENDOR_CURRENCY = {"LL": "GBP", "KT": "EUR", "OL": "EUR", "PX": "CAD"}
DATE_FORMATS = ["%Y-%m-%d", "%b %d, %Y", "%d/%m/%Y", "%B %d, %Y", "%d %b %Y"]  # index 2 replaced per currency
BILL_TO = ["Fernway Studio Ltd.", "Copperleaf Analytics Inc.", "Tidewater Goods Co."]


def money(v, sym):
    return f"{sym}{v:,.2f}"


ORDER = (VENDORS * 3)[:30]
random.shuffle(ORDER)  # every vendor appears 2-3 times, so all categories are covered


def make_invoice(i):
    vendor, addr, prefix, catalog = ORDER[i]
    cur = VENDOR_CURRENCY.get(prefix, "USD")
    issued = date(2026, 8, 1) + timedelta(days=random.randint(0, 60))
    has_due = random.random() > 0.2
    n = random.randint(1, min(4, len(catalog)))
    items = []
    for desc, cat, (lo, hi) in random.sample(catalog, n):
        qty = random.choice([1, 1, 1, 2, 3, 4, 5, 10]) if hi < 300 else 1
        unit = round(random.uniform(lo, hi), random.choice([0, 2]))
        items.append({"description": desc, "quantity": qty, "unit_price": unit,
                      "amount": round(qty * unit, 2), "category": cat})
    subtotal = round(sum(x["amount"] for x in items), 2)
    tax_rate = {"GBP": 0.20, "EUR": 0.19 if prefix == "KT" else 0.20, "CAD": 0.13}.get(cur, random.choice([0, 0.0625, 0.08, 0.0875]))
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax, 2)
    inv = {"vendor": vendor, "vendor_address": addr, "bill_to": random.choice(BILL_TO),
           "invoice_number": f"{prefix}-{random.randint(1000, 99999)}",
           "invoice_date": issued.isoformat(),
           "due_date": (issued + timedelta(days=random.choice([14, 30, 45]))).isoformat() if has_due else None,
           "currency": cur, "line_items": items, "subtotal": subtotal,
           "tax_rate": tax_rate, "tax": tax, "total": total, "expected_flags": []}
    # Deliberate errors on ~1 in 5 invoices (what is PRINTED is wrong; ground truth = printed values)
    err = random.random()
    if i % 5 == 3:
        if err < 0.5:
            inv["subtotal"] = round(subtotal + random.choice([90, 180, 100, 9]), 2)  # transposed / mistyped subtotal
            inv["expected_flags"].append("items_sum_mismatch")
        else:
            inv["total"] = round(total + random.choice([10, 50, 1]), 2)
            inv["expected_flags"].append("total_mismatch")
    if not has_due:
        inv["expected_flags"].append("missing_due_date")
    return inv


def draw(inv, path, style):
    sym = CURRENCIES[inv["currency"]]
    # numeric dates follow local convention, so the test never contains a truly ambiguous date
    fmt = random.choice(DATE_FORMATS[:2] + DATE_FORMATS[3:] + (["%m/%d/%Y"] if inv["currency"] == "USD" else ["%d/%m/%Y"]))
    d = lambda iso: date.fromisoformat(iso).strftime(fmt)
    size = LETTER if inv["currency"] in ("USD", "CAD") else A4
    W, H = size
    c = canvas.Canvas(str(path), pagesize=size)
    reg, bold = {"classic": ("Serif", "SerifB"), "modern": ("Lib", "LibB"), "minimal": ("Mono", "Mono")}[style]
    y = H - 60
    if style == "modern":
        c.setFillColorRGB(0.12, 0.30, 0.45); c.rect(0, H - 110, W, 110, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1); c.setFont(bold, 22); c.drawString(40, H - 60, inv["vendor"])
        c.setFont(reg, 10); c.drawString(40, H - 80, inv["vendor_address"])
        c.setFont(bold, 26); c.drawRightString(W - 40, H - 62, "INVOICE")
        c.setFillColorRGB(0, 0, 0); y = H - 150
    else:
        c.setFont(bold, 18 if style == "classic" else 14); c.drawString(50, y, inv["vendor"])
        c.setFont(reg, 9); c.drawString(50, y - 16, inv["vendor_address"])
        c.setFont(bold, 20 if style == "classic" else 14)
        c.drawRightString(W - 50, y, "Invoice" if style == "classic" else "TAX INVOICE")
        y -= 60
    c.setFont(reg, 10)
    meta = [("Invoice No.", inv["invoice_number"]), ("Date", d(inv["invoice_date"]))]
    if inv["due_date"]:
        meta.append(("Due", d(inv["due_date"])))
    meta.append(("Currency", inv["currency"]))
    for k, v in meta:
        c.drawRightString(W - 160, y, k + ":"); c.drawString(W - 150, y, v); y -= 15
    c.setFont(bold, 10); c.drawString(50, y + 15 * len(meta), "Bill to")
    c.setFont(reg, 10); c.drawString(50, y + 15 * len(meta) - 15, inv["bill_to"])
    y -= 30
    c.setFont(bold, 10)
    cols = [50, W - 260, W - 180, W - 50]
    c.drawString(cols[0], y, "Description"); c.drawRightString(cols[1], y, "Qty")
    c.drawRightString(cols[2], y, "Unit price"); c.drawRightString(cols[3], y, "Amount")
    c.line(50, y - 5, W - 50, y - 5); y -= 22
    c.setFont(reg, 10)
    for it in inv["line_items"]:
        c.drawString(cols[0], y, it["description"]); c.drawRightString(cols[1], y, str(it["quantity"]))
        c.drawRightString(cols[2], y, money(it["unit_price"], sym)); c.drawRightString(cols[3], y, money(it["amount"], sym))
        y -= 18
    c.line(W - 300, y, W - 50, y); y -= 20
    rate = f"Tax ({inv['tax_rate'] * 100:g}%)" if inv["tax_rate"] else "Tax"
    for k, v, b in [("Subtotal", inv["subtotal"], False), (rate, inv["tax"], False), ("Total due", inv["total"], True)]:
        c.setFont(bold if b else reg, 12 if b else 10)
        c.drawRightString(cols[2], y, k); c.drawRightString(cols[3], y, money(v, sym)); y -= 18
    c.setFont(reg, 8); c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(50, 50, "Fictional invoice generated for software testing. Not a real transaction.")
    c.save()


def photo(pdf_path, img_path):
    """Turn a PDF page into a phone-photo-like image: tilt, shadow, blur, noise, JPEG."""
    pix = pymupdf.open(pdf_path)[0].get_pixmap(dpi=130)
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    bg = Image.new("RGB", (im.width + 160, im.height + 160), (int(random.uniform(90, 140)),) * 3)
    bg.paste(im, (80, 80))
    im = bg.rotate(random.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=(60, 60, 60), expand=False)
    im = ImageEnhance.Brightness(im).enhance(random.uniform(0.75, 1.0))
    im = ImageEnhance.Contrast(im).enhance(random.uniform(0.8, 1.0))
    im = im.filter(ImageFilter.GaussianBlur(random.uniform(0.4, 1.1)))
    noise = Image.effect_noise(im.size, random.uniform(8, 18)).convert("RGB")
    im = Image.blend(im, noise, 0.06)
    im.save(img_path, quality=random.randint(55, 80))


truth = {}
styles = ["classic", "modern", "minimal"]
for i in range(30):
    inv = make_invoice(i)
    style = styles[i % 3]
    stem = f"inv_{i + 1:02d}_{inv['invoice_number'].split('-')[0].lower()}"
    pdf = OUT / f"{stem}.pdf"
    draw(inv, pdf, style)
    if i % 3 == 2:  # every third invoice becomes a phone photo
        img = OUT / f"{stem}.jpg"
        photo(pdf, img); pdf.unlink(); name = img.name
    else:
        name = pdf.name
    inv["layout"] = style
    inv["source"] = "photo" if name.endswith(".jpg") else "pdf"
    truth[name] = inv

json.dump(truth, open(Path(__file__).parent / "ground_truth.json", "w"), indent=2, ensure_ascii=False)
flags = sum(bool([f for f in t["expected_flags"] if f != "missing_due_date"]) for t in truth.values())
cats = {}
for t in truth.values():
    for it in t["line_items"]:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
print(f"{len(truth)} invoices ({sum(t['source'] == 'photo' for t in truth.values())} photos), "
      f"{sum(len(t['line_items']) for t in truth.values())} line items, {flags} with arithmetic errors")
print("currencies:", sorted({t['currency'] for t in truth.values()}))
print("categories:", cats)
