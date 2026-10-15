# Problem 4: With and without cached tokens

The vendor desk agent ran on all 12 practice documents in two setups, with the handbook served from the prompt cache and with caching switched off. Every model call is in [`cache_test.json`](cache_test.json). That includes the setup, the document, the raw `usage` block the API returned, and dollars at `data/prices.json` rates.

**Bottom line**

| | With cache | Without cache |
|---|---:|---:|
| Total, 12 documents (24 model calls) | **$0.011422** | **$0.027257** |
| Per document | **$0.000952** | **$0.002271** |
| Saved by caching | **$0.015835, or 58.1%** | |
| 1,000 docs/day for 30 days | **$28.55** as measured (≈ $26.02 at steady state) | **$68.14** |

The API's own counts back up both setups:
- **Without cache:** 0 cached tokens and 0 cache-write tokens on all 24 calls.
- **With cache:** 18 of the 23 calls after the first read the full handbook back from cache, 10,795–10,816 tokens per hit.

---

## How the two setups were built

Both setups use the same agent, prompt, handbook, tools, and model (`gpt-6-luna`, reported by the API as `gpt-6-luna-2026-09-22` on every call). Each document takes **2 model calls**: the agent calls `read_document`, then sends a second request to give its answer. Run them with `python agent.py --doc <file> --cache on|off`, or all 24 runs with `scripts/cache_test.py`.

| | With cache (`--cache on`) | Without cache (`--cache off`) |
|---|---|---|
| System prompt | `prompt.md` + handbook, identical on every call. The test batch adds one fixed first line, `Batch id: cache-test-062271c0`, so the first call starts with a cold cache instead of reusing earlier runs. | A new `Request id: <random>` first line on **every request**, so no request starts with text the model has seen before. |
| Cache settings sent to the API | An explicit `prompt_cache_breakpoint` right after the handbook, and one shared `prompt_cache_key` so all calls are routed to the same cache. | `prompt_cache_options: {"mode": "explicit"}` with no breakpoints. In this mode the API does not cache at all: no reads, no writes. |
| Portkey's own response cache | Bypassed (`x-portkey-cache-force-refresh`). Every call reaches the model. | Every request is unique, so Portkey's cache cannot match it (confirmed below). |

### Proof from the API's token counts

`scripts/cache_test.py` checks the raw `usage` blocks the API sent back (`verification` in `cache_test.json`):

| Check | Result |
|---|---|
| Every call has the raw API `usage` block saved | ✅ 48 of 48 |
| Logged counts match the raw API numbers | ✅ |
| Every call answered by gpt-6-luna | ✅ 48 of 48 (`gpt-6-luna-2026-09-22`) |
| **Without cache: calls showing cached tokens** | ✅ **0 of 24** (`cached_tokens` = 0 every time) |
| **Without cache: cache-write tokens** | ✅ **0** (nothing stored either) |
| With cache: first call | Cold: 0 cached, 10,813 tokens written to the cache |
| **With cache: later calls reading the cache** | **18 of 23 (78.3%)** |
| With cache: every hit covers the whole handbook | ✅ each hit read 10,795–10,816 tokens, more than the handbook's 10,058 |
| Fresh model answers, nothing replayed | ✅ all 48 calls have different server latency numbers |
| Portkey response-cache hits | ✅ 0 |

Both setups did what they claim. Caching off means zero cached tokens on every call. Caching on means the handbook was read back from cache on 18 of 23 calls. The 5 misses are explained in section 4.

---

## 1. Total cost, cost per document, and percent saved

| | With cache | Without cache |
|---|---:|---:|
| Model calls | 24 | 24 |
| Input (prompt) tokens | 264,806 | 265,080 |
| … read from cache ($0.01/1M) | 194,484 | 0 |
| … written to cache ($0.125/1M) | 67,298 | 0 |
| … normal input ($0.10/1M) | 3,024 | 265,080 |
| Output tokens ($0.50/1M) | 1,524 | 1,497 |
| Cost: cached input | $0.001945 | $0 |
| Cost: cache writes | $0.008412 | $0 |
| Cost: normal input | $0.000302 | $0.026508 |
| Cost: output | $0.000762 | $0.000749 |
| **Total (12 documents)** | **$0.011422** | **$0.027257** |
| **Per document** | **$0.000952** | **$0.002271** |
| Per model call | $0.000476 | $0.001136 |

**Percent saved:** ($0.027257 − $0.011422) ÷ $0.027257 = **58.1%** ($0.015835 saved across 12 documents).

Example math for a typical request-1 call that hits the cache: 10,795 cached × $0.01/1M + 19 written × $0.125/1M + 126 normal × $0.10/1M + 27 output × $0.50/1M ≈ $0.000137. A typical request 1 without cache: 10,951 × $0.10/1M + 27 × $0.50/1M ≈ $0.001109.

### Per document

"hit" means tokens read from the cache. "write" means a miss that stored the prefix at the write price. Request 1 reads the document, and request 2 gives the answer.

| Document | With cache: request 1 / request 2 | With cache cost | Without cache: input tokens | Without cache cost | Saved |
|---|---|---:|---|---:|---:|
| `p01_bluehen_quote.html` | write 10,813 (cold start) / hit 10,813 | $0.001575 | 22,079 (0 cached) | $0.002272 | 31% |
| `p02_elmcity_quote.html` | write 10,814 / hit 10,814 | $0.001575 | 22,085 (0 cached) | $0.002279 | 31% |
| `p03_ivyprint_catalog.html` | hit 10,795 / write 10,995 | $0.001565 | 22,084 (0 cached) | $0.002264 | 31% |
| `p04_harborstitch_quote.html` | write 10,816 / hit 10,816 | $0.001575 | 22,079 (0 cached) | $0.002280 | 31% |
| `p05_maplemills_quote.pdf` | hit 10,795 / hit 10,814 | $0.000313 | 22,051 (0 cached) | $0.002256 | 86% |
| `p06_qtextile_quote.pdf` | hit 10,795 / hit 10,814 | $0.000330 | 22,099 (0 cached) | $0.002272 | 85% |
| `p07_longwharf_quote.pdf` | hit 10,795 / hit 10,814 | $0.000340 | 22,066 (0 cached) | $0.002265 | 85% |
| `p08_chapelst_email.eml` | hit 10,795 / hit 10,815 | $0.000337 | 22,088 (0 cached) | $0.002278 | 85% |
| `p09_westville_email.eml` | hit 10,795 / write 11,139 | $0.001581 | 22,226 (0 cached) | $0.002274 | 30% |
| `p10_eastrock_email.eml` | hit 10,795 / hit 10,815 | $0.000341 | 22,110 (0 cached) | $0.002281 | 85% |
| `p11_yorkst_quote.html` | hit 10,795 / hit 10,814 | $0.000316 | 22,045 (0 cached) | $0.002259 | 86% |
| `p12_bluehen_quote.pdf` | hit 10,795 / write 10,978 | $0.001575 | 22,068 (0 cached) | $0.002276 | 31% |

A document where both calls hit costs about **$0.00033**, 85% less than without cache. A document with one miss costs about **$0.00157**, only 31% less. The misses decide the total.

Answers didn't change with caching. Both setups got 67 of 72 fields right, and the same three documents had errors in both: p02, p07, and p12. Each one hides text meant to change the agent's answer, and defenses come in a later problem. No trap tool was called (`trap_calls.json` is still `[]`).

---

## 2. How the real numbers compare to the Problem 2 estimate

| | Problem 2 estimate | Real (Problem 4) | Verdict |
|---|---|---|---|
| Handbook size | 10,058 tokens (tiktoken `o200k_base`) | **10,058 tokens** in gpt-6-luna's own count* | **Exact match** |
| Input tokens per model call | 10,058 (handbook alone) | ~10,950 (request 1), ~11,140 (request 2) | Handbook is ~91% of each call. The rest is `prompt.md` (434), tool and answer schemas, the user message, and in request 2 the document text. |
| Model calls per document | Priced per call | **2 per document** | The handbook is paid twice per document. |
| One call, no cache | $0.0010058 (handbook only) | $0.001109 (request 1), $0.001163 (request 2) | Handbook = 88.6% of the real no-cache bill. |
| One call, cache hit | $0.00010058 (handbook only) | $0.000137 (request 1), $0.000194 (request 2) | Same $0.00010058 for the cached handbook, plus the non-handbook tokens and output. |
| One call, cache write | $0.00125725 | $0.001377 (cold call, 10,813 written) | As predicted, plus non-handbook tokens. |
| 128-token cache blocks | Assumed 9,984 of 10,058 cached | **Wrong for this model.** Hits were 10,795 and 10,814 tokens, not multiples of 128. | This model caches up to "breakpoints", not 128-token blocks, so the simple estimate was closer. |
| 1,000 calls, no cache | $1.0058 | $1.1357 ($0.00113569 × 1,000) | 13% higher, all from non-handbook tokens and output. |
| 1,000 calls, cache | $0.1017 (1 write + 999 hits) | $0.4759 at this test's 78% hit rate | **4.7× the estimate:** Problem 2 assumed every call after the first hits. |
| Savings from caching | 89.9% | **58.1%** measured; 85.5% on documents where both calls hit | The gap is the cache misses (section 4). |

\* `scripts/handbook_token_check.py` sent two requests that were identical except for the handbook, with caching off. The API reported 10,543 and 484 prompt tokens. 10,543 − 484 = 10,059, minus 1 joining token = **10,058**. Those 2 calls cost $0.0011 and are saved under `handbook_token_check` in `cache_test.json`.

**In short:** the token estimate was exactly right. Per call, the cache prices behave as Problem 2 predicted. The total cache savings came in lower than predicted because Problem 2 assumed a perfect hit rate. It also ignored two things: each document makes two calls, and every call has about 900 tokens of overhead.

---

## 3. Projection: 1,000 documents a day for 30 days (30,000 documents, 60,000 model calls)

Assumes the same document mix as the practice set, 2 calls per document, and `prices.json` rates.

| Scenario | Per document | Per day (1,000 docs) | **30 days** | vs. no cache |
|---|---:|---:|---:|---:|
| **Without cache** (measured) | $0.002271 | $2.27 | **$68.14** | — |
| **With cache, as measured** (this test: 78% hit rate, includes the cold start) | $0.000952 | $0.95 | **$28.55** | −58.1% ($39.59 saved) |
| With cache, steady state at the measured hit rates* | $0.000867 | $0.87 | **$26.02** | −61.8% ($42.12 saved) |
| With cache, every call hits (measured cost of documents where both calls hit) | $0.000329 | $0.33 | **$9.88** (≈ $9.92 with one cold restart per day) | −85.5% ($58.26 saved) |
| *Problem 2 handbook-only estimate, no cache* | | | *$60.35* | |
| *Problem 2 handbook-only estimate, cache* | | | *$6.04* | |

\* Steady state leaves out the cold start. It uses the hit rates after warm-up: 9 of 11 first requests and 9 of 12 second requests. Math: 0.818 × $0.000137 + 0.182 × $0.001378 + 0.75 × $0.000194 + 0.25 × $0.001437 = $0.000867 per document.

**Realistic monthly bill: about $26–29 with caching vs. about $68 without**, saving about $40 a month. At 1,000 documents a day the cache stays warm: even spread over 24 hours that's a document every ~86 seconds, well inside the cache's 30-minute lifetime. Only one cold write a day matters (≈ $0.0014). Every miss costs about $0.0012 more than a hit, so raising the hit rate is worth up to another $16/month (from $26 down to $10).

---

## 4. What surprised me in the numbers, and why

1. **Caching wasn't reliable, even with everything set up right.** The prefix was the same, the routing key was the same, and the Portkey target and Azure model session were the same on every call (`targets[2]`, East US 2, session `…dcfa9b8a`). Still, 5 of 23 later calls missed. Three of the five were request 2, sent about a second after request 1 had just written the cache. Most likely causes: the provider's cache is best-effort, and a fresh write can take a moment before it's readable. This is the third try at the with-cache setup. Implicit caching alone got 11 of 23 hits ([attempt 1](cache_test_attempt1.json)). Explicit breakpoint + key got 9 of 23 the first time ([attempt 2](cache_test_attempt2.json)) and 18 of 23 when rerun with routing recorded. Same settings, very different luck.

2. **A cache miss costs more than not caching at all.** A miss stores ~11,000 tokens at the write price of $0.125/1M instead of $0.10/1M. That makes a miss call about 24% more expensive than the same call with caching off ($0.00138–0.00144 vs. $0.00111–0.00116). The 6 write calls (1 cold start + 5 misses) were **74% of the with-cache bill**. Changing the prompt prefix without switching caching off doesn't avoid the premium either. In attempt 1, the "without cache" setup only changed the prefix, and it cost $0.0338, 24% more than turning caching off for real ($0.0273). Every call paid to write a cache that nothing ever read.

3. **Portkey has its own response cache that can fake the token counts.** While diagnosing misses, I sent the same request several times. Portkey answered the repeats itself (`x-portkey-cache-status: HIT`) without calling the model. Its reply still carried the first call's `usage` block, so the token counts looked real but described a different call. The agent now sends `x-portkey-cache-force-refresh` on every request. The final data shows 0 Portkey cache hits, and every call has its own latency numbers.

4. **Each document is two model calls, so the handbook is paid twice.** The agent asks for `read_document`, gets the text, then makes a second full request to answer. Each document sends about 22,090 input tokens, 2.2 times the handbook. That's the biggest gap from the Problem 2 per-call math, and an obvious place to cut cost later.

5. **Cached counts weren't multiples of 128.** I assumed 128-token blocks in Problem 2. This model instead caches up to "breakpoints." Request 1 reads everything up to the breakpoint after the handbook (10,795 tokens). Request 2 reads that plus the user message that request 1 wrote (10,814). Also, 126 tokens per request are never cached or written in either setup. They are always billed at the normal input price.

6. **Output gets relatively more expensive once input is cached.** Output is only about 125 tokens per document, but it costs 5× the input rate. It is 2.7% of the no-cache bill and 6.7% of the cached bill, because caching cuts input cost by 10× while output stays at $0.50/1M.

7. **The tokenizer estimate was exact.** gpt-6-luna counted the handbook as 10,058 tokens, the same number tiktoken `o200k_base` gave in Problem 2.

---

## Files and what this cost

| File | What it is |
|---|---|
| `output/cache_test.json` | Final data. Every model call from both setups (raw `usage`, token counts, dollars, and route for with-cache calls), per-document answers, verification, summary, and the handbook token check. The without-cache calls are from 15:52 UTC; the with-cache calls are from a 15:59 UTC rerun with routing headers recorded, using the same prompt and settings. |
| `output/cache_test_attempt1.json` | Attempt 1 (rejected): implicit caching only, 11 of 23 hits; the random-prefix "without cache" setup still paid for cache writes. |
| `output/cache_test_attempt2.json` | Attempt 2: current settings, no routing headers, 9 of 23 hits. Its without-cache half is the final without-cache data. |
| `scripts/cache_test.py` | Runs the test (`--setups`, or `--summarize-only` to recompute from saved data with no API calls). |
| `scripts/handbook_token_check.py` | The paired-call handbook token measurement. |

**Problem 4 API spend:** about **$0.124** of Luna credit in total, about 12 cents:

| Item | Cost |
|---|---:|
| Attempt 1 | $0.0539 |
| Attempt 2 | $0.0499 |
| With-cache rerun | $0.0114 |
| 2 single-document sanity runs | $0.0051 |
| 2 diagnostic probes | ≈ $0.003 |
| Handbook token check | $0.0011 |

Every agent run is also in `output/usage_log.json` and `output/audit_trail.json`.
