# Data-plane cost model for a polling fleet

Use when deciding — or justifying — **how devices GET their data**: a static object behind a CDN, a
per-request compute endpoint (Lambda Web Functions, a serverless API, an ALB), or a push channel.
Also use it when someone proposes a new AWS primitive and asks "does this help us?".

Answer with a table: **$/month per device, at three fleet sizes**, assumptions named in the same
message. "Serverless is cheaper at scale" is not an answer; at fleet sizes below a few thousand it
is frequently false.

## Inputs to read from the code, not from the doc

The cadence constants decide everything and docs go stale. Grep them:

```bash
cd <project> && grep -rnE 'YOKLAMA|POLL|DAMGA|REFRESH|INTERVAL' --include=*.py --include=*.ts . | grep -i ms
```

Then per device per cycle: how many requests (one manifest = 1; stamp + trigger + command marker =
3), payload size of each (a 40-byte stamp and a 260 KB full document differ by 10,000×), and how
often the full document is actually fetched (usually "on stamp change", ~1–2×/day).

## Prices (read from AWS's own pricing pages; re-check before quoting to a user)

| Item | Price |
|---|---|
| CloudFront HTTPS request | $0.0120/10k (EU/Türkiye), $0.0100/10k (US) |
| CloudFront free tier | 10 M requests + 1 TB transfer out per month |
| CloudFront data transfer out | $0.085/GB after the first TB |
| CloudFront cache invalidation | first 1,000 paths/month free |
| Lambda Web Functions — requests | $0.30 per million |
| Lambda Web Functions — active CPU | $0.0000276944 per vCPU-second |
| Lambda Web Functions — memory | $0.0000036667 per GB-second **for the environment's whole lifetime** |
| API Gateway REST (compare before quoting) | confirm current list price; it is priced per request, not per active CPU |

## Formula

```python
SEC_MONTH = 30*24*3600
istek   = cihaz * (86400/aralik_sn) * 30          # one request per cycle
veri_gb = (istek*kb_kucuk + tam_istek*kb_tam)/1024/1024
cf  = max(0, istek-10_000_000)*1.15/1e6 + veri_gb*0.085
env = max(1, int(cihaz/aralik_sn/64) + 1)          # default maxConcurrencyPerEnvironment = 64
wf  = istek*0.30/1e6 + istek*(cpu_ms/1000)*0.0000276944 + env*env_gb*SEC_MONTH*0.0000036667
```

## Measured example (600–6,000 devices, 512 MB environment, 10 ms active CPU/request)

| devices | interval | requests/mo | static CDN | per-request compute | delta |
|---|---|---|---|---|---|
| 600 | 120 s | 13.0 M | $4.21 | $12.23 | +8.01 |
| 600 | 30 s | 51.8 M | $49.06 | $34.66 | −14.40 |
| 2,000 | 120 s | 43.2 M | $40.88 | $29.68 | −11.21 |
| 2,000 | 30 s | 172.8 M | $190.35 | $109.20 | −81.15 |
| 6,000 | 120 s | 129.6 M | $145.65 | $79.52 | −66.12 |
| 6,000 | 30 s | 518.4 M | $594.06 | $318.10 | −275.96 |

CPU sensitivity at 600 devices / 120 s: 5 ms → $10.43, 10 ms → $12.23, 30 ms → $19.41, 80 ms → $37.35.
Once requests are cheap, the CPU-per-request term is the bill.

## What actually decides it

- **The free tier hides the crossover.** 600 devices at 120 s is 13 M requests, so 10 M are free; the
  same fleet at 30 s is 52 M and the free tier is noise. A comparison done at list price without the
  free tier overstates the CDN by ~3× at small fleet sizes.
- **Per-request compute bills memory for the environment's LIFETIME, idle included.** "Scales to
  zero" only helps a fleet that goes quiet; devices polling every 30–120 s never let it. One 512 MB
  environment kept warm 24/7 is ≈ $4.75/month of memory before a single request.
- **You lose the edge cache.** Every poll now reaches compute; static objects are collapsed at the
  edge and are free to serve. Add the origin CPU this implies at your cadence, not at the demo's.
- **Long-lived connections are the expensive variant.** 600 persistent SSE/WebSocket clients at the
  default 64 concurrent per environment ≈ 10 environments 24/7 ≈ $47/month of memory alone — more
  than the whole static data plane — and LTE devices reconnecting after a drop create a reconnect
  storm. A self-hosted broker writing one small local file per push is the cheap lane.
- **Runtime and platform cost.** Lambda Web Functions is Node.js only; a Python service cannot move.
  A new deploy surface (revisions, endpoints, traffic weights, no CDK L2 yet → hand-written
  CloudFormation) is operational cost that does not appear in the table.

## Default recommendation shape

1. Device read path stays a static object on a CDN with one manifest per cycle; push (if anything)
   is a broker that only writes a local trigger file on the device.
2. Per-request compute is a candidate for the **write** path (a validated API in front of the bucket
   instead of handing browsers an identity-pool credential) and for other services in the account —
   not for the device read path below ~2,000 devices.
3. Refuse a data-plane migration whose modelled saving is a few dollars a month at the current fleet:
   one new deploy surface and a cold-start path cost more attention than that.
4. Whatever you recommend, give the table, the assumptions, and the two decisions you did **not**
   take (cost, and what would flip the answer).

## Traps

- Quoting a per-device figure for one cadence when the code ships several (poll interval when push is
  connected vs when it is not) — price the worst case and say which one it is.
- Comparing request prices while ignoring that the manifest collapsed three documents into one; the
  "cheaper" plane wins on a request count that no longer exists.
- Treating a data-plane swap as a code change: it re-opens publish→stamp→trigger→cache ordering,
  offline cold start and both runtimes. Price the migration, not only the steady state.
