# 01 · System Design

An agent is an orchestra, not a soloist. You're coordinating a decision-maker (the LLM), executors (tools), state storage, and sometimes sub-agents. The architecture is what prevents this from becoming spaghetti.

## Three questions to answer before writing code

1. **Where does state live at each step?** Trace it on paper. If you can't, your spec is incomplete.
2. **What happens when a component fails?** Timeout, 5xx, invalid output, prompt injection — each needs an explicit answer.
3. **Where can you cleanly split work?** If you can't split at true information boundaries, don't split at all. Multi-agent coordination adds 3–10x token overhead; one agent with the full context is usually cheaper.

## Context budgets

Estimate tokens per turn in `AGENT_SPEC.md §3`. If total > ~50k, you likely need retrieval or subagents, not more context. Opus 4.7's 1M-token window exists — but "it fits" is not the same as "it works well." Relevance matters more than capacity.

## The data-flow sketch

Even a rough ASCII diagram forces you to name the boundaries. Where does user input enter? Where does it get validated? Which state survives between turns? Which doesn't?

Things you can usually safely put in the loop: tool schemas, last N turns, retrieved chunks.
Things you probably can't: entire document libraries, raw logs, every historical turn of a long session.
