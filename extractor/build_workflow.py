"""Generate the importable n8n workflow from spec.py + n8n_code.py.

    python extractor/build_workflow.py   ->  workflow.json
"""
import json, uuid
from pathlib import Path
from spec import CATEGORIES  # noqa: F401  (kept for reference in the workflow notes)
from n8n_code import BUILD_REQUEST_JS, PARSE_VALIDATE_JS, INVOICE_ROW_JS, LINE_ROWS_JS

MODEL = "gemini-3.5-flash-lite"
X = 260  # horizontal spacing


def node(name, type_, version, pos, params, **extra):
    return {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)), "name": name,
            "type": type_, "typeVersion": version, "position": pos, **extra}


def sheet(name, tab, pos):
    return node(name, "n8n-nodes-base.googleSheets", 4.5, pos, {
        "operation": "append",
        "documentId": {"__rl": True, "value": "", "mode": "url"},
        "sheetName": {"__rl": True, "value": tab, "mode": "name"},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {},
    }, retryOnFail=True, maxTries=3, waitBetweenTries=3000)


nodes = [
    node("Upload form", "n8n-nodes-base.formTrigger", 2.2, [0, 0], {
        "formTitle": "Upload invoices",
        "formDescription": "PDF or phone photo. Extracted data is written to the Invoices Google Sheet.",
        "formFields": {"values": [{
            "fieldLabel": "Invoice", "fieldType": "file", "multipleFiles": True,
            "acceptFileTypes": ".pdf, .jpg, .jpeg, .png", "requiredField": True}]},
        "options": {"respondWithOptions": {"values": {
            "formSubmittedText": "Thanks! Your invoices are being processed. Check the Google Sheet in a few seconds."}}},
    }),
    node("Build Gemini request", "n8n-nodes-base.code", 2, [X, 0], {"jsCode": BUILD_REQUEST_JS.strip()}),
    node("Gemini extract", "n8n-nodes-base.httpRequest", 4.2, [2 * X, 0], {
        "method": "POST",
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.body) }}",
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=3, waitBetweenTries=5000, onError="continueRegularOutput",
       notes="Header Auth credential: name = x-goog-api-key, value = your Gemini API key"),
    node("Parse + validate", "n8n-nodes-base.code", 2, [3 * X, 0], {"jsCode": PARSE_VALIDATE_JS.strip()}),
    node("Invoice row", "n8n-nodes-base.code", 2, [4 * X, -120], {"jsCode": INVOICE_ROW_JS}),
    node("Line item rows", "n8n-nodes-base.code", 2, [4 * X, 120], {"jsCode": LINE_ROWS_JS}),
    sheet("Sheets: Invoices", "Invoices", [5 * X, -120]),
    sheet("Sheets: Line Items", "Line Items", [5 * X, 120]),
]


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


connections = {}
for a, b in [("Upload form", "Build Gemini request"), ("Build Gemini request", "Gemini extract"),
             ("Gemini extract", "Parse + validate"), ("Invoice row", "Sheets: Invoices"),
             ("Line item rows", "Sheets: Line Items")]:
    connections.update(link(a, b))
connections["Parse + validate"] = {"main": [[
    {"node": "Invoice row", "type": "main", "index": 0},
    {"node": "Line item rows", "type": "main", "index": 0}]]}

wf = {"name": "Invoice Extractor", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).parent.parent / "workflow.json"
out.write_text(json.dumps(wf, indent=2, ensure_ascii=False))
print("wrote", out, len(nodes), "nodes")
