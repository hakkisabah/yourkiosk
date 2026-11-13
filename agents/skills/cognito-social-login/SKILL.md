---
name: cognito-social-login
description: Use when wiring Cognito login or social sign-in.
version: 1.0.0
author: agents
license: MIT
metadata:
  agents:
    tags: [aws, cognito, authentication, oauth, cdk]
    related_skills: [ts-monorepo-build-gotchas]
---

# Amazon Cognito login + social federation

## When to Use

- Adding email/password sign-in, sign-up, email confirmation or password reset
  to a browser app backed by an AWS Cognito user pool.
- Adding Google / Facebook / Apple sign-in (federation) to such an app.
- Reviewing a Cognito setup for cost traps (MAU tiers, `AdminGetUser`) or for
  missing PKCE / state validation.

For SPAs on AWS (API Gateway Cognito authorizer + Lambda). Skip
`amazon-cognito-identity-js`/Amplify unless you need SRP: the raw IDP API plus
OAuth code+PKCE is ~250 lines and much smaller in the bundle.

## Pick the flow deliberately

- **Password login, branded form**: `InitiateAuth` with `USER_PASSWORD_AUTH`
  from the browser. The client must set `authFlows.userPassword = true`. The
  password reaches Cognito over TLS; your backend never sees it. Leave
  `userSrp: true` enabled too, so SRP can be adopted later without an infra
  change.
- **Social login**: OAuth 2.0 Authorization Code **+ PKCE on the client**
  (Cognito user pool app clients for SPAs cannot hold a secret). Store
  `code_verifier`, `state` and the return path in `sessionStorage`; verify
  `state` on the callback and refuse the flow on mismatch; exchange the code at
  `https://<domain>/oauth2/token` with `code_verifier` and no `client_secret`.
- **Beware default OAuth flows**: CDK's `addClient` enables `implicit` + `code`
  and example callback URLs when `oAuth` is omitted. Pass `disableOAuth: true`
  when there is no social provider.

## MAU tiers decide your bill — configure federation correctly

- Built-in **social** providers (Google, Facebook, Sign in with Apple, Login
  with Amazon) share the **10,000 free MAU** monthly allowance.
- Users federated through **generic SAML/OIDC** get only **50 free MAU**.
  Adding Google as a generic OIDC provider instead of the `Google` provider
  therefore moves your users into the small bucket.
- Twitter/X is **not** a built-in user-pool provider and is not a real OIDC IdP;
  Sign in with X also needs a billable `GET /2/users/me` call.
- `AdminGetUser` counts the user as an MAU (it is an identity operation).
  List users with `ListUsers` and keep `cognito-idp:AdminGetUser` out of the
  Lambda role.

## Single-admin panel: cost verdict and the no-Cognito fallback

* **Cost verdict to state, not guess:** user pools on Lite/Essentials give **10,000 MAU/month free,
  and that allowance never expires** (not tied to the 12-month AWS free tier); **identity pools are free**
  ("provided at no charge"). MAU counts *distinct* users per month, so one admin logging in 100 times = 1 MAU.
  A single-admin panel is therefore **$0**; charges start only above 10,000 MAU, on the **Plus** tier
  (no free allowance) or on M2M token flows.
* **Make the auth/access layer swappable from day one** — users often ask to delete Cognito later:
  one `VeriKaynagi` interface (`read/write/info/list/delete`) with two implementations
  (direct S3 with temporary STS credentials vs presigned URLs through an API), screens bound to the
  interface, mode picked by one env var.
* **No-Cognito pattern that stays free and credential-free in the browser:** Lambda Function URL
  (`auth-type NONE`; your own layer authorises) + `pbkdf2_sha256$iter$salt$hash` password digest
  (never plaintext) + HMAC-signed **HttpOnly; Secure; SameSite=Lax** session cookie (expiring;
  invalid if tampered) + presigned GET/PUT only for an allow-listed set of object names.
  Guard write races with a conditional read (`IfMatch` → 412 means "warn, do not write"), compare the
  `Origin` header against the panel URL (CSRF) and rate-limit login attempts.
* **Lambda Function URL request bodies cap at 6 MB:** writing a 20-30 MB data file needs the direct-S3
  mode (or multipart presigning). State that limit in the README instead of failing silently.

## Standing up pools from the CLI (no CDK)

Order matters, and two errors here are pure brick walls later:

1. `create-user-pool --cli-input-json file://pool.json` — the CLI has **no**
   `--no-allow-admin-create-user-only` flag (canonical place is
   `AdminCreateUserConfig.AllowAdminCreateUserOnly`), `UserPoolTags` requires
   `cognito-idp:TagResource` (drop the tags when the setup key is scoped), and
   `AdminCreateUserConfig.UnusedAccountValidityDays` is rejected — use
   `PasswordPolicy.TemporaryPasswordValidityDays`.
2. `create-user-pool-client --no-generate-secret --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH
   ALLOW_USER_SRP_AUTH ALLOW_REFRESH_TOKEN_AUTH --prevent-user-existence-errors ENABLED`.
3. `create-identity-pool` **must** name its providers at creation:
   `--cognito-identity-providers ProviderName=cognito-idp.<region>.amazonaws.com/<pool>,ClientId=<client>,ServerSideTokenCheck=false`.
   Without it every `GetId` fails `NotAuthorizedException: … does not have identity providers
   configured`; repairing that afterwards needs `UpdateIdentityPool`, which a scoped setup key
   usually lacks.
4. The role's trust policy `aud` must equal **that identity pool's id**, or
   `GetCredentialsForIdentity` returns `InvalidIdentityPoolConfigurationException`. A trust policy
   is immutable without `iam:UpdateAssumeRolePolicy` — create a **new** role carrying the right
   `aud` and re-point the pool with `set-identity-pool-roles` rather than widening the setup
   policy mid-run (the stale roles become cleanup items).
5. Admin user with no verified sending domain: `admin-create-user --message-action SUPPRESS` then
   `admin-set-user-password --permanent` — generate the password, write it to a 0600 file and hand
   over the **path**, not the value.

Verify the whole chain without an SDK: these endpoints are unsigned, so plain HTTPS works —
`InitiateAuth` (`USER_PASSWORD_AUTH`) → `GetId` with
`Logins: {"cognito-idp.<region>.amazonaws.com/<pool>": IdToken}` → `GetCredentialsForIdentity` →
use the temporary keys for one allowed write **and one denied write outside the prefix**. The
negative case is the only proof that the identity pool's role is actually scoped.

## Identity provider values and console setup

- `identity_provider` values are `Google`, `Facebook`, `SignInWithApple`
  (note: **not** `Apple`).
- In each provider console the authorized redirect URI is
  `https://<prefix>.auth.<region>.amazoncognito.com/oauth2/idpresponse`.
- Apple needs a Services ID as `clientId`, plus teamId, keyId and the `.p8`
  private key content.

## Secrets in CDK

- `UserPoolIdentityProviderGoogle` accepts `clientSecretValue` — pass
  `SecretValue.secretsManager(arn, { jsonField })` and the template carries a
  `{{resolve:secretsmanager:...}}` reference, not the value. CDK emits trailing
  empty segments (`...:client_secret::`); that is normal.
- `UserPoolIdentityProviderFacebook` accepts **only a plain string** secret: use
  the dynamic reference string
  `{{resolve:secretsmanager:<arn>:SecretString:client_secret}}`.
- Never put a client secret in CDK context — context values land in `cdk.json`
  and shell history. Keep an explicit opt-in env flag before accepting an inline
  dev secret, and validate in wording the CDK CLI cannot redact (it masks
  `true` in error text as `***`).

## Errors and validation

- IDP API errors carry the type in **`__type`** (e.g.
  `com.amazonaws...#NotAuthorizedException`), not `name`/`code`. Read `__type`
  first or every error falls through to a generic message.
- Compute/validate the endpoint **outside** the try block that maps network
  failures, or a config error ("region missing") is reported as "server
  unreachable".
- To avoid user enumeration, map `UserNotFoundException` to the **same** message
  as `NotAuthorizedException`.
- Validate `?redirect=` targets: only single-slash app paths. `//host` and
  `https://host` are open-redirect vectors.
- `CfnOutput` ids must not collide with construct ids (`AuthDomain`) —
  "There is already a Construct with name" is the symptom.

## Verification that catches real breakage

Synth-level scenario checks (no AWS account needed): assert IdPs/domain are
absent when social is unconfigured, present when configured, secrets are
`{{resolve:...}}` references rather than plaintext, `identity_provider` names
match, and that missing secret/domain/callback/unknown provider each make
`cdk synth` fail.
