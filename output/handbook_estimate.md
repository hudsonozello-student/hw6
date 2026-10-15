# Problem 2: Size up the handbook

The vendor desk agent sends `data/shop_handbook.md` to `gpt-6-luna` on every call. This file estimates how many tokens that is and what the handbook alone costs. These are offline estimates: no API calls were made. Problem 4 will check them against the token usage that real runs report.

**Bottom line:**

| | Value |
|---|---|
| Handbook size | **10,058 tokens** (o200k_base tokenizer) |
| One call, no caching | **$0.0010058** (about 0.1 cent) |
| 1,000 calls, no caching | **$1.0058** (about $1.01) |
| One call, cache hit | **$0.00010058** (about 0.01 cent) |
| 1,000 calls with caching (1 cache write + 999 cache hits) | **$0.1017** (about $0.10) |
| Savings from caching over 1,000 calls | **$0.9041, or 89.9%** |

---

## 1. Token count and how I got it

### Method

1. **Tool:** OpenAI's open-source tokenizer library `tiktoken` (v0.14.0), installed in this homework's `.venv`. The script is [`scripts/handbook_estimate.py`](../scripts/handbook_estimate.py). It saves its raw numbers to [`output/handbook_estimate.json`](handbook_estimate.json) so Problem 4 can compare against them.
2. **Encoding:** `o200k_base`. This is the tokenizer that OpenAI uses for the GPT-4o and GPT-5 families. OpenAI has not published a separate tokenizer for `gpt-6-luna`, so I assume it uses `o200k_base` too. Problem 4 will test this assumption.
3. **Input text:** the full handbook, read the same way the agent will read it (`Path.read_text(encoding="utf-8")`). That call turns the Windows line endings (`\r\n`) into plain `\n`.
4. **Count:** `len(tiktoken.get_encoding("o200k_base").encode(handbook_text))` = **10,058 tokens**.

Run it again from the Homework 6 folder with:

```powershell
.\.venv\Scripts\python.exe scripts\handbook_estimate.py
```

### Cross-checks

| Method | Count | Notes |
|---|---|---|
| **tiktoken `o200k_base`** (used for all costs) | **10,058** | The GPT-4o/GPT-5 family tokenizer. |
| tiktoken `cl100k_base` | 10,184 | The older GPT-4/GPT-3.5 tokenizer. Only 1.3% higher, so the count doesn't depend much on which tokenizer is used. |
| Raw file with Windows `\r\n` line endings | 10,069 | +11 tokens if the file is sent byte-for-byte without normalizing line endings. Too small to matter. |
| Rule of thumb: characters ÷ 4 | 7,226 | 28,903 characters ÷ 4. **Underestimates by 28%.** |
| Rule of thumb: words × 4/3 | 8,169 | 6,127 words × 1.333. **Underestimates by 19%.** |

The handbook is about what the assignment says ("~10k tokens"). The rules of thumb come in low because about 89% of the handbook's tokens are in markdown tables (sections 5, 6, 9, and 10). Prices like `$29.48`, SKUs like `CC-HD-001`, and the `|` separators each split into several short tokens. That works out to about 2.9 characters per token, while ordinary English prose runs about 4.

Other file stats: 28,903 characters (29,241 bytes on disk with `\r\n`), 6,127 words, 339 lines.

### Where the tokens are (by section)

| Section | Tokens | Share |
|---|---:|---:|
| Title and version line | 24 | 0.2% |
| 1. Who we are | 192 | 1.9% |
| 2. Staff and roles | 106 | 1.1% |
| 3. Store hours | 63 | 0.6% |
| 4. Purchasing rules | 269 | 2.7% |
| 5. Approved vendors | 417 | 4.1% |
| 6. Removed and pending vendors | 117 | 1.2% |
| 7. Returns and exchanges | 95 | 0.9% |
| 8. Discounts | 94 | 0.9% |
| **9. Product catalogue** (176 SKU rows) | **6,920** | **68.8%** |
| **10. Recent purchase orders** (40 rows) | **1,462** | **14.5%** |
| 11. Brand and quality checklist | 105 | 1.0% |
| 12. Big-weekend planning | 123 | 1.2% |
| 13. How the vendor desk agent should report | 71 | 0.7% |
| **Total** | **10,058** | **100%** |

The sections add up exactly to 10,058. Two tables make up **83.3%** of the handbook: the product catalogue (6,920) and the purchase-order history (1,462). The parts the four purchasing checks actually use (section 4 rules, sections 5–6 vendor lists, and the SKU / max unit cost columns of section 9) are a much smaller slice. That matters when we try to cut the bill later.

---

## 2. What the handbook alone costs

### Prices used (`data/prices.json`, gpt-6-luna, $ per 1M tokens)

| Token type | Price per 1M | Price per token |
|---|---:|---:|
| Input (normal, not cached) | $0.10 | $0.0000001 |
| Cached input (cache hit / read) | $0.01 | $0.00000001 |
| Cache write (first time a prefix is stored) | $0.125 | $0.000000125 |
| Output | $0.50 | $0.0000005 |

The handbook is part of the **input** (the prompt), so output pricing doesn't apply. "Handbook alone" means only its 10,058 tokens. The vendor document, the instructions, the model's answer, and any reasoning tokens are left out. Those come up in later problems.

Formula: **cost = tokens × (price per 1M ÷ 1,000,000)**

### A. Without caching (every call pays full input price)

**One call:**

```
10,058 tokens × $0.10 / 1,000,000 = $0.0010058
```

**1,000 calls:**

```
$0.0010058 × 1,000 = $1.0058   (≈ $1.01)
```

Same thing in one step: 10,058 × 1,000 = 10,058,000 tokens = 10.058M tokens × $0.10 = **$1.0058**.

### B. With caching

Prompt caching saves a prompt prefix the model has already seen, so later calls that start with that same prefix are billed at the cheaper cached rate. The handbook is identical on every call, so we put it at the **start** of the prompt and every call after the first gets a cache hit.

**First call (cache write).** The handbook gets stored in the cache at the write price:

```
10,058 × $0.125 / 1,000,000 = $0.00125725
```

That's 25% more than the uncached call ($0.0010058). It's a one-time premium for storing the prefix.

**Each later call (cache read):**

```
10,058 × $0.01 / 1,000,000 = $0.00010058
```

That's one tenth of the uncached price.

**1,000 calls (1 write + 999 reads):**

```
  1 × $0.00125725  = $0.00125725
999 × $0.00010058  = $0.10047942
                     -----------
Total              = $0.10173667   (≈ $0.10)
```

**Savings vs. no caching:**

```
$1.0058 − $0.10173667 = $0.90406333 saved   (89.9% cheaper)
```

**Break-even:** caching costs an extra $0.025 per 1M on the first call and saves $0.09 per 1M on every later call. It pays for itself on the **2nd call**.

### B2. A more precise caching estimate (128-token blocks)

OpenAI only caches prompts that are at least 1,024 tokens long, and it caches the prefix in whole **128-token blocks**. Leftover tokens at the end of the prefix are billed at the normal input price. If the handbook is the first thing in the prompt:

```
Cacheable  = floor(10,058 / 128) × 128 = 78 × 128 = 9,984 tokens
Leftover   = 10,058 − 9,984            = 74 tokens (always full price)
```

| | Math | Cost |
|---|---|---:|
| First call (write) | 9,984 × $0.125/1M + 74 × $0.10/1M = $0.001248 + $0.0000074 | $0.0012554 |
| Each later call (hit) | 9,984 × $0.01/1M + 74 × $0.10/1M = $0.00009984 + $0.0000074 | $0.00010724 |
| 1,000 calls | $0.0012554 + 999 × $0.00010724 = $0.0012554 + $0.10713276 | **$0.10838816 (≈ $0.11)** |

That's about $0.007 more per 1,000 calls than the simple version and still **89.2%** cheaper than no caching. In a real call, the chat-format tokens around the system message (a few tokens) shift where the 128-token blocks fall. So the real number lands between $0.1017 and $0.1084 per 1,000 calls.

### Summary table

| Scenario | One call | 1,000 calls |
|---|---:|---:|
| **No caching** | $0.0010058 | **$1.0058** |
| **Caching** (simple: all 10,058 tokens cached) | write $0.00125725, then hit $0.00010058 | **$0.1017** |
| **Caching** (128-token blocks: 9,984 cached + 74 full price) | write $0.0012554, then hit $0.00010724 | **$0.1084** |

### What could make the cached number worse

- **Cache expiry.** OpenAI keeps a cached prefix for only about 5–10 minutes of inactivity (up to about an hour off-peak). If the 1,000 calls are spread over days, there are more cache writes. Each extra write costs $0.00125725 − $0.00010058 = $0.00115667 more than a hit. Even with **50 cache writes** (50 × $0.00125725 + 950 × $0.00010058 = $0.0628625 + $0.095551 = $0.1584), caching is still 84% cheaper than no caching.
- **Prompt order.** Caching only matches an **identical prefix**. If anything that changes between calls (the vendor document, a date, a run ID) comes *before* the handbook, every call misses the cache and costs the full $0.0010058. The agent should send: handbook + fixed instructions first, then the vendor document last.
- **Cache-write pricing.** OpenAI doesn't normally bill cache writes separately (the first call just pays the normal $0.10 input rate). If Portkey bills it that way, the first call costs $0.0010058 and 1,000 calls cost $0.0010058 + $0.10047942 = **$0.1015**. That's almost the same; I used the course's price list with the $0.125 write rate above.

---

## 3. What Problem 4 should check

When we run the agent for real, the API's `usage` block reports `prompt_tokens` and `prompt_tokens_details.cached_tokens`. To compare against these estimates:

1. **Token count:** `prompt_tokens` will be **more than 10,058**, because each real prompt also includes the instructions, the vendor document, and a few chat-format tokens per message. To isolate the handbook, compare a run with the handbook against the same run without it. The difference should be about 10,058 if `gpt-6-luna` uses `o200k_base`.
2. **Caching:** on the 2nd and later calls with the same handbook prefix, `cached_tokens` should be a multiple of 128 and at least about 9,984 (the handbook plus any fixed instructions in front of it).
3. **Cost:** recompute the dollars from the reported usage with the same `prices.json` rates and compare against the $0.0010058 per call (no cache) and $0.00010058 per call (cache hit) figures above.
