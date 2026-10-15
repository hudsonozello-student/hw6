"""Problem 2: count the tokens in the shop handbook and price it with gpt-6-luna rates.

Offline only. No API calls are made here; Problem 4 checks these numbers
against the usage that real gpt-6-luna runs report.

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\handbook_estimate.py
"""

import json
import math
import re
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent.parent
HANDBOOK = ROOT / "data" / "shop_handbook.md"
PRICES = ROOT / "data" / "prices.json"
OUT = ROOT / "output" / "handbook_estimate.json"

MODEL = "gpt-6-luna"
CALLS = 1_000
CACHE_MIN_TOKENS = 1_024  # OpenAI only caches prompts of at least 1,024 tokens
CACHE_STEP = 128  # cache hits grow in 128-token steps past that


def main():
    text = HANDBOOK.read_text(encoding="utf-8")
    rates = json.loads(PRICES.read_text(encoding="utf-8"))[MODEL]

    o200k = tiktoken.get_encoding("o200k_base")  # GPT-4o / GPT-5 family tokenizer
    cl100k = tiktoken.get_encoding("cl100k_base")  # older GPT-4 tokenizer, for comparison

    tokens = len(o200k.encode(text))
    counts = {
        "o200k_base_tokens": tokens,
        "cl100k_base_tokens": len(cl100k.encode(text)),
        "characters": len(text),
        "bytes_utf8": len(text.encode("utf-8")),
        "words": len(text.split()),
        "lines": text.count("\n") + 1,
    }
    counts["chars_div_4"] = round(counts["characters"] / 4)
    counts["words_x_4_3"] = round(counts["words"] * 4 / 3)

    # Token count per "## " section, to see where the bulk sits.
    sections = []
    for chunk in re.split(r"(?m)^(?=## )", text):
        title = chunk.splitlines()[0].lstrip("# ").strip()
        n = len(o200k.encode(chunk))
        sections.append({"section": title, "tokens": n, "share": round(n / tokens, 4)})

    per_m = 1_000_000
    no_cache_one = tokens * rates["input_per_1m"] / per_m
    write_one = tokens * rates["cache_write_per_1m"] / per_m
    read_one = tokens * rates["cached_input_per_1m"] / per_m

    # Precise version: only whole 128-token blocks of the prefix are cached;
    # the leftover tokens at the end of the handbook bill at the normal rate.
    cacheable = (tokens // CACHE_STEP) * CACHE_STEP if tokens >= CACHE_MIN_TOKENS else 0
    leftover = tokens - cacheable
    precise_read_one = (cacheable * rates["cached_input_per_1m"] + leftover * rates["input_per_1m"]) / per_m
    precise_write_one = (cacheable * rates["cache_write_per_1m"] + leftover * rates["input_per_1m"]) / per_m

    costs = {
        "no_cache": {
            "one_call": no_cache_one,
            "1k_calls": no_cache_one * CALLS,
        },
        "cached_simple": {
            "first_call_cache_write": write_one,
            "later_call_cache_read": read_one,
            "1k_calls": write_one + read_one * (CALLS - 1),
        },
        "cached_128_blocks": {
            "cacheable_tokens": cacheable,
            "leftover_tokens_full_price": leftover,
            "first_call_cache_write": precise_write_one,
            "later_call_cache_read": precise_read_one,
            "1k_calls": precise_write_one + precise_read_one * (CALLS - 1),
        },
    }
    costs["savings_1k_calls"] = costs["no_cache"]["1k_calls"] - costs["cached_simple"]["1k_calls"]
    costs["savings_pct"] = costs["savings_1k_calls"] / costs["no_cache"]["1k_calls"]
    # Number of calls after which caching pays for the 25% write premium.
    costs["break_even_calls"] = 1 + math.ceil(
        (rates["cache_write_per_1m"] - rates["input_per_1m"]) / (rates["input_per_1m"] - rates["cached_input_per_1m"])
    )

    result = {"model": MODEL, "rates_per_1m": rates, "counts": counts, "sections": sections, "costs": costs}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
