---
name: spa-api-auth-wiring
description: "Use when wiring SPA route auth, admin roles, or API CORS."
version: 1.0.0
author: agents
license: MIT
platforms: [linux, macos, windows]
metadata:
  agents:
    tags: [auth, authorization, cors, routing, spa, api-gateway, cognito, rbac, security]
---

# SPA + API auth wiring (routes, admin roles, CORS)

## When to Use

- Anonymous visitors land on a login screen instead of the public/landing page.
- The user asks "why does it keep sending me to login?" / "why did the panel
  bounce me out?"
- Adding public pages (landing, registration, share pages) to an app that
  currently gates everything.
- Admin or dashboard menus redirect inconsistently, or an admin area is blocked
  for a user who was just made admin.
- Reviewing or setting CORS for a SPA that calls an API on a different origin.
- Granting, verifying, or revoking admin rights on a deployed app.

## The access model: declare once, in data, fail-closed

- The route table carries the whole contract as meta: `public: true`,
  `requiresAuth: true`, `requiresAdmin: true`, `noindex: true`, plus
  `title`/`description` for page SEO.
- **Default is DENY.** A route carrying no flag is treated as protected.
  Rationale: forgetting `public` on a new page only hides that page, while
  forgetting `requiresAuth` on a panel page exposes it. Fail closed, and say so
  in a comment so the next editor does not "fix" it back.
- Guard logic lives in ONE pure function (e.g. `resolveNavigation(to)` returning
  `true | RouteLocationRaw`), separate from the router plugin, so it is unit
  testable without mounting the app or faking a browser.
- Nested routes inherit the parent's meta. Assert that by resolving the CHILD
  path and checking the merged meta — never by reading the parent record and
  assuming.
- Lock the contract with a test that iterates the exported routes and fails if
  any route or child declares neither `public` nor `requiresAuth`. After that,
  a new page cannot ship silently mis-scoped.
- Serve SEO from the same meta (`useRouteSeo()` reading `route.meta`) rather than
  hand-writing per-page head tags — one declaration, two consumers.

## Every auth redirect must state its reason

The single most confusing symptom class is "it randomly sends me to login". Make each redirect explain itself:

- No session → `/login?redirect=<fullPath>`; after login return to that path,
  but validate it first (must start with `/`) so the query value cannot become an
  open redirect.
- Authenticated but wrong role → a dedicated 403 page with an explanation.
  Never a silent redirect to the dashboard; silence is what the user reads as a bug.
- Token rejected/expired (API 401) → handle it in ONE place: a response
  interceptor on the HTTP client that calls a handler registered from the app
  entry point, clearing the session and going to `/login?expired=1` with an
  explicit "your session expired" notice.
- Do NOT clear the session on 401 from public/unauthenticated endpoints — filter
  by URL prefix, or users get logged out spuriously.
- Persist both token AND user object; recomputing identity from a token alone
  loses the role on refresh and produces the classic "worked, then redirected
  after reload" report.

## The sign-in handler must navigate — a guard cannot fix the screen you are on

Route guards run on navigation, so a successful login that only writes the session leaves the user
staring at the login form until they reload (the guard finally fires on the next navigation).
Symptom the user reports: "I logged in, the page still showed login, I refreshed and it was fine."

- After a successful sign-in, `router.replace()` to the validated `?redirect=` target or the
dashboard. Replace, not push, so the login screen stays out of the back stack.
- Add a belt-and-braces `watch` on the auth state in the app shell: if the session turns
authenticated while the current route is the login route, replace to the dashboard. That catches
sessions restored by a second tab, a cookie-based (Lambda) mode, or a provider callback that
bypasses the form.
- Lock it with a test on the submit path that asserts a route change — asserting only that the store
flipped to authenticated passes while the screen stays wrong.

## A fresh backend makes a panel look broken: list once, never probe

A panel that knows N documents must not issue N GETs at boot. Against an empty bucket/API every one
returns 404; the browser logs each failed request as an error even when the code handles "missing"
correctly, and the user reports "the console is full of 404s" as a bug.

- List the prefix once (`ListObjectsV2`, or one index endpoint), then read only the keys that exist
and mark the rest absent locally.
- Fall back to per-document reads only when the listing itself fails, so a narrowly scoped
`ListBucket` (prefix-conditional) cannot break the panel.
- Keep the decision in a pure function — `okumaPlani(existingKeys, prefix)` → `[{ad, varMi}]` — and
unit-test three cases: empty index (nothing fetched), partial index (exactly those fetched), listing
failed (all fetched).

## Copy panel state as data, never as a proxy

State read through a Pinia/Vue getter is a **reactive Proxy**, and `structuredClone` cannot clone a
Proxy — it throws `DataCloneError: #<Object> could not be cloned`. A save flow that snapshots the
store with `structuredClone` therefore shows "an unexpected error occurred" **after the write
already succeeded**: the throw comes from the watcher that re-seeds the form, not from the save.

- Deep-copy with a JSON round trip (`JSON.parse(JSON.stringify(v))`, guarded for
  `null`/`undefined`) or `toRaw` plus a manual deep unwrap — both are safe because the documents
  are JSON. Put it in one helper (`kopya()`), not inline at 16 call sites.
- Diagnose "error toast but the file/row exists" as this bug first: read the target back before
  suspecting credentials, CORS, or the write path.
- Lock it with a test: `expect(() => structuredClone(reactive({a:1}))).toThrow()` plus an assertion
  that the replacement clone is deep-independent (mutating the copy must not touch the store).

## Anything in `VITE_*` ships to the browser — it is not a secret store

Front-end build variables are inlined into the JS bundle, so a password, API key or token placed in
`VITE_…` is downloadable by anyone who can load the page — including a login-gated panel, because the
bundle is fetched before the user authenticates. Keep only non-secrets there: service URLs, pool ids,
client ids, bucket/prefix names.

- When the browser genuinely needs a write capability (e.g. publishing a "refresh" ping to a broker),
  do not paste a long-lived credential into the build. Options, in order: mint a **short-lived** token
  per session from the authenticated backend / Cognito identity, put a **thin proxy** in front of the
  write, or accept a deliberately scoped credential that can only write one topic and is rotated — and
  say which trade-off you took instead of leaving it implicit.
- A `wss://` endpoint and an ACL-limited account are not a substitute for keeping the secret off the
  client: the ACL limits blast radius, it does not make the credential private.

## Admin rights come from the identity provider, never from app data

- Create the role groups at provisioning time (ADMIN / EDITOR / USER) and enforce
  them at TWO layers: the gateway authorizer, and a group check inside the
  handler.
- Never derive admin from a heuristic (email prefix, first user, a self-serve
  profile field). Self-signup must always land in the lowest role.
- **Groups are written into the token at sign-in.** After granting a role the
  user must sign out and back in. This is the first thing to check when someone
  reports "I made myself admin but still get 403".
- Ship grant / verify / revoke commands in the setup doc, reading the pool id
  back from stack outputs instead of pasting it.
- Claim parsing: authorizers may deliver groups as an array OR as the literal
  string `"[ADMIN, EDITOR]"` — handle both. Match whole group names so
  `ADMINISTRATOR` never satisfies an `ADMIN` check.

## CORS posture for a SPA on a different origin than its API

Always-on invariants (implementation recipe: `references/cors-allowlist-implementation.md`):

- **Allowlist, not `*`.** With Bearer-token auth a wildcard is not by itself a
  credential leak, but it lets any origin read any endpoint that is mistakenly
  left unauthenticated, and it turns into a real hole the day auth moves to
  cookies. Treat it as a loose default to remove, not as a fire to fight.
- Never set `Access-Control-Allow-Credentials` on a token-based API.
- Emit `Vary: Origin` whenever you echo a specific origin.
- ONE source of truth for the list: the same list feeds the gateway's preflight
  configuration AND the handler's response headers (hand it to the function as an
  env var from IaC). Two lists drift.
- Keep the list in deploy configuration (an IaC context flag), not hardcoded, and
  document that adding a domain requires a redeploy.
- A request with no `Origin` header (curl, server-to-server, webhooks) needs no
  CORS header — do not invent one.
- When explaining this to a user, give the honest split: what is exploitable
  today vs. what becomes exploitable under a plausible next change.

## Verifying auth/CORS work (do not trust source reading)

- For each route class — anonymous, authenticated-wrong-role, authenticated-
  correct-role — assert the resolved navigation outcome. One case per class per
  protected route family is enough.
- For a reported "public page shows login" bug, the regression lock is a test that
  mounts the page as an anonymous user and asserts BOTH that the public content is
  present AND that the login form is absent.
- After IaC changes run `cdk synth` and inspect `cdk.out/*.template.json` for the
  real header values, method authorization types, and env vars. Source-level
  intent is not evidence.
- Exercise the built server artifact once with a synthetic event; a suite of unit
  tests can pass while the emitted/handler code is broken (see
  `ts-monorepo-build-gotchas` §9).

## Pitfalls

- When a reported symptom does not reproduce, SAY SO plainly and show what the
  code actually does, then lock the intended behavior with a test. Do not invent
  a root cause to satisfy the report; a fabricated diagnosis sends the user
  chasing the wrong thing.
- Do not create a `requiresAdmin` guard that redirects to the login page — a
  permission failure that looks like an authentication failure is the most
  expensive confusion in this whole area.
- Do not let a public route inherit a protected parent's meta by accident; check
  the resolved child meta when nesting public pages under a layout.
