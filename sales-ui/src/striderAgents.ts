export type AppRoute =
  | "dashboard"
  | "project-info"
  | "agent-1"
  | "agent-2"
  | "agent-3"
  | "agent-4"
  | "agent-5"
  | "agent-6"
  | "agent-7"
  | "agent-8";

export type AgentSlug =
  | "agent-1"
  | "agent-2"
  | "agent-3"
  | "agent-4"
  | "agent-5"
  | "agent-6"
  | "agent-7"
  | "agent-8";

export type StriderAgent = {
  slug: AgentSlug;
  n: number;
  name: string;
  tier: 1 | 2 | 3;
  /** Shipped in this console vs roadmap only */
  live: boolean;
};

export const STRIDER_AGENTS: readonly StriderAgent[] = [
  { slug: "agent-1", n: 1, name: "Prospect research", tier: 1, live: true },
  { slug: "agent-2", n: 2, name: "Account targeting", tier: 1, live: false },
  { slug: "agent-3", n: 3, name: "Contact enrichment", tier: 1, live: false },
  { slug: "agent-4", n: 4, name: "Outreach composer", tier: 2, live: false },
  { slug: "agent-5", n: 5, name: "Sequence orchestrator", tier: 2, live: false },
  { slug: "agent-6", n: 6, name: "Reply triage", tier: 3, live: false },
  { slug: "agent-7", n: 7, name: "Meeting qualification", tier: 3, live: false },
  { slug: "agent-8", n: 8, name: "Pipeline hygiene & CRM", tier: 3, live: false },
] as const;

export function agentBySlug(slug: AgentSlug): StriderAgent | undefined {
  return STRIDER_AGENTS.find((a) => a.slug === slug);
}
