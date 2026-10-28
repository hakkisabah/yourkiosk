#!/usr/bin/env bash
# CloudWatch alarmlarını kurar (idempotent) — ayrıntı: README.md
#
# Gerekli ortam:
#   AWS_PROFILE ya da AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY (izin listesi README §2)
#   BILDIRIM_EPOSTA   — SNS aboneliği (onay e-postası size gelir)
#   AYLIK_LIMIT_USD   — fatura alarm eşiği (varsayılan 10)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

BILDIRIM_EPOSTA="${BILDIRIM_EPOSTA:-}"
AYLIK_LIMIT_USD="${AYLIK_LIMIT_USD:-10}"
KONU_ADI="${KONU_ADI:-yourkiosk-alarm}"
# SNS ARN'i (hesap kimliği içerir) ÇALIŞMA AĞACINA YAZILMAZ (i5 bulgusu): betik depodan
# çalıştırıldığında `$HERE/.sns-arn` yanlışlıkla commit'lenebiliyordu. Kalıcı kullanıcı
# durum dizinine yazılır; ARN_DOSYASI ile başka yol verilebilir.
DURUM_DIZINI="${XDG_STATE_HOME:-$HOME/.local/state}/yourkiosk"
mkdir -p "$DURUM_DIZINI"
chmod 0700 "$DURUM_DIZINI" 2>/dev/null || true
ARN_DOSYASI="${ARN_DOSYASI:-$DURUM_DIZINI/sns-arn}"
# Eski sürümün çalışma ağacına bıraktığı dosya varsa bir kez taşı (ve sil).
if [[ -f "$HERE/.sns-arn" && ! -f "$ARN_DOSYASI" ]]; then
  mv "$HERE/.sns-arn" "$ARN_DOSYASI"
  echo "not: .sns-arn çalışma ağacından $ARN_DOSYASI yoluna taşındı"
fi
#: S3 istek metrikleri (5xxErrors) ücretsiz değildir: kovada "request metrics" açmak gerekir ve
#: istek başına ücretlenir. Ücretsiz kalmak isteyen S3_ALARM=0 verir (CloudFront 5xx zaten ücretsiz).
S3_ALARM="${S3_ALARM:-1}"
ALARM_ADLARI="fatura-aylik-esik cloudfront-5xx-orani lambda-hatalari"
[[ "$S3_ALARM" == "1" ]] && ALARM_ADLARI="fatura-aylik-esik s3-5xx-orani $ALARM_ADLARI"

# --- BÖLGE (27 Ekim i5 bulgusu) ---------------------------------------------
# CloudFront metrikleri CloudWatch'a YALNIZ `us-east-1`'de yayınlanır (CloudFront küresel bir
# servistir ama metrik uç noktası us-east-1'dir). Alarm `--region` VERİLMEDEN kurulursa
# varsayılan bölgede (ör. eu-central-1) oluşur, orada hiç veri olmadığı için `notBreaching`
# ile SONSUZA KADAR OK kalır — yani ölü alarm. Aynı bölge kuralı --liste/--sil için de geçerli:
# yanlış bölgede sorgularsanız alarm "yok" görünür ve silinmez.
FATURA_BOLGESI="us-east-1"      # AWS/Billing metrikleri de yalnız us-east-1'de
GLOBAL_BOLGE="us-east-1"        # AWS/CloudFront metrikleri yalnız us-east-1'de
BOLGE_ONEKLI_ALARMLAR=("fatura-aylik-esik" "cloudfront-5xx-orani")
VARSAYILAN_BOLGE_ALARMLARI=("s3-5xx-orani" "lambda-hatalari")

#: Bir alarmın kurulduğu bölge: global (us-east-1) metrikler ayrı, diğerleri varsayılan bölge.
alarm_bolgesi() {
  case "$1" in
    fatura-aylik-esik|cloudfront-5xx-orani) echo "$GLOBAL_BOLGE" ;;
    *) echo "" ;;   # boş = AWS varsayılan bölgesi (AWS_REGION / profil)
  esac
}

#: `aws` çağrısına bölge argümanı ekler (boşsa hiçbir şey eklemez).
bolge_arg() {
  local bolge="$1"; shift
  if [[ -n "$bolge" ]]; then
    aws --region "$bolge" "$@"
  else
    aws "$@"
  fi
}

komut_yok() {
  command -v aws >/dev/null 2>&1 || {
    echo "✗ aws CLI bulunamadı. Kurun: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
    exit 2
  }
}

konu_arn() {
  if [[ -f "$ARN_DOSYASI" ]]; then
    cat "$ARN_DOSYASI"
    return
  fi
  local arn
  # KMS (27 Ekim i5 bulgusu, BİLGİ): SNS konusu varsayılan olarak AWS tarafından yönetilen
  # anahtarla şifrelenir; konuya/aboneliğe erişebilen bir hesap anahtarı da kullanabilir.
  # Kendi müşteri anahtarınızla (CMK) şifrelemek isterseniz SNS_KMS_ANAHTAR verin — anahtar
  # politikası SNS'in `decrypt` yapmasına izin vermelidir. Verilmezse kabul edilen risk
  # deploy/cloudwatch/README.md §5'te yazılıdır (metin testi kilitler).
  if [[ -n "${SNS_KMS_ANAHTAR:-}" ]]; then
    arn="$(aws sns create-topic --name "$KONU_ADI" \
      --attributes "KmsMasterKeyId=$SNS_KMS_ANAHTAR" --query TopicArn --output text)"
  else
    arn="$(aws sns create-topic --name "$KONU_ADI" --query TopicArn --output text)"
  fi
  echo "$arn" >"$ARN_DOSYASI"
  echo "$arn"
}

liste() {
  komut_yok
  # NOT: alarm adları "yourkiosk" öneki taşımıyor; --alarm-name-prefix ile listelemek boş dönerdi.
  # Bölge farkındalığı ZORUNLU: global metrik alarmları us-east-1'de, diğerleri varsayılan
  # bölgede. Tek bölgede sorgulamak alarmları "yok" gösterir (i5 bulgusu).
  bolge_arg "$GLOBAL_BOLGE" cloudwatch describe-alarms \
    --alarm-names "${BOLGE_ONEKLI_ALARMLAR[@]}" \
    --query 'MetricAlarms[].[AlarmName,StateValue,MetricName,Threshold]' \
    --output table
  if [[ ${#VARSAYILAN_BOLGE_ALARMLARI[@]} -gt 0 ]]; then
    bolge_arg "" cloudwatch describe-alarms \
      --alarm-names "${VARSAYILAN_BOLGE_ALARMLARI[@]}" \
      --query 'MetricAlarms[].[AlarmName,StateValue,MetricName,Threshold]' \
      --output table
  fi
}

sil() {
  komut_yok
  for ad in $ALARM_ADLARI; do
    bolge_arg "$(alarm_bolgesi "$ad")" cloudwatch delete-alarms --alarm-names "$ad" >/dev/null 2>&1 || true
  done
  if [[ -f "$ARN_DOSYASI" ]]; then
    aws sns delete-topic --topic-arn "$(cat "$ARN_DOSYASI")" >/dev/null 2>&1 || true
    rm -f "$ARN_DOSYASI"
  fi
  echo "✓ alarmlar ve SNS konusu silindi"
}

kur() {
  komut_yok
  [[ -n "$BILDIRIM_EPOSTA" ]] || {
    echo "✗ BILDIRIM_EPOSTA boş — bildirim gitmeyeceği için kurulum yapılmadı." >&2
    echo "  Örnek: BILDIRIM_EPOSTA=yonetici@ornek.com $0" >&2
    exit 2
  }

  local arn
  arn="$(konu_arn)"
  echo "SNS konu: $arn"

  # Abonelik idempotent: aynı e-posta ikinci kez eklenmez.
  aws sns subscribe --topic-arn "$arn" --protocol email --notification-endpoint "$BILDIRIM_EPOSTA" >/dev/null
  echo "→ $BILDIRIM_EPOSTA adresine ONAY e-postası gitti; onaylamadan bildirim gelmez."

  # 1) FATURA (us-east-1 + AWS/Billing; başka bölgede veri GELMEZ)
  bolge_arg "$FATURA_BOLGESI" cloudwatch put-metric-alarm \
    --alarm-name fatura-aylik-esik \
    --alarm-description "yourkiosk: tahmini aylık AWS faturası \$${AYLIK_LIMIT_USD} üstünde" \
    --namespace AWS/Billing \
    --metric-name EstimatedCharges \
    --dimensions Name=Currency,Value=USD \
    --statistic Maximum \
    --period 21600 \
    --evaluation-periods 1 \
    --threshold "$AYLIK_LIMIT_USD" \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$arn"

  # 2) S3 5xx — cihazlar veri çekemiyor demektir (S3_ALARM=0 ise atlanır: bu metrik ücretsiz değil)
  if [[ "$S3_ALARM" == "1" ]]; then
  bolge_arg "" cloudwatch put-metric-alarm \
    --alarm-name s3-5xx-orani \
    --alarm-description "yourkiosk: S3 5xx (cihazlar veri çekemiyor)" \
    --namespace AWS/S3 \
    --metric-name 5xxErrors \
    --dimensions Name=FilterId,Value=EntireBucket \
    --statistic Sum \
    --period 300 \
    --evaluation-periods 2 \
    --datapoints-to-alarm 2 \
    --threshold 1 \
    --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$arn"
  fi

  # 3) CloudFront 5xx oranı (yayın bozuk) — metrikler YALNIZ us-east-1'de: `--region us-east-1`
  #    verilmezse alarm hiç veri görmeyen bir bölgede kalır (27 Ekim i5 bulgusu).
  bolge_arg "$GLOBAL_BOLGE" cloudwatch put-metric-alarm \
    --alarm-name cloudfront-5xx-orani \
    --alarm-description "yourkiosk: CloudFront 5xx oranı %1 üstü" \
    --namespace AWS/CloudFront \
    --metric-name 5xxErrorRate \
    --dimensions Name=DistributionId,Value="${CLOUDFRONT_ID:?CLOUDFRONT_ID gerekli}" Name=Region,Value=Global \
    --statistic Average \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 1 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --alarm-actions "$arn"

  # 4) Lambda hataları (yalnız auth-modu: lambda)
  if [[ "${AUTH_MODU:-cognito}" == "lambda" ]]; then
    bolge_arg "" cloudwatch put-metric-alarm \
      --alarm-name lambda-hatalari \
      --alarm-description "yourkiosk: panel Lambda hataları" \
      --namespace AWS/Lambda \
      --metric-name Errors \
      --dimensions Name=FunctionName,Value="${LAMBDA_ADI:?LAMBDA_ADI gerekli}" \
      --statistic Sum \
      --period 600 \
      --evaluation-periods 1 \
      --threshold 0 \
      --comparison-operator GreaterThanThreshold \
      --treat-missing-data notBreaching \
      --alarm-actions "$arn"
  fi

  echo "✓ alarmlar kuruldu ($ALARM_ADLARI) — hepsi standart çözünürlük: ücretsiz kotanın (10 alarm metriği) içinde"
  echo "  S3_ALARM=0 → S3 istek metriği açılmaz (ücret doğurmaz); CloudFront 5xx alarmı yayın hatasını yine yakalar."
  liste
}

case "${1:-}" in
  --liste) liste ;;
  --sil) sil ;;
  "") kur ;;
  *) echo "kullanım: $0 [--liste|--sil]" >&2; exit 2 ;;
esac
