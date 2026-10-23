#!/usr/bin/env bash
# yourkiosk · TEK KURULUM GİRİŞİ
#
#   ./kur.sh kontrol     # makinede ne eksik? (hiçbir şey kurmaz)
#   ./kur.sh kiosk       # kiosk çalışma zamanı: venv + bağımlılıklar + web derleme
#   ./kur.sh panel       # yönetim paneli: npm bağımlılıkları + derleme + .env.local
#   ./kur.sh broker      # MQTT broker'ı (VPS'te, root): deploy/mosquitto/kur.sh
#   ./kur.sh docker      # Docker Compose ile kiosk (+ isteğe bağlı yerel broker)
#   ./kur.sh hepsi       # kiosk + panel + kontrol
#
# Tasarım: bu depoyu indiren kişi yalnızca bu betiği çalıştırır; ayrıntıları betik yönetir.
set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KOK"

renk() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
ok()   { renk "32" "  ✓ $*"; }
uyar() { renk "33" "  ⚠ $*"; }
hata() { renk "31" "  ✗ $*"; }
baslik() { echo; renk "1;36" "=== $* ==="; }

PYTHON="${KIOSK_PYTHON:-python3}"
VENV="$KOK/kiosk/.venv"

# ------------------------------------------------------------------ kontrol
kontrol() {
  local sorun=0
  baslik "ortam denetimi"

  if "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    ok "python: $("$PYTHON" -V 2>&1)"
  else
    hata "python3 >= 3.11 gerekli (bulunan: $("$PYTHON" -V 2>&1))"; sorun=1
  fi

  if [ -x "$VENV/bin/python" ]; then
    ok "kiosk venv: $VENV"
    for p in PyQt6 paho.mqtt; do
      if "$VENV/bin/python" -c "import $p" 2>/dev/null; then ok "  $p kurulu"; else uyar "  $p YOK → ./kur.sh kiosk"; sorun=1; fi
    done
  else
    uyar "kiosk venv yok → ./kur.sh kiosk"; sorun=1
  fi

  if command -v node >/dev/null 2>&1; then ok "node: $(node -v) · npm: $(npm -v)"; else uyar "node/npm yok (panel + web derlemesi için gerekli)"; sorun=1; fi

  if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; then
    ok "tarayıcı: $(command -v chromium || command -v chromium-browser || command -v google-chrome)"
  else
    uyar "chromium yok (tarayıcı modu için gerekli; Qt modu çalışır)"
  fi

  [ -f "$KOK/web/dist/index.html" ] && ok "web derlemesi var (web/dist)" || uyar "web derlemesi yok → ./kur.sh kiosk"
  [ -f "$KOK/panel/.env.local" ] && ok "panel/.env.local var" || uyar "panel/.env.local yok → ./kur.sh panel"

  # broker erişimi (ayarlardan okunur, yoksa atlanır)
  local broker port
  broker="$(python3 - <<'PY' 2>/dev/null || true
import json, pathlib
for ad in ("kiosk/ayarlar.json", "kiosk/ayarlar.ornek.json"):
    p = pathlib.Path(ad)
    if not p.is_file():
        continue
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        continue
    t = d.get("tetik", {})
    if t.get("push_aktif"):
        print(t.get("push_broker", ""))
        break
PY
)"
  port="$(python3 -c "
import json,pathlib
p=pathlib.Path('kiosk/ayarlar.json')
d=json.loads(p.read_text()) if p.is_file() else {}
print(d.get('tetik',{}).get('push_port',8883))" 2>/dev/null || echo 8883)"
  if [ -n "$broker" ]; then
    if timeout 5 bash -c "echo >/dev/tcp/$broker/$port" 2>/dev/null; then ok "MQTT broker erişilebilir: $broker:$port"
    else uyar "MQTT broker'a erişilemiyor: $broker:$port (yerel ayarlarda push_aktif=true)"; sorun=1; fi
  else
    uyar "MQTT push ayarlı değil (yoklama emniyet ağıyla çalışır)"
  fi

  # veri kaynağı erişimi
  local adres
  adres="$(python3 -c "
import json,pathlib
p=pathlib.Path('kiosk/ayarlar.json')
d=json.loads(p.read_text()) if p.is_file() else {}
print(d.get('veri',{}).get('dosya_adresi',''))" 2>/dev/null || true)"
  if [ -n "$adres" ]; then
    if curl -fsS -m 8 -o /dev/null "${adres%/}/lastupdate.json" 2>/dev/null; then ok "veri adresi erişilebilir: $adres"
    else uyar "veri adresine erişilemiyor: $adres"; sorun=1; fi
  fi

  echo
  if [ "$sorun" -eq 0 ]; then renk "1;32" "SONUÇ: hazır ✓ — ./kur.sh kiosk ile başlatabilirsiniz"
  else renk "1;33" "SONUÇ: eksikler var (yukarıdaki uyarılar)"; fi
  return 0
}

# ------------------------------------------------------------------ kiosk
kiosk() {
  baslik "kiosk çalışma zamanı"
  if [ ! -x "$VENV/bin/python" ]; then
    ok "sanal ortam oluşturuluyor: $VENV"
    "$PYTHON" -m venv "$VENV" || { hata "venv oluşturulamadı"; return 1; }
  fi
  ok "pip güncelleniyor"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  ok "bağımlılıklar: kiosk/requirements.txt + paho-mqtt"
  "$VENV/bin/python" -m pip install -q -r kiosk/requirements.txt paho-mqtt || { hata "pip kurulumu başarısız"; return 1; }

  # ESKİ HATA: yalnız `web/dist/index.html` YOKSA derliyordu → kaynak değişse bile "mevcut" deyip
  # eski paket kalıyordu (kullanıcı güncellemeyi göremedi, beyaz ekran sürdü).
  # Artık: kaynak dosyalar dist'ten YENİYSE yeniden derler; başarısızlık SESSİZ değil.
  if [ -f web/package.json ]; then
    YENI_KAYNAK="$(find web/src web/index.html web/package.json web/vite.config.ts web/tsconfig.json \
        -newer web/dist/index.html -type f 2>/dev/null | head -1 || true)"
    if [ ! -f web/dist/index.html ] || [ -n "$YENI_KAYNAK" ]; then
      ok "web arayüzü derleniyor${YENI_KAYNAK:+ (kaynak değişmiş: ${YENI_KAYNAK#web/})}"
      if ! ( cd web
             NODE_ENV=development npm ci --include=dev >/dev/null 2>&1 \
               || NODE_ENV=development npm install --include=dev >/dev/null 2>&1
             NODE_ENV=development npm run build ); then
        hata "web derlemesi BAŞARISIZ — tarayıcı modu eski paketle çalışır"
        return 1
      fi
      # damga: hangi commit'in derlendiğini cihazda görebilelim (--tani yazar)
      printf '{"git": "%s", "zaman": "%s"}\n' \
        "$(git -C "$KOK" rev-parse --short HEAD 2>/dev/null || echo '-')" \
        "$(date -Iseconds)" > web/dist/surum.json
      ok "web derlemesi tamam (surum.json yazıldı)"
    else
      ok "web derlemesi güncel"
    fi
  fi

  ok "hazır. Başlatmak için:"
  echo "     cd kiosk && .venv/bin/python tools/tarayici_kiosk.py --tani   # ön kontrol"
  echo "     cd kiosk && .venv/bin/python main.py                          # Qt modu"
}

# ------------------------------------------------------------------ panel
panel() {
  baslik "yönetim paneli"
  if [ ! -f panel/.env.local ]; then
    if [ -f panel/.env.ornek ]; then
      cp panel/.env.ornek panel/.env.local
      uyar "panel/.env.local oluşturuldu — AWS/Cognito değerlerini doldurun (VITE_*)"
      uyar "MQTT için: VITE_MQTT_URL / VITE_MQTT_KONU / VITE_MQTT_KULLANICI / VITE_MQTT_PAROLA"
    else
      hata "panel/.env.ornek bulunamadı"; return 1
    fi
  else
    ok "panel/.env.local mevcut"
  fi
  ok "npm bağımlılıkları (dev dahil)"
  ( cd panel && NODE_ENV=development npm ci --include=dev >/dev/null 2>&1 || NODE_ENV=development npm install --include=dev >/dev/null 2>&1 ) \
    || { hata "panel npm kurulumu başarısız"; return 1; }
  ok "panel derleniyor"
  ( cd panel && NODE_ENV=development npm run build >/dev/null 2>&1 ) || { hata "panel derlemesi başarısız"; return 1; }
  ok "hazır. Yayınlamak için: ./panel/infra/yayinla.sh (AWS yayın anahtarı gerekir)"
}

# ------------------------------------------------------------------ broker
broker() {
  baslik "MQTT broker (VPS)"
  if [ "$(id -u)" -ne 0 ]; then
    hata "bu komut sunucuda ROOT olarak çalışır"
    echo "     ssh ubuntu@<IP>  →  cd yourkiosk && sudo bash deploy/mosquitto/kur.sh --host <alan-adı> --eposta <e-posta>"
    return 2
  fi
  bash "$KOK/deploy/mosquitto/kur.sh" "$@"
}

# ------------------------------------------------------------------ docker
docker_kur() {
  baslik "Docker ile çalıştırma"
  if ! command -v docker >/dev/null 2>&1; then hata "docker kurulu değil"; return 1; fi
  if docker compose version >/dev/null 2>&1; then DC="docker compose"; elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; else hata "docker compose yok"; return 1; fi
  [ -f web/dist/index.html ] || uyar "web/dist yok — imaj içinde derlenmeyecek, önce ./kur.sh kiosk"
  ok "imaj derleniyor (ilk seferde chromium indirilir, birkaç dakika)"
  $DC build || { hata "imaj derlenemedi"; return 1; }
  ok "başlatılıyor"
  $DC up -d || { hata "başlatılamadı"; return 1; }
  $DC ps
  echo
  echo "  günlük: docker compose logs -f kiosk"
  echo "  durdur: docker compose down"
}

case "${1:-}" in
  kontrol) kontrol ;;
  kiosk)   kiosk ;;
  panel)   panel ;;
  broker)  shift; broker "$@" ;;
  docker)  docker_kur ;;
  hepsi)   kiosk; panel; kontrol ;;
  ""|-h|--help|help)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *) hata "bilinmeyen komut: $1"; sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
