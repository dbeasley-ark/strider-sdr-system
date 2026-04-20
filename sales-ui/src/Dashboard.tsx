import { STRIDER_AGENTS } from "./striderAgents";

function DashCell({ label }: { label: string }) {
  return (
    <div className="dash-cell">
      <span className="dash-cell-label">{label}</span>
      <span className="dash-cell-value" aria-hidden>
        —
      </span>
    </div>
  );
}

export default function Dashboard() {
  return (
    <div className="dash-page">
      <header className="dash-page-head">
        <h1 className="workspace-title">Dashboard</h1>
        <p className="muted workspace-sub">
          Cross-agent view when Strider is fully wired. Values appear here from live telemetry and
          CRM—not placeholder data.
        </p>
      </header>

      <section className="dash-grid-metrics" aria-label="Summary metrics">
        <DashCell label="Qualified accounts (rolling)" />
        <DashCell label="Research tasks / week" />
        <DashCell label="Drafts awaiting review" />
        <DashCell label="Meetings booked (Strider-assisted)" />
      </section>

      <div className="dash-two-col">
        <section className="card dash-card">
          <h2 className="h3 card-title">Agent status</h2>
          <p className="muted dash-card-note">Live vs roadmap; last activity when agents report in.</p>
          <div style={{ overflowX: "auto" }}>
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Tier</th>
                  <th>Console</th>
                  <th>Last run</th>
                  <th>Queue depth</th>
                </tr>
              </thead>
              <tbody>
                {STRIDER_AGENTS.map((a) => (
                  <tr key={a.slug}>
                    <td>
                      <span className="dash-agent-name">{a.n}. {a.name}</span>
                    </td>
                    <td>
                      <span className={`agent-rail-tier agent-rail-tier--t${a.tier}`}>Tier {a.tier}</span>
                    </td>
                    <td>{a.live ? "Live" : "Planned"}</td>
                    <td className="dash-nd">—</td>
                    <td className="dash-nd">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card dash-card">
          <h2 className="h3 card-title">Throughput</h2>
          <p className="muted dash-card-note">Tasks completed over time by agent.</p>
          <div className="dash-chart-placeholder" aria-hidden>
            <span className="dash-chart-caption">Chart area</span>
          </div>
          <ul className="dash-legend" aria-label="Legend placeholder">
            <li>
              <span className="dash-legend-swatch dash-legend-swatch--a" /> <span className="dash-nd">—</span>
            </li>
            <li>
              <span className="dash-legend-swatch dash-legend-swatch--b" /> <span className="dash-nd">—</span>
            </li>
            <li>
              <span className="dash-legend-swatch dash-legend-swatch--c" /> <span className="dash-nd">—</span>
            </li>
          </ul>
        </section>
      </div>

      <section className="card dash-card">
        <h2 className="h3 card-title">Compliance & review</h2>
        <p className="muted dash-card-note">
          ITAR filter passes, human approvals pending, audit events—populated from production logs.
        </p>
        <div className="dash-row-metrics">
          <div className="dash-stat">
            <span className="dash-stat-label">Pending human approvals</span>
            <span className="dash-stat-value dash-nd">—</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-label">Flagged incidents (30d)</span>
            <span className="dash-stat-value dash-nd">—</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-label">Last full audit export</span>
            <span className="dash-stat-value dash-nd">—</span>
          </div>
        </div>
      </section>
    </div>
  );
}
