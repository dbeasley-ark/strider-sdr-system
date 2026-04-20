import StriderAgentRail from "./StriderAgentRail";

export default function ProjectInfo() {
  return (
    <div className="info-page">
      <header className="info-page-hero">
        <h1 className="info-page-title">Project info</h1>
        <p className="muted info-page-lede">
          Strider SDR is Arkenstone's agentic sales development system: eight specialized agents with
          explicit inputs, outputs, and review gates—not a single monolithic model.
        </p>
      </header>

      <section className="card info-block">
        <h2 className="h3 card-title">How this console fits in</h2>
        <p className="info-prose muted">
          This application runs the Tier 1 <strong className="info-strong">prospect research</strong>{" "}
          agent (Agent 1) in batch: structured briefs, ICP signals, and hooks from public sources only.
          Downstream agents—targeting, enrichment, drafting, cadence, replies, meetings, and CRM
          hygiene—follow the phased roadmap and are not exposed here yet.
        </p>
        <p className="info-prose muted">
          Strider is not autonomous outbound. No agent sends email, LinkedIn messages, or meeting
          requests without explicit human approval; that constraint is architectural.
        </p>
      </section>

      <StriderAgentRail />

      <section className="card info-block">
        <h2 className="h3 card-title">Risk tiers (summary)</h2>
        <ul className="tier-list">
          <li className="tier-list-item">
            <span className="agent-rail-tier agent-rail-tier--t1">Tier 1</span>
            <p className="tier-list-copy muted">
              Read-only intelligence. No external writes, no prospect contact. Establishes the data
              quality floor.
            </p>
          </li>
          <li className="tier-list-item">
            <span className="agent-rail-tier agent-rail-tier--t2">Tier 2</span>
            <p className="tier-list-copy muted">
              Drafting and internal system writes under human review before anything customer-facing
              ships.
            </p>
          </li>
          <li className="tier-list-item">
            <span className="agent-rail-tier agent-rail-tier--t3">Tier 3</span>
            <p className="tier-list-copy muted">
              Live pipeline support with the highest governance bar: observability, overrides, and
              compliance sign-off per program gate.
            </p>
          </li>
        </ul>
      </section>
    </div>
  );
}
