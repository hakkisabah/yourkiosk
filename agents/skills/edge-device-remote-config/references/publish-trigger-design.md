# Publish trigger: settings, gates, tests

Use when a panel/back-office must make devices refresh *immediately* after a publish, in more than one
runtime, optionally switched off.

## Setting shape

```jsonc
{"trigger": {"enabled": true, "modes": ["native", "browser"]}}
```

- `modes` values are runtime identifiers the device compares against its own mode; compare
  case-insensitively and treat unknown values as "no match" rather than an error.
- Empty list is a valid state (= nobody triggers) and must be tested.

## Gate helper (single source of truth)

```python
def trigger_enabled(mode: str) -> bool:
    if not config.TRIGGER_ENABLED:
        return False
    return mode.lower() in {m.strip().lower() for m in config.TRIGGER_MODES}
```

Call it in **both** runtimes at the point where the trigger would be applied — not where the trigger
is fetched. Remote commands stay outside this gate.

## Emit side

- Emit after every successful write of a document that can change the screen.
- Emit best-effort: a trigger write failure must not roll back a valid save; log one line.
- Emit the scope the trigger supports (all devices / district / region) so one device class does not
  wake a whole fleet.

## Test matrix

| Case | Assertion |
|---|---|
| enabled + both modes | helper true for each runtime |
| disabled | helper false for every runtime |
| modes = ["native"] | native true, browser false |
| modes = [] | both false |
| browser gate closed | long-poll returns `changed: false` and returns after a heartbeat, not instantly |
| write of a display document | trigger document written, correct scope + timestamp |
| write of a non-display document | no trigger written |

## Remote data: the signature is local

When the device reads its data from a CDN, the long-poll signature (`mtime+size` of local files, or a
hash of them) does **not** change when the panel publishes — nothing local changed yet. The trigger
document has to land on disk first. If that download only happens in a background sync loop (typical
interval 20–60 s), the user's "immediate refresh" is really a 20–60 s delay and gets reported as
"publishing does nothing".

- Let the long-poll handler pull the trigger document itself while it waits: one tiny GET every
  `trigger.poll_ms` (default 2–5 s), only when the data source is remote and push is off. The wait
  then ends 1–3 s after the publish instead of at the next sync tick.
- Keep the same pull out of the loop when the data is local — the signature already changes on write.
- Persist the downloaded trigger next to the data so the restart path and the signature agree.
- Test: publish, then assert the wait returns `changed: true` within ~3 s with the background loop
  disabled entirely.

## Fleet scale: push instead of polling

Polling is billed per **request**, and a cycle usually costs more than one. Price both dimensions:

| Poll interval | Requests/month (600 devices, **1 request per cycle**) | Cost/month* |
|---|---|---|
| 3 s | 518 M | ≈ $596 |
| 20 s | 78 M | ≈ $89 |
| 60 s | 26 M | ≈ $30 |
| 5 min | 5 M | ≈ $6 |
| 30 min | 0.86 M | ≈ $1 |

\* CDN HTTPS requests plus origin GETs when the object is not cached (a `no-store` JSON file is not).
Multiply the request column by the number of documents a cycle reads: reading stamp + trigger +
command marker separately **triples** the bill (600 devices × 3 docs / 5 min ≈ 15.5 M ≈ $18).

### Collapse the cycle into one manifest

Publish a single small document from the same save hook that writes the content:

```jsonc
{"timestamp": "…", "stamp": "2026-10-24 09:11:58",
 "trigger": {"timestamp": "…", "ilceId": ""},
 "command": {"timestamp": "…", "id": "…"}}
```

- Device reads it once per cycle: stamp change → refresh data; trigger matches scope → forced refresh;
  command marker changed → fetch the (rare) command document.
- Keep the old three-document read as the fallback when the manifest 404s, so devices on the previous
  build and a fresh install both work during the transition.
- Measured effect at 600 devices: 3 docs / 5 min ≈ $18 → 1 doc / 30 min ≈ $1 (≈ 18× fewer requests).

### Adapt the interval to push health

| Push state | Interval | Why |
|---|---|---|
| connected | 1800 s | instant updates come from push; the poll is insurance |
| lost | 60 s, doubling to a 300 s ceiling | one lost broker must not bill the fleet at the fast rate forever |

Log the chosen interval and the reason once per change (`poll interval: 1800 s (push connected)`);
silent interval changes are indistinguishable from "polling stopped working".

Always price the chosen interval for the target fleet before shipping it; "instant" at 600 devices
by polling costs hundreds of dollars a month.

Push design that keeps the existing code path:

1. Device holds **one** long-lived MQTT connection (TLS) to a broker; subscribe to one topic.
2. On message, the subscriber **only writes the local trigger document** (timestamp + scope). A
   dedicated local watcher (≈2 s, `stat` only on the trigger files — no network) sees the write and
   drives the refresh in both runtimes; the poll interval stays as the slow fail-safe. Do **not** rely
   on "the signature machinery" alone: a native runtime evaluates that signature only on its poll
   timer, so once the interval is widened to 1800 s the push is dead for 1800 s and the user's only
   workaround is restarting the app. When both a manifest trigger and a local trigger are present,
   apply the one with the **newer** timestamp — the manifest is rewritten on every publish, so
   "remote first, local second" precedence means the push never wins.
3. While push is connected, skip the remote trigger poll entirely; keep the interval as the fail-safe
   for when the broker is unreachable or the MQTT library is absent (silently fall back, never block
   startup).
4. Publishing side: the panel's save hook publishes one small message (dynamic `import()` the MQTT
   client so the bundle stays lean; skip silently when unconfigured). Any publisher works — the
   message body only means "refresh".
5. Auth: username/password over TLS for a self-hosted broker (Mosquitto + websockets listener for the
   browser panel); X.509 `ca`/`cert`/`key` for AWS IoT Core, which does not accept bare
   username/password. Expose both as settings.

Cost at 600 devices: a managed broker ≈ $2/month (connection-minutes), a small VPS ≈ $5/month flat —
versus $596/month for 3 s polling. Latency ≈ 100 ms.

## Failure modes seen in practice

- Trigger written only by the one screen that has a manual button → every other publish looks broken.
- Switch implemented as "stop polling" → device never updates again; the fallback interval must stay.
- Long-poll disabled path returns immediately → percent CPU, one request per millisecond.
- Mode list compared against a different spelling than the launcher writes → silently never matches.
- **Interval widened for cost, trigger file written but never read** → push is dead for the whole
  interval; the broker log shows delivery, every test is green, and only a restart applies the change.
  The symptom ("it works after I restart") points at consumption, not at caching or freshness.
- **Fixed precedence between two trigger sources** (manifest before local file) → the always-present
  manifest shadows every push. Compare timestamps instead; keep the newer one.
- **Push flag treated as connection state** → when the broker is down the long-poll still believes
  push is coming and learns nothing. Track `attempted`/`connected` separately.
- **Watcher with an undefined path constant inside `except: pass`** → silent no-op indistinguishable
  from a working watcher. Compute the device directory explicitly and assert the refresh log line
  appears within seconds of a hand-written trigger file.
