#!/usr/bin/env python3
"""One-time, additive, idempotent migration: add an `Item` column to
SESSIONS_STATE.md's session-registry table. ADH-011 SPEC.md sec.7.

Every row today is implicitly episode 1 of its own item (nothing has ever
been reopened before this session), so `Item` is simply that row's own
Session ID -- except the template's `_none yet_` placeholder row, which
gets an empty Item cell like its other empty cells.

Pure text-in/text-out (no I/O) so it's unit-testable without touching the
filesystem; the `.sh` wrapper does dry-run/commit/verify I/O.
"""
import sys


def _split_row(line):
    inner = line.rstrip("\n").strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return inner.split("|")


def _join_row(cells):
    return "|" + "|".join(cells) + "|"


def _is_separator_row(cells):
    return all(set(c.strip()) <= {"-"} and c.strip() for c in cells)


def add_item_column(text):
    """Insert an `Item` column right after `Session ID` in the
    SESSIONS_STATE.md table. Idempotent: returns ``text`` unchanged if the
    header already has one, or if no `| Session ID |` header is found at
    all. Every non-table line (title, legend prose, comments) passes
    through byte-for-byte."""
    lines = text.splitlines(keepends=True)

    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("| Session ID |"):
            header_idx = i
            break
    if header_idx is None:
        return text

    header_cells = _split_row(lines[header_idx])
    if len(header_cells) > 1 and header_cells[1].strip() == "Item":
        return text  # already migrated

    out = list(lines[:header_idx])
    for i in range(header_idx, len(lines)):
        line = lines[i]
        newline = "\n" if line.endswith("\n") else ""
        stripped = line.rstrip("\n")

        if not (stripped.startswith("|") and stripped.endswith("|")):
            out.append(line)
            continue

        cells = _split_row(line)
        if i == header_idx:
            cells.insert(1, " Item ")
        elif i == header_idx + 1 and _is_separator_row(cells):
            cells.insert(1, "---")
        else:
            session_id = cells[0].strip()
            item_value = "" if session_id == "_none yet_" else session_id
            cells.insert(1, " " if not item_value else f" {item_value} ")
        out.append(_join_row(cells) + newline)

    return "".join(out)


def main():
    text = sys.stdin.read()
    sys.stdout.write(add_item_column(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
