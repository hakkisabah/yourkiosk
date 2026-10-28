# API sunucusu — Open WebUI bağlantısı (güvenlik duvarı kullanmadan)

**Hedef:** Open WebUI, Hermes ajanına bağlanacak. Hermes API sunucusu bu makinenin **docker0
köprüsünde** (`172.17.0.1:8642`; konteyner yoksa `127.0.0.1:8642`) dinler ve gelen isteği
**terminal yetkili bir ajan** olarak çalıştırır — yani anahtarı bilen kişi o makinede kabuk
komutu çalıştırabilir. LAN'a açmak bilinçli bir `--kabul-et-lan` kararıdır.

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
cd <proje-kökü>          # ör. ~/evrim_otonom/yourkiosk — klon yolunuz makineye göre değişir
git pull

./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol   # mevcut durum
./otomasyon/betik/api-sunucu-sertlestir.sh --kuru      # ne yapılacağını göster
./otomasyon/betik/api-sunucu-sertlestir.sh             # uygula (anahtar + docker0)
```

> Dinleme adresi **beyaz listede**: `127.0.0.1` · `172.17.0.1` · `172.18.0.1`. `0.0.0.0` yalnız
> `--kabul-et-lan` ile yazılır; yazım hatalı adresler reddedilir (çıkış 2). Anahtar **komut
> satırına** hiç verilmez: dosyadan okunur ve `.env`'e yazılır (argv sızıntısı yok).

### 3a. Bu makinede seçilen kurulum: LAN'a açık (operatör onaylı)

Geliştirme makinesinde Hermes istemcileri **başka makinelerden** bağlanıyor → sunucu
`0.0.0.0:8642` dinliyor. Bu bilinçli bir operatör kararıdır ve **kayda geçer**: uygulama anında
`~/.config/hermes-secrets/api-server.lan-onay` dosyası yazılır (0600). `--kontrol` bu dosyayı
görürse `0.0.0.0` satırı ✗ değil **✓ "LAN'a açık (operatör onaylı)"** olur; dosya yoksa ✗ kalır.
Geri alma (`--dinle 172.17.0.1` / `127.0.0.1`) kaydı **siler** → karar görünür ve geri alınabilir.

```bash
./otomasyon/betik/api-sunucu-sertlestir.sh --dinle 0.0.0.0 --kabul-et-lan   # onay kaydını yazar
./otomasyon/betik/api-sunucu-sertlestir.sh --kontrol                        # ✓ LAN'a açık (operatör onaylı)
```

> `0.0.0.0`'da uç **ağdan erişilebilir** ve terminal yetkilidir: erişim yalnız `API_SERVER_KEY`
> ile sınırlıdır. Ağ değişirse anahtarı döndürün (`--anahtar-yenile`). Güvenlik sınırı: aynı
> LAN'daki başka bir kullanıcı anahtarı ele geçirirse kabuk komutu çalıştırabilir — kabul edilen
> risk ve gerekçesi `docs/GUVENLIK-BAGLAM.md` §5'te.

> **Open WebUI:** bu makinede operatör kararıyla `-p 0.0.0.0:3000` yayınında ve **değiştirilmeyecek**
> (ağdan erişim gerekiyor). Aşağıdaki `-p 127.0.0.1:3000:8080` önerisi yeni/temiz kurulum içindir;
> çalışan konteynerde operatör onayı olmadan yeniden oluşturmayın.

Betik gateway'i **yeniden başlatmaz**; ayrı bir kabukta:

```bash
hermes gateway restart
```

Open WebUI'yi başlat — imaj etiketini **sabitle** ve arayüz portunu **yalnız loopback'e** yayınla:

```bash
# ':main' her yeniden başlatmada denetlenmemiş upstream kod çekebilir → sürüm etiketi seçin
docker pull ghcr.io/open-webui/open-webui:<SABIT-ETIKET>
docker run -d --name open-webui --restart unless-stopped \
  -p 127.0.0.1:3000:8080 \
  -v open-webui:/app/backend/data -e ENABLE_SIGNUP=false \
  ghcr.io/open-webui/open-webui:<SABIT-ETIKET>
```

`-p 127.0.0.1:3000:8080` arayüzü LAN'a kapatır (tarayıcıdan `http://localhost:3000`);
`-p 3000:8080` yazılırsa Open WebUI **tüm ağlara** açılır.

Open WebUI → **Ayarlar → Bağlantılar → OpenAI API**:

| Alan | Değer |
|---|---|
| Base URL | `http://172.17.0.1:8642/v1` |
| API Key | `cat ~/.config/hermes-secrets/api-server.key` |

> **Neden TLS yok?** `172.17.0.1` bir fiziksel ağ kartı değil, bu makinenin **docker0 köprüsü**:
> paket makineden çıkmaz, LAN'a görünmez. Anahtarın köprüde açık gitmesi bu yüzden kabul edilmiş
> bir risktir (`docs/GUVENLIK-BAGLAM.md` §5). Yine de anahtarı bir ağdan geçirmeniz gerekirse
> (başka makine, tünel) TLS sonlandıran bir vekil kullanın — düz `http://` ile taşımayın.

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

## 6. Nöbetçi ile aynı gateway'i paylaşma sorunu — ÇÖZÜLDÜ (ayrı profil)

i5 makinesi hem Open WebUI sohbetlerini hem `nobetci.py` → `hermes chat --oneshot` PR incelemesini
aynı gateway sürecinde çalıştırırsa: aynı CPU, aynı model kotası, aynı `max_concurrent_runs`.
25 Ekim kanıtı: 3 PR tek oturuma verildi, oturum `çıkış 124` ile öldü, PR'lar saatlerce bekledi.

Çözüm (uygulandı — `nobetci.py --profil`, `nobetci-kur.sh --profil`):

```bash
hermes profile create guvenlik
hermes -p guvenlik config set platforms.api_server.enabled false
bash otomasyon/nobetci-kur.sh i5 --profil guvenlik
```

Unit dosyasına yazılanlar: `Environment=NOBETCI_PROFIL=guvenlik`, `Nice=10`, `CPUWeight=50`,
`ExecStart=… nobetci.py --rol i5 --aralik 15 --profil guvenlik`. Nöbetçi artık `hermes -p guvenlik
chat …` çağırır: kendi config'i, kendi oturum sayacı, kendi model anahtarı. Profil yoksa kurulum
**reddedilir** (sessizce varsayılana düşmez). Ayrıntı: `otomasyon/NOBETCI.md` §Ayrı profil.
