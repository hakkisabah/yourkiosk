---
name: phase-gated-build-projects
description: Use when a build runs in approved phases with gates.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [process, planning, phases, approval-gate, reporting]
    related_skills: [mcp-server-and-plugin-surfaces, requesting-code-review]
---

# Phase-gated build projects

## When to Use

Load this when the user hands a project prompt and expects to approve a framework
and a phased plan before any code exists, then to be consulted at every phase
boundary. Signals: "plan first, then wait for my ok", "do not start without
saying start", numbered requirements ending in "after the report we decide whether
to begin", or a standing instruction that he writes the plan and you execute it.

This is the shape of the work, not the subject of it: it applies to a retrieval
tool, a deploy pipeline, a data migration, anything multi-phase.

## Procedure

1. **Declare the capability you need before starting.** If the environment cannot
   record reusable procedures (skills) or cannot reach a tool the plan assumes,
   say so in the first message and stop. Do not start a project whose method you
   cannot carry to the next session.
2. **Write the framework before the plan.** Scope in, scope out (the things you
   will not touch without written approval), the flexibility allowance per phase,
   the quality gate that closes a phase, and the stopping rule ("I stop at each
   phase end and wait"). Naming what is out of scope is what keeps a later phase
   from quietly growing.
3. **Plan in named phases, each with an output and a machine-checked acceptance
   criterion.** A phase without a verification command is not a phase, it is an
   intention. Alternate research and build phases when a decision depends on
   measurement: research -> decision -> build -> measure -> adjust.
4. **List the blocking prerequisites and open decisions before the first line of
   code** — environment limits, missing endpoints or credentials, and the two or
   three choices that change the plan's shape. Ask them as numbered questions with
   a recommendation each, and accept a one-line answer.
5. **Execute only the approved phase.** Then stop.
6. **Close every phase the same way**: what was built, the measured numbers, the
   real errors found and the gate that now catches each one, the decisions you
   need next, and what remains unverified. Then wait.

## Pitfalls

- **When the only way to verify needs his credential, build a second path that
  does not.** A freshness check that reads the installed artifact through an admin
  API turns every phase boundary into a wait, and a check you cannot run is one
  you will skip — which is how an artifact older than the source gets reported as
  fixed. The database file, the on-disk copy, the service's own socket, the
  container's own interpreter: each is readable without his session (open it
  read-only where it matters, and assert the check wrote nothing), and each closes
  the loop on your side. Keep **writing** behind the credential and **verifying**
  outside it, then say plainly which half is his.
- **Audit the goal sentence, not the pipeline, before closing a phase.** Take the
  user's own words for what the tool is for and grep the repo for their nouns
  (`conversation|transcript|chat|passage`, or whatever the equivalent is) before
  writing the report. A phase can pass every gate with good measured numbers
  while the corpus the product exists for is never indexed at all: the pipeline
  ranked catalogues, the goal was in-conversation passages, and three phases of
  metrics said nothing about the missing half. An empty grep means the phase is
  not done - say that instead of presenting the numbers.
- **A tuning instruction is a hypothesis, not an order to ship.** When the user
  says "raise weight X", measure it: this kind of change commonly improves the
  isolated metric and degrades the end-to-end one. Report the contradiction with
  the numbers from both configurations, keep the value the measurement supports,
  and say plainly that his instruction did not survive. Silently obeying is worse
  than disagreeing with evidence, and so is silently ignoring him.
- **Never present a plan you have not checked against reality.** Read the upstream
  repo or API before promising what it can do; a tool that is not a search engine
  cannot be the retrieval layer, and finding that out three phases in costs a
  rewrite.
- **Fabricated evidence ends the project.** If a step cannot be run (no credential,
  no GPU, no browser), say "not verified" with the reason. A measured number and
  "untested, URL-level only" are both acceptable; a plausible number is not. A
  blocked or unanswered approval is not consent either: do not retry the same
  command, stop, and report that step as unrun.
- **Size parts for a turn that can be cut, and stop after each one.** When he says the
  work is taking too long and keeps getting cut in half, the fix is not a longer
  answer: split the plan into parts of roughly ten minutes each, each with a
  one-line measured output, write the list (plus a `STATE (measured)` header: branch,
  head sha, service state, which machines you can reach) to a scratch plan file, then
  finish ONE part, report its measured result, and wait for "devam" before the next.
  Merging three parts into one turn destroys both his approval gate and his ability to
  know where the cut left you.
- **Do not roll into the next phase because the current one is nearly done.** The
  stop is the product: his decisions at the boundary are what keep the build
  aligned. Asking four cheap questions beats delivering the wrong four hundred
  lines.
- **A torn-off turn is not a finished phase.** When the session is interrupted
  mid-work (a change of window, an approval that never arrived), re-read the
  working tree before continuing - `git status`/`git diff` - because writes from
  the interrupted turn may already be on disk, half-applied, and the earlier
  message may have described them as done. Re-derive the state from files, then
  run the gate before claiming anything.
- **Each error class earns a gate, not a memory.** Every real bug found during a
  phase becomes a numbered stage in the repo gate script plus a test that proves
  the stage fails when the bug returns. Report the gate count, not a promise to be
  careful.
- **A `doctor`/diagnose command must not change what it diagnoses, and must take
  its root from one flag.** Two defects live in almost every first version: it
  builds the engine to read health, which creates the store it was asked to look
  for, so the second run contradicts the first; and its token/socket/matrix paths
  still come from module-level defaults, so `doctor --home /other` silently
  inspects the real install and calls it healthy. Skip the engine when the store is
  absent, derive every path from the root flag, sort output failures-first, attach
  the exact fix command to each failing line (advice without a command is a
  complaint), and return a non-zero exit code so scripts can use it. Test the
  passive property directly: run it twice against an empty directory and assert
  both runs say the same thing and that no file appeared.
- **A machine-readable mode needs typed fields, never prose to parse.** The moment
  an installer scrapes a number out of a human sentence, rewording the sentence
  becomes a silent zero. Emit the counts as their own keys in `--json` and have the
  caller read those; assert the field's type in a test so it cannot drift back into
  a formatted string.
- **Kill what you started before you report.** No listener, daemon or background
  job outlives the phase that started it, unless he asked for a permanent service.
  Prove it with `pgrep -af` / `ss -ltn` output in the report; a service he did not
  expect is a trust failure, not a convenience.
- **Steps behind his login are his.** Admin sessions, API-key creation, UI
  dialogs: write them as numbered clicks, mark them as his, and never write the
  report as if they are done. Likewise one canonical route plus a labelled
  fallback — never two equivalent options he has to disambiguate.
- **"Install it and continue" means continue:** isolate his one blocked step
  (`--check` command, the clicks, the API key) into a single numbered block, do
  everything that does not depend on it, and keep going with the next phase. A
  phase that stops dead because one step needs his session hands back a project
  that has made no progress since he last looked, and he will say so.
- **Every artifact you add must appear as a numbered install step.** A systemd
  user unit, a token file, a socket directory, an installed function, a wrapper
  script: each one needs create / verify / remove in the install doc, in the same
  document, or a clean machine ends up with a working repo and a dead feature. He
  will say so if you skip one, and he is right to. Back it with a docs gate that
  fails the build when a documented command, path or flag does not exist — a
  README line naming a binary the package never installs is the same defect as an
  omitted step, and only the gate catches it before he does.
- **A contract copied from your own notes is not verified.** When a phase wires
  into a host (plugin API, function signature, protocol field), read the
  signature out of the installed host before writing the integration. A
  remembered call shape that the host has since changed fails on his machine, not
  in your tests, and produces the worst kind of report: confident and wrong.
- **Test an installer by shadowing the commands it calls.** A script that writes a
  systemd unit, calls `systemctl`, `ufw` or `docker` cannot be verified by reading
  it. Put a fake executable first on `PATH` that appends `"$@"` to a log, run the
  installer against a throwaway `HOME`, then assert the **call sequence**: reload
  always, `enable` only after the precondition holds, `start` only when asked. This
  is also how you prove a refusal branch really refuses — the fake log stays empty.
  A `--dry-run` that prints the generated files costs three lines and is what the
  user reads before running anything.
- **Never weaken a language/ASCII gate to fit test data.** When the repo forbids
  non-ASCII (or enforces one language) in source, fixtures containing the real
  words must use escapes (`\u0131`) or an external data file — editing the gate is
  how the rule dies, and the gate is the only thing that keeps the repo consistent
  after you leave.
- **A generated file is a program too.** When a script emits a service unit,
  compose file or wrapper, extract what it emitted and run it through the parser or
  guard it will face at runtime, in a test. The generator and the binary are two
  programs, and only that test knows they agree — a unit asking for a flag the CLI
  refuses is correct code on both sides and a dead service on his machine.
- **Replacing a mechanism is a three-part edit: code, the tests that assert the
  old one, and the docs that describe it.** A fix that swaps the mechanism (a
  script bridge for a native anchor, a request field for a store read, a model
  surface for a button) leaves the suite asserting the shape you just deleted, and
  the honest reading of nine failures is "the previous design is still the
  specification". Grep the test tree and the docs for the removed mechanism's
  nouns - the old event type, the old selector, the old field, the old surface
  name - and rewrite or delete those assertions in the same change. Patching them
  green one at a time is how a dead design survives in the suite and steals the
  next session's afternoon. Treat "tests fail because they encode the previous
  design" as work, not as noise.
- **Assume the turn can be cut at any tool call.** Long mechanical sweeps - dozens
  of edits, a fifteen-stage gate, a full test run - are exactly where an iteration
  cap or a lost window lands, and what it leaves is a half-applied tree that reads
  like breakage. Run the gate before starting a sweep, keep each edit atomic, and
  leave the tree resumable: uncommitted work either complete or reverted, never
  half. On resume, re-read the working tree and re-run the gate before describing
  anything as finished.
- **Finding the handler is not finding the trigger, and finding the trigger is
  not finding the delivery.** Reading a host's code proves a mechanism exists; it
  does not prove it runs on the event you are going to cause, nor that your
  affordance can reach it. Check three things: the *phase* it is bound to (read on
  mount versus on every navigation, first render versus a later toggle), whether
  the reader is **reactive** (a framework watching the URL/param re-runs; a
  one-shot read at mount does not), and what the renderer does to the element
  **you** emit. A handler that only reads a parameter at mount answers a full page
  load and stays silent for a same-page link — but the mirror mistake is just as
  expensive: dismissing the platform's own reader and reaching for a "phase-free"
  primitive (a fragment, an anchor id) when the markup layer rewrites your tag. A
  renderer that hardcodes `target="_blank"`, injects its own click handler or
  re-creates the node means a technically correct fragment still navigates away,
  and you spend rounds blaming the parameter. Resolve which of the two is
  actually failing — the handler's timing or your element's attributes — before
  replacing either, and read the component that *emits* your tag, not only the one
  that consumes the event.
- **Do not accept a mechanism you cannot see run.** When the environment cannot
  exercise the affordance (no browser, no admin session), the deliverable is: the
  mechanism read out of the live host, a test asserting the artifact it produces,
  the exact observation that will confirm or refute it in his hands, and a plain
  statement of which half is his. Two rounds of "it still does not work" is what a
  guessed mechanism costs.
- **The same complaint twice means the mechanism is wrong, not the tuning.** If he
  reports a defect again after a fix, do not harden the same approach: assume the
  mechanism assumption is false and replace it with one that cannot fail the same
  way (a native HTML disclosure instead of a script that may not run; reading the
  conversation from the store instead of from a request field that is not sent).
  His second report is the evidence; your passing test is not.
- **Verify a fix on his path, not yours.** The installed copy, the running
  service, the container's own interpreter, the real endpoint: a fix demonstrated
  in a local process while the host still runs the previous build is not a fix,
  and shipping it teaches him to distrust the word "fixed". Compare the artifact
  bytes or the running process, then report the delta and the one command he runs
  to pick it up.
- **A successful write is not a successful display.** When the user reports a
  rendering symptom ("not clickable", "shows raw markup", "the box will not
  close"), every assertion about the write landing can pass while the artifact is
  drawn by a component that does not interpret it - and the same complaint returns
  after each fix. Before re-engineering the mechanism again, read the stored row
  and ask **which element holds the artifact and which renderer draws that
  element**: the write path and the display path are separate contracts, and a
  write into the wrong container looks exactly like a broken feature. A chart, a
  block, a link, a panel: name the component that renders it, confirm from that
  component's own code that it renders the form you wrote, and only then judge the
  mechanism.

- **A surface has a fixed inventory of affordances, and a mechanism swap silently
  drops the ones outside the fix's scope.** For a result panel that inventory is:
  an icon that actually draws, the block opens, the block closes, a row is
  clickable, the click lands at the right place, and the row says what it matched.
  Rewrites of the container trade one for another - a sandboxed card could fold but
  could not jump, a Markdown block could jump but could not fold - and each round
  came back as a fresh defect because the previous one had been fixed. Write the
  inventory down before changing the mechanism, mark which items the new one
  supports, and state in the report which item the new design costs. An affordance
  quietly lost between phases reads to him as the same bug returning.

## Deliverable shape for this user

- Turkish prose, numbered steps, verbatim commands with real paths (no `***`, no
  `<placeholder>`). Code, identifiers and documents inside the repo are English
  only unless he says otherwise; a language gate script enforces it.
- **Phase reports live outside the repository** in a sibling directory
  (`<project>-reports/`), one file per phase, with the benchmark JSON next to it.
  The repo holds code, guides and gates; findings are not source.
- Install guides follow the single-path shape documented in the
  `mcp-server-and-plugin-surfaces` skill (its install-and-docs-gate reference).
- **A shipped tool needs a usage document in the repo, not only a phase report.**
  He will ask "how is this meant to be used" before he lets the next phase start,
  and his reason is that other people will use it. Write `docs/USAGE.md` in the
  repo (English, like the code) covering: what the tool does in one sentence, what
  it explicitly does **not** do, three good input examples and two bad ones with
  the measured reason each fails, what every marker on the output means, and which
  surface searches what. A find-style tool whose input is a query needs that
  "write it like this" section — the difference between a useful hit and "these
  results are irrelevant" is the query, and nothing in the UI says so.
- Cost claims carry units and a per-user/per-device figure with the plan tier
  named; "cheap" is not a number.
- **Describe an integration by what he will see and press, not by the host's
  vocabulary.** "Press the magnifier under any answer, type the phrase, press
  Enter" tells him what to do; "it is an Action with a valve", or naming a
  surface he did not ask for, does not - and a single unexplained host noun makes
  him stop and ask whether the feature even exists. Name the host term afterwards,
  in one clause, if it matters for support. Get the surface right first: a find
  tool belongs on a button, not in a model picker, so never write instructions
  that assume the tool is a chat model.
- End the report with the 2-4 decisions you need and an explicit statement that
  you are waiting. He replies with short keyed answers (`K1`, `K2`) — do not pad
  those into a new plan.
