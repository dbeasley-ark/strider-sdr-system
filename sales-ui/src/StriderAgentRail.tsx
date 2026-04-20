import { STRIDER_AGENTS } from "./striderAgents";

export default function StriderAgentRail() {
  return (
    <section className="agent-rail" aria-labelledby="strider-rail-heading">
      <h2 id="strider-rail-heading" className="agent-rail-heading">
        Agent composition
      </h2>
      <ol className="agent-rail-list">
        {STRIDER_AGENTS.map((a) => (
          <li
            key={a.slug}
            className={`agent-rail-item agent-rail-item--tier-${a.tier} agent-rail-item--${a.live ? "live" : "planned"}`}
          >
            <span className="agent-rail-num" aria-hidden>
              {a.n}
            </span>
            <span className="agent-rail-name">{a.name}</span>
            <span className="agent-rail-meta">
              <span className={`agent-rail-tier agent-rail-tier--t${a.tier}`}>Tier {a.tier}</span>
              {a.live ? (
                <span className="agent-rail-status agent-rail-status--live">Live</span>
              ) : (
                <span className="agent-rail-status agent-rail-status--planned">Planned</span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
