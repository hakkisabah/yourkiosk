#!/usr/bin/env bash
# Hermes API sunucusunu Open WebUI için hazırla — GÜVENLİK DUVARI KULLANMADAN.
#
# TASARIM KARARI (v2 — v1'deki nftables yaklaşımı TERK EDİLDİ):
#   v1 portu 0.0.0.0'a açıp kaynağı nftables ile sınırlıyordu. Yanlış IP yazılınca erişim
#   tamamen kesildi ve uzaktan teşhis imkânsız hâle geldi (25 Ekim'de yaşandı).
#   v2 güvenlik duvarına HİÇ dokunmaz: portu **docker0 köprü adresine** (172.17.0.1) bağlar.
#   Uç yalnız konteyner ağından görünür, LAN'dan ulaşılamaz → yanlış kural riski yok.
#
# Kullanım:
#   ./api-sunucu-sertlestir.sh --kontrol          # durumu göster, hiçbir şeyi değiştirme
#   ./api-sunucu-sertlestir.sh --kuru             # ne yapacağını göster, değiştirme
#   ./api-sunucu-sertlestir.sh                    # uygula: güçlü anahtar + docker0'a bağla
#   ./api-sunucu-sertlestir.sh --dinle 127.0.0.1  # yalnız yerel (konteyner kullanmıyorsan)
#   ./api-sunucu-sertlestir.sh --anahtar-yenile   # anahtarı değiştir (istemciler 401 alır)
#
# Dinleme adresi BEYAZ LİSTE ile sınırlıdır (127.0.0.1 · 172.17.0.1 · 172.18.0.1).
# `0.0.0.0` yalnız açık `--kabul-et-lan` ile yazılır: bu uç, gelen isteği terminal yetkisiyle
# çalıştıran bir ajandır; yanlışlıkla tüm ağlara açmak makineyi ele verir.
#
# Bu betik gateway'i YENİDEN BAŞLATMAZ (ajan süreci içinden güvenli değil); komutu yazdırır.

set -uo pipefail

HERMES="$(command -v hermes || true)"
[ -n "$HERMES" ] || HERMES="$HOME/.local/bin/hermes"
SIR_DIR="$HOME/.config/hermes-secrets"
ANAHTAR_DOSYA="$SIR_DIR/api-server.key"
#: Operatörün "LAN'a aç" kararının izi. Bu dosya yoksa `0.0.0.0` bir SORUN sayılır; varsa
#: "operatör onaylı" olarak ✓ gösterilir. Gerekçe: bu makinede sunucuya ağdan (LAN) erişilmesi
#: gerekiyor; kararın kendisi görünür ve geri alınabilir olmalı — sessizce 0.0.0.0'da bırakmak
#: ile her kontrolde kırmızı yanıp kimsenin bakmadığı bir uyarıya dönüşmek arasındaki fark.
#:
#: 26 Ekim i5 bulgusu: dosya `~/.config/hermes-secrets/` altındaydı ve `lan_onayli()` yalnız
#: VARLIĞINA bakıyordu → aynı kullanıcıdaki herhangi bir süreç (ajan dahil) `touch` ile "operatör
#: onayı" üretebiliyordu. Artık yol ROOT sahipli `/etc` altında; `--kabul-et-lan` dosyayı sudo ile
#: yazar ve onay yalnız root sahipli + grup/dünya-yazılamaz ise geçerli sayılır.
LAN_ONAY_DOSYA="/etc/yourkiosk-api-lan-onay"
#: Onay dosyasını silerken sudo gerekir (dosya root sahipli /etc altında).
onay_sil() {
  [ -e "$LAN_ONAY_DOSYA" ] || return 0
  if [ "${KURU:-0}" -eq 1 ]; then echo "  [KURU] onay dosyası silinecek: $LAN_ONAY_DOSYA"; return 0; fi
  if sudo rm -f "$LAN_ONAY_DOSYA"; then
    echo "  onay kaydı silindi: $LAN_ONAY_DOSYA"
  else
    echo "  ⚠ onay kaydı SİLİNEMEDİ (sudo başarısız): $LAN_ONAY_DOSYA — 0.0.0.0 açık kalırsa --kontrol onayı geçerli sayar" >&2
  fi
}

ENV_DOSYA="$("$HERMES" config env-path 2>/dev/null | tail -1)"
[ -n "$ENV_DOSYA" ] || ENV_DOSYA="$HOME/.hermes/.env"

PORT=8642
DINLE="172.17.0.1"          # docker0 köprüsü — LAN'dan görünmez
KIP="uygula"
YENILE=0
KURU=0
KABUL_LAN=0
ANAHTAR=""

kullanim() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --kontrol) KIP="kontrol"; shift ;;
    --kuru)    KURU=1; shift ;;
    --dinle)   DINLE="${2:?--dinle bir IP ister}"; shift 2 ;;
    --anahtar-yenile) YENILE=1; shift ;;
    --kabul-et-lan) KABUL_LAN=1; shift ;;
    -h|--help) kullanim 0 ;;
    *) echo "bilinmeyen argüman: $1" >&2; kullanim 2 ;;
  esac
done

# Onay dosyası /etc altına sudo ile kurulurken kullanılan geçici kopya (sır değil, tarih+not).
GECICI_ONAY="$(mktemp "${TMPDIR:-/tmp}/yourkiosk-lan-onay.XXXXXX")"
trap 'rm -f "$GECICI_ONAY"' EXIT

# ── dinleme adresi doğrulaması ───────────────────────────────────────────────────────────────
# 26 Ekim i5 bulgusu: --dinle değeri hiç denetlenmiyordu (yazım hatası ya da 0.0.0.0 sessizce
# kabul ediliyordu). Beyaz liste: yalnız yerel/konteyner köprüsü adresleri.
case "$DINLE" in
  127.0.0.1|172.17.0.1|172.18.0.1) ;;
  0.0.0.0)
    if [ "$KABUL_LAN" -ne 1 ]; then
      echo "✗ --dinle 0.0.0.0 verildi ama --kabul-et-lan yok." >&2
      echo "  Bu uç terminal yetkili bir ajandır. Konteyner için 172.17.0.1 kullanın;" >&2
      echo "  gerçekten LAN'a açacaksanız açıkça: --dinle 0.0.0.0 --kabul-et-lan" >&2
      exit 2
    fi ;;
  *)
    echo "✗ geçersiz --dinle değeri: '$DINLE'" >&2
    echo "  İzinli: 127.0.0.1 · 172.17.0.1 · 172.18.0.1 (0.0.0.0 yalnız --kabul-et-lan ile)" >&2
    exit 2 ;;
esac

cfg_get() { "$HERMES" config get "$1" 2>/dev/null | tail -1 || true; }
cfg_set() {
  if [ "$KURU" -eq 1 ]; then
    echo "  [KURU] config set $1 $2"
    return 0
  fi
  "$HERMES" config set "$1" "$2" >/dev/null
}

# Dosya içeriği bash yerleşik yönlendirmesiyle okunur.
# DİKKAT (26 Ekim i5 bulgusu): eski sürüm "anahtar hiçbir zaman bir komut satırında görünmez"
# diyordu ama `hermes config set API_SERVER_KEY "$yeni"` anahtarı argv'ye koyuyordu; /proc/<pid>/cmdline
# aynı makinedeki herkese okunur. Artık anahtar yalnız DOSYADAN okunur ve .env'e python ile
# yazılır — komut satırında hiç görünmez (argüman olarak yalnız dosya YOLLARI geçer).
anahtar_oku() { if [ -s "$ANAHTAR_DOSYA" ]; then ANAHTAR="$(<"$ANAHTAR_DOSYA")"; else ANAHTAR=""; fi; }

anahtari_env_yaz() {  # anahtar dosyası → .env (değer argv'de DEĞİL)
  python3 - "$ENV_DOSYA" "$ANAHTAR_DOSYA" <<'PY'
import os
import pathlib
import sys
import tempfile

env_yolu, anahtar_yolu = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
anahtar = anahtar_yolu.read_text(encoding="utf-8").strip()
if not anahtar:
    sys.exit("anahtar dosyası boş")
satirlar = env_yolu.read_text(encoding="utf-8").splitlines() if env_yolu.exists() else []
cikti, bulundu = [], False
for satir in satirlar:
    if satir.startswith("API_SERVER_KEY="):
        cikti.append(f"API_SERVER_KEY={anahtar}")
        bulundu = True
    else:
        cikti.append(satir)
if not bulundu:
    cikti.append(f"API_SERVER_KEY={anahtar}")
env_yolu.parent.mkdir(parents=True, exist_ok=True)
# 26 Ekim i5 bulgusu: sabit adlı `.env.tmp` + O_CREAT sembolik bağı izler → aynı kullanıcıdaki
# bir süreç bağı önceden koyup .env'i başka yere taşıtabilirdi. mkstemp: tahmin edilemez ad,
# O_EXCL, 0600; dosya .env ile AYNI dizinde olduğu için os.replace atomik kalır.
fd, gecici = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(env_yolu.parent))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(cikti) + "\n")
    os.chmod(gecici, 0o600)
    os.replace(gecici, env_yolu)
finally:
    if os.path.exists(gecici):
        os.unlink(gecici)
os.chmod(env_yolu, 0o600)
print(f"  API_SERVER_KEY .env'e yazıldı (0600): {env_yolu}")
PY
}

kod_al() {  # kod_al <url> [anahtar]
  # 26 Ekim i5 bulgusu: anahtar `-H "Authorization: Bearer $2"` ile curl'ün ARGV'sine giriyordu
  # (/proc/<pid>/cmdline aynı makinedeki herkese okunur). Artık başlık `--config -` ile
  # STDIN'den verilir: değer hiçbir süreç argümanında görünmez.
  if [ -n "${2:-}" ]; then
    printf 'header = "Authorization: Bearer %s"\n' "$2" \
      | curl -s -m 4 -o /dev/null -w '%{http_code}' --config - "$1" || true
  else
    curl -s -m 4 -o /dev/null -w '%{http_code}' "$1" || true
  fi
}

dinlenen() { ss -tlnH "sport = :$PORT" 2>/dev/null | awk '{print $4}' | head -1 || true; }

# ---------------------------------------------------------------- --kontrol
if [ "$KIP" = "kontrol" ]; then
  sorun=0
  satir() { if [ "$1" = 1 ]; then printf '✓ %-30s %s\n' "$2" "$3"; else printf '✗ %-30s %s\n' "$2" "$3"; sorun=$((sorun+1)); fi; }

  etkin="$(cfg_get API_SERVER_ENABLED)"
  [ "${etkin,,}" = "true" ] && satir 1 "API sunucusu açık" "true" || satir 0 "API sunucusu açık" "${etkin:-ayarsız}"

  anahtar_oku
  [ "${#ANAHTAR}" -ge 32 ] && satir 1 "anahtar ≥ 32 karakter" "${#ANAHTAR}" \
    || satir 0 "anahtar ≥ 32 karakter" "${#ANAHTAR} (16'dan kısa anahtarla Hermes sunucuyu BAŞLATMAZ)"

  # 26 Ekim i5 bulgusu: --kontrol anahtar DOSYASININ İZNİNE hiç bakmıyordu; 0644 (dünya-okur)
  # bir anahtar dosyası "temiz" görünüyordu. Sır dosyası 0600, sır dizini 700 olmalı.
  if [ -f "$ANAHTAR_DOSYA" ]; then
    izin="$(stat -c '%a' "$ANAHTAR_DOSYA" 2>/dev/null || echo '?')"
    sahip="$(stat -c '%U' "$ANAHTAR_DOSYA" 2>/dev/null || echo '?')"
    if [ "$izin" = "600" ]; then
      satir 1 "anahtar dosyası izni" "$izin ($sahip)"
    else
      satir 0 "anahtar dosyası izni" "$izin → 0600 olmalı: chmod 600 $ANAHTAR_DOSYA"
    fi
  else
    satir 0 "anahtar dosyası" "yok ($ANAHTAR_DOSYA)"
  fi
  if [ -d "$SIR_DIR" ]; then
    izin="$(stat -c '%a' "$SIR_DIR" 2>/dev/null || echo '?')"
    if [ "$izin" = "700" ]; then
      satir 1 "sır dizini izni" "$izin"
    else
      satir 0 "sır dizini izni" "$izin → 0700 olmalı: chmod 700 $SIR_DIR"
    fi
  else
    satir 0 "sır dizini" "yok ($SIR_DIR)"
  fi

  # 26 Ekim i5 bulgusu: anahtarın KOPYASI .env'de duruyor; --kontrol yalnız anahtar dosyasının
  # iznine bakıyordu. .env 0644 kalmışsa anahtar aynı makinedeki her kullanıcıya okunur ve
  # kontrol yine "temiz" derdi. Artık .env de 0600 olmalı.
  if [ -f "$ENV_DOSYA" ]; then
    izin="$(stat -c '%a' "$ENV_DOSYA" 2>/dev/null || echo '?')"
    if [ "$izin" = "600" ]; then
      satir 1 ".env izni (anahtar kopyası)" "$izin ($ENV_DOSYA)"
    else
      satir 0 ".env izni (anahtar kopyası)" "$izin → 0600 olmalı: chmod 600 $ENV_DOSYA"
    fi
  else
    satir 0 ".env" "yok ($ENV_DOSYA) — anahtar kopyası yazılmamış"
  fi

  # 26 Ekim i5 bulgusu: burada yalnız `0.0.0.0` kırmızıydı; geri kalan HER adres "LAN'a kapalı"
  # sayılıyordu (`192.168.1.50` yeşil görünüyordu). Artık iki ayrı kaynak beyaz listeye karşı
  # denetlenir: (a) yapılandırılmış API_SERVER_HOST, (b) `ss -tlnH` ile GERÇEKTEN dinlenen adres.
  # İkisinden biri 127.0.0.1 · 172.17.0.1 · 172.18.0.1 dışındaysa kontrol ÇIKIŞ 1 verir.
  beyaz_listede() {
    case "${1:-}" in
      127.0.0.1|172.17.0.1|172.18.0.1) return 0 ;;
      *) return 1 ;;
    esac
  }

  host="$(cfg_get API_SERVER_HOST)"; host="${host:-127.0.0.1}"
  #: Operatör "LAN'a aç" kararını verdi mi? → 0 onaylı · 1 yok · 2 güvenilmez (root sahipli değil
  #: ya da yazılabilir → ajan tarafından üretilmiş olabilir, onay SAYILMAZ).
  lan_onay_durumu() {
    [ -e "$LAN_ONAY_DOSYA" ] || return 1
    local sahip mod
    sahip="$(stat -c '%u' "$LAN_ONAY_DOSYA" 2>/dev/null || echo '?')"
    mod="$(stat -c '%a' "$LAN_ONAY_DOSYA" 2>/dev/null || echo '?')"
    [ "$sahip" = "0" ] || return 2
    [ $(( 0$mod & 022 )) -eq 0 ] || return 2
    return 0
  }
  case "$host" in
    0.0.0.0)
      lan_onay_durumu
      case "$?" in
        0) satir 1 "LAN'a açık (operatör onaylı)" "0.0.0.0 · onay: $(head -1 "$LAN_ONAY_DOSYA" 2>/dev/null)" ;;
        2) satir 0 "LAN'a kapalı (yapılandırılmış host)" \
             "$host → tüm ağlara açık · operatör onayı DOĞRULANAMIYOR (dosya ajan tarafından yazılabilir: $LAN_ONAY_DOSYA)" ;;
        *) satir 0 "LAN'a kapalı (yapılandırılmış host)" "$host → tüm ağlara açık (onay dosyası yok: $LAN_ONAY_DOSYA)" ;;
      esac ;;
    *)
      if beyaz_listede "$host"; then
        satir 1 "LAN'a kapalı (yapılandırılmış host)" "$host"
      else
        satir 0 "LAN'a kapalı (yapılandırılmış host)" \
          "$host → beyaz liste dışı (127.0.0.1 · 172.17.0.1 · 172.18.0.1)"
      fi ;;
  esac

  adres="$(dinlenen)"
  [ -n "$adres" ] && satir 1 "port $PORT dinleniyor" "$adres" || satir 0 "port $PORT dinleniyor" "hayır"

  # `ss` çıktısı `adres:port` biçiminde (IPv6: `[::]:port`) → portu ayır, adresi denetle.
  adres_host=""
  if [ -n "$adres" ]; then
    case "$adres" in
      \[*\]:*) adres_host="${adres%]:*}"; adres_host="${adres_host#[}" ;;
      *:*)     adres_host="${adres%:*}" ;;
      *)       adres_host="$adres" ;;
    esac
    if beyaz_listede "$adres_host"; then
      satir 1 "LAN'a kapalı (dinlenen adres)" "$adres_host"
    elif [ "$adres_host" = "0.0.0.0" ] && lan_onay_durumu; then
      satir 1 "LAN'a açık (operatör onaylı, dinlenen adres)" "0.0.0.0"
    else
      satir 0 "LAN'a kapalı (dinlenen adres)" "$adres_host → beyaz liste dışı (LAN'a açık)"
    fi
  fi

  if [ -n "$adres" ]; then
    # `0.0.0.0` bağlaması loopback'i de kabul eder; köprü adresi (172.17.0.1) olmayan makinelerde
    # yoklama boşa düşmesin diye 0.0.0.0'da 127.0.0.1 denenir.
    yokla_host="$DINLE"; [ "$DINLE" = "0.0.0.0" ] && yokla_host="127.0.0.1"
    kod="$(kod_al "http://$yokla_host:$PORT/v1/models" "$ANAHTAR")"
    [ "$kod" = "200" ] && satir 1 "anahtarlı istek" "HTTP 200" || satir 0 "anahtarlı istek" "HTTP $kod"
    kod="$(kod_al "http://$yokla_host:$PORT/v1/models")"
    [ "$kod" = "401" ] && satir 1 "anahtarsız istek reddediliyor" "HTTP 401" || satir 0 "anahtarsız istek reddediliyor" "HTTP $kod"
  fi

  if command -v nft >/dev/null 2>&1; then
    nft_cikti="$(nft list table inet hermes_api 2>&1 >/dev/null)"
    if [ -z "$nft_cikti" ]; then
      satir 0 "eski nftables kuralı" "inet hermes_api HÂLÂ VAR → api-sunucu-geri-al.sh"
    elif printf '%s' "$nft_cikti" | grep -qi "no such file\|not found"; then
      satir 1 "eski nftables kuralı" "yok (temiz)"
    else
      printf '· %-30s %s\n' "eski nftables kuralı" "okunamadı (root gerekir): sudo nft list ruleset"
    fi
  fi

  echo
  [ "$sorun" -eq 0 ] && echo "✓ kontrol noktaları temiz" || echo "✗ $sorun kontrol noktası sorunlu"
  exit $([ "$sorun" -eq 0 ] && echo 0 || echo 1)
fi

# ---------------------------------------------------------------- uygula
echo "== 1/3 anahtar =="
mkdir -p "$SIR_DIR"; chmod 700 "$SIR_DIR"
anahtar_oku
if [ "$YENILE" -eq 1 ] || [ "${#ANAHTAR}" -lt 32 ]; then
  if [ "$KURU" -eq 1 ]; then
    echo "  [KURU] 64 karakterlik yeni anahtar üretilecek → $ANAHTAR_DOSYA (+ .env)"
  else
    # 26 Ekim i5 bulgusu: `openssl rand` başarısız olursa (PATH'te yok, kaynak tükenmesi) `yeni`
    # BOŞ kalıyor ve `printf > $ANAHTAR_DOSYA` MEVCUT anahtarı boş dosyayla eziyordu — üstelik
    # betik "yeni anahtar üretildi" diye başarı bildiriyordu. Artık: üret → doğrula (64 hex) →
    # geçici dosyaya yaz → atomik taşı. Üretim başarısızsa hiçbir dosyaya DOKUNULMAZ.
    if ! command -v openssl >/dev/null 2>&1; then
      echo "✗ openssl bulunamadı — anahtar ÜRETİLMEDİ, mevcut anahtar ve .env korunuyor." >&2
      exit 3
    fi
    yeni="$(openssl rand -hex 32 2>/dev/null || true)"
    if [ "${#yeni}" -ne 64 ]; then
      echo "✗ anahtar üretilemedi (openssl hatası, ${#yeni} karakter) — mevcut anahtar KORUNUYOR; hiçbir dosya değişmedi." >&2
      unset yeni
      exit 3
    fi
    gecici="$(mktemp "$SIR_DIR/.api-server.key.XXXXXX" 2>/dev/null)" || {
      echo "✗ geçici dosya açılamadı ($SIR_DIR) — mevcut anahtar KORUNUYOR." >&2
      unset yeni; exit 3
    }
    (umask 077; printf '%s\n' "$yeni" > "$gecici") && chmod 600 "$gecici" || {
      rm -f "$gecici"; echo "✗ anahtar yazılamadı — mevcut anahtar KORUNUYOR." >&2; unset yeni; exit 3
    }
    mv -f "$gecici" "$ANAHTAR_DOSYA" || {
      rm -f "$gecici"; echo "✗ anahtar taşınamadı — mevcut anahtar KORUNUYOR." >&2; unset yeni; exit 3
    }
    unset yeni
    anahtari_env_yaz
    anahtar_oku
    echo "  yeni anahtar üretildi → $ANAHTAR_DOSYA (0600) ve .env"
  fi
else
  echo "  mevcut anahtar yeterli (${#ANAHTAR} karakter) — korunuyor"
fi

echo "== 2/3 dinleme adresi =="
cfg_set API_SERVER_ENABLED true
cfg_set API_SERVER_HOST "$DINLE"
cfg_set API_SERVER_PORT "$PORT"
echo "  ENABLED=true · HOST=$DINLE · PORT=$PORT"
case "$DINLE" in
  172.17.0.1|172.18.0.1)
    onay_sil
    echo "  → yalnız Docker köprüsünden erişilebilir; LAN'dan görünmez, güvenlik duvarı gerekmez." ;;
  127.0.0.1)
    onay_sil
    echo "  → yalnız bu makineden (konteynerden erişilemez)." ;;
  0.0.0.0)
    # Operatör kararı KAYDA geçer: `--kontrol` bu dosyayı görürse 0.0.0.0'ı "onaylı" sayar,
    # görmezse sorun. Böylece "her kontrolde kırmızı" ile "sessizce açık" arasındaki iki kötü
    # uç yerine görünür ve geri alınabilir bir karar kalır (geri al: --dinle 172.17.0.1).
    if [ "$KURU" -eq 1 ]; then
      echo "  [KURU] onay dosyası yazılacak: $LAN_ONAY_DOSYA"
    else
      printf '%s — operatör: API sunucusu LAN'"'"'a açık (Hermes istemcileri başka makineden bağlanıyor)\n' \
        "$(date -Iseconds)" >"$GECICI_ONAY"
      # ROOT sahipli /etc altına sudo ile kur: ajan aynı dosyayı üretemez (26 Ekim i5 bulgusu).
      if sudo install -o root -g root -m 0644 "$GECICI_ONAY" "$LAN_ONAY_DOSYA"; then
        echo "  onay kaydı: $LAN_ONAY_DOSYA (root:root 0644)"
      else
        echo "  ⚠ onay kaydı YAZILAMADI — sudo başarısız. 0.0.0.0 açık kalırsa --kontrol bunu SORUN sayar." >&2
      fi
      rm -f "$GECICI_ONAY"
    fi
    echo "  ⚠ 0.0.0.0 = tüm ağlara açık. Bu uç terminal yetkili ajandır; yalnız anahtar (API_SERVER_KEY)"
    echo "    ile erişilir. Ağ değişirse anahtarı döndür: $0 --anahtar-yenile" ;;
  *)
    onay_sil
    echo "  → yalnız $DINLE adresinden erişilebilir." ;;
esac

echo "== 3/3 doğrulama =="
if [ "$KURU" -eq 1 ]; then
  echo "  [KURU] atlandı"
else
  adres="$(dinlenen)"
  if [ -z "$adres" ]; then
    echo "  port henüz dinlenmiyor — ayar yeni yazıldı; gateway yeniden başlatılmalı (aşağıdaki 1. adım)."
  elif [ "$adres" != "$DINLE:$PORT" ]; then
    echo "  ⚠ dinlenen adres $adres — beklenen $DINLE:$PORT (yeniden başlatmadan sonra düzelir)"
  else
    echo "  anahtarlı : HTTP $(kod_al "http://$DINLE:$PORT/v1/models" "$ANAHTAR")   (200 beklenir)"
    echo "  anahtarsız: HTTP $(kod_al "http://$DINLE:$PORT/v1/models")   (401 beklenir)"
  fi
fi

GW="hermes gateway"
KENDI="$(printf '%s' "$0")"
cat <<NOT

──── sonraki adım ────
1) Ayarın etkinleşmesi için AYRI bir kabukta:
     $GW restart

2) Open WebUI'yi konteynerde çalıştır (köprüden 172.17.0.1'e erişir).
   İmaj etiketini SABİTLE: ':main' her yeniden başlatmada denetlenmemiş upstream kod çekebilir.
     docker pull ghcr.io/open-webui/open-webui:<SABIT-ETIKET>
     docker run -d --name open-webui --restart unless-stopped \\
       -p 127.0.0.1:3000:8080 \\
       -v open-webui:/app/backend/data -e ENABLE_SIGNUP=false \\
       ghcr.io/open-webui/open-webui:<SABIT-ETIKET>

   ('-p 127.0.0.1:3000:8080' → arayüz LAN'a kapalı; tarayıcıdan http://localhost:3000)
   Sabit etiketi seçmek için: docker images | grep open-webui   (ya da ghcr.io sürüm listesi)

3) Open WebUI → Ayarlar → Bağlantılar → OpenAI API:
     Base URL : http://172.17.0.1:$PORT/v1
     API Key  : dosyadan oku →  less $ANAHTAR_DOSYA

4) Kontrol:
     $KENDI --kontrol
NOT
