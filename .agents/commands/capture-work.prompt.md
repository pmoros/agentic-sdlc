---
agent: agent
description: Guided, structured capture into work/INBOX.md — a note plus optional source/link, inserted newest-at-top. Front door for #triage-inbox; assigns no priority/scope/ticket.
---

# Capture Work

Turn a raw idea/observation into a well-formed `work/INBOX.md` entry
without hand-writing markdown. `<work>` is the sibling `../work-sessions`
repo. This is a fast, low-ceremony front door — it never assigns
priority, scope, or a ticket; that stays `#triage-inbox`'s job.

## Step 1 — Get the note

If the invocation supplied the note as a quoted argument
(`#capture-work "note text"`), use it directly. Otherwise ask: "What do
you want to capture?"

## Step 2 — Get the optional follow-ups

If `--source "<text>"` and/or `--link "<text>"` were given in the
invocation, use them directly. For whichever wasn't supplied, ask (each
skippable — press Enter to omit):
- "Where did this come from? (Slack, a meeting, a code review, an idea —
  press Enter to skip)"
- "Any related link or ticket? (press Enter to skip)"

Never ask for priority, scope, or a ticket ID here — deliberately
deferred to `#triage-inbox`.

## Step 3 — Sanitize

For the note and for `--source`/`--link` (whichever were supplied):
1. Collapse every run of whitespace (including embedded newlines — e.g.
   from a multi-line paste) to a single space.
2. Trim leading/trailing whitespace from the result.

After sanitizing:
- If the **note** is now empty, do not proceed to Step 4. Report
  "Nothing to capture — the note was empty." and, for a bare invocation,
  return to Step 1 to ask again; for a flagged invocation with an empty
  note argument, stop here.
- If `--source` and/or `--link` is now empty, treat that one as **not
  supplied** — its bracket is omitted entirely from the formatted line in
  Step 4, the same as if the flag had never been passed.

No other sanitization is applied — a note or `--source`/`--link` value
that happens to contain ` — ` or the literal substring `[source:` or an
unbalanced `]` is left as-is. `#triage-inbox` reads the whole line as
free text regardless, so this is at most a human-readability wrinkle at
triage time, not a parsing concern.

## Step 4 — Format the line

```
- <YYYY-MM-DD HH:MM> — <note>[ [source: <source>]][ [link: <link>]]
```

Only include a bracketed suffix for a field that survived Step 3 (was
supplied and non-empty after sanitizing). A note-only capture renders
identically to `work/INBOX.md`'s original, pre-`#capture-work` format —
no empty brackets, ever.

## Step 5 — Insert into `work/INBOX.md`

Read `<work>/work/INBOX.md` fresh (this command's only read of the file,
positioned as late as possible — immediately before this step — to keep
the unlocked-file race window as small as it reasonably can be; a
genuinely simultaneous write from elsewhere can still corrupt the file,
and that residual risk is accepted, not hidden, for this low-stakes
scratch file).

Find the `<!-- newest entries at the top -->` marker line. Insert the
new line **immediately after the marker, unconditionally** — before any
entries already present below it, never after an existing entry. This is
what keeps captures newest-at-top: each new insertion pushes everything
already there further down, rather than accumulating in arrival order.

If the marker is missing or doesn't match exactly (e.g. reworded by a
hand-edit), **stop and report** rather than guessing an insertion point
— name what was expected and what was found, and do not write anything.

Write the file back with the new line spliced in; every other existing
line's content and relative order stays byte-identical.

## Step 6 — Report and offer

Show the exact line that was written. Ask whether to run `#triage-inbox`
now (useful when this is the only/latest pending capture) or leave it
for later — either answer is fine; this command's job ends at the
capture.
