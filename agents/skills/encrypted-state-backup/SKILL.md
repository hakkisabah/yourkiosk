---
name: encrypted-state-backup
description: "Use when backing up or syncing tool state as an encrypted archive."
version: 1.1.0
author: agents
license: MIT
metadata:
  agents:
    tags: [backup, encryption, state, local-first, aes-gcm, scrypt]
    related_skills: [mmap-score-index, local-vector-index-mmap]
---

# Encrypted state backup for a local-first tool

A local-first tool that sells a cloud tier has one honest paid feature: carrying
the small part of its state that cannot be re-derived to another machine. Get the
division of state wrong and the "cheap cloud box" arithmetic collapses before a
line of server code exists.

## When to Use

- A local tool needs a portable backup, sync or restore, and the pricing depends
  on how much has to cross the wire.
- "Back up everything" is the current plan and the store is hundreds of MB of
  data that is public or rebuildable.
- An existing archive format must be extended, or a restore has to merge into a
  machine that already has data.
- A backup silently accepted a wrong passphrase, or a truncated file half-loaded.
- **The archive has to leave the machine**: a remote store, a "cloud tier", or a
  multi-device restore. Read "The remote half" below before writing any server
  code — the design is mostly refusals, and each one is cheaper to add first.
- Scheduling it: a backup that only runs when someone remembers is not a backup.

## Procedure

1. **Classify every artefact before designing the format.** Three buckets:

   | bucket | test | goes in the archive? |
   |---|---|---|
   | derived | one command rebuilds it (a downloaded catalogue, an index, a matrix) | **no** - header/fingerprint only, so a restore can tell you it no longer matches |
   | state | it cost money, latency or a model call to produce (decision cache, learned weights, user edits) | **yes** |
   | secret | a credential, token or key | **never** - write the *name of the variable* that holds it |

   Measure both sides and put the ratio in the report: 44 MB derived vs 380 KB of
   state is the argument that a 512 MB box is enough, and it is also the reason a
   "full backup" command is a bug - it spends quota on public data.
2. **Pick a container with an explicit version, and authenticate the header.**
   `MAGIC | salt(16) | nonce(12) | AEAD(ciphertext)`, with `MAGIC || salt || nonce`
   as associated data so the parameters cannot be swapped. A leading version byte
   or string lets a newer archive be refused with "written by a newer format"
   instead of being misparsed.
3. **Derive the key with a memory-hard KDF and give it room.**
   `scrypt(passphrase, salt, n=2**15, r=8, p=1, dklen=32)`.
4. **Load the passphrase from the environment or the TTY, never from argv.**
5. **Export to a temp file, `chmod 0600`, then `os.replace`** - same atomic-publish
   pattern as an index file. A half-written archive that a later run trusts is the
   worst possible artefact.
6. **Restore is a merge, not a replacement.** For each incoming row: if the local
   row is newer or equal, skip it; else upsert. Report `added / updated / skipped`
   and never delete a local row the archive does not know about.
7. **Inspect must not need local state.** An `info` path that reads only the
   archive and the passphrase is what lets someone check a backup on a fresh
   machine before restoring it.
8. **Make the crypto an optional extra, and keep the gate green without it.**
   `pip install 'pkg[backup]'`; the import failure must name that command, and the
   test module starts with `pytest.importorskip("cryptography")` so a host without
   the extra skips rather than fails. Never hand-roll the AEAD to avoid the
   dependency.

## The remote half: a store that cannot read what it holds

The strongest position on a rented box is not a policy, it is arithmetic: the
client seals, the server only ever touches ciphertext, so "the operator cannot
read my memory" needs no trust. Design the transfer around that and the cheapest
instance becomes enough on measured numbers rather than optimism.

1. **Two independent locks, and say which proves what.** A bearer **token**
   proves *who may write* (32 random bytes; store only its SHA-256, compare with
   `hmac.compare_digest`). A pinned **certificate fingerprint** (SHA-256 of the
   DER) proves *which server this is*. Because the identity is a hash rather than
   a name in a CA's book, a **self-signed ten-year certificate is the right
   choice** — nothing to renew, nothing to expire silently, and a different box on
   the same IP is refused. Neither lock substitutes for the passphrase.
2. **Refuse plaintext unless the caller is loopback, and refuse a wildcard bind
   unless TLS is loaded.** A store with no user accounts is one leaked token away
   from being someone else's disk. Two guards, both fail-closed: scheme other than
   `https` → refuse unless `--allow-plaintext` *and* loopback; `0.0.0.0`/`::` →
   refuse unless an explicit `--expose-public` flag, and never without TLS. A
   wildcard bind that a deployment needs must be a flag the deployment passes, not
   a default the code allows.
3. **Content-address the objects.** Name each file by the SHA-256 of its own
   bytes, verify the digest on arrival (`hash mismatch: body hashes to X, not Y`),
   and re-verify on read (`the stored object no longer hashes to its name`). That
   gives idempotent uploads (same bytes → `already_stored: true`), free duplicate
   suppression across devices, and detection of a file edited on disk behind the
   index. Publish with tmp + `fsync(file)` + `os.replace` + `fsync(dir)`.
4. **Read the object back before reporting success.** `put()` must download what
   it just wrote and compare it to the bytes it sent; "the POST returned 200" is a
   claim about the request, not about the backup. Same for `pull`: verify the hash,
   and offer `--verify` that decrypts and prints a summary so a restore is proven
   before it is merged.
5. **Split the quota by who can actually enforce it, and label the half that is
   advisory.** `max_bytes` and `max_objects` are server-enforced (507 with the
   numbers in the message). A **row** limit cannot be: the server cannot count rows
   inside a payload it cannot decrypt. Enforce rows on the client, record the
   declared count for display, and have `usage` return
   `rows_unit: "client-declared; the store cannot count rows inside ciphertext"`.
   Printing a limit you cannot enforce is the same class of lie as a bare score.
6. **Schedule it as one command.** `backup run` = export to a temp file, push,
   verify the read-back, delete the temp copy. The passphrase comes from a 0600
   `EnvironmentFile` (never argv — visible in `ps` and shell history), and the
   timer installer must **refuse to enable itself while that file has no
   passphrase**: a timer that fails every night still looks scheduled. `--start`
   should run the service once, so a broken setup fails now rather than at 03:30.
7. **Deploy with a script that prints the two things the client needs** — the
   account token exactly once, and the certificate fingerprint — plus the exact
   client commands with the real values substituted. Enable the unit, do not start
   it.

### An object store is not a cheaper version of the box

The recurring question — "why rent a box instead of putting the blobs in S3?" —
has an arithmetic answer, and it is not the one the byte count suggests. Measure
one archive first, then split what the rent actually buys:

| line | basis | cost |
|---|---|---|
| 100 users x 20 snapshots = 0.71 GiB on S3 Standard | derived from one 380,906 B archive | ~$0.03/month |
| the same blobs on the rented box | the box exists for its other duties | nothing extra |
| PUT requests, daily sync | 3,000/month | ~$0.02 |
| PUT requests, 15-minute sync | 288,000/month | ~$1.55 |

- **Name what the rent pays for before comparing prices.** TLS, token
authentication, plan and quota enforcement, the signed entitlement webhook, the
per-account lock and retention pruning all live in the process. An object store
alone leaves no service, so the like-for-like comparison is object store *plus*
whatever still runs those checks — and that is usually a box again.
- **Storage is not a saving while the data already fits.** Snapshot bytes inside
the box's spare disk gain nothing by moving, and every backend added brings a
credential chain and a failure mode with it. Say "no measurable gain at this
scale" plainly instead of proposing a migration.
- **Object storage wins on three concrete conditions**, and the answer should name
which one applies: no server at all (functions + bucket, paying per request,
gaining cold starts and a provider lock-in), more state than the disk holds, or a
durability/versioning requirement one disk cannot meet.
- **Price the request count, not only the bytes.** Write and read charges scale
with sync frequency, so shortening the timer is a line item; the saving from
leaving a box can be eaten by uploads alone. (First ~100 GB of egress is free on
S3, which is why egress is not the number to quote.)
- **Make the blob directory a swappable backend behind one config file.**
  Content-addressed objects plus a JSON index already have the right shape: a
  four-verb interface (`put`/`get`/`delete`/`exists`) with a local-directory
  implementation and an S3-compatible one (path-style plus a custom endpoint, so
  R2/MinIO/B2 fit) behind it, and the quota/pruning logic stays in the process.
  **The index stays on local disk in every case** — it is the thing `flock`
  protects during a read-modify-write, and an object store has no compare-and-swap,
  so putting it there turns the quota check into a race between two uploads. Keep
  local disk as the default so the free tier stays offline and free. Shape, SigV4
  details, the probe and the migration contract: `references/storage-backends.md`.
- **A backend swap is a migration, and the config file is the commit point.**
  Read each object from the source, hash it, write it, read it **back** from the
  target and hash it again; rewrite the config only after every object passed, and
  abort the run on the first refused write. An interrupted migration then leaves a
  store pointing at data that still exists; rewriting the config first (or
  continuing past a failure) leaves a store pointing at a half-copied target, which
  is strictly worse than one that never moved. `--keep-source` is the default, so
  the reverse command is a migration back rather than a loss, and the old blobs are
  deleted only after a real restore from the new backend has been compared.
- **Prove the backend before writing the config that depends on it.** A wrong
  bucket, region or secret all read as `403` from a distance; only a round trip
  (write probe, read back, compare, delete) separates "I can reach it" from "I can
  use it". Run that probe inside `storage set` so a config that would only fail at
  the next start never lands, and hand the same command to the user for his real
  bucket — IAM policy is the one part no local test can prove.

Concrete endpoints, file layout, the deploy/timer script shape, the cost table
template and the rotation steps: `references/remote-store.md`. The pluggable blob
backend, SigV4 signing, the probe, the verified migration and the four refusals
that keep a rude endpoint from breaking the store (`max_bytes` ceiling, no
redirect following, flattened error text, path-validated bucket):
`references/storage-backends.md`.

## The paid tier is a price table, and the table has to be the code

A plan is a set of limits, not a feature flag, and a price table nothing reads is
marketing. Make one dict the source of every number, then **parse the markdown
table in the docs and compare it cell by cell against that dict in a gate**. A
prose table drifts silently the first time a number changes, and the pricing page
is the one document a reader will quote back at you.

- **One row per tier, five numbers per row**: rows, snapshots, bytes, devices,
  retention. The free tier gets a row too (`price 0`, all limits `0`) so "no cloud
  at all" is a line in the same table instead of a footnote — and assert that no
  engine module imports the billing layer, so search quality cannot be sold by
  accident. The store never holds a key, so it cannot improve a ranking even if
  someone wanted it to; say that as the product argument, not as a promise.
- **Split enforcement by who can actually count.** Bytes, snapshots and devices
  are server-enforced (it can count files and digests). Rows are **client**-enforced
  — the payload is sealed — and `usage` must return
  `rows_unit: "client-declared"`. Retention is server-side: prune on the next
  write, **before** the quota check, or a 30-day plan fails on day 31 because the
  snapshot that should have expired is still occupying the quota.
- **A device is a second token, never a reprinted one.** Store one digest per
  device, mint at most `max_devices`, print the new token once, and keep the first
  one working. A store that can reprint a token can leak every token.
- **Entitlement is the automatable half of resale; the invoice is not.** There is
  no cloud metering API that charges an account two dollars, so: a payment
  provider posts an HMAC-signed claim, the store turns it into limits in one
  atomic write, and the invoice stays with the payment provider. Never write a
  report implying end-to-end billing automation.
- **Renting the box is scripted, and the script prints before it spends.** Default
  action `plan` prints the exact commands and runs none; a confirm environment
  variable gates the real call; `status` needs only a read permission. Put the
  exact IAM action list in the script header — a publish-only key answering
  `AccessDeniedException` is the correct outcome, not a bug to route around.

Claim shape, the verification order, the replayed-event ledger and the gate that
proves table == docs == enforcement: `references/plans-and-entitlement.md`.

## The traps that cost the most time

- **`maxmem` too tight makes scrypt fail before it derives anything.**
  `hashlib.scrypt(..., maxmem=128*N*r)` raises `ValueError: memory limit
  exceeded`; OpenSSL wants the whole working set, `128*r*(N+2)` plus its own
  slack. Use `maxmem=128*r*(N+2) + 1024*1024`. The message says "memory limit",
  which reads like a host problem and is not.
- **A wrong passphrase, a flipped byte and a truncated file must all fail the same
  way, before anything is written.** GCM gives you that for free - but only if you
  decrypt the whole payload *in memory* and parse it *after*, never streaming rows
  into the live database. Assert it: flip one byte of a real archive and require
  the restore to raise.
- **Do not catch the AEAD failure and fall through to "empty backup".** An archive
  that cannot be opened is an error; returning zero rows to merge makes a lost
  passphrase look like a successful restore.
- **A restore into a directory with no schema yet must say which command creates
  it**, not create a half-schema of its own. "Run the installer once" is the
  message; a silent `CREATE TABLE` invents a second, drifting definition.
- **Merge by the natural key with a timestamp, and compare `>=`.** Ties must not
  flip a row back and forth on every sync; and a row arriving from a machine with
  a slow clock must not overwrite a newer local one.
- **An "accounts/quota" story must not be built on the word "token"** when the
  thing counted is not model tokens: count rows or bytes and say so, or every
  cost conversation afterwards is wrong.
- **A generated service unit must be checked against the CLI's own guards, not
  assumed compatible.** The installer wrote `--host 0.0.0.0` into the unit while
  the CLI refused wildcard binds: correct code, correct intent, and the box would
  have died on its first start with the one error nobody reads. After generating a
  unit, extract its `ExecStart` and run that exact argv through the parser (or the
  guard function) in a test. The unit and the binary are two programs and only the
  test knows they agree.
- **A client that hangs up is traffic, not an error.** A store on a public address
  sees port scanners and half-open connections all day; without catching
  `BrokenPipeError`/`ConnectionResetError`/`TimeoutError`/`ssl.SSLError` around
  `handle_one_request`, each one prints a traceback and costs a thread — and the
  noise hides the real one. Assert it with `capfd`: connect five times, never send
  a request line, then require `"Traceback" not in captured.err`.
- **A malformed header must be 400, not a dropped connection.** `int(header)` on a
  non-numeric value raises inside the handler, so the caller cannot tell a bad
  request from a dead store. Parse inside `try` and answer 400 with the field name.
- **A group-or-world-readable token/accounts file is refused, not warned about,**
  exactly like the credential file: check `mode & 0o077` on load and on the client
  token read, and say "chmod 600 it". A warning gets ignored; a refusal is fixed.
- **The store's own index must be as durable as the objects.** Writing the object
  and then losing the index entry leaves an orphan the quota still counts; writing
  the index before the object leaves a row pointing at nothing. Order: object,
  `fsync`, rename, then index, then `fsync(dir)` — and have `get()` treat a missing
  file for an indexed digest as an error, not as an empty read.
- **A content hash must name the object, not the temp file.** Publishing with
  `tmp = target.with_suffix(".tmp")` means two writers storing the *same* archive
  at the same moment pick the same temporary path, and one of them dies with
  `FileNotFoundError` on its own rename — while the other looks fine. Put pid and
  thread id in the tmp name; the hash identifies bytes, and a temporary name is
  not an identity.
- **A thread lock is not a lock when two processes share the root.**
  Read-modify-write on the index guarded only by an in-process `RLock` loses an
  update the moment a second server is pointed at the same store: both read, both
  write, one snapshot disappears and the quota silently under-counts. Take a
  per-account `flock` around the whole read-modify-write, and pass a `locked=True`
  flag down to the helpers it calls so the inner calls do not self-deadlock.
- **A secret the docs tell him to set must have a delivery path in the generated
  unit.** Documenting `TRICK_ADMIN_SECRET=…` is worthless when the unit has no
  `EnvironmentFile`: the documented route then answers 401 forever and the feature
  reads as broken. Emit `EnvironmentFile=-/etc/<svc>/admin.env` (the leading `-`
  keeps the unit startable without it), document the `install -m 600` that creates
  it, and assert in a test that the generated unit contains that line.
- **An entitlement applied twice is a refund.** Verify the HMAC over the raw body
  **before** parsing it, bound the claim with a timestamp window, and record every
  applied event id so a retried webhook returns `applied: false` instead of
  re-applying yesterday's plan. A claim for an unknown account is a 404, never an
  account created — a signed message from a billing provider must not be able to
  conjure a disk.
- **An optional positional argument arrives as `None`, and `Path(None)` is a
  `TypeError`.** A verb whose archive path is declared with `nargs="?"` crashes
  with a traceback when run bare — not one of the tool's own exit paths, and it
  reads as a broken release rather than a missing argument. Validate the argument
  before it reaches any path API and raise the tool's own usage error naming an
  example command; parameterise one test over every action that takes it. The
  same hole opens on every path-valued argument: a missing one raises, it does
  not become an empty path.
- **A test constant that the algorithm does not actually use still passes when it
  is corrupted.** The SigV4 test pinned the published signature but wrote the
  sample access key inline; the repository's secret scan scrubbed that literal
  into a placeholder and the suite stayed green — the access key id is **not part
  of the HMAC**, it only appears in the `Credential=` field. Assert every part of
  the artifact you claim to check, not just the hash: signature *and* credential
  scope. The same shape bites an API key in a URL, a bucket name in a path, a
  header name in a signed-headers list.
- **A secret-scan gate eats credential-shaped test fixtures, and weakening the
  gate is not the fix.** Build such constants by concatenation
  (`"AKIA" + "IOSFODNN7EXAMPLE"`) or from parts the scanner does not match, and
  leave the scan strict. The failure is silent in both directions: scrubbed
  constants weaken tests, and a relaxed regex ships the next real key.
- **A key that already carries a directory prefix must not be rooted on that
  directory.** Keys were `objects/<acct>/<sha>.trk` while the filesystem backend
  was rooted at `<store>/objects`, so every write landed in
  `objects/objects/...`: the write succeeded, the read failed, and the first
  symptom was an empty listing after a migration. Pick one convention — key
  includes the prefix, backend rooted at the store root — and assert the resolved
  path in a test.
- **Say what the store still learns.** The archive's size and the moment it
  arrived are visible to any operator. One sentence in the docs beats an implied
  "encrypted, therefore nothing is exposed"; the user will ask.

## Tests to write with it

- round-trip: seal then open returns the same document;
- the passphrase does not appear anywhere in the ciphertext;
- wrong passphrase / one flipped bit / truncated file / foreign magic / newer
  format version: five refusal tests, each asserting the error text names the
  cause it can name;
- credentials in the settings snapshot are replaced by their variable name, while
  non-secret settings survive verbatim;
- export sets `0600`;
- merge: older local row wins, newer archive row replaces, unrelated local row
  survives, and a destination without schema is refused;
- `info` works with no local state at all;
- **remote parity as a gate, not a demo**: start a real TLS server as its own
  process with a generated certificate, pin the fingerprint, export a real archive
  from the real state directory, push it, pull it, import into an empty cache, and
  compare **three** things — bytes (sha256 of pulled == pushed == name), payload
  (decrypted documents equal key for key), rows (import into an empty cache yields
  exactly the source rows). If all three do not hold, the gate fails. A store
  tested with a synthetic fixture and a fake transport proves the code path, not
  the backup.
- **backend parity as a gate, not a unit test**: start the real store process over
TLS, push a real archive, pull it back, `migrate` the blobs to an S3-compatible
server that **verifies SigV4**, restart, pull again, `migrate` back to local
disk, pull again, then import the last pull into an empty installation. Compare
sha256 at every leg and row counts at the end; a backend swap that changes one
byte fails the build. A fake S3 that ignores the signature proves nothing — the
fake must rebuild the canonical request and reject a wrong secret, scope or
payload hash the way the provider would.
- the store refuses: wrong token, unknown digest, edited-on-disk object,
  over-quota body (and nothing is written when it refuses), non-archive upload,
  plaintext off loopback, wildcard bind without TLS, mismatched fingerprint;
- a hang-up leaves no traceback, and a malformed header is 400;
- **hardening, because these only show up under load or after a crash**: SIGKILL a
  writer mid-publish and require either no map at all or a complete one (never a
  partial); fail `os.replace` and require the previous map byte-identical; keep an
  `mmap` reader open across a republish and require it to keep the old file; eight
  threads and two store instances writing the same six blobs and require exactly
  six objects with no lost index entry; fuzz the corpus (random unicode, control
  characters, the tool's own rendered block, 40 rounds) and require unique ids,
  sane offsets and no self-output in the index.

## Reporting it

State what is *not* in the backup and why, in the same paragraph as what is. A
user who assumes the archive is a full copy will discover the omission on a new
machine, and "the catalogue rebuilds in one command" is only reassuring if it was
said before the disaster rather than after.

For the paid tier, put the arithmetic in a table with a column saying whether each
line is **measured** or **derived** (one archive's byte size and row count are
measured; "process RSS ~30 MB" is derived; "100 users fit" is arithmetic on the
first, not a load test). Never present an unrented box's capacity as a measurement,
and never write a report that reads as if you provisioned the instance: renting
costs money, so that stays the user's step, with the script and the verification
command ready. Say separately which half of the setup you could not test — the
systemd enable, the browser click, the real certificate — instead of letting a
green gate imply it.
