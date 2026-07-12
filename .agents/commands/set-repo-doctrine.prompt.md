# Set Repo Doctrine

Deduce and persist repo-specific context to `.copilot-doctrine.md`. This command is additive — it never silently overwrites existing doctrine. Run once when setting up a new repo, or again to refresh after significant changes.

The generated doctrine captures only what is **repo-specific** (purpose, stack, architectural characteristics, folder conventions). The universal engineering defaults (TDD/BDD/design-first/Well-Architected/KIS) live in `.agents/rules/engineering.instructions.md` and are not duplicated here — the doctrine only records deviations/overrides from them.

## Steps

### 1. Check for existing doctrine
Read `.copilot-doctrine.md` if it exists. If found, display the current content and inform the user:
> "Existing doctrine found. This run will propose updates — you will review a diff before anything is written."

If not found:
> "No `.copilot-doctrine.md` found. I will explore the repo and propose one."

### 2. Explore the repo autonomously
Gather the following signals (use available tools — do not ask the user for information that can be discovered):

- **README, CHANGELOG, docs/** — repo name, stated purpose, target audience
- **Package manifests** (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Gemfile`, `Cargo.toml`, `*.csproj`, etc.) — languages, frameworks, key dependencies
- **CI/CD configs** (`.github/workflows/`, `Jenkinsfile`, `.circleci/`, etc.) — build, test, deploy tooling
- **Folder structure** — top-level layout, naming patterns, presence of monorepo indicators (`packages/`, `apps/`, `services/`, `libs/`)
- **Existing ADRs** — any decision records to infer architectural direction
- **IaC / infra** (`terraform/`, `k8s/`, `docker-compose.yml`, etc.) — infrastructure patterns
- **Code patterns** — entry points, service boundaries, dominant module patterns

### 3. Propose repo purpose and tech stack
Based on exploration, draft:
- **Repo Purpose** — 1–2 sentences: what does this repo do, for whom, and in what context?
- **Tech Stack** — detected languages, key frameworks, infra tooling (list concisely; no guessing)

Display the proposals and ask: "Does this look accurate? Correct anything or press Enter to accept."

### 4. Propose architectural characteristics
Present the user with **4 options**, each containing exactly **3 "-ilities"** selected to reflect what matters most for this specific repo's domain. Draw from:

> reliability, scalability, security, evolvability, observability, simplicity, performance, portability, testability, maintainability, availability, consistency, durability, interoperability

Tailor the options to what the repo exploration revealed. Example for a data-heavy API service:

```
Option A: Reliability + Observability + Scalability
  → Prioritize uptime, tracing/metrics, and horizontal growth

Option B: Security + Reliability + Consistency
  → Prioritize data integrity, access control, and safe failure modes

Option C: Evolvability + Testability + Simplicity
  → Prioritize clean design, fast iteration, and low maintenance burden

Option D: Performance + Scalability + Observability
  → Prioritize throughput, growth capacity, and runtime visibility

Option E (custom): I'll define my own three characteristics
```

Ask: "Which option best represents this repo's architectural north star? (A / B / C / D / E)"

If E: ask the user to name their 3 characteristics.

### 5. Infer folder conventions
Document the observed folder structure as a descriptive table — not a prescription. Example:

```
| Folder/Pattern     | Observed purpose                        |
|--------------------|------------------------------------------|
| src/               | Application source code                  |
| tests/ or __tests__| Test files co-located with source        |
| docs/              | Documentation and ADRs                   |
| infra/ or deploy/  | Infrastructure and deployment configs    |
| .github/           | CI workflows and agent framework files   |
```

Show the table and ask: "Does this capture the folder conventions accurately? Add or correct anything."

### 6. Show proposed doctrine and confirm
Assemble the full proposed `.copilot-doctrine.md` content. Show it in its entirety:

```markdown
## Doctrine — <repo name>
Generated: <date> | Updated: <date>

### Repo Purpose
<1–2 sentences>

### Tech Stack
<bullet list>

### Architectural Characteristics (north star)
- Primary: <char 1>
- Primary: <char 2>
- Primary: <char 3>

### Engineering Doctrine
Universal defaults (TDD · BDD · Design-first · Well-Architected · KIS) apply from
`.agents/rules/engineering.instructions.md`. List only this repo's **deviations
or overrides** below (or "none").
- <override, or "none — universal defaults apply">

### Folder Conventions
<table>

### Notes / Overrides
<!-- Add any manual overrides or context the agent cannot infer here -->
```

If a previous doctrine file existed, show a diff (old vs. proposed). Ask:
> "Write this to `.copilot-doctrine.md`? (yes / edit / cancel)"

If edit: allow the user to describe changes; re-generate and show again before writing.

### 7. Write the file
Write the approved content to `.copilot-doctrine.md` at the repo root. This is autonomous once the user approves in step 6.

Remind the user:
> "`.copilot-doctrine.md` is gitignored and local to your machine. It's read automatically at session start. To update it later, run `#set-repo-doctrine.prompt.md` again."
