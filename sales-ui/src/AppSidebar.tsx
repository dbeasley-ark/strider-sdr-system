import Logomark from "./Logomark";
import ThemeToggle from "./ThemeToggle";
import type { AppRoute } from "./striderAgents";
import { STRIDER_AGENTS } from "./striderAgents";
import type { Theme } from "./theme";

type Props = {
  active: AppRoute;
  onNavigate: (route: AppRoute) => void;
  logoHorizontal: string;
  theme: Theme;
  onThemeToggle: () => void;
  mobileOpen: boolean;
};

export default function AppSidebar({
  active,
  onNavigate,
  logoHorizontal,
  theme,
  onThemeToggle,
  mobileOpen,
}: Props) {
  const go = (route: AppRoute) => {
    onNavigate(route);
  };

  return (
    <aside
      id="strider-sidebar"
      className={`sidebar${mobileOpen ? " sidebar--open" : ""}`}
      aria-label="Strider navigation"
    >
      <div className="sidebar-brand">
        <img className="sidebar-logo" src={logoHorizontal} alt="Arkenstone Defense" />
        <div className="sidebar-product">
          <span className="sidebar-product-name">Strider SDR</span>
          <span className="sidebar-product-sub">Agentic sales development</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <button
          type="button"
          className={`sidebar-link${active === "dashboard" ? " sidebar-link--active" : ""}`}
          onClick={() => go("dashboard")}
          aria-current={active === "dashboard" ? "page" : undefined}
        >
          Dashboard
        </button>

        <p className="sidebar-section-label">Agents</p>
        <ul className="sidebar-agent-list">
          {STRIDER_AGENTS.map((a) => (
            <li key={a.slug}>
              <button
                type="button"
                className={`sidebar-link sidebar-link--agent${active === a.slug ? " sidebar-link--active" : ""}`}
                onClick={() => go(a.slug)}
                aria-current={active === a.slug ? "page" : undefined}
              >
                <span className="sidebar-agent-num">{a.n}</span>
                <span className="sidebar-agent-name">{a.name}</span>
                {a.live ? (
                  <span className="sidebar-agent-badge" title="Available in this console">
                    Live
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>

        <button
          type="button"
          className={`sidebar-link${active === "project-info" ? " sidebar-link--active" : ""}`}
          onClick={() => go("project-info")}
          aria-current={active === "project-info" ? "page" : undefined}
        >
          Project info
        </button>
      </nav>

      <div className="sidebar-footer">
        <Logomark className="logomark logomark--sidebar" />
        <div className="sidebar-footer-actions">
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
          <span className="sidebar-env">Internal</span>
        </div>
      </div>
    </aside>
  );
}
