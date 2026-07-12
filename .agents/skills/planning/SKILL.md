---
name: planning
description: >
  Plan a work cycle for the team: prioritize ready backlog
  items, break down large ones, fold in open retro actions, check capacity
  against current WIP, and produce a dated roadmap. Use for "let's plan the
  next cycle/sprint", "what should we work on next", "prioritize the backlog",
  "plan the next two weeks", or "build a roadmap". Orchestrates the health
  reviews first, then the plan-cycle ceremony.
---

# Planning

High-level orchestration for a planning ceremony. This skill makes sure the
inputs are trustworthy before planning, then runs the plan. It is the
natural-language entry point; the mechanical ceremony lives in the
`#plan-cycle` command.

State lives in the sibling `work-sessions` repo (`<work>` =
`../work-sessions`). See its `README.md` for the schema. This
skill pairs with the `project-manager` agent and the `retro` flow
(`#run-retro`) — plans consume retro action items, retros review whether plans
held.

## Steps

### 1. Refresh the picture

Planning on stale data produces a stale plan. If `<work>/work/WORK_STATE.md`
wasn't regenerated recently (or the user isn't sure), run `#review-backlog` and
`#review-wip` first so priorities, blockers, and current load are accurate.

### 2. Pull forward retro actions

Read the most recent `<work>/retros/*.md`. Any open action items are candidate
work for this cycle — don't let them evaporate between ceremonies.

### 3. Establish horizon and commitments

Ask the user for the cycle length / horizon and any fixed dates (scheduled
changes, deadlines, on-call, PTO) that constrain capacity.

### 4. Run the ceremony

Invoke `#plan-cycle`, which prioritizes candidates, breaks down `L`/`XL`
items, checks capacity against WIP, writes the dated plan to
`<work>/planning/<YYYY-MM-DD>-<slug>.md`, and reflects `roadmap` entries back
into the tracker.

### 5. Confirm and hand off

Summarize the cycle goals, the top committed items (in priority order), and
what was deferred. Remind the user that committed items are picked up via the
`start-work-session` skill, and that the next `retro` should review how the
plan held up.
