# Vue + Vuetify test failures in jsdom that look like something else

Symptoms below all surface as misleading errors (timeouts, "element not found",
"expected X to be called"), so diagnose the setup, not the component.

## A failing test that hides a real error

Rule: when a `waitFor`-style poll times out on a Vuetify overlay (`v-dialog`,
`v-menu`, `v-tooltip`), check for **unhandled asynchronous errors** first — the
setup may be missing a browser API, and the thrown error never reaches the
assertion. Run vitest and look for an `Unhandled Errors` block.

- jsdom does not implement `visualViewport`. Vuetify's overlay code touches it
  while opening, so dialogs never render and the test dies on timeout.
  Fix: define a `visualViewport` stub in the test setup file.
- Other APIs jsdom lacks that Vuetify needs: `ResizeObserver`, `matchMedia`,
  `CSS.supports`, `Element.scrollTo`, and (on Node 22+) `localStorage` — Node
  defines a `globalThis.localStorage` getter that shadows jsdom's, so
  `localStorage.clear()` throws `Cannot read properties of undefined`.

## Mounting a real Vuetify component (not just stubs)

Two setup errors fire before any assertion when you mount a real Vuetify view:

- `Unknown file extension ".css"` — Vuetify imports `.css` from its component
  modules and Node cannot load it. Set `test: { css: false }` in `vite.config`
  and inline Vuetify for the test transform:
  `test: { server: { deps: { inline: ['vuetify'] } } }`.
- `[Vuetify] Could not find defaults instance` — inner components need the
  plugin even when you stub the outer ones: pass
  `global: { plugins: [createVuetify()] }` to `mount`.
- Stub the component set by TAG NAME (`'v-select': true`, `'v-btn': …`) only when
  the test is about data flow; leave `v-text-field` real if the assertion reads
  `input.value` (a stub never reflects the bound model).

## Prefer one integration mount over stubbing everything

When the bug is "the user edits a field, clicks save, and the stored bytes are the
old ones", stubbing all UI components makes the test pass while the product stays
broken — the stub is what broke the binding. Mount the **real view** with real
Vuetify, replace only the network layer (`vi.mock` of the store/connection),
trigger the real `input` event and the real button, then assert the payload handed
to the store: `expect(payload.<path>.field).toBe('NEW VALUE')`. That assertion
fails loudly for a draft reset, a stale clone, or a no-op save.

## `document.querySelector` finds nothing although the component rendered

`@vue/test-utils` mounts into a **detached** div unless `attachTo` is given.
Without it, `wrapper.text()` works (it reads the wrapper's own DOM) but every
`document.querySelector` returns null — and anything Vuetify **teleports** to
`document.body` (dialog, menu, snackbar content) is unreachable.

Fix: create a host element, append it to `document.body`, pass it as `attachTo`,
and remove hosts in `afterEach`. Detached-but-alive Vue apps otherwise pile up
across tests.

## Dialog assertions hit the wrong field

Vuetify keeps an overlay's content mounted after it was opened once. If two
dialogs in one view share a `data-testid`, a query matches the hidden one and
input silently goes nowhere. Give each dialog its own id
(`suspend-reason`, `ban-reason`) instead of a shared `reason`.

## `mock.calls.length === 0` while the component clearly used the mock

Prototype spies (`vi.spyOn(Class.prototype, 'method')`) are correct and work
across tests *provided the setup restores mocks in `afterEach`*. If identity
looks wrong, print `Class.prototype.method === spy` and
`typeof Class.prototype.method.getMockName` **before** chasing anything else —
that distinguishes "spy not installed" from "assertion broken". Do not assume
a duplicate module instance; measure it.

## Inputs and buttons in tests

- A `v-text-field`'s value lives in the input's `value` property, not in
  `wrapper.text()` — assert with `input.value`, set with
  `input.value = ...; input.dispatchEvent(new Event('input'))`.
- A raw `element.click()` does fire Vue handlers, but Vuetify's `keyup.enter`
  modifiers need a realistic `KeyboardEvent`; prefer clicking a visible button
  that performs the same call rather than synthesising key events.
