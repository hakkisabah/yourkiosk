# IAM policy validation and action-name traps

IAM validates a policy at save time and rejects the whole document for one bad token. Lint locally
with `scripts/iam-policy-lint.py` (pulls AWS's own action list) instead of discovering it in the
console.

```bash
./scripts/iam-policy-lint.py path/to/policy.json
# ✓ policy.json: 6 statements, all actions valid
```

## What the validator checks

1. Top-level keys are only `Version` / `Statement` / `Id`, and each statement only
   `Sid|Effect|Action|NotAction|Resource|NotResource|Condition|Principal|NotPrincipal`.
   IAM **rejects unknown keys** — a `"_aciklama": [...]` block kept for humans makes the whole
   policy unsavable. Comments belong in a sibling `.md`.
2. Every `service:Action` exists. `Action: "*"` and `"s3:*"` are fine.
3. ARN shape: S3 ARNs carry **no account segment** (`arn:aws:s3:::bucket/key`); IAM ARNs carry a
   12-digit account or `*`.

## Action names people get wrong

| Wrong | Right |
|---|---|
| `s3:GetBucketLifecycleConfiguration` / `s3:PutBucketLifecycleConfiguration` | `s3:GetLifecycleConfiguration` / `s3:PutLifecycleConfiguration` |
| `s3:HeadObject` | does not exist — HeadObject is authorized as `s3:GetObject` |
| `s3:PutBucketCors` (case) | `s3:PutBucketCORS` / `s3:GetBucketCORS` |
| `s3:PutEncryptionConfiguration` on a fresh bucket | only needed if you actually re-set it; new buckets default to SSE-S3 |
| `cognito-idp:TagResource` when passing `UserPoolTags` | drop the tags or grant the action |

Related CLI-level surprises: `create-user-pool` rejects `AdminCreateUserConfig.UnusedAccountValidityDays`
("use TemporaryPasswordValidityDays in PasswordPolicy instead"), and the CLI has no
`--no-allow-admin-create-user-only` flag — pass the whole shape with `--cli-input-json file://…`.

## Placeholders are invalid, patterns are not

`arn:aws:iam::ACCOUNT_ID:user/...` and `arn:aws:s3:::BUCKET_NAME` fail with
`Invalid ARN Account: … Provide a 12-digit account ID` / invalid-character errors. Any policy handed
to a user must be **paste-ready**:

```json
"Resource": [
  "arn:aws:s3:::myapp-*",
  "arn:aws:iam::*:user/myapp-*",
  "arn:aws:iam::*:policy/myapp-*",
  "arn:aws:iam::*:role/myapp-*"
]
```

This is also better security hygiene than a placeholder: it scopes by naming convention, so the
setup user can only ever touch the app's own resources even if the key leaks.

## Building the action list source (gotcha)

`https://awspolicygen.s3.amazonaws.com/js/policies.js` is `callback({...});` — strip to the first
`=`/`(` and parse JSON. Service keys are **exact names**, and prefix matching silently picks the
wrong service:

- `"Amazon S3"` also prefixes `Amazon S3 Files` (prefix `s3files`).
- `"AWS Identity and Access Management"` prefixes `… Roles Anywhere` (prefix `rolesanywhere`); the
  real key is `"AWS Identity and Access Management (IAM)"`.

Match on the exact key, then keep `StringPrefix` → `Actions`.

## Setup-key policy: what it genuinely needs

Bucket/role/Cognito provisioning from one temporary user:

- `sts:GetCallerIdentity`;
- S3 bucket config (`CreateBucket`, policy/CORS/lifecycle/versioning/public-access-block, encryption +
  ownership **only if** you insist on re-setting defaults), objects (`ListBucket`, `GetObject`,
  `PutObject`, `DeleteObject`) and `ListAllMyBuckets` on `*`;
- IAM on `<app>-*` only: `CreateRole/GetRole/PutRolePolicy/AttachRolePolicy/ListAttachedRolePolicies`,
  `UpdateAssumeRolePolicy` (**easy to forget — trust policies change when pool ids change**),
  `CreateUser/PutUserPolicy/CreateAccessKey`, `DeleteRole/DeleteRolePolicy`, `PassRole`;
- `cognito-identity`: `CreateIdentityPool/DescribeIdentityPool/SetIdentityPoolRoles/
  GetIdentityPoolRoles/UpdateIdentityPool/DeleteIdentityPool`;
- `cognito-idp`: `CreateUserPool/CreateUserPoolClient/DescribeUserPool*`, `AdminCreateUser`,
  `AdminSetUserPassword`, `UpdateUserPoolClient`, `DeleteUserPool*`.

Expect to add 3–5 actions after the first real run; that is normal, not a failure — just add them to
  the file (and re-lint) so the next bootstrap is clean.

## When you cannot change what you already created

Without `iam:UpdateAssumeRolePolicy` an existing role's trust policy is frozen. Do not stall and do
not widen the policy mid-run: create a **new** role with the correct trust document and re-point the
consumer (`set-identity-pool-roles`). Same for identity pools created without providers — create a
fresh pool instead of `UpdateIdentityPool`, and delete the orphan later.
