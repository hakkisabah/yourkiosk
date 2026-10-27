#!/usr/bin/env bash
# nobetci-bakim.sh — nöbetçiyi KENDİNİ ONARIR hale getirir. sudo YOK, `git pull` YOK.
#
# NEDEN VAR (26 Ekim, i5 gerçek arızası):
#   · i5'te `git pull` çalışmıyordu: .git/config içinde onlarca `[branch "..."]` bölümü vardı ve
#     dalın izlediği uzak dal başka bir dala bakıyordu → "There is no tracking information".
#   · Nöbetçi servisi İNSAN deposundan çalışıyordu; yani kod güncellemesi için insanın elle pull
#     yapması gerekiyordu. Yapılamayınca makine ESKİ kodu (bellek tavanı olmayan sürümü) çalıştırmaya
#     devam etti ve node `FatalProcessOutOfMemory` ile core dump üretti.
#
# ÇÖZÜM (bu betik): servis artık makineye ait AYRI bir klondan çalışır
#   ~/.local/share/yourkiosk-nobetci/depo   (origin/main'e `reset --hard` ile çekilir)
# İnsan deposunun dalı/yerel değişiklikleri NE okunur NE değiştirilir → pull sorunu kökten biter.
# Klonun içindeki nöbetçi kendini günceller (nobetci.py --guncelle): yeni kod geldiğinde kendini
# yeniden başlatır. Yani bu betik makinede SON kez elle çalıştırılan şeydir.
#
# KULLANIM
#   bash otomasyon/betik/nobetci-bakim.sh i5                 # kur/onar + canlı bellek tavanı
#   bash otomasyon/betik/nobetci-bakim.sh i3 --kuru          # ne yapacağını göster (değiştirmez)
#   bash otomasyon/betik/nobetci-bakim.sh i5 --dal <dal>      # İZLENEN DAL (varsayılan main)
#   bash otomasyon/betik/nobetci-bakim.sh i5 --yeniden-baslat # ayrıca servisi hemen yeniden başlat
#   bash otomasyon/betik/nobetci-bakim.sh i5 --sessiz        # ajan oturumundan: kısa çıktı
#
# TEK SATIR KURULUM (depo eski/bozuk olsa bile çalışır — pull/checkout GEREKMEZ):
#   git -C ~/projeler/yourkiosk fetch origin main && \
#     git -C ~/projeler/yourkiosk show origin/main:otomasyon/betik/nobetci-bakim.sh | bash -s -- i5
set -euo pipefail

UNIT_ADI="yourkiosk-nobetci.service"
DURUM_KLASORU="$HOME/.local/state/yourkiosk-otomasyon"
KOD_DEPO="${NOBETCI_KOD_DEPO:-$HOME/.local/share/yourkiosk-nobetci/depo}"
VARSAYILAN_UZAK="git@github.com:hakkisabah/yourkiosk.git"
DAL="${NOBETCI_DAL:-main}"

ROL="${1:-}"
if [ "$ROL" = "i5" ] || [ "$ROL" = "i3" ]; then shift; else
  echo "kullanım: $0 <i5|i3> [--kuru] [--yeniden-baslat] [--sessiz] [--gecikme=SN]" >&2
  exit 2
fi

KURU=0; YENIDEN=0; SESSIZ=0; GECIKME=900
# Seçenekler TEK geçişte okunur: `--dal <ad>` değeri bir sonraki sözcüktür, "bilinmeyen seçenek"
# sayılmamalı (27 Ekim: iki geçişli ilk sürüm `--dal duzeltme/dal` biçimini reddediyordu).
while [ $# -gt 0 ]; do
  case "$1" in
    --kuru) KURU=1 ;;
    --yeniden-baslat) YENIDEN=1 ;;
    --sessiz) SESSIZ=1 ;;
    --dal) shift; DAL="${1:-}" ;;
    --dal=*) DAL="${1#--dal=}" ;;
    --gecikme=*) GECIKME="${1#--gecikme=}" ;;
    *) echo "✗ bilinmeyen seçenek: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$GECIKME" in ''|*[!0-9]*) echo "✗ --gecikme sayı olmalı" >&2; exit 2 ;; esac
dal_gecerli() {
  local d="$1"
  [ -n "$d" ] && [ "${#d}" -le 120 ] || return 1
  case "$d" in -*) return 1 ;; */) return 1 ;; *..*) return 1 ;; *//*) return 1 ;; esac
  case "$d" in *[!A-Za-z0-9._/-]*) return 1 ;; esac
  return 0
}
if ! dal_gecerli "$DAL"; then
  echo "✗ geçersiz --dal değeri: '$DAL'" >&2
  echo "  İzinli biçim: harf/rakam/._/- (ör. main, ozellik/karar-kapisi-adil-kuyruk)" >&2
  exit 2
fi

# Bu betiğin bulunduğu depo (kaynak): <depo>/otomasyon/betik/nobetci-bakim.sh
# `git show … | bash -s --` ile (boru hattı) çalıştırılırsa dosya yolu YOKTUR: o durumda kaynak
# depo bilinmez, uzak adres varsayılana düşer. Betik kaynak depoya hiçbir şey YAZMAZ.
KAYNAK=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd || true)"
fi
soyle() { [ "$SESSIZ" -eq 1 ] || printf '%s\n' "$*"; }
hata() { printf '✗ %s\n' "$*" >&2; }

# ── 0) git var mı ─────────────────────────────────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || { hata "git bulunamadı (PATH)"; exit 3; }

# ── 1) UZAK adres: varsa kaynak deponun origin'i, yoksa varsayılan ────────────────────────────
UZAK="${NOBETCI_UZAK:-}"
if [ -z "$UZAK" ]; then
  UZAK="$(git -C "$KAYNAK" remote get-url origin 2>/dev/null || true)"
  [ -z "$UZAK" ] && UZAK="$VARSAYILAN_UZAK"
fi
soyle "kaynak      : ${KAYNAK:-(boru hattı — dosya yolu yok)}"
soyle "kod deposu  : $KOD_DEPO"
soyle "uzak        : $UZAK ($DAL)"

if [ "$KURU" -eq 1 ]; then
  if [ -d "$KOD_DEPO/.git" ]; then
    soyle "kuru: klon var → fetch + reset --hard origin/$DAL"
  else
    soyle "kuru: klon yok → git clone --branch $DAL --single-branch $UZAK $KOD_DEPO"
    soyle "kuru: izlenen dal dosyası → $DURUM_KLASORU/nobetci-dal ($DAL)"
  fi
  soyle "kuru: bellek tavanı → $HOME/.config/systemd/user/$UNIT_ADI.d/50-bellek.conf (drop-in)"
  soyle "kuru: sonra → bash <klon>/otomasyon/nobetci-kur.sh $ROL --klon $KOD_DEPO"
  exit 0
fi

mkdir -p "$(dirname "$KOD_DEPO")"

# ── 2) Klon: yoksa oluştur, varsa origin/main'e çek ───────────────────────────────────────────
if [ ! -d "$KOD_DEPO/.git" ]; then
  if [ -e "$KOD_DEPO" ] && [ -n "$(ls -A "$KOD_DEPO" 2>/dev/null || true)" ]; then
    hata "$KOD_DEPO var ama git deposu değil ve boş değil — elle inceleyin (silinmedi)"
    exit 4
  fi
  soyle "→ klon oluşturuluyor"
  git clone --branch "$DAL" --single-branch "$UZAK" "$KOD_DEPO" >/dev/null 2>&1 || {
    hata "klon başarısız: $UZAK (dal: $DAL)"
    hata "  SSH anahtarı yetkili mi?  ssh -T git@github.com"
    hata "  Dal uzakta var mı?        git ls-remote --heads $UZAK $DAL"
    exit 5
  }
fi
# Makineye ait kopya işareti: nobetci.py bu işareti görürse `reset --hard` ile günceller.
# İşaret yoksa (insan deposu) nöbetçi yalnız `merge --ff-only` dener → kimsenin işini ezmez.
touch "$KOD_DEPO/.git/yourkiosk-nobetci-kopya"
# İzlenen dal TEK kaynaktan okunsun: servis, --guncelle ve --kendini-denetle bu dosyaya bakar.
mkdir -p "$DURUM_KLASORU"
printf '%s\n' "$DAL" > "$DURUM_KLASORU/nobetci-dal"

ESKI_SHA="$(git -C "$KOD_DEPO" rev-parse --short=10 HEAD 2>/dev/null || echo '?')"
git -C "$KOD_DEPO" fetch --prune origin "$DAL" >/dev/null 2>&1 || {
  hata "fetch başarısız (ağ/anahtar?) — klon güncellenmedi"; exit 5; }
git -C "$KOD_DEPO" reset --hard "origin/$DAL" >/dev/null 2>&1 || {
  hata "reset --hard origin/$DAL başarısız"; exit 5; }
YENI_SHA="$(git -C "$KOD_DEPO" rev-parse --short=10 HEAD 2>/dev/null || echo '?')"
if [ "$ESKI_SHA" = "$YENI_SHA" ]; then soyle "kod         : $YENI_SHA (değişmedi)"
else soyle "kod         : $ESKI_SHA → $YENI_SHA (güncellendi)"; fi

# ── 3) BELLEK TAVANI — birimden BAĞIMSIZ drop-in ──────────────────────────────────────────────
# 26 Ekim arızasının ikinci yarısı: klon origin/main'e çekilse bile, o sürümün nobetci-kur.sh'ı
# bellek tavanı üretmiyorsa (sıra: #90 birleşmemişse) makine yine tavansız kalır ve node OOM'u
# tekrarlar. Bu yüzden tavanlar BURADA, kur.sh sürümünden bağımsız olarak drop-in'e yazılır:
#   ~/.config/systemd/user/yourkiosk-nobetci.service.d/50-bellek.conf
# Drop-in ana birimdeki aynı anahtarları GEÇERSİZ KILAR (systemd kuralı) → tek doğru kaynak burası.
RAM_MB="$(awk '/^MemTotal:/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || true)"
case "${RAM_MB:-}" in ''|*[!0-9]*) RAM_MB=0 ;; esac
if [ "$RAM_MB" -gt 1024 ]; then
  MEM_HIGH_MB=$(( RAM_MB * 60 / 100 ))
  MEM_MAX_MB=$(( RAM_MB * 75 / 100 ))
  NODE_HEAP_MB=$(( RAM_MB / 4 ))
  [ "$NODE_HEAP_MB" -lt 512 ] && NODE_HEAP_MB=512
  [ "$NODE_HEAP_MB" -gt 2048 ] && NODE_HEAP_MB=2048
else
  MEM_HIGH_MB=1024; MEM_MAX_MB=1280; NODE_HEAP_MB=768
  soyle "UYARI: MemTotal okunamadı (${RAM_MB} MB) → muhafazakâr tavanlar"
fi
DROPIN_DIZIN="$HOME/.config/systemd/user/$UNIT_ADI.d"
mkdir -p "$DROPIN_DIZIN"
cat > "$DROPIN_DIZIN/50-bellek.conf" <<DROPIN
# nobetci-bakim.sh tarafından üretildi (RAM ${RAM_MB} MB) — elle düzenlemeyin, betiği çalıştırın.
[Service]
MemoryAccounting=yes
MemoryHigh=${MEM_HIGH_MB}M
MemoryMax=${MEM_MAX_MB}M
TasksMax=1024
OOMPolicy=stop
Environment=NODE_OPTIONS=--max-old-space-size=${NODE_HEAP_MB}
DROPIN
soyle "bellek      : RAM ${RAM_MB} MB → High ${MEM_HIGH_MB} MB · Max ${MEM_MAX_MB} MB · heap ${NODE_HEAP_MB} MB"

# ── 4) Birim dosyasını klondan üret ──────────────────────────────────────────────────────────
KUR="$KOD_DEPO/otomasyon/nobetci-kur.sh"
[ -f "$KUR" ] || { hata "klonda nobetci-kur.sh yok: $KUR"; exit 6; }
soyle "→ birim yazılıyor (klon yolu, çökme freni)"
# TEST/KURU KANCASI: systemd'ye dokunmadan birim metnini üretmek için (testler ve systemd'siz
# makineler). Üretimde tanımlı değildir → gerçek kurulum yapılır.
# KOD UYUM KAPISI (27 Ekim i5 arızası): ilk sürüm burada klonun `nobetci-kur.sh`ını çağırıyor ve
# çıktısını `>/dev/null` ile YUTUYORDU. i5'te klon origin/main'e çekildiği için ESKİ kur.sh çalıştı;
# o sürüm `--klon` bilmiyor, birimi insan deposu gibi yazıyor ve hata verince tek görünen şey
# "✗ birim kurulumu başarısız" oldu — neden yok. Artık: (1) klondaki kodun bu kurulum biçimini
# destekleyip desteklemediği ÖLÇÜLÜR, (2) gerçek kurulumun çıktısı hatada AYNEN gösterilir.
KUR_LOG="$(mktemp -t yourkiosk-bakim-XXXXXX.log)"
trap 'rm -f "$KUR_LOG"' EXIT
if ! bash "$KUR" "$ROL" --kuru --klon "$KOD_DEPO" --dal "$DAL" >"$KUR_LOG" 2>&1; then
  hata "birim üretimi başarısız (klon kodu: $YENI_SHA) — çıktı:"
  sed 's/^/    /' "$KUR_LOG" | tail -20 >&2
  exit 7
fi
eksik=""
grep -q "^WorkingDirectory=$KOD_DEPO$" "$KUR_LOG" || eksik="WorkingDirectory=$KOD_DEPO"
grep -q -- "--guncelle" "$KUR_LOG" || eksik="${eksik:+$eksik, }--guncelle"
# --dal desteği yalnız main DIŞI bir dal istenirken ZORUNLU: eski kod (main) zaten main'i izler.
if [ "$DAL" != "main" ]; then
  grep -q -- "--dal $DAL" "$KUR_LOG" || eksik="${eksik:+$eksik, }--dal $DAL"
fi
if [ -n "$eksik" ]; then
  hata "klondaki kod ($DAL @ $YENI_SHA) makine kopyası + kendini güncelleme biçimini DESTEKLEMİYOR"
  hata "  eksik: $eksik"
  hata "  sebep: origin/$DAL henüz bu düzeltmeleri içermiyor (düzeltme bir PR dalında olabilir)."
  hata "  çözüm: düzeltmeyi taşıyan daldan kur →  $0 $ROL --dal <düzeltme-dalı>"
  hata "  (main'e merge edildikten sonra: $0 $ROL   → dal yine main olur)"
  exit 8
fi
if [ "${NOBETCI_SISTEMD_ATLA:-0}" = "1" ]; then
  soyle "sistemd     : atlandı (NOBETCI_SISTEMD_ATLA=1) — birim yazılmadı"
  soyle "kod         : $KOD_DEPO @ $YENI_SHA ($DAL)"
  exit 0
fi
if ! bash "$KUR" "$ROL" --klon "$KOD_DEPO" --dal "$DAL" >>"$KUR_LOG" 2>&1; then
  hata "birim kurulumu başarısız (klon kodu: $YENI_SHA) — komut çıktısı:"
  sed 's/^/    /' "$KUR_LOG" | tail -25 >&2
  hata "  günlük: journalctl --user -u $UNIT_ADI -n 30 --no-pager"
  exit 7
fi

# ── 5) CANLI bellek tavanı: çalışan birimi yeniden başlatmadan uygula ────────────────────────
# (Oturum içinden `systemctl restart` yapılırsa o oturumun kendisi ölür — bu yüzden set-property.)
if systemctl --user is-active "$UNIT_ADI" >/dev/null 2>&1; then
  if systemctl --user set-property "$UNIT_ADI" "MemoryHigh=${MEM_HIGH_MB}M" "MemoryMax=${MEM_MAX_MB}M" 2>/dev/null; then
    soyle "bellek      : canlı tavan uygulandı (High ${MEM_HIGH_MB} MB · Max ${MEM_MAX_MB} MB)"
  else
    soyle "bellek      : canlı uygulanamadı (birim yeniden başlayınca etkin olacak)"
  fi
fi

# ── 5) Yeniden başlatma: oturum içindeysek GECİKMELİ, dışındaysak hemen ──────────────────────
icinde=0
if grep -qs "$UNIT_ADI" /proc/self/cgroup 2>/dev/null; then icinde=1; fi
if [ "$YENIDEN" -eq 1 ]; then
  if [ "$icinde" -eq 1 ]; then
    hata "bu kabuk nöbetçi biriminin içinde → hemen restart oturumu öldürür; gecikmeli kuruluyor"
    YENIDEN=0
  fi
  systemctl --user restart "$UNIT_ADI" && soyle "servis      : yeniden başlatıldı"
else
  # Yeni ExecStart (klon yolu) bir sonraki yeniden başlatmada devreye girer. Oturum içindeysek
  # systemd-run ile GECİKMELİ devralma kurarız: oturum biter, sonra servis yeni koddan kalkar.
  if [ "$icinde" -eq 1 ]; then
    if command -v systemd-run >/dev/null 2>&1 && \
       systemd-run --user --collect --on-active="${GECIKME}s" \
         --unit="yourkiosk-nobetci-devralma-$(date +%s)" \
         systemctl --user restart "$UNIT_ADI" >/dev/null 2>&1; then
      soyle "servis      : ${GECIKME}s sonra yeni koddan yeniden başlayacak (gecikmeli devralma)"
    else
      soyle "servis      : yeniden başlatma kurulamadı → elle: systemctl --user restart $UNIT_ADI"
    fi
  else
    soyle "servis      : birim dosyası güncellendi (etkin olması için: systemctl --user restart $UNIT_ADI)"
  fi
fi

# ── 6) Özet + tek doğrulama komutu ───────────────────────────────────────────────────────────
soyle ""
soyle "=== bakım bitti ==="
soyle "kod         : $KOD_DEPO @ $YENI_SHA ($DAL)"
soyle "doğrula     : (cd $KOD_DEPO && python3 otomasyon/betik/nobetci.py --rol $ROL --dal $DAL --kendini-denetle)"
soyle "günlük      : tail -f $DURUM_KLASORU/nobetci-$ROL.log"
exit 0
