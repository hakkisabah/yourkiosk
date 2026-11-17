#!/usr/bin/env bash
# cdn-access-triage.sh <cdn-host> <bucket> <key> [region]
#
# "The CDN returns 403 for this object" → print the FACTS before changing anything:
#   * which distribution serves the host, its origins, OriginPath, OAC/OAI
#   * every bucket-policy statement (Sid / Effect / Resource / AWS:SourceArn)
#   * HEAD of the CDN URL vs the bucket URL, with the `server:` header that says who refused
#
# Read-only: no put-bucket-policy, no invalidation, no writes.
set -uo pipefail

CDN=${1:?kullanım: cdn-access-triage.sh <cdn-host> <bucket> <key> [region]}
BUCKET=${2:?bucket gerekli}
KEY=${3:?key gerekli}
REGION=${4:-eu-central-1}
export AWS_PAGER=""   # CLI v1 + v2 (`--no-cli-pager` is v2-only and aborts the run on v1)

echo "=== kimlik ==="
aws sts get-caller-identity --query "[Account,Arn]" --output text || {
  echo "✗ AWS kimliği yok (AWS_PROFILE / AWS_SHARED_CREDENTIALS_FILE)" >&2; exit 2; }

echo
echo "=== dağıtım ==="
ID=$(aws cloudfront list-distributions \
      --query "DistributionList.Items[?DomainName=='$CDN'].Id" --output text 2>/dev/null | head -1)
if [ -z "$ID" ] || [ "$ID" = "None" ]; then
  echo "✗ '$CDN' dağıtımı bulunamadı (farklı hesap/alan adı?)" >&2
else
  echo "distribution: $ID"
  aws cloudfront get-distribution-config --id "$ID" \
    --query "DistributionConfig.Origins.Items[].{Id:Id,Domain:DomainName,OriginPath:OriginPath,OAC:OriginAccessControlId,OAI:S3OriginConfig.OriginAccessIdentity}" \
    --output table
  echo "-- cache behaviors (varsayılan + path pattern → origin) --"
  aws cloudfront get-distribution-config --id "$ID" \
    --query "DistributionConfig.{default:DefaultCacheBehavior.TargetOriginId,behaviors:CacheBehaviors.Items[].[PathPattern,TargetOriginId]}" \
    --output json
  echo "NOT: OriginPath istek yolunun BAŞINA eklenir — /x ile /onek/x aynı nesneye gitmez."
fi

echo
echo "=== kova politikası (Effect'i oku: Deny her zaman kazanır) ==="
aws s3api get-bucket-policy --bucket "$BUCKET" --query Policy --output text 2>/dev/null \
  | python3 -c 'import json,sys
p=json.load(sys.stdin)
for i,s in enumerate(p.get("Statement",[]),1):
    pr=s.get("Principal")
    if isinstance(pr,dict): pr=pr.get("Service") or pr.get("AWS") or pr.get("CanonicalUser")
    src=""
    for rule in (s.get("Condition") or {}).values():
        if isinstance(rule,dict) and "AWS:SourceArn" in rule: src=rule["AWS:SourceArn"]
    print(f"{i}. {s.get(\"Sid\",\"-\"):<26} {s.get(\"Effect\",\"?\"):<6} {pr} {s.get(\"Action\")}")
    print(f"   resource={s.get(\"Resource\")}")
    if src: print(f"   SourceArn={src}")
' 2>/dev/null || echo "(politika okunamadı — izin ya da politika yok)"

echo
echo "=== HEAD: CDN vs S3 (server başlığı kimin reddettiğini söyler) ==="
for URL in "https://$CDN/$KEY" "https://$BUCKET.s3.$REGION.amazonaws.com/$KEY"; do
  printf '%-72s ' "$URL"
  curl -sSI --max-time 12 "$URL" 2>/dev/null | tr -d '\r' \
    | awk 'NR==1{s=$0} tolower($1)=="server:"{v=$2} tolower($1)=="x-cache:"{x=$2} END{printf "%s · server=%s · x-cache=%s\n", s, v, x}'
done

echo
echo "Yorum: 'server=AmazonS3' → istek kovaya ulaştı ve kova reddetti (CORS/invalidation ilgisiz)."
echo "      'OriginPath' doluysa URL'de aynı öneki TEKRARLAMAYIN."
