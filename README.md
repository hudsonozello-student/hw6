# Campus Customs Vendor Desk Agent — MGT 409 Homework 6

An AI agent that reads a vendor document (an HTML quote, a PDF, or an `.eml` email), pulls out the key
facts (vendor, SKU, unit price, lead time, minimum order), and recommends whether the Campus Customs
shop should buy — following the rules in the shop handbook. The homework studies two things: the
**cost** of sending a ~10,000-token handbook on every call, and the **safety** of documents that hide
instructions aimed at the AI.

**Model:** every AI call uses `gpt-6-luna` through Portkey. Nothing else runs.

**Safety:** the email and payment tools never send or pay anything — they only write to a log. The
defended agent goes further (see *Defenses* below).

## Quick start

```bash
# 1. From this folder, create a virtual environment and install dependencies
python -m venv .venv
# Windows:  .venv\Scripts\activate       macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your Portkey key
cp .env.example .env            # Windows: copy .env.example .env
#   then edit .env and paste your real PORTKEY_API_KEY

# 3. Run the agent on one document
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

The agent prints the answer (vendor, SKU, price, lead time, minimum order, a recommend / do-not-recommend
decision, and a one-sentence reason) and appends to the logs in `output/`.

## How to run it

```bash
python agent.py --doc <path>                 # full defenses (default)
python agent.py --doc <path> --defenses none # the undefended Problem 3 agent
python agent.py --doc <path> --cache off      # turn prompt caching off
```

- `--doc` takes any file under `data/` — a practice doc, an exam doc, or one of the two attack files
  in `data/my_attacks/`.
- `--defenses` is `all` (default), `none`, or a comma list like `code,prompt`.

### The three defense layers

1. **Code** (`sanitize.py`) — before any model sees the document, strip text a person could not see
   (hidden/zero-size/white/off-page/invisible-render-mode text, comments, the hidden half of an email,
   invisible characters).
2. **Design** (`agent.py`, `rules.py`) — the model that reads the document has **no tools** and only
   reports facts; a plain program checks the facts against the document and the handbook and makes the
   decision. A poisoned document cannot reach the email/payment tools or write the decision.
3. **Prompt** (`prompts/prompt.md`) — safety rules telling the model to treat the document as untrusted
   data and ignore "corrections" to the quoted numbers.

## Layout

| Path | What it is |
|---|---|
| `agent.py` | Entry point: builds and runs the agent, writes the logs |
| `tools.py` | Document reader + the two log-only trap tools (`send_email`, `approve_payment`) |
| `models.py` | Structured types (the answer, tool results, defense report, log entries) |
| `sanitize.py` | Defense layer 1 (code): keep only the text a person would see |
| `rules.py` | Defense layer 2 (design): check facts and make the decision in code |
| `prompts/prompt.md` | Defended instructions (fact reader + safety rules); `prompt_undefended.md` is the Problem 3 prompt |
| `data/` | Shop handbook, price list, 12 practice docs + key, 10 exam docs, 2 red-team attack files |
| `output/` | All results and reports (see below) |
| `scripts/` | Helper scripts used to produce each problem's output |
| `AI_prompts.md` | Verbatim log of every prompt typed into the vibe coder |

### Key outputs

- `output/hw6_report.html` — the one-page results report (open by double-click, works offline)
- `output/harness.md` — reference for the agent's fields, tools, and safety layers
- `output/handbook_estimate.md` — token count and cost of the handbook (Problem 2)
- `output/cache_test.md` / `.json` — caching results (Problem 4)
- `output/attack_results.md` / `.json` — attacks on the undefended agent (Problem 5)
- `output/defense_results.md` / `.json` — the defenses, before and after (Problem 6)
- `output/red_team.md` — two home-made attacks (Problem 7)
- `output/exam_results.json` — the final defended agent on the 10 exam docs (Problem 8)
- `output/usage_log.json`, `output/audit_trail.json`, `output/trap_calls.json` — per-run logs

## Notes for graders

- The repo is self-contained: the whole `data/` folder is included, so the agent runs on any document
  immediately after you add a `.env`.
- `trap_calls.json` stays `[]` — the email/payment tools were never triggered, defended or not.
- Reproducing a run needs a working `PORTKEY_API_KEY` with access to `gpt-6-luna`. The scripts in
  `scripts/` regenerate every file in `output/`.
