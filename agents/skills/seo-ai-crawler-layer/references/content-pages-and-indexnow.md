# Content pages, CDN routing and index submission

Depth for the parts that are only needed when you actually wire them up.

## Content module shape

One module per site (e.g. `shared/content/pages.ts`) exporting page records:

```ts
interface ContentPage {
  path: string;          // '/gizlilik', '/rehber/xyz'
  title: string;
  description: string;   // meta description AND the intro paragraph
  updatedAt: string;     // real ISO date -> sitemap lastmod
  noindex?: boolean;
  order?: number;        // sitemap / AI-index ordering
  sections: { heading?: string; paragraphs?: string[]; bullets?: string[] }[];
}
```

Structured sections (not raw HTML, not markdown) let three renderers share one
source with no parser: `renderContentBody` (HTML for the page), `renderInline`
(escape, then `**bold**` / `[text](https://...)`), `renderContentMarkdown`
(for `.md` twins and the AI index).

Wire the same list into: server render → sitemap entries (with `lastmod`) → AI
index section(s) → app route(s). A page added to the list then appears in all
four places with no other edit.

## Routing table for a hybrid static+SSR site

| Path | Origin | Why |
|---|---|---|
| assets (`/assets/*`), default | S3 (OAC) | hashed bundles, cheap |
| `/` | S3 `index.html` | build-time prerendered home, no compute |
| entity pages, `/robots.txt`, `/sitemap*.xml`, `/llms.txt` | render Lambda | per-request content, edge-cached |
| editorial/trust pages | render Lambda (easiest) | avoids the extensionless-key problem |
| everything else | S3 `spa.html` via error responses | SPA routes; `noindex` shell |

If you instead want editorial pages as static files, add a CloudFront Function
(viewer-request) that appends `/index.html` to extensionless URIs, then map both
403 and 404 error responses to the SPA shell.

## IndexNow recipe

1. Key lives in site settings (admin-editable). The render Lambda serves
   `/{key}.txt` from that setting, so no manual file upload and no drift.
2. On content create/update (and item add/remove/reorder), call the endpoint
   `https://api.indexnow.org/indexnow` with
   `{ host, key, keyLocation, urlList }`.
3. **Fire-and-forget**: never make the user's save depend on a third-party
   response. Wrap in try/catch and swallow failures; log at most.
4. Submit only pages that pass your indexability gate — announcing a page you
   also mark `noindex` is a contradictory signal.
5. Cap `urlList` at 10,000 URLs per request; include the `.md` twin if you
   publish one.
6. Google does not participate: for Google the only channels are the `Sitemap:`
   line in robots.txt and Search Console (API for automation).
