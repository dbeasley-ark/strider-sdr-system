import { Font, pdf } from "@react-pdf/renderer";

import type { BriefFeedEntry } from "../briefStorage";
import { buildBriefPresentation } from "../briefPresentation";
import BriefPdfDocument, { type BriefPdfInput } from "./BriefPdfDocument";

const DM_SANS_400 =
  "https://unpkg.com/@fontsource/dm-sans@5.0.21/files/dm-sans-latin-400-normal.woff";
const DM_SANS_700 =
  "https://unpkg.com/@fontsource/dm-sans@5.0.21/files/dm-sans-latin-700-normal.woff";

let fontsRegistered = false;

function ensureFonts(): void {
  if (fontsRegistered) return;
  try {
    Font.register({
      family: "DM Sans",
      fonts: [
        { src: DM_SANS_400, fontWeight: 400 },
        { src: DM_SANS_700, fontWeight: 700 },
      ],
    });
  } catch {
    /* duplicate registration (e.g. HMR) */
  }
  fontsRegistered = true;
}

function triggerDownload(blob: Blob, filename: string): void {
  const name = filename.endsWith(".pdf") ? filename : `${filename}.pdf`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function briefFeedToPdfInputs(entries: BriefFeedEntry[]): BriefPdfInput[] {
  return entries.map((e) => ({
    rowNumber: e.index + 1,
    companyQueried: e.company,
    domain: e.domain,
    savedAt: e.savedAt,
    pres: buildBriefPresentation(e.brief),
  }));
}

export async function downloadBriefPdf(input: BriefPdfInput, filename: string): Promise<void> {
  ensureFonts();
  const blob = await pdf(<BriefPdfDocument entries={[input]} />).toBlob();
  triggerDownload(blob, filename);
}

export async function downloadBriefPdfBundle(
  entries: BriefPdfInput[],
  filename: string,
): Promise<void> {
  if (!entries.length) return;
  ensureFonts();
  const blob = await pdf(<BriefPdfDocument entries={entries} />).toBlob();
  triggerDownload(blob, filename);
}
