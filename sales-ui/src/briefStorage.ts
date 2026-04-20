/** Client-only persistence for completed briefs (browser localStorage). */

export const BRIEF_FEED_LS_KEY = "ark-prospect-research.briefFeed.v1";

export type BriefFeedEntry = {
  index: number;
  company: string;
  domain: string | null;
  savedAt: string;
  brief: Record<string, unknown>;
};

export type StoredBriefFeed = {
  version: 1;
  jobId: string;
  filename: string | null;
  entries: BriefFeedEntry[];
};

export function readStoredBriefFeed(): StoredBriefFeed | null {
  try {
    const raw = localStorage.getItem(BRIEF_FEED_LS_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as StoredBriefFeed;
    if (data?.version !== 1 || !Array.isArray(data.entries) || typeof data.jobId !== "string") {
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function writeStoredBriefFeed(data: StoredBriefFeed): void {
  try {
    localStorage.setItem(BRIEF_FEED_LS_KEY, JSON.stringify(data));
  } catch {
    /* quota or private mode */
  }
}

export function clearStoredBriefFeed(): void {
  try {
    localStorage.removeItem(BRIEF_FEED_LS_KEY);
  } catch {
    /* ignore */
  }
}
