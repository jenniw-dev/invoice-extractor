"""JavaScript bodies for the n8n Code nodes. Kept here so they can be unit-tested with node."""
import json
from spec import PROMPT, SCHEMA, VALIDATE_JS

BUILD_REQUEST_JS = """
// Turns each uploaded file into a Gemini generateContent request body.
const PROMPT = %s;
const SCHEMA = %s;
const out = [];
for (let i = 0; i < $input.all().length; i++) {
  const item = $input.all()[i];
  const keys = Object.keys(item.binary || {});
  if (!keys.length) throw new Error('No file found on item ' + i);
  for (const key of keys) {   // the upload form allows several files at once
    const bin = item.binary[key];
    const buf = await this.helpers.getBinaryDataBuffer(i, key);
    const mime = bin.mimeType && bin.mimeType !== 'application/octet-stream'
      ? bin.mimeType
      : (/\\.pdf$/i.test(bin.fileName || '') ? 'application/pdf' : 'image/jpeg');
    out.push({ json: {
      file_name: bin.fileName || key,
      body: {
        contents: [{ parts: [
          { inline_data: { mime_type: mime, data: buf.toString('base64') } },
          { text: PROMPT },
        ] }],
        generationConfig: { temperature: 0, responseMimeType: 'application/json', responseSchema: SCHEMA },
      },
    } });
  }
}
return out;
""" % (json.dumps(PROMPT), json.dumps(SCHEMA))

PARSE_VALIDATE_JS = VALIDATE_JS + """
// Parses Gemini's JSON, runs deterministic checks, and shapes rows for Google Sheets.
const requests = $('Build Gemini request').all();
return $input.all().map((item, i) => {
  const fileName = (requests[i] && requests[i].json.file_name) || 'unknown';
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
  let inv = null, error = '';
  try {
    const text = item.json.candidates[0].content.parts[0].text;
    inv = JSON.parse(text);
  } catch (e) {
    error = item.json.error ? JSON.stringify(item.json.error).slice(0, 200) : 'Could not read model output';
  }
  if (!inv) {
    return { json: { invoice: { processed_at_utc: now, file: fileName, status: 'Extraction failed', issues: error }, lines: [] } };
  }
  const items = inv.line_items || [];
  const itemsSum = Math.round(items.reduce((s, it) => s + (it.amount || 0), 0) * 100) / 100;
  const flags = validate(inv);
  const invoice = {
    processed_at_utc: now,
    file: fileName,
    status: flags.length ? 'Needs review' : 'OK',
    issues: flags.join(', '),
    vendor: inv.vendor,
    invoice_number: inv.invoice_number,
    invoice_date: inv.invoice_date,
    due_date: inv.due_date || '',
    currency: inv.currency,
    subtotal: inv.subtotal,
    tax_rate: inv.tax_rate,
    tax: inv.tax,
    total: inv.total,
    line_items_sum: itemsSum,
    line_item_count: items.length,
    bill_to: inv.bill_to,
    vendor_address: inv.vendor_address,
  };
  const lines = items.map((it, n) => ({
    invoice_number: inv.invoice_number,
    vendor: inv.vendor,
    invoice_date: inv.invoice_date,
    line: n + 1,
    description: it.description,
    category: it.category,
    quantity: it.quantity,
    unit_price: it.unit_price,
    amount: it.amount,
    currency: inv.currency,
  }));
  return { json: { invoice, lines } };
});
"""

INVOICE_ROW_JS = "return $input.all().map(i => ({ json: i.json.invoice }));"
LINE_ROWS_JS = "return $input.all().flatMap(i => (i.json.lines || []).map(l => ({ json: l })));"
