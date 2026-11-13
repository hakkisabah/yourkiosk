---
name: mcp-server-and-plugin-surfaces
description: Use when exposing a local engine to MCP or plugin hosts.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [mcp, plugin, service, socket, integration]
    related_skills: [hybrid-retrieval-reranking, mmap-score-index, open-webui]
---

# Exposing a local engine to LLM hosts

## When to Use

Load this when one local engine (search core, index, inference loop, tool) has to
be reachable from several hosts at once - an MCP client, Open WebUI, a Gemini CLI
extension, a desktop shortcut, a shell script - without each host embedding a
second copy of the logic.

## Architecture: one engine, many doors

```
host (MCP client / UI plugin / CLI / script)
   |-- unix socket  $STATE_DIR/run/<name>.sock   owner-only, transport of record
   |-- http bridge  127.0.0.1:<port>/v1/...       bearer token, for hosts that
   |                                              cannot open a socket (containers,
   |                                              browser-side plugins)
   +--> core service: ONE engine, ONE worker thread, ONE cache, ONE ranking path
```

The bridge must **forward to the socket**, not reimplement the engine. Two paths
through the code is how two hosts start disagreeing about the same query. The CLI
then does the same: try the socket, fall back to an in-process engine, and say in
the docs that in-process mode means a second cache.

## Procedure

1. **Write the wire format first.** Newline-delimited JSON:
   `{"id":N,"method":"search","params":{...}}` -> `{"id":N,"ok":true,"result":{...}}`
   or `{"ok":false,"error":{"s_code":"S5","message":"..."}}`. Reuse the
   project's existing failure taxonomy as `s_code` instead of inventing HTTP-only
   error strings; the same code then reads identically in the TUI, the MCP result
   and the HTTP body.
2. **Bind the socket owner-only and prove it in a test.** `0700` on the run dir,
   `0600` on the socket file via `os.chmod` right after `bind` (the umask decides
   otherwise). A stale file left by a killed process must be detected by
   *connecting* to it, never by `exists()`: bind-then-close leaves a file that
   refuses connections, and a live socket must never be unlinked. A regular file
   at the path is a config error, not something to delete.
3. **Serialise onto one engine thread.** See the thread-affinity pitfall below.
4. **Cap the frame, then keep the stream usable.** Refuse a line over the limit
   with an error *after draining to the next newline*, so the client gets one
   clean error instead of a desynchronised stream. A malformed line costs one
   request, never the connection.
5. **Add the HTTP bridge only for hosts that need it.** Bearer token from a
   `0600` file created with `O_EXCL`, compared with `hmac.compare_digest`, never
   logged and never echoed in an error body (scrub it in the request logger too).
   Bind **loopback by default and refuse a wildcard outright**: `0.0.0.0`, `::`,
   empty, `*` are never acceptable even when the operator asks, because the
   service has no accounts and a wildcard plus one leaked token means someone
   else spends the user's paid API credits. But do not stop at "loopback only":
   a container cannot reach the host's `127.0.0.1`, so allow one *specific* local
   address behind an explicit flag (`--expose-network`). The docker bridge
   gateway (`ip -4 -o addr show docker0 | awk '{print $4}'`, usually
   `172.17.0.1`) is reachable from containers and not from the LAN. Refusing
   every non-loopback address with no escape hatch pushes the operator to
   disable the check instead. Cap the body and size the cap to the largest
   *legitimate* payload: 32 KB is plenty for a query, but a request that may carry
   a conversation window is ~150 KiB and needs a 1 MiB cap - the small cap turns a
   valid request into a truncated line, which surfaces as a mysterious failure
   rather than a refusal. Refuse an over-cap body before parsing, but drain a
   bounded amount first and then answer `413`: closing the connection hands the
   client a broken pipe it reports as a crash. CORS stays off unless an explicit origin
   allow-list is configured - a wildcard lets any page in the user's browser spend
   the user's paid API credits. Map `s_code` -> HTTP status in one table
   (auth/unavailable 401/503, bad input 400, contention 429, disk 507).
6. **Add the MCP server on stdio** (see below), then the CLI subcommands, then
   wire the host plugins.
7. **Test through real sockets and real stdio.** See the test list below.

## Pitfalls that cost the most time

- **A SQLite connection belongs to the thread that created it; an mmap has no
  lock of its own.** A mutex around the call is not enough: the first request
  builds the connection on one handler thread and later requests arrive on
  another, which fails with "SQLite objects created in a thread can only be used
  in that same thread". Queue every job to one worker thread and block the caller
  on a per-job `Event`. Then guard the worker's *creation* with a lock and a
  double check - two requests arriving together otherwise spawn two workers, and
  the second touches the first one's connection (same bug, different disguise).
- **Opening a shared store must not take the write lock.** The service and a
  second process (a CLI query, an ingest, the terminal UI) point at the same
  SQLite file. If opening it writes anything - a schema version row, a migration,
  a `PRAGMA` that needs the lock - the second process dies with
  `database is locked` while the first is only ranking, and the failure looks like
  corruption rather than contention. Read the recorded schema version first and
  write only when it is absent or different; give the connection a `busy_timeout`;
  and translate a still-blocked write into the project's contention code instead
  of leaking `sqlite3` exceptions. A failed *cache* write must cost the memo, not
  the ranking: return false and list the storage code as degraded.
- **A health probe is not allowed to be a write.** The idiomatic FTS5 probe
  `INSERT INTO t(t) VALUES('integrity-check')` takes the write lock, so whenever
  another process is writing it fails and the store silently downgrades to LIKE
  matching - correct answers at many times the cost, with no error explaining it.
  Probe with `SELECT count(*) FROM t` instead. In general: anything in an open or
  probe path has to be read-only, or a busy neighbour changes your performance
  characteristics instead of your error message.
- **Prefer one MCP server over a per-host extension.** An MCP server is reachable
  from every MCP-capable host (agent CLIs, tool-calling frameworks, desktop
  clients) with no second artifact to install, version or remove; a host-specific
  extension is another file in the install guide and another thing to keep in
  sync. Write the extension only for a host that genuinely cannot speak MCP, and
  when the user drops a host from scope, delete its extension from the tree
  rather than leaving it as dead weight.
- **MCP: stdout is the protocol.** One stray `print` corrupts the stream and the
  host reports a broken server with no clue why. Every diagnostic goes to stderr,
  and a gate check should assert that every stdout line parses as JSON-RPC.
- **A host may spawn your server with a sanitised environment, not your shell's.**
  Gemini CLI (measured on 0.66.0) launches MCP servers with a filtered `PATH`, so
  a manifest saying `"command": "trick"` dies with `spawn trick ENOENT` even
  though the binary is on the user's PATH. Ship an absolute command
  (`/bin/sh` or `/usr/bin/env`) plus a wrapper script that resolves the
  interpreter itself, in a declared order, and sets `PYTHONPATH`/`NODE_PATH` to
  the source tree so no install step is required. A manifest that depends on
  ambient `PATH` works on the author's machine and fails on the first desktop
  launch; assert in the gate that the command is not a bare name.
- **Exposing a local engine to several hosts breaks in a different place than the code.**
  Installers belong in the gate too (see `references/gemini-cli-extension.md`).
- **A missing input must fail loudly, not shrink the job.** When the context the
  tool exists for is absent from the host call (the conversation, the quoted
  selection, the attached file), never answer with the part that still works: a
  "find in this chat" that silently searches its own catalogue instead returns
  confident, unrelated rows, which the user reports as a relevance bug rather than
  a wiring bug - and it hides the real fault for as long as nobody reads the code.
  Return the honest branch: the card/tool result states that the context could not
  be read and names the fix. Then verify the host actually sends it: read the
  dispatch code in the running host for the field list instead of trusting a
  doc-comment, and assert the field's presence on every surface.
- **A new request field must be added to every hop, and asserted at every hop.**
  One optional argument (a transcript, a scope, a filter) travels through socket
  dispatch, HTTP dispatch, the MCP schema *and* its call handler, and the host
  plugin. A hop that forgets it does not fail: it answers as though the field was
  never sent, and that answer reads as "the data does not contain it" - the one
  wrong conclusion to invite. Add it to the wire, then add a gate check that greps
  each surface for the field name.
- **A field that only *rides along* with a result is the easier one to lose, and
  it fails silently.** The message id used to point a hit back at its source is
  not a query parameter, so no hop thinks it owns it: the untrusted-input validator
  rebuilt each message as `{role, content}` and deleted it, and the UI then drew
  rows that looked clickable and pointed nowhere. Any validator that reconstructs
  objects from input must whitelist every field downstream code reads, not just the
  ones it understands; assert survival across the whole chain in one test (host
  handler → validator → chunker → row → JSON → render). If the result is cached,
  hash the riding field into the cache key as well — replayed rows otherwise carry
  the previous ids, and the bug reappears on the second query only.
- **A long-lived bridge serves the code it started with.** A process left
  listening from an earlier phase keeps answering with the pre-fix engine, so a
  host-side probe reports yesterday's behaviour and the fix looks like it did
  nothing — measured here at 16.5 hours of uptime against a file edited an hour
  ago. Before any verification that goes through the service, compare the
  listener's age to the tree's mtime (`ss -ltnp` for the pid, `ps -o etime,lstart`
  for the start, `git log -1 --format=%cI` for the code) and restart it when the
  code is newer; a rebind then fails with the project's "another service is
  listening" code because the old process still owns the socket — kill it and
  remove the stale socket file first. Do the same before handing the feature to
  the user: a stale listener is indistinguishable from a broken fix.
- **A probe that omits an optional field is testing the service's default.**
  Sending only the fields the caller cares about let the server apply its own
  `scope` default and search a different corpus, so the reply carried zero rows
  for the corpus under test and the transport was blamed twice for a payload
  mistake. In a verification call, send every field that decides *what is read*
  explicitly, even when the real host omits it; when the in-process engine
  returns rows and the transport returns none, diff the payloads before reading
  the dispatch code.
- **Grep the test doubles before widening a shared method signature.** Hand-rolled
  fakes reimplement the old shape, so one new keyword argument turns a green suite
  into a dozen failures that look like regressions in code you just wrote.
  `grep -rn 'def search(' tests/` first, give the fakes the new default, then run.
- **A tool failure is a result, not a crash.** Return `isError: true` with the
  project's `s_code` plus a sentence, so the model can tell the user "the scorer
  did not answer" instead of the turn dying mid-way.
- **Notifications have no `id` and must get no reply.** Replying to
  `notifications/initialized` desynchronises strict clients. Unknown methods get
  `-32601`, malformed JSON gets `-32700` *and the session continues*.
- **Echo the client's `protocolVersion` when you support it**, otherwise answer
  with your own and log the mismatch to stderr rather than failing the handshake.
- **One renderer for every surface.** Same rows, same `*`/`-` scored marker, same
  degraded codes, same wording. Whatever a surface displays must never claim a
  model score that did not happen.
- **A new env var is not config until documented.** Contact email for scholarly
  APIs, CORS origins, port, socket path: each one a single read point plus a line
  in the README, or nobody finds it.

## Tests that actually catch these

- Real `socket.socket(AF_UNIX)` client, real HTTP client: assert status codes and
  bodies, not mocked transports.
- Reachability and auth are one check from the far side: an unauthenticated call
  from inside the container/namespace that returns `401` proves the bridge is
  reachable *and* enforcing the token, while `111`/timeout is the network bug. Read
  it that way or a healthy `401` gets reported as a failure.
- Permission asserts: socket `0600`, run dir `0700`, token file `0600`; a
  world-readable token file is refused with a "run chmod 600" message.
- Auth: missing token -> 401, wrong token -> 401, and the token string never
  appears in any response body.
- Concurrency: N threads, each with its own client, all searching at once; assert
  N/N succeed (this is the test that catches the thread-affinity bug).
- Framing: a malformed line then a valid request on the same connection; an
  oversized line; a stale socket file; a regular file at the socket path.
- MCP: scripted stdin with `initialize`, a notification, `tools/list`, a tool
  call, an unknown method, broken JSON - assert the replies, the ids, and that
  stdout held nothing else.
- Every surface answers the same query with the same payload: unwrap each
  transport's own envelope (bridge `{"ok","result"}`, MCP
  `result.structuredContent`, CLI bare object) and compare an identity tuple per
  row, not row counts. Sending each surface a *different* transcript window turns
  every turn number and reports a transport bug that does not exist.
- TUI/CLI: piped stdin behaves like a session; Enter submits; a failed search
  prints one honest line and the session continues; blank lines are ignored.

## Deliverable shape for this user

- **Installation is a deliverable, not an afterthought.** One guide, numbered
  steps, and each artifact with a create/verify/remove triple; a generated service
  unit (`--dry-run` prints it, `--start` is opt-in) instead of a committed unit
  with hard-coded paths; and a documentation gate that fails the build when a
  document names a command, path or state default the code does not have. Recipe
  and the four gate checks: `references/install-and-docs-gate.md`.
- **Leave the machine as you found it.** Kill every listener and daemon you
  started at the end of a phase, and show the evidence (`pgrep -af`, `ss -ltn`)
  rather than asserting it. A bridge left running on `172.17.0.1:8765` between
  phases is exactly what makes the user distrust the next step. The one exception
  is a listener the *next* step needs: then say it is running, on which address,
  and give the stop command in the same message — never let it be discovered later.
- **Steps that need his session are his.** Admin logins, credential creation and
  UI valve dialogs cannot be done for him: state them as numbered clicks, mark
  them explicitly, and never phrase the report as though the install is complete.
  Offer **one** route for that install (script + API key), and mention the UI
  import only as the fallback for when the script fails: two equivalent routes
  for the same install read as "which one is safe?" and invite the user to stop
  and ask instead of proceeding.
- Gate script gains a stage per surface (schema intact, loopback-only bridge,
  transport permissions, stdout purity) next to the existing tests/compile/
  language/secret stages, numbered so a reader sees the coverage.
- Report the concurrency result as a measured number (N requests, wall time) and
  the end-to-end latency percentiles, not adjectives. Anything not measured this
  session is labelled as untested, including a fix whose only evidence is a
  URL-level assertion.
- **An installer's "OK" is not evidence.** After creating or updating a remote
  record (Open WebUI function, extension registration), read the object back and
  compare it to what was sent - byte count or a hash - and fail loudly on a
  mismatch. A successful POST proves the request was accepted, nothing about the
  stored content.

## References

- `references/gemini-cli-extension.md` - Gemini CLI extension manifest, wrapper
  script, verification recipe and the model-level limit of that check; read it
  only for a host that has no MCP support, since one MCP server already covers
  every MCP-capable host.
- `references/install-and-docs-gate.md` - install-guide shape, generated systemd
  unit, and the documentation gate that keeps a guide honest.
