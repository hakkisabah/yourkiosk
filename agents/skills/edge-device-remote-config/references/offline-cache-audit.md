# Offline cache audit — checklist and test matrix

Use before claiming a device "works offline", and again whenever the data source moves from local
files to a remote base URL.

## 1. Trace the boot path

For every cached document answer these in order:

| Question | Why it matters |
|---|---|
| Where does the freshness stamp come from? | If it is fetched, an offline boot has none |
| Is there a persisted copy of the last good stamp? | Without it the disk cache is unreachable offline |
| On network failure, is the disk cache consulted or only the in-memory one? | Memory dies with the process |
| Are assets (images/video) cached with the same stamp logic? | Bodies cached, media not → broken screen |
| What does a *never-online* device show? | Empty is correct; crashing is not |

## 2. Test matrix

| Case | Setup | Expected |
|---|---|---|
| Warm cache, network up | stamp D1 in store, cache has D1 | served from cache when stamp unchanged; no large download |
| Warm cache, network down, **cold start** | fetcher raises, persisted stamp D1 | served from cache |
| Warm cache, network down, mid-run | fetcher raises after first success | last in-memory copy returned |
| No cache, network down | fetcher raises, no persisted stamp | `None` / empty state, no exception |
| Remote settings down, cache present | 403 on settings | last good settings from local cache |
| Remote settings down, no cache | 403 on settings | local file, then defaults |

Each row is one unit test with the fetcher monkeypatched — no network, no sleeps.

## 3. Implementation notes

- Persist the stamp next to the cache directory (one small file) and update it on every successful
  data round; read it as the fallback validity key.
- Keep the lookup order in one function:
  `stamp = remote_stamp() or persisted_stamp()` → `cache.read(doc, stamp)` → `fetch` → `cache.write`.
- Cache entries are only valid for the stamp they were written under; bumping the stamp invalidates
  them implicitly, which is what makes "panel published → devices refresh" work without a purge API.
- For settings specifically, the offline chain is: remote → last good copy (memory + persistent
  storage) → local file → built-in defaults. All four must be reachable in that order.

## 4. What to report back

State which rows you actually exercised, with the assertion that proves them. "The cache is used" is
not a result; "fetcher raises, persisted stamp D1, cached bytes returned" is.

## 5. Assets: revalidate with 304, never blind re-download

The trap looks like correct code: the data refresh marks every cached asset `stale` ("stamp changed,
assets may have changed"), and the asset reader treats `stale` as `miss`:

```python
kayit = index["asset"].get(key)
if not kayit or kayit.get("bayat"):   # ← every asset re-downloads after every data update
    return None
```

Disks fill up and the history shows the file present; a diagnostic that only prints "cache: hit/miss"
reports miss forever. Symptom the user reports: "the same images are fetched again and again".

### Fix shape

Cache index entry per asset:

```json
{"url": "…", "bytes": 2531968, "sha256": "…", "content_type": "image/png",
 "etag": "\"a1b539ff…\"", "last_modified": "Mon, 27 Apr 2026 19:31:31 GMT",
 "fetched_at": "…", "last_shown": "…", "stale": false}
```

Reader order:

1. fresh entry → disk, no network;
2. stale entry **with a validator** → conditional GET (`If-None-Match`, else `If-Modified-Since`):
   - `304` → clear `stale`, record `verified_at`, serve the disk copy (no body transferred);
   - `200` → body changed, rewrite file + validators;
3. no entry / no validator → normal GET.

Details that bite: `urllib` may raise `HTTPError(304)` instead of returning a response — handle both;
keep the validator when the 304 response omits it; trim only the `Content-Length`/`Accept-Encoding`
of the cached body, not the headers you need for revalidation.

### Tests (network-free)

| Case | Expect |
|---|---|
| entry with etag, server 304 | no body read, disk bytes returned, `stale` cleared |
| entry with etag, server 200 | body replaced, new etag stored |
| stale entry, server unreachable | falls back to disk copy, single warning |
| asset on disk but index says stale and no validators | one GET (old behaviour, still correct) |

One real-world probe is worth more than all of them: request the URL once for body+ETag, then once
more with `If-None-Match` and assert the second response has **no body** (`304`). Do that before
claiming the cache saves bandwidth.

### Why it matters

Before revalidation: 600 devices × 2 assets × ~3 MB, re-downloaded once per data update (every few
minutes), is tens of TB/month of CDN egress and dominates the whole bill. After revalidation egress
nearly vanishes (a 304 has no body) and **request count** becomes the bill — a new campaign costs
600 × 220 KB ≈ 132 MB ≈ $0.01. Two consequences worth stating:

- Never quote a fleet cost before you know which cache path actually runs; a fix earlier in this
  session invalidated a "thousands of dollars" estimate within the same day. Re-derive the table after
  the cache behaviour changes.
- Keep request-count pricing and egress pricing in separate rows, so a change that improves one is not
  credited against the other by mistake.

### Prefer content-addressed keys and skip revalidation entirely

Revalidation is the fix when names are stable. If **you control the name**, derive it from the bytes:
`<sha256(body)[:16]>.<ext>`. Then an unchanged asset has an unchanged URL and a changed asset has a
new one, so:

- `Cache-Control: public, max-age=31536000, immutable` — the device does not revalidate, does not
  re-download, and the CDN never re-checks the origin;
- the same bytes referenced by two campaigns/regions are **one object and one local file**, not two;
- deletion becomes reference counting instead of time guessing.

Keep the ETag path for URLs you do not control (external hosts, legacy links).

## 6. Asset size: format conversion is the only real lever

S3 does not compress static objects, and CloudFront's automatic compression covers only text types
(html/css/js/json/svg) — **images are excluded**, and PNG/JPEG are already compressed, so gzipping them
buys nothing. Convert instead. Measured on production content in this repo:

| Asset | Original | WebP q82 (same size) | WebP q82 (≤1920 px) | JPEG q85 (≤1920 px) |
|---|---|---|---|---|
| 1916×1080, 9.79 bit/px | 2473 KB | 211 KB (8.5%) | 130 KB (5.3%) | 185 KB (7.5%) |
| 1920×1080, 1.45 bit/px | 366 KB | 30 KB (8.2%) | 18 KB (4.9%) | 41 KB (11.2%) |
| second encoder (Qt) | 2473 KB / 366 KB | 221 KB (91% smaller) / 31 KB (92%) | — | — |

Pipeline rules:

- Cap the long edge at the display resolution (1920 px for a 1080p kiosk); larger only wastes RAM —
  1916×1080 decodes to ~7.9 MB, 1280×720 to ~3.5 MB.
- Keep alpha: convert PNG-with-transparency to **WebP**, never to JPEG (transparent becomes black).
- Strip EXIF/GPS in the re-encode; quality ~82 for photos, 88–92 for flat posters/logos.
- Verify the **client decoder** supports the format before rolling it out (`QImageReader.supportedImageFormats()`
  / a real decode to a pixmap), not just the encoder you used.
- Name the result content-addressed (§5) and set `Content-Type` explicitly when uploading; a wrong type
  trips the client's content-type allow-list and the asset is silently dropped.
