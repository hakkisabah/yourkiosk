# Nöbetçi — olay güdümlü i5/i3 (cron yerine)

## Neden değişti

| | Eski (cron 30 dk) | Yeni (nöbetçi) |
|---|---|---|
| Gecikme | 0–30 dakika | **≤ 15 saniye** |
| Boşta oturum | Her turda bir oturum (iş olmasa da) | **0** |
| İş başına oturum | Her tur ayrı | Olay başına **1** (tur içinde tüm PR'lar) |
| 7/24 | cron çalışıyorsa | systemd `Restart=always` + `enable-linger` |
| Maliyet | Boş turlar token/oturum üretir | Boşta yalnız 304 yanıtı (ücretsiz) |

## Nasıl çalışır

```
[GitHub]  ←  ETag/If-None-Match (15 sn)  ←  nobetci.py --rol i5
   │                                              │
   │ değişiklik varsa                             │ iş listesi boş → uyu (0 oturum)
   ▼                                              ▼
açık PR'ların head sha + durum kontrolleri   iş listesi dolu → TEK `hermes chat --oneshot`
                                                  → listedeki tüm PR'lar işlenir
                                                  → yaz.py ile durum/yorum/etiket
```

- **i5** işi: `guvenlik/inceleme` durumu **olmayan** (ya da `guvenlik/sorun` etiketli) PR'ları inceler.
- **i3** işi: i5 onayı (`guvenlik/inceleme=success`) olup **kararı yazılmamış** PR'lara karar verir,
  `--birlestir --cift-onay` ile birleştirir.
- İki makine birbirini **commit status** üzerinden görür; ayrı bir kuyruk/veritabanı yok.
- Aynı anda iki nöbetçi çalışmasın diye `flock` kilidi var (`nobetci-<rol>.lock`).

## Neden webhook değil?

Hermes'in webhook altyapısı (`hermes webhook subscribe`, port 8644) **gelen** HTTP isteği ister.
i5/i3 ev/ofis ağında, dışarıdan erişilebilir adresleri yok (NAT). Gerçek push için üç seçenek var:

1. **Tünel** (cloudflared/ngrok) + webhook → en hızlı (~1 sn), ama üçüncü taraf servis + yapılandırma.
2. **Self-hosted GitHub Actions runner** → GitHub işi doğrudan makineye iter (~1–2 sn), gelen port
   gerekmez; kurulum token'ı **GitHub arayüzünden** alınır (Settings → Actions → Runners → New
   self-hosted runner). Genel (public) depoda fork PR'ları makinede kod çalıştırabileceği için
   `if: github.event.pull_request.head.repo.full_name == github.repository` şartı zorunludur.
3. **Nöbetçi (bu çözüm)** → 15 sn gecikme, ek servis yok, NAT sorunu yok, kurulumu 1 komut.

15 saniye, PR akışı için pratikte "anlık" sayılır; bu yüzden nöbetçi varsayılan seçildi.

## Kurulum (her makinede bir kez)

```bash
cd ~/projeler/yourkiosk && git pull

bash otomasyon/nobetci-kur.sh i5          # i5 makinesinde
bash otomasyon/nobetci-kur.sh i3          # i3 makinesinde

# eski cron görevini kaldır (artık gerekmiyor)
bash otomasyon/nobetci-kur.sh i5 --cron-kaldir
```

Kurulum sonrası:

```bash
bash otomasyon/nobetci-kur.sh i5 --durum          # servis + nöbetçi durumu
tail -f ~/.local/state/yourkiosk-otomasyon/nobetci-i5.log
journalctl --user -u yourkiosk-nobetci -f
```

## Ayarlar

| Ayar | Yer | Varsayılan |
|---|---|---|
| Yoklama aralığı | `nobetci-kur.sh` içindeki `--aralik` | 15 sn |
| Tur başına PR | `--limit` | 8 |
| Oturum zaman aşımı | `--zaman-asimi` | 1860 sn (tavan 120 × 15 sn + 60 sn; türetilir) |
| Tur tavanı | `nobetci.py` `OTURUM_TUR_TAVANI` | 120 tur (bütçe darsa kısılır) |
| Depo | `Environment=GITHUB_DEPO` | `hakkisabah/yourkiosk` |
| Token | `~/.config/hermes-secrets/github-yourkiosk.token` | — |

## Sorun giderme

| Belirti | Bak |
|---|---|
| Servis düşüyor | `journalctl --user -u yourkiosk-nobetci -n 50` |
| "iş yok" ama PR bekliyor | `./otomasyon/nobetci --rol i5 --bir-kez --kuru` → iş listesi |
| Oturum açılıyor ama durum yazılmıyor | `nobetci-i5.log` sonunda oturum çıktısı; `hermes chat -q` çalışıyor mu |
| Aynı PR'a tekrar tekrar oturum | i5 durumu yazamıyor olabilir; `yaz.py` çıktısına bak |
| Oturum kapanınca duruyor | `loginctl enable-linger $USER` — bazı sistemlerde polkit onayı ister: `sudo loginctl enable-linger $USER` (kurulum betiği uyarı verir, hata değil) |

## Sınırlar

- GitHub API oranı: kimlik doğrulamalı 5.000 istek/saat; koşullu isteklerde 304'ler sayılmaz → 15 sn'de
  bir yoklama ≈ 240 istek/saat (yalnız PR listesi) + PR başına 1 durum isteği (o da ETag'li).
- Nöbetçi **kod yazmaz**; yalnız inceleme/karar/merge yapar (i5 ve i3 promptlarındaki sınırlar geçerli).
- Token'da `Administration` izni yok — gerekmiyor; durum/yorum/etiket/merge için `Contents`,
  `Pull requests`, `Commit statuses`, `Issues` yeterli.
