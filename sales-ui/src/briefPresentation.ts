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
  lastFunding?: LastFundingPrep;
  federalPrimes: FederalPrimeLine[];
};

export type BriefPresentation = {
  title: string;
  track?: string;
  verdict?: string;
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

export function buildBriefPresentation(brief: Record<string, unknown>): BriefPresentation {
  const track = str(brief.track);
  const verdict = str(brief.verdict);
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

    if (whatTheyDo || fedramp || hrPeo || lastFunding || federalPrimes.length > 0) {
      salesPrep = {
        whatTheyDo,
        fedramp,
        hrPeo,
        lastFunding,
        federalPrimes,
      };
    }
  }

  return {
    title: pickBriefTitle(brief),
    track: track ? humanizeUnderscores(track) : undefined,
    verdict: verdict ? humanizeUnderscores(verdict) : undefined,
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
