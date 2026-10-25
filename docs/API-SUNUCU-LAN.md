# API sunucusu — LAN'dan erişim (güvenli yapılandırma)

**Durum:** Open WebUI (kullanıcının kendi bilgisayarında) Hermes ajanına LAN üzerinden bağlanacak.
Bu belge, o erişimin **açık ama sınırlı** olmasını sağlayan yapılandırmayı ve gerekçesini yazar.

## 1. Neden LAN'a açılıyor

`hermes` API sunucusu varsayılan olarak yalnız `127.0.0.1:8642` dinler. İstemci **başka bir
bilgisayarda** olduğu için üç seçenek var:

| Seçenek | Durum | Değerlendirme |
|---|---|---|
| **LAN'a bağla + kaynak IP izin listesi** | ✅ seçilen | Tek komut, ek servis yok; aynı ev/ofis ağında risk yönetilebilir |
| Tailscale/WireGuard tüneli | ⏳ yükseltme yolu | Anahtar ağ katmanında da korunur; yeni bir bağımlılık + her cihaza istemci |
| Port yönlendirme (internete açma) | ❌ yasak | Bu uç terminal yetkili ajan çalıştırır; internete açmak = uzaktan kod çalıştırma yüzeyi |

**Anahtar cümle:** bu uç "sohbet" ucu değil, **terminal yetkili ajan** ucudur. Anahtarı bilen kişi
o makinede komut çalıştırabilir. Bu yüzden anahtar güçlü olmalı **ve** kaynak IP sınırlanmalı.

## 2. Üç katmanlı savunma

| Katman | Ne yapar | Zorunlu mu |
|---|---|---|
| **Anahtar** (`API_SERVER_KEY`) | 32 bayt rastgele, `~/.config/hermes-secrets/api-server.key` (0600) + `.env` | ✅ zorunlu — Hermes, 16 karakterden kısa/placeholder anahtarla sunucuyu **başlatmaz** |
| **Kaynak IP** (nftables) | `8642/tcp` yalnız izinli adreslerden; diğerleri düşer | ✅ zorunlu (LAN'a açıyorsan) |
| **Taşıma şifrelemesi** | WireGuard/Tailscale ya da TLS'li ters vekil (`Caddy`) | ⏳ ortak Wi-Fi'de önerilir (HTTP'de anahtar düz metin gider) |

## 3. Kurulum (i5 / i3 makinesinde)

```bash
cd <depo>
git pull

# 1) kuru kontrol: mevcut durum ne?
./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol

# 2) yapılandır — Open WebUI'nin çalıştığı BİLGİSAYARIN LAN IP'sini yaz
./otomasyon/betik/api-sunucu-sertlestir.sh --kaynak-ip 192.168.1.30 --anahtar-yenile
```

Betik şunları yapar: güçlü anahtar üretir → `API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0`,
`API_SERVER_PORT=8642` yazar → nftables kural dosyasını üretir → gateway'i yeniden başlatır →
kendini sınar (anahtarsız 401, anahtarlı 200).

Kuralı uygulamak `sudo` ister (betik kendisi çalıştırmaz, komutu yazdırır):

```bash
sudo nft -f ~/.local/state/yourkiosk-otomasyon/api-sunucu.nft
# kalıcı (açılışta yüklensin):
sudo install -D -m644 ~/.local/state/yourkiosk-otomasyon/api-sunucu.nft /etc/nftables.d/60-hermes-api.nft
sudo systemctl enable --now nftables
```

> **Docker notu:** Open WebUI **aynı makinede** konteynerde çalışıyorsa istekler köprü adresinden
> gelir → `--kaynak-ip 172.17.0.1` (ya da `--kaynak-ip 172.18.0.0/16`).

## 4. Open WebUI ayarı

| Alan | Değer |
|---|---|
| Base URL | `http://<i5-LAN-IP>:8642/v1` |
| API Key | `cat ~/.config/hermes-secrets/api-server.key` (o makinede) |
| Model | `/v1/models` ne döndürüyorsa (varsayılan profil modeli) |

## 5. Doğrulama (üç ayrı yerden)

```bash
# a) sunucunun kendisinde
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8642/v1/models          # 401 beklenir
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $(cat ~/.config/hermes-secrets/api-server.key)" \
     http://127.0.0.1:8642/v1/models                                               # 200 beklenir

# b) Open WebUI'nin çalıştığı bilgisayardan (izinli)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer <anahtar>" http://<i5-ip>:8642/v1/models  # 200

# c) İZİNSİZ bir makineden (kontrol noktası)
curl -m 3 -o /dev/null -w '%{http_code}\n' http://<i5-ip>:8642/v1/models          # 000/timeout beklenir
```

(c) 401 dönüyorsa **kaynak IP kuralı uygulanmamış** demektir: port hâlâ herkese açık, yalnız anahtar
koruyor. Bu durumu kabul etme.

## 6. Neden nöbetçi ile aynı makinede sorun oluyor

i5 makinesi iki iş yapıyor: (a) Open WebUI sohbetleri (`/v1`), (b) `nobetci.py` → `hermes chat
--oneshot` ile PR incelemesi. İkisi **aynı gateway sürecini, aynı CPU'yu, aynı model kotasını ve
aynı `max_concurrent_runs` sınırını** paylaşır. 25 Ekim kanıtı: 3 PR tek oturuma verildi, oturum
1200 sn'de `çıkış 124` ile öldü, karar yazılmadı, PR'lar saatlerce bekledi.

Ayrıştırma (önerilen, ayrı PR):

```bash
hermes profile create guvenlik                     # kendi config/memory/oturum sayacı
hermes -p guvenlik config set platforms.api_server.enabled false
# nobetci-kur.sh içindeki ExecStart'ı şu hale getir:
#   hermes -p guvenlik chat --query-file … --oneshot …
# ve servise kaynak sınırı ekle:
#   Nice=10
#   CPUWeight=50
```

Böylece Open WebUI yükü nöbetçinin oturum tavanını ve CPU'sunu yemez; profil çökse API etkilenmez.

## 7. Kontrol noktaları

```bash
./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol
```

| # | Kontrol | Beklenen |
|---|---|---|
| 1 | `API_SERVER_ENABLED` | `true` |
| 2 | Anahtar uzunluğu | ≥ 32 karakter |
| 3 | Dinlenen adres | LAN IP (`0.0.0.0`) |
| 4 | nftables `inet hermes_api` tablosu | var |
| 5 | `8642` dinleniyor | evet |
| 6 | Anahtar dosyası | `~/.config/hermes-secrets/api-server.key` (0600) |

## 8. Bilinen tuzak

`API_SERVER_KEY` 16 karakterden kısaysa Hermes sunucuyu **başlatmaz** ve gateway "DEGRADED" olur:

```
[Api_Server] Refusing to start: API_SERVER_KEY is a placeholder or too short (<16 chars).
```

Bu durumda `8642` hiç dinlenmez; istemci "bağlanamıyorum" der. Çözüm: `--anahtar-yenile`.
