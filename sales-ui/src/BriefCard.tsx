import {
  buildSingleBriefPayload,
  downloadJsonFile,
  singleBriefFilename,
} from "./exportBriefs";

type Props = {
  index: number;
  company: string;
  domain: string | null;
  savedAt?: string;
  brief: Record<string, unknown>;
};

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function pickBriefTitle(b: Record<string, unknown>): string {
  return (
    str(b.company_name_canonical) ||
    str(b.company_name_queried) ||
    "Prospect brief"
  );
}

export default function BriefCard({
  index,
  company,
  domain,
  savedAt,
  brief,
}: Props) {
  const title = pickBriefTitle(brief);
  const track = str(brief.track);
  const verdict = str(brief.verdict);
  const rationale = str(brief.rationale);
  const why = str(brief.why_not_confident);
  const rev = brief.revenue_estimate as Record<string, unknown> | undefined;
  const revBand = rev ? str(rev.band) : undefined;
  const roles = Array.isArray(brief.target_roles)
    ? (brief.target_roles as Record<string, unknown>[])
    : [];
  const hooks = Array.isArray(brief.hooks)
    ? (brief.hooks as Record<string, unknown>[])
    : [];
  const salesPrep =
    brief.sales_conversation_prep && typeof brief.sales_conversation_prep === "object"
      ? (brief.sales_conversation_prep as Record<string, unknown>)
      : null;
  const wall = typeof brief.wall_seconds === "number" ? brief.wall_seconds : undefined;
  const cost = typeof brief.cost_usd === "number" ? brief.cost_usd : undefined;

  const onDownloadJson = () => {
    const entry = {
      index,
      company,
      domain,
      savedAt: savedAt ?? new Date().toISOString(),
      brief,
    };
    downloadJsonFile(singleBriefFilename(entry), buildSingleBriefPayload(entry));
  };

  return (
    <article className="brief-card">
      <header className="brief-card-head">
        <div className="brief-card-head-row">
          <span className="brief-card-kicker">Brief · Row {index + 1}</span>
          <button
            type="button"
            className="btn btn-secondary btn-compact"
            onClick={onDownloadJson}
          >
            Download JSON
          </button>
        </div>
        <h3 className="brief-card-title">{title}</h3>
        <p className="brief-card-sub muted">
          Queried as {company}
          {domain ? ` · ${domain}` : ""}
        </p>
        <div className="brief-card-tags">
          {track ? (
            <span className="brief-tag">
              <span className="brief-tag-dot" />
              {track.replace(/_/g, " ")}
            </span>
          ) : null}
          {verdict ? (
            <span className="brief-tag brief-tag-verdict">
              <span className="brief-tag-dot" />
              {verdict.replace(/_/g, " ")}
            </span>
          ) : null}
          {revBand ? <span className="brief-meta">{revBand.replace(/_/g, " ")}</span> : null}
          {wall !== undefined && cost !== undefined ? (
            <span className="brief-meta">
              {wall.toFixed(0)}s · ${cost.toFixed(2)}
            </span>
          ) : null}
        </div>
      </header>

      {why ? (
        <p className="brief-why muted">
          <span className="brief-why-label">Confidence</span> {why}
        </p>
      ) : null}

      {rationale ? <p className="brief-rationale">{rationale}</p> : null}

      {salesPrep ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Before the call</h4>
          <dl className="brief-list brief-dl">
            {(() => {
              const wtd = salesPrep.what_they_do as Record<string, unknown> | undefined;
              const summary = wtd ? str(wtd.summary) : undefined;
              const wUrl = wtd ? str(wtd.citation_url) : undefined;
              if (!summary) return null;
              return (
                <div key="wtd" className="brief-dl-row">
                  <dt>What they do</dt>
                  <dd>
                    {summary}
                    {wUrl ? (
                      <>
                        {" "}
                        <a href={wUrl} target="_blank" rel="noopener noreferrer" className="brief-hook-link">
                          Source
                        </a>
                      </>
                    ) : null}
                  </dd>
                </div>
              );
            })()}
            {(() => {
              const fr = salesPrep.fedramp_posture as Record<string, unknown> | undefined;
              const st = fr ? str(fr.status) : undefined;
              const stage = fr ? str(fr.stage) : undefined;
              const notes = fr ? str(fr.notes) : undefined;
              const fUrl = fr ? str(fr.citation_url) : undefined;
              if (!st) return null;
              return (
                <div key="fed" className="brief-dl-row">
                  <dt>FedRAMP</dt>
                  <dd>
                    <span className="brief-meta">{st.replace(/_/g, " ")}</span>
                    {stage ? <span className="muted"> — {stage}</span> : null}
                    {notes ? <p className="muted brief-dl-notes">{notes}</p> : null}
                    {fUrl ? (
                      <div>
                        <a href={fUrl} target="_blank" rel="noopener noreferrer" className="brief-hook-link">
                          Source
                        </a>
                      </div>
                    ) : null}
                  </dd>
                </div>
              );
            })()}
            {(() => {
              const hr = salesPrep.hr_peo as Record<string, unknown> | undefined;
              const st = hr ? str(hr.status) : undefined;
              const hint = hr ? str(hr.provider_hint) : undefined;
              const hUrl = hr ? str(hr.citation_url) : undefined;
              if (!st) return null;
              return (
                <div key="peo" className="brief-dl-row">
                  <dt>HR PEO</dt>
                  <dd>
                    {st.replace(/_/g, " ")}
                    {hint ? <span className="muted"> — {hint}</span> : null}
                    {hUrl ? (
                      <>
                        {" "}
                        <a href={hUrl} target="_blank" rel="noopener noreferrer" className="brief-hook-link">
                          Source
                        </a>
                      </>
                    ) : null}
                  </dd>
                </div>
              );
            })()}
            {(() => {
              const lf = salesPrep.last_funding as Record<string, unknown> | undefined;
              const round = lf ? str(lf.round_label) : undefined;
              const dt = lf ? str(lf.observed_date) : undefined;
              const conf = lf ? str(lf.confidence) : undefined;
              const lUrl = lf ? str(lf.citation_url) : undefined;
              if (!round && !dt && conf === "unknown" && !lUrl) return null;
              return (
                <div key="fund" className="brief-dl-row">
                  <dt>Last funding</dt>
                  <dd>
                    {[round, dt].filter(Boolean).join(" · ") || "—"}
                    {conf && conf !== "unknown" ? (
                      <span className="muted"> ({conf})</span>
                    ) : null}
                    {lUrl ? (
                      <>
                        {" "}
                        <a href={lUrl} target="_blank" rel="noopener noreferrer" className="brief-hook-link">
                          Source
                        </a>
                      </>
                    ) : null}
                  </dd>
                </div>
              );
            })()}
            {Array.isArray(salesPrep.federal_prime_awards) &&
            (salesPrep.federal_prime_awards as unknown[]).length > 0 ? (
              <div className="brief-dl-row">
                <dt>Federal primes</dt>
                <dd>
                  <ul className="brief-list">
                    {(salesPrep.federal_prime_awards as Record<string, unknown>[]).map(
                      (row, i) => {
                        const aUrl = str(row.citation_url);
                        return (
                          <li key={i}>
                            <strong>{str(row.agency_or_context) ?? "—"}</strong>
                            {str(row.amount_or_band) ? (
                              <span className="muted"> — {str(row.amount_or_band)}</span>
                            ) : null}
                            {str(row.period_hint) ? (
                              <span className="muted"> ({str(row.period_hint)})</span>
                            ) : null}
                            {aUrl ? (
                              <>
                                {" "}
                                <a
                                  href={aUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="brief-hook-link"
                                >
                                  USAspending
                                </a>
                              </>
                            ) : null}
                          </li>
                        );
                      },
                    )}
                  </ul>
                </dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}

      {roles.length > 0 ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Target roles</h4>
          <ul className="brief-list">
            {roles.map((role, i) => (
              <li key={i}>
                <strong>{str(role.title) ?? "—"}</strong>
                {str(role.rationale) ? (
                  <span className="muted"> — {str(role.rationale)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {hooks.length > 0 ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Hooks</h4>
          <ul className="brief-hooks">
            {hooks.map((h, i) => {
              const url = str(h.citation_url);
              return (
                <li key={i}>
                  <p className="brief-hook-text">{str(h.text) ?? "—"}</p>
                  {url ? (
                    <a
                      className="brief-hook-link"
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Source
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
