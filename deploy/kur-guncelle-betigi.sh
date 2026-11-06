#!/usr/bin/env bash
# GÜNCELLEME BETİĞİ KOPYASINI KUR — root olarak, DEPLOY adımının parçası.
#
#   sudo deploy/kur-guncelle-betigi.sh
#
# NEDEN AYRI BİR ADIM (i5 bulgusu 25.10 19:18):
#   `yourkiosk-guncelle.service` root olarak /usr/local/lib/yourkiosk/guncelle.sh KOPYASINI
#   çalıştırır. Kopyayı güncelleme koşusu sırasında depodaki dosyadan yenilemek, `kiosk`
#   kullanıcısının YAZABİLDİĞİ içeriğin root tarafından çalıştırılması olurdu (yerel yetki
#   yükseltmesi). Ayrıca birimde ProtectSystem=full + ReadWritePaths=/opt/yourkiosk olduğu için
#   /usr altına yazma zaten EROFS ile düşer; yani "kendini yenileme" üretimde hiç çalışmıyordu.
#   Bu yüzden betik kopyası yalnız burada, bilinçli bir root adımıyla, DEPO TEMİZKEN kurulur.
set -euo pipefail

HEDEF="${HEDEF:-/usr/local/lib/yourkiosk/guncelle.sh}"
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KAYNAK="$KOK/deploy/guncelle.sh"

[[ $EUID -eq 0 ]] || { echo "✗ root gerekli: sudo $0" >&2; exit 2; }
[[ -f "$KAYNAK" ]] || { echo "✗ kaynak yok: $KAYNAK" >&2; exit 2; }

# 1) Sözdizimi: bozuk betiği root olarak kurma.
bash -n "$KAYNAK"

# 2) Depo temizliği: kurulan kopya, commit'lenmiş sürümle aynı olmalı.
#    (kirli ağaçta kurulan kopya, sonradan 'bu nereden geldi' sorusunu cevapsız bırakır)
if command -v git >/dev/null 2>&1 && git -C "$KOK" rev-parse --git-dir >/dev/null 2>&1; then
  # `git diff --quiet` YALNIZ çalışma ağacı ↔ INDEX farkına bakar; `git add` ile stage edilen
  # değişiklik "temiz" görünür ve root:root kurulur (i5 bulgusu 26.10, bu head'de ölçüldü).
  # `status --porcelain` staged + unstaged + untracked hepsini kapsar.
  KIRLI="$(git -C "$KOK" status --porcelain -- deploy/guncelle.sh)"
  if [ -n "$KIRLI" ]; then
    echo "✗ deploy/guncelle.sh commit'lenmemiş değişiklik içeriyor (staged olanlar dahil):" >&2
    echo "$KIRLI" | sed 's/^/    /' >&2
    echo "  Önce commit edin (git add + git commit), sonra bu adımı tekrarlayın." >&2
    exit 1
  fi
  SURUM="$(git -C "$KOK" rev-parse --short HEAD)"
else
  SURUM="bilinmiyor (git yok)"
fi

install -Dm0755 -o root -g root "$KAYNAK" "$HEDEF"

# 3) Doğrulama: bayt bayt aynı olmalı.
cmp -s "$KAYNAK" "$HEDEF" || { echo "✗ kopya doğrulanamadı: $HEDEF" >&2; exit 1; }

echo "✓ güncelleme betiği kuruldu: $HEDEF (root:root 0755, kaynak sürüm $SURUM)"
echo "  birim bu kopyayı çalıştırır: systemctl cat yourkiosk-guncelle.service | grep ExecStart"
echo "  değişiklik sonrası: sudo systemctl daemon-reload (birim dosyası da değiştiyse)"
