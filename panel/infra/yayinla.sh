#!/usr/bin/env bash
# Paneli derler ve CloudFront'a yayınlar (tek komut).
#
#   ./panel/infra/yayinla.sh            # derle + yükle + önbelleği temizle
#   ./panel/infra/yayinla.sh --kuru     # yalnız derle, yükleme yapma
#
# Gerekli: `aws` CLI erişimi (kurulum anahtarı veya panel kullanıcısı) + VITE_* değişkenleri (.env.local).
set -euo pipefail

DIZIN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KOK="$(cd "$DIZIN/.." && pwd)"
KOVA="${KOVA:-yourkiosk-veri}"
DIST="${DIST:-EVR6YMP2UVX8A}"
ONEK="${ONEK:-panel/}"
# `less` kurulu olmayan makinelerde AWS CLI sayfalayıcı açmaya çalışıp hata veriyor
# ("Unable to redirect output to pager ... 'less'"). Sayfalayıcıyı tamamen kapat.
export AWS_PAGER=""

KURU=0
[ "${1:-}" = "--kuru" ] && KURU=1

cd "$DIZIN"
echo "=== derleme ==="
NODE_ENV=development npm run build

if [ "$KURU" -eq 1 ]; then echo "(kuru) yükleme atlandı"; exit 0; fi

echo "=== yükleme (varlıklar: 1 yıl önbellek) ==="
aws --no-cli-pager s3 sync dist "s3://$KOVA/$ONEK" --delete --exclude "index.html" \
  --cache-control "public,max-age=31536000,immutable" --only-show-errors

echo "=== index.html (önbelleksiz) ==="
aws --no-cli-pager s3 cp dist/index.html "s3://$KOVA/${ONEK}index.html" \
  --cache-control "no-cache,must-revalidate" --content-type "text/html; charset=utf-8" --only-show-errors

echo "=== önbellek temizliği ==="
aws --no-cli-pager cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --query "Invalidation.{Id:Id,Status:Status}" --output json

echo "=== dağıtım doğrulaması ==="
YEREL_PAKET="$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' dist/index.html | head -1)"
YAYINDA_PAKET="$(curl -fsS -H 'Cache-Control: no-cache' "https://${DAGITIM_ADI:-d308vfb9mn2991.cloudfront.net}/" | grep -o 'assets/index-[A-Za-z0-9_-]*\.js' | head -1 || true)"
if [ -n "$YEREL_PAKET" ] && [ "$YEREL_PAKET" = "$YAYINDA_PAKET" ]; then
  echo "  ✓ yayındaki paket güncel: $YEREL_PAKET"
else
  echo "  ⚠ yayındaki paket farklı (yerel: ${YEREL_PAKET:-?} · yayında: ${YAYINDA_PAKET:-?})"
  echo "    invalidation tamamlanmamış olabilir; 1-2 dakika sonra tekrar kontrol edin."
fi

echo "✓ yayınlandı"
