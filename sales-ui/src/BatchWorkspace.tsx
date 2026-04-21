import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import BriefCard from "./BriefCard";
import {
  readStoredBriefFeed,
  type BriefFeedEntry,
  writeStoredBriefFeed,
} from "./briefStorage";
import {
  buildBriefBundlePayload,
  bundleBriefsFilename,
  collectExportableEntries,
  downloadJsonFile,
} from "./exportBriefs";

type ApiRow = {
  index: number;
  company: string;
  domain: string | null;
};

type RowView = ApiRow & {
  status: "pending" | "running" | "ok" | "error";
  track?: string;
  verdict?: string;
  error?: string;
  brief?: Record<string, unknown> | null;
};

type BatchCreateResponse = {
  job_id: string;
  filename: string;
  row_count: number;
  rows: ApiRow[];
};

type StreamEvent =
  | { type: "job_started"; job_id: string; total: number; filename: string }
  | { type: "row_started"; index: number; company: string; domain: string | null }
  | {
      type: "row_complete";
      index: number;
      company: string;
      domain?: string | null;
      status: string;
      exit_code?: number;
      track?: string;
      verdict?: string;
      error?: string;
      brief?: Record<string, unknown> | null;
    }
  | { type: "job_complete"; job_id: string; ok: number; error: number };

function applyEvent(rows: RowView[], ev: StreamEvent): RowView[] {
  const next = rows.map((r) => ({ ...r }));
  if (ev.type === "row_started") {
    const r = next.find((x) => x.index === ev.index);
    if (r) r.status = "running";
    return next;
  }
  if (ev.type === "row_complete") {
    const r = next.find((x) => x.index === ev.index);
    if (r) {
      r.status = ev.status === "ok" ? "ok" : "error";
      r.track = ev.track;
      r.verdict = ev.verdict;
      r.error = ev.error;
      if (ev.brief != null && typeof ev.brief === "object") {
        r.brief = ev.brief;
      }
    }
    return next;
  }
  return next;
}

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename.replace(/\.[^.]+$/, "") + "-results.json";
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function BatchWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [companyCol, setCompanyCol] = useState("");
  const [domainCol, setDomainCol] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [rows, setRows] = useState<RowView[]>([]);
  const [jobName, setJobName] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const [drag, setDrag] = useState(false);
  const [briefFeed, setBriefFeed] = useState<BriefFeedEntry[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const stored = readStoredBriefFeed();
    if (stored?.entries?.length) {
      setBriefFeed(stored.entries);
      if (stored.jobId) {
        setJobId(stored.jobId);
      }
      if (stored.filename != null) {
        setJobName(stored.filename);
      }
    }
    return () => {
      esRef.current?.close();
    };
  }, []);

  const [singleCompany, setSingleCompany] = useState("");
  const [singleWebsite, setSingleWebsite] = useState("");
  const [singlePocName, setSinglePocName] = useState("");
  const [singlePocTitle, setSinglePocTitle] = useState("");

  const listenStream = useCallback((id: string, initial: RowView[], batchFilename: string) => {
    esRef.current?.close();
    const es = new EventSource(`/api/batches/${id}/stream`);
    esRef.current = es;
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as StreamEvent;
        if (ev.type === "row_started" || ev.type === "row_complete") {
          setRows((prev) => applyEvent(prev.length ? prev : initial, ev));
        }
        if (ev.type === "row_complete" && ev.brief != null && typeof ev.brief === "object") {
          const entry: BriefFeedEntry = {
            index: ev.index,
            company: ev.company,
            domain: ev.domain ?? null,
            savedAt: new Date().toISOString(),
            brief: ev.brief,
          };
          setBriefFeed((prev) => {
            const pos = prev.findIndex((p) => p.index === entry.index);
            const next =
              pos >= 0
                ? prev.map((p, i) => (i === pos ? entry : p))
                : [...prev, entry];
            writeStoredBriefFeed({
              version: 1,
              jobId: id,
              filename: batchFilename,
              entries: next,
            });
            return next;
          });
        }
        if (ev.type === "job_complete") {
          setFinished(true);
          es.close();
          void (async () => {
            const res = await fetch(`/api/batches/${id}`);
            if (res.ok) {
              const snap = await res.json();
              setRows(
                snap.rows.map(
                  (r: {
                    index: number;
                    company: string;
                    domain: string | null;
                    status: string;
                    track?: string;
                    verdict?: string;
                    error?: string;
                    brief?: Record<string, unknown> | null;
                  }) => ({
                    index: r.index,
                    company: r.company,
                    domain: r.domain,
                    status: r.status as RowView["status"],
                    track: r.track,
                    verdict: r.verdict,
                    error: r.error,
                    brief: r.brief ?? undefined,
                  }),
                ),
              );
            }
          })();
        }
      } catch {
        /* ignore malformed chunks */
      }
    };
    es.onerror = () => {
      es.close();
    };
  }, []);

  const beginJob = useCallback(
    (data: BatchCreateResponse) => {
      setJobId(data.job_id);
      setJobName(data.filename);
      writeStoredBriefFeed({
        version: 1,
        jobId: data.job_id,
        filename: data.filename,
        entries: [],
      });
      setBriefFeed([]);
      const initial: RowView[] = data.rows.map((r) => ({
        ...r,
        status: "pending" as const,
      }));
      setRows(initial);
      listenStream(data.job_id, initial, data.filename);
    },
    [listenStream],
  );

  const onSubmitSingle = async (e: React.FormEvent) => {
    e.preventDefault();
    const company = singleCompany.trim();
    if (!company) return;
    setErr(null);
    setBusy(true);
    setFinished(false);
    setJobId(null);
    setRows([]);
    try {
      const res = await fetch("/api/single", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company,
          website: singleWebsite.trim() || null,
          poc_name: singlePocName.trim() || null,
          poc_title: singlePocTitle.trim() || null,
        }),
      });
      const text = await res.text();
      if (!res.ok) {
        let msg = text || res.statusText;
        try {
          const j = JSON.parse(text) as { detail?: string | unknown };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          /* keep msg */
        }
        throw new Error(msg);
      }
      const data = JSON.parse(text) as BatchCreateResponse;
      beginJob(data);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setErr(null);
    setBusy(true);
    setFinished(false);
    setJobId(null);
    setRows([]);
    const fd = new FormData();
    fd.append("file", file);
    if (companyCol.trim()) fd.append("company_column", companyCol.trim());
    if (domainCol.trim()) fd.append("domain_column", domainCol.trim());
    try {
      const res = await fetch("/api/batches", { method: "POST", body: fd });
      const text = await res.text();
      if (!res.ok) {
        let msg = text || res.statusText;
        try {
          const j = JSON.parse(text) as { detail?: string };
          if (j.detail) msg = j.detail;
        } catch {
          /* keep msg */
        }
        throw new Error(msg);
      }
      const data = JSON.parse(text) as BatchCreateResponse;
      beginJob(data);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  };

  const onExport = async () => {
    if (!jobId) return;
    const res = await fetch(`/api/batches/${jobId}`);
    if (!res.ok) return;
    const snap = await res.json();
    downloadJson(jobName || "batch", snap);
  };

  const onExportAllBriefs = useCallback(() => {
    const stored = readStoredBriefFeed();
    const entries = collectExportableEntries(briefFeed, rows);
    if (!entries.length) return;
    const jid = jobId ?? stored?.jobId ?? "unknown";
    const jname = jobName ?? stored?.filename ?? null;
    downloadJsonFile(
      bundleBriefsFilename(jid, jname),
      buildBriefBundlePayload(jid, jname, entries),
    );
  }, [briefFeed, rows, jobId, jobName]);

  const exportableBriefEntries = useMemo(
    () => collectExportableEntries(briefFeed, rows),
    [briefFeed, rows],
  );

  return (
    <>
      <div className="workspace-head">
        <div className="workspace-head-text">
          <h1 className="workspace-title">Prospect research</h1>
          <p className="muted workspace-sub">
            Run one company from the form below, or upload a list. Rows run in order; briefs appear
            as each row finishes. Spreadsheet company and domain columns auto-detect from common
            headers when left blank.
          </p>
        </div>
      </div>

      {err ? <div className="err-banner">{err}</div> : null}

      <form className="card card--workspace" onSubmit={onSubmitSingle}>
        <h3 className="h3 card-title">Single run</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Company name is required. Website improves domain allowlist seeding. Point of contact and
          position are optional rep context (not verified by the agent).
        </p>
        <div className="field-grid">
          <label className="field">
            Company name
            <input
              value={singleCompany}
              onChange={(e) => setSingleCompany(e.target.value)}
              placeholder="e.g. Acme Industries"
              autoComplete="organization"
            />
          </label>
          <label className="field">
            Website
            <input
              value={singleWebsite}
              onChange={(e) => setSingleWebsite(e.target.value)}
              placeholder="e.g. https://www.acme.com"
              autoComplete="url"
            />
          </label>
          <label className="field">
            Point of contact
            <input
              value={singlePocName}
              onChange={(e) => setSinglePocName(e.target.value)}
              placeholder="Optional"
              autoComplete="name"
            />
          </label>
          <label className="field">
            Position
            <input
              value={singlePocTitle}
              onChange={(e) => setSinglePocTitle(e.target.value)}
              placeholder="Optional (e.g. VP Engineering)"
            />
          </label>
        </div>
        <div className="actions">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={!singleCompany.trim() || busy}
          >
            {busy ? "Starting…" : "Run research"}
          </button>
        </div>
      </form>

      <form className="card card--workspace" onSubmit={onSubmit}>
        <h3 className="h3 card-title">Import</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          UTF-8 CSV or TXT (comma-separated) or XLSX · header row required · up to 500 rows
        </p>

        <label
          className={`dropzone ${drag ? "drag" : ""}`}
          onDragEnter={() => setDrag(true)}
          onDragLeave={() => setDrag(false)}
          onDragOver={(e) => {
            e.preventDefault();
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files[0];
            if (f) setFile(f);
          }}
        >
          <input
            type="file"
            accept=".csv,.txt,.xlsx,.xlsm"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) setFile(f);
            }}
          />
          <div className="dropzone-inner">
            <span className="dropzone-kicker">File</span>
            {file ? (
              <>
                <span className="dropzone-ready">Ready</span>
                <span className="dropzone-filename" title={file.name}>
                  {file.name}
                </span>
              </>
            ) : (
              <>
                <span className="dropzone-title">Drop a file here</span>
                <span className="dropzone-sub">or click to browse</span>
                <span className="dropzone-formats">.csv · .txt · .xlsx · .xlsm</span>
              </>
            )}
          </div>
        </label>

        <div className="field-grid">
          <label className="field">
            Company column (optional)
            <input
              value={companyCol}
              onChange={(e) => setCompanyCol(e.target.value)}
              placeholder="Auto-detect from header"
            />
          </label>
          <label className="field">
            Domain column (optional)
            <input
              value={domainCol}
              onChange={(e) => setDomainCol(e.target.value)}
              placeholder="Auto-detect from header"
            />
          </label>
        </div>

        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={!file || busy}>
            {busy ? "Starting…" : "Run batch"}
          </button>
        </div>
      </form>

      {jobId && finished ? (
        <div className="actions" style={{ marginTop: 12 }}>
          <button className="btn btn-secondary" type="button" onClick={onExport}>
            Download full job JSON
          </button>
        </div>
      ) : null}

      {exportableBriefEntries.length > 0 ? (
        <section className="card brief-feed" aria-live="polite">
          <div className="brief-feed-head">
            <h3 className="h3 card-title">Briefs</h3>
            <div className="brief-feed-actions">
              <button
                type="button"
                className="btn btn-secondary btn-compact"
                onClick={onExportAllBriefs}
              >
                Download all briefs (JSON)
              </button>
            </div>
          </div>
          <p className="muted brief-feed-note">
            Updated as each row completes. Kept in this browser only (local storage).
          </p>
          <div className="brief-feed-list">
            {exportableBriefEntries.map((e) => (
              <BriefCard
                key={`${e.index}-${e.savedAt}`}
                index={e.index}
                company={e.company}
                domain={e.domain}
                savedAt={e.savedAt}
                brief={e.brief}
              />
            ))}
          </div>
        </section>
      ) : null}

      {rows.length > 0 ? (
        <section className="card" aria-live="polite">
          <h3 className="h3 card-title">Queue</h3>
          {jobId ? (
            <p className="muted">
              Job <span style={{ fontFamily: "var(--font-mono)" }}>{jobId}</span>
              {jobName ? <> — {jobName}</> : null}
            </p>
          ) : null}
          <div style={{ overflowX: "auto" }}>
            <table className="batch">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Company</th>
                  <th>Domain hint</th>
                  <th>Status</th>
                  <th>Track</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.index}>
                    <td>{r.index + 1}</td>
                    <td>{r.company}</td>
                    <td className="muted">{r.domain ?? "—"}</td>
                    <td
                      className={`status-cell status-${r.status === "pending" ? "pending" : r.status === "running" ? "running" : r.status === "ok" ? "ok" : "err"}`}
                    >
                      <span className="status-dot" />
                      {r.status}
                      {r.error ? (
                        <span className="muted" style={{ display: "block", marginTop: 4 }}>
                          {r.error}
                        </span>
                      ) : null}
                    </td>
                    <td>{r.track ?? "—"}</td>
                    <td>{r.verdict ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
