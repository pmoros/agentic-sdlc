---
agent: agent
description: (Re)authenticate the session's AWS SSO profiles. Reuses the existing browser login when the token is still valid (zero interaction); only opens the browser when the SSO token has actually expired. Wraps scripts/aws-login.sh and respects the session .env allow-list.
---

# AWS Reauthenticate

Refresh AWS credentials for this work session. Backed by
`scripts/aws-login.sh`, which reads the session `.env`
(`AWS_PROFILE` / `AWS_DEFAULT_REGION` / `AWS_ALLOWED_PROFILES`).

**Key behaviour:** it does **not** blindly re-login. It first checks
`aws sts get-caller-identity`; if the SSO token is still valid the profile is
reused with **zero interaction**. A browser only opens when the token has
genuinely expired — and one login covers every profile on the same SSO start
URL. Any profile not in `AWS_ALLOWED_PROFILES` is refused.

## Steps

### 1. Resolve context (no auth)

Run from the session folder (or any subdir — the script walks up to find `.env`):

```bash
scripts/aws-login.sh --list
```

Report the resolved profile, region, and allow-list back to the user.

### 2. Reauthenticate

Because `aws sso login` needs the user's TTY/browser, **when a login is
actually required do not run it in a blocking foreground agent call** — it will
hang. Prefer one of:

- Tell the user to run it themselves via the `!` prompt:
  > `! scripts/aws-login.sh` (default profile) or `! scripts/aws-login.sh --all` (every allowed profile)
- Or run it in the **background** so the agent isn't blocked while the user
  completes the browser approval.

When the token is still valid, the script just prints `credentials valid …
skipping login` and exits — safe to run inline.

```bash
scripts/aws-login.sh                 # reauth the session default profile
scripts/aws-login.sh cw-partner      # a specific allowed profile
scripts/aws-login.sh --all           # every profile in AWS_ALLOWED_PROFILES
scripts/aws-login.sh --force         # force a fresh sso login
```

### 3. Confirm

The script re-verifies with `get-caller-identity` after any login and prints
the account + ARN. Relay success (or the exact error) to the user. If a
profile is refused, point them at `AWS_ALLOWED_PROFILES` in the session `.env`.

## Notes

- The `sso_start_url` in `~/.aws/config` must **not** carry a trailing `#/`
  fragment — that hashes to a different token cache file and forces a needless
  re-login. See `.agents/rules/aws.instructions.md` → *Session AWS environment*.
- For fewer prompts over time, migrate `~/.aws/config` profiles to a shared
  `[sso-session]` block (enables refresh tokens). Documented in the same rule.
