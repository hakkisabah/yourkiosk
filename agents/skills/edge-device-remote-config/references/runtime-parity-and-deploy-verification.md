# Runtime parity & deploy verification

Two checks that keep "the fix is committed" from being mistaken for "the fix is running", and keep a
feature from working in one runtime and silently failing in the other.

## 1. Runtime parity matrix

When the same device ships two runtimes (native window / embedded browser), every policy that can
reject content must be checked in both. Fill this in per feature and keep it in the repo:

| Concern | Native path | Browser path | Shared? |
|---|---|---|---|
| host allow-list | `dogrula_url()` before fetch | proxy endpoint, server-side fetch | must be one helper |
| content-type / magic bytes | image policy | proxy response type | one helper |
| cache lookup + freshness stamp | disk cache | Cache API / localStorage | same key shape |
| trigger document polling | background sync thread | long-poll endpoint | same file, same parser |
| "asset rejected" handling | skip item and advance | keep screen, show nothing | decide once |

Rules:

- **A reject is a silent skip by design** (a broken image must not freeze a kiosk) — which is exactly
  why a one-runtime policy difference looks like "the feature is off" rather than an error. Log a
  single INFO line on the exception path ("host accepted via public-asset rule") so the log states
  which rule won.
- **Test the verdict, not the call.** For each runtime, assert the same URL yields the same
  allow/deny decision, and that a loopback/private address is denied in both.
- **An exception added under pressure belongs in the shared layer immediately.** Adding it to the
  browser proxy to unblock a demo is the standard way the native path stays broken for weeks.

## 2. Did the change actually ship?

Chain: source → build output → published artifact → device cache → screen. A break anywhere shows the
old symptom with green tests.

### Build freshness

- A build step that runs **only when the output directory is missing** never rebuilds after a code
  change: `if [ ! -f dist/index.html ]; then build; fi`. Make it `! -f dist/index.html || any source
  file newer than dist/index.html`, and use `find <src dirs> <entry html> <config files> -newer
  dist/index.html -type f | head -1` to test it in one command.
- Never silence the build: `npm run build >/dev/null 2>&1 || warn …` hides a failing type check and
  leaves the previous bundle in place. Let it print, and return non-zero.
- Stamp the output after a successful build (`dist/version.json` = commit + timestamp) and print that
  stamp in the runtime's diagnostics. "Which bundle am I running?" then has a one-line answer.

### Published artifact

Fetch what the user's browser/device fetches, then assert on content:

```bash
curl -sS "$CDN/" | grep -oE 'assets/index-[A-Za-z0-9._-]+\.js' | sort -u   # what is referenced
curl -sS "$CDN/assets/index-XXXX.js" -o /tmp/live.js                        # every chunk, not just the entry
grep -c "$REAL_ID_FROM_ENV" /tmp/live.js        # must be >= 1
grep -cE 'X{6,}|placeholder' /tmp/live.js      # must be 0
```

- Grep **every** referenced asset: lazily imported views and schema JSON land in their own chunks, so
  checking only the entry bundle reports a false pass.
- Search for the **real identifier's presence**, not only the placeholder's absence: a bundle built from
  the example env has both a fresh hash and a passing freshness check.
- Beware false positives on the placeholder patterns: a generic word like `EXAMPLE`/`ORNEK` appears
  legitimately in UI copy. Match the structural shapes (`eu-central-1_XXXX…`, `1111-2222-…`,
  runs of 20+ `X`) instead.
- Cache invalidation is not a correctness mechanism: JSON documents published with
  `Cache-Control: no-store` are revalidated anyway, and a fixed-prefix invalidation is one path per
  publish (first 1,000/month free). Resolve the distribution from the served hostname rather than a
  hard-coded id, and print the id used.

### A gate that fails can itself be the bug

A pre-merge/pre-deploy gate is code, and it lies in the same ways: run the suite from the wrong
working directory and the test runner exits with a **collection error** (exit 2) that reads exactly
like "200 tests broken"; run it on a branch that is commits behind with a dirty tree and the failures
belong to neither side.

- Invoke runner commands with an explicit `cwd=` for the subproject that owns them
  (`subprocess.run(["tools/test.sh", "tests", "-q"], cwd=repo/"app")`) — a script that assumes the
  caller's directory works when you run it by hand and fails when a gate runs it.
- Before fixing code because a gate went red, read the gate's own output: a collection/import error,
  a "not found" path, or a dirty-tree warning means fix the gate. Then prove the gate by running it
  once on a known-good tree and seeing every row green.
- Report exit codes and the command that produced them, not just "tests pass". A gate whose output is
  swallowed (`>/dev/null 2>&1`) cannot be trusted either way.

### Device cache

- A runtime that serves from cache on an unchanged freshness stamp needs the stamp bumped on every
  content write (see SKILL.md §5.2). When reviewing "the panel says saved, the screen is stale",
  fetch the stamp, save once, fetch again — before reading any rendering code.

## 3. Observability minimum for a display pipeline

One INFO line at each state transition is enough to end the guessing permanently:

```
content loaded: <key> · <region> · N records · M assets (stamp=…)
asset mode started: M assets
asset showing: 1/M · <url>
asset rejected: <url> → reason
```

Then "nothing shows on screen" splits cleanly into: no records selected (upstream), asset rejected
(policy), or rendering (layout). Without these lines every report costs a full re-derivation of the
pipeline, and the user is right to say the work was not understood.
