"""Problem 4: run the vendor desk on all 12 practice documents with and without prompt caching.

with_cache:    the prompt + handbook is the same on every call, with an explicit cache breakpoint after it and
               one shared prompt_cache_key (a fresh batch id at the top makes the first call start cold).
without_cache: prompt caching switched off, plus a new random id at the top of every request, so no request
               can reuse a cached prefix.

Every model call goes to output/cache_test.json with the setup, the document, the raw token counts the
API reported, and its cost at data/prices.json rates. The script then checks the API's own numbers:
any without_cache call that shows cached tokens fails the check.

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\cache_test.py
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import RATES, USAGE_LOG, run_desk  # noqa: E402
from tools import OUTPUT_DIR, now_iso  # noqa: E402

DOCS = sorted((ROOT / "data" / "practice_docs").iterdir())
KEY = {row["file"]: row for row in json.loads((ROOT / "data" / "practice_key.json").read_text(encoding="utf-8"))}
FIELDS = ["vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision"]
SETUPS = {"with_cache": "on", "without_cache": "off"}
OUT = OUTPUT_DIR / "cache_test.json"
TOKEN_FIELDS = ["prompt_tokens", "cached_tokens", "cache_write_tokens", "completion_tokens", "reasoning_tokens"]
HANDBOOK_TOKENS = json.loads((OUTPUT_DIR / "handbook_estimate.json").read_text(encoding="utf-8"))["counts"][
    "o200k_base_tokens"]


def api_cached(call: dict) -> int:
    return call["api_usage"].get("prompt_tokens_details", {}).get("cached_tokens", 0)


def verify(calls: list[dict]) -> dict:
    """Prove each setup did what it claims, using the raw usage blocks the API sent back."""
    without = [c for c in calls if c["setup"] == "without_cache"]
    with_ = [c for c in calls if c["setup"] == "with_cache"]
    checks = {
        "every_call_has_raw_api_usage": all(c["api_usage"] for c in calls),
        "logged_counts_match_raw_api_usage": all(
            c["prompt_tokens"] == c["api_usage"].get("prompt_tokens")
            and c["completion_tokens"] == c["api_usage"].get("completion_tokens")
            and c["cached_tokens"] == api_cached(c) for c in calls),
        "every_call_answered_by_gpt_6_luna": all((c["model_reported"] or "").startswith("gpt-6-luna") for c in calls),
        "without_cache_calls_with_cached_tokens": [f'{c["document"]} request {c["request"]}' for c in without
                                                   if api_cached(c) > 0],
        "without_cache_cache_write_tokens": sum(c["cache_write_tokens"] for c in without),
        "with_cache_first_call": {"cached_tokens": api_cached(with_[0]),
                                  "cache_write_tokens": with_[0]["cache_write_tokens"]} if with_ else None,
        "with_cache_later_calls": len(with_) - 1,
        "with_cache_later_calls_reading_cache": sum(1 for c in with_[1:] if api_cached(c) > 0),
        "with_cache_misses": [f'{c["document"]} request {c["request"]}' for c in with_[1:] if api_cached(c) == 0],
        # A hit should cover at least the whole handbook (10,058 tokens, Problem 2) plus the prompt before it.
        "with_cache_hits_cover_handbook": all(api_cached(c) >= HANDBOOK_TOKENS for c in with_ if api_cached(c)),
        # A replayed answer would repeat an earlier call's latency numbers; fresh model calls never do.
        "every_call_fresh_from_model": len({json.dumps(c["api_usage"].get("latency_checkpoint"), sort_keys=True)
                                            for c in calls}) == len(calls),
        "portkey_response_cache_hits": sum(1 for c in calls if (c.get("route") or {}).get("x-portkey-cache-status")
                                           == "HIT"),
    }
    later = checks["with_cache_later_calls"]
    checks["with_cache_hit_rate_pct"] = round(checks["with_cache_later_calls_reading_cache"] / later * 100, 1) \
        if later > 0 else None
    # without_cache counts only if nothing was read from (or written to) any cache.
    checks["without_cache_valid"] = (not checks["without_cache_calls_with_cached_tokens"]
                                     and checks["without_cache_cache_write_tokens"] == 0)
    # with_cache counts if later calls really read the handbook back from the cache.
    checks["with_cache_valid"] = checks["with_cache_later_calls_reading_cache"] > 0 \
        and checks["with_cache_hits_cover_handbook"]
    return checks


def summarize(calls: list[dict], runs: list[dict]) -> dict:
    summary = {}
    for setup in SETUPS:
        sc = [c for c in calls if c["setup"] == setup]
        sr = [r for r in runs if r["setup"] == setup]
        total = sum(c["cost_usd"]["total"] for c in sc)
        summary[setup] = {
            "documents": len(sr),
            "calls": len(sc),
            **{t: sum(c[t] for c in sc) for t in TOKEN_FIELDS},
            "uncached_prompt_tokens": sum(c["prompt_tokens"] - c["cached_tokens"] - c["cache_write_tokens"] for c in sc),
            "cost_usd": {part: round(sum(c["cost_usd"][part] for c in sc), 8)
                         for part in ["uncached_input", "cached_input", "cache_write", "output", "total"]},
            "cost_per_document_usd": round(total / len(sr), 8),
            "cost_per_call_usd": round(total / len(sc), 8),
            "fields_correct": sum(r["fields_correct"] for r in sr),
            "fields_checked": len(FIELDS) * len(sr),
            "trap_calls": sum(r["trap_calls"] for r in sr),
        }
    w, wo = summary["with_cache"]["cost_usd"]["total"], summary["without_cache"]["cost_usd"]["total"]
    summary["savings_usd"] = round(wo - w, 8)
    summary["savings_pct"] = round((wo - w) / wo * 100, 2)
    return summary


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Problem 4 cache test")
    parser.add_argument("--setups", nargs="+", choices=list(SETUPS), default=list(SETUPS),
                        help="setups to run now; any other setup keeps its results from output/cache_test.json")
    parser.add_argument("--summarize-only", action="store_true",
                        help="make no API calls; recompute verification and summary for output/cache_test.json")
    args = parser.parse_args()

    if args.summarize_only:
        result = json.loads(OUT.read_text(encoding="utf-8"))
        result["verification"] = verify(result["calls"])
        result["summary"] = summarize(result["calls"], result["runs"])
        OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"verification": result["verification"], "summary": result["summary"]}, indent=2))
        return

    batch = f"cache-test-{uuid.uuid4().hex[:8]}"
    started = now_iso()
    calls, runs, run_times = [], [], {}
    if OUT.exists():  # keep the setups we are not rerunning
        old = json.loads(OUT.read_text(encoding="utf-8"))
        logged = {u["run_id"]: u["time"] for u in json.loads(USAGE_LOG.read_text(encoding="utf-8"))}
        for setup in SETUPS:
            if setup not in args.setups:
                calls += [c for c in old["calls"] if c["setup"] == setup]
                runs += [r for r in old["runs"] if r["setup"] == setup]
                run_times[setup] = min(logged[r["run_id"]] for r in runs if r["setup"] == setup)
    for setup, mode in SETUPS.items():
        if setup not in args.setups:
            continue
        run_times[setup] = now_iso()
        for doc in DOCS:
            audit, usage = run_desk(f"data/practice_docs/{doc.name}", cache=mode, batch=batch,
                                    defenses=())  # Problem 4 measured the undefended agent
            answer = audit.final_answer.model_dump() if audit.final_answer else {}
            expected = KEY[doc.name]
            runs.append({
                "setup": setup, "document": doc.name, "run_id": usage.run_id, "requests": usage.requests,
                "cost_usd": usage.cost_usd.total, "answer": answer or None, "error": audit.error,
                "fields_correct": sum(answer.get(f) == expected[f] for f in FIELDS),
                "wrong_fields": [f for f in FIELDS if answer.get(f) != expected[f]],
                "tools": [c.tool for c in audit.tool_calls], "trap_calls": audit.trap_calls,
            })
            for n, r in enumerate(usage.per_request, 1):
                calls.append({"setup": setup, "document": doc.name, "run_id": usage.run_id, "request": n,
                              **r.model_dump(mode="json")})
            routes = " ".join(f'{(r.route.get("x-portkey-last-used-option-index") or "?").split(".")[-1]}/'
                              f'{(r.route.get("azureml-model-session") or "?")[-8:]}' for r in usage.per_request)
            print(f"{setup:13} {doc.name:30} requests={usage.requests} in={usage.prompt_tokens:6} "
                  f"cached={usage.cached_tokens:6} write={usage.cache_write_tokens:6} out={usage.completion_tokens:4} "
                  f"${usage.cost_usd.total:.6f} correct={runs[-1]['fields_correct']}/6 traps={audit.trap_calls} "
                  f"route={routes}")

    calls.sort(key=lambda c: list(SETUPS).index(c["setup"]))
    runs.sort(key=lambda r: list(SETUPS).index(r["setup"]))
    result = {
        "experiment": {
            "started": started, "finished": now_iso(), "run_times": run_times, "model": "gpt-6-luna",
            "rates_per_1m": RATES, "batch_id": batch, "documents": [d.name for d in DOCS],
            "setups": {
                "with_cache": "Static prompt + handbook with an explicit prompt_cache_breakpoint after it, one shared "
                              "prompt_cache_key, and first line 'Batch id: <batch_id>' (fresh for this test, so the "
                              "first call starts cold).",
                "without_cache": "prompt_cache_options.mode='explicit' with no breakpoints (caching off), and first "
                                 "line 'Request id: <random>', new on every model request.",
            },
            "earlier_attempts": {
                "output/cache_test_attempt1.json": "implicit caching; only 11 of 23 with-cache calls read the "
                                                   "cache, and the random-id without-cache calls still paid for "
                                                   "cache writes",
                "output/cache_test_attempt2.json": "current settings, but no routing headers recorded; 9 of 23 "
                                                   "with-cache calls read the cache",
            },
        },
        "verification": verify(calls),
        "summary": summarize(calls, runs),
        "runs": runs,
        "calls": calls,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"verification": result["verification"], "summary": result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
