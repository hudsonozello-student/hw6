"""Problem 8: run the final defended agent on the 10 exam documents and write output/exam_results.json.

Maximum defenses (code + design + prompt). One entry per file, saved exactly as the agent returns it
(no hand-editing). The entry fields are the ones the grader asked for. A companion file,
output/exam_defense_detail.json, keeps what each defense layer did per document (what the code layer
removed, what the reader flagged) as evidence, without touching the graded fields.

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\exam_run.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import ALL_LAYERS, run_desk  # noqa: E402
from tools import OUTPUT_DIR, now_iso  # noqa: E402

EXAM_DIR = ROOT / "data" / "exam_docs"
OUT = OUTPUT_DIR / "exam_results.json"
DETAIL = OUTPUT_DIR / "exam_defense_detail.json"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    results, detail = [], []
    for doc in sorted(EXAM_DIR.iterdir()):
        audit, usage = run_desk(f"data/exam_docs/{doc.name}", cache="on", defenses=ALL_LAYERS)
        a = audit.final_answer
        results.append({
            "file": doc.name,
            "vendor": a.vendor if a else None,
            "sku": a.sku if a else None,
            "unit_price": a.unit_price if a else None,
            "lead_time_days": a.lead_time_days if a else None,
            "min_order": a.min_order if a else None,
            "decision": a.decision if a else None,
            "reason": a.reason if a else None,
            "trap_tool_called": audit.trap_calls > 0,
            "input_tokens": usage.prompt_tokens,
            "cached_tokens": usage.cached_tokens,
            "output_tokens": usage.completion_tokens,
            "cost_usd": round(usage.cost_usd.total, 8),
        })
        report = audit.defense_report
        detail.append({
            "file": doc.name, "run_id": audit.run_id, "defenses": audit.defenses,
            "code_layer_removed": [{"text": r.text, "why": r.why} for r in (report.removed_hidden_text if report else [])],
            "invisible_characters_removed": report.invisible_characters_removed if report else 0,
            "reader_flagged_suspicious": report.suspicious_text if report else [],
            "checks": [{"check": c.check, "passed": c.passed, "detail": c.detail} for c in (report.checks if report else [])],
            "error": audit.error,
        })
        r = results[-1]
        flags = []
        if detail[-1]["code_layer_removed"]:
            flags.append(f"code removed {len(detail[-1]['code_layer_removed'])} hidden piece(s)")
        if r["trap_tool_called"]:
            flags.append("TRAP TOOL CALLED")
        if detail[-1]["reader_flagged_suspicious"]:
            flags.append(f"{len(detail[-1]['reader_flagged_suspicious'])} suspicious quote(s)")
        print(f"{doc.name:22} {r['vendor'] or '-':26} {r['sku'] or '-':10} ${r['unit_price'] or 0:>7} "
              f"{str(r['lead_time_days']):>4}d min{str(r['min_order']):>5} {r['decision'] or 'ERROR':16} "
              f"${r['cost_usd']:.6f}  {'; '.join(flags)}")

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DETAIL.write_text(json.dumps({"finished": now_iso(), "model": "gpt-6-luna", "defenses": list(ALL_LAYERS),
                                  "documents": detail}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    recs = sum(r["decision"] == "recommend" for r in results)
    print(f"\n{len(results)} files: {recs} recommend, {len(results) - recs} do_not_recommend, "
          f"{sum(r['trap_tool_called'] for r in results)} trap calls, "
          f"total ${sum(r['cost_usd'] for r in results):.6f}")
    print("wrote output/exam_results.json and output/exam_defense_detail.json")


if __name__ == "__main__":
    main()
