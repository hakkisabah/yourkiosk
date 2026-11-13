---
name: github
description: "GitHub via gh CLI: PRs, issues, reviews, repos, auth."
version: 2.0.0
author: Ben Barclay (benbarclay), DSH Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  agents:
    tags: [github, gh, git, pull-requests, issues, code-review, repos, auth, ci]
    category: software-development
    related_skills: [codebase-inspection, requesting-code-review]
---

# GitHub

Work GitHub end to end with the `gh` CLI (REST fallback where noted): auth,
issues, the PR lifecycle, issue-to-PR delivery, code review, and repo
management. This skill consolidates six former skills; each workflow lives
complete in its reference file — ALWAYS read the matching reference before
starting that workflow, the body below only routes.

## Routing

| Task | Read first |
|---|---|
| Auth broken / new machine / token or SSH setup / gh login | `references/auth.md` |
| Create, triage, label, assign, close issues | `references/issues.md` |
| Branch, commit, open PR, watch CI, merge | `references/pr-workflow.md` |
| Carry an ISSUE to a verified PR (full delivery loop) | `references/issue-to-pr.md` |
| Review someone's PR: diffs, inline comments, verdict | `references/code-review.md` |
| Clone/create/fork repos, remotes, releases; **first-time publish of a local project** (pre-flight leak/size checks, empty-repo rule, license by runtime) | `references/repo-management.md` |
| Branch protection, rulesets, fine-grained PAT scopes, handing a token to an agent, secret hygiene before `git add -A` | `references/branch-protection-and-tokens.md` |
| Several machines/agents reviewing through GitHub (status gates, labels as state machine, JSON-in-comment) | `references/machine-review-bus.md` |

Supporting assets: `scripts/gh-env.sh` + `scripts/git-credential-token.py`
(auth helpers), `templates/` (PR bodies, bug report, feature request),
`references/ci-troubleshooting.md`, `references/conventional-commits.md`,
`references/github-api-cheatsheet.md`, `references/review-output-template.md`,
`references/branch-protection-and-tokens.md`, `references/machine-review-bus.md`.

## Core discipline (applies to every workflow)

- Preflight once per session: `gh auth status` — if it fails, go to
  `references/auth.md` before anything else.
- Prefer `gh` over raw REST; drop to `gh api` only for endpoints the
  porcelain lacks (the cheatsheet lists them).
- Never report CI green without checking `gh pr checks` yourself; never
  claim merged without verifying `state,mergedAt`.
- Read full context before writing: `gh issue view --comments` /
  `gh pr view --comments` — decisions live in threads, not titles.
- Merge gates are written to the **PR head SHA**, never the default-branch head: a status
  on `main`'s tip leaves the PR's required check at "Expected — waiting" forever while every
  bot reports success. Details: `references/machine-review-bus.md`.
- **Before opening a PR, prove the branch holds exactly your commits:**
  `git log --oneline origin/main..HEAD`. A branch created from a stale/merged local branch shows
  foreign commits and lands `mergeable_state: dirty`; a branch that ended up equal to `main` (a
  cherry-pick or checkout that silently did nothing) opens an empty PR. Cut work branches from the
  remote tip (`git switch -c <feature> origin/main`), and if the wrong history is already there,
  re-cut from `origin/main`, cherry-pick the one commit, then `git push --force-with-lease`. Push
  before `gh pr create`: a head branch that does not exist on the remote is a 422, not a helpful
  error.
- Sweep for duplicates before creating anything:
  `gh pr list --search` / `gh issue list --search`.

## Verification

- The workflow's own reference file defines done for that task.
- Cross-cutting: every claim about remote state (CI, merge, release,
  issue state) is backed by a fresh `gh` read, never memory.
