---
name: edge-device-remote-config
description: "Use when devices pull config from a remote store."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [config, offline, caching, kiosk, fleet, s3, cdn, reliability]
    category: software-development
    related_skills: [browser-kiosk-display-mode, pyqt6-kiosk-hardening, aws-cli-provisioning]
---

# Remote config for devices that must survive the network

A fleet of kiosks/signage/edge boxes that fetch their own settings and content from a bucket or CDN.
The two failure modes are always the same: **a bad publish bricks a device** (no way back in) and
**"offline support" that only works while the process stays alive**.

## When to use

- Wiring a panel/back-office that publishes settings + content for remote devices.
- A user asks "when I publish, does the device pick it up?" or "does it still show data offline?".
- A device has two runtimes (native window vs embedded browser) and settings behave differently.
- Auditing an existing cache/offline claim before promising it to someone.

## 1. Split bootstrap from published config

The device needs a few keys to even reach the remote config. Keep them **local** and everything else
remote:

| Tier | Lives | Contains |
|---|---|---|
| Bootstrap | local file on the device | source mode, remote base URL, host allow-list, runtime/proxy paths, cache directory |
| Published | remote document | feature flags, layout, content windows, limits, schedules |

Merge order: **remote is the base, local overrides the bootstrap whitelist**. Never the reverse — if
local wins everywhere the panel is decorative, and if remote wins everywhere one mistyped publish
disconnects the fleet from the settings it needs to find the panel again.

- Express the whitelist as code (`LOCAL_PRIORITY = frozenset({"veri.kaynak", "veri.dosya_adresi",
  "ag.izinli_hostlar", ...})`), not as prose in a doc, and unit-test both directions: remote wins for
  ordinary keys, local wins for every whitelisted key.
- A failed fetch (offline, 403, truncated JSON) must log one warning and continue with local values.
  Config loading may never raise; a device with no settings does not boot.

## 2. One knob per intent, per runtime

If two runtimes read two different keys for "where does my data come from" (`source` for the native
app, `web_source` for the embedded browser), that duplication WILL be reported as a bug ("I set it to
https and nothing changed"):

- Put the runtime each key controls in its label and description, in the generated schema and in the
  docs — not in a comment nobody opens.
- Better: derive the second runtime's value from the first unless it must differ, and if it must,
  say why in the field description.
- When you find the second key is read but the first is silently ignored, that is a real defect:
  fix the reader, then write the test that proves the value takes effect (see §5).
- **A policy exception added for one runtime must exist in both.** Two runtimes that share a settings
  file but not a policy layer drift: an image/asset allow-list widened in the browser proxy but not in
  the native fetch path means the same content renders in one mode and is silently dropped in the
  other — and the drop is invisible because the consumer treats "asset rejected" as "skip this item".
  Put the exception in one shared helper (`image_settings_for(cfg, url)`) that both runtimes call, and
  add a parity test asserting the native and browser paths reach the same verdict for the same URL.

## 3. A URL parameter nobody passes is a silent fallback

Embedded-browser runtimes usually take their config through the launch URL (`?mode=remote&base=…`).
If the launcher writes the mode but not the base, the page falls back to its local default and the
feature looks broken while every log line says success.

- Build the launch URL in ONE function, add the base only when the mode is remote, and strip the
  trailing slash (pages typically join as `${base}/${file}`, so a trailing slash yields `//`).
- Test the URL builder directly: remote mode contains the encoded base and no trailing separator;
  remote mode with an empty base adds nothing; an unknown mode collapses to the local default.

## 4. Offline means cold start, not "while it is running"

A memory fallback makes an in-process network blip invisible and creates a false sense of safety.
The claim that matters is: **power-cycle the box with the cable unplugged and it still shows the last
content.** Audit that path explicitly:

- The cache is usually keyed by a freshness stamp (a `lastupdate` document). If the stamp is fetched
  from the network at boot, an offline boot has no stamp → the cache lookup is skipped → nothing is
  shown, even though the disk cache is full. **Persist the last known stamp and fall back to it when
  the network read fails.**
- Cache the heavy assets too (images), and expire them by last-shown date rather than by delete-time.
- **Revalidate assets, do not re-download them.** Any flag the app sets on "data changed" (a `stale`
  marker over every cached asset) turns the next render into a full re-download of every image, with
  the bytes already sitting on disk. Store the HTTP validators (`ETag`, `Last-Modified`) in the cache
  index and revalidate with `If-None-Match` / `If-Modified-Since`: a `304` has no body, so the disk
  copy is reused and only a genuinely changed asset is fetched. At fleet scale this is the difference
  between gigabytes per device per month and a few kilobytes — price it and say so. Recipe, index
  fields and tests: `references/offline-cache-audit.md` §5.
- Prove the disk is really the source: log one INFO line when an asset is served from disk (`asset
  served from disk (N bytes)`) and one when it is re-downloaded. An asset cache whose hits are only
  DEBUG-visible looks like "the cache is not used" and invites a rewrite of working code.
- A browser runtime fetching the CDN is a **cross-origin** request: it needs the bucket's CORS rules
  (anonymous `GET`/`HEAD` from any origin) or it fails with an opaque `Failed to fetch` that reads as
  "file missing". Add a second path that reads the same document through the local server that already
  caches it (same origin, no CORS), and fall back to it — the browser runtime then works even with the
  bucket policy not yet applied.
- With no cache at all (a box that has never been online) an empty screen is correct — say so instead
  of treating it as a bug.

Recipe and test matrix: `references/offline-cache-audit.md`.

## 5. Verification that actually proves it

- **Publish → device:** write the document to the store, then read it back through the same URL the
  device uses (CDN host, not the bucket API) and assert the exact bytes/JSON the panel wrote.
- **Remote wins / local wins:** unit-test the merge with a faked fetcher; one case per branch.
- **Offline:** monkeypatch the fetcher to raise, set the persisted stamp, and assert the cached bytes
  are returned. A second case with no stamp and no cache asserts `None` (empty screen, no crash).
- **Mode plumbing:** assert the URL builder and the reader agree on parameter names — a mismatch
  between launcher and page is invisible in unit tests that only exercise one side.
- Never claim "works offline" from reading the cache code; restart-path evidence is the only evidence.
- **Prove "no restart needed" with a stub origin and the real app, not by reading the poll code.**
  Serve the freshness stamp + content documents from a tiny stdlib HTTP server, point the app's base
  URL at it, and override the app's own config so the settings file cannot win. Register the stub
  host in the allow-list and its port in the allowed-port tuple, and widen the scheme check only
  inside the test process (production policy rejects plain `http`). Wait for the first stamp, then
  rewrite stamp **and** content while the app stays up, pump the event loop in a bounded loop, and
  assert the app's stamp moved — print the elapsed seconds as the evidence. Two traps: isolate the
  cache directory per test (a stale stamp left by the real device is picked up at boot and the test
  passes or fails for the wrong reason), and use the real identity/document shapes or the app renders
  "identity not found" and never loads — which surfaces as an empty stamp, not as an identity error.
- **A fix must not regress a path that already worked.** Everything here is cross-cutting (publish →
  stamp → trigger → cache → both runtimes), so after changing one link re-run *all* suites and the
  real publish path, and report which paths you re-verified. One extra test run is far cheaper than a
  regression: "you fixed X and broke Y again" is the fastest way to lose trust in the whole change.
- **"Only works after a restart" is the signature of an unconsumed trigger, not a cache bug.** Measure
  the notification path (write the trigger, watch the clock) before touching cache or freshness code —
  a restart rebuilds the state, so it cures consumption and invalidation failures alike and tells you
  nothing about which one you have.
- **A red gate is not yet a red product.** Verify the gate's own invocation (correct `cwd`, clean tree,
  branch not behind) before editing code in response to it — a runner started from the wrong directory
  reports a collection error that looks identical to a hundred failing tests.
- **Prove the bytes you shipped are the bytes being run.** A fix that is committed but never rebuilt,
or built into a directory the runtime does not read, shows the user the old symptom forever while every
  test passes. Stamp the build output with the commit and build time, print that stamp in the device's
  diagnostics, and have the deploy fetch the live artifact and assert a real value from it (not just a
  changed hash). Checklist and the live-artifact probe: `references/runtime-parity-and-deploy-verification.md`.

## 5.1 The panel's write prefix and the device's read base are ONE namespace

A panel that writes `<bucket>/<prefix>/settings.json` while devices read `<cdn>/settings.json` looks
completely healthy from both sides: saves succeed, publishes succeed, and the device never changes.
The same mismatch hides behind an anonymous 403 — a prefix that the bucket policy does not expose for
public read is a prefix devices cannot read at all, so someone "fixes" the missing files by writing
them at the bucket root while the panel keeps using the prefix.

- Keep the prefix in **one** place and validate it in preflight: derive the device URL from the same
  value (`base = cdn + prefix`) and print both the write key and the exact GET a device will perform.
- A panel that 404s on a document it just saved (visible as console errors on its own prefix) is not
  a panel bug — it is evidence the two namespaces differ. Read the request path before debugging auth.
- Resolve deliberately, never by accident: either empty the prefix so panel and device share the root,
  or expose the prefix through the CDN (behaviour + OAC/public read) and point the device base at it.
  Tightening the panel's IAM role to a prefix without opening that prefix for reads leaves the fleet
  unable to see anything the panel writes.
- **Read the origin config before adding a prefix anywhere.** A distribution origin may already carry
  an `OriginPath` (`/kiosk`), in which case the root URL *already* serves that folder: the write
  namespace and the read namespace are aligned and the apparent bug is elsewhere. Appending the same
  prefix to the device base then requests `<prefix>/<prefix>/…` and returns 403 — which reads as
  "permission missing" and sends you editing bucket policies that were already correct. Confirm with
  `aws cloudfront get-distribution-config --id <id> --query "DistributionConfig.Origins.Items[].{Domain:DomainName,OriginPath:OriginPath,OAC:OriginAccessControlId}"`
  and by fetching the root document, before proposing any prefix change.
- Assert it end to end: write through the panel's code path, then `GET` the device URL and compare
  bytes. A unit-tested write path and a unit-tested read path that never meet are still a broken pipe.

## 5.2 Every content write must bump the freshness stamp

A polling device compares the stamp (`lastupdate` or equivalent) and, when it has not moved, serves the
cached body **without a network read**. A publisher that writes the content document and a trigger but
leaves the stamp alone therefore looks successful in the panel and is invisible on every device whose
push did not arrive: the push path bypasses the cache, the poll path does not. This is the single most
common shape of "I saved it and the screen did not change" — and it survives every test that only
asserts the write succeeded.

- Put the stamp bump **inside the same save function as the content write**, for every document the
device consumes (settings, scope, template, content). Not behind a separate "publish" action the user
can forget; a manual notify button is not a substitute.
- Order it content → stamp → trigger → push, all best-effort after the content is live: if the stamp
  write fails, log and still emit the trigger, but never fail a save whose bytes already landed.
- Exempt the documents the device never reads (machine identity, panel-only files) so they do not
  cause fleet-wide refreshes.
- Regression-test at the store level by recording every write call: `save('content', …)` must produce
  content + stamp + trigger; a non-consumed document must produce only itself. Assert on the recorded
  write list, not on the returned boolean.
- When a user reports "saved, nothing changed", check this before anything else: fetch the stamp
  through the device URL, save once, fetch again, and see whether the value moved at all.

## 5.3 Segment content per device — optional scope fields, filtered before download

A fleet usually needs some content for everyone and some for one district, region or single screen
(`ilceId` / `bolgeId` / `cihazId` on each item). Three rules make this safe and cheap:

- **Scope fields are OPTIONAL and empty means "everyone".** Adding them must not change the behaviour
  of existing documents; alias the spellings the data might use (`ilce_id`, `ilce`, `clientID`) and
  treat unknown/blank as no constraint. Multiple fields = AND.
- **Filter in the pool builder, not at render time.** A non-matching item must never enter the device's
  working set: not downloaded, not cached, not counted in "N items". Filtering at render leaves the
  fetch (and the CDN bill) untouched.
- **Fail closed when the device does not know its own scope.** If the identity/location document could
  not be read, a targeted item must be hidden, not shown: printing another region's campaign is worse
  than printing nothing. The untargeted items still render, so the screen is not blank.

Keep one implementation per runtime and test both against the same table; contract and test matrix:
`references/content-targeting.md`.

## 5.4 The panel editor: an unsaved draft must survive, and a no-op save must not write

"I edited the record, pressed save, and the device still shows the old value" has two causes on the
panel side, both silent. Kill them separately.

- **Do not let a derived-annotation helper mutate the store's data.** A helper that walks records and
  fills in missing ids (`record.districtId ??= key`) mutates the objects the store holds; the store's
  deep watcher fires, the view re-clones its draft from the store, and everything typed between those
  two moments is gone — the save then writes the OLD body and reports success. Return copies from
  annotations/pure projections, and add a test that the input document is byte-identical
  (`JSON.stringify`) after the helper runs, plus one asserting a record that already carries the id is
  returned by reference (no accidental copy churn).
- **Guard the store→draft watcher on dirtiness.** If the draft differs from the source, do not
  overwrite it: keep the user's edits and say so ("updated elsewhere, unsaved changes kept").
- **Refuse the no-op save with a message.** Saving when the draft equals the source must not issue a
  PUT; a success toast on an unchanged body is exactly what makes a broken edit look applied. Put the
  decision in a pure function (`{ write, message }`) so it is unit-testable.
- **Read the document back after writing and compare it to the payload.** A wrong key, a different
  prefix or an ETag mismatch is otherwise invisible; equality on the round trip is the only evidence
  that the bytes the panel believes it wrote are the bytes stored.
- **A shared document registry is also the panel's state schema.** Enumerating
  `Object.entries(REGISTRY)` and then doing `this[key].field = …` throws
  `Cannot set properties of undefined` on page load the moment a document is added to the registry
  without a matching state entry. Add the state entry, exclude write-only documents (a manifest the
  device consumes but the panel never reads) from the read plan, and assert `registry keys ⊆ state
  keys` plus "write-only documents are never read" in a regression test.

## 6. Panel side: mode-dependent fields must be visible

Schema-driven admin forms hide keys flagged "advanced" by default. Any field that a **mode selection
requires** (the URL that `source=https` needs, the allow-list host, the proxy path) must live in the
basic tier with a description that states the dependency ("required when source = https, end with /").
A generator that classifies keys by naming heuristics (`key.split('_')[-1] in {...}`) mislabels these;
keep an explicit visible-list and assert in a test that the required keys are not flagged advanced.

Adding one key touches every artifact generated from the settings registry: the panel's schema JSON,
the layout/metrics constants, sample documents. Regenerate them in the same change and re-run the
"artifact is current" tests — a stale artifact keeps showing the old field list in the panel (and
fails with a hash mismatch that looks unrelated to your edit) while the device already accepts the new
key. The same applies to a key you *hide* or re-tier: the panel keeps the previous visibility until
the artifact is rebuilt and redeployed.

## 7. Publish triggers: one master switch + one mode list

"When I publish, the device should refresh immediately" is a separate feature from the periodic poll.
Build it as two settings, not one:

| Key | Type | Meaning |
|---|---|---|
| `trigger.enabled` | bool | publish wakes the device immediately (off = normal interval only) |
| `trigger.modes` | list | which runtimes obey it (`native`, `browser`); empty list = none |

Rules that keep it from becoming a support ticket:

- **Every display-affecting document emits the trigger**, not only the one screen that happens to have
  a manual "notify" button. Keep the list in code (`TRIGGER_FILES = [...]`) next to the writers, and
  emit after a successful write, best-effort (a failed trigger must not fail the save).
- **Disabled must not mean frozen.** The device falls back to its normal refresh interval; remote
  commands (restart/refresh) stay independent of this switch — they have their own auth chain.
- Gate at the *consumer*: one helper `trigger_enabled(mode)` used by both runtimes, so a mode list of
  `["native"]` cannot be honoured by one runtime and ignored by the other.
- **Never let the disabled path hot-loop.** A browser long-poll endpoint that returns
  `changed: false` instantly will be re-requested in a tight loop; sleep roughly a heartbeat
  (1–10 s, clamped) before answering.
- Document the latency honestly: native runtimes re-read settings at start, so a *settings* publish
  lands on the next restart while a *content* publish lands within one poll.
- **With remote data the long-poll signature is computed from LOCAL files.** The trigger only changes
  that signature after it has been downloaded, so "instant" is really the background sync interval
  (tens of seconds) unless the long-poll handler pulls the small trigger document itself while it
  waits. Pull on a `trigger.poll_ms` cadence and only when the data source is remote — a local-file
  device already sees the change in its signature. Default that cadence to **tens of seconds**; a few
  seconds is a single-device convenience, and at fleet scale it is the whole bill (600 devices × 3 s
  ≈ 518 M requests/month). Decide the default by fleet size, not by the demo.
- **Do not reuse the asset downloader's content-type allow-list for control documents.** A fetch
  helper written for images usually whitelists `image/*` and rejects everything else — so a JSON
  trigger/command document fails with `content type not accepted: application/json` and the push path
  is dead while polling keeps working (native runtime only, which makes it look like a runtime bug).
  Validate content type **per document kind**: images by type + magic bytes, control documents by
  `json`/`text`/`octet` and then by parsing. Treat 403/404 on an optional document as "absent" at
  DEBUG level — warning every poll cycle trains everyone to ignore the log that would have shown the
  real failure.
- **Redact credentials when logging applied settings.** A settings loader that logs
  `key=value` for every applied key writes passwords, tokens and private-key paths into the journal in
  plaintext; the same lines end up in bug reports. Mask any key whose name contains
  `password|secret|token|key` and log `***` — keep the length and presence, not the value.
- **A device running on LOCAL data never fetches the published document at all**, so every setting
  that mode needs (push credentials above all) has to exist in its own local settings file. Ship a
  one-command writer (`settings_push.py --broker … --user … --test`) that merges into
  the local file, keeps the other keys intact, writes it 0600 and **verifies the real connection**;
  do not hand the user a JSON snippet to paste. When that writer touches the allow-list, **union with
  the code defaults — never replace the list**: the local file overrides the defaults wholesale, so a
  writer that stores only the newly-derived host silently revokes every host the app shipped with and
  breaks unrelated features (content images, update checks) days later. Read the defaults from config
  and append, then print the resulting list. And make the device's diagnostics flag perform the
  connection attempt rather than reporting "not tried" — the latter reads as a failure and sends
  everyone chasing the broker.
- **The same writer must also switch the data source and register its host, atomically.** Setting
  `source=https` + `base=<cdn>` without touching `host_allowlist`/`allowed_ports` makes every fetch
  fail with `host not in allow-list`; the identity document then cannot be read, the client id comes
  back empty, the layout cannot match a record and the screen renders **blank with a green "data
  complete" report**. Derive the hostname from the base URL, append it to the allow-list, add `443`
  to the ports, and prove the result with a real `GET <base>/<freshness-stamp>.json` — not by printing
  the config back. Diagnose that blank screen bottom-up: allow-list rejection → missing identity →
  0 records.
- **Never take a credential as a bare CLI argument in a user-facing tool**: `--password '…'` lands in
  shell history, `ps` output and the transcript. Offer `--password-stdin`/`--password-file` (0600) and
  a hidden `getpass` prompt as the default path, keeping the plain flag only as a documented last
  resort. The same rule applies to the panel side, where build-time env (`VITE_*`, `NEXT_PUBLIC_*`) is
  **inlined into the published JS bundle**: a browser-visible secret is not a secret, so scope that
  account to publish-only, document the exposure, and plan rotation or a server-side bridge
  (a device certificate removes the password entirely).
- **Price the data plane before recommending a new AWS primitive — with a per-device $/month table
  at three fleet sizes.** "Serverless scales to zero" is worthless for a fleet that polls every
  30–120 s: the environment never goes idle, and its memory is billed for its whole lifetime. The
  request-rate free tier also hides the crossover, so a list-price comparison misleads at small
  fleets. Model, quote assumptions, and keep the current plane unless the saving is real at today's
  size: `references/data-plane-cost-model.md`.
- **Polling cost grows linearly with the fleet; push does not.** Per-device polling is fine for tens
  of devices and wrong for hundreds: price it (devices × interval × 30 days × request rate) before
  promising "instant". At fleet scale add a push path whose subscriber does nothing but write the
  local trigger document, and stop remote polling while push is connected, keeping the interval as
  the fail-safe when the broker is down.
- **Widening the interval for cost silently kills push unless something CONSUMES the trigger file.**
  The subscriber only writes it; the reader is a timer that fires on the poll interval. Set that
  interval to tens of minutes and push is dead for exactly that long — every test passes, the broker
  log shows delivery, and the user's only workaround is restarting the app. Give the local trigger its
  own watcher with its own cadence (≈2 s) that does nothing but `stat` the trigger files (mtime +
  size): no network, so it costs the fleet nothing and can stay fast forever, while the poll timer
  remains the slow path. Prove it by measurement, not by reading code — start the app, write the
  trigger file by hand, and assert the refresh log line appears within a couple of seconds. A watcher
  whose base-path constant is undefined and whose body is wrapped in `except: pass` is a silent no-op
  that looks exactly like a working one.
- **"Enabled" is not "connected".** A push flag read from settings only says the feature is switched
  on; if the broker connection dropped, no message arrives and a long-poll that trusts the flag learns
  nothing, so the change waits for the (now very long) poll. Track connection state as a tri-state
  (`attempted`, `connected`) and treat `attempted && !connected` as "push unavailable, pull remotely";
  treat never-attempted as "trust push" so startup does not pay for a redundant request.
- **One manifest per cycle, not one request per fact.** A cycle that reads the stamp, the trigger and
  the command marker separately is three requests per device per cycle, and requests — not bytes — are
  the bill once caching is right. Have the save hook publish a single small manifest
  (`{timestamp, stamp, trigger, command_marker}`), read it in one GET, and keep the multi-document
  read as the fallback when the manifest is absent (older installs). Measured at 600 devices: three
  documents every 5 min ≈ 15.5 M requests/month ≈ $18, one manifest every 30 min ≈ 0.86 M ≈ $1.
- **A manifest fast path must still read the LOCAL trigger the push writes.** The push subscriber's
  only job is to write the trigger document on the device; a reader that switches to the manifest and
  stops consulting that local file drops every push notification — instant updates die while polling
  keeps working, so it looks like "push worked yesterday". **Merge by recency, never by fixed
  priority:** the manifest is rewritten on every publish, so it is always present, and a "manifest
  first, local file second" rule means the push trigger can never win — the device refreshes on the
  next poll and the user reports "it only applies if I restart the app". Take both candidate triggers
  and keep the one with the later timestamp (ISO-8601 UTC stamps compare lexicographically as
  strings); none when neither exists. Make that merge a pure function with four cases (remote newer /
  local newer / only one / neither) plus one where the local read raises, because a device whose
  local trigger is a corrupt file must still refresh on the stamp.
- **Never let the manifest be the only source of the stamp.** The publisher can fail to write it
  (permissions, a partial save, an older panel build) and the fleet then sits on stale content with a
  green diagnostic. Read the authoritative stamp document itself every Nth cycle (≈10 turns is
  enough) and prefer it when the two disagree; log the disagreement at DEBUG, not as an error.
- **Adapt the interval to push health, and back off — do not sit at the fast interval.** While push is
  connected the poll is pure insurance: widen it to tens of minutes. When push drops, start short
  (≈60 s) and double up to a ceiling (≈5 min) instead of hammering 60 s forever: a fleet whose broker
  is down for a day at a fixed 60 s pays multiples of the monthly bill for zero benefit. Log the
  chosen interval and the reason (`push connected` / `push lost, backoff N`) once per change.
- **The health signal must come from the client library's own accessor, and its failure branch must not look like a state.** A cached `connected` flag in a dict the callbacks update goes stale across short drops; ask the client each time you decide (`client.is_connected()`). Worse: a helper shaped `try: connected = status() except Exception: connected = False` converts **every** error inside `status()` — including a `NameError` from a missing import — into "push is down", so the fast interval runs forever while the log printed "connected" two lines earlier. Take the fallback, log the exception once at WARNING, and unit-test that the status symbol actually resolves (the module attribute exists), not only that the interval arithmetic is right.
- **Resolve the effective interval at startup, not from the persisted settings key.** The timer is created with whatever the settings document holds — usually a deliberately slow value (tens of minutes). If the health-aware interval is only applied at the *end* of the first cycle, that first cycle is tens of minutes away and the device looks frozen immediately after boot, exactly when the user is watching it. Call the interval setter once while wiring the timers.
- **One INFO heartbeat line per cycle, showing both sides of the comparison:** `cycle #7 · remote=<stamp> · device=<stamp> · push=connected`. Without it, "it does not update" has no evidence and every investigation restarts at the network. The line also proves the cycle is still running — shield the cycle body so an exception in one link (command marker, trigger read) cannot skip the freshness comparison, and log that traceback instead of letting the tick die quietly.
- Self-hosted broker hardening, and prove it with negative tests: TLS-only listener, `allow_anonymous
  false`, devices **read-only** on the topic / panel **write-only**, ~1 KB message size limit, no
  persistence, cert renewal deploy hook; anonymous connect and device publish must both be DENIED and
  the plain-text port must be closed. Assert the denial with a **subscriber** (message must not
  arrive), never with the publisher's exit code — MQTT 3.1.1 drops a denied publish silently and
  still exits `0`, which reads as "no ACL" when the ACL is fine.

Setting shape, gate helper, emit side, the remote-mode pull and the fleet-cost/push design:
`references/publish-trigger-design.md`. Choosing the *serving* plane (static object on a CDN vs a
per-request compute endpoint such as Lambda Web Functions) is a separate decision with its own
pricing traps — free tier, memory billed for the environment's whole lifetime, lost edge cache:
`references/data-plane-cost-model.md`.

Standing up the broker itself — host choice and CGNAT check, per-listener auth, the two opposite
ACL accounts, Let's Encrypt with a renewal hook, the port-both-layers rule, the installer shape, the
startup traps (dropped-in `log_dest` collision, auth-directory ownership, password-file owner,
credentials file written too late), the negative verification set, the `paho` 2.x client traps and the
three-signal triage for "I published and nothing happened", and the four-link live-check script you
hand the user instead of interpreting signals over chat: `references/push-broker-mqtt.md`.

## 8. CDN: one distribution per content class

Serving an SPA and device data from one distribution breaks the data path: the SPA needs
`403/404 → /index.html` (status 200), so a **missing data file comes back as 200 + HTML** and the
device parses HTML as JSON. Custom error responses are distribution-wide, not per-behaviour.

- Give data its own distribution (origin path `/data`, no custom error responses, cache disabled or
  short TTL, `no-store` on JSON) and keep the SPA fallback on the panel distribution.
- Assert it with a negative test: a non-existent data object must return 403/404, never 200.
- Keep writes authenticated (identity pool / signed requests) even when reads are public via the CDN;
  allow reads with a bucket policy scoped to `service=cloudfront` + `AWS:SourceArn` of that one
  distribution.

## Pitfalls

- A remote-data switch that does not update the host allow-list blanks the device and still reports
  "data complete": the failure is a rejected fetch, not missing content. Provision host + port with
  the data-source switch and verify with a real HTTP GET.
- A diagnostic that reports a connection as "not tried" is indistinguishable from a failure to the
  person reading it — make the diagnostic perform the attempt.
- Publishing a whitelisted key from the panel and expecting it to take effect: it will not, by design.
  Put that sentence in the panel next to the field.
- Settings are read at process start in native runtimes: a publish lands on the **next restart**.
  State the latency, or add a reload-on-trigger path — do not let the user discover it.
- Two cache layers (memory + disk) with different keys look like "the cache is broken" when only one
  is consulted on the failure path; keep the lookup order in one function.
- **Widening a shared function's signature breaks call sites that splat a tuple.** `f(items, *self._scope())`
  binds the first tuple element to whatever positional parameter comes next — often the clock/`now` —
  and if the consumer wraps each item in `except TypeError`, every item is skipped with a plausible
  data-shaped warning ("timestamp/timezone mismatch") and nothing crashes. Pass new optional filters
  by keyword at every call site, and validate the call once before the loop so a signature error can
  never be mistaken for bad data.
