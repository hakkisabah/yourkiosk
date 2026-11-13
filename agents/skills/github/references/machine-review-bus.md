# Multi-machine review bus over GitHub

Pattern for "machine A develops, machine B reviews security, machine C arbitrates"
where the machines cannot reach each other (NAT, no ports, machines asleep).
GitHub becomes the only transport: no inbound connections, durable, authenticated,
and a message posted while a machine is offline is simply waiting when it wakes.

## Channels (pick one meaning per channel, never mix)

| Channel | Use |
|---|---|
| **Commit status** `POST /statuses/<sha>` | the merge gate — branch protection requires the context name |
| **Label** | state machine, and the cheap query a downstream machine polls (`GET /issues?state=open&labels=needs-decision`) |
| **PR comment** | human summary on top, fenced ```json block at the bottom for machines |
| **One rolling log issue** | verdicts for commits that have **no PR** (merged to the default branch directly, or squash-merge commits) |

Give each reviewer its own status context (`review/security`, `review/decision`) so
their verdicts never overwrite each other. One label per state, not per reviewer.

**The status `description` is capped at 140 characters** — it is a headline, not a report.
Always write the full verdict somewhere durable: the PR comment when there is a PR, and
otherwise a single issue titled e.g. `review log (automation)` that every PR-less verdict
appends a comment to. One issue, not one per commit — it stays greppable and does not spam
the repo. `POST /issues/N/comments` needs only `Issues: RW`; `POST /commits/<sha>/comments`
needs `Contents: RW`, which a reviewer must not have.

## Feeding a reviewer cheaply (this is the whole cost model)

- Context comes from `git fetch` + a local `git diff`, **not** from API calls. One
  clone per machine, one fetch per run.
- Exactly one API call to find work (`issues?...&labels=...`), then ~4 calls per
  verdict (status, comment, label add, label remove).
- Keep a `last-reviewed-sha` file. If the remote head equals it, exit **before**
  calling the model — an idle reviewer then costs nothing, which is what makes a
  15-minute schedule viable on an i3.
- Cap the diff (e.g. 120 KB), drop lockfiles/binaries/node_modules, and mask any
  secret-looking match (`abcd***`) before it reaches a model or a comment.
- Split responsibilities: the **script** gathers context and posts results, the
  **agent** judges. A script cannot decide, and an agent should not hand-roll
  HTTP and JSON formatting on every run.
- Reviewers do static review only — no `npm install`, no test runs. Build/test
  verification stays on the developer machine.
- Helper scripts must fail LOUDLY on a bad working directory: resolve the repo path
  explicitly (flag → env var → known locations) and on failure print every path tried
  and exit non-zero. A bundle builder that prints `0 commits / 0 findings` when it
  cannot find the clone reads as "nothing to review", so the pipeline goes permanently
  silent while appearing healthy.
- Never document a JSON payload as a hand-written heredoc. `<<'JSON'` with an embedded
  `"$(git rev-parse HEAD)"` produces invalid JSON (the quotes survive literally) and the
  first run dies in the parser. Ship a `--example` flag that writes a valid template and
  fills the SHA from the repo, and make the consumer report `satır/kolon` plus a pointer
  to that flag on a parse error.
- When a reviewer runs as a DSH cron job, use the scheduler's own `monitor`
  gate (a script whose deterministic stdout is compared tick-to-tick) instead of a
  hand-rolled last-sha file: identical output skips the agent run inside the
  scheduler, so idle ticks cost zero tokens without any extra bookkeeping. See
  `dsh-agent` → `references/background-systems.md`.

## Bootstrap the remote machine with ONE command, not a numbered doc

Multi-step install docs are where users stop halfway and report "hiçbir şey yapılamadı". Ship a
bootstrap script next to the docs (`bash otomasyon/kur.sh i5|i3 [--cron]`) that is idempotent and
prints what it did:

1. run an **environment check** first (never a bare failure later): python version, `git`, `curl`,
   repo clone + `git fetch`, token file exists / mode 0600 / repo `200` / PR-read / label-read,
   state dir writable, scheduler CLI on PATH;
2. write the wrapper scripts into the scheduler's scripts dir (`~/.dsh/scripts/`) with the repo
   path **absolute** inside them — never rely on the cron cwd (`--depo "$DEPO"`), cron jobs run
   with a different working directory than the shell that created them;
3. **verify the monitor script actually emits the deterministic line** before trusting it (a
   reviewer whose gate prints nothing appears healthy and silently never runs);
4. print (or with `--cron`, execute) the job-creation command, skipping if a job with that name
   already exists;
5. **reset the reviewer's last-reviewed marker** (`rm ~/.local/state/<app>/last-sha`) so the
   very first tick reviews HEAD. Without this the first run sees "nothing changed", posts
   nothing, and the pipeline looks dead while it is merely waiting for a new commit — the
   user reports "the agents never talked" and there is nothing to debug;
6. print the *next* step only — the whole reason the doc exists is the checks, not the clicks.

The companion checker (`ortam-kontrol.py --rol i5|i3|kiosk|dev`) prints one line per capability with
`✓/✗` **and a `→ fix` line for every ✗**, and exits `0` ready / `2` missing pieces / `3` no token.
That single output is what a user pastes back when stuck; make it diagnostic, not decorative.

Pitfalls:
- **Mask credentials in every diagnostic.** The remote URL may carry a token
  (`https://x-access-token:github_pat_…@github.com/…`) because someone cloned with it; printing
  `git remote -v` verbatim pastes a live credential into the terminal, the transcript and the
  chat. Match `://[^/@]+@` and replace with `://***@`, and add a separate warning line with the
  fix (`git remote set-url origin https://github.com/o/r.git` — a public repo needs no token)
  plus a "revoke and reissue" note, because the log is already permanent.
- **A generator must refuse when its defaults would silently change the artifact's meaning.**
  A tool whose default parameter sets identity/scope (region, tenant, device, environment) will
  one day be run without the flag and rewrite an existing artifact for the wrong target — the
  output looks valid, so nothing errors. Read the existing artifact, resolve the current mapping,
  compare it with the requested one, and stop (`old → new`, the `--force` flag, exit non-zero)
  unless the user asks for the change. Log the refusal; a silent rewrite of live data is the
  hardest kind of incident to reconstruct.
- **Empty monitor output is normal for the arbiter** when no PR carries the problem label; treat it
  as "nothing to decide", not as a failure. Only the primary reviewer's empty output is suspicious.
- Test the bootstrap in a sandbox (`HOME=/tmp/x`) and with a **fake `dsh`** shim on `PATH`; that
  proves the wiring without creating real jobs in the user's scheduler. Say so plainly when you have
  not run it against the real scheduler.
- The role's prompt file must be read from disk (`"$(cat …)"`), never printed inline in the usage
  text — a prompt dump makes the instructions unusable.
- Every reviewer script must be **Python 3.8-compatible** unless you verified the machine's version:
  avoid `str.removeprefix`/`removesuffix` (3.9+) or ship a tiny helper; old Ubuntu LTS hosts are
  common for idle review boxes.
- **User-facing `.py` tools need an extension-less `sh` wrapper.** Someone will type
  `sh otomasyon/durum.py`; the shell then executes the Python text (`line 2: main: command not
  found`) and it reads as your bug. Ship `otomasyon/durum` (and friends) as `/bin/sh` one-liners
  that `exec python3 "$DIR/betik/durum.py" "$@"` — then `./otomasyon/durum`, `sh otomasyon/durum`
  and `python3 otomasyon/betik/durum.py` all work, and the docs can drop `.py` entirely. A
  shell/python polyglot header is NOT a fix: `from __future__ import annotations` must be the
  first statement, so a dual header breaks every annotated module.

## Answering "is the reviewer alive?" in one read-only command

Ship a status board next to the bootstrap (`durum.py` / `status.py`) that only reads and
prints: the last few commits with their status contexts, open PRs with labels, the most
recent fenced-JSON verdict found in PR comments, and one verdict line.

- Judge **evidence**, not "the latest commit". The head of the default branch is usually a
  squash-merge commit, which no machine reviews and which therefore carries no statuses —
  a naive "latest commit has a status?" check reports "the reviewer never ran" on a healthy
  pipeline. Count each reviewer's contexts across the last N commits **and the open PR head
  SHAs**, report both numbers, and treat a merge commit without statuses as normal.
- **A verdict comment proves the pipeline wrote it, not that the reviewer model ran.** With one
  GitHub account driving every machine, `review/security ✓` looks identical whether an agent or a
  developer session posted it — and a developer session writing the same payload for local testing
  leaves a healthy-looking board over a pipeline that never executed. Verify on the machine: its
  session store (`created_source`), its watcher log, the token's last-used time. When reporting,
  separate "observed running" from "I posted this myself", because the user reads the board as proof.
- A single manual status posted while testing makes a naive `any()` say the pipeline works
  forever. Report per-context counts and the most recent verdict timestamp instead of a boolean.
- Extract verdicts by parsing ```json blocks and keeping objects with a `machine` field, so a
  human-formatted comment cannot be mistaken for a verdict.
- Include the two or three fix-it commands in the output (`dsh cron list`, bootstrap,
  environment check). The user pastes this output when stuck; make it self-explanatory.

## What to review: the PR head, never the default-branch head

A status that gates a merge must land on the **PR head SHA** (`pulls/N.head.sha`). A reviewer
that bundles `origin/main` and posts its status there writes a green commit no PR points at:
the required context stays `Expected — waiting` on the PR forever, the PR is `blocked`, and
every component reports success. This is the default failure mode of a hand-rolled reviewer,
and it survives review because the status really is attached to a real commit — make PR
discovery the primary path, not an afterthought.

```bash
# 1) work list — one API call
GET /repos/$O/$R/pulls?state=open&per_page=30     # number, head.sha, base.ref, labels, draft

# 2) per PR: fetch its head ref, diff against the merge-base with the base branch
#    (never against the base tip: that diff shows other people's merges as your changes)
git fetch origin "+refs/pull/$N/head:refs/remotes/origin/pr/$N" "$BASE_REF"
base=$(git merge-base "origin/$BASE_REF" "refs/remotes/origin/pr/$N")
git diff --no-color -U3 "$base..refs/remotes/origin/pr/$N"
```

The verdict payload must carry the PR number **and** the head SHA it was computed from; if the
head moved between the diff and the status write, re-review instead of posting (otherwise the
gate green-lights code nobody read).

For a push straight to the default branch (no PR), fall back to the previous-commit diff — and
put that verdict in the rolling log issue, because no PR exists to hold the comment:

```bash
base=$(git rev-parse origin/main)
# never hardcode HEAD~50: it dies with "ambiguous argument" on short/shallow history
parent=$(git rev-parse --verify --quiet "$base~1" || true)
[ -n "$parent" ] && git diff --no-color -U3 "$parent..$base"
[ -z "$parent" ] && git show --no-color -U3 --format= "$base"   # root commit
```

Store the sha only after the verdict is posted, so a crash mid-run re-reviews
rather than silently skipping.

## Wiring the gate

1. Reviewer posts its status at least once (so the context exists).
2. Then add that context to branch protection (`required_status_checks.contexts`).
   Adding a context that never ran blocks every merge with "Expected — waiting".
3. Approvals stay at 0 on a solo repo (see
   `references/branch-protection-and-tokens.md` §3).
4. If the reviewer is down, merges wait. That is the point of a gate — say so
   explicitly instead of adding a bypass.

## Letting a reviewer merge (closing the loop)

When the user wants to stop clicking "Squash and merge", the reviewer that holds the last
approval can merge — but only behind guards, because an unguarded auto-merge turns one bad
verdict into a bad `main` with no human in between.

Guards, all of which must pass (refuse and **comment the reason** otherwise):

1. the PR is open and not a draft;
2. `mergeable_state == "clean"` — retry a few times over ~8 s before believing `blocked` or
   `unknown`: GitHub recomputes it asynchronously, so the status you *just* posted is not
   visible yet on the first read. `behind` is a **separate** state, not a bug: under strict
   checks every base-branch merge moves the base, so a PR that was mergeable goes `behind`.
   Update the branch (`PUT /pulls/N/update-branch`, or merge the base into the branch) — but
   that rewrites the head SHA and invalidates *both* verdicts, so re-run the reviewers rather
   than merging on the stale pair. Comment the reason so the developer does not see a silent stall;
3. `head.sha` equals the SHA the verdict was written for — pin it in the merge call too
   (`PUT /pulls/N/merge {"merge_method":"squash","sha":HEAD_SHA}`) so a commit pushed after
   the review cannot ride along;
4. no blocking label, including a **kill-switch** label (`merge/hold`) the user can add to any
   PR — that is the per-PR brake, the scheduler pause is the global one;
5. no other context is `failure`/`pending` on that SHA;
6. the branch was cut from the **current base tip**, not from another unmerged branch. A PR built on
   top of an open PR reports `mergeable_state: dirty` (real conflicts) the moment that other PR is
   squash-merged — the shared commits land on the base under new SHAs. Do not attempt a merge or a
   "update branch": re-create the branch from a freshly pulled base
   (`git checkout -B feat origin/main && git cherry-pick <commit>`) and force-push. That rewrites the
   head SHA, so re-post both verdicts — identical rule to the `behind` case above.
   `dirty` = conflicts, `unknown` = GitHub still computing; retry `unknown`, never `dirty`.

Dual approval: when two machines must both agree, make both contexts required and let the
**second** machine perform the merge, with a flag that re-checks *both* contexts are `success`
before merging. A failure from the first reviewer cannot be overridden — GitHub blocks the merge
on the required context anyway, so the second machine's job is to add an approval, not to veto it.
Ordering is what makes this work: the merger runs after the first reviewer, never before (if it
runs first, "blocked" is the correct, expected answer).

**Give the second machine a verification job, not a rubber stamp.** Its prompt must require, for
each finding the first reviewer wrote, a verdict — confirmed / wrong / unsupported — with one line
of evidence (the file and line it re-read, the command it ran), plus a list of what the first
reviewer *missed*: build-time secrets inlined into a published bundle, host allow-list and TLS gaps,
IAM/ACL scope, missing test evidence. Then put the gate in code: the merge helper refuses unless the
decision is accept, the missed list is empty and every finding is confirmed, printing which
condition failed. Without that, "two approvals" degenerates into one reviewer plus one echo — and
the misses stay invisible because both contexts are green.

After changing a reviewer's prompt file, the scheduler job still holds the **old** text — the
prompt is embedded at creation time. Recreate (or edit) the job, or the machine will keep merging
with the previous policy. Give the installer an explicit refresh flag (`kur.sh i5 --cron
--refresh-job`) that removes and re-creates the job; without the flag it must **print a warning
that the old policy is still running**, not just "job exists, skipped". Finding the id is the
fiddly part — in `dsh cron list` the `Name:` line sits on the line *after* the id, so match the
name and take the id from the preceding line:
`grep -B1 "Name:.*$NAME" | grep -oE '^[[:space:]]*[0-9a-f]{12}'`.

## Boundaries worth stating to the user

- **Close every multi-machine turn with the ordered remainder.** When a step fails, restate it by
  number, then list the remaining steps in the order they must run and who runs them (developer /
  first reviewer / second reviewer) — the plan otherwise lives in three machines' output and the
  user has to reconstruct it. Name the command for each step, not just its goal.
- Reviewers cannot see runtime behaviour; say "static review only".
- Two machines writing the same PR ends with last-write-wins on the comment;
  acceptable because verdicts live in separate status contexts.
- Prefer this over GitHub Actions when the repo is private (minute quotas, extra
  secret surface) and the machines are already idle.
