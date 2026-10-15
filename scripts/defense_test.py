"""Problem 6: re-run the 12 practice documents with defenses, and measure each layer on its own.

Runs the agent with all three layers (code, design, prompt), then with each layer alone, on all 12
practice documents. Each answer is scored exactly like Problem 5 (scripts/attack_test.py) and gets its
tokens and dollars. "Before" is the undefended Problem 5 run in output/attack_results.json.
Results go to output/defense_results.json.

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\defense_test.py                   # all + each layer alone
    .\\.venv\\Scripts\\python.exe scripts\\defense_test.py --configs all     # just the full defense
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agent import MODEL_NAME, RATES, USAGE_LOG, parse_defenses, run_desk  # noqa: E402
from attack_test import DOCS, HUMAN_VIEW, print_row, score_run  # noqa: E402
from tools import OUTPUT_DIR, TRAP_LOG, now_iso  # noqa: E402

OUT = OUTPUT_DIR / "defense_results.json"
BEFORE = OUTPUT_DIR / "attack_results.json"
CONFIGS = {"all": "code,design,prompt", "code": "code", "design": "design", "prompt": "prompt"}


def tokens(usage: dict) -> dict:
    return {k: usage[k] for k in ("requests", "prompt_tokens", "cached_tokens", "cache_write_tokens",
                                  "uncached_prompt_tokens", "completion_tokens", "total_tokens")}


def no_cache_cost(usage: dict) -> float:
    """What the run would cost with every input token at the full price: compares layers without cache luck."""
    return round(usage["prompt_tokens"] * RATES["input_per_1m"] / 1e6
                 + usage["completion_tokens"] * RATES["output_per_1m"] / 1e6, 8)


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "documents": n,
        "documents_fooled": [r["document"] for r in rows if r["fooled"]],
        "fields_matched": f"{sum(sum(v['matched'] for v in r['fields'].values()) for r in rows)} of {5 * n}",
        "decisions_matched": f"{sum(r['decision']['matched'] for r in rows)} of {n}",
        "trap_tool_calls": sum(len(r["trap_calls"]) for r in rows),
        "answers_with_strange_text": [r["document"] for r in rows if r["strange_text_in_answer"]],
        "errors": [r["document"] for r in rows if r.get("error")],
        "per_document_average": {
            "requests": round(sum(r["tokens"]["requests"] for r in rows) / n, 2),
            "prompt_tokens": round(sum(r["tokens"]["prompt_tokens"] for r in rows) / n, 1),
            "completion_tokens": round(sum(r["tokens"]["completion_tokens"] for r in rows) / n, 1),
            "cost_usd": round(sum(r["cost_usd"] for r in rows) / n, 8),
            "cost_usd_no_cache": round(sum(r["cost_usd_no_cache"] for r in rows) / n, 8),
        },
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 8),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Problem 6 defense test")
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    args = parser.parse_args()

    views = json.loads(HUMAN_VIEW.read_text(encoding="utf-8"))
    logged = {u["run_id"]: u for u in json.loads(USAGE_LOG.read_text(encoding="utf-8"))}
    saved = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    runs = saved.get("runs", {})
    traps_before = len(json.loads(TRAP_LOG.read_text(encoding="utf-8")))

    for config in args.configs:
        layers = parse_defenses(CONFIGS[config])
        print(f"\n=== defenses: {config} ({', '.join(layers)})")
        rows = []
        for doc in DOCS:
            audit, usage = run_desk(f"data/practice_docs/{doc.name}", cache="on", defenses=layers)
            row = score_run(doc, audit, usage, views)
            u = usage.model_dump(mode="json")
            row.update(defenses=list(layers), tokens=tokens(u), cost_breakdown_usd=u["cost_usd"],
                       cost_usd_no_cache=no_cache_cost(u),
                       defense_report=audit.defense_report.model_dump(mode="json") if audit.defense_report else None)
            rows.append(row)
            print_row(row)
        runs[config] = {"time": now_iso(), "layers": list(layers), "summary": summarize(rows), "documents": rows}

    # Before = the undefended Problem 5 run, with its tokens from the usage log.
    before_rows = json.loads(BEFORE.read_text(encoding="utf-8"))["documents"]
    for r in before_rows:
        u = logged[r["run_id"]]
        r.update(defenses=[], tokens=tokens(u), cost_breakdown_usd=u["cost_usd"], cost_usd_no_cache=no_cache_cost(u))
    before = summarize(before_rows)

    def brief(r: dict) -> dict:
        return {"fooled": r["fooled"], "fields_matched": sum(v["matched"] for v in r["fields"].values()),
                "decision": r["decision"]["agent"], "decision_matched": r["decision"]["matched"],
                "trap_tool_called": r["trap_tool_called"], "strange_text": r["strange_text"],
                "cost_usd": r["cost_usd"], "prompt_tokens": r["tokens"]["prompt_tokens"],
                "completion_tokens": r["tokens"]["completion_tokens"]}

    after = runs.get("all")
    result = {
        "experiment": {"finished": now_iso(), "model": MODEL_NAME, "cache": "on",
                       "before": "undefended Problem 3 agent, Problem 5 run (output/attack_results.json)",
                       "after": "all three defense layers: code, design, prompt",
                       "trap_calls_json_entries_before_and_after_this_run": [traps_before,
                                                                             len(json.loads(TRAP_LOG.read_text(encoding="utf-8")))]},
        # Same shape as output/attack_results.json, for the full defense, plus tokens and dollars per document.
        "summary": after["summary"] if after else None,
        "documents": after["documents"] if after else [],
        "before_after": [{"document": b["document"], "key_decision": b["decision"]["key"], "before": brief(b),
                          **{config: brief(next(r for r in runs[config]["documents"] if r["document"] == b["document"]))
                             for config in CONFIGS if config in runs}}
                         for b in before_rows],
        "before_summary": before,
        "layer_summaries": {config: runs[config]["summary"] for config in CONFIGS if config in runs},
        "runs": runs,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"before": before, **result["layer_summaries"]}, indent=1))


if __name__ == "__main__":
    main()
