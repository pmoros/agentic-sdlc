#!/usr/bin/env python3
"""Pure Impact Analysis completeness-checking logic for
check-spec-complete.sh.

WHY THIS EXISTS
  Impact Analysis enforcement is scripted for deployments (the "not valid if
  any artifact is empty" rule in `#start_guided_deployment`) but was
  review-only on the session side. This is the session-side equivalent — a
  lightweight automated precondition before a design goes to the reviewer
  agent for Gate A.
  See work-sessions/sessions/ADH-008-decouple-control-exec/SPEC.md §6.

The decision-making logic lives in :func:`find_missing_fields` (pure — takes
a string, returns a list) so it can be unit-tested without touching the
filesystem; only :func:`main` does I/O.

Inputs come from the environment (set by check-spec-complete.sh), mirroring
scripts/lib/regenerate_views.py's convention: `SPEC_FILE_ENV`.
"""
import os
import re
import sys

REQUIRED_FIELDS = ("Stakeholders", "Components", "Data dependencies", "Side effects")

_HEADING_RE = re.compile(r'^##\s+Impact analysis\s*$')


def _field_re(label):
    return re.compile(r'^-\s*\*\*' + re.escape(label) + r':\*\*\s*(.*)$')


def find_missing_fields(text):
    """Return the required Impact Analysis field names that are missing or
    empty in ``text`` (a SPEC.md's full contents). Pure — no I/O.

    An empty list means the ``## Impact analysis`` heading was found and all
    four fields have non-empty content on their bullet line. If the heading
    itself is absent, every field is reported missing — there is no section
    to check field-by-field.
    """
    lines = text.splitlines()

    heading_idx = None
    for i, line in enumerate(lines):
        if _HEADING_RE.match(line.strip()):
            heading_idx = i
            break
    if heading_idx is None:
        return list(REQUIRED_FIELDS)

    section = []
    for line in lines[heading_idx + 1:]:
        if line.lstrip().startswith("#"):
            break
        section.append(line)

    missing = []
    for label in REQUIRED_FIELDS:
        pattern = _field_re(label)
        match = None
        for line in section:
            match = pattern.match(line.strip())
            if match:
                break
        if match is None or not match.group(1).strip():
            missing.append(label)
    return missing


def main():
    spec_file = os.environ.get("SPEC_FILE_ENV", "").strip()
    if not spec_file:
        print("check-spec-complete: SPEC_FILE_ENV is required", file=sys.stderr)
        return 2

    if not os.path.isfile(spec_file):
        print(f"check-spec-complete: SPEC.md not found at {spec_file}", file=sys.stderr)
        return 2

    with open(spec_file) as fh:
        text = fh.read()

    missing = find_missing_fields(text)
    if missing:
        print(
            "check-spec-complete: Impact analysis incomplete in "
            f"{spec_file} — missing/empty field(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    print(f"check-spec-complete: {spec_file} — Impact analysis complete", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
