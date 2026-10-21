#!/usr/bin/env bash
# TEK KOMUT KURULUM (i5 / i3) — ortam denetimi + sarmalayıcı betikler + cron komutu.
#
#   bash otomasyon/kur.sh i5            # denetler, ~/.hermes/scripts betiklerini kurar, komutu YAZDIRIR
#   bash otomasyon/kur.sh i5 --cron     # ayrıca 'hermes cron create' ile görevi oluşturur
#   bash otomasyon/kur.sh i3
#
# Hiçbir şeyi silmez; tekrar çalıştırmak güvenlidir (betikler üzerine yazılır, cron varsa atlanır).
set -uo pipefail

ROL="${1:-}"
[ "$ROL" = "i5" ] || [ "$ROL" = "i3" ] || { echo "kullanım: bash otomasyon/kur.sh i5|i3 [--cron]" >&2; exit 2; }
CRON_ISTENDI=0
for arg in "$@"; do [ "$arg" = "--cron" ] && CRON_ISTENDI=1; done

DEPO="$(cd "$(dirname "$0")/.." && pwd)"
BETIK="$DEPO/otomasyon/betik"
PROMPT="$DEPO/otomasyon/prompt/i5-guvenlik.md"
[ "$ROL" = "i3" ] && PROMPT="$DEPO/otomasyon/prompt/i3-karar.md"
IZLE="$([ "$ROL" = "i3" ] && echo i3-durum.sh || echo i5-imza.sh)"
ZAMAN="30m"
AD="$([ "$ROL" = "i3" ] && echo 'i3 karar' || echo 'i5 guvenlik')"

echo "=== yourkiosk $ROL kurulumu ==="
echo "depo : $DEPO"

# 1) ortam denetimi (eksik varsa da devam: eksikleri yazdırır)
python3 "$BETIK/ortam-kontrol.py" --rol "$ROL" --depo "$DEPO" || true
echo

# 2) sarmalayıcı betikler
mkdir -p "$HOME/.hermes/scripts"
[ -f "$BETIK/topla.py" ] || { echo "HATA: $BETIK/topla.py yok — depo yolu yanlış: $DEPO" >&2; exit 4; }

cat > "$HOME/.hermes/scripts/i5-imza.sh" <<EOF
#!/usr/bin/env bash
# üretildi: kur.sh — $DEPO
TOPLA="$BETIK/topla.py"
[ -f "\$TOPLA" ] || { echo "HATA: \$TOPLA yok (sarmalayıcı bayat) — bash $DEPO/otomasyon/kur.sh ${ROL} ile yenileyin" >&2; exit 3; }
exec python3 "\$TOPLA" --depo "$DEPO" --imza
EOF
cat > "$HOME/.hermes/scripts/i3-durum.sh" <<EOF
#!/usr/bin/env bash
TOPLA="$BETIK/topla.py"
[ -f "\$TOPLA" ] || { echo "HATA: \$TOPLA yok (sarmalayıcı bayat) — bash $DEPO/otomasyon/kur.sh ${ROL} ile yenileyin" >&2; exit 3; }
exec python3 "\$TOPLA" --depo "$DEPO" --imza-prlar
EOF
cat > "$HOME/.hermes/scripts/otomasyon-topla.sh" <<EOF
#!/usr/bin/env bash
TOPLA="$BETIK/topla.py"
[ -f "\$TOPLA" ] || { echo "HATA: \$TOPLA yok (sarmalayıcı bayat) — bash $DEPO/otomasyon/kur.sh ${ROL} ile yenileyin" >&2; exit 3; }
exec python3 "\$TOPLA" --depo "$DEPO" --cikti /tmp/otomasyon-paket.json
EOF
chmod +x "$HOME/.hermes/scripts/i5-imza.sh" "$HOME/.hermes/scripts/i3-durum.sh" "$HOME/.hermes/scripts/otomasyon-topla.sh"
# İLK KOŞU: son nokta dosyasını sıfırla → i5 son commit'i de inceler.
# (Aksi hâlde "değişiklik yok" deyip hiç yorum/durum yazmaz; kullanıcı "konuşmadı" sanır.)
mkdir -p "$HOME/.local/state/yourkiosk-otomasyon"
rm -f "$HOME/.local/state/yourkiosk-otomasyon/son-sha"
echo "ilk koşu son commit'i inceleyecek (son nokta sıfırlandı)"

echo "sarmalayıcılar kuruldu: $HOME/.hermes/scripts/{i5-imza,i3-durum,otomasyon-topla}.sh"

# 3) izleme betiği tek satır üretiyor mu? (cron monitor için kritik)
IMZA="$(bash "$HOME/.hermes/scripts/$IZLE" 2>/dev/null | head -1)"
if [ -n "$IMZA" ]; then
  echo "monitor çıktısı: $IMZA ✓"
elif [ "$ROL" = "i3" ]; then
  echo "monitor çıktısı: (boş — 'guvenlik/sorun' etiketli açık PR yok; bu NORMAL, ajan çalışmaz)"
else
  echo "monitor çıktısı BOŞ ✗ → git erişimi/token sorunu olabilir (yukarıdaki denetime bakın)"
fi

# 4) cron komutu
CRON_KOMUT=(hermes cron create "$ZAMAN" "$(cat "$PROMPT")" \
  --name "$AD" --workdir "$DEPO" --script otomasyon-topla.sh \
  --monitor-script "$IZLE" --deliver local)

echo
echo "=== sıradaki adım: cron görevi ==="
if [ "$CRON_ISTENDI" -eq 1 ]; then
  if ! command -v hermes >/dev/null 2>&1; then
    echo "hermes CLI bulunamadı; aşağıdaki komutu Hermes'in kurulu olduğu kabukta çalıştırın:" >&2
    printf '%q ' "${CRON_KOMUT[@]}"; echo
    exit 3
  fi
  if hermes cron list 2>/dev/null | grep -q "$AD"; then
    echo "'$AD' görevi zaten var → atlandı (düzenlemek için: hermes cron edit)"
  else
    "${CRON_KOMUT[@]}" && echo "görev oluşturuldu: $AD ($ZAMAN)"
  fi
else
  echo "Şunu çalıştırın (ya da dashboard'dan aynı alanlarla oluşturun):"
  echo
  cat <<KOMUT
  hermes cron create '$ZAMAN' "\$(cat '$PROMPT')" \\
    --name "$AD" --workdir "$DEPO" \\
    --script otomasyon-topla.sh --monitor-script "$IZLE" --deliver local
KOMUT
  echo
  echo "Tümünü otomatik yapmak için: bash otomasyon/kur.sh $ROL --cron"
fi
