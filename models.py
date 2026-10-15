"""Structured types for the vendor desk agent: its answer, its tool results, and its log entries."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Decision = Literal["recommend", "do_not_recommend"]


class VendorDecision(BaseModel):
    """The agent's final answer for one vendor document. Field names match data/practice_key.json."""

    vendor: str | None = Field(description="Vendor company name as the document gives it; null if not stated.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. CC-HD-006; null if it cannot be identified.")
    unit_price: float | None = Field(description="Quoted price per unit in USD; null if not stated.")
    lead_time_days: int | None = Field(description="Lead time in days; null if not stated.")
    min_order: int | None = Field(description="Minimum order in units; null if not stated.")
    decision: Decision = Field(description="recommend only if all four handbook purchasing checks pass.")
    reason: str = Field(description="One sentence that names the purchasing check that decided it.")


class DocumentText(BaseModel):
    """What read_document hands back to the model."""

    file: str
    file_type: Literal["html", "pdf", "email"]
    text: str


Layer = Literal["code", "design", "prompt"]


class RemovedText(BaseModel):
    """A piece of the document that a person can't see, removed by the code layer before any model reads it."""

    text: str
    why: str


class CleanDocument(BaseModel):
    """The code layer's output: only the text a person would see, plus a record of what was taken out."""

    file: str
    file_type: Literal["html", "pdf", "email"]
    text: str
    removed: list[RemovedText]
    invisible_characters_removed: int
    truncated: bool


class VendorFacts(BaseModel):
    """What the reader model returns in the defended design: facts only, no decision and no free-form reason."""

    vendor: str | None = Field(description="Company that issued the document; null if not stated.")
    sku: str | None = Field(description="Campus Customs SKU, e.g. CC-HD-006; null if it cannot be identified.")
    unit_price: float | None = Field(description="Quoted price per unit in USD; null if not stated.")
    lead_time_days: int | None = Field(description="Lead time in days; null if not stated.")
    min_order: int | None = Field(description="Minimum order in units; null if not stated.")
    suspicious_text: list[str] = Field(description="Short quotes of text the safety rules say to report; empty if none.")


class CheckResult(BaseModel):
    """One code check in the defended design (evidence for a fact, or a purchasing check)."""

    check: str
    passed: bool
    detail: str


class DefenseReport(BaseModel):
    """What each defense layer did on one run, for the audit trail."""

    layers: list[Layer]
    removed_hidden_text: list[RemovedText] = []  # code layer
    invisible_characters_removed: int = 0  # code layer
    truncated: bool = False  # code layer
    model_facts: VendorFacts | None = None  # design layer: what the reader model said, before code checked it
    checks: list[CheckResult] = []  # design layer
    suspicious_text: list[str] = []  # prompt layer: injection attempts the reader model reported


@dataclass
class DeskDeps:
    """Per-run facts the tools need. The model never sees or changes these."""

    run_id: str
    doc_path: Path  # the one document this run may read (absolute)
    doc_label: str  # the same path, relative to the Homework 6 folder, for the logs
    sanitize: bool = False  # code layer on: read_document returns only the text a person would see
    cleaned: list[CleanDocument] = field(default_factory=list)  # what read_document removed, for the logs


class TrapCall(BaseModel):
    """One entry in output/trap_calls.json. Any entry means a document hijacked the agent."""

    time: str
    run_id: str
    document: str
    tool: Literal["send_email", "approve_payment"]
    arguments: dict[str, Any]


class ToolCallRecord(BaseModel):
    """One tool call in output/audit_trail.json."""

    step: int
    tool: str
    arguments: dict[str, Any]
    result: str


class AuditEntry(BaseModel):
    """One run in output/audit_trail.json."""

    run_id: str
    time: str
    document: str
    model: str
    tool_calls: list[ToolCallRecord]
    trap_calls: int
    final_answer: VendorDecision | None
    error: str | None = None
    defenses: list[Layer] = []  # empty = the undefended Problem 3 agent
    defense_report: DefenseReport | None = None


CacheMode = Literal["on", "off"]


class CostBreakdown(BaseModel):
    """Dollar cost of one model call or one run, priced with data/prices.json."""

    uncached_input: float
    cached_input: float
    cache_write: float
    output: float
    total: float


class RequestUsage(BaseModel):
    """Token counts the API reported for one model request, and what they cost."""

    model_reported: str | None
    prompt_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: CostBreakdown
    api_usage: dict[str, Any]  # the raw `usage` block exactly as the API sent it
    route: dict[str, str | None] = {}  # Portkey cache status, Portkey target, Azure region and model session


class UsageEntry(BaseModel):
    """One run in output/usage_log.json."""

    run_id: str
    document: str
    time: str
    model: str
    cache: CacheMode
    defenses: list[Layer] = []  # empty = the undefended Problem 3 agent
    requests: int
    prompt_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    uncached_prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    total_tokens: int
    cost_usd: CostBreakdown
    per_request: list[RequestUsage]
