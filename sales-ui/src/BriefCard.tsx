type Props = {
  index: number;
  company: string;
  domain: string | null;
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

export default function BriefCard({ index, company, domain, brief }: Props) {
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
  const wall = typeof brief.wall_seconds === "number" ? brief.wall_seconds : undefined;
  const cost = typeof brief.cost_usd === "number" ? brief.cost_usd : undefined;

  return (
    <article className="brief-card">
      <header className="brief-card-head">
        <span className="brief-card-kicker">Brief · Row {index + 1}</span>
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
