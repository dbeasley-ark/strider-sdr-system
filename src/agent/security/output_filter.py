"""Output filter: runs on every brief before it leaves the agent.

Two orthogonal responsibilities, combined here because they share the
same "brief about to be returned" choke point:

    1. Compliance scan (§7.3) — scan text fields for classified /
       CUI / ITAR / export-control markings. HARD_STOP markings abort
       the run; WARN markings strip the offending span and force
       verdict=low_confidence.

    2. Citation validation (§7.1) — every hook.citation_url must
       resolve to a URL that actually appeared as a fetched URL or
       a web_search citation in this run's trace. Hooks whose URL
       has no matching tool call are dropped; if that empties the
       hooks list or leaves it sparse, verdict is downgraded.

Runs as a non-LLM pass. That's deliberate: the LLM is the thing we
don't fully trust for security-critical decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from pydantic import HttpUrl

from agent.brief import Brief, FederalPrimeAwardLine, PersonalizationHook, SalesConversationPrep
from agent.security.compliance_keywords import Hit, Severity, has_hard_stop, scan


class ComplianceHardStop(Exception):
    """Raised when the brief contains classified-marking text.

    On §6 policy: the run aborts, no brief is returned, and a
    SECURITY_INCIDENT trace line is written.
    """

    def __init__(self, hits: list[Hit]) -> None:
        labels = sorted({h.pattern_label for h in hits if h.severity is Severity.HARD_STOP})
        super().__init__(f"Compliance hard-stop triggered: {labels}")
        self.hits = hits


@dataclass
class FilterReport:
    """Everything the output filter observed, for the trace."""

    compliance_hits: list[Hit] = field(default_factory=list)
    dropped_hooks: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    dropped_sp_citations: list[tuple[str, str]] = field(
        default_factory=list,
    )  # (url, field path)
    downgraded_verdict: bool = False
    downgrade_reason: str | None = None


def apply_filter(
    brief: Brief,
    *,
    fetched_urls: set[str],
    citation_urls: set[str],
    seed_hosts: set[str] | None = None,
) -> tuple[Brief, FilterReport]:
    """Return (filtered_brief, report).

    Args:
      brief: the LLM-produced brief, already schema-validated by Pydantic.
      fetched_urls: every URL passed to fetch_company_page during this run
        (post-redirect URLs too, so we accept either form).
      citation_urls: every URL surfaced by web_search during this run.
      seed_hosts: registrable-domain hosts from the caller's input
        (the prospect domain). A citation to the company's own site is
        accepted even if no fetch landed on that exact URL — the allowlist
        already guaranteed it was fetchable. Without this, the model got
        credit only for URLs it actively fetched, which punished briefs
        that correctly cited press pages on the prospect's own domain
        (e.g. secondfront.com/resources/news/..., 5 hooks dropped in the
        2026-04-20T21-20-42Z run).

    Raises:
      ComplianceHardStop if a HARD_STOP marker is found anywhere in the
      brief's text surface.
    """
    report = FilterReport()
    seed_hosts = seed_hosts or set()

    # ── 1. Compliance scan on everything the SDR will see ──────────
    compliance_surface = _serialize_for_scan(brief)
    hits = scan(compliance_surface)
    if has_hard_stop(hits):
        # This is the §7.3 classified-markings hard stop. Do NOT return
        # a brief — the caller must abort.
        raise ComplianceHardStop(hits)

    report.compliance_hits = hits

    # ── 2. Citation validation + hook filtering ────────────────────
    allowed = {_normalize_url(u) for u in (fetched_urls | citation_urls)}
    kept_hooks: list[PersonalizationHook] = []
    for hook in brief.hooks:
        url = str(hook.citation_url)
        if _normalize_url(url) in allowed or _host_on_seed(url, seed_hosts):
            kept_hooks.append(hook)
        else:
            report.dropped_hooks.append((url, "url_not_in_trace"))

    # ── 3. Downgrade verdict when the filter significantly altered the brief ──
    downgraded_for_compliance = any(h.severity is Severity.WARN for h in hits)
    downgraded_for_hooks = (
        len(kept_hooks) == 0 and len(brief.hooks) > 0
    ) or (len(kept_hooks) < len(brief.hooks) // 2 and len(brief.hooks) >= 2)

    new_verdict = brief.verdict
    new_why = brief.why_not_confident
    if brief.verdict == "high_confidence" and (downgraded_for_compliance or downgraded_for_hooks):
        new_verdict = "low_confidence"
        reasons = []
        if downgraded_for_compliance:
            reasons.append("compliance scan flagged content")
        if downgraded_for_hooks:
            reasons.append("output validator dropped hooks without trace-backed citations")
        new_why = "; ".join(reasons)
        report.downgraded_verdict = True
        report.downgrade_reason = new_why

    sales_prep = _filter_sales_conversation_prep_urls(
        brief.sales_conversation_prep,
        allowed=allowed,
        seed_hosts=seed_hosts,
        report=report,
    )

    filtered = brief.model_copy(
        update={
            "hooks": kept_hooks,
            "sales_conversation_prep": sales_prep,
            "verdict": new_verdict,
            "why_not_confident": new_why,
        }
    )
    return filtered, report


def _serialize_for_scan(brief: Brief) -> str:
    """Flatten the brief's text surface into one string for scanning."""
    parts: list[str] = [
        brief.rationale,
        brief.why_not_confident or "",
        brief.revenue_estimate.rationale,
    ]
    parts.extend(r.rationale for r in brief.target_roles)
    parts.extend(r.title for r in brief.target_roles)
    parts.extend(h.text for h in brief.hooks)
    sp = brief.sales_conversation_prep
    parts.append(sp.what_they_do.summary)
    if sp.fedramp_posture.notes:
        parts.append(sp.fedramp_posture.notes)
    if sp.fedramp_posture.stage:
        parts.append(sp.fedramp_posture.stage)
    if sp.hr_peo.provider_hint:
        parts.append(sp.hr_peo.provider_hint)
    if sp.last_funding.round_label:
        parts.append(sp.last_funding.round_label)
    for a in sp.federal_prime_awards:
        parts.append(a.agency_or_context)
        parts.append(a.amount_or_band)
        if a.period_hint:
            parts.append(a.period_hint)
    return "\n".join(parts)


def _url_citation_allowed(
    url: str, *, allowed: set[str], seed_hosts: set[str]
) -> bool:
    return _normalize_url(url) in allowed or _host_on_seed(url, seed_hosts)


def _filter_sales_conversation_prep_urls(
    prep: SalesConversationPrep,
    *,
    allowed: set[str],
    seed_hosts: set[str],
    report: FilterReport,
) -> SalesConversationPrep:
    """Drop sales_prep citation_url values not present in the trace."""

    def _strip_bad_citation(url: HttpUrl | None, field: str) -> HttpUrl | None:
        if url is None:
            return None
        s = str(url)
        if _url_citation_allowed(s, allowed=allowed, seed_hosts=seed_hosts):
            return url
        report.dropped_sp_citations.append((s, field))
        return None

    wd = prep.what_they_do
    new_wd = wd.model_copy(
        update={"citation_url": _strip_bad_citation(wd.citation_url, "sales_prep.what_they_do")}
    )

    fp = prep.fedramp_posture
    new_fp = fp.model_copy(
        update={
            "citation_url": _strip_bad_citation(
                fp.citation_url, "sales_prep.fedramp_posture"
            ),
        }
    )

    hp = prep.hr_peo
    new_hp = hp.model_copy(
        update={"citation_url": _strip_bad_citation(hp.citation_url, "sales_prep.hr_peo")}
    )

    lf = prep.last_funding
    new_lf = lf.model_copy(
        update={
            "citation_url": _strip_bad_citation(lf.citation_url, "sales_prep.last_funding"),
        }
    )

    new_awards: list[FederalPrimeAwardLine] = []
    for i, a in enumerate(prep.federal_prime_awards):
        new_awards.append(
            a.model_copy(
                update={
                    "citation_url": _strip_bad_citation(
                        a.citation_url,
                        f"sales_prep.federal_prime_awards[{i}]",
                    ),
                }
            )
        )

    return SalesConversationPrep(
        what_they_do=new_wd,
        fedramp_posture=new_fp,
        hr_peo=new_hp,
        last_funding=new_lf,
        federal_prime_awards=new_awards,
    )


def _normalize_url(url: str) -> str:
    """Lower-case scheme + host; drop trailing slash and fragment.

    We intentionally KEEP the path and query — two different pages on the
    same host are not the same citation. The loose rule is: the LLM must
    cite a URL that a tool actually touched.
    """
    p = urlparse(url.strip())
    scheme = p.scheme.lower() or "https"
    netloc = p.netloc.lower()
    path = p.path.rstrip("/")
    query = f"?{p.query}" if p.query else ""
    return f"{scheme}://{netloc}{path}{query}"


def _host_on_seed(url: str, seed_hosts: set[str]) -> bool:
    """True if the URL's host matches any seed host (or a subdomain).

    Mirrors `UrlAllowlist.allows` semantics: `www.example.com` matches a
    seed of `example.com`; `notexample.com` does not.
    """
    if not seed_hosts:
        return False
    host = urlparse(url.strip()).hostname or ""
    host = host.lower()
    if not host:
        return False
    return any(host == h or host.endswith(f".{h}") for h in seed_hosts)
