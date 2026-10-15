"""Problem 4: measure the handbook in gpt-6-luna's own tokens, to check the Problem 2 tiktoken estimate.

Sends two requests that are identical except that one includes the handbook, with prompt caching off
and Portkey's response cache bypassed. The difference in the prompt_tokens the API reports is the
handbook (plus its "---" separator, counted separately with tiktoken and subtracted).
Results go into output/cache_test.json under "handbook_token_check".

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\handbook_token_check.py
"""

import json
import sys
import uuid
from pathlib import Path

import tiktoken
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import HANDBOOK, MODEL_NAME, PORTKEY_BASE_URL, PROMPT_FILE, portkey_key, price  # noqa: E402
from tools import OUTPUT_DIR, now_iso  # noqa: E402

SEPARATOR = "\n\n---\n\n"
OUT = OUTPUT_DIR / "cache_test.json"


def main() -> None:
    key = portkey_key()
    client = OpenAI(api_key=key, base_url=PORTKEY_BASE_URL,
                    default_headers={"x-portkey-api-key": key, "x-portkey-cache-force-refresh": "true"})
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    handbook = HANDBOOK.read_text(encoding="utf-8")
    head = f"Request id: {uuid.uuid4().hex}\n\n"
    variants = {"with_handbook": head + prompt + SEPARATOR + handbook, "without_handbook": head + prompt}

    calls = {}
    for name, system in variants.items():
        r = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": "Vendor document path: data/practice_docs/p01_bluehen_quote.html"}],
            max_completion_tokens=5, reasoning_effort="none", prompt_cache_options={"mode": "explicit"},
        )
        u = r.usage.model_dump()
        d = u.get("prompt_tokens_details") or {}
        calls[name] = {
            "model_reported": r.model, "api_usage": u,
            "cost_usd": price(u["prompt_tokens"], d.get("cached_tokens", 0), d.get("cache_write_tokens", 0),
                              u["completion_tokens"]).model_dump(),
        }

    enc = tiktoken.get_encoding("o200k_base")
    diff = calls["with_handbook"]["api_usage"]["prompt_tokens"] - calls["without_handbook"]["api_usage"]["prompt_tokens"]
    sep = len(enc.encode(prompt + SEPARATOR + handbook)) - len(enc.encode(prompt)) - len(enc.encode(handbook))
    tiktoken_count = len(enc.encode(handbook))
    check = {
        "time": now_iso(),
        "method": "Two requests identical except for the handbook; caching off; Portkey response cache bypassed.",
        "calls": calls,
        "prompt_tokens_difference": diff,
        "separator_and_join_tokens_tiktoken": sep,
        "handbook_tokens_gpt_6_luna": diff - sep,
        "handbook_tokens_tiktoken_o200k": tiktoken_count,
        "estimate_error_pct": round((tiktoken_count - (diff - sep)) / (diff - sep) * 100, 2),
    }
    result = json.loads(OUT.read_text(encoding="utf-8"))
    result["handbook_token_check"] = check
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(check, indent=2))


if __name__ == "__main__":
    main()
