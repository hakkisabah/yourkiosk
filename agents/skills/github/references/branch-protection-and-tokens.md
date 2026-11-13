# Branch protection, PAT scopes, and secret hygiene (REST, no `gh`)

When `gh` is absent or the token is a fine-grained PAT, everything here is `curl`
against `https://api.github.com`. All calls need
`Authorization: Bearer <token>` and `Accept: application/vnd.github+json`.

## 1. Fine-grained PAT: smallest scope that does the job

| Role | Repository permissions |
|---|---|
| Setup/admin (protection, labels, dependabot) | **Administration: RW**, **Contents: RW**, **Pull requests: RW**, **Issues: RW**, **Commit statuses: RW**, Metadata: R (implied) |
| Developer agent (open a PR **and merge it**) | **Contents: RW** (merge writes to the branch), **Pull requests: RW**, **Issues: RW**, **Commit statuses: RW** — no Administration |
| Reviewer bot / CI-ish agent (post statuses, comment, label) | Contents: R, **Pull requests: RW**, **Issues: RW**, **Commit statuses: RW** — **no Administration** |
| Read-only watcher | Contents: R, Metadata: R |

Rules:
- One token per machine/role; a leaked bot token must not be able to rewrite
  protection rules.
- Expiry 30 days for setup tokens; revoke after the job.
- Verify before doing anything else:
  `curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat $TOK)" https://api.github.com/repos/OWNER/REPO`
  → `200` ok, `404` token cannot see the repo (wrong owner or not selected in
  "Only select repositories"), `403` permission missing for the call you tried.

## 2. Handing a token to an agent without leaking it

Never paste a token into chat, a commit, a log, or a command line that gets
logged. Have the user write it into a 0600 file and hand over only the path:

```bash
mkdir -p ~/.config/dsh-secrets && chmod 700 ~/.config/dsh-secrets
read -rsp "token: " T && printf '%s\n' "$T" > ~/.config/dsh-secrets/github-OWNER-REPO.token && unset T
chmod 600 ~/.config/dsh-secrets/github-OWNER-REPO.token
```

In code, read it with `Path(...).read_text().strip()` and pass it into headers;
fall back to `GH_TOKEN`/`GITHUB_TOKEN`. Print HTTP codes, never the token.

## 3. Branch protection: the solo-repo trap

GitHub **does not let you approve your own PR**. On a single-human repo,
`required_approving_review_count: 1` makes every PR permanently unmergeable.
Use approvals **0** and make the security gate a **required status check** that a
bot posts (e.g. `security/review`). Add real approvals only when a second
account is a collaborator.

`PUT /repos/OWNER/REPO/branches/main/protection`:

```json
{
  "required_status_checks": {"strict": true, "contexts": ["<check-name>"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {"required_approving_review_count": 0, "dismiss_stale_reviews": true},
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
```

Pitfalls:
- **Do not require a check context that has never run.** GitHub then shows
  "Expected — waiting" forever and nothing merges. Apply the PR rule first, let
  the bot post the status once, then add the context.
- `enforce_admins: true` is what stops an admin (you) from bypassing the gate —
  without it the rule is advisory.
- Verify by reading back `GET .../branches/main/protection` and asserting
  `enforce_admins.enabled` and `allow_force_pushes.enabled == false`; a `200` on
  the PUT is not proof the shape landed.
- The UI equivalent is Settings → Branches → add rule for `main`; note it now
  reads "Add branch ruleset" in newer accounts, same fields.
- **Make the setup script refuse on a check name nothing can produce — not on missing
  evidence.** Two different failure modes get confused here:
  - *Typo / unknown context* (`security/revie` instead of `security/review`): nobody will
    ever post it, so every PR waits forever. Refuse, print the known set, exit non-zero;
    a `--force` flag covers the deliberate case.
  - *Known context with no status on the branch head*: **advisory, not a stop.** Statuses
    live on the PR head commit; with squash-merge the reviewed commit never enters `main`,
    so `main`'s history carries no statuses at all and "no evidence" is the normal state of
    a healthy repo. Blocking on it makes the tool unusable (and pushes people to `--force`,
    which removes the guard). Print a warning naming the machine that has to run, and how to
    roll back, then proceed.
  Keep a read-only `--status` mode that prints the live protection fields, which contexts
  are required, and what the open PRs' heads carry — the user asks "is the gate on?" far
  more often than they change it, and answering it must not require write scope.
- **`enforce_admins: true` blocks the owner too.** A direct `git push origin main` fails with
  `remote: error: GH006: Protected branch update failed … Changes must be made through a pull
  request`. That rejection is the proof the gate is live — quote it instead of loosening the
  rule to land your own commit. `required_linear_history: true` additionally forbids merge
  commits, so the only merge methods are squash and rebase.
- **Rollback is a PUT, not a delete:** re-send the same payload with
  `"required_status_checks": null` to drop the required contexts while keeping the PR rule,
  force-push ban and `enforce_admins`. Give the setup script an empty `--check ""` path for it so
  a broken producer can be unblocked in one command.

### Free account: a private repo cannot have protection at all

On a private repo owned by a free account, both
`PUT /repos/{o}/{r}/branches/{branch}/protection` and `POST /repos/{o}/{r}/rulesets`
answer `403 Upgrade to GitHub Pro or make this repository public to enable this
feature`. There is no API workaround — pick one deliberately and say why:

- **Public:** protection, rulesets, secret scanning and push protection are all
  free. Before flipping, scan the entire history for secrets and tell the user that
  the commit author e-mail becomes public (rewriting it changes every SHA, so that
  is a separate decision). Visibility is reversible from Settings → Danger Zone,
  but forks/mirrors that already exist stay public.
- **Paid plan:** keeps it private; secret scanning for private repos is a further
  paid add-on, so never promise it.

Do not flip visibility as a side effect of retrying a failed call — name the
constraint, state the trade-off, then do it.

## 4. Labels and statuses (the pieces a review bot needs)

- Labels: `POST /repos/OWNER/REPO/labels` with
  `{"name":"a/b","color":"0e8a16","description":"…"}`; `422` means it
  already exists — treat as success. Names containing `/` must be URL-quoted when
  used in a path (`/issues/N/labels/a%2Fb`).
- Commit status:
  `POST /repos/OWNER/REPO/statuses/<sha>` body
  `{"state":"success|failure|error|pending","context":"<name>","description":"≤140 chars"}`.
  Context is the string branch protection matches on.
- PR comments are issues comments:
  `POST /repos/OWNER/REPO/issues/<pr>/comments`.
- Dependabot alerts: `PUT /repos/OWNER/REPO/vulnerability-alerts` (free, and it
  works on private repos). Secret scanning / push protection on a **private** repo
  needs GitHub Secret Protection (paid) — do not promise it; on a public repo both
  are free and enabled with
  `PATCH /repos/{o}/{r}` `{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}`.
- Alert **reads** need their own scopes: `GET /dependabot/alerts` requires
  "Dependabot alerts: Read" and `GET /secret-scanning/alerts` requires "Secret
  scanning alerts: Read". Without them both answer
  `403 Resource not accessible by personal access token` even though writes succeed.
- Alerts are evaluated against the **default branch**: fixing a dependency on a
  feature branch leaves the count unchanged until the fix is merged into `main`.
  Verify with `GET /dependabot/alerts?state=open` *after* the merge, not before —
  and say "will clear on merge" instead of "fixed" until you have re-read it.
- Triage without those scopes: read the committed lockfile(s) and POST the exact
  name/version pairs to OSV —
  `POST https://api.osv.dev/v1/querybatch` with
  `{"queries":[{"package":{"name":"vitest","ecosystem":"npm"},"version":"3.2.7"}],…}`
  (≈500 per call, no auth). The hit count matches Dependabot's, and
  `GET https://api.osv.dev/v1/vulns/<id>` gives the `fixed` version, so you can name
  the package and the target version before asking the user for more scopes.

## 6. Probe each capability separately — one 200 proves one endpoint

A fine-grained token is a set of independent switches, and earlier successes say
nothing about the next call: creating labels, posting commit statuses and creating
pull requests are three different permissions. A token with Administration + Contents
+ Issues + Commit statuses can still fail PR creation with
`403 Resource not accessible by personal access token` because `Pull requests: RW`
is missing — while every status and label write keeps working.

- Before promising a workflow, hit the exact endpoints it needs, cheapest first:
  `GET /repos/{o}/{r}` (identity) → `POST /statuses/<sha>` (merge gate) →
  `POST /issues/N/labels` (state) → `POST /pulls` (the one people forget).
- On `403 Resource not accessible`, do not try variants: name the missing permission
  and give the one-click fix (fine-grained token → Edit → tick the permission → Save;
  the token string does not change, so the file on disk stays valid).
- **Merging is a fourth switch.** `PUT /pulls/N/merge` needs **Contents: RW** even
  though opening the PR only needed `Pull requests: RW`; without it you get
  `403 Resource not accessible by personal access token` after a *successful* PR
  creation. Cheap probe before promising a merge:
  `POST /repos/{o}/{r}/git/blobs -d '{"content":"x","encoding":"utf-8"}'` — `403`
  means no Contents write (the blob is inert, it never becomes a commit). A
  reviewer bot should *not* have merge rights; keep the merge permission on the
  developer token only.
- Sequence that avoids wasted passes: identity → status write → label write → PR
  create → blob write (merge). Report the first `403` you hit, not all of them.
- Step blocked by permissions? Finish everything else, push the branch, and leave a
  precise unblock instruction — add scope X, or use the compare URL GitHub prints
  (`…/pull/new/<branch>`) for a two-click PR. Never weaken branch protection just to
  land your own change; that removes the gate you were asked to install.
- **Admin-only calls are machine-scoped, so a 403 is first a WHERE question.** A
  protection/ruleset write from a reviewer box fails by design — those tokens carry no
  Administration. Before touching permissions, check: (1) which host and which token file
  ran it, (2) whether `GH_TOKEN`/`GITHUB_TOKEN` in that shell shadows the file (print the
  token *source* in the tool's banner so this is visible, never the value), (3) re-run the
  same idempotent PUT from the admin machine — if it succeeds there, nothing is broken.
  Then report the correct host, not a code fix.
- **Never slice a response body you are about to `json.loads`.** A helper that returns
  `body[:400]` for logging will make a healthy `200` look unreadable (`corrupt JSON`,
  `HTTP 200 but no fields`). Keep the full body for parsing and truncate only where you
  print it.

## 5. Secret hygiene around `git add -A`

Generating a key/token mid-session ("make me a signing key") creates a file one
stray `git add -A` away from a public history. Order matters:

1. Add the ignore entries FIRST (`<name>`, `<name>.*`, state files, `.tmp`),
   then create the secret.
2. Prove the ignore works before staging:
   `git check-ignore -v kiosk/key kiosk/state.json` (silent + exit 1 = NOT
   ignored) and `git add -A -n | grep -iE 'key|token|\.env|secret'` (expect only
   source files, no data/secret files).
3. After pushing, `git ls-tree -r --name-only HEAD | grep -iE 'token|key$|\.env$'`
   — the tree is what leaked, not the working directory.
4. Editing `.gitignore` with a text patch can silently merge two lines
   (`a/` + `b/` → `a/b/`); re-check with `git check-ignore -v` after the edit
   rather than trusting the diff.
