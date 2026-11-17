# Remote store — endpoints, layout, deployment, cost

Depth for the second half of a backup feature: the server that holds ciphertext
and the client that refuses to trust it wrongly. Everything here is a shape that
was run; adapt names, keep the order.

## Surface

Four routes and nothing else. Anything richer is a second product.

| method | path | returns |
|---|---|---|
| GET | `/v1/ping` | liveness, **unauthenticated** (a health check that needs a token cannot be used by a proxy) |
| GET | `/v1/usage` | `{account, objects, bytes, declared_rows, max_bytes, max_objects, max_rows, rows_unit}` |
| GET | `/v1/objects` | listing, newest first: `{sha256, bytes, rows, created_at, stored_at}` |
| GET | `/v1/objects/<sha>` | raw octet-stream; hash re-verified before it is sent |
| PUT | `/v1/objects/<sha>` | body = ciphertext, `X-…-Rows` / `X-…-Created` headers for display |
| DELETE | `/v1/objects/<sha>` | frees quota |

Status mapping: quota → 507, bad input → 400, wrong token → 401, unknown digest
→ 404, internal → 500. The client turns any 4xx/5xx into one sentence carrying
the server's `message`, so the user reads *why*, not a code.

Bodies up to 8 MB, refused on `Content-Length` before reading. A refusal must
drain the announced body (bounded, e.g. 2 MB) so the client receives the 413
rather than a reset it cannot interpret.

## On-disk layout

```
<root>/accounts.json          mode 0600, {"accounts":[{name, token_sha256, max_bytes, max_objects, max_rows}]}
<root>/objects/<account>/index.json
<root>/objects/<account>/<sha256>.trk
```

- Never store the token; store `sha256(token)`. Compare against every account with
  `hmac.compare_digest` so a wrong token reveals nothing by timing.
- `account` is sanitised to `[A-Za-z0-9._-]` and the directory is resolved through
  that sanitised name — an account name is data, not a path.
- Client-declared row counts live in the index for display only (see `rows_unit`).

## Client refuses, in this order

1. scheme not `https` → refuse (`--allow-plaintext` only for loopback tests);
2. no host → refuse; token shorter than 32 chars → refuse;
3. fingerprint given but not 64 hex → refuse;
4. on connect: peer DER absent → refuse; `sha256(DER) != pinned` →
   `certificate fingerprint mismatch: expected X, got Y; a store that cannot prove
   who it is is not a backup target`. Pinning means
   `check_hostname=False`, `verify_mode=CERT_NONE` **and** the manual digest check —
   disabling verification without the digest compare is not pinning, it is trusting
   everything;
5. body not starting with the archive magic → refuse *before* sending
   (`this is not a Trick archive; export one with …`), so a zip never reaches the
   store;
6. after PUT: re-download and compare bytes, then `verified: true`. Differing
   length → `the store returned N bytes that differ from the M uploaded`.

## Server refusals

| situation | answer |
|---|---|
| wildcard host, no `--expose-public` | refuse at construction, name the flag |
| wildcard host, no TLS | refuse: `a wildcard bind requires TLS` |
| no TLS, not `--allow-plaintext` | refuse: `the store only speaks TLS` |
| `--allow-plaintext` off loopback | refuse |
| key file group/world readable | refuse with `chmod 600` and the octal mode |
| `Content-Length` absent/0/oversize | 400 / 400 / 413 |
| digest mismatch | 400 `hash mismatch: the body hashes to X, not Y` |
| over quota | 507 with `used + incoming exceeds max` |

## Deployment script (Linux, systemd)

One script, run as root, that prints the two things the client needs:

1. system user with `nologin`, venv in `/opt/<app>`, store root `/var/lib/<app>`
   at 0700, config in `/etc/<app>`;
2. `vault init` once → token printed **once**, its JSON written to a 0600 file;
3. self-signed EC P-256 certificate, 3650 days, key 0600 — a CA is unnecessary
   because the client pins a hash;
4. hardened unit: `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp`,
   `NoNewPrivileges`, `CapabilityBoundingSet=`, `ReadWritePaths=<store>`,
   `MemoryMax` well under the instance size (a guard, not a budget), and
   `--expose-public` in `ExecStart` because the deployment does need the wildcard;
5. `ufw allow <port>/tcp` only if ufw is already active — do not enable a firewall
   the user did not ask for;
6. `systemctl enable`, **never** `start`; print `journalctl -u …` and the exact
   client commands with the fingerprint substituted.

**Test the generated `ExecStart` against the CLI's own parser.** The one time this
was skipped the unit asked for a wildcard bind the CLI refuses, and the first start
would have failed.

## Timer (systemd --user)

```
Service: Type=oneshot, EnvironmentFile=%h/.config/<app>/backup.env,
         ExecStart=<venv>/python -m <app> backup run
Timer:   OnCalendar=*-*-* 03:30:00, Persistent=true, RandomizedDelaySec=600
```

- the env file is created 0600, with `PASSPHRASE=` empty;
- the installer greps for `^PASSPHRASE=.\+` and, when empty, prints the one-liner
  to fill it and exits **0 with nothing enabled** — deliberate: a timer that fires
  with no passphrase fails every night and still looks scheduled;
- `--start` enables the timer, then `systemctl --user start --wait <service>` so a
  broken setup fails immediately;
- `backup run` itself: refuse unless the passphrase is in the environment with a
  message saying a timer has no terminal and argv is leaked by `ps`.

Flow-test the installer with a fake `systemctl` on `PATH` that appends to a log:
assert `daemon-reload` happens always, `enable` only after the passphrase exists,
and `start --wait` only with `--start`.

## Cost table template

Rows, and an honest column for each:

| line | value | measured / derived |
|---|---|---|
| one archive | bytes, rows | **measured** on the real state |
| store RSS | ~30 MB | derived (one process, no index, no model) |
| requests per backup | 4 (ping, put, read-back, usage) | derived from the client |
| per-account quota | 64 MB / 200 objects | code default |
| users that fit | quota × users vs disk; daily bytes vs transfer | arithmetic |
| cost per user | monthly price / users | arithmetic |

Quote the cheapest instance's real limits (e.g. 1 vCPU, 512 MB, 20 GB, 1 TB) and
show the two bindings separately: **disk** (`users × quota`) and **transfer**
(`users × daily bytes × 30`). Whichever binds first is the answer; say which.

Resale automation, if asked: instance creation/teardown is an API call, but a
cloud provider generally has no customer-billing/metering API, so invoicing and the
quota ledger stay yours (your own payment provider + your own counter). Say that
plainly instead of implying end-to-end automation exists.

## If the question becomes "no server at all"

Keep the store's shape and move each duty to a managed service: API Gateway (or a
function URL) for TLS and routing, a function for token check + quota + presigned
PUT, the bucket for blobs, a key/value table for accounts and the replayed-event
ledger, a scheduler for retention. Entitlement does not change — HMAC over the raw
body, constant-time compare, timestamp window, `attribute_not_exists(event_id)`
on the ledger instead of a file, unknown account still `404`.

- **The quota check races the upload unless the write is authorised first.**
  Function checks quota → returns a presigned PUT with `content-length-range` →
  client writes straight to the bucket → counter incremented on completion. Without
  the range constraint the client can store more than it declared.
- **Price the request count before believing the saving.** 100 users on the $1
  plan: bucket ~$0.09, PUT ~$0.03, function and API fractions of a cent, so well
  under a dollar. The same 100 users on a 15-minute sync spend ~288k PUT/month and
the request line alone outgrows the whole saving — daily is the design point, and
shortening the timer is a cost decision, not a preference.
- **Break-even with a rented box is storage-driven, in the low thousands of
  users.** Below it the managed stack is ~40x cheaper; above it the bucket bill is
  what grows while the box's rent stays flat. Quote the crossing point, not a
  verdict.
- **Do not add WAF or API-key usage plans for rate limiting at this size.** Their
flat monthly fees are larger than the entire bill; a per-account token bucket in
  the function (counter in the same table) is the proportionate answer.

## Rotation

- token: new root (or remove the account), `vault init`, rewrite the client's 0600
  token file;
- certificate: regenerate, restart, update `--fingerprint` on the client. The old
  fingerprint stops working immediately, which is the point of pinning;
- passphrase: no rotation path — a new passphrase means a new archive, and the old
  one still opens with the old passphrase. Say so.
