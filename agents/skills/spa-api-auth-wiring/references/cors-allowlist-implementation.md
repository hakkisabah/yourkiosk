# CORS allowlist implementation (IaC + serverless handler)

Recipe for a SPA calling an API on a different origin, where the allowlist must
feed both the gateway preflight and the handler's real responses.

## 1. One list, two consumers

Keep the canonical list in deploy configuration and pass it down:

```bash
npx cdk deploy --all -c allowedOrigins="https://app.example,https://www.app.example,http://localhost:5173"
```

```ts
// infra bin/app.ts — read the context flag once, pass an array
allowedOrigins: app.node.tryGetContext('allowedOrigins')
  ? String(app.node.tryGetContext('allowedOrigins')).split(',').map(o => o.trim()).filter(Boolean)
  : undefined,
```

In the stack, resolve it once and use it for both purposes:

```ts
const allowedOrigins = props.allowedOrigins?.length ? props.allowedOrigins : DEFAULT_ALLOWED_ORIGINS;

const commonEnv = {
  DATA_BUCKET: props.dataBucket.bucketName,
  ALLOWED_ORIGINS: allowedOrigins.join(','),   // consumed by the handler
};

new apigw.RestApi(this, 'Api', {
  defaultCorsPreflightOptions: {
    allowOrigins: allowedOrigins,               // preflight OPTIONS
    allowMethods: apigw.Cors.ALL_METHODS,
    allowHeaders: ['Content-Type', 'Authorization'],
    maxAge: cdk.Duration.hours(1),
  },
});
```

Export a `DEFAULT_ALLOWED_ORIGINS` (prod domains + `http://localhost:5173`,
`http://127.0.0.1:5173`) in BOTH the stack and the server package so local
`npm run dev` keeps working before anyone supplies the context flag. Never let
`*` be one of those defaults.

## 2. Per-request responder in the handler — not a module constant

A module-level header constant cannot depend on the request, so build the
responder per invocation and let every branch use it:

```ts
export function responderFor(event, allowlist = parseAllowlist(process.env.ALLOWED_ORIGINS)) {
  const allowedOrigin = resolveAllowedOrigin(header(event, 'origin'), allowlist);
  const headers = { 'Content-Type': 'application/json' };
  if (allowedOrigin) {
    headers['Access-Control-Allow-Origin'] = allowedOrigin;
    headers['Vary'] = 'Origin';
  }
  return { ok, fail, allowedOrigin };
}
```

Details that matter:

- Read the `Origin` header case-insensitively (`origin` vs `Origin`).
- Normalise trailing slashes on both the allowlist entries and the incoming
  origin.
- Match exactly: `http://app.example` and `https://evil.app.example` must NOT
  pass an allowlist containing `https://app.example`.
- Return `null` (no header at all) for a non-allowed origin or a missing
  `Origin`. The content still goes out — CORS is a browser rule, not
  authorization — so authorization stays the authorizer's job.
- Keep `parseAllowlist` and `resolveAllowedOrigin` exported and pure so they can
  be unit tested without any AWS involved.
- Declare the responder ABOVE `try` if `catch` also returns a response. Declaring
  it inside `try` type-errors and breaks the error path at runtime — see
  `ts-monorepo-build-gotchas` §9.

## 3. Multi-origin preflight in CDK (verify, don't assume)

Passing several origins to `defaultCorsPreflightOptions.allowOrigins` DOES work,
but not the way it reads. CDK emits:

- a static `Access-Control-Allow-Origin` equal to the FIRST origin, plus
- a response template that overrides that header at runtime for the remaining
  origins:

```
#if($origin == "https://www.app.example" || $origin == "http://localhost:5173")
  #set($context.responseOverride.header.Access-Control-Allow-Origin = $origin)
#end
```

Consequences worth knowing: a comma-joined header is NOT emitted (browsers would
reject it), and the first entry in your list acts as the static default. Confirm
the generated shape rather than trusting that "multiple origins are supported".

## 4. Verification commands

Inspect the synthesized template — this is the only evidence that the wiring
landed:

```bash
npx cdk synth --quiet
node -e "
const t = require('./cdk.out/Api.template.json');
const opts = Object.entries(t.Resources).filter(([k,v]) => v.Type==='AWS::ApiGateway::Method' && v.Properties.HttpMethod==='OPTIONS');
for (const [,v] of opts.slice(0,1))
  console.log(v.Properties.Integration.IntegrationResponses[0].ResponseParameters);
const fn = Object.entries(t.Resources).find(([k,v]) => v.Type==='AWS::Lambda::Function');
console.log(fn[1].Properties.Environment.Variables.ALLOWED_ORIGINS);
"
```

A raw grep for `'*'` in a template is noise — IAM policies legitimately use
`"*"`. Grep the Access-Control response parameters specifically.

Exercise the built handler behaviour directly:

```bash
node -e "
const { responderFor, parseAllowlist } = require('./dist/<pkg>/src/utils/http.js');
for (const origin of ['https://app.example','https://evil.example', undefined])
  console.log(origin ?? '(none)', responderFor({ headers: origin ? { origin } : {} }, parseAllowlist()).ok({}).headers);
"
```

Expected: the allowed origin echoed with `Vary: Origin`; no ACAO key for the
foreign origin and for the missing `Origin`.

## 5. Unit tests worth having

- allowed origin echoed, header name case-insensitive
- foreign origin → no ACAO, and `allowedOrigin === null`
- subdomain and protocol variants rejected
- missing `Origin` → no ACAO
- error responses carry the same policy as success responses
- `Access-Control-Allow-Credentials` is never present
- default allowlist contains no `*`
