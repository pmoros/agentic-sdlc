# 0001 — Tiered, Conditional Loading of Integration & Lifecycle Rules

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-13 |
| **Deciders** | Paul Moros |
| **Tags** | token-usage, context-window, cache-efficiency, copilot-compat |

## Context

`AGENTS.md` (symlinked as `CLAUDE.md`, and as `.github/copilot-instructions.md`) carries an unconditional auto-load block:

```
<!-- Claude Code: auto-load all rules -->
@.agents/rules/atlassian.instructions.md
@.agents/rules/aws.instructions.md
@.agents/rules/github.instructions.md
@.agents/rules/engineering.instructions.md
@.agents/rules/deployments.instructions.md
@.agents/rules/session-state.instructions.md
@.agents/rules/dev-lifecycle.instructions.md
```

Measured on a live session, this pulls **~16–17K tokens** into context before any work begins: AGENTS.md itself (~6K) plus all seven rule files (~10–11K combined). None of the seven rule files carries `applyTo:` frontmatter or any other conditional-scoping mechanism — confirmed by inspecting all seven file heads.

Two problems, one root cause (no scoping):

1. **Token/context cost.** Most of the always-loaded content is integration-specific — Jira ADF formatting, AWS SSO profile gotchas, GitHub PR/branch conventions, production deployment policy — and irrelevant to a large fraction of sessions (e.g. a docs fix, a pure-code session with no Jira/AWS touch). AGENTS.md § "Integration Schemas" already states the intended contract — *"Read these files before any operation with their respective system"* — but the `@`-include block force-loads them regardless, contradicting that stated intent.
2. **Cross-tool correctness gap.** `@`-includes are a **Claude Code–specific** convention (the comment even says so). GitHub Copilot does not expand them. Copilot's native scoping mechanism is `applyTo:` frontmatter on `.github/instructions/*.instructions.md` — which these files also lack. The practical effect: **under Copilot, none of these seven rules may be reliably in effect**, silently, regardless of token cost.

A third constraint shapes the fix: the always-on block, as a **stable prefix**, is currently a fully cacheable prompt segment (Anthropic prompt caching: ~0.1× cost on cache reads after turn one). A naive fix that swaps in different rule subsets per task type would fragment that cache — turning one stable prefix into many keys, each paying a fresh cache-write. The fix must reduce token volume *and* preserve prefix stability.

## Decision

Adopt a **three-tier loading model** for `.agents/rules/*.instructions.md`, replacing the blanket `@`-include:

**Tier 1 — Always-on core (stays in the AGENTS.md prefix).**
Only rules needed on *every* session regardless of task: Operational Safety, Git Policy, Commit Message Convention, Approval Protocol, the one-line Engineering Doctrine reminder, and a pointer to where integration/lifecycle schemas live. Target: ~2.5–3K tokens, unchanged turn-to-turn — remains the cacheable prefix.

**Tier 2 — Conditional integration schemas** (`atlassian`, `aws`, `github`, `deployments`).
No `@`-include. Two parallel mechanisms so both tools are covered:
- **Claude Code / any agent runtime:** load via an explicit `Read` when a command is about to operate on that system (Jira, AWS, GitHub, or a deployment) — a `Read` tool result does not sit in the cached system-prompt prefix, so it doesn't fragment the cache.
- **GitHub Copilot:** add `applyTo:` frontmatter (glob-scoped, e.g. `applyTo: "**/*.tf,**/cdk/**"` for AWS-adjacent work, or command-scoped where file globs don't apply) to each `.github/instructions/*.instructions.md` symlink target, so Copilot's native instruction-scoping activates them without any `@`-include equivalent.

**Tier 3 — Conditional lifecycle rules** (`session-state`, `dev-lifecycle`).
Loaded only by the commands that need them: `session-state.instructions.md` by `#pause_work_session` / `#resume_work_session` / `#stop_work_session` / `#end_work_session`; `dev-lifecycle.instructions.md` by the design/QA/gate-adjacent commands (`design` skill, `#groom-item`, Gate A/B review flow).

Each Tier 2/3 rule file keeps a one-line self-declaration at its own top (e.g. *"Load this before any Jira/Confluence operation"*) so the contract is discoverable by reading the file itself, not only by remembering this ADR.

## Consequences

### Positive
- Always-on context drops from ~16–17K to an estimated ~3–4K tokens — roughly 13K tokens of context window reclaimed for actual task work on every session that doesn't touch Jira/AWS/deployments/lifecycle commands.
- Closes the Copilot correctness gap: rules gain a real conditional-scoping mechanism (`applyTo:`) instead of silently depending on an `@`-include Copilot never expands.
- Preserves prompt-cache efficiency: the Tier 1 prefix stays stable and cacheable; Tier 2/3 content arrives via `Read`, which doesn't fragment the cached prefix.
- Makes the framework's own stated principle ("read before any operation with that system") actually true in the loading mechanism, not just in prose.

### Negative / Trade-offs
- More moving parts: seven rule files now need either an `applyTo:` glob (imperfect for command-triggered, non-file-scoped cases like "any Jira operation") or a documented Read-trigger in the relevant commands/skills — some judgment calls per file on the best trigger.
- Commands and skills that implicitly relied on the rule already being in context (because AGENTS.md force-loaded it) must be audited and given an explicit `Read` step; a missed one is a silent regression back to "rule not applied."
- Token savings are structural (freed context, fewer cache-writes, closed correctness gap), not a large *direct dollar* saving per turn — the removed block was already cache-read-priced at ~0.1× after turn one. Communicate the benefit as reclaimed working context and cross-tool correctness, not primarily as a cost cut.

### Neutral
- The `.agents/` ⟷ `.github/` ⟷ `.claude/` triplication is **not** a duplication problem — confirmed to be symlinks (`CLAUDE.md → AGENTS.md`, `.github/copilot-instructions.md → ../AGENTS.md`, every `.github/instructions/*.instructions.md → ../../.agents/rules/*`). No action needed there; `.agents/rules/*` remains the single edited source.

## Alternatives Considered

**A — Leave the blanket `@`-include, accept the cost.** Rejected: leaves the Copilot correctness gap unaddressed and wastes context on every session regardless of tool.

**B — Split rules by moving conditional content directly into each command/skill prompt file (inline duplication).** Rejected: recreates the inlining problem already observed in `review-pr.prompt.md` (duplicates GitHub tool-priority content) — trades one maintenance burden for another and multiplies drift risk across N commands instead of 1 rule file.

**C — Keep the `@`-include but gate it with a per-session flag the user sets manually ("load AWS rules: y/n").** Rejected: adds a manual step to every session start, contradicts the framework's preference for automatic, dynamic discovery (cf. the existing dynamic commit-signing discovery pattern in AGENTS.md), and still does nothing for Copilot.

## References

- `AGENTS.md` (this repo) — the auto-load block under revision, and its own stated "read before any operation" principle in § Integration Schemas.
- `.agents/rules/*.instructions.md` — the seven rule files affected.
- `shared/prompt-caching.md` (Claude API skill reference) — prefix-match caching invariant motivating the Tier 1 / Tier 2+3 split.
- Investigation: token-usage sweep of this framework, 2026-07-13 (Explore agent findings + manual verification of symlink structure and rule-file frontmatter).
