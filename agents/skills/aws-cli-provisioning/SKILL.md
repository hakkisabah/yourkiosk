---
name: aws-cli-provisioning
description: Use when provisioning AWS S3/IAM/Cognito from the CLI.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [aws, s3, iam, cognito, cli, cost, least-privilege]
    category: software-development
    related_skills: [cognito-social-login, spa-api-auth-wiring, aws-cdk-git-deploy-pipeline]
---

# AWS provisioning from the CLI

Standing up real AWS resources (bucket, role, pools) with `aws` + raw API calls, for an app that
lives outside CDK/Terraform. Covers the two things that actually cost time: **policies that AWS
refuses to save** and **cost/security settings applied after the data is already there**.

## When to use

- Creating an S3 bucket / IAM role / Cognito pools for a browser or device app.
- Handing a user an IAM policy to paste into the console (it must save on the first try).
- Auditing a bucket's cost and exposure before writing data into it.
- Any task where an agent is given a temporary "setup" credential.

## Order of work (do not reorder)

### 0. Credential model — decide before touching anything

- **Never root.** A dedicated IAM user (`<app>-setup`) whose policy you write, restricted to
  `<app>-*` resource patterns. The user creates policy + user + access key in the console and puts
  the key in `~/.config/hermes-secrets/<app>.credentials` (0600) — never in chat, never in the repo.
- Say what the **runtime** uses instead (Cognito Identity Pool temporary credentials, or presigned
  URLs). A permanent key must not end up in the browser bundle.
- Announce the endgame up front: **the setup key gets deactivated and deleted** when provisioning
  finishes.
- Also collect at the start: region, bucket name, admin e-mail, and whether pools are wanted.
  Asking later costs a round trip per item.
- **One credentials file per key, selected per command** (`AWS_SHARED_CREDENTIALS_FILE=…/<app>-publish.credentials
  aws s3 cp …`). Never merge keys into `~/.aws/credentials` under guessed profile names; a
  per-operation file makes "which key am I using?" answerable from the command itself.
- **Two credential failures look similar and have opposite owners.** `InvalidClientTokenId` /
  `InvalidAccessKeyId` ("the security token included in the request is invalid") means the KEY is dead
  — deleted, rotated, or a placeholder — so ask for a new one; no policy edit will help. `AccessDenied …
  not authorized to perform: s3:ListBucket` means the key is alive and the policy is narrow: a
  publish-only key that can `PutObject` and not `ListBucket` is working as designed, so **do not
  diagnose it as broken because `aws s3 ls` fails**. Probe with a call the key is supposed to be able
  to make (`sts get-caller-identity` for liveness, `s3api head-object` / a real `s3 cp` for scope).
- **A doc that names a credentials file is a pointer, not a guarantee.** If `docs/AWS-*.md` says to
  export `~/.config/hermes-secrets/<app>.credentials` and that file now holds a dead key, the operator
  follows the doc into `InvalidClientTokenId`. When you find the live key under a different name,
  update the doc in the same change — a correct command with a stale path fails identically to a
  wrong command.

### 1. CLI install without sudo

Use AWS CLI v2 as a static tree under `$HOME` (no root, no package manager):

```bash
mkdir -p ~/.local/awscli && cd ~/.local/awscli
curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscli.zip
python3 -m zipfile -e awscli.zip .        # no unzip needed
chmod +x aws/install
./aws/install -i "$HOME/.local/aws-cli" -b "$HOME/.local/bin" --update
chmod -R u+x "$HOME/.local/aws-cli" "$HOME/.local/bin/aws"   # zipfile drops the exec bit
export PATH="$HOME/.local/bin:$PATH"; aws --version
```

Then pin the identity once per session and confirm it before any write:

```bash
export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/hermes-secrets/<app>.credentials"
export AWS_DEFAULT_REGION=<region>
aws sts get-caller-identity        # account + user ARN; refuse to continue on failure
```

### 2. Write and LINT the policy before the user pastes it

An IAM policy that fails console validation costs a full user round trip and erodes trust in every
later step. Lint first: `scripts/iam-policy-lint.py` (validates against AWS's own action list).

Rules that make it save:

- **No comments, no metadata keys.** IAM rejects unknown fields (`_aciklama`, `notes`). Put
  explanations in a `.md`, never in the JSON.
- **No placeholders in ARNs.** `arn:aws:iam::ACCOUNT_ID:user/...` and `arn:aws:s3:::BUCKET_NAME`
  are rejected (account must be 12 digits or `*`; bucket names must be valid characters). Prefer a
  **naming pattern** (`arn:aws:s3:::<app>-*`, `arn:aws:iam::*:role/<app>-*`) so the policy needs no
  editing and stays scoped.
- Account-level actions (`s3:ListAllMyBuckets`, `sts:GetCallerIdentity`) need `"Resource": "*"` in
  their own statement; bucket-scoped actions do not.
- Keep the file as the single source of truth and re-lint after every denial-driven edit.
- **Grant the maintenance verbs for everything the run creates, not just `Create*`.** A
create-only policy turns the first misconfiguration into "make a duplicate": reconciling a role or
identity pool without `UpdateAssumeRolePolicy` / `UpdateIdentityPool`, or cleaning up without
`DeleteRole` / `DeleteRolePolicy` / `DeleteIdentityPool`, is impossible, so the run leaves orphans
the user has to delete by hand. Include the `Get`/`List`/`Update`/`Delete` companions for the
resource patterns in scope up front; they disappear with the setup key at the end.

Action names and failure shapes: `references/iam-policy-validation.md`.

### 2b. Operational key policies are DERIVED from the scripts that use them

A policy for a long-lived operational key (alarms, backups, publishing) drifts the moment a script
changes. Audit it in both directions instead of reading it:

- **Script → policy.** Map each `<service> <subcommand>` pair the scripts contain to the actions it
  needs (`sns create-topic → sns:CreateTopic`, `sns subscribe → sns:Subscribe`,
  `s3api copy-object → GetObject|GetObjectVersion|PutObject`, `s3api head-object → GetObject`,
  `cloudwatch put-metric-alarm → PutMetricAlarm`, …) and fail the check when the policy does not
  grant one. A missing permission surfaces as a silent `AccessDenied` at the worst time (no alarm
  during the incident), so this direction is a gate, not a report.
- **Policy → script.** Every action in the policy must be either invoked by a script or listed in a
  justified allow-list ("the operator reads the billing metric with this key, see README §2").
  "Might be needed later" is not a justification: an unused verb is blast radius. A compromised
  topic-attribute permission (`SetTopicAttributes`) is enough to repoint notification subscribers, so
  if nothing calls it, delete it; same for `*Tagging` and `ListBucket` companions that nothing uses.
- **Squeeze object resources to the exact keys the script writes.** A backup/restore key that can
  `PutObject` on `<bucket>/prefix/*` can overwrite the panel bundle, published images and settings
  files; a script that rewrites two keys gets a policy with exactly two ARNs. A test should fail if
  the `/*` wildcard comes back.
- **Make the doc summary equal the policy, mechanically.** Compare the `sns:*`/`cloudwatch:*`/`s3:*`
  sets parsed out of the README paragraph against the JSON; a prose summary drifts silently. Actions
  deliberately withheld may be named in the doc with their reason (`sns:Publish` — alarms publish as
  an AWS service, not from this key), and the test should also require that reason sentence to exist.
- **A verification command the key cannot run belongs in the doc.** If the README tells the operator
  to check subscribers with `ListSubscriptionsByTopic` but the key lacks it (by design — subscriber
  e-mail addresses are PII), say so; otherwise the operator "fixes" the key by widening it.

### 3. Bucket — cost and exposure first, data second

Fixed order, each step verified by a read-back:

```bash
aws s3api create-bucket --bucket <name> --create-bucket-configuration LocationConstraint=<region>
aws s3api put-public-access-block --bucket <name> --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket <name> --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket <name> --lifecycle-configuration file://<app>/infra/s3-lifecycle.json
aws s3api put-bucket-cors --bucket <name> --cors-configuration file://<app>/infra/s3-cors.json
```

- `put-bucket-cors` takes **`{"CORSRules": [...]}`**, not a bare array — a bare array fails with the
  misleading `ParamValidation: Invalid JSON`.
- **Two CORS rules, not one:** anonymous devices read (`GET`/`HEAD`, `AllowedOrigins: ["*"]`) while the
  admin panel writes (`PUT`, only the panel's own origins). One rule covering both either blocks the
  panel or lets any origin attempt writes. Put the `put-bucket-cors` call **inside the deploy script**
  so every publish re-applies it, and verify from a device-shaped origin:
  `curl -si -H "Origin: http://127.0.0.1:<port>" <cdn>/<file>.json | grep -i access-control` must show
  `access-control-allow-origin`. Edge nodes keep answering without CORS headers until the deploy's
  invalidation completes, so re-check with `Cache-Control: no-cache` before declaring success.
- **`file://` parameter files are resolved against the CURRENT WORKING DIRECTORY**, not the repo or the
  script's directory. `--cors-configuration file://panel/infra/s3-cors.json` surfaces as
  `Unable to load paramfile …: [Errno 2] No such file or directory` whenever the user runs it from
  `$HOME`. Always build the argument from an absolute path (`KOK="$(pwd)"; file://$KOK/...`) and print
  the resolved path in the error message.
- New buckets already default to **SSE-S3** and **BucketOwnerEnforced**. Do not demand
  `s3:PutEncryptionConfiguration` / `s3:PutBucketOwnershipControls` just to re-set a default; note
  the default instead of widening the setup policy.
- Lifecycle JSON, cost maths, and which storage classes to *avoid*: `references/s3-bucket-cost-setup.md`.

### 4. Pools first, role second (the order is forced)

The role's trust policy needs the **identity pool id** in its `aud` condition, so the pool cannot
come after the role:

1. `cognito-identity create-identity-pool --identity-pool-name <app> --no-allow-unauthenticated-identities \
   --cognito-identity-providers ProviderName="cognito-idp.<region>.amazonaws.com/<user-pool-id>",ClientId=<client-id>,ServerSideTokenCheck=false`
   → note the returned `IdentityPoolId`.
2. `iam create-role` with a trust policy whose `cognito-identity.amazonaws.com:aud` **is that pool
   id**, plus `ForAnyValue:StringLike cognito-identity.amazonaws.com:amr = authenticated`.
3. `iam put-role-policy` — least privilege, prefix-scoped (`<prefix>/*`), Get/Put/Delete only.
4. `cognito-identity set-identity-pool-roles --identity-pool-id … --roles authenticated=<role-arn>`.

Failure shapes to expect (each has one cause):

- `NotAuthorizedException: … does not have identity providers configured` → the pool was created
  **without** `--cognito-identity-providers`. Fixing it needs `UpdateIdentityPool`, which the setup
  policy usually lacks; the cheap path is a **new pool with providers** + a **new role whose `aud`
  is the new pool id** (`CreateRole` + `SetIdentityPoolRoles` only).
- `InvalidIdentityPoolConfigurationException: Check assigned IAM roles` → the role's `aud` does not
  match this pool id (typical after re-creating the pool). Same remedy: new role, new `aud`.
  `UpdateAssumeRolePolicy` is the alternative but is rarely granted to a setup user.
- Both leave an orphan; list them in the cleanup table instead of widening permissions to tidy up
  mid-run.

User-pool CLI quirks: `AllowAdminCreateUserOnly` lives in `AdminCreateUserConfig` (there is no
`--no-allow-admin-create-user-only` flag); do not set `UnusedAccountValidityDays` (rejected — use
`TemporaryPasswordValidityDays` in `PasswordPolicy`); `UserPoolTags` requires `cognito-idp:TagResource`,
so drop tags rather than adding the permission. Full flow: `cognito-social-login`
("Standing up pools from the CLI").

### 5. Verify end to end — including a NEGATIVE test

Be logged in as the app, not as the setup user. For a Cognito-backed SPA the whole chain is
callable over plain HTTPS (no signing, no SDK):

1. `InitiateAuth` (`USER_PASSWORD_AUTH`) → IdToken.
2. `GetId` (`IdentityPoolId` + `Logins`) → IdentityId.
3. `GetCredentialsForIdentity` → temporary AccessKeyId/SecretKey/SessionToken.
4. With those credentials: write/read/delete under the allowed prefix.
5. **Write outside the prefix and assert it is denied.** A green run without this proves nothing
   about the blast radius.

`execute_code` + `urllib` is enough; export the temporary keys into a subprocess env for the
`aws s3` calls and never print them.

### 6. Close the loop

- Write the app's `.env.local` from the real ids (it is git-ignored), run the app's test suite, and
  report the pass count. **Preflight that env file before every build**: a bundle built from the
  example file (`…_XXXXXXXX`, `1111…-5555`, empty ids) deploys successfully and then greets the user
  with the app's own setup screen in production. A tiny validator that rejects placeholder patterns
  and unknown auth-mode values, wired into the deploy script *before* `npm run build`, turns a silent
  live outage into a one-line refusal.
- Record every resource in the provisioning doc: bucket, role ARNs **actually in use**, pool ids,
  client id, admin user, where the admin password file lives (path only).
- Delete what the run left behind (superseded roles, an identity pool created without providers).
  Orphans are the real product of "quick retries"; a table with "in use / leftover" columns keeps
  the cleanup honest.
- Deactivate + delete the setup access key, and confirm `sts get-caller-identity` now fails.
- **Leave a deploy path behind.** Deleting the setup key also deletes your ability to publish again,
  and the next code change will hit `InvalidAccessKeyId` mid-deploy. Create a narrow runtime user in
  the same run — `<app>-publish`: write/delete only under the deploy prefix, `cloudfront:CreateInvalidation`
  on the one distribution, nothing else (it must not be able to touch device data or the identity
  provider). Store it in its own credentials file and select per operation:

  ```bash
  export AWS_SHARED_CREDENTIALS_FILE="$HOME/.config/hermes-secrets/<app>-publish.credentials"
  ./<app>/infra/deploy.sh        # build + sync + invalidate, same script the setup run used
  ```

  Ship the deploy script and the publish policy JSON in the repo so the user can re-run them without
  the agent or the setup key. Make the script pager-proof with `export AWS_PAGER=""` **alone**:
  `--no-cli-pager` exists only in CLI v2, and on v1 it aborts the deploy mid-run with
  `Unknown options: --no-cli-pager` after the uploads already happened (the script looks broken, the
  data is half-published). Then make it self-verifying (compare the asset hash in `dist/index.html` with the one the CDN serves), because
  the person running it will not read its logs.
- **`--only-show-errors` is a high-level `aws s3` flag; `aws s3api …` rejects it**
  (`Unknown options: --only-show-errors`). Those calls usually sit *after* the uploads, so the deploy
  dies halfway and both sides look broken: files are live, the script exited non-zero. Drop the flag
  from `s3api` commands, keep `AWS_PAGER=""` for paging, and make non-load-bearing steps
  (`put-bucket-cors`) warn-and-continue instead of aborting the run.
- **Invalidate the distribution that actually SERVES the artifact, and prove it.** A hard-coded or
  copied distribution id from another stack (data vs panel are always two distributions) sends the
  invalidation to the wrong edge: uploads land, `index.html` keeps its old `last-modified`, and the
  user keeps seeing the previous deploy. Resolve it from the domain the app is served on
  (`aws cloudfront list-distributions --query "DistributionList.Items[?DomainName=='<cdn-host>'].Id"
  --output text`), print the id in the log, and allow an explicit override env var. If lookup fails,
  say "invalidation skipped", never silently reuse a default.
- **Assert a real value from `.env.local`, not just an asset hash.** A bundle built from `.env.ornek`
  has a fresh hash and passes any freshness check while the app greets the user with its setup
  screen. Fetch the served `index.html` → every `assets/index-*.js` it references → assert the
  concrete pool/client id appears (`grep -c`) and the placeholder patterns do not. Match the
  **structural** placeholder shapes (`eu-central-1_XXXX…`, `1111-2222-3333-…`, runs of 20+ `X`), not
  generic words: `ORNEK`/`EXAMPLE` appear legitimately in UI copy, and a false positive blocks a good
  deploy just as expensively as a missed one. Ship that as a
  script the deploy calls at the end, so "deploy succeeded" means "the live bytes are the right ones". When checking that a change really shipped, compare
  hashes or search **every** emitted asset: a lazily-imported module (schema JSON, a heavy view) lands
  in its own chunk, so grepping only the entry bundle reports a false "deploy failed".

### 7. Serve it — CloudFront + OAC (no custom domain needed)

A private bucket has no HTTPS origin of its own; `*.cloudfront.net` gives one for free, with the
bucket still unreachable directly. Create the OAC, point the distribution at the S3 REST endpoint
with an `OriginPath` (`/panel` → bucket `panel/` maps to `/`), and grant read through the bucket
policy with a service principal plus `AWS:SourceArn` — a policy like that still saves while
`BlockPublicPolicy=true` because it is not public. Details, cache-control split, SPA error mapping
and the verification set: `references/cloudfront-static-spa.md`.

**`OriginPath` is PREPENDED to the viewer path.** A prefix the distribution already prepends must not
also appear in the URL: with `OriginPath=/kiosk`, `/match.json` reads `kiosk/match.json` (works) while
`/kiosk/match.json` reads `kiosk/kiosk/match.json` and S3 answers **403 AccessDenied**, not 404. Before
adding a second prefix "so the device reads the right folder", read the origin config and compare the
URL you plan to hand out with the key that actually exists.

**After attaching an OAC, read it back — attaching is not configuring.**
`aws cloudfront get-origin-access-control --id <id>` must show `SigningBehavior: always` (not `never`)
and `OriginAccessControlOriginType: s3`; `never` sends unsigned requests, which the bucket then denies
exactly like a missing statement. Two similarly named controls (`<app>-panel-oac`, `<app>-data-oac`)
exist in practice — confirm the id the origin references is the one you configured, and that the
bucket statement's `AWS:SourceArn` names *this* distribution.

**A 403 from the data path is a bucket decision until proven otherwise.** Check the `server:` header:
`AmazonS3` means the request reached the bucket and the bucket refused it — CORS, invalidation and edge
cache behaviour are all irrelevant at that moment. Print the facts before editing anything:
`scripts/cdn-access-triage.sh <cdn-host> <bucket> <key>` (origin `DomainName`/`OriginPath`/`OAC`/`OAI`,
every policy statement's `Effect`/`Resource`/`AWS:SourceArn`, and a HEAD of the CDN URL vs the bucket
URL). Two traps that keep the guessing going:

- A statement whose `Resource` is `arn:aws:s3:::<bucket>/*` is **not** proof of access — it is usually
  conditioned on one specific distribution's `AWS:SourceArn`, so a second distribution gets 403 while
  the first serves fine. Add a statement per distribution instead of widening the existing one.
- `Allow` is additive but **`Deny` always wins**, so an explicit `Deny` on a prefix survives every
  `Allow` you add. The triage prints `Effect` for exactly this reason; never conclude "policy is fine"
  from the `Allow` lines alone.

When a fix requires a bucket-policy statement that already exists in a slightly different shape, add
it under a distinct `Sid` and delete the stale one — S3 rejects duplicate `Sid` values in one policy.

## Standing rules

- **Cost work happens before the first byte of data** and is shown as a table (setting → what it
  prevents → estimated $/month). If the user asks for this gate, treat it as a hard prerequisite.
- Never print secrets; write them to a 0600 file and hand over the **path**. Session tokens and
  id tokens are secrets too.
- A denied call is information, not a wall: collect the missing action, add it to the policy file,
  re-lint, and tell the user exactly which line changed. Never paper over a security setting with
  "probably default"; check whether AWS now defaults it and say so explicitly.
- **No credentials in your own shell is not permission to guess.** When `sts get-caller-identity`
  fails here and the user has to run the call, ship the read-only triage
  (`scripts/cdn-access-triage.sh`) and ask for its output — do not propose a different cause per turn
  ("the policy is fine, OAC must be missing"). One round trip with facts beats three hypotheses; label
  anything unverified as such.
- Verify every write with a read (`get-public-access-block`, `get-bucket-versioning`,
  `get-identity-pool-roles`, `head-bucket`). `&&`-chained commands hide which step actually failed.
- Anything the user must do by hand goes in a numbered, copy-pasteable block with the console path
  spelled out (`IAM → Policies → Create policy → JSON`), not a prose description.
- **Never put a masked value in a copy-paste block.** A redacted secret rendered as `***` (or any
  `…`) is indistinguishable from a value to a user who copies the block verbatim — it ends up inside
  `.env.local`, the deploy refuses or the app breaks, and the round trip is yours. Use an explicit
  token (`<MQTT_PASSWORD>`, `<ACCOUNT_ID>`), state in one line that it must be filled by hand, and
  keep real identifiers (pool ids, client ids, bucket names) unmasked — they are not secrets. When a
  config file is already corrupted this way, ship a one-flag repair that rewrites **only** the broken
  key (leaving permissions and other lines alone) instead of asking for manual editing.
- **ACM cannot certify a non-AWS endpoint.** ACM certificates are not exportable and attach only to
  ALB / CloudFront / API Gateway, so a self-hosted broker or server on a VPS uses Let's Encrypt
  (HTTP-01, port 80 must be open) with a deploy hook that copies the cert and reloads the service —
  do not accept "I have ACM" as a plan for it. A real subdomain costs one DNS `A` record; `nip.io`
  is only the fallback when no domain exists.
