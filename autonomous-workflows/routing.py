"""Task-based model selection — the model-routing intelligence.

Maps a worker's ROLE (or task type) to the right Claude model per ADR-001's
tiering (Opus for planning/reasoning, Sonnet for coding, Haiku for classify),
so the swarm spends on the model each task actually needs instead of defaulting
everything to Sonnet 5.

CLI (used by run-worker.sh to resolve ANTHROPIC_MODEL):
    python3 routing.py <role-or-task-type>   # prints the model id
"""
from __future__ import annotations

ROLE_MODEL = {
    "planner": "claude-opus-4-8",     # hard reasoning / decomposition / final review
    "coder": "claude-sonnet-5",       # bulk read-edit-test (near-Opus coding, ~40% cheaper)
    "classifier": "claude-haiku-4-5", # triage / routing / cheap subagents
}

TASK_TYPE_ROLE = {
    # reasoning-heavy -> planner (Opus)
    "plan": "planner", "planning": "planner", "design": "planner",
    "architect": "planner", "review": "planner", "research": "planner",
    "spike": "planner", "analyze": "planner", "analysis": "planner",
    "discovery": "planner", "design-review": "planner",
    # implementation -> coder (Sonnet)
    "code": "coder", "coding": "coder", "implement": "coder", "fix": "coder",
    "refactor": "coder", "feat": "coder", "test": "coder", "chore": "coder",
    "build": "coder", "docs": "coder",
    "qa": "coder", "verify": "coder", "validate": "coder",   # QA runs on Sonnet (fresh reviewer)
    # light / triage -> classifier (Haiku)
    "classify": "classifier", "triage": "classifier", "route": "classifier",
    "label": "classifier", "summarize": "classifier",
}

DEFAULT_ROLE = "coder"


def model_for_role(role: str) -> str:
    try:
        return ROLE_MODEL[role]
    except KeyError:
        raise ValueError(f"unknown role {role!r}; expected one of {sorted(ROLE_MODEL)}")


def role_for_task_type(task_type: str) -> str:
    """Map a task type to a role; unknown types default to the coder tier."""
    return TASK_TYPE_ROLE.get(str(task_type).lower(), DEFAULT_ROLE)


def select_model(role: str | None = None, task_type: str | None = None) -> str:
    """Resolve a model: explicit role wins, then task_type, else the coder default."""
    if role:
        return model_for_role(role)
    if task_type:
        return model_for_role(role_for_task_type(task_type))
    return ROLE_MODEL[DEFAULT_ROLE]


if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ROLE_MODEL:
        print(model_for_role(arg))          # it's a role
    elif arg:
        print(model_for_role(role_for_task_type(arg)))  # treat as a task type
    else:
        print(ROLE_MODEL[DEFAULT_ROLE])
