# Geçiş Runbook'u (makineler)

Bu adımlar **elle** çalıştırılır; DSH oturumundan systemd bus'a erişilemiyor.
Her adımın altında beklenen çıktı var.

## 1. aceri5 — servisleri durdur

```bash
systemctl --user disable --now otonom-tik.timer otonom-bekci.timer
systemctl --user stop otonom-tik.service otonom-bekci.service 2>/dev/null
systemctl --user list-timers 'otonom-*' --no-pager
```
Beklenen: "0 timers listed" veya yalnız geçmiş kayıt.

## 2. i5 — nöbetçiyi durdur

```bash
systemctl --user disable --now yourkiosk-nobetci.service
systemctl --user status yourkiosk-nobetci.service --no-pager | head -3
```
Beklenen: `inactive (dead)`.

## 3. i3 — nöbetçiyi durdur

Aynı komutlar (i3 makinesinde).

## 4. aceri5 — ajan arşivi (silmeden önce)

```bash
mkdir -p ~/yedekler/yourkiosk-2026-11-13
tar -czf ~/yedekler/yourkiosk-2026-11-13/agents-tam.tgz -C ~ .agents
tar -czf ~/yedekler/yourkiosk-2026-11-13/dsh-tam.tgz -C ~ .dsh
sha256sum ~/yedekler/yourkiosk-2026-11-13/agents-tam.tgz ~/yedekler/yourkiosk-2026-11-13/dsh-tam.tgz
```

## 5. Plan dosyasını taşı

```bash
mv /tmp/PLAN-dsh-agents-2026-11-13.md ~/yedekler/PLAN-dsh-agents-2026-11-13.md
ls -lh ~/yedekler/PLAN-dsh-agents-2026-11-13.md
```

## 6. Hermes hafızasını arşivle ve sil

```bash
mkdir -p ~/yedekler/yourkiosk-2026-11-13/agents-eski
mv ~/.agents/memory/HERMES-USER.md ~/.agents/memory/HERMES-MEMORY.md \
   ~/yedekler/yourkiosk-2026-11-13/agents-eski/ 2>/dev/null || true
ls ~/.agents/memory
```
Beklenen: yalnız yeni/kısa dosyalar kalır.

## 7. Skill'leri yeni pakete kopyala

```bash
mkdir -p /home/hakki/evrim_otonom/yourkiosk/agents/skills
cp -a ~/.agents/skills/. /home/hakki/evrim_otonom/yourkiosk/agents/skills/
find /home/hakki/evrim_otonom/yourkiosk/agents/skills -name SKILL.md | wc -l
```
Beklenen: 20+ skill. Hermes atıflı olanlar bir sonraki adımda ayıklanır.

## 8. Doğrulama

```bash
systemctl --user list-units --all | grep -Ei 'otonom|yourkiosk' || echo temiz
ls ~/.local/state/yourkiosk-otonom ~/.local/share/yourkiosk-otonom 2>/dev/null
```
Beklenen: servis yok; dizinler arşivlendikten sonra silinecek.
