# Enable Flex Mode

Flex Mode relaxes the default guardrails for a specific, explicitly declared sandbox or local environment. It does **not** remove all guardrails — production, staging, customer-facing environments, and external SaaS APIs remain fully guarded.

## Steps

### 1. Explain what flex mode does
Inform the user:

> Flex Mode allows autonomous write operations (deploys, applies, mutations) for a specific declared environment only. All other environments and external systems remain guarded. This setting applies to the current session only.

### 2. Declare the sandbox environment
Ask the user: "Which environment should be unlocked for autonomous operations?"

Examples:
- `localhost`
- `docker-compose`
- `dev-sandbox` (AWS account 123456789)
- `local kind cluster`

Record the answer as `<sandbox-env>`.

### 3. Optional: unlock specific SaaS APIs
Ask: "Should any external SaaS APIs also be unlocked for this session? (default: no)"

If yes, ask which ones and record them. These must be development/test instances — never production endpoints.

### 4. Update session file
Find the active session in `<work-sessions-repo>/SESSIONS_STATE.md` (sibling `../work-sessions` of this repo; `Status: active`). In that session's `CONTEXT.md`, append to `## Activity log`:
```
- <YYYY-MM-DD HH:MM> flex mode enabled — <sandbox-env>[, <api-1>, <api-2>]
```
If no active session is found, the flex declaration is conversation-scoped only — note this to the user.

### 5. Confirm the new authorization boundary
Show a clear summary to the user and ask them to confirm:

```
Flex Mode active for this session.

AUTONOMOUS (no approval needed):
- All operations targeting: <sandbox-env>
- localhost and dev containers (always in flex scope)
[- <unlocked SaaS APIs>, if any]

STILL GUARDED (always require explicit approval):
- Production, staging, and all customer-facing environments
- git push to any remote
- gh pr create / merge
- Destructive operations (delete, destroy, remove) — elevated caution applies regardless of mode
- Any environment or API not listed above
```

**Wait for the user to confirm this summary before considering flex mode active.**

### 6. Reminder
Inform the user that flex mode is session-scoped only. It resets when the session ends. To re-enable in a future session, run this prompt again.
