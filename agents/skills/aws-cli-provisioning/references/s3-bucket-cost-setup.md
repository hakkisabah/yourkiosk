# Cost-first S3 bucket setup

Apply these **before** the first upload, and present the result as a table the user can check.

## Lifecycle rules worth having on every bucket

```json
{
  "Rules": [
    { "ID": "abort-mpu", "Status": "Enabled", "Filter": { "Prefix": "" },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 } },
    { "ID": "old-versions", "Status": "Enabled", "Filter": { "Prefix": "" },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30, "NewerNoncurrentVersions": 3 } },
    { "ID": "media-expiry", "Status": "Enabled", "Filter": { "Prefix": "media/" },
      "Expiration": { "Days": 45 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 15 } }
  ]
}
```

Why each one:

- **abort-mpu** — half-finished multipart uploads are invisible in the console and billed forever.
- **old-versions** — versioning is the cheapest backup you get, but without noncurrent expiry the
  bucket grows on every write for the app's lifetime. `NewerNoncurrentVersions: 3` keeps a usable
  undo window.
- **media-expiry** — safety net under whatever the app already deletes; keep it longer than the
  app's own retention so it never fights it.

Verify with `aws s3api get-bucket-lifecycle-configuration` and print the rule ids + settings.

### Expiry keyed to a content date is NOT expressible — layer it

"Delete the poster when its campaign ends" cannot be a lifecycle rule. Lifecycle knows only:

| Selector | Reality |
|---|---|
| `Expiration.Days` | N days after the object was **created** — not the item's `end` field |
| `Expiration.Date` | one fixed calendar day per **rule**; every object matching the rule dies that day |
| `Filter.Tag` | tag **values** are static; a date cannot be a tag condition |
| rule count | 1000 per bucket — "one rule per item" does not scale |

So the working shape is three layers, and only the middle one is app logic:

1. **Application sweep (the real one).** The publisher deletes the record and the object once
   `end + margin` has passed and **no other item still references that URL**. Reference counting, not
   time guessing — the same image is often reused by a later campaign.
2. **Daily sweeper (cheap safety net).** EventBridge + Lambda reads the published index, computes
   `max(end)`, and deletes objects with no reference past that point. Pennies/month; catches deletions
   the panel never ran (crash, offline admin).
3. **Coarse lifecycle backstop.** Keep a prefix expiry (e.g. 90 days) merely to stop orphan growth;
   keep it **longer** than any real campaign so it never races the app.

If a Lambda is not acceptable, a date-prefixed upload (`assets/2026-10-30/<hash>.webp`) plus
`Expiration.Days = 30` approximates it — but an item that outlives the prefix loses its asset while
still live, so state that trade-off out loud.

### Compression: what S3 and CloudFront will and will not do

S3 stores bytes as given (gzip only if you upload a gzipped body with `Content-Encoding: gzip`), and
CloudFront auto-compresses **text types only** (html/css/js/json/svg). Images are excluded, and
PNG/JPEG are already compressed, so re-compressing is wasted work. The lever is **format conversion**
at upload time (WebP/AVIF), not a bucket setting — see
`edge-device-remote-config/references/offline-cache-audit.md` §6 for measured numbers.

## What to deliberately NOT do (say why, with numbers)

| Skipped | Reason |
|---|---|
| Intelligent-Tiering | monitoring fee is per 1,000 objects; with hundreds of objects it exceeds the savings |
| Standard-IA / Glacier | frequently-read JSON pays retrieval fees and a 30-day minimum; wrong tool |
| Disabling versioning | loses the backup; expiring noncurrent versions is strictly better |
| CDN in front, on day one | low device count fits inside free quotas; revisit when egress or request counts grow |

## The cost table to hand over

Estimate in four lines, monthly: storage (GB × class rate), GET count (polls/day × devices ×
rate/1000), PUT count, egress (GB × rate). Show the arithmetic, e.g. a small fleet lands at
**≈ $0.20/month**, dominated by GET requests from a tiny "has anything changed" poll. If request
count dominates, the lever is the poll interval plus device-side caching, not a storage-class
change.

## Exposure settings that pair with the cost work

```bash
aws s3api put-public-access-block --bucket <name> --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket <name> --versioning-configuration Status=Enabled
```

- Public access block first, always: an accidentally public object is both a leak and an egress bill.
- Writes should come from a role scoped to one prefix (`app/*`), read/write/delete only — verify with
  a denied write outside the prefix.
- **New buckets are already SSE-S3 encrypted and BucketOwnerEnforced.** Setting them explicitly
  requires extra IAM actions for no security gain; state the default instead.
- If a browser writes directly, CORS must use the `{"CORSRules": [...]}` wrapper and list exact
  origins (`http://localhost:5173`, the deployed origin). Wildcard subdomains are not allowed — add
  the real host after it exists.

## Post-run hygiene

Keep the bucket ARN, lifecycle rule ids, and versioning state in the provisioning doc; delete test
objects (`s3 rm`) before declaring done so the bucket starts empty with rules already active.
