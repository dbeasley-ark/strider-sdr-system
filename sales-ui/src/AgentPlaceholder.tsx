import type { StriderAgent } from "./striderAgents";

type Props = {
  agent: StriderAgent;
};

export default function AgentPlaceholder({ agent }: Props) {
  return (
    <div className="agent-placeholder-page">
      <header className="dash-page-head">
        <p className="eyebrow agent-placeholder-eyebrow">
          Agent {agent.n} · Tier {agent.tier}
        </p>
        <h1 className="workspace-title">{agent.name}</h1>
        <p className="muted workspace-sub">
          This workspace will host the {agent.name.toLowerCase()} agent when it ships. No mock
          metrics—telemetry and lists will render here from live integrations.
        </p>
      </header>

      <div className="dash-two-col">
        <section className="card dash-card">
          <h2 className="h3 card-title">Overview</h2>
          <dl className="agent-placeholder-dl">
            <dt>Status</dt>
            <dd>Roadmap</dd>
            <dt>Last successful job</dt>
            <dd className="dash-nd">—</dd>
            <dt>Queue</dt>
            <dd className="dash-nd">—</dd>
          </dl>
        </section>
        <section className="card dash-card">
          <h2 className="h3 card-title">Signals</h2>
          <p className="muted dash-card-note">KPIs defined in the agent spec will surface here.</p>
          <ul className="agent-placeholder-list">
            <li>
              <span className="agent-placeholder-metric">Throughput</span>
              <span className="dash-nd">—</span>
            </li>
            <li>
              <span className="agent-placeholder-metric">Error rate</span>
              <span className="dash-nd">—</span>
            </li>
            <li>
              <span className="agent-placeholder-metric">Latency p95</span>
              <span className="dash-nd">—</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
