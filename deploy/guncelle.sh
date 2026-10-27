#!/usr/bin/env bash
# CİHAZ GÜNCELLEMESİ — imzalı yayın etiketi → arayüz derle → servisi yeniden başlat → SAĞLIK DENETİMİ.
#
# NEDEN SAĞLIK DENETİMİ: etiketten güncelleme başarılı olup arayüz derlemesi patlarsa cihaz bir sonraki
# açılışta BEYAZ EKRAN verir. Bu betik sağlık denetimi başarısızsa önceki commit'e döner.
#
# YETKİ MODELİ (i5 bulgusu): betik ROOT olarak çalışır ama depo `kiosk` kullanıcısınındır.
# Root, kiosk'un YAZABİLDİĞİ betiği çalıştırmamalı (yerel yetki yükseltmesi) ve git, sahibi
# farklı depoda "detected dubious ownership" verir. Bu yüzden:
#   • birim, ROOT'a ait KOPYAYI çalıştırır (`/usr/local/lib/yourkiosk/guncelle.sh`, 0755 root:root),
#   • depodaki her işlem (git/npm/pip/sağlık testi) `runuser -u kiosk` ile AYRICALIKSIZ koşar,
#   • yalnız `systemctl restart` root yetkisiyle yapılır (birim zaten root).
# Kurulum: `sudo install -Dm0755 deploy/guncelle.sh /usr/local/lib/yourkiosk/guncelle.sh`
#
# Kullanım (root ya da sudo):
#   /usr/local/lib/yourkiosk/guncelle.sh              # güncelle
#   /usr/local/lib/yourkiosk/guncelle.sh --kuru       # ne yapacağını göster (hiçbir şey değiştirmez)
#   /usr/local/lib/yourkiosk/guncelle.sh --zorla      # yerel değişiklik olsa da devam et
set -euo pipefail

KOK="${KIOSK_KOK:-/opt/yourkiosk}"
KIOSK_KULLANICI="${KIOSK_KULLANICI:-kiosk}"
KURU=0
ZORLA=0
for arg in "$@"; do
  case "$arg" in
    --kuru) KURU=1 ;;
    --zorla) ZORLA=1 ;;
    *) echo "bilinmeyen argüman: $arg" >&2; exit 2 ;;
  esac
done

cd "$KOK"
log() { printf '%s  %s\n' "$(date '+%F %T')" "$*"; }

# AYRICALIKSIZ ÇALIŞTIRICI: depo işlemleri kiosk kullanıcısı olarak koşar. Böylece git sahipliği
# doğru olur ("dubious ownership" yok), npm/pip önbelleği ve üretilen dosyaların sahibi kiosk olur.
# HOME açıkça verilir; verilmezse npm kökün evine yazmaya çalışır.
kiok() {
  runuser -u "$KIOSK_KULLANICI" -- env HOME="$KIOSK_HOME" \
    PATH="/usr/local/bin:/usr/bin:/bin" "$@"
}

# EV DİZİNİ (i5 bulgusu): güncelleme birimi `ProtectHome=yes` ile koşar → /home erişilemez ve
# BOŞ görünür. `HOME=/home/kiosk` verilirse npm/pip önbellek yazamaz, güncelleme her koşuda
# düşer ve geri alınır. Bu yüzden kiosk kullanıcısının yazabildiği kalıcı bir dizin kullanılır.
KIOSK_HOME="${KIOSK_HOME:-/var/lib/yourkiosk-guncelle}"
if [[ $KURU -eq 0 ]]; then
  mkdir -p "$KIOSK_HOME"
  chown "$KIOSK_KULLANICI:$KIOSK_KULLANICI" "$KIOSK_HOME" 2>/dev/null || true
  chmod 0750 "$KIOSK_HOME" 2>/dev/null || true
fi

# GÜVENLİ GEÇİCİ DİZİN (i5 bulgusu): sabit `/tmp/yourkiosk-canli.log` yolu, /tmp'ye sembolik bağ
# kurabilen yerel kullanıcının root'un rastgele bir dosyayı kesmesine açıktı. mktemp -d 0700
# verir; trap ile temizlenir. Güncelleme günlüğü ayrıca kalıcı dizine (varsa) yazılır.
GECICI="$(mktemp -d "${TMPDIR:-/tmp}/yourkiosk-guncelle.XXXXXX")"
trap 'rm -rf "$GECICI"' EXIT
LOGDIZIN="${KIOSK_LOG_DIZIN:-/var/log/yourkiosk}"
[[ -d "$LOGDIZIN" && -w "$LOGDIZIN" ]] || LOGDIZIN="$GECICI"
# Hata sonrası okunabilsin diye günlük KALICI dizine yazılır; 14 günden eskiler silinir.
CANLI_LOG="$LOGDIZIN/canli-$(date '+%Y%m%d-%H%M%S').log"
[[ "$LOGDIZIN" != "$GECICI" ]] && find "$LOGDIZIN" -maxdepth 1 -name 'canli-*.log' -mtime +14 -delete 2>/dev/null || true

[[ -d .git ]] || { log "✗ $KOK bir git deposu değil"; exit 2; }
id -u "$KIOSK_KULLANICI" >/dev/null 2>&1 || { log "✗ '$KIOSK_KULLANICI' kullanıcısı yok (KIOSK_KULLANICI ile belirtin)"; exit 5; }

# SAHİPLİK ÖN DENETİMİ: beklenmeyen sahip (ör. başka bir yerel kullanıcı) varsa hiç başlamayalım.
SAHIP="$(stat -c '%U' .git 2>/dev/null || echo '?')"
# 26 Ekim i5 bulgusu: eski kapı 'root'u da kabul ediyordu, ama tüm depo işlemleri
# `runuser -u $KIOSK_KULLANICI` ile koşuyor → root'a ait depoda git "detected dubious ownership"
# verir ve status/rev-parse/pull başarısız olur (sessiz yarım güncelleme). Depo sahibi kiosk
# kullanıcısı olmalı; root'a ait depo AÇIKÇA reddedilir ve çözümü yazılır.
if [[ "$SAHIP" != "$KIOSK_KULLANICI" ]]; then
  log "✗ depo sahibi '$SAHIP' — beklenen '$KIOSK_KULLANICI'; güncelleme durduruldu"
  log "  Çözüm: sudo chown -R $KIOSK_KULLANICI: $PWD  (root'a ait depoda git dubious-ownership verir)"
  exit 4
fi

if [[ $ZORLA -eq 0 && -n "$(kiok git status --porcelain)" ]]; then
  log "✗ çalışma ağacı temiz değil — önce elle çözün (ya da --zorla)"
  kiok git status --short | head -20
  exit 3
fi

ONCEKI="$(kiok git rev-parse HEAD)"
log "önceki commit: $ONCEKI"

# --- İMZALI YAYIN ETİKETİ (i5 bulgusu 3) -------------------------------------
# ÖLÇÜLEN: eski satır `git pull --ff-only` ile `main` UCUNU çekip derliyordu. `main`'e yazma
# yetkisi olan ele geçirilmiş bir hesap/token (ya da yanlışlıkla push) doğrudan 600 cihazda
# kod çalıştırıyordu — imza/etiket kapısı yoktu.
#
# EN AZ YETKİYLE ÇÖZÜM: güncelleme yalnız `yayin-*` desenli, ANNOTATED + GPG İMZALI bir
# etiketten yapılır. `git verify-tag` geçmeden derleme/çalıştırma YOK (fail-closed): etiket yok,
# imza yok ya da anahtar yok → güncelleme ATLANIR ve günlüğe açık satır yazılır (sessiz atlama yok).
#
# Anahtar kurulumu (bir kez, cihaz başına):
#   runuser -u kiosk -- gpg --import yayin-anahtari.asc     # yayın imza anahtarının AÇIK anahtarı
ETIKET_DESENI="${KIOSK_YAYIN_ETIKET_DESENI:-yayin-*}"
log "imzalı yayın etiketi aranıyor (desen: $ETIKET_DESENI · origin/main)"
# KURU KOŞU HİÇBİR ŞEYİ DEĞİŞTİRMEZ (i5 bulgusu, 27 Ekim): `git fetch --tags --prune --force`
# yerel etiketleri de günceller/siler, yani --kuru "hiçbir şey değişmez" sözünü tutmuyordu.
# Kuru koşuda fetch ATLANIR; karşılaştırma ELDEKİ yerel etiketlerle yapılır ve çıktıda bunun
# bayat olabileceği açıkça yazılır.
if [[ $KURU -eq 1 ]]; then
  log "KURU: git fetch ATLANDI (yerel etiketler değişmez) — karşılaştırma yerel etiketlerle"
  ETIKET="$(kiok git tag --list "$ETIKET_DESENI" --sort=-creatordate | head -1 || true)"
else
  if ! kiok git fetch --tags --prune --force origin main >/dev/null 2>&1; then
    log "✗ git fetch başarısız (ağ/origin?) — güncelleme yapılmadı, ağaç DEĞİŞMEDİ"
    exit 6
  fi
  ETIKET="$(kiok git tag --merged origin/main --list "$ETIKET_DESENI" --sort=-creatordate | head -1 || true)"
fi

# --- İMZALAYAN BEYAZ LİSTESİ ----------------------------------------------
# ROOT'a ait dosya: kiosk kullanıcısı yazamaz → ele geçirilmiş bir hesap kendi anahtarını
# imzalayan olarak "kaydedemez". Satır başına bir parmak izi (40 hex), `#` yorumları serbest.
# Yol yalnız test/kurulum için ortamdan değiştirilebilir; birim bu değişkeni VERMEZ.
IMZACI_DOSYASI="${KIOSK_YAYIN_IMZACI_DOSYASI:-/etc/yourkiosk/yayin-imzaci}"

#: `git verify-tag --raw` çıktısındaki VALIDSIG satırından BİRİNCİL anahtarın parmak izini döner.
#: (Son alan: alt anahtarla imzalanmışsa birincil anahtarın parmak izi; boş = bulunamadı.)
validsig_parmak_izi() {
  awk '/^\[GNUPG:\] VALIDSIG / {print $NF; exit}' | tr '[:lower:]' '[:upper:]'
}

#: Beyaz listedeki parmak izleri (satır satır). Dosya yok/boşsa çıkış 1 (fail-closed).
beklenen_imzacilar() {
  [[ -r "$IMZACI_DOSYASI" ]] || return 1
  awk '!/^[[:space:]]*#/ && NF {print toupper($1)}' "$IMZACI_DOSYASI"
}

#: Parmak izi beyaz listede mi? Biçim (40 hex) ve liste varlığı da denetlenir.
imzaci_izinli() {
  local fpr="$1" beklenen
  [[ "$fpr" =~ ^[0-9A-F]{40}$ ]] || return 1
  beklenen="$(beklenen_imzacilar)" || return 1
  [[ -n "$beklenen" ]] || return 1
  grep -qx -- "$fpr" <<<"$beklenen"
}

etiket_dogrula() {
  if [[ -z "$ETIKET" ]]; then
    log "✗ origin/main üzerinde '$ETIKET_DESENI' desenli etiket YOK — güncelleme yapılmadı"
    log "  yayın: imzalı etiket atın (git tag -s yayin-YYYYMMDD -m ...) ve push edin"
    return 6
  fi
  if [[ "$(kiok git cat-file -t "refs/tags/$ETIKET" 2>/dev/null || true)" != "tag" ]]; then
    log "✗ $ETIKET ANNOTATED etiket değil (hafif etiket imza taşımaz) — güncelleme yapılmadı"
    return 6
  fi

  # --- İMZALAYANIN KİMLİĞİ (27 Ekim i5 bulgusu 5) ---------------------------
  # ÖLÇÜLEN: `git verify-tag` yalnız "imza GEÇERLİ mi" der, imzalayanın KİMLİĞİNE bakmaz.
  # Anahtar halkası kiosk kullanıcısının yazabildiği $KIOSK_HOME altında olduğu için ele
  # geçirilmiş bir kiosk hesabı KENDİ anahtarını import edip KENDİ etiketini imzalayabiliyordu
  # → kapı "geçerli imza" diyerek açılıyordu.
  #
  # ÇÖZÜM: beklenen imzalayan(lar) BEYAZ LİSTE ile sabitlenir; `git verify-tag --raw` çıktısındaki
  # `[GNUPG:] VALIDSIG <parmak izi> … <birincil parmak izi>` satırının son alanı (birincil anahtar
  # parmak izi) listeyle karşılaştırılır. Liste ROOT'a ait bir dosyadır (/etc/yourkiosk/yayin-imzaci)
  # → kiosk kullanıcısı değiştiremez. Liste yoksa/boşsa FAIL-CLOSED: güncelleme reddedilir.
  local imza fpr
  if ! imza="$(kiok git verify-tag --raw -- "$ETIKET" 2>&1)"; then
    log "✗ $ETIKET GPG imzası DOĞRULANAMADI (imza yok / yanlış anahtar / anahtar kurulu değil)"
    log "  anahtar kurulumu: runuser -u $KIOSK_KULLANICI -- gpg --import yayin-anahtari.asc"
    log "  güncelleme REDDEDİLDİ (fail-closed) — ağaç DEĞİŞMEDİ"
    return 6
  fi
  fpr="$(printf '%s\n' "$imza" | validsig_parmak_izi)"
  if [[ -z "$fpr" ]]; then
    log "✗ $ETIKET imzası geçti ama VALIDSIG parmak izi okunamadı — güncelleme REDDEDİLDİ"
    log "  (git/gpg sürümü --raw çıktısını değiştirmiş olabilir; imzalayan kimliği doğrulanamaz)"
    return 6
  fi
  if ! beklenen_imzacilar >/dev/null; then
    log "✗ imzalayan beyaz listesi yok/okunamıyor: $IMZACI_DOSYASI"
    log "  kurulum: sudo install -d -m0755 /etc/yourkiosk"
    log "           echo 'PARMAK_IZI' | sudo tee $IMZACI_DOSYASI   # 40 haneli, gpg --fingerprint"
    log "  güncelleme REDDEDİLDİ (fail-closed) — ağaç DEĞİŞMEDİ"
    return 6
  fi
  if ! imzaci_izinli "$fpr"; then
    log "✗ imzalayan parmak izi $fpr beyaz listede DEĞİL ($IMZACI_DOSYASI)"
    log "  anahtar halkası kiosk kullanıcısının yazabildiği dizinde; kendi anahtarını ekleyip"
    log "  kendi etiketini imzalamak bu kapıyı AÇMAZ. Yayın anahtarını değiştirdiyseniz listeyi"
    log "  root olarak güncelleyin (sudo $0 --kuru ile doğrulayın)."
    log "  güncelleme REDDEDİLDİ (fail-closed) — ağaç DEĞİŞMEDİ"
    return 6
  fi
  log "✓ imza geçerli · imzalayan beyaz listede: $fpr"
  return 0
}

if [[ $KURU -eq 1 ]]; then
  if etiket_dogrula; then
    log "KURU: git checkout --detach $ETIKET (imza ✓) · npm ci + npm run build (web) · systemctl restart yourkiosk-kiosk"
  else
    log "KURU: imza kapısı geçmedi → gerçek koşuda güncelleme ATLANIR (yukarıdaki satırlara bakın)"
  fi
  exit 0
fi

etiket_dogrula || exit 6

# --- GERİ DÖNÜŞ -------------------------------------------------------------
# NEDEN trap: sağlık denetimi yalnız servis açıldıktan SONRA çalışır; `npm run build` ya da
# `git checkout` bu noktadan ÖNCE patlarsa `set -e` betiği olduğu yerde bırakır ve cihaz yarım
# güncellenmiş ağaçla (beyaz ekran) kalırdı. trap herhangi bir hata satırında geri döndürür.
GERI_DONULDU=0
geri_don() {
  [[ $GERI_DONULDU -eq 1 ]] && return 0
  GERI_DONULDU=1
  set +e
  log "GERİ DÖNÜŞ: $ONCEKI commit'ine dönülüyor"
  kiok git reset --hard "$ONCEKI"
  if [[ -f web/package.json ]]; then ( cd web && kiok npm ci --no-audit --no-fund && kiok npm run build ); fi
  systemctl restart yourkiosk-kiosk.service
  log "✗ güncelleme geri alındı — journal: journalctl -u yourkiosk-kiosk -n 100"
}
trap 'kod=$?; log "✗ hata (satır $LINENO, kod $kod) — geri dönülüyor"; geri_don; exit "$kod"' ERR

log "imzalı etiketten güncelleme: $ETIKET"
kiok git -c advice.detachedHead=false checkout --detach --force "$ETIKET"

log "arayüz derlemesi (web)"
if [[ -f web/package.json ]]; then
  ( cd web && kiok npm ci --no-audit --no-fund && kiok npm run build )
fi

log "Python bağımlılıkları (değiştiyse)"
if [[ -f kiosk/requirements.txt ]]; then
  if [[ -x kiosk/.venv/bin/pip ]]; then
    ( cd kiosk && kiok .venv/bin/pip install -q -r requirements.txt )
  elif command -v pip3 >/dev/null; then
    kiok pip3 install -q -r kiosk/requirements.txt || log "uyarı: pip3 kurulumu başarısız (sistem paketleri kullanılıyor olabilir)"
  fi
fi

log "servis yeniden başlatılıyor"
systemctl restart yourkiosk-kiosk.service
sleep 8

# --- SAĞLIK DENETİMİ -------------------------------------------------------
# 1) servis ayakta mı?  2) canlı akış testi (panel/disk/MQTT halkaları) geçiyor mu?
SAGLIK=0
if ! systemctl is-active --quiet yourkiosk-kiosk.service; then
  log "✗ servis ayakta değil"
  SAGLIK=1
elif [[ -x kiosk/.venv/bin/python && -f kiosk/tools/canli_test.py ]]; then
  # `--sure 15`: MQTT'ye ayrılan bekleme (araçta ayrıştırılıyor).
  # Push KAPALI cihazda MQTT halkası "atlandı" sayılır → çıkış 0 (i5 bulgusu: her gece geri dönüyordu).
  # Ayrıcalıksız koşar: cihazın kendi yerel sunucusuna 127.0.0.1'den bakar, root gerekmez.
  if ! ( cd kiosk && kiok .venv/bin/python tools/canli_test.py --sure 15 >"$CANLI_LOG" 2>&1 ); then
    log "✗ canlı akış testi başarısız — ayrıntı: $CANLI_LOG"
    tail -20 "$CANLI_LOG" || true
    SAGLIK=1
  fi
else
  # i5 bulgusu: bu dal SESSİZCE atlanıyordu → bozuk derleme "başarılı" sayılıyordu.
  # Sağlık denetimi yapılamıyorsa güncelleme BAŞARISIZ sayılır (geri dönülür).
  log "✗ sağlık denetimi yapılamadı: kiosk/.venv/bin/python ya da kiosk/tools/canli_test.py yok"
  log "  (venv kurun: cd kiosk && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"
  SAGLIK=1
fi

if [[ $SAGLIK -ne 0 ]]; then
  geri_don
  exit 1
fi

# BETİK KOPYASI (i5 bulgusu 25.10 19:18): birim /usr/local/lib/yourkiosk/guncelle.sh KOPYASINI
# çalıştırır; kopya kendini OTOMATİK YENİLEMEZ.
#
# NEDEN: kopyayı depodaki dosyadan root olarak yenilemek, kiosk kullanıcısının yazabildiği
# içeriğin root tarafından çalıştırılması demektir (yerel yetki yükseltmesi) — birimin kendi
# yorumunun yasakladığı şey. Ayrıca birim ProtectSystem=full ile /usr'u salt-okunur bağlar,
# yani böyle bir kopyalama üretimde zaten EROFS'a düşer (koruma hiç çalışmaz).
# Doğru yol: betik kopyası DEPLOY adımının parçasıdır → `sudo deploy/kur-guncelle-betigi.sh`.
KOPYA="/usr/local/lib/yourkiosk/guncelle.sh"
if [[ -f "$KOPYA" ]] && ! cmp -s "$KOK/deploy/guncelle.sh" "$KOPYA"; then
  log "uyarı: $KOPYA depodaki sürümden farklı (otomatik kopyalanmaz — yetki yükseltmesi olur)"
  log "       güncellemek için root olarak: sudo $KOK/deploy/kur-guncelle-betigi.sh"
fi

log "✓ güncelleme tamam: $(kiok git rev-parse --short HEAD)"
