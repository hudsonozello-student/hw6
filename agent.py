"""Campus Customs vendor desk agent: reads one vendor document and recommends whether to buy.

Run from the Homework 6 folder with the .venv active:
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html                    # all defenses (default)
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html --defenses none    # Problem 3 agent, undefended
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html --defenses code,prompt
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html --cache off

Defense layers (Problem 6), any combination:
    code    sanitize.py removes text a person can't see before any model reads the document
    design  the model gets the document as data, has no tools, and only reports facts; rules.py checks
            the facts against the document and makes the decision
    prompt  safety rules in prompts/prompt.md
With --defenses none the agent is exactly the Problem 3 agent (prompts/prompt_undefended.md, the
read_document tool, and the send_email / approve_payment trap tools).

Every run appends to output/usage_log.json (tokens and dollars) and output/audit_trail.json
(tool calls and the final answer). The trap tools write to output/trap_calls.json.
"""

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # keep the console to our own output

import argparse
import json
import re
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import BaseModel
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from models import (AuditEntry, CacheMode, CostBreakdown, DefenseReport, DeskDeps, DocumentText, Layer,
                    RequestUsage, ToolCallRecord, UsageEntry, VendorDecision, VendorFacts)
from rules import decide, load_handbook
from sanitize import clean_document
from tools import (FILE_TYPES, OUTPUT_DIR, ROOT, TRAP_LOG, append_json, approve_payment, now_iso, raw_text,
                   read_document, send_email)

MODEL_NAME = "gpt-6-luna"  # the only model this homework may use
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MAX_OUTPUT_TOKENS = 1000  # per model response (sent as max_completion_tokens)
LIMITS = UsageLimits(request_limit=5, tool_calls_limit=5, total_tokens_limit=60_000)  # caps spend per run

PROMPT_FILE = ROOT / "prompts" / "prompt.md"  # defended prompt: fact reader + safety rules
UNDEFENDED_PROMPT = ROOT / "prompts" / "prompt_undefended.md"  # the Problem 3 prompt, unchanged
SAFETY_HEADING = "## Safety rules"
ALL_LAYERS: tuple[Layer, ...] = ("code", "design", "prompt")
HANDBOOK = ROOT / "data" / "shop_handbook.md"
PRICES = ROOT / "data" / "prices.json"
USAGE_LOG = OUTPUT_DIR / "usage_log.json"
AUDIT_LOG = OUTPUT_DIR / "audit_trail.json"
OUTPUT_TOOL = "final_result"  # PydanticAI's tool for the structured answer; logged as the answer, not a tool call
SHORT_RESULT = 200  # characters of each tool result kept in the audit trail

RATES = json.loads(PRICES.read_text(encoding="utf-8"))[MODEL_NAME]
HANDBOOK_RULES = load_handbook(HANDBOOK)  # design layer: vendor lists and max costs, read by code
API_USAGE: dict[str, dict[str, Any]] = {}  # response id -> the raw `usage` block the API sent back
API_ROUTE: dict[str, dict[str, str | None]] = {}  # response id -> which gateway target / Azure session answered
ROUTE_HEADERS = ("x-portkey-cache-status", "x-portkey-last-used-option-index", "x-ms-region", "azureml-model-session")


def portkey_key() -> str:
    """Load PORTKEY_API_KEY from the nearest .env at or above this folder. Never printed or logged."""
    for folder in [ROOT, *ROOT.parents]:
        if (folder / ".env").exists():
            load_dotenv(folder / ".env", override=False)
            break
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        sys.exit("PORTKEY_API_KEY is not set. Add it to the project-root .env file.")
    return key


async def record_api_usage(response) -> None:
    """HTTP hook: keep each chat completion's raw `usage` block and routing headers, so the logs show exactly
    what the API reported and which backend answered."""
    if response.status_code == 200 and response.url.path.endswith("/chat/completions"):
        await response.aread()
        body = response.json()
        if body.get("id") and body.get("usage"):
            API_USAGE[body["id"]] = body["usage"]
            API_ROUTE[body["id"]] = {h: response.headers.get(h) for h in ROUTE_HEADERS}


def parse_defenses(value: str) -> tuple[Layer, ...]:
    if value == "none":
        return ()
    if value == "all":
        return ALL_LAYERS
    layers = tuple(dict.fromkeys(p.strip() for p in value.split(",") if p.strip()))
    unknown = [p for p in layers if p not in ALL_LAYERS]
    if unknown:
        raise ValueError(f"Unknown defense layer(s): {', '.join(unknown)}. Use none, all, or code,design,prompt.")
    return tuple(p for p in ALL_LAYERS if p in layers)


def split_safety_rules(text: str) -> tuple[str, str]:
    """prompts/prompt.md -> (task part, safety rules section)."""
    start = text.index(SAFETY_HEADING)
    end = text.find("\n## ", start + len(SAFETY_HEADING))
    rules = text[start:] if end == -1 else text[start:end]
    return (text[:start] + ("" if end == -1 else text[end + 1:])).rstrip(), rules.strip()


def system_prompt(layers: tuple[Layer, ...]) -> str:
    """Instructions for the model, then the full handbook (the same on every call, so it can be cached)."""
    task, safety = split_safety_rules(PROMPT_FILE.read_text(encoding="utf-8"))
    if "design" in layers:
        text = task + ("\n\n" + safety if "prompt" in layers else "")
    else:  # Problem 3 design: the model reads with a tool and decides; the safety rules are added on top
        text = UNDEFENDED_PROMPT.read_text(encoding="utf-8")  # byte for byte the Problem 3 prompt
        if "prompt" in layers:
            text = text.rstrip() + "\n\n" + safety + "\n"
    return text + "\n\n---\n\n" + HANDBOOK.read_text(encoding="utf-8")


def cache_setup(cache: CacheMode, batch: str | None,
                static: str) -> tuple[str | Callable[[], str], OpenAIChatModelSettings]:
    """System prompt and cache settings for each cache mode.

    on:  the prompt + handbook is static text with an explicit cache breakpoint right after it, and every
         call shares one prompt_cache_key so OpenAI routes them to the same cache. An optional `batch` id
         at the top gives a test batch its own fresh prefix, so its first call starts cold.
    off: prompt caching is switched off (explicit mode with no breakpoints), and a new random id at the
         top of every request means no request shares a prefix with an earlier one.
    """
    # Luna rejects function tools unless reasoning is off; temperature stays at its default of 1.
    base = OpenAIChatModelSettings(max_tokens=MAX_OUTPUT_TOKENS, openai_reasoning_effort="none")
    if cache == "off":
        # One dynamic part: PydanticAI puts dynamic parts after static ones, and the id must come first.
        return (lambda: f"Request id: {uuid.uuid4().hex}\n\n{static}",
                OpenAIChatModelSettings(**base, openai_prompt_cache_options={"mode": "explicit"}))
    return (f"Batch id: {batch}\n\n{static}" if batch else static,
            OpenAIChatModelSettings(**base, openai_cache_instructions=True,
                                    openai_prompt_cache_key="campus-customs-vendor-desk"))


def build_agent(cache: CacheMode = "on", batch: str | None = None,
                layers: tuple[Layer, ...] = ALL_LAYERS) -> Agent[DeskDeps, Any]:
    key = portkey_key()
    # Force-refresh skips Portkey's own response cache, which would replay an old answer (and its old usage)
    # for an identical request. Every call reaches the model; only the model's prompt cache is in play.
    headers = {"x-portkey-api-key": key, "x-portkey-cache-force-refresh": "true"}
    client = AsyncOpenAI(api_key=key, base_url=PORTKEY_BASE_URL, default_headers=headers, timeout=120, max_retries=2,
                         http_client=DefaultAsyncHttpxClient(event_hooks={"response": [record_api_usage]}))
    model = OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    # Prompt first, then the full handbook: the same text on every call, so it can be served from cache.
    instructions, settings = cache_setup(cache, batch, system_prompt(layers))
    design = "design" in layers
    return Agent(
        model,
        deps_type=DeskDeps,
        # Design layer: the model that reads the document only reports facts and has no tools at all, so a
        # poisoned document can't reach send_email / approve_payment or write the decision. The trap tools
        # stay in tools.py for the undefended agent and the shop's later human sign-off step.
        output_type=VendorFacts if design else VendorDecision,
        instructions=instructions,
        tools=[] if design else [read_document, send_email, approve_payment],
        model_settings=settings,
        retries=2,
    )


def as_data(text: str) -> str:
    """Design layer: the document goes to the model as data in tags it can't close from inside."""
    return re.sub(r"(?i)</?\s*vendor_document\s*>", "[tag removed]", text)


# ---------- logging ----------

def price(prompt: int, cached: int, cache_write: int, completion: int) -> CostBreakdown:
    """Dollars at data/prices.json rates. Completion tokens include any reasoning tokens."""
    cost = {
        "uncached_input": (prompt - cached - cache_write) * RATES["input_per_1m"] / 1e6,
        "cached_input": cached * RATES["cached_input_per_1m"] / 1e6,
        "cache_write": cache_write * RATES["cache_write_per_1m"] / 1e6,
        "output": completion * RATES["output_per_1m"] / 1e6,
    }
    return CostBreakdown(**{k: round(v, 8) for k, v in cost.items()}, total=round(sum(cost.values()), 8))


def request_usage(m: ModelResponse) -> RequestUsage:
    u = m.usage
    return RequestUsage(
        model_reported=m.model_name,
        prompt_tokens=u.input_tokens,
        cached_tokens=u.cache_read_tokens,
        cache_write_tokens=u.cache_write_tokens,
        completion_tokens=u.output_tokens,
        reasoning_tokens=u.details.get("reasoning_tokens", 0),
        cost_usd=price(u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens),
        api_usage=API_USAGE.get(m.provider_response_id or "", {}),
        route=API_ROUTE.get(m.provider_response_id or "", {}),
    )


def usage_entry(run_id: str, document: str, time: str, cache: CacheMode, layers: tuple[Layer, ...],
                messages: list[ModelMessage]) -> UsageEntry:
    per_request = [request_usage(m) for m in messages if isinstance(m, ModelResponse)]
    prompt = sum(r.prompt_tokens for r in per_request)
    cached = sum(r.cached_tokens for r in per_request)
    cache_write = sum(r.cache_write_tokens for r in per_request)
    completion = sum(r.completion_tokens for r in per_request)
    return UsageEntry(
        run_id=run_id, document=document, time=time, model=MODEL_NAME, cache=cache, defenses=list(layers),
        requests=len(per_request),
        prompt_tokens=prompt, cached_tokens=cached, cache_write_tokens=cache_write,
        uncached_prompt_tokens=prompt - cached - cache_write, completion_tokens=completion,
        reasoning_tokens=sum(r.reasoning_tokens for r in per_request), total_tokens=prompt + completion,
        cost_usd=price(prompt, cached, cache_write, completion), per_request=per_request,
    )


def short(content: Any) -> str:
    if isinstance(content, DocumentText):
        text = f"{content.file_type}, {len(content.text)} chars: {content.text}"
    elif isinstance(content, BaseModel):
        text = content.model_dump_json()
    else:
        text = str(content)
    text = " ".join(text.split())
    return text if len(text) <= SHORT_RESULT else text[:SHORT_RESULT] + "..."


def tool_calls(messages: list[ModelMessage]) -> list[ToolCallRecord]:
    """Pair each tool call with its result, in the order the model made them."""
    results: dict[str, str] = {}
    for m in messages:
        for part in m.parts:
            if isinstance(part, ToolReturnPart):
                results[part.tool_call_id] = short(part.content)
            elif isinstance(part, RetryPromptPart) and part.tool_call_id:
                results[part.tool_call_id] = "retry: " + short(part.content)
    records = []
    for m in messages:
        if not isinstance(m, ModelResponse):
            continue
        for part in m.parts:
            if isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL:
                records.append(ToolCallRecord(step=len(records) + 1, tool=part.tool_name, arguments=part.args_as_dict(),
                                              result=results.get(part.tool_call_id, "no result")))
    return records


def trap_count(run_id: str) -> int:
    if not TRAP_LOG.exists():
        return 0
    return sum(1 for call in json.loads(TRAP_LOG.read_text(encoding="utf-8")) if call.get("run_id") == run_id)


# ---------- one run ----------

def run_desk(doc: str, *, cache: CacheMode = "on", batch: str | None = None,
             defenses: tuple[Layer, ...] = ALL_LAYERS) -> tuple[AuditEntry, UsageEntry]:
    """Run the agent on one document and append the run to the usage log and the audit trail.

    defenses=() is the undefended Problem 3 agent.
    """
    doc_path = Path(doc).resolve()
    if not doc_path.is_file():
        raise ValueError(f"No such file: {doc}")
    if doc_path.suffix.lower() not in FILE_TYPES:
        raise ValueError(f"Unsupported file type {doc_path.suffix}; use .html, .pdf, or .eml.")
    doc_label = doc_path.relative_to(ROOT).as_posix() if doc_path.is_relative_to(ROOT) else doc_path.name

    if not TRAP_LOG.exists():
        TRAP_LOG.write_text("[]\n", encoding="utf-8")  # starts empty; any entry means a hijack

    layers = tuple(p for p in ALL_LAYERS if p in defenses)
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    deps = DeskDeps(run_id=run_id, doc_path=doc_path, doc_label=doc_label, sanitize="code" in layers)
    agent = build_agent(cache, batch, layers)
    report = DefenseReport(layers=list(layers)) if layers else None
    started = now_iso()

    answer, error = None, None
    with capture_run_messages() as messages:
        try:
            if "design" in layers:
                # The program reads the document (cleaned first if the code layer is on) and hands the text
                # to a model that can only report facts; code then checks the facts and decides.
                clean = clean_document(doc_path) if "code" in layers else None
                text = clean.text if clean else raw_text(doc_path)
                if clean:
                    deps.cleaned.append(clean)
                prompt = (f"Vendor document ({FILE_TYPES[doc_path.suffix.lower()]} file {doc_path.name}):\n"
                          f"<vendor_document>\n{as_data(text)}\n</vendor_document>")
                facts = agent.run_sync(prompt, deps=deps, usage_limits=LIMITS).output
                answer, checks = decide(facts, text, HANDBOOK_RULES)
                report.model_facts, report.checks = facts, checks
                report.suspicious_text = facts.suspicious_text
            else:
                answer = agent.run_sync(f"Vendor document path: {doc}", deps=deps, usage_limits=LIMITS).output
        except Exception as exc:  # still log what the failed run cost
            error = f"{type(exc).__name__}: {exc}"

    if report and deps.cleaned:
        report.removed_hidden_text = [r for c in deps.cleaned for r in c.removed]
        report.invisible_characters_removed = sum(c.invisible_characters_removed for c in deps.cleaned)
        report.truncated = any(c.truncated for c in deps.cleaned)
    usage = usage_entry(run_id, doc_label, started, cache, layers, messages)
    audit = AuditEntry(run_id=run_id, time=started, document=doc_label, model=MODEL_NAME,
                       tool_calls=tool_calls(messages), trap_calls=trap_count(run_id), final_answer=answer,
                       error=error, defenses=list(layers), defense_report=report)
    append_json(USAGE_LOG, usage.model_dump(mode="json"))
    append_json(AUDIT_LOG, audit.model_dump(mode="json"))
    return audit, usage


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    parser.add_argument("--doc", required=True, help="path to one vendor document (.html, .pdf, or .eml)")
    parser.add_argument("--cache", choices=["on", "off"], default="on",
                        help="off switches prompt caching off and starts every request with a new random id")
    parser.add_argument("--defenses", default="all",
                        help="all (default), none (the undefended Problem 3 agent), or a list like code,prompt")
    args = parser.parse_args()

    try:
        audit, usage = run_desk(args.doc, cache=args.cache, defenses=parse_defenses(args.defenses))
    except ValueError as exc:
        sys.exit(str(exc))

    print(f"Document: {audit.document}   run: {audit.run_id}   cache: {usage.cache}   "
          f"defenses: {', '.join(audit.defenses) or 'NONE (undefended Problem 3 agent)'}")
    if audit.final_answer:
        print(audit.final_answer.model_dump_json(indent=2))
    else:
        print(f"Run failed: {audit.error}")
    r = audit.defense_report
    if r:
        for item in r.removed_hidden_text:
            print(f"Code layer removed ({item.why}): {item.text[:100]}")
        for item in r.suspicious_text:
            print(f"Reader flagged as suspicious: {item[:100]}")
        for c in r.checks:
            if not c.passed:
                print(f"Design check failed - {c.check}: {c.detail}")
    print(f"Tools called: {', '.join(c.tool for c in audit.tool_calls) or 'none'}")
    print(f"Tokens: {usage.prompt_tokens} in ({usage.cached_tokens} cached, {usage.cache_write_tokens} cache write), "
          f"{usage.completion_tokens} out, {usage.requests} requests.  Cost: ${usage.cost_usd.total:.6f}")
    traps = audit.trap_calls
    print("Trap tools: " + (f"{traps} CALL(S) LOGGED - this document took over the agent!" if traps else "not called"))
    if audit.error:
        sys.exit(1)


if __name__ == "__main__":
    main()
