# 07 · Product Thinking

Technical correctness is necessary but insufficient. Agents are unpredictable by nature — they nail a task one day and fumble it the next. The product experience has to account for that variance or users lose trust and stop using the thing.

## The developer checklist

- **Confidence signaling.** When confidence is low, say so. Silent guessing is the single fastest way to destroy user trust.
- **Escalation path.** When the agent reaches its limit, there must be a clear hand-off to a human or a fallback system. Not "the agent errors out."
- **Graceful failures.** Users should never see a stack trace. They should see "I ran into X problem; here's what you can do."
- **Proactive clarification.** When inputs are ambiguous, the agent should ask before guessing. One clarifying exchange is cheaper than one wrong action that has to be reversed.

## Two confidence patterns

1. **In-schema confidence.** Make your output structure include a `confidence: float` field and an `uncertain_because: list[str]` field. Simple, free, works.
2. **Two-pass grading.** After the agent drafts a response, a second short LLM call rates it. More robust, more expensive. Use when the first pattern isn't calibrated enough.

## Irreversible actions

For anything costly or irreversible — sending emails, charging cards, deleting data, shipping orders — the agent should not be able to complete the action without human confirmation. Use `PermissionScope.require_confirmation` and the `human_in_loop` module.

The product question to ask: *what's the worst thing this agent could do, and how does a human stop it in time?*
