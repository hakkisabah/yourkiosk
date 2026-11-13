# Content targeting: per-district / per-region / per-device items

Use when one content feed serves a fleet but some items must reach only part of it (a campaign for one
city, a notice for one store). Optional fields on the item — never a second feed, never a second base
URL.

## Field contract

```jsonc
"Yayinlar": {
  "5": {
    "start": "2026-10-24T08:30:00", "end": "2026-10-24T23:59:00",
    "contentUrl": "https://cdn/…/9f2c1ab34de5f607.webp", "duration": 30,

    "ilceId":  "30607352906750376",   // optional
    "bolgeId": "73154087615041151",   // optional
    "cihazId": "98273648723468273"    // optional, narrowest
  }
}
```

| Rule | Behaviour |
|---|---|
| field absent / `""` / whitespace | no constraint for that level |
| several fields present | **AND** — all must match |
| alias spellings | accept `ilce_id`/`ilce`, `bolge_id`/`bolge`, `cihaz_id`/`clientID`/`clientId` |
| unknown extra field | ignore (future `semt`, `group`) |

Backward compatibility is the whole point: an existing feed with no scope fields must behave exactly
as before. Test that case first, not last.

## Where the filter goes

**In the pool builder** — the function that turns the feed into the device's working list — not in the
renderer:

```python
havuz = [y for y in sirali(feed) if kapsam_uygun(y, ilce, bolge, cihaz)]
```

Why: the renderer runs after the asset fetch. Filtering there still downloads and caches every
non-matching image, so the fleet pays for content it can never show, and "N items" counts them.

## Fail closed

If the device cannot determine its own district/region (identity document unreadable, empty match),
a **targeted** item is hidden. Untargeted items still render. Rationale: showing another region's
campaign on a public screen is a real-world error; showing only the generic items is merely reduced.

Signal it in diagnostics (`scope: ilce=- bolge=- cihaz=…`) so "why is my targeted campaign missing"
has a one-line answer instead of a code hunt.

## Signature discipline

The scope is three strings, not a tuple to splat. Call sites pass keywords:

```python
mgr.get_active(items, ilce_id=i, bolge_id=b, cihaz_id=c)   # not *self._scope()
```

A splatted tuple binds to the next positional parameter (usually `now`), the per-item `except
TypeError` swallows it, and the symptom is "every future item skipped" with a timezone-shaped warning.

## Panel side

If the panel only displays the feed (read-only), no UI change is needed and the fields can be set in
the data document. Adding a selector is a design change: ask before touching the layout. When the
panel *does* get a selector, it must offer "all devices" as the default and echo the resolved scope
in the same language the diagnostics use.

## Test matrix

| Case | Expect |
|---|---|
| no scope fields, any device | visible |
| `ilceId` matches / differs | visible / hidden |
| `bolgeId` matches / differs | visible / hidden |
| `cihazId` matches / differs | visible / hidden |
| district + region both set, region differs | hidden (AND) |
| blank / whitespace fields | treated as no constraint |
| alias spelling (`ilce_id`, `clientID`) | resolved |
| device scope unknown (no match doc) | targeted hidden, untargeted visible |
| non-matching item | absent from the pool, zero fetches |

Assert on the resulting **list of URLs**, not on a boolean — a filter that returns the right count but
the wrong item passes a boolean test.

## Reporting

State the numbers: how many items the feed has, how many the test device sees, and how many assets it
therefore downloads. "Targeting works" without those three numbers is not evidence.
