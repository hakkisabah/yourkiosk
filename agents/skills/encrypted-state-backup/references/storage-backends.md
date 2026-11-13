# Pluggable blob backend — fs, S3, and a verified move between them

Depth for "the store's disk is a choice": a backend interface, an S3-compatible
implementation on the standard library, a probe, and a migration that cannot lose
an archive. Shapes below were run against a store holding a real 380 KB archive.

## The split that makes it one config line

The store keeps two kinds of bytes and only one of them may move.

| half | size | needs | stays on |
|---|---|---|---|
| index (`accounts.json`, `objects/<acct>/index.json`) | KBs | atomic read-modify-write under `flock` (quota, pruning, listing) | **local disk, always** |
| blobs (`objects/<acct>/<sha256>.trk`) | 100s of KB each, write-once | nothing but put/get/delete | **backend of choice** |

An object store has no compare-and-swap, so an index there turns the quota check
into a race between two uploads that both saw the old usage. That is the sentence
to put in the doc, because "why not the whole store in S3" comes back otherwise.

## Interface (four verbs)

```python
class BlobBackend:
    name = "none"
    def put(self, key: str, blob: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def describe(self) -> dict: ...      # for `storage show`, no secrets
```

- `get` on a missing key raises the tool's config/not-found error, and the store
translates it: an object the *index* lists but the backend lacks is storage-io
(S6), not a wrong id, because the index is the authority on existence.
- `delete` on a missing key is success — the caller asked for "gone".
- `exists` is `HEAD`, not `GET`: proving presence must not download the archive.

## Key scheme, and the double-prefix trap

One key string in every backend, mirroring the on-disk layout:

```python
object_key(account, sha) -> f"objects/{account}/{sha}.trk"
```

Validate the inputs where the key is built (hex len 64, account matches
`[A-Za-z0-9._-]`, no `..`), so an account name can never escape a prefix.

**Because the key already starts with `objects/`, the filesystem backend must be
rooted at the store root, not at `root/objects`.** Rooting it one level deeper
writes `objects/objects/<acct>/<sha>.trk`: the write succeeds, the read fails, and
the only symptom is an empty listing or a "listed but absent" error after a
migration. Assert the resulting path in a test.

## S3 implementation on stdlib only

`PUT <url>` with body, `AWS4-HMAC-SHA256`, `x-amz-content-sha256` = the real body
hash (not `UNSIGNED-PAYLOAD`), signed headers lowercased and sorted, canonical URI
encoded per segment, canonical query sorted. Retry on 429/500/502/503/504 with
backoff; treat 404 on `GET`/`HEAD` as absent; 404 on `DELETE` as success.

- **Verify the signer against the provider's published vector before anything
  else.** The AWS documentation example (GET `test.txt`, `20130524T000000Z`,
  us-east-1, sample keys) pins the whole canonical request; a wrong ladder or a
  wrong header set fails immediately instead of producing 403s you cannot read.
- **The access key id is not part of the HMAC**, so a test whose access key was
  scrubbed to a placeholder *still* passes — and the assertion silently stops
  covering the Credential field. Assert both: the signature suffix **and**
  `Credential=<key>/<date>/<region>/s3/aws4_request` in the Authorization header.
- Path-style (`<endpoint>/<bucket>/<key>`) is the portable default and the only
  one a fake testing server can serve on `127.0.0.1`; virtual-host
  (`<bucket>.<endpoint>/<key>`) is a URL-shape change, testable at that level
  only. Say which one you exercised when reporting.
- Accept `http://` only for a loopback endpoint (a local MinIO). Anything else
  must be TLS, for the same reason the vault server refuses a plaintext public
  bind.
- Optional `x-amz-server-side-encryption` must be in the **signed** headers, not
  merely sent.

## When the endpoint is not polite

The happy path above was measured against a server that verifies signatures. That
proves the signer, not the client: a self-hosted MinIO, an R2/B2 endpoint, or any
proxy in front of one can answer with a redirect, a body that never ends, or an
error document that is not XML. Four refusals belong in the client, and each one
is silent when it is handled by accident.

- **Cap the response read; do not `response.read()`.** `read()` trusts
  `Content-Length` (or a chunked stream) to end, so a wrong or hostile endpoint
  can make the process buffer gigabytes. Loop in 64 KB chunks against an
  `max_bytes` ceiling (default 64 MB, overridable by env), raise the moment it is
  crossed, and ship one test that proves a body *at* the ceiling still passes —
  otherwise the cap eventually rejects the very archive it was sized for.
- **Never follow a redirect.** An S3 client that chases a `302` hands a signed
  request — and its `Authorization` header — to whatever host the answer names,
  and a `3xx` also invites a downgrade to plain HTTP. Treat any 3xx as an error
  and report the status. Testing this needs **two** fake servers: the redirecting
  one, and a second one as the `Location` target that must receive **zero**
  requests. Assert on the target's request log, not on the redirecting server's —
  a redirect is answered before the handler records anything, so counting there
  asserts `0 == 1` and the failure says nothing about the code.
- **Error text is untrusted input.** Strip control characters, flatten to one
  line, cap the length (60 for the code, ~300 for the message). A newline inside
  `<Message>` forges a second log line — the shape to test is
  `denied\nERROR … login succeeded` in the body and a one-line result out. A
  binary or non-XML body must produce `http 500` and no traceback.
- **Validate bucket and prefix at startup, as path segments.** A bucket name is a
  URL path component: refuse `/`, `\\`, whitespace and `..`; refuse a prefix whose
  segments contain `..`, an empty segment or a control character; refuse a
  non-positive ceiling. Failing at `storage set` beats failing on the next start,
  and it is the same class of guard as `object_key()` validating the account.
- Nothing from the request may appear in an error: not the Authorization header,
  not the access key id, not the secret. Assert it by raising a rejected request
  and searching the message for both keys.

Give the fake server misbehaviour switches rather than writing five ad-hoc
servers: `oversize=<bytes>`, `redirect=<url>`, `garbage=(status, body)` and the
existing `fail_first=<n>`. A fake that can only be polite tests only the path
that never breaks in production.

## Credentials never in the config file

`storage.json` holds endpoint, bucket, region, prefix, addressing, sse — bucket
names, not keys, because config files end up pasted into bug reports.

- Read `TRICK_S3_ACCESS_KEY` / `TRICK_S3_SECRET_KEY` from the environment first,
  then from a `credentials_file` that must be `0600`: check `mode & 0o077` and
  **refuse** with "chmod 600", never warn.
- The generated systemd unit needs `EnvironmentFile=-/etc/<svc>/storage.env`, and
the deploy script should create that file empty and `0600` — otherwise the
documented credential route has no delivery path and answers AccessDenied
forever.
- A **missing** credential must be a startup error naming both variable names,
never a silent fallback to an anonymous client.

## Probe before trusting a bucket

`storage test` = write a small probe object, read it back, compare, delete.
A wrong bucket, region or secret all look like "403" from a distance; only a
round trip distinguishes "I can reach the bucket" from "I can use the bucket".
Run it (a) as the gate before `storage set` writes the config, so a config that
only fails at the next start never lands, and (b) as the one command the user
runs against his real bucket, since IAM policy is the part no test can prove.

## Migration: read-back per object, config last

```
for each (account, sha) in local index:
    blob = source.get(key); assert sha256(blob) == sha      # source not corrupt
    target.put(key, blob)
    assert sha256(target.get(key)) == sha                  # target really holds it
write storage.json                                        # only after ALL passed
```

- **The config is the commit point.** Rewriting it earlier means an interrupted
  run leaves a store pointing at a half-copied target, which is strictly worse
  than a store that never moved.
- **Abort on the first refused write**, don't hammer a locked bucket through the
  rest of the list, and report what was verified before the stop.
- `--dry-run` counts objects/bytes and writes nothing.
- `--keep-source` is the default; deleting the old blobs is a separate deliberate
  step, taken after a real restore from the new backend has been imported and
  compared — not after a green exit code. Keeping them is also what makes the
  reverse command (`--backend fs`) a migration back rather than a loss.
- Idempotent by construction: content-addressed keys mean a second run rewrites
the same keys with the same bytes and re-verifies them.

## Gate it as three legs, not as a unit test

A backend test with a fake transport proves the code path, not the backup. The
check that belongs in the repo gate starts the **real store process over real
TLS**, pushes a real archive, then:

1. pull → sha256 == pushed archive;
2. `storage migrate --backend s3` against a server that **verifies SigV4**, restart
the store, pull → same sha256, and the config on disk now says `s3`;
3. `storage migrate --backend fs`, restart, pull → same sha256, config says `fs`;
4. import the last pull into an empty installation and compare row counts.

Write a fake S3 that rebuilds the canonical request from the bytes it received
and recomputes the signature: a server that ignores the signature would pass with
a wrong secret, wrong scope and wrong payload hash. Give it a first-attempt 503
knob so the retry path is exercised without a flaky network.

## Reporting limits honestly

Three sentences that keep the report true: the S3 half was measured against a
signature-verifying server, **not** against the provider (IAM policy is unproven
until the user runs `storage test` on his own bucket); virtual-host addressing was
checked at URL level only; and no instance was rented, so "it runs on a $5 box"
stays derived arithmetic.
