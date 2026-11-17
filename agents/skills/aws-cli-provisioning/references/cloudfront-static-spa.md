# CloudFront in front of a private S3 SPA (OAC, no domain)

Goal: `https://dxxxx.cloudfront.net` serves a Vite/SPA build that lives in a **private** bucket, the
bucket stays unreachable directly, and no certificate/domain purchase is needed.

## 1. Origin Access Control

```bash
aws cloudfront create-origin-access-control --origin-access-control-config \
  '{"Name":"<app>-oac","SigningProtocol":"sigv4","SigningBehavior":"always","OriginAccessControlOriginType":"s3"}'
```

Keep the returned `Id` — the origin needs it; there is no `OriginAccessIdentity` any more.

## 2. Distribution config that actually works

`aws cloudfront create-distribution --distribution-config file://cf-config.json` with:

| Field | Value | Why |
|---|---|---|
| `Origins[0].DomainName` | `<bucket>.s3.<region>.amazonaws.com` | REST endpoint, never the website endpoint |
| `Origins[0].OriginPath` | `/panel` | bucket prefix becomes `/`; later routes stay clean |
| `Origins[0].OriginAccessControlId` | the OAC id | |
| `Origins[0].S3OriginConfig.OriginAccessIdentity` | `""` | must be empty when using OAC |
| `DefaultRootObject` | `index.html` | |
| `DefaultCacheBehavior.CachePolicyId` | `658327ea-f89d-4fab-a63d-7e88639e58f6` | managed *CachingOptimized* |
| `ViewerProtocolPolicy` | `redirect-to-https` | http → 301 |
| `CustomErrorResponses` | 403 → `/index.html` 200, 404 → `/index.html` 200 | SPA deep links; S3 answers 403 (not 404) for missing keys in a private bucket |
| `PriceClass` | `PriceClass_100` | cheapest edge set; enough for a few users |
| `HttpVersion` | `http2and3` | |
| `ViewerCertificate` | `{"CloudFrontDefaultCertificate": true, "MinimumProtocolVersion": "TLSv1.2_2021", "SSLSupportMethod": "vip"}` | free `*.cloudfront.net` cert |
| `CallerReference` | unique per call | re-using it silently fails as a duplicate |

## 3. Bucket policy — CloudFront only

```json
{"Version":"2012-10-17","Statement":[{
  "Sid":"CloudFrontRead","Effect":"Allow",
  "Principal":{"Service":"cloudfront.amazonaws.com"},
  "Action":"s3:GetObject",
  "Resource":"arn:aws:s3:::<bucket>/<prefix>/*",
  "Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::<account>:distribution/<dist-id>"}}}]}
```

This is accepted while `BlockPublicPolicy=true` — the principal is a service plus a SourceArn
condition, so it is not a public policy. Never switch to `Principal: "*"` to "make it work".

## 4. Upload with a cache split

```bash
aws s3 sync dist s3://<bucket>/<prefix>/ --delete --exclude index.html \
  --cache-control "public,max-age=31536000,immutable"
aws s3 cp dist/index.html s3://<bucket>/<prefix>/index.html \
  --cache-control "no-cache,must-revalidate"
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
aws cloudfront get-distribution --id <dist-id> --query Distribution.Status   # poll until Deployed
```

Hashed assets get the immutable year; the entry point must be revalidated or users keep an old
bundle after a deploy. `Deployed` typically lands in 1–3 minutes for a new distribution; poll rather
than assume.

Two things that turn this snippet into a deploy script you can trust:

- **Kill the CLI pager.** `create-invalidation` prints a JSON body; the CLI pipes it to `less` and
  dies with `Unable to redirect output to pager ... 'less'` on a machine without a pager, aborting a
  `set -e` script *after* the upload succeeded. Put `export AWS_PAGER=""` at the top of the script
  and pass `--no-cli-pager` on every call.
- **Verify the result, not the exit codes.** Compare the asset hash referenced by the local
  `dist/index.html` with the one the distribution serves (`curl -H 'Cache-Control: no-cache'`); equal
  means the new build is live, different means the invalidation has not landed yet. A pager/exit-code
  failure can leave a script reporting failure after a successful deploy — the hash comparison is the
  only end-to-end evidence.
- **A missing string in the entry bundle does not mean the deploy failed.** Vite code-splits: schema,
  layout and per-view chunks load separately, so a newly added setting name lives in e.g.
  `assets/sema-*.js`, not in `assets/index-*.js`. Grep `dist/assets/` locally first to learn which
  chunk owns it, then fetch that exact file from the CDN — otherwise a good deploy looks broken and
  you go hunting in invalidation that already worked.

## 5. Verification set (all five, real responses)

```bash
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' "$D/"            # 200 text/html
curl -sS -o /dev/null -w '%{http_code}\n' "$D/some/spa/route"             # 200 text/html (fallback)
curl -sSI "$D/assets/index-*.js" | grep -i cache-control                  # immutable
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' "http://…/"     # 301 → https
curl -sS -o /dev/null -w '%{http_code}\n' "https://<bucket>.s3.<region>.amazonaws.com/<prefix>/index.html"  # 403
```

The last one is the point of the exercise: if direct S3 access returns 200, the bucket is public and
the OAC work is cosmetic.

## 6. Follow-ons that bite later

- **Browser at the CloudFront origin writing to S3** (Cognito-authenticated PUT): add
  `https://<dist>.cloudfront.net` to the bucket CORS `AllowedOrigins` before handing over the URL,
  otherwise every upload fails CORS with no server-side trace.
- **Device/data reads from the same bucket — give them their OWN distribution.** A second origin +
cache behavior on the panel distribution is not enough: `CustomErrorResponses` are
**distribution-wide**, so a missing data object returns `403 → /index.html` as **200 + HTML**, and
every client that parses JSON fails with a content-type error instead of a clean 404. A separate
distribution with `OriginPath=/<data-prefix>`, **no** `CustomErrorResponses`, and a *CachingDisabled*
policy (`4135ea2d-6df8-44a3-9df3-4b5a84be39ad`) answers **403** for missing files (S3 masks 404 as 403
under OAC) and can never be confused with the app. Keep expensive-but-static media (images) on a more
specific cached behavior if you want CDN savings without staleness on the JSON.
- Then extend the bucket policy with **one statement per distribution**, each with its own
  `AWS:SourceArn` — two distributions must never be granted through a single wildcard.
- Editing an existing distribution: `get-distribution-config` omits the **`Items` key entirely when
  `CacheBehaviors.Quantity` is 0**, so `cfg["CacheBehaviors"]["Items"]` raises `KeyError`; read with
  `.get("Items", [])`, append, then rewrite `Quantity`. `update-distribution` requires
  `--if-match <ETag>` from that same response, and the change is async — poll `Distribution.Status`
  to `Deployed` before you test, or you debug the old config.
- **Setup permissions**: creating a distribution needs `cloudfront:CreateDistribution`,
  `CreateOriginAccessControl`, `CreateInvalidation`, `ListDistributions`, `GetDistribution*`,
  `UpdateDistribution`, `ListCachePolicies` — all `"Resource": "*"` (CloudFront ARNs are only known
  after creation). Add them to the setup policy file and re-lint, do not hand-edit the console.
