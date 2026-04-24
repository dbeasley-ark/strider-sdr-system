"""Public DOL URLs and light classification for Form 5500 FOIA rows."""

from __future__ import annotations

from typing import Literal

# Trace-backed citations for Form 5500 tooling (DOL public disclosure).
DOL_FORM5500_DATASETS_URL = (
    "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/"
    "public-disclosure/foia/form-5500-datasets"
)
EFAST_5500_SEARCH_URL = "https://www.efast.dol.gov/5500Search/"

# Official EFAST2 public filing download (AckId query param).
EFAST_PUBLIC_DOWNLOAD_TEMPLATE = (
    "https://www.askebsa.dol.gov/EFASTPublic/5500/Download.aspx?AckId={ack_id}"
)


def plan_bucket(
    type_pension_bnft_code: str | None,
    type_welfare_bnft_code: str | None,
) -> Literal["pension_dc", "welfare", "combined", "other"]:
    """Coarse bucket from Form 5500 benefit-type code columns (FOIA layout)."""
    p = (type_pension_bnft_code or "").strip()
    w = (type_welfare_bnft_code or "").strip()
    if p and w:
        return "combined"
    if w:
        return "welfare"
    if p:
        return "pension_dc"
    return "other"


def normalize_ein(raw: str | None) -> str:
    """Digits-only EIN (9) for index lookup; empty string if unusable."""
    if not raw:
        return ""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) < 9:
        return ""
    return digits[-9:].zfill(9)
