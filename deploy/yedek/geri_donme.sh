#!/usr/bin/env bash
# YEDEKTEN GERİ DÖNME — S3 sürümlemeden bir nesneyi geri getirir (ve doğrular).
#
# Kullanım:
#   ./geri_donme.sh --kova yourkiosk-veri --anahtar kiosk/lastSystemData.json --liste
#   ./geri_donme.sh --kova yourkiosk-veri --anahtar kiosk/lastSystemData.json --kuru
#   ./geri_donme.sh --kova yourkiosk-veri --anahtar kiosk/lastSystemData.json            # bir önceki sürüm
#   ./geri_donme.sh --kova yourkiosk-veri --anahtar kiosk/lastSystemData.json --surum ABC123
#
# NEDEN copy-object: silinen nesneyi "geri alma" da aynı yolu kullanır — S3'te bir sürümü
# silmek yalnız DELETE işaretçisi koyar; sürüm kimliğiyle kopyalamak, o içeriği YENİ bir
# sürüm olarak yazar (yani mevcut akış bozulmadan geri döner).
set -euo pipefail

KOVA=""; ANAHTAR=""; SURUM=""; KURU=0; LISTE=0; PROFIL_ARG=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kova) KOVA="$2"; shift 2 ;;
    --anahtar) ANAHTAR="$2"; shift 2 ;;
    --surum) SURUM="$2"; shift 2 ;;
    --profil) PROFIL_ARG=(--profile "$2"); shift 2 ;;
    --kuru) KURU=1; shift ;;
    --liste) LISTE=1; shift ;;
    *) echo "bilinmeyen argüman: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$KOVA" && -n "$ANAHTAR" ]] || { echo "✗ --kova ve --anahtar zorunlu" >&2; exit 2; }
command -v aws >/dev/null || { echo "✗ aws CLI yok" >&2; exit 2; }

surumleri_listele() {
  # DİKKAT: --prefix önek eşleşmesidir ("kiosk/veri.json" → "kiosk/veri.json.bak" da gelir);
  # bu yüzden Key tam eşleşmeyle süzülür, yoksa yanlış nesnenin sürümü geri getirilir.
  aws "${PROFIL_ARG[@]}" s3api list-object-versions \
    --bucket "$KOVA" --prefix "$ANAHTAR" --max-items 10 \
    --query "Versions[?Key=='$ANAHTAR'].[VersionId,IsLatest,LastModified,Size]" --output table
}

if [[ "$LISTE" == "1" ]]; then
  surumleri_listele
  exit 0
fi

# Sürüm verilmediyse: en yeni İKİ sürümden, "latest" OLMAYAN (yani bir önceki) seçilir.
if [[ -z "$SURUM" ]]; then
  SURUM="$(aws "${PROFIL_ARG[@]}" s3api list-object-versions \
    --bucket "$KOVA" --prefix "$ANAHTAR" \
    --query "Versions[?Key=='$ANAHTAR' && !IsLatest]|[0].VersionId" --output text)"
  [[ -n "$SURUM" && "$SURUM" != "None" ]] || {
    echo "✗ geri dönülecek eski sürüm bulunamadı (sürümleme kapalı olabilir)." >&2
    echo "  Kontrol: aws s3api get-bucket-versioning --bucket $KOVA" >&2
    exit 3
  }
fi

echo "→ geri getirilecek: s3://$KOVA/$ANAHTAR (sürüm $SURUM)"

# Geri getirilecek sürümün boyutu (doğrulama için)
BEKLENEN_BOYUT="$(aws "${PROFIL_ARG[@]}" s3api list-object-versions \
  --bucket "$KOVA" --prefix "$ANAHTAR" \
  --query "Versions[?Key=='$ANAHTAR' && VersionId=='$SURUM']|[0].Size" --output text)"
echo "→ boyut: $BEKLENEN_BOYUT bayt"

# --- ŞİFRELEME / DEPOLAMA SINIFI (i5 bulgusu) ------------------------------
# NEDEN: `--metadata-directive REPLACE` nesne meta verisini sıfırlar; şifreleme belirtilmezse
# geri getirilen dosya kovanın VARSAYILANI ile yazılır. Kovanın varsayılan SSE'si yoksa veri
# sessizce ŞİFRESİZ kalır (denetimde "eskiden şifreliydi" görünür, gerçeği farklıdır).
# Bu yüzden eski sürümün meta verisi okunur ve birebir uygulanır.
ESKI_META="$(aws "${PROFIL_ARG[@]}" s3api head-object \
  --bucket "$KOVA" --key "$ANAHTAR" --version-id "$SURUM" --output json)"
META_ALAN() {
  printf '%s' "$ESKI_META" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1],'') or '')" "$1"
}
ESKI_SSE="$(META_ALAN ServerSideEncryption)"
ESKI_KMS="$(META_ALAN SSEKMSKeyId)"
ESKI_SINIF="$(META_ALAN StorageClass)"

KORUMA=()
case "$ESKI_SSE" in
  aws:kms) KORUMA+=(--server-side-encryption aws:kms)
           [[ -n "$ESKI_KMS" ]] && KORUMA+=(--sse-kms-key-id "$ESKI_KMS") ;;
  AES256)  KORUMA+=(--server-side-encryption AES256) ;;
  "")      echo "! UYARI: eski sürümde şifreleme bilgisi yok — kovanın varsayılanı uygulanacak" >&2 ;;
esac
if [[ -n "$ESKI_SINIF" && "$ESKI_SINIF" != "STANDARD" ]]; then
  KORUMA+=(--storage-class "$ESKI_SINIF")
fi
echo "→ şifreleme: ${ESKI_SSE:-yok}${ESKI_KMS:+ (kms $ESKI_KMS)} · depolama sınıfı: ${ESKI_SINIF:-STANDARD}"

if [[ "$KURU" == "1" ]]; then
  echo "KURU: aws s3api copy-object --bucket $KOVA --key $ANAHTAR \\"
  echo "       --copy-source \"$KOVA/$ANAHTAR?versionId=$SURUM\" ${KORUMA[*]}"
  exit 0
fi

YENI_ETAG="$(aws "${PROFIL_ARG[@]}" s3api copy-object \
  --bucket "$KOVA" --key "$ANAHTAR" \
  --copy-source "$KOVA/$ANAHTAR?versionId=$SURUM" \
  --metadata-directive REPLACE \
  --content-type "application/json; charset=utf-8" \
  --cache-control "no-store" \
  "${KORUMA[@]}" \
  --query 'CopyObjectResult.ETag' --output text)"

echo "→ yeni sürüm yazıldı (ETag $YENI_ETAG)"

# DOĞRULAMA: boyut + şifreleme (yanlış sürümü geri getirmek sessiz bir hatadır; şifrelemesiz
# geri getirmek de öyle — ikisi de kontrol edilir).
GERCEK_BOYUT="$(aws "${PROFIL_ARG[@]}" s3api head-object \
  --bucket "$KOVA" --key "$ANAHTAR" --query ContentLength --output text)"
YENI_SSE="$(aws "${PROFIL_ARG[@]}" s3api head-object \
  --bucket "$KOVA" --key "$ANAHTAR" --query ServerSideEncryption --output text)"
if [[ "$GERCEK_BOYUT" != "$BEKLENEN_BOYUT" ]]; then
  echo "✗ DOĞRULAMA BAŞARISIZ: beklenen $BEKLENEN_BOYUT, gelen $GERCEK_BOYUT" >&2
  exit 1
fi
if [[ -n "$ESKI_SSE" && "$YENI_SSE" != "$ESKI_SSE" && "$YENI_SSE" != "None" ]]; then
  echo "✗ DOĞRULAMA BAŞARISIZ: şifreleme beklenen $ESKI_SSE, gelen $YENI_SSE" >&2
  exit 1
fi
echo "✓ doğrulandı: $GERCEK_BOYUT bayt · şifreleme ${YENI_SSE:-yok}"

cat <<'NOT'
SONRAKİ ADIM (cihaz tarafı):
  * Cihaz `durum.json`u 30–120 sn içinde okur; geri dönen veri büyük dosya olduğu için
    `lastupdate` damgasını da geri getirmeniz gerekir (dosya değişmediyse cihaz indirmez):
        ./geri_donme.sh --kova KOVA --anahtar kiosk/lastupdate.json
  * Doğrulama: cihazda `tools/canli_test.py` (damga + veri + disk halkaları) ve ekranda
    beklenen kayıt sayısı.
NOT
