/** Normalized brief fields for UI + PDF (single source of truth). */

export function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

export function pickBriefTitle(b: Record<string, unknown>): string {
  return str(b.company_name_canonical) || str(b.company_name_queried) || "Prospect brief";
}

export type FederalPrimeLine = {
  agency_or_context: string;
  amount_or_band?: string;
  period_hint?: string;
  citation_url?: string;
};

export type TargetRoleLine = {
  title?: string;
  rationale?: string;
};

export type HookLine = {
  text?: string;
  citation_url?: string;
};

export type WhatTheyDoPrep = {
  summary: string;
  citation_url?: string;
};

export type FedrampPrep = {
  status: string;
  stage?: string;
  notes?: string;
  citation_url?: string;
};

export type HrPeoPrep = {
  status: string;
  provider_hint?: string;
  citation_url?: string;
};

export type Form5500BenefitsPrep = {
  signal_source?: string;
  dc_retirement_summary?: string;
  group_health_welfare_summary?: string;
  participant_scale_hint?: string;
  administrator_or_service_provider_hint?: string;
  multi_employer_plan_schedule?: boolean;
  citation_url?: string;
  confidence?: string;
  limitations?: string;
};

export type LastFundingPrep = {
  round_label?: string;
  observed_date?: string;
  confidence?: string;
  citation_url?: string;
};

export type SalesPrepPresentation = {
  whatTheyDo?: WhatTheyDoPrep;
  fedramp?: FedrampPrep;
  hrPeo?: HrPeoPrep;
  form5500Benefits?: Form5500BenefitsPrep;
  lastFunding?: LastFundingPrep;
  federalPrimes: FederalPrimeLine[];
};

export type BriefPresentation = {
  title: string;
  /** @deprecated use federalPostureDisplay */
  track?: string;
  federalPostureDisplay?: string;
  /** Buyer tier + lead priority for compact UI (e.g. card header tag row). */
  tiersDisplay?: string;
  /** @deprecated use postureConfidenceDisplay */
  verdict?: string;
  postureConfidenceDisplay?: string;
  buyerTierPlaybook?: string;
  leadPriorityPlaybook?: string;
  rationale?: string;
  why?: string;
  revBand?: string;
  wallSeconds?: number;
  costUsd?: number;
  salesPrep: SalesPrepPresentation | null;
  roles: TargetRoleLine[];
  hooks: HookLine[];
};

function humanizeUnderscores(s: string): string {
  return s.replace(/_/g, " ");
}

/** Playbook Part 2 tier titles (verbatim phrasing from arkenstone_sales_playbook_master). */
export function playbookBuyerTierLabel(tier: string | undefined): string | undefined {
  if (!tier) return undefined;
  switch (tier) {
    case "tier_1_strike_zone":
      return "Tier 1 — Strike Zone";
    case "tier_2_displacement":
      return "Tier 2 — Displacement";
    case "tier_3_future_growth":
      return "Tier 3 — Future Growth";
    default:
      return undefined;
  }
}

export function formatFederalPostureLabel(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  switch (raw) {
    case "sponsorship_in_hand":
      return "Federal posture: sponsorship in hand";
    case "pre_sponsorship_path":
      return "Federal posture: pre-sponsorship path";
    case "not_in_federal_icp":
      return "Federal posture: not in federal revenue segment";
    case "track_1":
      return "Federal posture: sponsorship in hand (legacy)";
    case "track_2":
      return "Federal posture: pre-sponsorship path (legacy)";
    case "neither":
      return "Federal posture: not in federal revenue segment (legacy)";
    default:
      return humanizeUnderscores(raw);
  }
}

/** Maps agent `verdict` to SDR-facing label (playbook uses P1–P3 for timing, not this field). */
function postureConfidenceDisplay(verdict: string | undefined): string | undefined {
  if (!verdict) return undefined;
  switch (verdict) {
    case "high_confidence":
      return "Research confidence: high";
    case "medium_confidence":
      return "Research confidence: medium";
    case "low_confidence":
      return "Research confidence: low";
    case "insufficient_data":
      return "Research confidence: insufficient data";
    default:
      return humanizeUnderscores(verdict);
  }
}

function leadPriorityPlaybookLabel(p: string | undefined): string | undefined {
  if (!p) return undefined;
  if (p === "unknown") return "Lead priority: unknown";
  const table: Record<string, string> = {
    p1: "P1 — same-day (playbook: Tier 1 + DoD + CMMC gap + renewal <90d, or referral)",
    p2: "P2 — within 24h (playbook: Tier 1–2 + contract + compliance exposure)",
    p3: "P3 — within 48h (playbook: Tier 3 / SBIR or longer horizon)",
  };
  return table[p] ?? humanizeUnderscores(p);
}

export function buildBriefPresentation(brief: Record<string, unknown>): BriefPresentation {
  const postureRaw =
    str(brief.federal_revenue_posture) ?? str(brief.track);
  const verdict = str(brief.verdict);
  const buyerTierRaw = str(brief.buyer_tier);
  const priorityRaw = str(brief.suggested_contact_priority);
  const rationale = str(brief.rationale);
  const why = str(brief.why_not_confident);
  const rev = brief.revenue_estimate as Record<string, unknown> | undefined;
  const revBand = rev ? str(rev.band) : undefined;
  const roles = Array.isArray(brief.target_roles)
    ? (brief.target_roles as Record<string, unknown>[])
    : [];
  const hooks = Array.isArray(brief.hooks) ? (brief.hooks as Record<string, unknown>[]) : [];
  const wall = typeof brief.wall_seconds === "number" ? brief.wall_seconds : undefined;
  const cost = typeof brief.cost_usd === "number" ? brief.cost_usd : undefined;

  const salesPrepRaw =
    brief.sales_conversation_prep && typeof brief.sales_conversation_prep === "object"
      ? (brief.sales_conversation_prep as Record<string, unknown>)
      : null;

  let salesPrep: SalesPrepPresentation | null = null;
  if (salesPrepRaw) {
    const wtd = salesPrepRaw.what_they_do as Record<string, unknown> | undefined;
    const summary = wtd ? str(wtd.summary) : undefined;
    const whatTheyDo: WhatTheyDoPrep | undefined =
      summary != null && summary.length > 0
        ? { summary, citation_url: wtd ? str(wtd.citation_url) : undefined }
        : undefined;

    const fr = salesPrepRaw.fedramp_posture as Record<string, unknown> | undefined;
    const fst = fr ? str(fr.status) : undefined;
    const fedramp: FedrampPrep | undefined =
      fst != null
        ? {
            status: humanizeUnderscores(fst),
            stage: fr ? str(fr.stage) : undefined,
            notes: fr ? str(fr.notes) : undefined,
            citation_url: fr ? str(fr.citation_url) : undefined,
          }
        : undefined;

    const hr = salesPrepRaw.hr_peo as Record<string, unknown> | undefined;
    const hst = hr ? str(hr.status) : undefined;
    const hrPeo: HrPeoPrep | undefined =
      hst != null
        ? {
            status: humanizeUnderscores(hst),
            provider_hint: hr ? str(hr.provider_hint) : undefined,
            citation_url: hr ? str(hr.citation_url) : undefined,
          }
        : undefined;

    const f5raw = salesPrepRaw.form_5500_benefits as Record<string, unknown> | undefined;
    const f5src = f5raw ? str(f5raw.signal_source) : undefined;
    const form5500Benefits: Form5500BenefitsPrep | undefined =
      f5raw &&
      (f5src != null ||
        str(f5raw.dc_retirement_summary) ||
        str(f5raw.group_health_welfare_summary) ||
        str(f5raw.administrator_or_service_provider_hint) ||
        str(f5raw.limitations))
        ? {
            signal_source: f5src ? humanizeUnderscores(f5src) : undefined,
            dc_retirement_summary: str(f5raw.dc_retirement_summary),
            group_health_welfare_summary: str(f5raw.group_health_welfare_summary),
            participant_scale_hint: f5raw.participant_scale_hint
              ? humanizeUnderscores(str(f5raw.participant_scale_hint))
              : undefined,
            administrator_or_service_provider_hint: str(
              f5raw.administrator_or_service_provider_hint,
            ),
            multi_employer_plan_schedule:
              typeof f5raw.multi_employer_plan_schedule === "boolean"
                ? f5raw.multi_employer_plan_schedule
                : undefined,
            citation_url: str(f5raw.citation_url),
            confidence: f5raw.confidence
              ? humanizeUnderscores(str(f5raw.confidence))
              : undefined,
            limitations: str(f5raw.limitations),
          }
        : undefined;

    const lf = salesPrepRaw.last_funding as Record<string, unknown> | undefined;
    const round = lf ? str(lf.round_label) : undefined;
    const dt = lf ? str(lf.observed_date) : undefined;
    const conf = lf ? str(lf.confidence) : undefined;
    const lUrl = lf ? str(lf.citation_url) : undefined;
    const lastFunding: LastFundingPrep | undefined =
      round != null || dt != null || conf === "unknown" || lUrl != null
        ? {
            round_label: round,
            observed_date: dt,
            confidence: conf,
            citation_url: lUrl,
          }
        : undefined;

    const awardsRaw = salesPrepRaw.federal_prime_awards;
    const federalPrimes: FederalPrimeLine[] = Array.isArray(awardsRaw)
      ? (awardsRaw as Record<string, unknown>[]).map((row) => ({
          agency_or_context: str(row.agency_or_context) ?? "—",
          amount_or_band: str(row.amount_or_band),
          period_hint: str(row.period_hint),
          citation_url: str(row.citation_url),
        }))
      : [];

    if (
      whatTheyDo ||
      fedramp ||
      hrPeo ||
      form5500Benefits ||
      lastFunding ||
      federalPrimes.length > 0
    ) {
      salesPrep = {
        whatTheyDo,
        fedramp,
        hrPeo,
        form5500Benefits,
        lastFunding,
        federalPrimes,
      };
    }
  }

  const buyerTierPlaybook = playbookBuyerTierLabel(buyerTierRaw);
  const leadPriorityPlaybook = leadPriorityPlaybookLabel(priorityRaw);
  const tierParts = [buyerTierPlaybook, leadPriorityPlaybook].filter(Boolean) as string[];
  const tiersDisplay = tierParts.length > 0 ? tierParts.join(" · ") : undefined;

  return {
    title: pickBriefTitle(brief),
    track: postureRaw ? humanizeUnderscores(postureRaw) : undefined,
    federalPostureDisplay: formatFederalPostureLabel(postureRaw),
    tiersDisplay,
    verdict: verdict ? humanizeUnderscores(verdict) : undefined,
    postureConfidenceDisplay: postureConfidenceDisplay(verdict),
    buyerTierPlaybook,
    leadPriorityPlaybook,
    rationale,
    why,
    revBand: revBand ? humanizeUnderscores(revBand) : undefined,
    wallSeconds: wall,
    costUsd: cost,
    salesPrep,
    roles: roles.map((role) => ({
      title: str(role.title),
      rationale: str(role.rationale),
    })),
    hooks: hooks.map((h) => ({
      text: str(h.text),
      citation_url: str(h.citation_url),
    })),
  };
}
