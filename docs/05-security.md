# 05 · Security

An agent is a new attack surface. Two threat categories matter most:

## 1. Prompt injection

Any text from an untrusted source can contain instructions. Scraped web pages, user-submitted content, email bodies, PDF attachments, tool outputs from external APIs — treat all of them as adversarial.

**This template's defenses:**
- `InputValidator` runs pattern-match refusal on obvious jailbreak attempts (`ignore previous instructions`, role injection, exfil phrases). It catches the obvious. It is not a silver bullet.
- The agent loop passes tool results back as `type: tool_result` content, which Claude treats with less authority than user messages.
- Permission scopes prevent a compromised prompt from triggering tools that aren't in the allow list.

**What the template cannot do for you:**
- Define your threat model. That lives in `AGENT_SPEC.md §7`.
- Decide which tools should require human confirmation. That's a product decision, not a framework one.
- Audit your tool outputs for sensitive data leakage. Write output filters for anything the agent might return that shouldn't leave your system (PII, secrets, internal data).

## 2. Over-privileged agents

Default-deny. Every agent should run under a `PermissionScope` with the minimum tools it needs.

Pattern: `read_only` scope for everyday queries, `admin` scope with required-confirmation for sensitive operations. Choose the scope at agent construction time based on caller identity.

## 3. The skip flag

If your agent ever runs with flags like `--dangerously-skip-permissions` or equivalent, that code path belongs in isolated CI/CD sandboxes only. Never in a local dev environment with access to sensitive files. This is how breaches happen.
