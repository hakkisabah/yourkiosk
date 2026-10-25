# API sunucusu — Open WebUI bağlantısı (güvenlik duvarı kullanmadan)

**Hedef:** Open WebUI, Hermes ajanına bağlanacak. Hermes API sunucusu `127.0.0.1:8642` dinler ve
gelen isteği **terminal yetkili bir ajan** olarak çalıştırır — yani anahtarı bilen kişi o makinede
kabuk komutu çalıştırabilir.

## 1. Neden güvenlik duvarı yaklaşımı TERK EDİLDİ

İlk sürüm (v1) portu `0.0.0.0`'a açıp kaynağı **nftables** ile sınırlıyordu. Sonuç:

- Yanlış kaynak IP yazıldı → erişim tamamen kesildi,
- "Kural mı, servis mi, anahtar mı?" ayırt edilemedi (uzaktan teşhis imkânsız),
- Betiğin `sudo`'lu kalıcı kural kurulumu makineyi kilitleme riski taşıdı.

**Kural:** bu uç için güvenlik duvarı **kullanılmaz**. Erişim, soketin bağlandığı **adres** ile
sınırlanır. Yanlış yapılandırma en kötü ihtimalle "erişemiyorum" olur — makine kilitlenmez.

## 2. Seçilen yöntem: docker0 köprüsü

```
[Open WebUI konteyneri]  →  172.17.0.1:8642  →  Hermes API (yalnız docker0'da dinler)
[LAN / başka makine]     →  ✗ ulaşamaz (172.17.0.0/16 bu makinenin dışına yönlendirilmez)
```

| Dinleme adresi | Kim erişir | Ne zaman kullan |
|---|---|---|
| `172.17.0.1` (docker0) | yalnız aynı makinedeki Docker konteynerleri | **Open WebUI konteynerde — önerilen** |
| `127.0.0.1` | yalnız bu makinedeki süreçler | konteyner yok, CLI/script istemcisi |
| `0.0.0.0` | **tüm ağ** | ❌ kullanma (terminal yetkili uç LAN'a açılmaz) |

Ek savunma: 32 bayt rastgele anahtar (`~/.config/hermes-secrets/api-server.key`, 0600).
Hermes, 16 karakterden kısa anahtarla sunucuyu **başlatmaz** (kendi koruması).

## 3. Kurulum

```bash
cd ~/evrim_otonom/yourkiosk && git pull

./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol   # mevcut durum
./otomasyon/betik/api-sunucu-sertlestir.sh --kuru      # ne yapılacağını göster
./otomasyon/betik/api-sunucu-sertlestir.sh             # uygula (anahtar + docker0)
```

Betik gateway'i **yeniden başlatmaz**; ayrı bir kabukta:

```bash
hermes gateway restart
```

Open WebUI'yi başlat:

```bash
docker run -d --name open-webui --restart unless-stopped -p 3000:8080 -v open-webui:/app/backend/data -e ENABLE_SIGNUP=false ghcr.io/open-webui/open-webui:main
```

Open WebUI → **Ayarlar → Bağlantılar → OpenAI API**:

| Alan | Değer |
|---|---|
| Base URL | `http://172.17.0.1:8642/v1` |
| API Key | `less ~/.config/hermes-secrets/api-server.key` |

> Open WebUI'yi **başka bir makinede** çalıştıracaksan `172.17.0.1` işe yaramaz (o adres yalnız
> bu makinenin konteyner ağında var). O durumda ya Open WebUI'yi bu makineye kur, ya da iki
> makineyi WireGuard/Tailscale ile bağlayıp `API_SERVER_HOST=<tünel-adresi>` kullan.

## 4. Doğrulama

```bash
# bu makinede
ss -tlnH 'sport = :8642'                                  # beklenen: 172.17.0.1:8642
curl -s -o /dev/null -w '%{http_code}\n' http://172.17.0.1:8642/v1/models        # 401
./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol      # tüm maddeler ✓

# konteyner içinden (köprüden gerçekten erişiliyor mu)
docker exec open-webui curl -s -o /dev/null -w '%{http_code}\n' http://172.17.0.1:8642/v1/models
```

## 5. Geri alma

nftables döneminden kalıntı varsa (tablo `inet hermes_api`, `/etc/nftables.d/60-hermes-api.nft`):

```bash
./otomasyon/betik/api-sunucu-geri-al.sh --kontrol                # durumu göster (değişiklik yok)
./otomasyon/betik/api-sunucu-geri-al.sh                          # tabloyu sil, ayarı 127.0.0.1'e al
./otomasyon/betik/api-sunucu-geri-al.sh --dinle 172.17.0.1       # geri al + docker köprüsüne bağla
```

Tek satırlık acil geri alma (betik yoksa):

```bash
sudo nft delete table inet hermes_api ; sudo rm -f /etc/nftables.d/60-hermes-api.nft
sudo nft list ruleset | head -20          # hermes_api YOK olmalı
```

`nftables` systemd servisi bu makinede **08 Ekim'den beri kapalı** (`disabled/inactive`); açılışta
kural yüklemez. `sudo systemctl disable --now nftables` yalnız servis bir ara açıldıysa gerekir.

## 6. Nöbetçi ile aynı gateway'i paylaşma sorunu (ayrı iş)

i5 makinesi hem Open WebUI sohbetlerini hem `nobetci.py` → `hermes chat --oneshot` PR incelemesini
aynı gateway sürecinde çalıştırır: aynı CPU, aynı model kotası, aynı `max_concurrent_runs`.
25 Ekim kanıtı: 3 PR tek oturuma verildi, oturum `çıkış 124` ile öldü, PR'lar saatlerce bekledi.

Ayrıştırma (ayrı PR):

```bash
hermes profile create guvenlik
hermes -p guvenlik config set platforms.api_server.enabled false
# nobetci-kur.sh ExecStart → hermes -p guvenlik chat --query-file … --oneshot …
# servise: Nice=10 · CPUWeight=50
```
