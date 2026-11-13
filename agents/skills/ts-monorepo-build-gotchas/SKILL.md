---
name: ts-monorepo-build-gotchas
description: "Use when a TS monorepo build or test fails oddly."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [typescript, vite, vitest, jsdom, aws-cdk, lambda, monorepo, build, troubleshooting]
---

# TypeScript monorepo build/test gotchas

## When to Use

- `npm install`/`npm ci` reports success but `vite`, `vitest`, `tsc`, or
  `vue-tsc` are missing from `node_modules/.bin`.
- Vitest tests fail with `Cannot read properties of undefined (reading 'clear')`
  or a `--localstorage-file` warning.
- A Vue component mount throws `Could not find injected layout`.
- `vue-tsc`/`tsc` reports `ImportMeta.env`, `TS6059 rootDir`, or duplicate
  identifier errors.
- A Lambda deployed from a compiled `dist/` fails with module-resolution or
  ESM/CJS errors.
- `cdk synth`/`cdk deploy` complains about `--app` or a missing asset.
- The test suite is green but the build (`tsc`/`vue-tsc`) fails — or the reverse.
- The build fails **inside a `*.test.ts`** on the user's machine (`Cannot find module
  '@vue/test-utils'`, implicit `any`) while the same suite passes locally — see §15.
- `tsc` throws `TS2345`/`TS18047` only after a refactor hoisted a null check or
  widened a literal union, with tests still green.
- `vitest`/`vue-tsc` aborts with `FatalProcessOutOfMemory` or a parent unit restarts in a loop —
  a memory-ceiling problem, see §16.
- Dependabot / `npm audit` reports advisories in devDependencies (`vite`, `minimatch`, `glob`) and the
  fix has to survive the next `npm install` — see §17.

Failure modes that look like app bugs but are toolchain/environment issues.
Check these before reading application code.

## 1. `npm install` says "up to date" but deps are missing

`NODE_ENV=production` exported in the shell (or `omit=dev` in `.npmrc`) makes npm
skip devDependencies. Symptom: `vite: not found`, `vitest` absent from
`node_modules/.bin`, yet install reports success.

Fix: `npm ci --include=dev` / `npm install --include=dev`. If a stale
`node_modules/.package-lock.json` still fools npm, `rm -rf node_modules` first.

A warning like `install-scripts N packages had install scripts blocked because they are not covered
by allowScripts` (`esbuild`, `vue-demi`) is **not** the same failure: the platform binary package
(`@esbuild/linux-x64`) is installed as a regular dependency, so the tool still works. Verify instead
of panicking — `node -e "require('esbuild').version"`, then run the real build once. Only if that
fails does the blocked postinstall matter.

## 2. `localStorage is not available because --localstorage-file was not provided`

Node 22+ defines its own experimental `globalThis.localStorage` getter, which
shadows jsdom's. In vitest+jsdom, `localStorage` is `undefined` and any
`localStorage.clear()` throws `Cannot read properties of undefined`.

Fix: a `setupFiles` module that installs an in-memory `Storage` on `globalThis`
when the existing one has no `getItem`. Also stub `ResizeObserver`,
`window.matchMedia`, `CSS.supports`, and `window.scrollTo` (jsdom throws
"Not implemented" on scrollTo, and vue-router's scrollBehavior calls it).

## 3. Vuetify component mounts fail with `Could not find injected layout`

`v-app-bar` / `v-main` require an ancestor `v-app`. In tests, wrap the component
under test in `h(VApp, null, { default: () => h(Component) })` instead of
stubbing layout components (stubbing removes the text you assert on).

Mounting a real Vuetify view (plugin required, `test.css: false`, integration
mount that asserts the payload instead of stubbing everything):
`references/vue-vuetify-jsdom-tests.md`.

## 4. `vue-tsc`/`tsc`: `Property 'env' does not exist on type 'ImportMeta'`

A tsconfig `types: [...]` array REPLACES the default type inclusion. Add
`vite/client` to it, or `import.meta.env` is untyped.

## 5. `TS6059: File ... is not under 'rootDir'`

Happens with a shared folder outside the package. Set `rootDir` to the common
parent (e.g. `".."`) and keep `outDir` inside the package. Output then nests as
`dist/<package>/src/...` plus `dist/<shared>/...` — update IaC handler paths to match.

## 6. Lambda: `Cannot find module '@shared/types'` or `exports is not defined`

- `tsc` does **not** rewrite `paths` aliases. Add `tsc-alias` to the build script
  (`tsc -p tsconfig.json && tsc-alias -p tsconfig.json`).
- If the package has `"type": "module"` but tsc emits CommonJS, Node reads the
  nearest package.json and treats emitted `.js` as ESM. Write
  `dist/package.json` = `{"type":"commonjs"}` in a post-build step.
- Emitting real ESM instead requires explicit `.js` extensions in relative
  imports — usually more churn than it is worth.

Verify the artifact instead of assuming:
`node -e "const h=require('./dist/<pkg>/src/handlers/x.handler.js'); console.log(typeof h.handler)"`
and invoke the exported handler with a fake event.

## 7. CDK: `--app is required` / asset directory not found

`cdk deploy` needs `infra/cdk.json` with `"app": "node dist/bin/app.js"` when the
app is compiled (there is no ts-node by default). Also: build the Lambda source
BEFORE synth/deploy, because `Code.fromAsset('../backend/dist')` must exist.
Verify with `npx cdk synth` — it needs no AWS credentials when stacks are
env-agnostic. Inspect `cdk.out/*.template.json` to assert authorizers, methods,
and IAM wiring actually landed.

## 8. Vitest async navigation assertions


`await new Promise(r => setTimeout(r, 0))` is not enough when the navigation
lazy-loads a route component. Use a polling `waitFor(predicate)` helper
(~10 ms interval, ~3 s timeout).

## 9. Green test suite, failing build — test runners do not type-check

Vitest/esbuild strip types; they resolve nothing. A name or scope error passes
every test and fails only under the real compiler. Concrete shape: a per-request
local declared INSIDE `try` and referenced in the matching `catch` →
`TS2304: Cannot find name 'x'` from `tsc`, while all tests stay green — and at
runtime that same line is a `TypeError` on the error path, i.e. a crash that
only fires when something else already went wrong.

Rules:
- Declare per-request locals that both `try` and `catch` need ABOVE the `try`.
- Run `tsc --noEmit` / `vue-tsc --noEmit` (or the package `build` script) after
  any refactor, before claiming the change works. The test suite is not the gate.
- When adding a new integration point, drive it once through the built artifact
  (`node -e "require('./dist/...')"` with a fake input) — that is the only run
  that exercises the emitted code, its module resolution and its error paths
  together.

## 10. Narrowing and literal unions lost in "harmless" refactors

Type narrowing lives in the expression, not in a boolean variable. Hoisting a
guard is the classic way to lose it:

```ts
// narrows — `a` is non-null at the call
if (!a || !b) return null;
use(a, b);

// does NOT narrow — TS18047 / TS2345 at `use`
const hasA = Boolean(a), hasB = Boolean(b);
if (!hasA || !hasB) return null;
use(a, b);
```

Fix by narrowing into a value (`const x = cond ? a : null`) or keeping the guard
inline. Do not "fix" it with `a!` — the compiler is pointing at a path the tests
never take.

Related: an `as const` array of a string-literal union (`readonly ['a','b']`)
checked with `ARR.includes(value)` where `value: string` fails with
`TS2345: Argument of type 'string' is not assignable to parameter of type
'a' | 'b'`, because the parameter type is the narrow union. Widen the list
(`([...ARR] as string[])` or a typed `<T>[]` declaration) instead of casting the
argument you are validating.

## 11. Tests import gitignored fixtures → the clean-clone build fails

Symptom: `npm run build` (`vue-tsc --noEmit` / `tsc --noEmit`) dies with
`TS2307: Cannot find module '../../kiosk/lastSystemData.json'` on a fresh clone,
while the identical command passes on the machine that produced the data file.
Cause: the fixture is a real-device artifact in `.gitignore`, and the typecheck
covers `tests/**/*.ts`, so `import`/`await import('…json')` inside a test is a
hard build dependency on a file the repo does not contain. The working tree can
never reproduce it.

Rules:
- Never statically import a fixture the repo does not track. Read it at runtime
  with `import.meta.glob('../../../kiosk/*.json')`: the key set is resolved from
  what actually exists, so a missing file is an absent key — no TS2307, no throw.
- Gate only the data-dependent suites, keep synthetic ones unconditional:
  `describe.skipIf(!veriVar)(…)` plus a `console.warn` naming the expected
  paths, so a skipped suite is visible instead of silently green.
- Do NOT reach for `node:fs`/`node:path` in a `// @vitest-environment jsdom`
  file: that environment shims node builtins and both fail at runtime
  (`fileURLToPath is not a function`, `resolve is not a function`).
  `import.meta.glob` is the env-safe route; `process.cwd()`-relative resolution
  is the fallback only for `node`-environment test files.
- Verify in the place the bug lives: `git clone <remote> /tmp/x && cd /tmp/x/web
  && npm install --include=dev && npm run build && npm test`. A green local run
  proves nothing here.

## 12. Major vitest bump → `vite.config.ts` stops type-checking

Symptom, immediately after upgrading vitest: `vitest run` passes but
`vue-tsc --noEmit` / `tsc --noEmit` fails in `vite.config.ts` with
`TS2769: No overload matches this call … 'test' does not exist in type
'UserConfigExport'`.

Cause: the `test` block is only part of the type when `defineConfig` is imported
from `vitest/config`. Older versions leaked it through `vite`'s export; new ones do
not.

Fix: `import { defineConfig } from 'vitest/config'`. Keep `vite`'s `defineConfig`
only for configs with no `test` block. Same class of failure follows every
toolchain major (eslint flat config, `vitest.workspace` → `projects`): the config
file is type-checked, so a silent type-surface change turns the build red while
tests stay green.

After such an upgrade, confirm the advisories that motivated it actually left the
tree: run `npm audit` (or an OSV query over the committed lockfile) and check the
package is gone or on a fixed version — a dependency can disappear entirely rather
than be bumped.

## 13. Module-level browser stubs leak across tests in the same file

Vitest runs every `describe` in one module scope, so anything stubbed at module
level (or in a file-wide `beforeAll`) carries into later tests — and the failure
looks like a bug in the component, not in the test.

Two shapes, both seen in a single jsdom suite:

- **`document.body.innerHTML = ''` in one `afterEach`** removes the `#app` mount
target. A later test that calls `mount('#app')` warns and renders nothing, so the
assertion times out with `expected null not to be null`. Fix: create the mount
target inside the test (`document.body.innerHTML = '<div id="app"></div>'`)
before mounting — never rely on markup left by `beforeAll`.
- **A warm `caches`/`fetch` stub** from an earlier real-data test serves the cached
body, so the "data missing" scenario never reaches the 404 path and asserts the
wrong message. Fix: re-stub with a **fresh empty store** in that test
(`caches.open → {match: async () => undefined, …}`) and re-stub `fetch` with the
exact responses that scenario needs.

Rule: a test that asserts *absence* or *failure* must install its own clean slate
(body markup, cache store, fetch responses) instead of inheriting the file's
fixtures. When the message under assertion mentions a filename, assert on the
filename and on the fix command it prints — a stack-trace-free product message is
the thing being tested.

## 14. Tests that iterate live/real data break on a date boundary

Symptom: a suite green yesterday fails today with `IndexError` or an empty-list
assertion, with no code change. Cause: the test mounts the app against the REAL
fixture file, whose valid records change with the calendar (expired broadcasts,
"today's" block). Freezing the clock does not help — the data itself is trimmed by
real time, so the item count the test iterates shrinks.

Rules:
- Seed what the test asserts on. Replace the data at its seam, e.g.
  `monkeypatch.setattr(type(app), "pharmacies", property(lambda self: FIXTURE))`, and
  then re-run the app's own prepare step. Do not assign the DERIVED list
  (`app.ticker_items = [...]`): the prepare step rebuilds it from the source and
  silently discards your seed — the test keeps failing and the fix looks wrong.
- Keep one or two real-data tests, gated with `skipIf` when the file is absent, so a
  clean clone stays green while a device machine still exercises reality.
- When a test loops `n` items, assert `len(fixture) >= n` explicitly — that converts
  a confusing `IndexError` into "the fixture is too small", which points at the data
  instead of the code.

## 15. The release typecheck compiles TEST files → a new test breaks the build

Symptom: `npm run build` (`vue-tsc --noEmit` / `tsc --noEmit`) dies with
`TS2307: Cannot find module '@vue/test-utils'`, `TS7006: Parameter … implicitly has an 'any' type`
or `TS2339` inside a `*.test.ts` — on the user's machine only, while the same suite is green for you.
Nothing is wrong with the test; the app's own typecheck is compiling it.

Cause: `tsconfig.include` lists `src/**/*.ts` (or `tests/**`), which matches test files, so the
RELEASE typecheck pulls them in. Test-only packages live in `devDependencies`; a machine that
installed without them (`NODE_ENV=production`, `--omit=dev`) cannot resolve the import, and the build
the deploy script runs fails before Vite is ever reached.

Fix — two configs, one gate each:

```jsonc
// tsconfig.json (app / release)      → test files are NOT type-checked
"exclude": ["src/**/*.test.ts", "src/**/__tests__/**"]

// tsconfig.test.json (tests)         → everything, plus runner globals
{ "extends": "./tsconfig.json", "compilerOptions": { "types": ["vitest/globals"] }, "exclude": [] }
```

with a separate `"typecheck:test": "vue-tsc --noEmit -p tsconfig.test.json"` script, so test typing
keeps working without being a release dependency.

Rules:
- **A config change ships in the SAME commit as the code that needs it.** An uncommitted `tsconfig`/
  `vite.config` edit makes the change look finished locally and breaks the release for everyone else
  — the worst shape, because the suite stays green and only the deploy fails.
- When a deploy/publish script builds, run **that script** (`--dry`/`--kuru` where it exists) before
  saying the change is done, and reproduce the user's environment shape: `NODE_ENV=production npx
  vue-tsc --noEmit`, once more with the test-only package moved out of `node_modules`.
- A deploy script that builds must fail loudly when the toolchain is missing rather than with
  `vite: not found`: check `npx --no-install vue-tsc --version` and install with `--include=dev`
  when absent (see §1).

## 16. `vitest`/`vue-tsc` dies with `FatalProcessOutOfMemory` on a small-RAM host

Symptom: the toolchain is present and the suite was green, then the run aborts with
`node::OOMErrorHandler` / `v8::internal::Heap::FatalProcessOutOfMemory`, "dumped core", or
`Restart=always` restarts the parent unit every few seconds. On another machine the same command is
fine.

- It is **not** the kernel's OOM-killer: the process aborted against **its own** heap ceiling. V8
derives that ceiling from its defaults (~2 GB, or 8 GB when the parent tool asks for it), never from
physical RAM — so on a 4 GB box the ceiling sits above what the machine can back and the heap grows
into swap until GC gives up.
- `vue-tsc --noEmit` is the biggest consumer (≈0.9–1 GB for a mid-size Vue app), then `vitest`
  (≈0.3–0.6 GB). One command fits on 4 GB; **two concurrent ones plus an agent/gateway process do
  not** — so the fix is a cap **plus serialization**, not "more RAM".
- Do not reach for `ulimit -v`: V8 reserves huge virtual ranges and will fail for no visible reason.
  Cap with cgroups and a `--max-old-space-size` sized from them.

Fix shape and the ready-made runner: `heavy-workload-memory-guard` (§3 unit fields, §4
`scripts/memory-capped-run.sh` with exit 7 = no headroom, 8 = another heavy job running). Measure
before choosing numbers — `systemd-run --user --scope -p MemoryMax=… -p MemoryAccounting=yes` prints
the real peak for each command.

## 17. Dependency advisories: bump the direct dep, `overrides` the transitive ones, then lock it

`npm audit` and the GitHub Dependabot alert list are **two different sources and they disagree**.
Dependabot only reports what an advisory exists for; `npm audit` also flags advisory-less issues
(`glob` < 14.0.2 AbortSignal traversal) and transitive copies Dependabot folds into one alert. Fix the
**union**, then re-run both — stopping at "Dependabot shows 0" leaves an auditable finding behind.

```bash
npm audit --json | python3 -m json.tool | head -50      # per-tree, includes transitive chains
npm ls <paket>                                          # WHO pulls it in — decide before pinning
```

- **Direct dependency** (`vite` in `devDependencies`): raise the range in `package.json`
  (`^6.0.7` → `^6.4.5`) and re-install so the lockfile records the patched version.
- **Transitive dependency** (`minimatch` under `@vue/test-utils → js-beautify → glob/editorconfig`,
  under `vue-tsc → @vue/language-core`): there is no place to bump it — pin it with `overrides`.

```jsonc
"overrides": { "minimatch": "^11.0.1", "glob": "^14.0.3" }
```

  Apply it to **every** tree that reports the advisory (a monorepo's `panel/` and `web/` each carry
  their own lockfile; one shared override in the root is invisible to a workspace that ignores it).
  An override that cannot be satisfied installs cleanly and silently keeps the old version — confirm
  the resolved version in the lockfile, not the intent in `package.json`:

```bash
python3 -c "import json;d=json.load(open('package-lock.json'))['packages'];\
print({k.split('node_modules/')[-1]:d[k]['version'] for k in ('node_modules/vite','node_modules/minimatch','node_modules/glob') if k in d})"
npm audit            # hedef: "found 0 vulnerabilities"
```

- **Lock the fix with a test that reads the lockfile, not the code.** Otherwise the next
  `npm install`/`npm ci` or a dependabot branch resurrects the vulnerable version and nothing turns
  red. Keep a small table of `(paket, etkilenen_alt, etkilenen_üst, ilk_güvenli, GHSA)`, walk every
  `packages[*]` entry whose name matches, compare semver triples, and separately assert that each
  transitive package has an `overrides` entry ≥ first-patched. Also assert the direct dep's declared
  range ≥ first-patched — an override hides the resolve, not the intent.
- Prove it the usual way: revert one override / one range → at least one test must go red; restore →
  green. A lockfile test that stays green under mutation is checking nothing but JSON syntax.
- After the upgrade still run the full gate: `npm run build` (`vue-tsc --noEmit` + `vite build`) and
  the suite. A dependency bump that fixes an advisory can break the build (§9, §12) — the audit result
  says nothing about that.

