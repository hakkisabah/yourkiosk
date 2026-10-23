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
DAGITIM_ADI="${DAGITIM_ADI:-d308vfb9mn2991.cloudfront.net}"
# DİKKAT: önceki varsayılan EVR6YMP2UVX8A VERİ dağıtımıydı → panel önbelleği hiç temizlenmiyordu.
DIST="${PANEL_DIST:-}"
ONEK="${ONEK:-panel/}"
# `less` kurulu olmayan makinelerde AWS CLI sayfalayıcı açmaya çalışıp hata veriyor
# ("Unable to redirect output to pager ... 'less'"). Sayfalayıcıyı tamamen kapat.
export AWS_PAGER=""      # v1 + v2 uyumlu sayfalayıcı kapatma (`--no-cli-pager` YALNIZ v2'de var)

KURU=0
[ "${1:-}" = "--kuru" ] && KURU=1

cd "$DIZIN"
echo "=== .env.local denetimi ==="
python3 "$DIZIN/infra/env_denetle.py" || { echo "✗ yayın durduruldu: .env.local yer tutucu/eksik"; exit 1; }

echo "=== derleme ==="
NODE_ENV=development npm run build

if [ "$KURU" -eq 1 ]; then echo "(kuru) yükleme atlandı"; exit 0; fi

echo "=== AWS kimliği ==="
if ! aws sts get-caller-identity --query Account --output text 2>/tmp/aws-kimlik.log; then
  echo "✗ AWS kimliği yok — yayın durduruldu." >&2
  echo "  ~/.aws/credentials ya da AWS_PROFILE ayarla (yayın anahtarı: docs/AWS-KURULUM.md §10)" >&2
  sed -n '1,3p' /tmp/aws-kimlik.log >&2
  exit 1
fi



echo "=== yükleme (varlıklar: 1 yıl önbellek) ==="
aws s3 sync dist "s3://$KOVA/$ONEK" --delete --exclude "index.html" \
  --cache-control "public,max-age=31536000,immutable" --only-show-errors

echo "=== index.html (önbelleksiz) ==="
aws s3 cp dist/index.html "s3://$KOVA/${ONEK}index.html" \
  --cache-control "no-cache,must-revalidate" --content-type "text/html; charset=utf-8" --only-show-errors

echo "=== CORS (cihazlar: GET/HEAD her origin · panel: PUT) ==="
# Kiosk tarayıcısı 127.0.0.1'den CloudFront'a istek atar → CORS şart. Eksikse data okunamaz
# ("match.json okunamadı"). Kural her yayında tazelenir.
if [ -f "$KOK/panel/infra/s3-cors.json" ]; then
  # NOT: s3api `--only-show-errors` kabul etmez (yalnız `aws s3 ...` alır); CORS kritik olmadığı
  # için hata yayını durdurmaz, uyarı basar.
  if aws s3api put-bucket-cors --bucket "$KOVA" \
      --cors-configuration "file://$KOK/panel/infra/s3-cors.json"; then
    echo "  ✓ CORS uygulandı"
  else
    echo "  ⚠ CORS uygulanamadı (yayın devam ediyor; cihazlar CORS'a muhtaç değil)" >&2
  fi
fi

if [ -z "$DIST" ]; then
  DIST="$(aws cloudfront list-distributions \
      --query "DistributionList.Items[?DomainName=='$DAGITIM_ADI'].Id" --output text 2>/dev/null | head -1)"
  if [ -z "$DIST" ] || [ "$DIST" = "None" ]; then
    echo "⚠ panel dağıtımı bulunamadı ($DAGITIM_ADI) — invalidation atlandı (PANEL_DIST=... verin)"
    DIST=""
  fi
fi

echo "=== önbellek temizliği${DIST:+ (dağıtım $DIST)} ==="
if [ -n "$DIST" ]; then
  aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
    --query "Invalidation.{Id:Id,Status:Status}" --output json
fi

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

echo "=== canlı doğrulama ==="
python3 "$DIZIN/infra/yayin_dogrula.py" --adres "https://$DAGITIM_ADI/" || {
  echo "✗ CANLI DOĞRULAMA BAŞARISIZ — panel yanlış derlenmiş görünüyor (yukarıdaki maddelere bak)" >&2
  exit 1
}
