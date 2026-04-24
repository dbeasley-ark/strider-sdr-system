import ExcelJS from "exceljs";

import { buildBriefPresentation, str, type BriefPresentation } from "./briefPresentation";
import type { BriefFeedEntry } from "./briefStorage";

/** Human-readable column order aligned with PDF brief flow (row context → body → before the call → roles → hooks → raw identifiers). */
export const BRIEF_EXCEL_HEADERS = [
  "Row",
  "Company queried",
  "Domain",
  "Browser saved at",
  "Title",
  "Track",
  "Verdict",
  "Confidence",
  "Rationale",
  "Revenue band",
  "Wall seconds",
  "Cost USD",
  "What they do",
  "What they do (source URL)",
  "FedRAMP status",
  "FedRAMP stage",
  "FedRAMP notes",
  "FedRAMP (source URL)",
  "HR PEO status",
  "HR PEO provider",
  "HR PEO (source URL)",
  "Last funding (round)",
  "Last funding (date)",
  "Last funding confidence",
  "Last funding (source URL)",
  "Federal primes",
  "Target roles",
  "Hooks",
  "Run ID",
  "Generated at (brief)",
  "Revenue estimate source",
  "Revenue estimate rationale",
  "Halt reason",
] as const;

function cellStr(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return "";
}

function humanizeUnderscores(s: string): string {
  return s.replace(/_/g, " ");
}

function federalPrimesBlock(pres: BriefPresentation): string {
  const sp = pres.salesPrep;
  if (!sp?.federalPrimes.length) return "";
  return sp.federalPrimes
    .map((row) => {
      const bits = [
        row.agency_or_context,
        row.amount_or_band ? `— ${row.amount_or_band}` : "",
        row.period_hint ? `(${row.period_hint})` : "",
        row.citation_url ?? "",
      ]
        .filter(Boolean)
        .join(" ");
      return bits.trim();
    })
    .join("\n");
}

function targetRolesBlock(pres: BriefPresentation): string {
  if (!pres.roles.length) return "";
  return pres.roles
    .map((r) => [r.title, r.rationale].filter(Boolean).join(" — "))
    .join("\n");
}

function hooksBlock(pres: BriefPresentation): string {
  if (!pres.hooks.length) return "";
  return pres.hooks
    .map((h) => {
      const t = h.text ?? "";
      const u = h.citation_url ?? "";
      return u ? `${t}\n${u}` : t;
    })
    .join("\n\n");
}

function rawBriefTail(brief: Record<string, unknown>): {
  "Run ID": string;
  "Generated at (brief)": string;
  "Revenue estimate source": string;
  "Revenue estimate rationale": string;
  "Halt reason": string;
} {
  const runId = cellStr(brief.run_id);
  const gen = brief.generated_at;
  let generatedAt = "";
  if (typeof gen === "string") generatedAt = gen;
  else if (gen instanceof Date && !Number.isNaN(gen.getTime())) generatedAt = gen.toISOString();

  const rev = brief.revenue_estimate;
  let revSource = "";
  let revRationale = "";
  if (rev && typeof rev === "object") {
    const r = rev as Record<string, unknown>;
    const src = str(r.source);
    revSource = src ? humanizeUnderscores(src) : "";
    revRationale = str(r.rationale) ?? "";
  }

  const halt = str(brief.halt_reason);
  const haltOut = halt ? humanizeUnderscores(halt) : "";

  return {
    "Run ID": runId,
    "Generated at (brief)": generatedAt,
    "Revenue estimate source": revSource,
    "Revenue estimate rationale": revRationale,
    "Halt reason": haltOut,
  };
}

export function buildBriefExcelRow(entry: BriefFeedEntry): (string | number)[] {
  const pres = buildBriefPresentation(entry.brief);
  const sp = pres.salesPrep;
  const tail = rawBriefTail(entry.brief);

  const wall = pres.wallSeconds;
  const cost = pres.costUsd;

  type RowMap = Record<(typeof BRIEF_EXCEL_HEADERS)[number], string | number>;

  const row: RowMap = {
    Row: entry.index + 1,
    "Company queried": entry.company,
    Domain: entry.domain ?? "",
    "Browser saved at": entry.savedAt,
    Title: pres.title,
    Track: pres.track ?? "",
    Verdict: pres.verdict ?? "",
    Confidence: pres.why ?? "",
    Rationale: pres.rationale ?? "",
    "Revenue band": pres.revBand ?? "",
    "Wall seconds": wall !== undefined ? wall : "",
    "Cost USD": cost !== undefined ? cost : "",
    "What they do": sp?.whatTheyDo?.summary ?? "",
    "What they do (source URL)": sp?.whatTheyDo?.citation_url ?? "",
    "FedRAMP status": sp?.fedramp?.status ?? "",
    "FedRAMP stage": sp?.fedramp?.stage ?? "",
    "FedRAMP notes": sp?.fedramp?.notes ?? "",
    "FedRAMP (source URL)": sp?.fedramp?.citation_url ?? "",
    "HR PEO status": sp?.hrPeo?.status ?? "",
    "HR PEO provider": sp?.hrPeo?.provider_hint ?? "",
    "HR PEO (source URL)": sp?.hrPeo?.citation_url ?? "",
    "Last funding (round)": sp?.lastFunding?.round_label ?? "",
    "Last funding (date)": sp?.lastFunding?.observed_date ?? "",
    "Last funding confidence": sp?.lastFunding?.confidence
      ? humanizeUnderscores(sp.lastFunding.confidence)
      : "",
    "Last funding (source URL)": sp?.lastFunding?.citation_url ?? "",
    "Federal primes": federalPrimesBlock(pres),
    "Target roles": targetRolesBlock(pres),
    Hooks: hooksBlock(pres),
    ...tail,
  };

  return BRIEF_EXCEL_HEADERS.map((h) => row[h]);
}

export async function downloadBriefsExcel(entries: BriefFeedEntry[], filename: string): Promise<void> {
  const sorted = [...entries].sort((a, b) => a.index - b.index);
  const wb = new ExcelJS.Workbook();
  wb.creator = "Strider";
  wb.created = new Date();
  const sheet = wb.addWorksheet("Briefs", {
    views: [{ state: "frozen", ySplit: 1 }],
  });

  sheet.addRow([...BRIEF_EXCEL_HEADERS]);
  const headerRow = sheet.getRow(1);
  headerRow.font = { bold: true };
  headerRow.alignment = { vertical: "top", wrapText: true };

  for (const e of sorted) {
    const values = buildBriefExcelRow(e);
    sheet.addRow(values);
  }

  const wallCol = BRIEF_EXCEL_HEADERS.indexOf("Wall seconds") + 1;
  const costCol = BRIEF_EXCEL_HEADERS.indexOf("Cost USD") + 1;
  for (let r = 2; r <= sheet.rowCount; r++) {
    const row = sheet.getRow(r);
    const w = row.getCell(wallCol).value;
    if (typeof w === "number") row.getCell(wallCol).numFmt = "0";
    const c = row.getCell(costCol).value;
    if (typeof c === "number") row.getCell(costCol).numFmt = "0.00";
    row.alignment = { vertical: "top", wrapText: true };
  }

  sheet.columns.forEach((col) => {
    col.width = 18;
  });

  const name = filename.endsWith(".xlsx") ? filename : `${filename}.xlsx`;
  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
