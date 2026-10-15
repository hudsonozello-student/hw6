"""Defense layer 2 (design): code, not the model, checks the facts and makes the buy decision.

In the defended design the model that reads a vendor document has no tools and can only fill in five
facts. This module takes those facts and:
  1. checks each one against the document text the model was shown (a number or name the document
     doesn't contain is treated as unknown, so the model can't invent or "correct" a value),
  2. checks the vendor's identity against the contact addresses in the document,
  3. runs the four purchasing checks from handbook section 4 using the handbook's own tables,
  4. writes the decision and the one-sentence reason itself.
A document can't reach this code with instructions; it can only influence the five facts, and each
fact has to be backed by the document.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from models import CheckResult, VendorDecision, VendorFacts

HANDBOOK = Path(__file__).resolve().parent / "data" / "shop_handbook.md"
OUR_DOMAIN = "campuscustoms.example"
EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b")
SKU = re.compile(r"^CC-[A-Z]{2}-\d{3}$")


@dataclass
class Handbook:
    approved: dict[str, tuple[str, str | None]]  # normalized name -> (name, order email domain)
    blocked: dict[str, tuple[str, str]]  # normalized name -> (name, status) for removed and pending vendors
    catalogue: dict[str, tuple[str, float]]  # SKU -> (item, max unit cost)
    max_lead_days: int
    max_min_order: int


def norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def tables(markdown: str) -> dict[str, list[dict[str, str]]]:
    """Markdown tables by section number ("5", "6", "9", ...)."""
    found = {}
    for section in re.split(r"(?m)^## ", markdown)[1:]:
        number = section.split(".", 1)[0].strip()
        rows = [[c.strip() for c in line.strip().strip("|").split("|")]
                for line in section.splitlines() if line.strip().startswith("|")]
        rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r)]
        if rows:
            found[number] = [dict(zip(rows[0], r)) for r in rows[1:]]
    return found


def load_handbook(path: Path = HANDBOOK) -> Handbook:
    md = path.read_text(encoding="utf-8")
    t = tables(md)
    approved = {}
    for row in t["5"]:
        domain = re.search(r"orders@([\w.-]+\.example)", row["Notes"])
        approved[norm(row["Vendor"])] = (row["Vendor"], domain.group(1).lower() if domain else None)
    blocked = {norm(r["Vendor"]): (r["Vendor"], r["Status"]) for r in t["6"]}
    catalogue = {r["SKU"]: (r["Item"], float(r["Max unit cost"].lstrip("$").replace(",", ""))) for r in t["9"]}
    lead = re.search(r"lead time is (\d+) days or less", md)
    min_order = re.search(r"minimum order is (\d+) units or less", md)
    return Handbook(approved, blocked, catalogue, int(lead.group(1)) if lead else 21,
                    int(min_order.group(1)) if min_order else 600)


# ---------- evidence: every fact must be backed by the document ----------

def number_in(text: str, value: float, decimals: bool) -> bool:
    plain = text.replace(",", "")
    forms = {f"{value:.2f}", f"{value:g}"} if decimals else {str(int(value))}
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", plain) for f in forms)


def verify(facts: VendorFacts, text: str, hb: Handbook) -> tuple[VendorFacts, list[CheckResult]]:
    """Keep only facts the document itself backs up; anything else becomes unknown (null)."""
    checks, kept = [], facts.model_copy()

    def evidence(field: str, ok: bool, detail: str) -> None:
        checks.append(CheckResult(check=f"evidence: {field}", passed=ok, detail=detail))
        if not ok:
            setattr(kept, field, None)

    if facts.vendor is not None:
        evidence("vendor", norm(facts.vendor) in norm(text), f'"{facts.vendor}" '
                 + ("appears in the document" if norm(facts.vendor) in norm(text) else "is not in the document"))
    if facts.sku is not None:
        sku = facts.sku.strip().upper()
        kept.sku = sku
        item = hb.catalogue.get(sku, ("", 0))[0]
        ok = bool(SKU.match(sku)) and sku in hb.catalogue and (sku in text.upper() or norm(item) in norm(text))
        evidence("sku", ok, f"{sku} " + ("is in the catalogue and the document" if ok
                                         else "is not a catalogue SKU backed by the document"))
    if facts.unit_price is not None:
        ok = 0 < facts.unit_price < 100_000 and number_in(text, facts.unit_price, True)
        evidence("unit_price", ok, f"${facts.unit_price:.2f} " + ("appears in the document" if ok else "is not in the document"))
    if facts.lead_time_days is not None:
        ok = 0 <= facts.lead_time_days <= 365 and number_in(text, facts.lead_time_days, False)
        evidence("lead_time_days", ok, f"{facts.lead_time_days} days " + ("appears in the document" if ok else "is not in the document"))
    if facts.min_order is not None:
        ok = 0 < facts.min_order < 1_000_000 and number_in(text, facts.min_order, False)
        evidence("min_order", ok, f"{facts.min_order} units " + ("appears in the document" if ok else "is not in the document"))
    return kept, checks


def identity_problem(vendor: str, text: str, hb: Handbook) -> str | None:
    """An approved vendor's documents come from its own domain. Contact addresses from somewhere else contradict the claim."""
    entry = hb.approved.get(norm(vendor))
    if not entry or not entry[1]:
        return None
    domains = {d.lower() for d in EMAIL.findall(text)} - {OUR_DOMAIN}
    if domains and entry[1] not in domains:
        return (f"the document's contact address ({', '.join(sorted(domains))}) is not the domain on file for "
                f"{entry[0]} ({entry[1]}), so the vendor can't be confirmed")
    return None


# ---------- the four purchasing checks (handbook section 4) ----------

def decide(facts: VendorFacts, text: str, hb: Handbook) -> tuple[VendorDecision, list[CheckResult]]:
    kept, checks = verify(facts, text, hb)
    failures = []

    v = kept.vendor
    if v is None:
        vendor_ok, why = False, "the vendor could not be confirmed from the document"
    elif norm(v) in hb.blocked:
        name, status = hb.blocked[norm(v)]
        status = status.split(". ")[0].rstrip(".")
        vendor_ok, why = False, f"{name} is on the handbook's removed or pending list ({status[0].lower() + status[1:]})"
    elif norm(v) not in hb.approved:
        vendor_ok, why = False, f"{v} is not on the approved vendor list"
    elif problem := identity_problem(v, text, hb):
        vendor_ok, why = False, problem
    else:
        vendor_ok, why = True, f"{hb.approved[norm(v)][0]} is approved"
    checks.append(CheckResult(check="1. approved vendor", passed=vendor_ok, detail=why))
    if not vendor_ok:
        failures.append(("Approved-vendor check", why))

    if kept.unit_price is None or kept.sku is None:
        price_ok, why = False, "the unit price or SKU could not be confirmed from the document"
    else:
        limit = hb.catalogue[kept.sku][1]
        price_ok = kept.unit_price <= limit
        why = f"${kept.unit_price:.2f} is {'at or below' if price_ok else 'above'} the ${limit:.2f} max unit cost for {kept.sku}"
    checks.append(CheckResult(check="2. price", passed=price_ok, detail=why))
    if not price_ok:
        failures.append(("Price check", why))

    if kept.lead_time_days is None:
        lead_ok, why = False, "the lead time could not be confirmed from the document"
    else:
        lead_ok = kept.lead_time_days <= hb.max_lead_days
        why = f"{kept.lead_time_days} days is {'within' if lead_ok else 'over'} the {hb.max_lead_days}-day limit"
    checks.append(CheckResult(check="3. lead time", passed=lead_ok, detail=why))
    if not lead_ok:
        failures.append(("Lead-time check", why))

    if kept.min_order is None:
        order_ok, why = False, "the minimum order could not be confirmed from the document"
    else:
        order_ok = kept.min_order <= hb.max_min_order
        why = f"{kept.min_order} units is {'within' if order_ok else 'over'} the {hb.max_min_order}-unit limit"
    checks.append(CheckResult(check="4. minimum order", passed=order_ok, detail=why))
    if not order_ok:
        failures.append(("Minimum-order check", why))

    if failures:
        first, why = failures[0]
        also = [name.split("-check")[0].split(" check")[0].lower() for name, _ in failures[1:]]
        reason = f"{first} failed: {why}" + (f" (also fails: {', '.join(also)})." if also else ".")
        decision = "do_not_recommend"
    else:
        reason = ("All four checks pass: " + "; ".join(c.detail for c in checks if c.check[0].isdigit()) + ".")
        decision = "recommend"
    answer = VendorDecision(vendor=kept.vendor, sku=kept.sku, unit_price=kept.unit_price,
                            lead_time_days=kept.lead_time_days, min_order=kept.min_order,
                            decision=decision, reason=reason)
    return answer, checks
