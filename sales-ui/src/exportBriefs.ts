import type { BriefFeedEntry } from "./briefStorage";

export type RowWithBrief = {
  index: number;
  company: string;
  domain: string | null;
  brief?: Record<string, unknown> | null;
};

const MAX_SEGMENT = 60;

/** Safe single path segment for download filenames (cross-platform). */
export function safeFileSegment(raw: string): string {
  const s = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_SEGMENT);
  return s || "brief";
}

export function downloadJsonFile(filename: string, data: unknown): void {
  const name = filename.endsWith(".json") ? filename : `${filename}.json`;
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function buildSingleBriefPayload(entry: BriefFeedEntry): BriefFeedEntry {
  return {
    index: entry.index,
    company: entry.company,
    domain: entry.domain,
    savedAt: entry.savedAt,
    brief: entry.brief,
  };
}

export function buildBriefBundlePayload(
  jobId: string,
  sourceFilename: string | null,
  entries: BriefFeedEntry[],
): {
  export_version: 1;
  exported_at: string;
  job_id: string;
  source_filename: string | null;
  entries: BriefFeedEntry[];
} {
  return {
    export_version: 1,
    exported_at: new Date().toISOString(),
    job_id: jobId,
    source_filename: sourceFilename,
    entries: entries.map((e) => buildSingleBriefPayload(e)),
  };
}

/**
 * Prefer briefFeed order; add any row with a brief whose index is missing
 * (e.g. snapshot arrived without a matching stream brief entry).
 */
export function collectExportableEntries(
  briefFeed: BriefFeedEntry[],
  rows: RowWithBrief[],
): BriefFeedEntry[] {
  const byIndex = new Map<number, BriefFeedEntry>();
  for (const e of briefFeed) {
    byIndex.set(e.index, e);
  }
  for (const r of rows) {
    if (r.brief == null || typeof r.brief !== "object") continue;
    if (byIndex.has(r.index)) continue;
    byIndex.set(r.index, {
      index: r.index,
      company: r.company,
      domain: r.domain,
      savedAt: new Date().toISOString(),
      brief: r.brief,
    });
  }
  return [...byIndex.values()].sort((a, b) => a.index - b.index);
}

export function singleBriefFilename(entry: BriefFeedEntry): string {
  const slug = safeFileSegment(entry.company);
  return `brief-${slug}-row${entry.index + 1}.json`;
}

export function bundleBriefsFilename(jobId: string, jobName: string | null): string {
  const label = jobName ? safeFileSegment(jobName.replace(/\.[^.]+$/, "")) : safeFileSegment(jobId.slice(0, 8));
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  return `briefs-${label}-${stamp}.json`;
}
