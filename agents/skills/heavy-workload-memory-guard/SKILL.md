---
name: heavy-workload-memory-guard
description: "Use when a build/agent process OOMs on a small host."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [memory, oom, systemd, cgroup, node, v8, vitest, vue-tsc, ci, small-host]
---

# Memory guard for heavy workloads on a small host

## When to Use

- A stack trace shows `FatalProcessOutOfMemory`, `OOMErrorHandler`, `Heap::CollectGarbage` or
  `Process <pid> (node-MainThread) dumped core`.
- A long-running agent/service unit suddenly restarts, and each restart burns tokens or disk.
- The host has little RAM (< 8 GB) and is expected to run builds/tests **and** a chat/agent gateway
  at the same time.
- Several projects (or several agents) run `npm test` / `tsc` / `vite build` on one box.
- You are deciding between "add swap", "buy RAM" and "cap and serialize" — cap and serialize first;
  it is free and turns a dead machine into a slow one.

Symptom-level entry point for TS projects: `ts-monorepo-build-gotchas` §16.

## 1. Classify the death before capping anything

The two look alike in a journal and need different fixes:

| Signature | Who killed it | Meaning |
|---|---|---|
| `node::OOMErrorHandler`, `v8::internal::Heap::FatalProcessOutOfMemory`, `abort`, "dumped core", sweeper threads busy | the **process itself** | V8's own heap ceiling was reached and GC could not recover — the ceiling is wrong for this machine |
| `oom-kill:…`, `Killed process … total-vm`, `Task in … killed as a result of limit of …` | the **kernel / cgroup** | the host or unit ran out of real memory — no ceiling, or too many concurrent consumers |

Read the numbers that decide it:

```bash
awk '/MemTotal|MemAvailable|SwapTotal|SwapFree/' /proc/meminfo   # real headroom
systemctl --user show <unit> -p MemoryMax -p MemoryHigh -p Environment   # any cap at all?
journalctl --user -u <unit> --since -24h -o cat | grep -cE 'dumped core|Out of memory|oom-kill'
```

A V8 ceiling is **not** derived from physical RAM: Node's default is ~2 GB, and tools that ship a
fleet of them (agent TUIs, some runners) ask for 8 GB outright. On a 4 GB box the ceiling sits above
what the machine can back, so the heap grows into swap until the process aborts. That is why the same
unit can be healthy on a big dev machine and fatal on a small one.

If only one of several machines shows it, diff **what each machine runs**, not the unit files: a
machine that only reads/writes metadata never spawns the heavy child.

## 2. Measure the real peaks before choosing caps

Run each heavy command once, isolated in a scratch cgroup, and read the peak — never guess:

```bash
cd <project-dir> && systemd-run --user --unit=mem-probe --wait --collect \
  -p MemoryMax=1800M -p MemoryAccounting=yes --same-dir \
  bash -c 'npm test 2>&1 | tail -5'; systemctl --user show mem-probe -p MemoryPeak -p Result
```

(`MemoryPeak` is often `[not set]` after `--collect`; the `systemd-run` summary line prints
`Memory peak: …` — read that.) Typical numbers for a Vue/TS repo: `vitest` 350–600 MB,
`vue-tsc --noEmit` 0.9–1 GB. The conclusion that matters is usually not "one command is too big" but
"one command fits, two plus the agent gateway do not" — which dictates serialization, not a bigger cap.

## 3. Harden the service unit (derive every number at install time)

Never hardcode megabytes: the same installer runs on 4 GB and 16 GB hosts. Read `/proc/meminfo` in
the installer and write the derived values into the unit so they are **visible**:

```ini
[Unit]
StartLimitIntervalSec=300
StartLimitBurst=5                 # a crash loop must stop itself, not restart forever

[Service]
Environment=NODE_OPTIONS=--max-old-space-size=<RAM/4 clamped 512..2048>
MemoryAccounting=yes
MemoryHigh=<RAM*60%>M             # soft: kernel applies reclaim back-pressure
MemoryMax=<RAM*75%>M              # hard: OOM kills THIS unit only, machine survives
OOMPolicy=stop
TasksMax=1024
TimeoutStopSec=30
NoNewPrivileges=true              # agent sessions inside this unit must never attempt sudo
Restart=always
RestartSec=5
```

- `Environment=` reaches grandchildren (the node/tsc/vitest child of an agent session) — that is the
  only reason a Node heap ceiling works from a Python/other runtime's unit.
- Print the derived caps in the installer output (`RAM 3795 MB → MemoryHigh 2277 MB · MemoryMax
  2846 MB · heap 948 MB`). Silent caps get "fixed" later by someone who cannot see them.
- Keep the clamp: heap < 512 MB makes GC thrash, > 2048 MB is pointless on a box that cannot back it.
- `NoNewPrivileges=true` belongs in the same block even though it has nothing to do with memory: it is
  what stops an agent session running **inside** the unit from trying `sudo` on a passwordless host.
  Every attempt feeds `pam_faillock`, and after three the account is locked for everyone — including
  the operator who knows the password — so the machine closes for both the agent and the human. Read
  the live value, not the file (`systemctl --user show <unit> -p NoNewPrivileges` → `yes`); a unit
  generated by an older installer does not carry it, so add a `60-…conf` drop-in and `daemon-reload`
  instead of re-running the installer. Do **not** add `PrivateTmp` to the same unit when decision or
  state files are exchanged with the operator through `/tmp`.
- Validate syntax before installing, without touching the live unit: write the generated text to
  `~/.config/systemd/user/<name>-dogrula.service`, run `systemd-analyze --user verify <name>-dogrula.service`,
  then delete it and `daemon-reload`. (`SYSTEMD_UNIT_PATH` alone fails: `basic.target not found`.)

### Put the caps in a drop-in, not only in the installer's unit text

The caps normally live in whatever the installer emits. That makes the guard depend on **which
version of the installer is checked out on that machine** — a stale checkout emits no caps at all and
the box OOMs with a perfectly correct fix sitting on the remote. Write the caps to a drop-in owned by
the maintenance path, so the guard does not depend on the app's own install script:

```bash
~/.config/systemd/user/<unit>.d/50-bellek.conf     # [Service] MemoryHigh/Max, OOMPolicy, NODE_OPTIONS
```

A drop-in **overrides** the same keys in the main unit (systemd merge rule), so it is the single
source of truth once present. Both places still compute `<RAM*60%>` etc. independently → if the two
formulas drift, one file says `2277M` and the other `2048M` and nobody notices. Test for equality:
render the unit (`--dry-run`/`--kuru`) and the drop-in, compare the `MemoryHigh=`/`MemoryMax=` lines
literally, and assert the `--max-old-space-size` value exists in both.

**`systemctl set-property` writes a SECOND drop-in in a DIFFERENT directory.** The live-apply path is
not free of side effects: it persists `~/.config/systemd/user.control/<unit>.d/50-MemoryHigh.conf` and
`50-MemoryMax.conf` — note `user.control`, not `user/<unit>.d` — so after one live apply the unit has
two cap sources, and they do not even look alike (`systemctl show -p MemoryMax` reports **bytes**: the
value written from `2332M` comes back as `2445279232`). Anyone later asking "which cap is actually in
force?" now has to reconcile two files and a unit of measure, and a stale copy outlives your fix.

Rule: the maintenance script may use `set-property` to apply caps to the **running** unit, then it
deletes what that call wrote and keeps the single source (`user/<unit>.d/50-bellek.conf`):

```bash
CONTROL="$HOME/.config/systemd/user.control/<unit>.d"
[ -d "$CONTROL" ] && rm -f "$CONTROL"/50-MemoryHigh.conf "$CONTROL"/50-MemoryMax.conf && rmdir "$CONTROL" 2>/dev/null || true
```

Assert it from the project self-check, not by eyeballing: fail when `user.control/<unit>.d/*.conf`
exists at all, or when the effective `MemoryMax` (converted to MB) deviates from `RAM*75%` by more
than rounding (±2 MB). The unit-test stub for `systemctl` must **emulate the side effect** (write those
two files on `set-property`), otherwise the cleanup path is never exercised and a regression returns
silently.

### Apply caps to the running unit, and never restart it from inside itself

Editing a unit file does nothing until the process restarts, and a restart issued from inside that
same unit kills the caller (an agent session is a grandchild of the unit — it dies mid-turn, and
`Restart=always` then starts a fresh session that repeats the failure). Two safe paths, in order:

```bash
# 1) live cap, no restart at all — works on a running unit
#    DİKKAT: set-property AYRI bir drop-in dizinine yazar (user.control/…), yani ikinci bir
#    kaynak doğurur — uyguladıktan sonra o kopyaları sil (aşağıdaki "tek kaynak" notu).
systemctl --user set-property <unit> MemoryHigh=2277M MemoryMax=2846M

# 2) restart is genuinely needed (new ExecStart): detect ANCESTRY, then defer
#
# "Am I inside the unit?" must be the unit's MainPID in this shell's ancestry, NOT a match on
# /proc/self/cgroup: every process spawned UNDER the unit (the agent's own test suite, a review
# run started from its shell) also carries the unit name there, so the grep sends you down the
# deferred branch from a plain terminal too — and that branch is the one that skips reset-failed
# and the immediate restart, i.e. the branch the crash loop actually needs.
unit_icinde() {
  main="$(systemctl --user show "<unit>" -p MainPID --value 2>/dev/null)" || return 1
  case "${main:-}" in ''|*[!0-9]*) return 1 ;; esac
  [ "$main" -gt 1 ] || return 1          # 0/1 = no running main process → not inside
  pid=$$; i=0
  while [ "$i" -lt 16 ] && [ "${pid:-0}" -gt 1 ]; do
    [ "$pid" = "$main" ] && return 0
    pid="$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null)"
    case "${pid:-}" in ''|*[!0-9]*) return 1 ;; esac
    i=$(( i + 1 ))
  done
  return 1
}
if unit_icinde; then
  systemd-run --user --collect --on-active=900s --unit="<unit>-devralma-$(date +%s)" \
    systemctl --user restart "<unit>"        # current turn finishes, then the unit picks up new code
fi
```

Also install without collateral kills: `systemctl --user enable <unit>` and only `start` when
`is-active` is false — `enable --now` plus a re-`start` on an already-running unit throws away an
in-flight job for no reason.

Make the detection testable instead of hand-verified: stub `systemctl` on `PATH` so
`show -p MainPID --value` echoes a chosen pid, and write two tests — `MainPID` = the test's own pid
(→ deferred branch, no immediate `restart`) and `MainPID` = an unrelated pid (→ immediate
`reset-failed` + `restart`). Without the stub both branches can only be exercised by running the
installer from inside the live unit, which is exactly the case that kills the caller.

Starting after a crash loop needs `reset-failed` **first**: an OOM loop leaves the unit `failed`
*and* the StartLimit counter full, so `systemctl --user start` refuses with "start request repeated
too quickly" — and an installer that treats that as an error reports failure for a unit that would
start fine. Order: `reset-failed` → `start`/`restart` → 2 s later `is-active`, else print
`journalctl --user -u <unit> -n 30` and exit non-zero.

## 4. Route heavy commands through a capped runner

`scripts/memory-capped-run.sh` (this skill) is the reusable shape; copy it into the repo, e.g.
`otomasyon/betik/agir-komut.sh`, so both humans and automation call the same entry point.

```bash
./<repo>/<path>/memory-capped-run.sh --kuru -- npm test     # plan only: caps, heap, lock, no execution
./<repo>/<path>/memory-capped-run.sh -- npm run tip         # capped run
```

Contract it provides, each point load-bearing:

- **Refuse when headroom is gone** (exit 7 with the numbers and the remedy). Starting a heavy job at
  200 MB free is how the machine dies; refusing is the cheap failure.
- **Set `NODE_OPTIONS=--max-old-space-size`** sized from the cgroup cap (≈60%), and leave an
  explicitly supplied ceiling alone.
- **Isolate in a cgroup** (`systemd-run --user --scope -p MemoryMax -p MemoryHigh`) so a blow-up kills
  the command, not the session or the host.
- **Serialize with `flock`** (exit 8 when another heavy job holds it). Concurrency, not any single
  command, is what overflows a small box. The lock file itself is an attack surface: a fixed name
  under `${TMPDIR:-/tmp}` opened with `exec 9>"$KILIT"` follows a symlink an attacker pre-created
  (O_NOFOLLOW/O_EXCL absent). Put the lock in a directory you own with `0700`, and check `-L` before
  opening — a symlink is exit 2 with the path printed, not a silent redirect. Test it by creating
  the symlink yourself and asserting the runner refuses.
- **Wall-clock `timeout`** plus one line per run in a log file, so "why did it die" is answerable.
  The log line carries the full argv, so its permissions are part of the contract: a token passed as
  an argument (`curl -H "Authorization: Bearer …"`) is written to disk. Create the log dir `0700` and
  the file `0600` **at creation time** (umask none, not `chmod` after the first append) and mask
  token/password-shaped argv segments before printing. **The masker must be case-insensitive and must
  cover every assignment/flag/query shape, not just the shapes you had in mind:** `/--token|--parola/`
  plus `(KEY|TOKEN)=` in capitals misses `--access_token=…`, `authToken=…`, `npm_config_//…:_authToken=…`
  and `https://host/x?token=…`, so the secret lands in the log anyway and the mask gives false
  confidence. Match `[A-Za-z_]*(token|secret|apikey|key)=` case-insensitively and mask query strings
  too, then **prove it with `--kuru`** on those exact argv shapes — the mask function is only as good
  as the probe you ran against it. A `0644` run log in a shared home directory is
  a secret leak with a friendly name, and it is the runner itself — the tool meant to be safe — that
  writes it.

## 5. Make the guard checkable, and tell automated reviewers what the exit codes mean

- Add the invariants as control points in the project's own self-check (`--kendini-denetle` style):
  cap present in the unit, headroom/swap sane, no OOM line in the last 24 h, runner installed and
  executable. A guard nobody asserts on is removed by the next refactor.
- Write the rule where agents read it (the review prompt, the repo's ops doc, AGENTS.md if you may
  edit it): heavy Node commands go through the runner, and **exit 7/8 is a self-correction signal, not
  a finding about the code under review** — otherwise an agent files a bug against the project for its
  own lack of memory.

## Pitfalls

- **`ulimit -v` is not a memory cap for V8/JVM.** Both reserve huge virtual ranges; an address-space
  limit makes them fail for no visible reason. Use cgroups (`MemoryMax`); if cgroups are unavailable,
  fall back to the heap ceiling alone and say so out loud.
- **`systemd-run` existing is not `systemd-run` working.** Without a user bus it fails before running
  the command, and a `|| true` around it turns into "the command silently never ran". Probe once
  (`systemd-run --user --scope --quiet --collect -- /bin/true`) and fall back with a printed warning.
- **`Restart=always` without `StartLimitBurst` is an amplifier.** The original crash restarts every few
  seconds, and if each start spawns an agent session you pay tokens and disk per crash.
- **Capping the wrong process.** A crash inside a unit is often a grandchild (node under a Python
  agent). Fix it with unit-level `Environment=` + cgroup, not by editing the child's config.
- **Capping only the service.** Interactive sessions of the same project OOM the box too — the runner
  is for humans as well; document it as the default way to run tests.
- **Silent degradation.** Any fallback path (no cgroup, unknown RAM, empty `/proc/meminfo`) must print
  one warning line. A guard that quietly does nothing reads as "fixed" until the next core dump.
- **Caps are worth nothing if the unit runs stale code.** The guard lives in the installer, so a
  service started from a developer's working checkout keeps executing the version that has no caps —
  the crash repeats while the fix sits merged on the remote. Before blaming the numbers, print the
  running code's revision and compare it with the remote tip (`git ls-remote --heads origin <branch>`)
  as a control point, and run long-lived services from a machine-owned clone instead of a human
  checkout (see `automated-pr-review-gate` § self-updating watcher).
- **A human checkout can make `git pull` fail outright.** After long use, `.git/config` accumulates
dozens of `[branch "x"]` sections whose `merge` points at a branch that no longer exists (or all at
`refs/heads/main`); plain `git pull` then dies with "no tracking information" and the owner learns to
type `git pull origin main` by hand — a step nobody repeats on an unattended machine. Treat that as
evidence for the machine-owned clone, not as user error worth documenting.
- **A cap that only exists in the unit file is not a cap.** Verify with
  `systemctl --user show <unit> -p MemoryMax -p MemoryHigh -p Environment` and by asserting it from the
  project's own self-check — reading the file you just wrote proves nothing about what runs.
- **Unit text emitted by an unquoted heredoc executes backticks.** `cat <<UNIT … UNIT` performs
  command substitution, so a backtick pair inside a *comment* (`# tells --guncelle to …` rewritten
  with backticks) runs a command: its output is inlined into the unit and the neighbouring word
  vanishes, with no error printed. Keep backticks out of the template and assert it — parse the
  rendered unit and require no backtick in any `#` line; rendering tests that only grep for the keys
  you expect stay green while the text is silently corrupted.

## Verification checklist

- [ ] Death classified (self-abort vs kernel/cgroup) and the number that proves it recorded.
- [ ] Real peaks measured per heavy command with `systemd-run --scope` + the `Memory peak:` line.
- [ ] Unit caps derived from `/proc/meminfo`, printed by the installer, `< MemoryHigh < MemoryMax`,
      both below physical RAM; `systemd-analyze --user verify` clean.
- [ ] ONE cap source: no leftover `user.control/<unit>.d/*.conf` from `set-property`, and the
      effective `MemoryMax` (MB) matches the drop-in within rounding.
- [ ] Runner: `--kuru` plan, exit 7 on low headroom, exit 8 under lock contention, child exit code
      propagated, V8 ceiling visible in the child (`node -e "…heap_size_limit…"`).
- [ ] Control point in the project self-check + the rule written where agents read it.
- [ ] Tests exist for the runner (fake `/proc/meminfo` file, threshold rejection, lock contention,
      exit-code propagation) — memory guards fail by accident, so they need deterministic tests.
