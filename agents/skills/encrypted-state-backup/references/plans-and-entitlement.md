# Plans, devices and a signed entitlement

Depth for the section of the same name in SKILL.md. Everything here is a shape
that survived a real gate, not a sketch.

## One dict, one table, one gate

```python
PLAN_LIMITS_COLUMNS = ("plan", "$/month", "rows", "snapshots", "bytes", "devices", "retention")

PLANS = {
    "local":       Plan(price=0.0, max_rows=0,        max_objects=0,     max_bytes=0,      max_devices=0),
    "backup":      Plan(price=1.0, max_rows=5_000,    max_objects=20,    max_bytes=16<<20, max_devices=3, retention_days=30),
    "backup_plus": Plan(price=3.0, max_rows=50_000,   max_objects=100,   max_bytes=160<<20,max_devices=10,retention_days=90),
    "owner":       Plan(price=0.0, max_rows=1_000_000,max_objects=10_000,max_bytes=8<<30,  max_devices=100),
}
```

`local` is not a hidden tier: it grants zero server allowance and nothing in the
engine reads it. The gate asserts that (grep the engine modules for an import of
the billing module and fail on a hit) so the free build cannot start depending on
a plan.

The gate parses the markdown table in the docs and rebuilds the expected row from
the dict, formatting both sides identically — `f"{price:g}"`, `f"{rows:,}"`,
`f"{bytes >> 20:,} MiB"`, `"never"` for a zero retention. Compare the whole cell
list; a partial compare passes a row where only the price changed.

```python
def parse_doc_table(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) != len(PLAN_LIMITS_COLUMNS) or cells[0] in ("plan", "---") or cells[0].startswith("-"):
            continue
        rows[cells[0]] = cells
    return rows
```

Then, in the same script, prove enforcement over real HTTP: start the store on
loopback, post an unsigned claim (expect 401), post a signed one (expect
`applied: true`), read `/v1/usage` back and compare its applied limits to the
table, post the same claim again (expect `applied: false`), and post a stale one
(expect 401). A table that matches the code but is never exercised by a request is
still a claim.

## The claim and its verification order

```
POST /v1/admin/entitlement
X-Trick-Signature: sha256=<hmac_sha256(secret, raw_body)>

{"account": "owner", "plan": "backup_plus", "event_id": "evt_1234", "ts": 1770000000}
```

Order matters and is the whole security content of the route:

1. read the body with a hard size cap (1..16 KiB) before anything else;
2. verify the HMAC over the **raw bytes**, `hmac.compare_digest`, and refuse
   before `json.loads` runs — a signature checked after parsing is theatre;
3. refuse when `ts` is outside a 300 s window (stops replay of an old
   cancellation);
4. refuse an unknown `plan` string before touching the store;
5. `event_id` seen already → 200 with `applied: false`, no write;
6. account must exit → else 404, never created;
7. apply, then record the event id, in that order: a crash between them re-applies
   (harmless), the reverse loses the change.

No secret configured → 401 on every attempt. That default is the feature.

The ledger is a small JSON map `{event_id: ts}` written with the same tmp +
`chmod 600` + `os.replace` pattern as everything else; a corrupt file is an error,
not an empty ledger (an empty ledger silently re-applies every old webhook).

## Applying a plan

The single write that both the CLI and the webhook go through:

```
load accounts.json  ->  replace that one account's five limit fields + plan name
                    ->  keep its token digests untouched
                    ->  write the file atomically  ->  swap the in-memory map
```

Swap memory **after** the file is on disk. A process that crashes between the two
serves limits that exist nowhere. Keep device digests across an upgrade and a
downgrade: changing plan must not log a device out, and a downgrade must lower the
ceiling immediately rather than at the next restart.

## Device minting

```
count existing digests -> refuse at max_devices (name the limit in the message)
-> new 32-byte urlsafe token -> store only its SHA-256 -> print once
```

Test three things: the minted token authenticates over real HTTP, the first token
still works, and a random token gets 401. Also assert the plaintext token does not
appear anywhere in `accounts.json`.

## CLI surface to keep

```sh
pkg vault plans
pkg vault plan  --root <store> --account owner            # read current
pkg vault plan  --root <store> --account owner --set backup
pkg vault device --root <store> --account owner
```

- `plans` needs no store at all.
- `plan`/`device` print JSON so a script can read the applied limits back.
- Unknown account → exit 1 with `no such account`, never a created one.
- The parser must accept all five actions in one `choices=` tuple, or the docs
  gate (which compares documented subcommands to the parser) passes a command that
  does not exist.

## What to say about resale

Two columns, and do not blur them:

| half | automatable? | who owns it |
|---|---|---|
| instance create / destroy / ports | yes, scripted, dry-print by default | you |
| plan → limits when someone pays | yes, signed webhook | you |
| the customer's invoice and tax | no (no cloud metering API) | the payment provider |
| the price-to-plan mapping | no | this table |

State plainly that a full end-to-end resale automation does not exist on the cloud
side, and that the missing piece is an invoice, not a store.
