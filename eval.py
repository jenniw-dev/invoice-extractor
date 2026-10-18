"""Score the invoice extractor against the labelled test set.

    export GEMINI_API_KEY=...            # never commit this
    python eval.py                       # extract all 30 invoices, then score
    python eval.py --model gemini-3.8-flash   # free tier ~20 req/day: runs over 2 days, cache resumes
    python eval.py --rescore             # score cached predictions only (no API calls)
    python eval.py --mock                # self-test the scorer without an API key

Writes results/report.md and results/summary.json. Uses only the Python standard library.
"""
import argparse, base64, json, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "extractor"))
from spec import PROMPT, SCHEMA, validate  # noqa: E402

TRUTH = json.loads((ROOT / "testdata/ground_truth.json").read_text())
INV_DIR = ROOT / "testdata/invoices"
OUT = ROOT / "results"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

TEXT_FIELDS = ["vendor", "vendor_address", "bill_to", "invoice_number", "invoice_date", "due_date", "currency"]
MONEY_FIELDS = ["subtotal", "tax", "total"]
ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]


# ---------- extraction ----------
def extract(path: Path, model: str, key: str) -> dict:
    mime = "application/pdf" if path.suffix == ".pdf" else "image/jpeg"
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(path.read_bytes()).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(5):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read())
            text = res["candidates"][0]["content"]["parts"][0]["text"]
            usage = res.get("usageMetadata", {})
            return {"data": json.loads(text), "latency_s": round(time.time() - t0, 2),
                    "tokens": usage.get("totalTokenCount")}
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 503) and attempt < 4:
                wait = 2 ** attempt * 5
                print(f"   HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise SystemExit(f"HTTP {e.code} for {path.name}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 4:
                time.sleep(5)
                continue
            raise SystemExit(f"Network error for {path.name}: {e}")


# ---------- scoring ----------
def norm(s):
    return re.sub(r"[^\w]", "", str(s).casefold()) if s is not None else None


def same(field, pred, true):
    if true is None or pred is None:
        return pred in (None, "") and true is None
    if field in MONEY_FIELDS or field in ("quantity", "unit_price", "amount"):
        try:
            return abs(float(pred) - float(true)) <= 0.01
        except (TypeError, ValueError):
            return False
    if field == "tax_rate":
        return abs(float(pred) - float(true)) <= 0.0005
    return norm(pred) == norm(true)


def score(preds: dict) -> dict:
    fields = {f: [0, 0] for f in TEXT_FIELDS + MONEY_FIELDS + ["tax_rate"]}
    item_fields = {f: [0, 0] for f in ITEM_FIELDS}
    cat = [0, 0]
    item_count_ok = 0
    perfect_docs = 0
    flag_tp = flag_fp = flag_fn = 0
    rows, by_source = [], {"pdf": [0, 0], "photo": [0, 0]}

    for name, truth in TRUTH.items():
        p = preds.get(name)
        if p is None:
            continue
        pred = p["data"]
        errors = []
        for f in fields:
            ok = same(f, pred.get(f), truth.get(f))
            if f == "tax_rate" and truth.get(f) == 0 and pred.get(f) in (None, 0):
                ok = True  # "no tax" printed either way
            fields[f][0] += ok
            fields[f][1] += 1
            if not ok:
                errors.append(f"{f}: got {pred.get(f)!r}, want {truth.get(f)!r}")
        ti, pi = truth["line_items"], pred.get("line_items") or []
        item_count_ok += len(ti) == len(pi)
        if len(ti) != len(pi):
            errors.append(f"line_items: got {len(pi)}, want {len(ti)}")
        for t, q in zip(ti, pi):
            for f in ITEM_FIELDS:
                ok = same(f, q.get(f), t.get(f))
                item_fields[f][0] += ok
                item_fields[f][1] += 1
                if not ok:
                    errors.append(f"item.{f}: got {q.get(f)!r}, want {t.get(f)!r}")
            cat[0] += q.get("category") == t["category"]
            cat[1] += 1
        got = set(validate(pred))
        want = set(truth["expected_flags"])
        flag_tp += len(got & want)
        flag_fp += len(got - want)
        flag_fn += len(want - got)
        if got != want:
            errors.append(f"flags: got {sorted(got)}, want {sorted(want)}")
        perfect = not [e for e in errors if not e.startswith("flags")]
        perfect_docs += perfect
        by_source[truth["source"]][0] += perfect
        by_source[truth["source"]][1] += 1
        rows.append({"file": name, "source": truth["source"], "perfect": perfect, "errors": errors,
                     "latency_s": p.get("latency_s"), "tokens": p.get("tokens")})

    total_ok = sum(v[0] for v in fields.values()) + sum(v[0] for v in item_fields.values())
    total_n = sum(v[1] for v in fields.values()) + sum(v[1] for v in item_fields.values())
    lat = [r["latency_s"] for r in rows if r["latency_s"]]
    return {
        "documents": len(rows),
        "field_accuracy": total_ok / total_n if total_n else 0,
        "documents_fully_correct": perfect_docs,
        "by_source": {k: f"{v[0]}/{v[1]}" for k, v in by_source.items()},
        "per_field": {f: f"{v[0]}/{v[1]}" for f, v in {**fields, **{"item." + k: v for k, v in item_fields.items()}}.items()},
        "line_item_count_correct": f"{item_count_ok}/{len(rows)}",
        "category_accuracy": cat[0] / cat[1] if cat[1] else 0,
        "flags": {"caught": flag_tp, "missed": flag_fn, "false_alarms": flag_fp,
                  "expected": sum(len(t["expected_flags"]) for t in TRUTH.values())},
        "avg_latency_s": round(sum(lat) / len(lat), 2) if lat else None,
        "rows": rows,
    }


def report(s: dict, model: str) -> str:
    f = s["flags"]
    lines = [
        f"# Invoice extraction eval: `{model}`", "",
        f"- **Field accuracy:** {s['field_accuracy']:.1%} (header fields + line items, {s['documents']} invoices)",
        f"- **Invoices with every field correct:** {s['documents_fully_correct']}/{s['documents']}"
        f" (PDF {s['by_source']['pdf']}, phone photo {s['by_source']['photo']})",
        f"- **Error detection:** caught {f['caught']}/{f['expected']} planted issues, {f['false_alarms']} false alarms",
        f"- **Line-item count correct:** {s['line_item_count_correct']}",
        f"- **Category accuracy (LLM classification, not printed):** {s['category_accuracy']:.1%}",
        f"- **Avg latency:** {s['avg_latency_s']} s per invoice", "",
        "## Per field", "", "| Field | Correct |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["per_field"].items()], "",
        "## Misses", "",
    ]
    misses = [r for r in s["rows"] if r["errors"]]
    if not misses:
        lines.append("None.")
    for r in misses:
        lines.append(f"**{r['file']}** ({r['source']})")
        lines += [f"- {e}" for e in r["errors"]]
        lines.append("")
    return "\n".join(lines) + "\n"


def mock_predictions() -> dict:
    """Ground truth with a few planted mistakes, to prove the scorer catches them."""
    import copy
    preds = {k: {"data": copy.deepcopy(v), "latency_s": 1.0, "tokens": 0} for k, v in TRUTH.items()}
    preds["inv_03_ol.jpg"]["data"]["vendor"] = "Wrong Vendor"
    preds["inv_14_bw.pdf"]["data"]["total"] = preds["inv_14_bw.pdf"]["data"]["subtotal"] + preds["inv_14_bw.pdf"]["data"]["tax"]
    preds["inv_21_ms.jpg"]["data"]["line_items"] = preds["inv_21_ms.jpg"]["data"]["line_items"][:-1]
    return preds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--only", help="comma-separated file names")
    a = ap.parse_args()

    cache = OUT / "predictions" / a.model
    cache.mkdir(parents=True, exist_ok=True)
    if a.mock:
        preds, model = mock_predictions(), "mock"
    else:
        model, preds = a.model, {}
        key = os.environ.get("GEMINI_API_KEY")
        names = a.only.split(",") if a.only else list(TRUTH)
        for i, name in enumerate(names, 1):
            cp = cache / (name + ".json")
            if cp.exists():
                preds[name] = json.loads(cp.read_text())
                continue
            if a.rescore:
                continue
            if not key:
                raise SystemExit("Set GEMINI_API_KEY first (export GEMINI_API_KEY=...)")
            print(f"[{i}/{len(names)}] {name}")
            preds[name] = extract(INV_DIR / name, model, key)
            cp.write_text(json.dumps(preds[name], indent=2, ensure_ascii=False))
            time.sleep(1)
    s = score(preds)
    OUT.mkdir(exist_ok=True)
    md = report(s, model)
    (OUT / ("report_mock.md" if a.mock else "report.md")).write_text(md)
    if not a.mock:
        (OUT / "summary.json").write_text(json.dumps({k: v for k, v in s.items() if k != "rows"} | {"model": model}, indent=2))
    print(md.split("## Per field")[0])


if __name__ == "__main__":
    main()
