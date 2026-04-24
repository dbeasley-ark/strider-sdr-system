import { useState } from "react";
import { buildBriefPresentation } from "./briefPresentation";
import {
  buildSingleBriefPayload,
  downloadJsonFile,
  singleBriefFilename,
  singleBriefPdfFilename,
} from "./exportBriefs";
import { downloadBriefPdf } from "./pdf/downloadBriefPdf";

type Props = {
  index: number;
  company: string;
  domain: string | null;
  savedAt?: string;
  brief: Record<string, unknown>;
};

export default function BriefCard({
  index,
  company,
  domain,
  savedAt,
  brief,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const pres = buildBriefPresentation(brief);
  const bodyId = `brief-body-${index}`;

  const entry = {
    index,
    company,
    domain,
    savedAt: savedAt ?? new Date().toISOString(),
    brief,
  };

  const onDownloadJson = () => {
    downloadJsonFile(singleBriefFilename(entry), buildSingleBriefPayload(entry));
  };

  const onDownloadPdf = () => {
    void downloadBriefPdf(
      {
        rowNumber: index + 1,
        companyQueried: company,
        domain,
        savedAt: entry.savedAt,
        pres,
      },
      singleBriefPdfFilename(entry),
    ).catch(() => {
      /* font fetch or PDF render failure */
    });
  };

  return (
    <article className={`brief-card ${expanded ? "brief-card--expanded" : "brief-card--collapsed"}`}>
      <header className="brief-card-head">
        <div className="brief-card-head-row">
          <button
            type="button"
            className="brief-card-summary"
            aria-expanded={expanded}
            aria-controls={bodyId}
            onClick={() => setExpanded((v) => !v)}
          >
            <span className="brief-card-chevron" aria-hidden />
            <span className="brief-card-summary-text">
              <span className="brief-card-kicker">Brief · Row {index + 1}</span>
              <span className="brief-card-title" role="heading" aria-level={3}>
                {pres.title}
              </span>
              <span className="brief-card-sub muted">
                Queried as {company}
                {domain ? ` · ${domain}` : ""}
              </span>
              <span className="brief-card-tags">
                {pres.tiersDisplay ? (
                  <span className="brief-tag">
                    <span className="brief-tag-dot" />
                    {pres.tiersDisplay}
                  </span>
                ) : null}
                {pres.postureConfidenceDisplay || pres.verdict ? (
                  <span className="brief-tag brief-tag-verdict">
                    <span className="brief-tag-dot" />
                    {pres.postureConfidenceDisplay ?? pres.verdict}
                  </span>
                ) : null}
                {pres.revBand ? <span className="brief-meta">{pres.revBand}</span> : null}
                {pres.wallSeconds !== undefined && pres.costUsd !== undefined ? (
                  <span className="brief-meta">
                    {pres.wallSeconds.toFixed(0)}s · ${pres.costUsd.toFixed(2)}
                  </span>
                ) : null}
              </span>
            </span>
          </button>
          <div className="brief-card-actions">
            <button
              type="button"
              className="btn btn-primary btn-compact"
              onClick={onDownloadPdf}
            >
              Download PDF
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-compact"
              onClick={onDownloadJson}
            >
              JSON
            </button>
          </div>
        </div>
      </header>

      <div id={bodyId} className="brief-card-body" hidden={!expanded}>
      {pres.why ? (
        <p className="brief-why muted">
          <span className="brief-why-label">Why not higher confidence</span> {pres.why}
        </p>
      ) : null}

      {pres.rationale ? <p className="brief-rationale">{pres.rationale}</p> : null}

      {pres.salesPrep ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Before the call</h4>
          <dl className="brief-list brief-dl">
            {pres.salesPrep.whatTheyDo ? (
              <div className="brief-dl-row">
                <dt>What they do</dt>
                <dd>
                  {pres.salesPrep.whatTheyDo.summary}
                  {pres.salesPrep.whatTheyDo.citation_url ? (
                    <>
                      {" "}
                      <a
                        href={pres.salesPrep.whatTheyDo.citation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="brief-hook-link"
                      >
                        Source
                      </a>
                    </>
                  ) : null}
                </dd>
              </div>
            ) : null}
            {pres.salesPrep.fedramp ? (
              <div className="brief-dl-row">
                <dt>FedRAMP</dt>
                <dd>
                  <span className="brief-meta">{pres.salesPrep.fedramp.status}</span>
                  {pres.salesPrep.fedramp.stage ? (
                    <span className="muted"> — {pres.salesPrep.fedramp.stage}</span>
                  ) : null}
                  {pres.salesPrep.fedramp.notes ? (
                    <p className="muted brief-dl-notes">{pres.salesPrep.fedramp.notes}</p>
                  ) : null}
                  {pres.salesPrep.fedramp.citation_url ? (
                    <div>
                      <a
                        href={pres.salesPrep.fedramp.citation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="brief-hook-link"
                      >
                        Source
                      </a>
                    </div>
                  ) : null}
                </dd>
              </div>
            ) : null}
            {pres.salesPrep.hrPeo ? (
              <div className="brief-dl-row">
                <dt>HR PEO</dt>
                <dd>
                  {pres.salesPrep.hrPeo.status}
                  {pres.salesPrep.hrPeo.provider_hint ? (
                    <span className="muted"> — {pres.salesPrep.hrPeo.provider_hint}</span>
                  ) : null}
                  {pres.salesPrep.hrPeo.citation_url ? (
                    <>
                      {" "}
                      <a
                        href={pres.salesPrep.hrPeo.citation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="brief-hook-link"
                      >
                        Source
                      </a>
                    </>
                  ) : null}
                </dd>
              </div>
            ) : null}
            {pres.salesPrep.lastFunding ? (
              <div className="brief-dl-row">
                <dt>Last funding</dt>
                <dd>
                  {[pres.salesPrep.lastFunding.round_label, pres.salesPrep.lastFunding.observed_date]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                  {pres.salesPrep.lastFunding.confidence &&
                  pres.salesPrep.lastFunding.confidence !== "unknown" ? (
                    <span className="muted"> ({pres.salesPrep.lastFunding.confidence})</span>
                  ) : null}
                  {pres.salesPrep.lastFunding.citation_url ? (
                    <>
                      {" "}
                      <a
                        href={pres.salesPrep.lastFunding.citation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="brief-hook-link"
                      >
                        Source
                      </a>
                    </>
                  ) : null}
                </dd>
              </div>
            ) : null}
            {pres.salesPrep.federalPrimes.length > 0 ? (
              <div className="brief-dl-row">
                <dt>Federal primes</dt>
                <dd>
                  <ul className="brief-list">
                    {pres.salesPrep.federalPrimes.map((row, i) => (
                      <li key={i}>
                        <strong>{row.agency_or_context}</strong>
                        {row.amount_or_band ? (
                          <span className="muted"> — {row.amount_or_band}</span>
                        ) : null}
                        {row.period_hint ? (
                          <span className="muted"> ({row.period_hint})</span>
                        ) : null}
                        {row.citation_url ? (
                          <>
                            {" "}
                            <a
                              href={row.citation_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="brief-hook-link"
                            >
                              USAspending
                            </a>
                          </>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}

      {pres.roles.length > 0 ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Target roles</h4>
          <ul className="brief-list">
            {pres.roles.map((role, i) => (
              <li key={i}>
                <strong>{role.title ?? "—"}</strong>
                {role.rationale ? <span className="muted"> — {role.rationale}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {pres.hooks.length > 0 ? (
        <section className="brief-section">
          <h4 className="brief-section-title">Hooks</h4>
          <ul className="brief-hooks">
            {pres.hooks.map((h, i) => (
              <li key={i}>
                <p className="brief-hook-text">{h.text ?? "—"}</p>
                {h.citation_url ? (
                  <a
                    className="brief-hook-link"
                    href={h.citation_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Source
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      </div>
    </article>
  );
}
