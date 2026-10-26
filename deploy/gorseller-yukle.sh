#!/usr/bin/env bash
# Yayın görsellerini S3'e yükle — panelde tek tek uğraşmadan, tek komutla.
#
# NEDEN: görseller içerik adlıdır (`kiosk/yayin-gorselleri/<sha>.webp`). Aynı görsel iki kez
# yüklenirse aynı anahtara gider (zararsız, üzerine aynı bayt yazılır). Adres değişmediği için
# cihaz önbelleği bozulmaz; CloudFront `immutable` önbelleği güvenle kullanılabilir.
#
# KULLANIM
#   ./gorseller-yukle.sh --kova yourkiosk-veri 1aef5f57384bad53.webp 4c5f059d6d323830.webp
#   ./gorseller-yukle.sh --kova yourkiosk-veri --dagitim d2dnrvsx5eevod.cloudfront.net *.webp
#   ./gorseller-yukle.sh --kova yourkiosk-veri --kuru *.webp      # hiçbir şey yüklemez
#
# ÖN KOŞUL
#   * `aws` CLI (yoksa: `python3 -m pip install --user awscli`)
#   * yazma izni olan profil: `AWS_PROFILE=yourkiosk-yayin` (politika: deploy/README.md §2)
#   * WebP üretimi: `kiosk/tools/gorsel_webp.py <png> --cikti <klasör>`
#
# ÇIKIŞ: yüklenen her nesne için **tam adres** yazılır. Panelde `contentUrl` SALT-OKUNUR (yalnız
# hedefleme düzenlenir; adres düzenlemesi #88) → adresi veri dosyasına yazın (deploy/README.md §2.5).
set -euo pipefail

KOVA=""
ONEK="kiosk/yayin-gorselleri"
DAGITIM=""
KURU=0
DOSYALAR=()

kullanim() {
  sed -n '3,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kova) KOVA="${2:-}"; shift 2 ;;
    --onek) ONEK="${2:-}"; shift 2 ;;
    --dagitim) DAGITIM="${2:-}"; shift 2 ;;
    --kuru) KURU=1; shift ;;
    -h|--help) kullanim 0 ;;
    -*) echo "bilinmeyen seçenek: $1" >&2; kullanim 1 ;;
    *) DOSYALAR+=("$1"); shift ;;
  esac
done

[[ -n "$KOVA" ]] || { echo "✗ --kova zorunlu" >&2; kullanim 1; }
[[ ${#DOSYALAR[@]} -gt 0 ]] || { echo "✗ en az bir .webp dosyası verin" >&2; kullanim 1; }

komut_var() { command -v "$1" >/dev/null 2>&1; }
# `aws` PATH'te yoksa depo venv'inde ara (kiosk/.venv/bin/aws) — sunucuda sistem paketi kurmadan
# çalışabilsin: `kiosk/.venv/bin/pip install awscli`.
AWS=""
if komut_var aws; then
  AWS="aws"
elif [[ -x "$(dirname "${BASH_SOURCE[0]}")/../kiosk/.venv/bin/aws" ]]; then
  AWS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../kiosk/.venv/bin" && pwd)/aws"
fi
if [[ $KURU -eq 0 ]] && [[ -z "$AWS" ]]; then
  echo "✗ aws CLI bulunamadı. Kurun: kiosk/.venv/bin/pip install awscli" >&2
  echo "  (ya da dağıtım paketinizden: sudo pacman -S aws-cli / sudo apt install awscli)" >&2
  exit 1
fi
[[ -n "$AWS" ]] && echo "aws: $AWS"

echo "=== yayın görselleri → s3://$KOVA/$ONEK/ ==="
[[ -n "${AWS_PROFILE:-}" ]] && echo "profil: $AWS_PROFILE"

TOPLAM=0
YUKLENEN=()
for dosya in "${DOSYALAR[@]}"; do
  [[ -f "$dosya" ]] || { echo "✗ dosya yok: $dosya" >&2; exit 1; }
  ad="$(basename "$dosya")"
  # Anahtar KURALI: ad = içerik sha'sı (ilk 16 hex) + .webp. Yanlış adlandırma önbelleği bozar.
  if [[ ! "$ad" =~ ^[0-9a-f]{16}\.webp$ ]]; then
    echo "✗ ad kuralı: <16 hex sha>.webp — '$ad' uymuyor." >&2
    echo "  Üretmek için: kiosk/.venv/bin/python kiosk/tools/gorsel_webp.py <girdi> --cikti ." >&2
    exit 1
  fi
  tur="$(file -b --mime-type "$dosya" 2>/dev/null || echo "?")"
  if [[ "$tur" != "image/webp" ]]; then
    echo "✗ '$ad' WebP değil (algılanan: $tur). Kaynağı PNG/JPEG ise gorsel_webp.py ile çevirin." >&2
    exit 1
  fi
  boyut=$(stat -c%s "$dosya")
  hedef="s3://$KOVA/$ONEK/$ad"
  printf '  %-28s %8s bayt → %s\n' "$ad" "$boyut" "$hedef"
  if [[ $KURU -eq 1 ]]; then
    continue
  fi
  "$AWS" s3 cp "$dosya" "$hedef" \
    --content-type image/webp \
    --cache-control "public,max-age=31536000,immutable" \
    --only-show-errors
  YUKLENEN+=("$ad")
  TOPLAM=$((TOPLAM + boyut))
done

if [[ $KURU -eq 1 ]]; then
  echo "kuru koşu: hiçbir şey yüklenmedi."
  exit 0
fi

echo
echo "yüklendi: ${#YUKLENEN[@]} nesne, $((TOPLAM / 1024)) KB"

if [[ -n "$DAGITIM" ]]; then
  echo
  echo "=== doğrulama (CloudFront) ==="
  for ad in "${YUKLENEN[@]}"; do
    adres="https://${DAGITIM}/${ONEK##kiosk/}/${ad}"
    kod=$(curl -s -o /dev/null -w '%{http_code} %{content_type}' --max-time 20 "$adres" || echo "000 -")
    printf '  %s → %s\n' "$adres" "$kod"
  done
fi

echo
echo "=== adresi veri dosyasına yaz (panelde contentUrl SALT-OKUNUR · düzenleme #88) ==="
echo "  \"Nöbet ve Yayınlar\" ekranı yalnız HEDEFLEME düzenler; adresi panelden giremezsiniz."
echo "  Aşağıdaki tek komut adresi lastSystemData.json içine yazar:"
echo "    kiosk/.venv/bin/python kiosk/tools/gorsel_webp.py --veri lastSystemData.json \\"
if [[ -n "$DAGITIM" ]]; then
  echo "      --url-taban https://${DAGITIM}/${ONEK##kiosk/} --yaz"
else
  echo "      --url-taban https://<dagitim-adresi>/${ONEK##kiosk/} --yaz"
fi
echo "  Yüklenen adresler (elle düzenleme YOK):"
for ad in "${YUKLENEN[@]}"; do
  if [[ -n "$DAGITIM" ]]; then
    echo "    https://${DAGITIM}/${ONEK##kiosk/}/$ad"
  else
    echo "    https://<dagitim-adresi>/${ONEK##kiosk/}/$ad"
  fi
done
echo '  → sonra veri dosyasını yükleyin + damgayı tazeleyin:'
echo '    aws s3 cp lastSystemData.json s3://<kova>/kiosk/lastSystemData.json --cache-control "public,max-age=60"'
echo "  → Cihaz yeni adresi ilk turda indirir (eski PNG önbelleği 7 gün içinde düşer)."
