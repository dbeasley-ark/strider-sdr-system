import ExcelJS from "exceljs";

import { buildBriefPresentation, str, type BriefPresentation } from "./briefPresentation";
import type { BriefFeedEntry } from "./briefStorage";

/** Arkenstone palette (see docs/ARKENSTONE_DESIGN_SYSTEM.md). Excel ARGB: AARRGGBB. */
const ARK = {
  brandBlack: "FF161616",
  brandBone: "FFE8E4D4",
  brandWhite: "FFFFFFFF",
  olive900: "FF1F2414",
  olive800: "FF2A3120",
  olive700: "FF414C32",
  orange500: "FFE85D2C",
  fgMuted: "FFA8A392",
  borderLight: "FFD4D4D4",
} as const;

const BRIEF_SHEET_BANNER_ROWS = 2;
const BRIEF_SHEET_HEADER_ROW = BRIEF_SHEET_BANNER_ROWS + 1;

function briefSheetHeaderLabels(): string[] {
  return BRIEF_EXCEL_HEADERS.map((h) => h.toUpperCase());
}

/** Human-readable column order aligned with PDF brief flow (row context → body → before the call → roles → hooks → raw identifiers). */
export const BRIEF_EXCEL_HEADERS = [
  "Row",
  "Company queried",
  "Domain",
  "Browser saved at",
  "Title",
  "Federal revenue posture",
  "Research confidence (federal posture)",
  "Why not higher confidence",
  "Buyer tier (playbook)",
  "Lead priority (playbook)",
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
  "Form 5500 signal",
  "Form 5500 DC summary",
  "Form 5500 health/welfare summary",
  "Form 5500 participant scale",
  "Form 5500 admin hint",
  "Form 5500 MEP schedule",
  "Form 5500 confidence",
  "Form 5500 limitations",
  "Form 5500 (source URL)",
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
    "Federal revenue posture": pres.federalPostureDisplay ?? pres.track ?? "",
    "Research confidence (federal posture)":
      pres.postureConfidenceDisplay ?? pres.verdict ?? "",
    "Why not higher confidence": pres.why ?? "",
    "Buyer tier (playbook)": pres.buyerTierPlaybook ?? "",
    "Lead priority (playbook)": pres.leadPriorityPlaybook ?? "",
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
    "Form 5500 signal": sp?.form5500Benefits?.signal_source ?? "",
    "Form 5500 DC summary": sp?.form5500Benefits?.dc_retirement_summary ?? "",
    "Form 5500 health/welfare summary": sp?.form5500Benefits?.group_health_welfare_summary ?? "",
    "Form 5500 participant scale": sp?.form5500Benefits?.participant_scale_hint ?? "",
    "Form 5500 admin hint": sp?.form5500Benefits?.administrator_or_service_provider_hint ?? "",
    "Form 5500 MEP schedule":
      sp?.form5500Benefits?.multi_employer_plan_schedule === undefined
        ? ""
        : String(sp.form5500Benefits.multi_employer_plan_schedule),
    "Form 5500 confidence": sp?.form5500Benefits?.confidence ?? "",
    "Form 5500 limitations": sp?.form5500Benefits?.limitations ?? "",
    "Form 5500 (source URL)": sp?.form5500Benefits?.citation_url ?? "",
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
  wb.creator = "Arkenstone Defense";
  wb.company = "Arkenstone Defense";
  wb.created = new Date();

  const colCount = BRIEF_EXCEL_HEADERS.length;
  const sheet = wb.addWorksheet("Briefs", {
    views: [{ state: "frozen", ySplit: BRIEF_SHEET_HEADER_ROW }],
  });

  sheet.mergeCells(1, 1, 1, colCount);
  const titleCell = sheet.getCell(1, 1);
  titleCell.value = "ARKENSTONE DEFENSE";
  titleCell.font = { name: "DM Sans", size: 16, bold: true, color: { argb: ARK.brandBone } };
  titleCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: ARK.olive800 } };
  titleCell.alignment = { vertical: "middle", horizontal: "left", indent: 1 };
  sheet.getRow(1).height = 36;

  sheet.mergeCells(2, 1, 2, colCount);
  const subCell = sheet.getCell(2, 1);
  const exportedAt = new Date().toISOString().replace("T", " ").slice(0, 19);
  subCell.value = {
    richText: [
      {
        font: { name: "DM Mono", size: 10, color: { argb: ARK.orange500 } },
        text: "PROSPECT BRIEFS",
      },
      {
        font: { name: "DM Mono", size: 10, color: { argb: ARK.fgMuted } },
        text: `  ·  EXPORTED ${exportedAt} UTC`,
      },
    ],
  };
  subCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: ARK.olive900 } };
  subCell.alignment = { vertical: "middle", horizontal: "left", indent: 1, wrapText: true };
  sheet.getRow(2).height = 26;

  sheet.addRow([...briefSheetHeaderLabels()]);
  const headerRow = sheet.getRow(BRIEF_SHEET_HEADER_ROW);
  headerRow.font = { name: "DM Mono", size: 9, bold: false, color: { argb: ARK.brandBlack } };
  headerRow.fill = { type: "pattern", pattern: "solid", fgColor: { argb: ARK.brandBone } };
  headerRow.alignment = { vertical: "top", wrapText: true };
  for (let c = 1; c <= colCount; c++) {
    const cell = headerRow.getCell(c);
    cell.border = {
      bottom: { style: "thin", color: { argb: ARK.brandBlack } },
    };
  }
  headerRow.height = 22;

  for (const e of sorted) {
    const values = buildBriefExcelRow(e);
    sheet.addRow(values);
  }

  const wallCol = BRIEF_EXCEL_HEADERS.indexOf("Wall seconds") + 1;
  const costCol = BRIEF_EXCEL_HEADERS.indexOf("Cost USD") + 1;
  const firstDataRow = BRIEF_SHEET_HEADER_ROW + 1;
  for (let r = firstDataRow; r <= sheet.rowCount; r++) {
    const row = sheet.getRow(r);
    const w = row.getCell(wallCol).value;
    if (typeof w === "number") row.getCell(wallCol).numFmt = "0";
    const c = row.getCell(costCol).value;
    if (typeof c === "number") row.getCell(costCol).numFmt = "0.00";
    row.alignment = { vertical: "top", wrapText: true };
    row.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      if (colNumber > colCount) return;
      cell.font = { name: "DM Sans", size: 11, color: { argb: ARK.brandBlack } };
      cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: ARK.brandWhite } };
      cell.border = {
        bottom: { style: "thin", color: { argb: ARK.borderLight } },
      };
    });
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
