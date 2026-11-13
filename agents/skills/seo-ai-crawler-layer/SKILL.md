---
name: seo-ai-crawler-layer
description: Use when making SPA pages crawlable for search and AI.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [seo, adsense, robots, sitemap, llms-txt, cloudfront]
    related_skills: [cognito-social-login]
---

# SEO and AI-crawler layer for a JS-rendered site

## When to Use

- Organic traffic is the goal and public pages are client-rendered (Vue/React SPA).

Depth: `references/content-pages-and-indexnow.md` — content-module shape, the
CloudFront behavior/route table, and the IndexNow submission recipe.
- AdSense was rejected, or will be, with "low value content".
- Someone asks about `llms.txt`, AI crawler robots rules, or sitemap submission.

## Diagnose before choosing tools

Fetch a public page as the server returns it and count visible text:
`curl -s https://site/c/slug | wc -c`, and look for an empty mount node
(`<div id="app"></div>`). If the body has no text, crawlers see nothing.

- Google renders JS but slowly; other engines poorly.
- **AdSense review crawlers read plain text only** — script-rendered content
  reads as a blank page. This makes server-rendered HTML a prerequisite for
  approval, not a nice-to-have.
- Framework migration (Nuxt/Next) is one answer, but not the cheapest one:
  render only the public routes and keep the SPA for authenticated ones.

## Rendering layout that works (and why)

- **Static/known content → prerender at build time** into the S3 `index.html`.
  No runtime cost, best TTFB.
- **Per-entity pages (e.g. /c/:slug) → server render** behind CloudFront, with
  `Cache-Control: public, s-maxage=600, stale-while-revalidate=86400` so the
  CDN is the cache. Only cache misses run compute.
- **SPA fallback must NOT be the homepage HTML.** Serving the prerendered home
  page for `/login`, `/admin` etc. returns the home canonical for many URLs →
  duplicate content. Ship a separate `spa.html` shell carrying `noindex` and
  no content, and point the CloudFront error responses at it.
- Emit the SPA's hashed script tag in the rendered HTML (or read the built
  `index.html` from the origin bucket) so hydration works and asset hashes are
  never duplicated by hand.
- **Editorial/trust pages (About, Contact, Privacy, Terms, guides) need a
  serving decision.** Unextensionless paths like `/hakkinda` do NOT resolve to
  `hakkinda/index.html` on an S3 REST origin — with OAC that returns 403 and
  your noindex SPA fallback serves instead, so the page never gets indexed.
  Either render these paths in the SAME server-render Lambda and route them
  there with CloudFront behaviors, or add a viewer-request CloudFront Function
  that rewrites `/{path}` to `/{path}/index.html` for pre-built static files.
- **Keep page content in ONE module** (e.g. `shared/content/pages.ts`) that
  feeds the server render, the app view, the sitemap and the AI index. Then
  adding a page registers it everywhere at once, and the crawler can never see
  different text than the user (which is what makes cloaking accusations land).
- A page rendered only server-side still needs an app route: if the SPA mounts
  and finds no matching route, the user sees your 404 view while the crawler
  read real content. Add the route and render the same shared content.
- Content parity matters: render the same content users see. Serving crawlers
  something different is cloaking.

## Quality gate: protect the whole domain

Mass thin UGC pages dilute site quality and can sink both rankings and an
AdSense application. Decide indexability in ONE function and reuse it for the
page's `robots` meta, the sitemap and any AI index:

- visibility is PUBLIC, enough active items, non-trivial title.
- Failing pages: return 200 but `noindex,follow`, exclude from sitemap.
- PRIVATE resources: return **404** (do not confirm existence). UNLISTED:
  200 + `noindex` — "reachable but not listed" is exactly what unlisted means.
- Enforce the gate at write time (write/delete an index marker on save) so the
  sitemap never contradicts the page's own `noindex`, and sitemap generation is
  a cheap LIST rather than a full-table scan of documents.
- **Apply the same "substantive or not indexed" test to your own editorial
  pages**, and lock it with a test that asserts a minimum word count per page.
  When that test fails, ADD CONTENT — never lower the threshold to make it pass;
  thin marketing copy is exactly what the AdSense rejection is about.
- Trust pages (About/Contact/Privacy/Terms) are a review requirement, not
  decoration: write them against what the system actually does (which auth
  provider, what is stored, how deletion works) rather than generic boilerplate.
  Flag them for legal review instead of inventing commitments.

## Hard facts that change the plan

- **Sitemap ping is dead**: Google retired it in 2023 (404), Bing in 2022 (410).
  Submit via a `Sitemap:` line in robots.txt and Search Console (API for
  automation).
- **IndexNow covers Bing, Yandex, Naver, Seznam, Yep, Amazon — not Google.**
  It submits individual URLs, not sitemaps.
- **`changefreq` and `priority` are ignored** by both major engines: omit them.
  `lastmod` must be genuinely accurate (never the sitemap generation time).
- Sitemap limits: 50,000 URLs / 50 MB per file → use a sitemap index beyond that.
- **`llms.txt` is a proposal (llmstxt.org v2), not a ratified standard**, and as
  of early 2026 no major provider has confirmed consuming it. Ship it cheaply
  alongside the sitemap; do not treat it as a ranking lever. Spec: H1 site name
  (only required part), blockquote summary, H2 sections of
  `- [name](url): description`. `llms-full.txt` is a community convention, not
  part of the spec. v2 also suggests a markdown twin per page plus
  `rel="alternate" type="text/markdown"` and `rel="describedby"`.
- **`Google-Extended` is a product token, not a crawler**, and does not affect
  Search or AI Overviews. AI Overviews run on normal Googlebot; control them
  with `nosnippet`/`data-nosnippet`/`max-snippet`/`noindex`.
- Separate **retrieval** bots (`OAI-SearchBot`, `ChatGPT-User`,
  `Claude-SearchBot`, `Claude-User`, `PerplexityBot`, `Perplexity-User`,
  `Amazonbot`, `Applebot`) from **training** bots (`GPTBot`, `ClaudeBot`,
  `Google-Extended`, `Applebot-Extended`, `Meta-ExternalAgent`, `CCBot`).
  Blocking retrieval removes you from AI answers; blocking training only
  affects model weights. List `Googlebot` in its own group so a later `*` change
  can never block it.

## Rendering user data server-side safely

- Escape everything (title, description, item names) — it is stored XSS
  otherwise, and JSON-LD needs `<` escaped (`\u003c`) so a payload cannot break
  out of the `<script type="application/ld+json">` block.
- Allow only `http`/`https` hrefs; reject `javascript:`, `data:`, `vbscript:`.
  Print such items as text, not links.
- Mark user-supplied outbound links `rel="nofollow noopener"`.
- For TRUSTED author-written content, still escape first and apply a tiny inline
  syntax (`**bold**`, `[text](https://...)`) AFTER escaping. That makes `v-html`
  in the app view safe by construction and keeps one renderer shared by server,
  app and markdown output.
- Write prose in non-English languages carefully inside single-quoted TS/JS
  strings: Turkish suffixes (`sitemap'e`, `Türkiye'den`) break the file with an
  unterminated-string error. Escape the apostrophe (`\'`) or move the copy into
  a data file with a template literal, and expect this repeatedly when the
  product copy is not English.

## Infra gotchas

- CloudFront → Lambda Function URL: use OAC with `authType: AWS_IAM` so the URL
  cannot be called directly to bypass the CDN and its cache.
- With **S3 + OAC, missing keys return 403, not 404** — the SPA fallback needs
  both error codes mapped, or deep links show an error page.
- Put the origin-supplied `Cache-Control` to work with a custom cache policy
  (`minTtl: 0`), and keep the CDN as the cache layer instead of relying on
  framework-level caches that are per-instance on Lambda.
- Viewer-request rewrite (cloudfront-js-2.0) details that matter: associate it
  with the **default behavior only** — attaching it there leaves the API/sitemap/
  entity behaviors untouched. Decide by the LAST path segment containing a dot
  (`/assets/x.js` untouched) and append `/index.html` otherwise. Unbuilt SPA
  routes still work because the rewritten key is missing → 403 → `spa.html`
  fallback, so the rewrite cannot break client-side routing.
- Prerender SPA-shell pages that have their own component but deserve real meta
  (`/register`, `/login`) into `dist/<path>/index.html`, with `/login` marked
  `noindex`. Otherwise they are served by the noindex fallback and inherit the
  homepage's title and canonical.

## Verification that catches real breakage

- Assert rendered HTML contains `<h1>`, the entity's links, canonical and
  JSON-LD, and that the SPA bundle tag survived injection.
- Assert thin/private entities are absent from the sitemap **and** carry
  `noindex`, and that robots.txt lists `Googlebot` without a site-wide disallow.
- Assert generated-text files by LINE, not by substring: `not.toContain('Disallow: /')`
  also matches `Disallow: /api/` and silently inverts the meaning of the check.
  Match `'Disallow: /\n'` or split into lines before asserting.
- Assert the prerender step FAILS the build when the produced `index.html` has
  no `<h1>` — a silently unprerendered build ships a blank homepage.
- Pitfall: `<!--marker-->` written inside an HTML comment makes it a nested
  comment, which fails Vite's parse5 with `parse5 error code nested-comment`.
  Describe markers in prose instead.
- Pitfall: in tests, factories that give every fixture the same `id` silently
  collapse Map-backed in-memory repositories to one record; derive the id from
  the unique field (e.g. slug).
- Pitfall: an env/mode-dependent component test (e.g. a dev-only ad placeholder)
  can fail once in a full parallel run and pass in isolation — re-run before
  "fixing" it, and pin the env with `vi.stubEnv` rather than chasing the flake.
- Pitfall: adding a content loop that pushes to a `checks`/results array
  declared LATER in the script is a runtime `ReferenceError` under `const` (TDZ)
  — declare the collector before the first writer.
