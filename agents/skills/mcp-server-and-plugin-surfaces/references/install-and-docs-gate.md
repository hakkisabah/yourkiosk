# Install guide and the documentation gate

The install guide is part of the deliverable, and it rots in exactly one
direction: it keeps claiming commands, paths and services that no longer exist.
An unverified guide is worse than no guide, because the user copies it verbatim.

## Shape of the guide

1. **Paths table first.** Repository, interpreter, state directory, every file the
   project writes, the credential file, the generated service unit. Absolute,
   with the override env var named next to the default.
2. **Prerequisites as a checkable claim**, not a sentence: the interpreter version,
   FTS5 (or the equivalent feature probe), the optional accelerator, and whether
   Docker/host plugins are needed at all.
3. **One numbered step per artifact**, each carrying three things in the same
   place: the command that creates it, the command that verifies it with an
   expected output string, and the command that removes it. A step that starts a
   process is marked `[starts a service]`; nothing else may start one.
4. **A closing table** of every artifact -> created by -> removed by. This is the
   page the user reads when he wants his machine back.
5. **Failure branches with the fix**, in the guide and in the product: `401` names
   the credential, `connection refused` names the URL, an empty result shows the
   `S<n>` reason so "no hits" cannot be read as "broken".

## A first-run script for the reader who has never installed anything

The numbered guide serves a reader who reads; one idempotent script serves the one
who pastes. Ship both, and keep the script honest:

- **Re-runnable, with a stage banner** (`== 3/6 catalogues`): a partial run and a
  resumed run then read the same.
- **Skip expensive work by measurement, not by hope.** Count what already exists
  (`doctor` JSON -> `store.docs`) and skip ingest above a floor, with a
  `--skip-ingest` flag for the developer loop. Never re-download the catalogue to
  prove the script still works.
- **Detect an existing listener before starting one.** A second `serve` on the same
  state dir exits with the contention code, and reporting that as "the server
  exited" sends the reader hunting a bug that is not there. Check the port with
  `ss -ltn`, print what is already listening, leave it alone.
- **Nothing starts without `--start`.** Without it, print the exact resolved
  command instead.
- **End by printing his steps verbatim** — real interpreter path, real token path,
  no placeholders — and say what he should see when it worked.

Test it the way a reader would: run it with the expensive stage skipped on a machine
that already holds state, and check the exit code and the final lines.

## The generated service unit

Never commit a unit file with a hard-coded path; it is wrong on the next machine.
Ship a small installer script that resolves the machine at install time:
repository path from `dirname $0/..`, interpreter from the venv, and the bind
address from `ip -4 -o addr show docker0 | awk '{print $4}'` (falling back to
loopback when Docker is absent). Two flags carry the semantics:

- `--dry-run` prints the rendered unit to stdout and touches nothing — no
  `mkdir`, no `daemon-reload`, no `systemctl`. This is the only form a test can
  assert on safely, so it must exist.
- `--start` (opt-in) is the only thing allowed to `systemctl --user enable --now`.
  Writing a unit is not consent to run it.

Then prove the `ExecStart` line survives systemd's clean environment before you
claim it works:

```sh
env -i HOME="$HOME" PATH=/usr/bin:/bin PYTHONPATH="$PWD/src" \
  ./venv/bin/python -m pkg serve --http-host 172.17.0.1 --expose-network
```

A service that works in your shell and dies under `env -i` was reading an
interactive-only variable. Keep the unit's `Environment=` lines to what the run
actually needs.

## Documentation gate

Add a gate stage that fails the build when a document disagrees with the code.
Four checks pay for themselves immediately:

1. **Enumerate subcommands from the real parser**, never from a hard-coded list:
   build the argument parser and read its `_SubParsersAction.choices`.
2. **Reject the bare program-name invocation** unless the package actually
   declares `[project.scripts]`. Regex `\bpkg\s+([a-z][\w-]*)\b` over the docs,
   skip a match preceded by `-m `, and report file + line. Allow-list lines that
   quote a process for `pkill`/`pgrep` — the pattern there legitimately reads
   like a command.
3. **Every repository-relative path a document names must exist**; every
   state-directory path must equal a default imported from the code, not a
   string retyped in the doc.
4. **Test the gate by injecting each mistake it exists to catch.** A gate nobody
   has watched fail is decoration: one test per check, asserting the gate returns
   the specific complaint.

The class this catches, in one line: a README that says `tool serve` while the
package declares no console script, so a clean machine answers `command not
found` and the user blames the install. Either declare the entry point or never
document the bare name.

## Retire the duplicate guide

One install path. When an integration README grows its own install steps, strip
it to the *why* and link the single guide, otherwise the two drift and the user
finds the stale one. Keep duplicated prose only where it is a rationale ("the
container cannot reach the host's 127.0.0.1"), never where it is a command.
