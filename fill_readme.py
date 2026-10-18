"""After `python eval.py`, run this to paste the headline numbers into README.md."""
import json, re
from pathlib import Path
s = json.loads(Path("results/summary.json").read_text())
f = s["flags"]
block = (f"Model: `{s['model']}`\n\n"
         f"| Metric | Result |\n|---|---|\n"
         f"| Field accuracy (header + line items) | **{s['field_accuracy']:.1%}** |\n"
         f"| Invoices with every field correct | {s['documents_fully_correct']}/{s['documents']} (PDF {s['by_source']['pdf']}, photo {s['by_source']['photo']}) |\n"
         f"| Planted errors caught | **{f['caught']}/{f['expected']}**, {f['false_alarms']} false alarms |\n"
         f"| Spend category (LLM-assigned) | {s['category_accuracy']:.1%} |\n"
         f"| Avg latency | {s['avg_latency_s']} s / invoice |\n\nFull per-field breakdown and every miss: [results/report.md](results/report.md)")
p = Path("README.md")
p.write_text(re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->",
                    f"<!-- RESULTS:START -->\n{block}\n<!-- RESULTS:END -->", p.read_text(), flags=re.S))
print(block)
