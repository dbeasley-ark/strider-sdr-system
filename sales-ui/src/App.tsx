import { useEffect, useState } from "react";

import AgentPlaceholder from "./AgentPlaceholder";
import AppSidebar from "./AppSidebar";
import BatchWorkspace from "./BatchWorkspace";
import Dashboard from "./Dashboard";
import Logomark from "./Logomark";
import ProjectInfo from "./ProjectInfo";
import { agentBySlug, type AppRoute } from "./striderAgents";
import { applyTheme, getStoredTheme, setStoredTheme, type Theme } from "./theme";
import logoHorizontalBlack from "../../assets/logos/Arkenstone-Logo-Horizontal-BrandBlack.svg?url";
import logoHorizontalWhite from "../../assets/logos/Arkenstone-Logo-Horizontal-BrandWhite.svg?url";

export default function App() {
  const [route, setRoute] = useState<AppRoute>("dashboard");
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    applyTheme(theme);
    setStoredTheme(theme);
  }, [theme]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [route]);

  const logoHorizontal = theme === "dark" ? logoHorizontalWhite : logoHorizontalBlack;

  const mainContent =
    route === "dashboard" ? (
      <Dashboard />
    ) : route === "project-info" ? (
      <ProjectInfo />
    ) : route === "agent-1" ? (
      <BatchWorkspace />
    ) : (
      (() => {
        const a = agentBySlug(route);
        return a ? <AgentPlaceholder agent={a} /> : <Dashboard />;
      })()
    );

  return (
    <div className="shell shell--app">
      <div className="app-body">
        {mobileNavOpen ? (
          <button
            type="button"
            className="sidebar-backdrop"
            aria-label="Close menu"
            onClick={() => setMobileNavOpen(false)}
          />
        ) : null}
        <AppSidebar
          active={route}
          onNavigate={setRoute}
          logoHorizontal={logoHorizontal}
          theme={theme}
          onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          mobileOpen={mobileNavOpen}
        />
        <div className="stage-wrap">
          <header className="stage-header">
            <button
              type="button"
              className="sidebar-toggle"
              aria-expanded={mobileNavOpen}
              aria-controls="strider-sidebar"
              onClick={() => setMobileNavOpen((o) => !o)}
            >
              <span className="sidebar-toggle-bar" />
              <span className="sidebar-toggle-bar" />
              <span className="sidebar-toggle-bar" />
              <span className="visually-hidden">Menu</span>
            </button>
            <span className="stage-header-title">Strider SDR</span>
          </header>
          <main id="strider-main" className="main-stage">
            {mainContent}
          </main>
          <footer className="site-footer site-footer--stage">
            <Logomark className="logomark" />
            <span className="footer-line">
              Strider SDR · Arkenstone Defense — internal program tooling
            </span>
          </footer>
        </div>
      </div>
    </div>
  );
}
