"""Autonomous-execution authorization classifier (Phase 1).

Executable form of docs/autonomous-execution.instructions.md. Given a described
action and the worker's session root, returns whether it may run UNATTENDED
("allowed") or must be routed to a human via any interaction channel ("gated").

Design: additive allow-list over guarded-by-default. Anything not explicitly
allowed — and anything destructive — is GATED. Fail closed.
"""
from __future__ import annotations

import os

ALLOWED = "allowed"
GATED = "gated"

# git subcommands that only affect the worker's own local checkout/branch.
# `push` is deliberately absent — it leaves the machine, so it is gated.
LOCAL_GIT = {
    "add", "commit", "status", "diff", "log", "show",
    "branch", "checkout", "switch", "restore", "worktree", "stash", "fetch",
}


# F1: bash/shell commands that perform a gated action must be caught even though
# they arrive as "just bash" — a gated command laundered through Bash must not
# read as a successful, unpenalized tool call. Space-padded patterns so short CLI
# names match only as standalone tokens.
_GATED_BASH = (
    " git push ", " gh ", " aws ", " gcloud ", " az ", " sudo ", " rm -rf ",
    " npm publish ", " yarn publish ", " docker push ", " curl ", " wget ",
)


def bash_command_is_gated(command: str) -> bool:
    """True if a bash command string performs a gated action (push/PR/cloud/
    destructive/network egress). Defense-in-depth — the primary control is simply
    not granting a fan-out worker broad Bash."""
    c = " " + " ".join(str(command).lower().split()) + " "
    return any(pat in c for pat in _GATED_BASH)


def _within(path: str, root: str) -> bool:
    """True iff `path` resolves to `root` or something beneath it (no escape)."""
    if not path:
        return False
    ap = os.path.normpath(path)      # collapses '..' so traversal can't escape
    ar = os.path.normpath(root)
    return ap == ar or ap.startswith(ar + os.sep)


def classify_action(action: dict, session_root: str) -> str:
    """Classify one action as ALLOWED (unattended) or GATED (needs a human).

    `action` is a dict with at least `kind`; optional `path`, `subcommand`,
    `destructive`. Unknown shapes fail closed to GATED.
    """
    # Destructive/irreversible always gated, regardless of kind (elevated caution).
    if action.get("destructive"):
        return GATED

    kind = action.get("kind")

    if kind == "read":
        return ALLOWED
    if kind in ("test", "build", "lint"):
        return ALLOWED
    if kind in ("edit", "write"):
        # edit within the worker's own worktrees / session tracking files only
        return ALLOWED if _within(action.get("path", ""), session_root) else GATED
    if kind == "git":
        return ALLOWED if action.get("subcommand") in LOCAL_GIT else GATED
    if kind in ("bash", "shell"):
        cmd = action.get("command")
        if not cmd:
            return GATED  # opaque bash — fail closed
        return GATED if bash_command_is_gated(cmd) else ALLOWED

    # Explicitly gated categories (push, PR/merge, external SaaS writes, all
    # cloud/AWS writes, deploys) and everything else — fail closed.
    return GATED
